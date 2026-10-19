# YTDownloader

<img src="assets/app-icon.png" alt="YTDownloader logo" width="64" align="right">

一个简洁、现代的 Windows 视频下载器，以 yt-dlp 为核心，提供下载归档、媒体工具箱、播放列表 / 番剧 / 合集下载、浏览器扩展联动、Cookie 登录、片段下载及媒体后处理。支持浅色 / 深色主题与十种界面语言。

YTDownloader is a modern Windows frontend for yt-dlp with download archives, standalone thumbnail and subtitle tools, selective playlists / collections, browser integration, clipping and media post-processing. It supports Windows notifications, light and dark themes and ten interface languages.

**[Latest Release: v0.7.0](https://github.com/kekaodeni/YTDownloader/releases/tag/v0.7.0) · [下载 Windows x64 ZIP](https://github.com/kekaodeni/YTDownloader/releases/download/v0.7.0/YTDownloader-0.7.0-win64.zip)**

## 界面预览

#### 浅色模式

<img src="docs/images/v0.7.0-download-light.png" alt="YTDownloader v0.7.0 下载页 · 浅色主题：视频解析、封面、画质与高级选项" width="1000">

#### 深色模式

<img src="docs/images/v0.7.0-download-dark.png" alt="YTDownloader v0.7.0 下载页 · 深色主题：视频解析、封面、画质与高级选项" width="1000">

## 主要功能

- **链接解析与画质选择：** 选择可用清晰度、视频 + 音频、仅视频或仅音频；音频支持保留原格式或转换为 M4A、MP3、Opus、FLAC。
- **下载归档与防重复：** 按媒体身份和已记录的本地文件路径标记已下载内容，支持重新下载；文件删除、移动或重命名后，原路径失效便恢复可下载。删除历史记录不会删除下载归档。
- **独立媒体工具箱：** 单独下载封面或提取字幕，无须同时下载视频。
- **播放列表 / 番剧 / 合集：** 支持 YouTube Playlist、Bilibili 番剧、合集和分段视频，提供分集预览、三态多选、下载状态筛选及批量画质策略；已完成批量任务可收纳为摘要。
- **Windows 系统通知：** 根据应用前后台状态发送完成 / 失败提醒，并聚合批量下载结果；可在设置中关闭。
- **浏览器扩展联动：** Chrome、Edge、Firefox 通过 Native Messaging 将主动选择的 URL 发送至桌面解析，支持单实例复用与冷启动。
- **Cookie 登录：** 配置浏览器或 `cookies.txt` 来源，按网站匹配，并查看登录状态提示。
- **任务与历史：** 多任务并发、下载进度、暂停、继续、取消、重试和历史记录管理；删除历史记录不会删除媒体文件。
- **下载预设 / Profile：** 保存常用下载设置，解析后应用默认选项。
- **视频片段下载：** 指定开始与结束时间，使用原生下载管线保存片段。
- **媒体后处理：** 嵌入封面、写入媒体信息、嵌入章节、重封装，以及通过 SponsorBlock 标记赞助片段。
- **字幕：** 按来源提供的人工 / 自动字幕选择语言、SRT / VTT 格式及内嵌选项。
- **媒体信息补探测：** yt-dlp 未提供视频尺寸且符合条件时，使用随包提供的 ffprobe 做有限补探测。
- **主题与语言：** 浅色 / 深色主题、高 DPI 界面和语言实时切换。
- **自动更新：** 验证更新清单的 Ed25519 签名与包完整性，用户确认后安装；启动检查失败时恢复原安装。

**10 种界面语言：** 简体中文、繁體中文、English、日本語、한국어、Русский、Español、Português、Tiếng Việt、ไทย。

## 下载

当前正式版本：**v0.7.0 · Windows 11 x64**。

- [下载 YTDownloader-0.7.0-win64.zip](https://github.com/kekaodeni/YTDownloader/releases/download/v0.7.0/YTDownloader-0.7.0-win64.zip)
- [版本说明与校验文件](https://github.com/kekaodeni/YTDownloader/releases/tag/v0.7.0)
- [全部版本](https://github.com/kekaodeni/YTDownloader/releases)

解压后启动 `YTDownloader.exe`，无需另外安装 Python、yt-dlp、Deno、FFmpeg 或 ffprobe。应用以便携 ZIP 分发；设置和历史记录保存在当前 Windows 用户的本地应用数据目录中。发布包未使用 Windows Authenticode 代码签名，Windows 可能显示未知发布者提示。

## 使用说明

1. 粘贴视频、播放列表或合集链接，点击“解析”。
2. 选择下载内容、清晰度和可用字幕；批量下载时选择需要的项目。
3. 需要登录时，在“设置 → 账户与 Cookie”配置自己的来源，再打开下载页“使用 Cookie”。
4. 按需选择下载预设，或在“高级选项”设置片段范围与媒体后处理。
5. 确认文件名和保存位置，开始下载；在任务卡片与历史页查看、重试或管理记录。

片段下载保留无损 stream-copy，实际起止位置和时长可能受关键帧影响。封面、章节、字幕等选项取决于源站是否提供对应内容，以及输出容器是否支持；SponsorBlock 标记取决于其服务是否有该视频的数据。

### 浏览器扩展：发送到 YTDownloader

1. 完整解压便携 ZIP，保留同目录的 `YTDownloaderBridge.exe` 和 `BrowserExtensions`。
2. 在“工具箱 → 浏览器扩展”选择浏览器，点击“开始配置”，按独立“安装指南”完成安装。
3. Chrome / Edge：在 `chrome://extensions` / `edge://extensions` 启用开发者模式，加载包内 `BrowserExtensions/Chrome` / `BrowserExtensions/Edge` 已解压目录。
4. Firefox：在 `about:debugging → 此 Firefox` 临时加载 `BrowserExtensions/Firefox/manifest.json`。临时扩展在浏览器重启后需重新载入；本扩展尚未通过 Mozilla 或浏览器商店签名 / 发布。
5. 打开支持的视频网页，使用扩展的“发送到 YTDownloader”。桌面端会解析链接，不会自动下载。

移动便携目录后，在新位置“修复连接”，并在浏览器重新加载新目录中的扩展。连接测试验证本地 Bridge / IPC；收到真实浏览器消息后才显示“已连接”。详细说明见 [浏览器扩展文档](browser-extension/README.md)。

### Cookie 与隐私

Cookie 是敏感登录凭据。应用保存来源引用和网站匹配信息，不保存网站账号密码、不复制浏览器 Cookie 数据库，也不会修改所选 `cookies.txt`。关闭“使用 Cookie”后，任务不会使用 Cookie。

浏览器 Cookie 的读取受浏览器配置、Windows 加密和访问权限影响。请勿公开分享 Cookie 文件、浏览器配置目录或含敏感信息的错误日志。

浏览器扩展仅发送用户主动选择的 HTTP(S) URL，不直接读取或传输 Cookie、网页正文或浏览历史。Native Messaging 注册使用当前用户 HKCU，不需要管理员权限，也不开放网络监听端口；桌面登录来源仍由应用设置控制。自动更新清单使用已内置信任公钥的 Ed25519 签名验证。

## 支持站点

下载能力基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp)；YTDownloader 对部分常用站点进行了额外的 UI、Cookie、清晰度与媒体解析适配。

| 站点 | 应用适配范围 |
| --- | --- |
| YouTube | 视频、播放列表、字幕、章节和 Cookie 来源。 |
| Bilibili | 视频、番剧 / 合集 / 分段视频、分集封面、质量档位与 Cookie 登录状态。 |
| X / Twitter | 视频解析与下载、按网站匹配 Cookie。 |
| Douyin | 视频链接与精选页 `modal_id` 链接兼容。 |
| Huya | VOD 视频格式兼容。 |
| SOOP / AfreecaTV | VOD 与 SOOP `/catch` 链接兼容。 |

其他站点可使用 yt-dlp 的解析与下载能力，实际结果取决于对应 extractor、媒体格式和访问条件，不保证每条内容都能下载。账号权限、地区、网络、DRM 和源站策略可能限制访问；应用不会绕过这些限制。播放列表最多展示 1000 项。

请只保存您有权使用的内容。本项目与上述网站无关联。

## 开发与构建

从源码运行需要 Windows 11 x64 和 Python 3.12 或更新版本：

```powershell
git clone https://github.com/kekaodeni/YTDownloader.git
cd YTDownloader
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\scripts\prepare_tools.ps1
.\.venv\Scripts\python.exe -m yt_downloader
```

工具脚本按 `tools.lock.json` 的 URL 与 SHA-256 获取锁定的运行组件。应用不会读取系统级 yt-dlp 配置。不要将 Cookie、浏览器配置或个人下载目录提交到仓库。

运行测试与构建验证包：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\scripts\build.ps1 -ValidationOnly
```

验证包不能执行正式安装更新。正式发布使用独立的验收与生产签名流程。

## 许可与第三方组件

本项目使用 [MIT License](LICENSE)。第三方组件的许可和来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)、[FFmpeg 来源与许可](licenses/FFMPEG-SOURCE.txt) 和 [工具锁文件](tools.lock.json)。
