# YTDownloader v0.6.0

v0.6.0 是一次较大的功能与交互更新，重点完善播放列表 / 合集下载、多语言、片段下载、媒体后处理、Cookie 状态检测以及整体 UI 与交互体验。

## 新功能

- 新增 **10 种界面语言**，支持运行时即时切换：简体中文、繁體中文、English、日本語、한국어、Русский、Español、Português、Tiếng Việt、ไทย。
- 新增 **YouTube Playlist / Bilibili 分段与合集下载**，支持批量选择、统一画质策略、独立任务与独立缩略图。
- 新增 **视频片段下载**，支持 `MM:SS` / `HH:MM:SS` 时间输入。
- 新增 **高级下载选项**：嵌入封面、写入媒体信息、嵌入章节、重封装，以及 SponsorBlock 赞助片段标记。
- 新增 **下载预设 / Profile**，支持自动推荐、最高质量与自定义下载配置。
- 新增 **Cookie 登录状态检测**，可识别有效、失效及未知状态。
- 新增更明确的 **错误分类与可执行修复操作**，例如重新解析、管理 Cookie 和重试。

## 体验与界面改进

- 重构 **设置页**，采用分类导航，统一下载、账户与 Cookie、网络、外观、更新及工具诊断。
- 统一一级 / 二级导航、展开面板、开关、滚动条和页面切换动画，并支持 **减少动画**。
- 改进 **历史记录管理**：整行多选、三态全选、批量删除和选区右键菜单。
- Playlist / Collection 下载任务统一使用普通下载任务卡片，并沿用暂停、继续、取消和删除操作。
- 改进下载任务速度、进度和缩略图显示，片段下载也提供正常任务进度反馈。

## 解析与兼容性改进

- 重构 **Bilibili 画质语义识别**，正确区分 4K、HDR / 杜比视界、1080p 高码率、1080p 60 FPS、普通 1080p 等档位。
- 修复异常 raw height 被误显示为 `1890p`、`886p` 等标签的问题。
- 媒体流缺少尺寸等必要信息时，增加带超时限制的 **ffprobe 通用探测 fallback**。
- 改善 **SOOP / AfreecaTV `/catch`**、Douyin 精选链接及 Huya 视频兼容性。
- 修复下载预设影响原始 metadata / format enumeration 的问题。
- 改善 YouTube 与 Bilibili Cookie、代理及登录态传递。

## 修复

- 修复片段下载的进度、速度、代理传递以及暂停 / 继续逻辑。
- 修复高级选项、片段开关在空任务状态下的闪烁、跳动及滚动位置变化。
- 修复 Playlist / Collection 子任务缩略图缺失。
- 修复 History 选区描边、右键批量删除及多余焦点短线。
- 修复语言下拉列表边界滚动抖动与回弹异常。
- 修复最终 MKV 中封面、metadata 与章节未正确写入的问题。
- YouTube 章节与 metadata 现在会按当前界面语言获取并保存。
- 补全冻结版应用的翻译资源及运行依赖。

## 下载与说明

下载 [YTDownloader-0.6.0-win64.zip](https://github.com/kekaodeni/YTDownloader/releases/download/v0.6.0/YTDownloader-0.6.0-win64.zip)，解压后运行 `YTDownloader.exe`。

便携包包含 `yt-dlp`、Deno、FFmpeg、ffprobe、Qt 和 PySide。片段下载默认使用无损 stream-copy，因此实际切点可能受源视频关键帧影响。网站访问可能受到网络、地区、登录状态和账号权限限制；需要登录的内容请使用自己的有效 Cookie。

Windows ZIP **未使用 Authenticode 代码签名**，系统可能显示“未知发布者”；应用更新清单使用 **Ed25519 签名校验**。

## 验证

v0.6.0 已完成真实 YouTube、YouTube Playlist、Bilibili、Bilibili Collection 和 SOOP 下载验证。最终 MKV 的封面、metadata 与中文章节已使用 ffprobe 检查；Light / Dark、100% / 125% / 150% / 200% DPI、多语言和完整自动化回归均已验证。

---

<details>
<summary>English release notes</summary>

## YTDownloader v0.6.0

v0.6.0 is a major feature and UX update focused on playlists and collections, localization, clipping, media post-processing, Cookie status and download reliability.

### New

- 10 interface languages with live switching: Simplified Chinese, Traditional Chinese, English, Japanese, Korean, Russian, Spanish, Portuguese, Vietnamese and Thai.
- YouTube Playlists and Bilibili collections / segmented videos, with batch selection, shared quality policies, independent tasks and thumbnails.
- Video section downloads with `MM:SS` / `HH:MM:SS` time input.
- Advanced options for thumbnail embedding, media metadata, chapters, remuxing and SponsorBlock markers.
- Download Profiles / presets for automatic recommendations, highest quality and custom settings.
- Cookie login-state detection for valid, expired and unknown states.
- Actionable error categories and recovery actions such as re-parsing, Cookie management and retry.

### Improved

- Redesigned Settings with categories for downloads, accounts and Cookies, network, appearance, updates, and diagnostics.
- Unified navigation, disclosure, toggle, scrollbar and page-transition animations, with a reduced-motion option.
- Improved History management with row selection, tri-state select-all, batch deletion and selection-aware context menus.
- Playlist / Collection items now use standard download task cards with the same pause, resume, cancel and delete actions as regular downloads.
- Improved task speed, progress and thumbnail display; section downloads also report normal task progress.
- Correct Bilibili quality semantics for 4K, HDR, Dolby Vision, high-bitrate 1080p, 1080p 60 FPS and standard 1080p.
- Added a time-bounded ffprobe fallback when media streams lack required dimensions.
- Improved SOOP / AfreecaTV `/catch`, Douyin selection-page and Huya VOD compatibility.
- Download Profiles no longer affect original metadata or format enumeration; improved YouTube and Bilibili Cookie, proxy and login-state propagation.

### Fixed

- Section-download progress, speed, proxy propagation and pause / resume behavior.
- Advanced Options flicker, switch jumps and scroll-position changes in the empty-task state.
- Missing Playlist / Collection child thumbnails.
- History selection outlines, context-menu batch deletion and stray focus marks.
- Language-popup edge scrolling and overscroll feedback.
- Cover, metadata and chapter preservation in final MKV files.
- YouTube metadata and chapters now follow the selected interface language.
- Missing translation resources and runtime dependencies in frozen packages.

### Download and notes

Download [YTDownloader-0.6.0-win64.zip](https://github.com/kekaodeni/YTDownloader/releases/download/v0.6.0/YTDownloader-0.6.0-win64.zip), extract it and run `YTDownloader.exe`.

The portable package includes yt-dlp, Deno, FFmpeg, ffprobe, Qt and PySide. Section downloads use lossless stream-copy, so exact cut points may depend on source keyframes. Availability may vary by network, region, login state and account permissions; use your own valid Cookies when needed.

The Windows ZIP is not Authenticode-signed, so Windows may show an unknown-publisher warning. Update manifests are protected by Ed25519 signature verification.

### Verification

Real downloads were verified for YouTube, YouTube Playlists, Bilibili, Bilibili Collections and SOOP. ffprobe verified cover art, metadata and Chinese chapters in the final MKV. Light / Dark themes, 100% / 125% / 150% / 200% DPI, localization and the full automated regression suite were also verified.

</details>
