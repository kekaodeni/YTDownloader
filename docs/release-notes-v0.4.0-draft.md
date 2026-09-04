# YT Downloader v0.4.0 Release Notes（草稿）

> 状态：Unreleased / 待发布
> 当前源码版本仍为 `0.3.0`。本文件只用于累积 v0.4.0 发布说明，不代表已经升版、构建、打标签、推送或发布。

## 中文

### 下载进度与文件大小

- 下载格式选择进一步对齐 yt-dlp 原生策略，移除 GUI 隐含的 MP4/M4A 偏好，避免 VP9 视频被错误切换到缺少可靠总大小的 HLS 格式。
- VP9、AV1 等编码统一使用 yt-dlp 返回的格式、字节总量、速度和 ETA，不再按编码分别实现进度逻辑。
- 精确大小、估算大小和未知大小采用不同语义：精确总量固定；完整的 yt-dlp 原生估算也可驱动进度，但明确标注“估算”且允许随分片更新；只有总量缺失时使用不定进度。
- 分离式音视频下载按组件累计，整体进度保持单调，只有下载完成并进入后处理阶段后才显示 100%。

### 失败任务重试

- 下载失败的任务卡新增“重试”按钮，并支持键盘焦点和辅助功能名称。
- 点击重试会返回解析与选项确认界面，保留原清晰度、文件名和保存目录；不会自动重新下载，也不会修改原历史记录。

## English

### Download progress and file size

- Aligned format selection more closely with yt-dlp by removing the GUI's hidden MP4/M4A preference, preventing VP9 videos from being silently redirected to HLS formats without reliable exact sizes.
- VP9, AV1, and other codecs now share the same yt-dlp-native progress path for format data, byte totals, speed, and ETA.
- Exact, estimated, and unknown sizes are represented separately. Exact totals are locked; complete native estimates also drive progress but remain explicitly labeled and may evolve. Only missing totals use indeterminate progress.
- Separate video and audio components are accumulated monotonically, and 100% is reserved for completion/post-processing.

### Retry failed tasks

- Added an accessible, keyboard-focusable Retry action to failed download cards.
- Retry returns to metadata parsing and option confirmation while preserving quality, filename, and destination. It never starts a download automatically or rewrites the original history record.

## 已完成验证

- 完整自动化测试：`168 passed`。
- 已覆盖 VP9 WebM 精确总量、VP9/HLS 估算总量、AV1/VP9 共用进度路径及失败任务重试交互。
- 已完成 Light/Dark、100%/125%/150%/200% 缩放和最小窗口 GUI 验证。
- 已完成 validation-only Windows 构建及解压后独立启动 smoke test；该验证构建不是正式 v0.4.0 发布物。
- 详细诊断与验证记录见 [VP9 下载进度与失败任务重试修复记录](vp9-progress-retry-fix.md)。

## 与下一轮改动一起发布

下次改动完成并由用户确认后，再将本文件中的内容与下一轮改动统一纳入 v0.4.0，并一次性执行：

1. 补全最终 Release notes；
2. 运行完整测试与 GUI 验收；
3. 将源码、About 页和构建元数据统一升至 `0.4.0`；
4. 生成正式 Windows x64 onedir/windowed 构建；
5. 对解压后的发布目录执行独立启动 smoke test；
6. 生成正式 ZIP 和 SHA256 文件。

在上述流程开始前，不覆盖 v0.3.0 发布物，不提前生成 v0.4.0 标签或 Release。
