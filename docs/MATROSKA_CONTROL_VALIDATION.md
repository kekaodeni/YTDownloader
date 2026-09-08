# MKV / WebM 封面兼容性最终验收（2026-09-08）

**本机已通过完整写入与 Explorer 显示验收。** 当前开发分支是 `develop`，版本仍为 v0.4.0。之前的“MKV Shell 显示尚未解决”记录是修复前结果，以本报告及下面的最终证据为准。

[使用已验收的 v0.4.0 包](../release/YTDownloader-0.4.0-cover-validation-win64.zip)，完整解压后运行 `YTDownloader.exe`。本轮最终修复是 Windows 用户配置，不需要重新构建同一应用代码；包 SHA-256 仍为 `aefd2615c678a7b6f794277c0cc499f5394a3b4c757456b304aca66e725af134`，389,015,488 字节。

## 根因与修复

MKVToolNix 101.0 和 YTDownloader 生成的 MKV 均已有规范 Attachment：`cover.jpg / image/jpeg` 或 `cover.png / image/png`。独立 `mkvmerge -J` 与 `mkvextract attachments` 验证结构和图片字节一致。因此没有重写已经正确的 MKV 封装逻辑。

限时 Process Monitor 跟踪证明：Icaros DLL 已被隔离宿主成功加载，但宿主读取 Windows 用户的 `Software\Icaros` 得到 `NAME NOT FOUND`；此前工具进程的 `UseCoverArt=1` 来自虚拟化的用户注册表视图。[关键事件](validation-matroska/registry-root-cause.json)

最终通过已运行的 Explorer，以普通桌面用户权限启动配置入口，仅设置已授权的 `.mkv` 两项缩略图关联与 `UseCoverArt=1`，对真实原值另存独立备份。随后真实桌面验证、实际文件夹显示，以及原工具路径的新样本复测全部通过。没有关闭缩略图进程隔离，没有修改视频打开方式。

## 验收结果

| 检查 | 结果与证据 |
| --- | --- |
| 13 种容器的真实封面写入、内容验证与 Shell 显示 | 全部通过：[矩阵](validation-matroska/desktop-container-matrix.json) |
| MKVToolNix / YTDownloader × JPEG / PNG | 四组全部通过：[独立对照](validation-matroska/desktop-known-good.json) |
| 原先失败的工具调用路径复测 | 四组全部通过：[复测](validation-matroska/post-setup-tool-comparison.json) |
| 同一文件连续更换两次封面 | MKV、WebM→MKV、MP4、M4V 共八次通过；音视频编码包哈希不变：[记录](validation-matroska/desktop-repeated-covers.json) |
| 实际资源管理器窗口 | 显示红色/品红色选中封面，未显示蓝色视频帧：[截图](validation-matroska/explorer-folder.png) |
| 用户现有历史文件 | 两份仍在本地的 MKV 均通过；其中一份旧缓存经单文件刷新后通过，文件大小及修改时间不变，数据库只读：[记录](validation-matroska/existing-history-cover-refresh.json) |
| 应用完整回归 | 267 项通过 / 124.71 秒，原 258 项保留：[日志](validation-matroska/build.log) |
| 新包独立解压 | 自检、解析子进程、GUI、updater 与健康检查等六项通过：[记录](validation-matroska/archive-acceptance.json) |
| 既有 Qt Quick UI | 21 个 QML 文件与前一已验收包逐字节一致：[记录](validation-matroska/ui-preserved.json) |

矩阵范围：MP4、M4V、MKV 直接写入；WebM、MOV、AVI、FLV、TS、M2TS、MPG、OGV、WMV、3GP 无重编码另存 MKV，保留原文件。覆盖这些容器的选定编码组合，不代表 FFmpeg 所有可能组合都已测试。历史记录缩略图未被用作文件封面成功证据。

前轮真实回归还修复了 MPEG 缺少 PTS 导致无法 remux，以及 3GP 的 `und` 与省略未定义语言被误判为流信息变化。编码、分辨率、音频参数、字幕、章节与原文件保护没有放宽。

## 本机配置与恢复

[真实桌面最终设置](validation-matroska/desktop-final-settings.json)：`UseCoverArt=1`；HKCU/HKLM 均没有设置 `DisableProcessIsolation`；MKV 打开方式仍是 `PotPlayerMini64.MKV`。

Icaros 3.3.6 安装于 `C:\Program Files\YTDownloader Shell\Icaros-3.3.6`。当前有效用户备份为 `%LOCALAPPDATA%\YTDownloader\shell\icaros-desktop-registration.json`；标准 COM 原设置备份为 `C:\Program Files\YTDownloader Shell\machine-registration.json`。早先工具视图备份保留供审计，不作为当前桌面恢复依据。

在普通 Windows PowerShell 中进入项目目录，可恢复本轮用户设置：

```powershell
.\.venv\Scripts\python.exe -B scripts/manage_explorer_cover.py --disable
```

如需再恢复标准 COM 注册，在管理员 Windows PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe -B scripts/manage_explorer_cover.py --unregister-server
```

恢复脚本保留安装后其他软件或用户做出的配置更改。其他电脑需要兼容的缩略图提供器及启用内嵌封面；应用不会自行安装 Icaros。执行系统配置应使用实际桌面会话，不能仅凭虚拟化工具中的注册表读数判断生效。

## 复现与收尾

独立结构诊断入口：

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_matroska_cover.py --mkvtoolnix <便携工具目录> --output <新的输出目录>
```

官方 MKVToolNix 101.0 便携包通过官方 SHA-256 校验：`4ee52c5065e4a9c2d88462e99bceac249f07eb2d3bfe415838b6f783642c6417`。[官方下载](https://mkvtoolnix.download/downloads.html)

Process Monitor 限时跟踪已结束，诊断进程与驱动已停止；完整原始 PML/CSV 已删除，仅保留相关证据。没有清空系统全局缩略图缓存。临时样本、工具和重复构建已清理；最后一轮删除 522 个文件、278,260,044 字节，轻量验收样本留在文档目录。[清理记录](validation-matroska/final-cleanup.json) 全部原有发布文件及当前交付包的 SHA-256 核对通过。

全部既有 release、Git 历史和当前源码保留。未推送、发布、修改版本号或生产更新配置。[交付清单](validation-matroska/delivery.json)
