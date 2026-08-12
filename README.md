# uploadimage

Typora 自定义图片上传器：通过 **Synology File Station API** 把本地图片传到群晖 NAS，并返回可公网访问的 URL。

Windows / macOS / Linux 共用同一套 Python 脚本。

## Features

- 对接 DSM File Station，上传后直接得到 `https://...` 图片地址
- Typora「Custom Command」一键集成（`upload.cmd` / `upload.sh`）
- 支持按日期分子目录：`images/YYYY/MM/DD/`
- 文件名自动加短 UUID，避免覆盖
- 优先使用项目内 `.venv`，避免 Typora 精简 PATH 落到无依赖的系统 Python

## Requirements

- Python **3.10+**
- 可访问的 DSM（File Station API）
- 公网（或内网）HTTP(S) 静态访问已指向 NAS 上传目录（与 `remote_path` 对应）

## Quick Start

```bash
git clone <your-repo-url> uploadimage
cd uploadimage
```

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml
chmod +x upload.sh
```

**Windows**

```bat
"%LOCALAPPDATA%\Python\bin\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy config.example.yaml config.yaml
```

> Windows 上若 `python` / `pip` 不可用，请用上面的 `python.exe -m ...`，避免微软商店占位符。

编辑 `config.yaml` 后自测：

```bash
# macOS / Linux
./upload.sh /path/to/test.png

# Windows
upload.cmd C:\path\to\test.png
```

成功时：日志在 **stderr**，**stdout 最后一行**为图片 URL（Typora 只取最后若干行）。

## Configuration

| 字段 | 说明 |
|------|------|
| `nas_url` | DSM 地址，如 `https://dsm.example.com` |
| `username` / `password` | 建议专用低权限账号，仅对上传目录读写 |
| `remote_path` | NAS 上对应静态站文档根的路径，如 `/home/share` |
| `public_base_url` | 公网 URL 前缀，如 `https://example.com/typora` |
| `verify_ssl` | 证书不匹配（自签 / IP 访问）时设为 `false` |
| `overwrite` | 是否覆盖同名文件（默认文件名已带 UUID，一般保持 `false`） |
| `date_subdir` | `true` 时上传到 `images/YYYY/MM/DD/` |

**URL 约定**

```text
远程:  {remote_path}/images/2026/08/12/foo_a1b2c3d4.png
输出:  {public_base_url}/images/2026/08/12/foo_a1b2c3d4.png
```

自定义配置文件路径：

```bash
export SYNO_UPLOAD_CONFIG=/path/to/config.yaml
```

### DSM 连接提示

| 方式 | 示例 | 说明 |
|------|------|------|
| 域名（推荐） | `https://dsm.example.com` | 经反代 / frp，TLS 在前端终结 |
| 公网 IP:5001 | `https://x.x.x.x:5001` | 证书常不匹配 → `verify_ssl: false` |
| 内网 | `https://192.168.x.x:5001` | 仅本机/内网可用时 |

不要把 `nas_url` 写成明文 `http://...:5000`，除非你确认 WebAPI 可走 HTTP。

## Typora Setup

1. 偏好设置 → **图像**
2. 「插入图片时…」选择上传图像
3. 图像上传器 → **Custom Command**
4. 命令填入本机绝对路径：

**Windows**

```text
E:\dev\uploadimage\upload.cmd
```

控制台乱码时可改为：

```text
@chcp 65001 >nul & cmd /d/s/c E:\dev\uploadimage\upload.cmd
```

**macOS / Linux**

```text
/path/to/uploadimage/upload.sh
```

5. 点击「验证图像上传器」，确认返回以 `https://` 开头的 URL。

## Project Layout

```text
uploadimage/
├── upload.py              # 主逻辑
├── upload.cmd             # Windows 入口（优先 .venv）
├── upload.sh              # Unix 入口（优先 .venv）
├── config.example.yaml    # 配置模板
├── config.yaml            # 本地配置（勿提交）
├── requirements.txt
└── README.md
```

## Security

- 使用仅有上传目录权限的 DSM 专用账号，不要用管理员
- 勿将 `config.yaml` 提交到 Git（已在 `.gitignore` 中忽略）
- 公网访问建议 HTTPS；静态目录只读、API 账号可写

## License

按需自行补充（MIT / 私有等）。
