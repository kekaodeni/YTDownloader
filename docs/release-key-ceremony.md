# YTDownloader 正式版 Ed25519 发布密钥仪式

本文档说明如何创建 YTDownloader 正式更新清单使用的签名身份。私钥、密码和其他凭据不得进入 Git、ZIP、GitHub Release、命令参数、日志或聊天消息。

本文档本身不会修改仓库。只有完成审核并记录公钥指纹后，才将公钥接入应用信任根。

## 1. 确定并记录密钥身份

选择一个稳定的 `key_id`，例如：

```text
yt-downloader-prod-2026
```

不要复用测试套件或临时验证流程使用的 key ID。将 key ID 和公钥 SHA-256 指纹记录在发布清单或经批准的离线仪式记录中；不要记录私钥内容或密码。

## 2. 在仓库外准备私钥目录

在正常 Windows PowerShell 中执行。目录必须位于仓库之外：

```powershell
$KeyRoot = Join-Path $env:USERPROFILE 'Documents\YTDownloader-ReleaseKeys'
New-Item -ItemType Directory -Force -Path $KeyRoot | Out-Null

# 移除继承权限，仅授予当前 Windows 用户完全控制权限。
icacls $KeyRoot /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F"

$env:YT_RELEASE_KEY_PATH = Join-Path $KeyRoot 'yt-downloader-prod-2026.pem'
$env:YT_RELEASE_PUBLIC_PATH = Join-Path $KeyRoot 'yt-downloader-prod-2026.public.hex'
```

确认 `$KeyRoot` 不在仓库内。不要把密钥放入 release、build、dist、临时验证目录、工具缓存目录或任何同步目录。

## 3. 生成加密 PKCS#8 Ed25519 私钥

下面的命令会交互式询问密码，不会把密码写入命令行或环境变量。它会生成加密 PEM 私钥、原始公钥 hex 文件，并只打印公钥指纹。

```powershell
@'
import hashlib
import os
from getpass import getpass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

private_path = Path(os.environ["YT_RELEASE_KEY_PATH"]).resolve()
public_path = Path(os.environ["YT_RELEASE_PUBLIC_PATH"]).resolve()
if private_path.exists() or public_path.exists():
    raise SystemExit("Refusing to overwrite an existing release key")

password = getpass("New encrypted release-key password: ").encode("utf-8")
confirm = getpass("Repeat release-key password: ").encode("utf-8")
if not password or password != confirm:
    raise SystemExit("Passwords do not match or are empty")

key = Ed25519PrivateKey.generate()
private_path.write_bytes(key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.BestAvailableEncryption(password),
))
raw_public = key.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw,
)
public_path.write_text(raw_public.hex() + "\n", encoding="ascii")
print("public_key_sha256=" + hashlib.sha256(raw_public).hexdigest())
print("private_key_written=" + str(private_path))
print("public_key_written=" + str(public_path))
'@ | .\.venv\Scripts\python.exe -

Remove-Item Env:YT_RELEASE_KEY_PATH
Remove-Item Env:YT_RELEASE_PUBLIC_PATH
```

私钥必须是加密 PKCS#8 PEM，且没有密码不能读取。应在独立受控位置保存加密备份，不要上传到 GitHub 或云盘。

## 4. 验证私钥、公钥和指纹

重新设置两个路径变量后，执行以下命令。密码只通过交互式提示输入：

```powershell
$env:YT_RELEASE_KEY_PATH = Join-Path $KeyRoot 'yt-downloader-prod-2026.pem'
$env:YT_RELEASE_PUBLIC_PATH = Join-Path $KeyRoot 'yt-downloader-prod-2026.public.hex'
@'
import hashlib
import os
from getpass import getpass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

private_path = Path(os.environ["YT_RELEASE_KEY_PATH"])
public_path = Path(os.environ["YT_RELEASE_PUBLIC_PATH"])
password = getpass("Release-key password: ").encode("utf-8")
loaded = serialization.load_pem_private_key(private_path.read_bytes(), password=password)
if not isinstance(loaded, Ed25519PrivateKey):
    raise SystemExit("The key is not Ed25519")
raw = loaded.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw,
)
expected = bytes.fromhex(public_path.read_text(encoding="ascii").strip())
if raw != expected:
    raise SystemExit("Public-key mismatch")
print("public_key_sha256=" + hashlib.sha256(raw).hexdigest())
print("public_key_match=PASS")
'@ | .\.venv\Scripts\python.exe -
Remove-Item Env:YT_RELEASE_KEY_PATH
Remove-Item Env:YT_RELEASE_PUBLIC_PATH
```

将输出的指纹与仪式记录比较。指纹是公开标识；密码和私钥内容不得写入仓库。

## 5. 将公钥接入应用信任根

源码中只能放入 32 字节原始公钥。完成审核后，在 `src/yt_downloader/updates/trusted_keys.py` 中使用以下格式，把占位 key ID 和 hex 值替换为批准的值：

```python
PRODUCTION_TRUSTED_KEYS: dict[str, bytes] = {
    "yt-downloader-prod-2026": bytes.fromhex(
        "<来自批准公钥文件的 64 个十六进制字符>"
    ),
}
```

私钥仍必须留在仓库外。签名程序会从私钥推导公钥，并与源码中的信任根比较；不一致时必须停止发布。

接入公钥后运行更新签名测试，并确认 `PRODUCTION_TRUSTED_KEYS` 只包含批准的 key ID。不要把测试密钥加入正式信任根。

## 6. 签名正式包

正式包必须已经通过生产构建，`BUILD-INFO.json` 必须包含 `"validation_only": false`，并且有独立验收报告且所有检查均为 true。签名程序会拒绝 validation-only 包、未加密私钥、仓库内私钥、未知 key ID 和哈希不匹配的包。

在正常 Windows PowerShell 中执行。私钥路径只作为本机参数使用，密码会交互式询问：

```powershell
$KeyRoot = Join-Path $env:USERPROFILE 'Documents\YTDownloader-ReleaseKeys'
.\.venv\Scripts\python.exe scripts\sign_update.py `
  --package release\YTDownloader-0.4.1-win64.zip `
  --private-key (Join-Path $KeyRoot 'yt-downloader-prod-2026.pem') `
  --key-id yt-downloader-prod-2026 `
  --version 0.4.1 `
  --minimum-auto-update-version 0.4.0 `
  --notes-zh docs\release-notes-v0.4.1-zh.md `
  --notes-en docs\release-notes-v0.4.1-en.md `
  --acceptance-report release\acceptance-report.json
```

脚本会在包旁生成 `update-manifest.json` 和 `update-manifest.sig`。上传前必须检查版本、包名、Release URL、key ID、压缩大小、解压大小和 SHA-256。

## 7. 必须停止的情况

出现以下任一情况，都必须停止：

- 私钥路径位于仓库内；
- 私钥未加密、不是 Ed25519，或无法用密码打开；
- 推导出的公钥与批准指纹不一致；
- key ID 不在已审核的信任根中；
- `BUILD-INFO.json` 为 `validation_only: true`；
- 缺少验收报告或包哈希不一致；
- 命令会打印密码或私钥内容；
- 私钥出现在 Git 状态、ZIP、Release 附件或日志中。

密钥轮换需要单独进行仪式：先加入并审核新公钥，再使用新 key ID 签名；旧公钥只能在明确批准的兼容窗口内保留。
