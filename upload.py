#!/usr/bin/env python3
"""Typora custom image uploader via Synology File Station API."""

from __future__ import annotations

import argparse
import mimetypes
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import requests
import yaml

CONFIG_ENV = "SYNO_UPLOAD_CONFIG"
SCRIPT_DIR = Path(__file__).resolve().parent
LAST_LOG = SCRIPT_DIR / "upload.last.log"

ERROR_HINTS = {
    105: "当前会话没有权限（检查账号对 remote_path 的读写权限）",
    106: "会话超时，请重试",
    107: "会话被重复登录中断",
    119: "无效会话（SID 未带到上传请求）",
    400: "账号不存在或密码错误",
    401: "账号已停用",
    402: "权限不足",
    403: "需要两步验证码（请在 config.yaml 填写 otp_code）",
    404: "两步验证失败",
    406: "必须绑定 OTP",
    407: "登录次数过多，账号已暂时锁定，请稍后再试",
    408: "密码已过期",
    409: "必须修改密码",
    410: "账号已锁定",
}


class SynologyError(RuntimeError):
    """Raised when DSM / File Station API returns an error."""


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
    try:
        with LAST_LOG.open("a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except OSError:
        pass


def fail(msg: str) -> int:
    """Log to stderr and stdout so Typora's validation dialog can show it."""
    log(msg)
    print(msg, flush=True)
    return 1


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SynologyError(f"配置文件不存在: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    required = ("nas_url", "username", "password", "remote_path", "public_base_url")
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise SynologyError(f"配置缺少字段: {', '.join(missing)}")
    data["nas_url"] = str(data["nas_url"]).rstrip("/")
    data["public_base_url"] = str(data["public_base_url"]).rstrip("/")
    data["remote_path"] = str(data["remote_path"]).rstrip("/") or "/"
    data.setdefault("verify_ssl", True)
    data.setdefault("overwrite", False)
    data.setdefault("date_subdir", True)
    return data


class SynologyClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.verify = bool(config["verify_ssl"])
        self.sid: str | None = None
        self.synotoken: str | None = None
        self._api_info: dict[str, Any] = {}

    def _webapi(self, api_name: str, fallback_path: str) -> str:
        info = self._api_info.get(api_name) or {}
        path = str(info.get("path") or fallback_path).lstrip("/")
        return f"{self.config['nas_url']}/webapi/{path}"

    def _entry(self) -> str:
        return self._webapi("SYNO.FileStation.Upload", "entry.cgi")

    def _auth(self) -> str:
        return self._webapi("SYNO.API.Auth", "entry.cgi")

    def _check(self, payload: dict[str, Any], action: str) -> dict[str, Any]:
        if not payload.get("success"):
            err = payload.get("error") or {}
            code = err.get("code", "unknown")
            hint = ERROR_HINTS.get(code) if isinstance(code, int) else None
            extra = f" — {hint}" if hint else ""
            raise SynologyError(f"{action} 失败 (error code={code}{extra}): {payload}")
        return payload.get("data") or {}

    def query_apis(self) -> None:
        url = f"{self.config['nas_url']}/webapi/query.cgi"
        resp = self.session.get(
            url,
            params={
                "api": "SYNO.API.Info",
                "version": 1,
                "method": "query",
                "query": "SYNO.API.Auth,SYNO.FileStation.Upload",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = self._check(resp.json(), "查询 API")
        self._api_info = data

    def _api_version(self, name: str, fallback: int) -> int:
        info = self._api_info.get(name) or {}
        max_ver = info.get("maxVersion")
        return int(max_ver) if max_ver else fallback

    def login(self) -> None:
        self.query_apis()
        # DSM 7 Auth 走 entry.cgi；version 6 兼容性最好。用 POST，避免反代/WAF 丢掉 URL 里的 passwd
        auth_ver = min(self._api_version("SYNO.API.Auth", 6), 6)
        payload = {
            "api": "SYNO.API.Auth",
            "version": str(auth_ver),
            "method": "login",
            "account": self.config["username"],
            "passwd": self.config["password"],
            "session": "FileStation",
            "format": "sid",
            "enable_syno_token": "yes",
        }
        otp = self.config.get("otp_code")
        if otp:
            payload["otp_code"] = str(otp)
        log(f"正在登录 DSM ({self.config['nas_url']}, 用户 {self.config['username']})...")
        resp = self.session.post(self._auth(), data=payload, timeout=30)
        resp.raise_for_status()
        data = self._check(resp.json(), "登录")
        sid = data.get("sid")
        if not sid:
            raise SynologyError("登录成功但未返回 sid")
        self.sid = sid
        self.synotoken = data.get("synotoken") or data.get("SynoToken")
        log("已登录 DSM")

    def logout(self) -> None:
        if not self.sid:
            return
        try:
            auth_ver = min(self._api_version("SYNO.API.Auth", 6), 6)
            self.session.post(
                self._auth(),
                data={
                    "api": "SYNO.API.Auth",
                    "version": str(auth_ver),
                    "method": "logout",
                    "session": "FileStation",
                    "_sid": self.sid,
                },
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"登出失败（可忽略）: {exc}")
        finally:
            self.sid = None
            self.synotoken = None

    def upload(self, local_path: Path, dest_folder: str, dest_name: str) -> None:
        if not self.sid:
            raise SynologyError("未登录")

        mime, _ = mimetypes.guess_type(local_path.name)
        if not mime:
            mime = "application/octet-stream"

        # multipart 里的 _sid 常被 DSM 忽略 → error 119；必须放在 query string
        params: dict[str, str] = {
            "api": "SYNO.FileStation.Upload",
            "version": str(min(self._api_version("SYNO.FileStation.Upload", 2), 3)),
            "method": "upload",
            "_sid": self.sid,
        }
        headers = {}
        if self.synotoken:
            params["SynoToken"] = self.synotoken
            headers["X-SYNO-TOKEN"] = self.synotoken

        # Upload API create_parents=true 会自动创建日期子目录，无需单独 CreateFolder
        with local_path.open("rb") as fh:
            files = {
                "file": (dest_name, fh, mime),
            }
            data = {
                "path": dest_folder,
                "create_parents": "true",
                "overwrite": "true" if self.config["overwrite"] else "false",
            }
            resp = self.session.post(
                self._entry(),
                params=params,
                data=data,
                files=files,
                headers=headers,
                timeout=120,
            )
        resp.raise_for_status()
        # 部分 DSM/反代会返回空 body 或非 JSON，尽量给出可读错误
        try:
            payload = resp.json()
        except ValueError as exc:
            raise SynologyError(
                f"上传 {local_path.name} 返回非 JSON (HTTP {resp.status_code}): {resp.text[:300]}"
            ) from exc
        self._check(payload, f"上传 {local_path.name}")

def unique_name(path: Path) -> str:
    stem = path.stem
    suffix = path.suffix
    short = uuid.uuid4().hex[:8]
    return f"{stem}_{short}{suffix}"


def build_dest(config: dict[str, Any], local_path: Path) -> tuple[str, str, str]:
    """Return (dest_folder, dest_name, public_url)."""
    remote_root = config["remote_path"]
    name = unique_name(local_path)

    if config.get("date_subdir"):
        today = datetime.now().strftime("%Y/%m/%d")
        rel_dir = f"images/{today}"
        dest_folder = f"{remote_root}/{rel_dir}"
        public_rel = f"{rel_dir}/{name}"
    else:
        dest_folder = remote_root
        public_rel = name

    # URL-encode each path segment, keep slashes
    encoded = "/".join(quote(seg) for seg in public_rel.split("/"))
    url = urljoin(config["public_base_url"] + "/", encoded)
    return dest_folder, name, url


def resolve_config_path() -> Path:
    env = os.environ.get(CONFIG_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return SCRIPT_DIR / "config.yaml"


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    try:
        LAST_LOG.write_text("", encoding="utf-8")
    except OSError:
        pass

    parser = argparse.ArgumentParser(description="Upload images to Synology for Typora")
    parser.add_argument("images", nargs="+", help="Local image file paths")
    args = parser.parse_args(argv)

    log(f"开始处理 {len(args.images)} 个文件")

    try:
        config = load_config(resolve_config_path())
    except SynologyError as exc:
        return fail(str(exc))

    paths: list[Path] = []
    for raw in args.images:
        p = Path(raw).expanduser().resolve()
        if not p.is_file():
            return fail(f"文件不存在: {p}")
        paths.append(p)

    client = SynologyClient(config)
    urls: list[str] = []
    try:
        client.login()
        for path in paths:
            dest_folder, dest_name, url = build_dest(config, path)
            log(f"上传 {path.name} -> {dest_folder}/{dest_name}")
            client.upload(path, dest_folder, dest_name)
            urls.append(url)
            log(f"成功: {url}")
    except (SynologyError, requests.RequestException, OSError) as exc:
        return fail(f"错误: {exc}")
    finally:
        client.logout()

    # Typora reads the last N lines of stdout as image URLs
    for url in urls:
        print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
