# YTDownloader v0.5.0 — Release notes draft

This is a release-candidate draft, not an announcement of a published release.
Final package hashes and acceptance results must be attached after validation.

## 中文

- 通用 yt-dlp 媒体解析，保留 YouTube 行为并覆盖 Bilibili、Vimeo；其他支持站点提供实验性提示。
- 视频+音频、仅视频、仅音频；音频支持原始格式与 M4A、MP3、Opus、FLAC。
- 手动/自动字幕选择、SRT/VTT 转换及兼容容器内嵌；可选字幕失败不删除已完成视频。
- 明确授权的浏览器 Cookie 或 Netscape 文件来源，默认关闭，不复制 Cookie 内容或写回源文件。
- 播放列表显式选择、批次状态、共享并发、暂停新任务、取消及仅重试失败项。
- About 检查更新、下载进度恢复、下载后确认安装与重启。
- 内部 updater、独立验签、健康确认、回滚及主程序启动时的中断恢复。
- 历史字段扩展前备份并事务迁移；保留 v0.4.x 记录及旧程序对数据库的读写兼容。

限制：站点可能要求登录、限制地区或改变接口；不绕过 DRM/付费/访问权限。
Vimeo 页面入口可能需要登录，公开播放器链接的可用性另行判定。
播放列表最多展示 1000 项；暂停不打断正在执行的下载或 FFmpeg。
浏览器 Cookie 的 fixture 验证不代表所有真实浏览器账户均可用。

更新链：v0.4.1 → v0.4.2 → v0.5.0。v0.4.2 必须继续作为 GitHub Latest；
未来本版本发布须使用 `make_latest=false`，新客户端通过 Releases 列表发现。
v0.5.0 标准包根目录不含 updater EXE；其清单按内部布局直接生成。

## English

- General yt-dlp media resolution with YouTube regression coverage and Bilibili/
  Vimeo fixtures; other supported extractors remain explicitly experimental.
- Video with audio, video only and audio only, including original audio and
  optional M4A, MP3, Opus or FLAC conversion.
- Manual/automatic subtitle selection, SRT/VTT conversion and supported-container
  embedding. Optional subtitle failures preserve completed media.
- Explicit browser or Netscape Cookie sources, disabled by default, with no
  stored Cookie contents or writes back to the selected file.
- Explicit playlist selection, batches, shared concurrency, pause-new-work,
  cancellation and failed-only retries.
- Update checks in About, resumable progress UI and confirmation before restart.
- Internal updater, independent verification, startup health, rollback and
  startup recovery for interrupted installations.
- Backed-up transactional history extensions retain old records and database
  read/write compatibility with v0.4.x.

Availability depends on site, network, region and account authorization. DRM and
access restrictions are not bypassed. Vimeo page URLs may require authentication;
public player URLs are assessed separately. Playlist selection is capped at 1000
entries. Pausing does not interrupt an active download or FFmpeg operation.
Browser fixtures do not constitute real-account acceptance for every browser.

Upgrade path: v0.4.1 → v0.4.2 → v0.5.0. Keep v0.4.2 as GitHub Latest and publish
this future release with `make_latest=false`. New clients enumerate Releases.
The standard v0.5.0 package has no root-level updater executable.
