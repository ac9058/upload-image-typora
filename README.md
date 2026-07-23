# Typora → 群晖 NAS 图片上传

通过 Synology File Station API 上传图片，供 Typora「自定义命令」使用。Windows 与 macOS 共用同一套 Python 脚本。

## 前置条件

1. 已安装 **Python 3.10+**
2. 能访问 DSM（本项目默认用 [https://dsm.bimsoft.top/](https://dsm.bimsoft.top/)）
3. `https://upload.bimsoft.top` 已通过 Web Station / 反向代理指向 NAS 上的上传目录（与配置中的 `remote_path` 对应）

### DSM 连接说明（本环境）

| 方式 | 地址 | 说明 |
|------|------|------|
| 推荐 | `https://dsm.bimsoft.top` | 域名访问 DSM，填入 `nas_url` |
| 备选 | `https://116.62.128.103:5001` | 公网直连 DSM HTTPS（5001） |
| 穿透 | frpc → 群晖 `5000` | 若域名只反代到 HTTP 5000，仍用 `https://dsm.bimsoft.top`（由前端 TLS 终结）；不要把 `nas_url` 写成 `http://...:5000` 除非你确认 WebAPI 可走明文 |

用 IP:5001 时，证书主机名往往不匹配，请把 `verify_ssl` 设为 `false`。

## 安装

```bash
cd /path/to/uploadimage

# Windows（若直接敲 pip/python 报错，用完整路径或 -m pip）
"%LOCALAPPDATA%\Python\bin\python.exe" -m pip install -r requirements.txt
copy config.example.yaml config.yaml

# macOS / Linux
python3 -m pip install -r requirements.txt
cp config.example.yaml config.yaml
```

> Windows 提示：`pip` / `python` 不是命令，多半是未进 PATH，或被微软商店占位符拦截。请用上面的 `python.exe -m pip`，不要单独运行 `pip`。

编辑 `config.yaml`：

| 字段 | 说明 |
|------|------|
| `nas_url` | 推荐 `https://dsm.bimsoft.top`；备选 `https://116.62.128.103:5001` |
| `username` / `password` | 建议专用低权限账号，仅对上传目录读写 |
| `remote_path` | NAS 上对应公网站点根目录的路径，如 `/web/upload` |
| `public_base_url` | `https://upload.bimsoft.top` |
| `verify_ssl` | 自签或 IP 访问导致证书不匹配时设为 `false` |
| `overwrite` | 是否覆盖同名文件（默认文件名带短 UUID，一般无需开启） |
| `date_subdir` | 为 `true` 时上传到 `images/YYYY/MM/DD/` |

URL 约定：远程文件 `{remote_path}/images/2026/07/23/foo_a1b2c3d4.png` 会输出：

```text
https://upload.bimsoft.top/images/2026/07/23/foo_a1b2c3d4.png
```

也可通过环境变量指定配置路径：

```bash
export SYNO_UPLOAD_CONFIG=/path/to/config.yaml
```

## Typora 设置

1. 偏好设置 → **图像**
2. 「插入图片时…」可选「上传图像」
3. 图像上传器选择 **Custom Command**
4. 命令填入：

**Windows：**

```text
E:\dev\uploadimage\upload.cmd
```

若验证时控制台乱码，可改为：

```text
@chcp 65001 >nul & cmd /d/s/c E:\dev\uploadimage\upload.cmd
```

**macOS：**

```bash
chmod +x /path/to/uploadimage/upload.sh
```

Typora 命令：

```text
/path/to/uploadimage/upload.sh
```

5. 点击「验证图像上传器」，确认返回以 `https://` 开头的 URL。

## 命令行自测

```bash
# macOS / Linux
./upload.sh /path/to/test.png

# Windows
upload.cmd C:\path\to\test.png
```

成功时：日志在 stderr，**最后一行 stdout 为图片 URL**（Typora 只取最后 N 行）。

## 目录结构

```text
uploadimage/
  upload.py              # 主逻辑
  upload.cmd             # Windows 入口
  upload.sh              # macOS 入口
  config.example.yaml
  config.yaml            # 本地配置（勿提交）
  requirements.txt
  README.md
```

## 安全建议

- 使用 DSM 专用账号，不要用管理员
- 不要把 `config.yaml` 提交到 Git（已在 `.gitignore` 中忽略）
- 公网域名建议启用 HTTPS，并限制上传目录仅 Web 可读、API 账号可写
