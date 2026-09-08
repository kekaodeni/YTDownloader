# VP9 进度与失败任务重试修复验证

日期：2026-09-04。修改仅在 develop 工作区，未提交、推送或发布。

## 已复现的根因

- GUI 的格式适配器仍含 `bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b`，不是无容器限制的原生默认策略。
- 本机日志显示公开视频 `bL0HpDGlNiU` 的 GUI 选择为 `628+140`，其中 628 是没有精确大小的 VP9/HLS；用户 CLI 选择为 HTTPS/WebM `315+251`。
- 本次仅解析元数据的真实对照确认：315 为 1,002,746,821 字节，251 为 8,970,523 字节，合计 1,011,717,344 字节。修复后 GUI 和 CLI 均选择 315+251。
- 聚合进度此前丢弃 `total_bytes_estimate`，导致有原生估算值的 HLS 仍然无限循环。
- 失败卡片此前没有重试按钮和对应控制器信号。

## 修改范围

- 选流改用 yt-dlp 自身的 `bv*+ba/b`；没有强制 AV1，也不增加编码/协议硬排序。
- 精确组件大小聚合后固定；原生 `filesize_approx` / hook 估算只作为动态估算展示，能被精确大小替代。总量缺失时不捏造音频大小、码率推算或基于时间推进。
- 速度与有效 ETA 仍使用原生 hook；不基于估算总量自造 ETA。下载中保留 100% 给 finished/处理阶段，最终使用文件实际大小。
- 失败卡片增加沿用现有 Fluent 样式的“重试”，支持键盘与无障碍名称；解析忙碌时禁用重复点击。重试回到解析页，预填原画质、文件名、目录，不自动入队、不改原历史。

## 实际验证

- 基线：156 passed。
- 原生选流测试 RED：GUI 628+140，而原生 315+251；修复后格式测试 20 passed。
- 聚合估算测试 RED：原生已有估算但 total_bytes 为 None；修复后通过。
- 下载服务 ETA 边界测试 RED：错误从估算自行生成 ETA；修复后通过。
- 真实 yt-dlp 本机 VP9/HLS 测试 RED：下载阶段提前 100%；修复后通过。
- 失败重试 Qt 测试 RED：没有 retry_button；完整流程修复后通过。
- 完整回归：168 passed；验证构建中再次运行 168 passed。
- FFmpeg 生成约 4 秒 VP9，原生 yt-dlp 经本机 HTTP 完成普通 WebM 和 HLS 下载；验证精确/估算总量、阶段、最终实际大小和临时目录清理。
- Qt 实际窗口检查：浅色/深色，100%/125%/150%/200%，1100×720 和 820×560；精确、估算、失败三种状态，共 48 张截图。关键数值无裁切；人工复核浅色重试按钮及深色最小窗口。
- `scripts/build.ps1 -ValidationOnly` 成功；EXE 资源/FFmpeg 自检、helper 取消/超时自检、GUI 启动自检通过，无残留构建进程。

## 验证版与限制

- EXE：`.tool-stage/package-validation/dist/YTDownloader/YTDownloader.exe`；需保留完整 onedir 目录。
- EXE 大小：12,043,867 字节。
- EXE SHA256：`F4A5B0ACB3B781E0C8CC7B97F98D5A7FFC5EBBA77F807E87CC2813C852E894CD`。
- 该产物是 validation-only，源码版本仍为 0.3.0；不是新正式 Release。
- 真实 YouTube 验证只解析了元数据，没有重新下载近 1 GB 的公开视频；不宣称本次验证过该视频的完整公网下载或吞吐速度。
- main、v0.1.0、v0.2.1、v0.3.0 未改变。既有正式 ZIP SHA256 仍为 `377E495407472F93CFDBF37B31DF79284DE6EA48EEFC3D17B2CCE39A6237557C`。

原生依据：[yt-dlp 格式选择与嵌入 API](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp)；本机锁定版本的 `downloader/common.py` 使用 total_bytes 或 total_bytes_estimate 展示进度，`downloader/fragment.py` 提供分片动态估算。
