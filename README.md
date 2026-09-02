# YT Downloader 0.1.0

YT Downloader 是一个面向 Windows 11 的 YouTube 单视频下载器。界面使用 PySide6 Qt Widgets 与统一的 Fluent 2 语义 Token；下载由 yt-dlp Python API 执行，合并、媒体校验和本地缩略图由随软件分发的 FFmpeg 完成。

![浅色主页](artifacts/gui-light.png)

![深色下载任务](artifacts/gui-dark-125.png)

## 功能

- 支持 `youtube.com/watch`、`youtu.be`、`shorts`、`live` 单视频地址；播放列表参数仅保留当前视频。
- 异步解析标题、频道、时长、官方缩略图和可用画质。
- 用户只看到 `2160p 4K`、`1080p 60 FPS` 等稳定标签，不显示 yt-dlp format ID。
- 自动组合兼容音频并用 FFmpeg 无损封装；下载完成后校验视频流和音频流。
- 单活动任务队列，保留可续传 `.part` 文件；退出时可等待或取消。
- 下载卡始终同时显示进度条、百分比、实时速度，并显示大小、ETA 和当前阶段。
- SQLite 历史记录，支持打开文件、定位目录、复制链接、重试和更换本地缩略图。
- 系统/浅色/深色主题、响应式导航、高 DPI、键盘焦点和辅助功能名称。
- 原子设置写入、SQLite schema migration、轮转日志、结构化中文错误和脱敏错误报告。

## 支持范围与法律提示

仅支持公开的 YouTube 单视频。不支持播放列表、频道、搜索、账号/Cookie 登录、自动更新、安装器或删除历史。私享、年龄限制、地区限制等内容会显示明确错误。

本项目与 YouTube 无关联。下载内容前请确认您有权保存和使用该内容，并遵守所在地法律与服务条款。

## 环境

- Windows 11 x64
- Python 3.12+
- PowerShell 7（Windows PowerShell 5.1 也可运行脚本）

发布版固定携带 Deno 2.9.5 和 yt-dlp FFmpeg Builds `N-126374-g089a48eb36-20260831`。应用运行时不会静默下载远程组件，也不会使用用户机器上的 yt-dlp 全局配置。

## 开发与运行

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\scripts\prepare_tools.ps1
.\.venv\Scripts\python.exe -m yt_downloader
```

用户数据写入 `%LOCALAPPDATA%\YTDownloader`：

```text
settings.json
history.db
logs\
cache\thumbnails\
```

卸载或重新打包不会删除这些数据。测试/CI 可显式设置 `YT_DOWNLOADER_DATA_DIR` 与 `YT_DOWNLOADER_VIDEOS_DIR`，正式运行默认不设置。

## 测试

普通测试完全隔离网络；yt-dlp 网络调用使用 mock：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

测试覆盖 URL、文件名、格式归一化与排序、大小/速度/进度、设置、错误脱敏、状态转换、SQLite migration、下载队列、pytest-qt UI 状态，以及真实本地 FFmpeg 的中文路径、ffprobe、帧提取和音视频流。

独立的真实 YouTube 烟雾测试不会进入 pytest。它解析 yt-dlp 的公开视频测试片段、下载最低画质，并用 ffprobe 验证音频流和视频流：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_youtube.py
```

该脚本需要可访问 YouTube 的网络，并可能因站点、地区或网络策略而失败。

## 视觉检查

可直接生成任一主题和页面的窗口截图：

```powershell
.\.venv\Scripts\python.exe -m yt_downloader --theme dark --preview-page download-demo --render-preview artifacts\dark.png
```

在启动进程前设置 `QT_SCALE_FACTOR=1`、`1.25`、`1.5`、`2` 可检查 100%–200% 缩放。窗口默认 1100×720，最小 820×560；宽度小于 900 时导航折叠为图标栏。

## 打包

工具锁文件 `tools.lock.json` 包含版本、下载 URL 与 SHA256。校验失败时 `prepare_tools.ps1` 会立即停止。

```powershell
.\scripts\prepare_tools.ps1
.\scripts\build.ps1
```

构建脚本会依次：生成 ICO、运行完整 pytest、校验资源、执行干净的 PyInstaller `onedir + windowed` 构建、启动打包后 GUI 烟雾测试、生成文件清单和 SHA256、创建分发 ZIP。

主要输出：

```text
dist\YTDownloader\YTDownloader.exe
dist\YTDownloader\third_party_licenses\
dist\YTDownloader\SHA256SUMS.json
release\YTDownloader-0.1.0-win64.zip
release\YTDownloader-0.1.0-win64.zip.sha256.txt
```

FFmpeg 使用启用了 GPL 组件的静态构建。分发目录包含 GPL 文本、构建来源、精确 FFmpeg 源码归档及其校验信息。详情见 `THIRD_PARTY_NOTICES.md`、`licenses/FFMPEG-SOURCE.txt` 和 `tools.lock.json`。

## 目录结构

```text
src/yt_downloader/
  core/             不可变模型、URL、格式、文件名、状态机、错误
  services/         yt-dlp、下载、FFmpeg、设置、历史、错误报告
  workers/          Qt 后台 Worker 与单任务队列
  infrastructure/   路径、日志、运行时工具、Shell、系统信息
  ui/               Fluent 主题、页面、Dialog 与复用控件
tests/               单元、pytest-qt、SQLite、本地 FFmpeg 测试
assets/              应用图标与 Fluent System Icons
scripts/             工具准备、真实烟雾测试、构建
licenses/            第三方许可与对应源码信息
```

## 已知限制

- YouTube 会变化；发布后需要定期更新锁定的 yt-dlp/yt-dlp-ejs。
- 不支持需要登录的内容。
- 4K 视频通常需要较大临时空间并在下载后合并。
- 没有代码签名与安装器；Windows SmartScreen 可能提示未知发布者。
- 当前工作区不是 Git 仓库，因此该交付不包含 commit、push、代码签名或线上发布。
