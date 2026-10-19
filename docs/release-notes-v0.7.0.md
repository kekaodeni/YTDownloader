# YTDownloader v0.7.0

v0.7.0 聚焦下载管理、独立媒体工具箱、播放列表体验及浏览器联动，进一步完善画质识别、Cookie 状态检测和交互一致性。

## 新功能

- **下载归档与防重复下载：** 按媒体身份及已记录的本地文件状态标记已下载内容，支持明确的重新下载入口。本地文件删除、移动或重命名使原路径失效后，重新解析会恢复可下载；删除历史记录不清除归档。
- **独立媒体工具箱：** 单独下载封面或提取人工 / 自动字幕，无须同时下载视频。
- **Windows 系统通知：** 支持完成 / 失败提醒，结合应用前后台状态减少干扰，聚合批量下载结果，并提供通知设置。
- **高级播放列表体验：** YouTube Playlist、Bilibili 番剧、合集及分段视频提供分集封面、标题、时长、已下载标记、三态多选、状态筛选和批量画质操作。
- **浏览器扩展：** Chrome、Microsoft Edge、Firefox 可通过 Native Messaging 将主动选择的网页 URL 发送至桌面解析，支持单实例复用及冷启动，不会自动开始下载。

## 体验改进

- 已完成的批量任务可收纳为摘要，失败任务保留明确的重试入口。
- 便携包包含浏览器 Bridge 及三种扩展资源，提供配置、连接检测、修复、移除和独立安装指南。
- 常规下拉框采用 PreferSelectedCenter，选中项尽量居中，靠近首尾时限制在合法范围；保留键盘、减少动画及轻微边界反馈。
- 安装指南采用固定标题 / 浏览器切换栏、独立滚动正文和固定页脚，技术说明可折叠；长路径可换行、选择与复制。
- 完善浅色 / 深色、十种语言和高 DPI 下的滚动边界与界面布局。

## 修复与兼容性

- YouTube 按语义画质档位聚合底层 FPS / codec rendition，优先展示高帧率代表项，保留低帧率候选及 144p 等独立档位。
- 完善 Bilibili 番剧分集 metadata、参考画质与封面传递，保持官方单集封面在解析、下载及最终嵌入阶段的一致性。
- 保留 Bilibili 普通 1080p、高码率、60 FPS、4K、SDR 增强、HDR 与杜比视界等不同语义。
- 修复归档忽略本地文件缺失、合集任务重试丢失上下文及批量完成卡片堆积的问题。
- 统一 Cookie/Auth 证据与状态展示，区分有效、无效及未知；网络、权限或证据不足不会被简单当作 Cookie 过期。
- 对无可下载音视频的有效页面给出明确提示，避免笼统归类为解析器错误。
- 修复 SOOP 单一媒体流缺少宽高时，SDR 标记错误阻止有界 ffprobe 补探测的问题。
- 修复浏览器操作按钮反馈、便携目录移动后的连接处理及 Firefox Native Messaging 启动生命周期问题。
- 修复下拉框选中项不可见、滚轮抖动、安装指南留白和滚动边界异常。

## 下载及注意事项

下载 `YTDownloader-0.7.0-win64.zip`，完整解压后运行 `YTDownloader.exe`。

便携包包含桌面应用、yt-dlp、Deno、FFmpeg、ffprobe、Qt/PySide、Updater、`YTDownloaderBridge.exe` 及 `BrowserExtensions/Chrome`、`Edge`、`Firefox`。

Chrome / Edge 扩展通过开发者模式加载已解压目录。Firefox 扩展采用临时安装，浏览器重启后需重新载入；本扩展尚未通过 Mozilla 或浏览器商店签名 / 发布。移动便携目录后需修复桌面连接，并重新加载新目录的扩展。

扩展只发送主动选择的 HTTP(S) URL，不读取或传输 Cookie、网页正文或浏览历史。连接测试验证本地 Bridge / IPC；收到真实浏览器消息后才显示已连接。

归档仅依据已记录的输出路径，不会扫描磁盘寻找重命名或移动后的文件。网站访问仍受网络、地区、账号权限、登录状态及源站策略限制。片段下载采用无损 stream-copy，切点可能受关键帧影响；封面、字幕、章节及其他后处理依赖源数据和容器支持。

Windows ZIP 未使用 Authenticode 代码签名，可能显示“未知发布者”。应用自动更新清单使用既有生产 Ed25519 公钥验证。

## 本次发布验证

- 最终源码重新执行：完整 pytest **1356 passed**，发布 focused tests **543 passed**；浏览器扩展 JavaScript 测试通过。
- 实际 Qt Quick：Light / Dark、100% / 125% / 150% / 200% DPI、十种语言和 Reduce Motion；320 次下拉框定位与 480 组安装指南检查通过，QML warnings **0**。
- 实际下载并用 ffprobe 检查 YouTube、YouTube Playlist、Bilibili、Bilibili 番剧、X 和 SOOP 成品的音视频、封面及 metadata；章节样本的最终 MKV 保留 **15 个章节**。独立封面、字幕提取、真实文件归档失效检查及 X 有效 / 失效 / 无媒体状态通过。
- 正式冻结包、生产签名、v0.6.0 → v0.7.0 更新与回滚的最终结果见 Release 附件 `release-validation-v0.7.0.json`；该报告仅在对应发布门禁通过后上传。

<details>
<summary>English release notes</summary>

## YTDownloader v0.7.0

v0.7.0 focuses on download management, standalone media tools, selective playlists and browser integration, with improved semantic quality selection, Cookie authentication status and UI consistency.

### New

- **Download Archive / Duplicate Prevention:** identify completed media using its identity and recorded local output. Re-download remains available. Deleting, moving or renaming the file makes the old path inactive when reparsing; removing a History row does not clear the archive.
- **Thumbnail Downloader / Subtitle Extractor:** save a cover or manual / automatic subtitles without downloading the video.
- **Windows Notifications:** completion and failure notifications respect foreground/background state, aggregate batch results and can be configured in Settings.
- **Selective Playlists / Collections:** YouTube playlists and Bilibili seasons, collections and segments provide per-entry thumbnails, titles, duration, downloaded badges, tri-state selection, filtering and batch quality controls.
- **Browser Companion / Native Messaging:** Chrome, Microsoft Edge and Firefox can send an explicitly selected URL to the desktop app for parsing, including single-instance reuse and cold start. Sending never starts a download automatically.

### Improved

- Completed batch tasks can collapse into a summary; failed tasks keep their retry actions.
- Portable Extension Distribution includes the Bridge and all three browser resources, with setup, connection checks, repair, removal and a separate installation guide.
- PreferSelectedCenter dropdown positioning balances context, clamps at list boundaries and retains keyboard navigation, reduced motion and subtle edge feedback.
- The installation guide has a fixed title/browser header, independently scrolling steps and fixed footer. Technical details are collapsible; paths wrap and support selection/copying.
- Refined scrolling and layout across light/dark themes, all ten languages and high DPI settings.

### Fixes / Compatibility

- YouTube quality options aggregate FPS/codec renditions within semantic tiers, prefer a high-FPS representative and retain lower-FPS fallbacks and distinct tiers such as 144p.
- Bilibili season metadata, reference quality and official per-episode covers remain consistent through parsing, downloading and embedding. Normal/high-bitrate/60-FPS 1080p, 4K, enhanced SDR, HDR and Dolby Vision retain distinct semantics.
- Missing local outputs invalidate active archive badges. Collection retries preserve their context, and completed batch cards no longer accumulate indefinitely.
- Cookie Authentication Status consistently distinguishes valid, invalid and unknown evidence; network errors, permission failures and insufficient evidence do not automatically imply expiration.
- Valid pages without downloadable audio/video receive a specific explanation.
- SOOP streams missing dimensions can use the existing bounded ffprobe fallback even when the extractor supplies an SDR flag.
- Fixed browser action feedback, moved-portable-directory handling, Firefox native-host lifecycle, dropdown visibility/wheel jitter and guide spacing/bounds.

### Download / Known Limitations

Extract `YTDownloader-0.7.0-win64.zip` completely and run `YTDownloader.exe`. It includes yt-dlp, Deno, FFmpeg, ffprobe, Qt/PySide, the Updater, Bridge and Chrome/Edge/Firefox extension resources.

Chrome/Edge use Developer mode and Load unpacked. Firefox uses a temporary installation that must be reloaded after restarting; this extension has not been signed/published by Mozilla or a browser store. After moving the portable directory, repair the desktop connection and reload the extension from its new folder.

Only explicitly selected HTTP(S) URLs are sent. Extensions do not access or transmit Cookies, page contents or browsing history. The connection test checks the local Bridge/IPC; Connected requires a real browser message.

The archive checks recorded paths and does not search the disk for renamed/moved files. Site availability depends on network, region, login, account permissions and source policies. Lossless stream-copy section cuts depend on keyframes. Post-processing depends on source metadata and container support.

The ZIP is not Authenticode-signed. Update manifests use the established production Ed25519 trust root.

### This release's validation

- Fresh final-source runs: **1356 full pytest tests** and **543 focused release tests** passed; browser-extension JavaScript tests passed.
- Native Qt Quick: light/dark, 100% / 125% / 150% / 200% DPI, all ten languages and Reduce Motion; 320 dropdown-positioning cases and 480 installation-guide cases passed, with **0 QML warnings**.
- Real YouTube, YouTube Playlist, Bilibili, Bilibili season, X and SOOP outputs were checked with ffprobe for audio/video, covers and metadata. The chapter sample retained **15 chapters** in its final MKV. Standalone cover/subtitle tools, real-file archive invalidation and X valid/invalid/no-media states passed.
- Final formal-package, production-signature, v0.6.0 → v0.7.0 upgrade and rollback results are recorded in the Release asset `release-validation-v0.7.0.json`, uploaded only after the corresponding publication gates pass.

</details>
