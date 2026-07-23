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


class SynologyError(RuntimeError):
    """Raised when DSM / File Station API returns an error."""


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


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
        self._api_info: dict[str, Any] = {}

    def _entry(self) -> str:
        return f"{self.config['nas_url']}/webapi/entry.cgi"

    def _auth(self) -> str:
        return f"{self.config['nas_url']}/webapi/auth.cgi"

    def _check(self, payload: dict[str, Any], action: str) -> dict[str, Any]:
        if not payload.get("success"):
            err = payload.get("error") or {}
            code = err.get("code", "unknown")
            raise SynologyError(f"{action} 失败 (error code={code}): {payload}")
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
        auth_ver = min(self._api_version("SYNO.API.Auth", 3), 3)
        resp = self.session.get(
            self._auth(),
            params={
                "api": "SYNO.API.Auth",
                "version": auth_ver,
                "method": "login",
                "account": self.config["username"],
                "passwd": self.config["password"],
                "session": "FileStation",
                "format": "sid",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = self._check(resp.json(), "登录")
        sid = data.get("sid")
        if not sid:
            raise SynologyError("登录成功但未返回 sid")
        self.sid = sid
        log("已登录 DSM")

    def logout(self) -> None:
        if not self.sid:
            return
        try:
            auth_ver = min(self._api_version("SYNO.API.Auth", 3), 3)
            self.session.get(
                self._auth(),
                params={
                    "api": "SYNO.API.Auth",
                    "version": auth_ver,
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

    def upload(self, local_path: Path, dest_folder: str, dest_name: str) -> None:
        if not self.sid:
            raise SynologyError("未登录")

        mime, _ = mimetypes.guess_type(local_path.name)
        if not mime:
            mime = "application/octet-stream"

        # Upload API create_parents=true 会自动创建日期子目录，无需单独 CreateFolder
        with local_path.open("rb") as fh:
            files = {
                "file": (dest_name, fh, mime),
            }
            data = {
                "api": "SYNO.FileStation.Upload",
                "version": "2",
                "method": "upload",
                "path": dest_folder,
                "create_parents": "true",
                "overwrite": "true" if self.config["overwrite"] else "false",
                "_sid": self.sid,
            }
            resp = self.session.post(
                self._entry(),
                data=data,
                files=files,
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
    parser = argparse.ArgumentParser(description="Upload images to Synology for Typora")
    parser.add_argument("images", nargs="+", help="Local image file paths")
    args = parser.parse_args(argv)

    try:
        config = load_config(resolve_config_path())
    except SynologyError as exc:
        log(str(exc))
        return 1

    paths: list[Path] = []
    for raw in args.images:
        p = Path(raw).expanduser().resolve()
        if not p.is_file():
            log(f"文件不存在: {p}")
            return 1
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
        log(f"错误: {exc}")
        return 1
    finally:
        client.logout()

    # Typora reads the last N lines of stdout as image URLs
    for url in urls:
        print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
