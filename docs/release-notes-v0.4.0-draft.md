# YT Downloader v0.4.0 Release Notes（草稿）

> 状态：本地候选 / 尚未发布
> 当前 `develop` 源码已统一为 `0.4.0`。生产公钥与公开更新源尚未启用，因此当前仅生成 validation-only 验证包；本文件不代表已经合并、打标签、推送或发布。

## 中文

### 下载进度与文件大小

- 下载格式选择进一步对齐 yt-dlp 原生策略，移除 GUI 隐含的 MP4/M4A 偏好，避免 VP9 视频被错误切换到缺少可靠总大小的 HLS 格式。
- VP9、AV1 等编码统一使用 yt-dlp 返回的格式、字节总量、速度和 ETA，不再按编码分别实现进度逻辑。
- 精确大小、估算大小和未知大小采用不同语义：精确总量固定；完整的 yt-dlp 原生估算也可驱动进度，但明确标注“估算”且允许随分片更新；只有总量缺失时使用不定进度。
- 分离式音视频下载按组件累计，整体进度保持单调，只有下载完成并进入后处理阶段后才显示 100%。

### 失败任务重试

- 下载失败的任务卡新增“重试”按钮，并支持键盘焦点和辅助功能名称。
- 点击重试会返回解析与选项确认界面，保留原清晰度、文件名和保存目录；不会自动重新下载，也不会修改原历史记录。

### 动效与界面性能

- 页面、解析卡、封面和任务卡改用可中断、可重定向的统一动效控制器；快速连续操作从当前视觉帧继续，不再排队或跳回起点。
- 任务卡增删/淘汰采用一次布局落位与有预算的快照代理，避免空白停顿、回弹和逐帧改变真实布局。
- 对话框、菜单、按钮反馈与离散鼠标滚轮统一为短时 Fluent 动效；触控板、键盘和滚动条保持原生行为。
- 进度事件在 GUI 积压时合并，SQLite 只在阶段变化和终态落库。10,000 条历史压力复验为 P95 7.61ms、P99 12.98ms、最大 45.36ms，未出现超过 50ms 的动效停顿。

### 安全自动更新基础设施

- 新增稳定通道更新检查、后台下载、SHA256/长度校验、Ed25519 detached signature 与 `key_id + TrustedKeyring` 信任模型；未知远程公钥永不自动受信。
- GitHub Release 只用于发现；验签后的原始 manifest 才是版本、平台、包大小、哈希和下载地址的权威来源。Release tag、manifest 和正式资源版本必须一致。
- 下载仅接受固定更新仓库及有限的 GitHub 官方 HTTPS 资源域名，禁止 HTTP 降级、凭据、`.netrc` 和任意第三方重定向；ZIP 使用 10 秒连接/30 秒停滞超时。
- 新增无 Qt、windowed 的外部 updater：严格拒绝路径穿越、ADS、设备名、大小写冲突、链接/reparse point 和清单外文件；同卷候选切换支持事务日志、旧版本备份、健康握手和失败回滚。
- 更新能力分为 `CHECK_ONLY`、`DOWNLOAD_AND_VERIFY`、`AUTO_INSTALL`。源码与 validation-only 构建不会替换安装目录；正式自动安装还需单独批准的生产公钥及公开更新仓库。
- Ed25519 只验证应用更新真实性，不等同于 Windows Authenticode；v0.4.0 不强制商业代码签名。v0.3.0 及更早版本首次升级仍需手动完成。

## English

### Download progress and file size

- Aligned format selection more closely with yt-dlp by removing the GUI's hidden MP4/M4A preference, preventing VP9 videos from being silently redirected to HLS formats without reliable exact sizes.
- VP9, AV1, and other codecs now share the same yt-dlp-native progress path for format data, byte totals, speed, and ETA.
- Exact, estimated, and unknown sizes are represented separately. Exact totals are locked; complete native estimates also drive progress but remain explicitly labeled and may evolve. Only missing totals use indeterminate progress.
- Separate video and audio components are accumulated monotonically, and 100% is reserved for completion/post-processing.

### Retry failed tasks

- Added an accessible, keyboard-focusable Retry action to failed download cards.
- Retry returns to metadata parsing and option confirmation while preserving quality, filename, and destination. It never starts a download automatically or rewrites the original history record.

### Motion and UI performance

- Page, metadata card, thumbnail, and task-card transitions now share interruptible, retargetable controllers. Rapid input continues from the current visual frame instead of queueing or restarting.
- Task insertion/removal uses one layout commit plus memory-bounded snapshot proxies, removing blank gaps and geometry bounce.
- Dialog, menu, button, and discrete mouse-wheel feedback follows short Fluent motion tokens while touchpad, keyboard, and scrollbar input remains native.
- Progress events are coalesced under GUI backlog and SQLite writes occur only at stage/terminal changes. The 10,000-row stress run measured P95 7.61ms, P99 12.98ms, max 45.36ms, with no motion-caused stall above 50ms.

### Secure update infrastructure

- Added stable-channel discovery, background download, length/SHA256 verification, detached Ed25519 signatures, and a `key_id + TrustedKeyring` trust model. Unknown server keys are never trusted automatically.
- GitHub Releases are discovery only; the verified raw manifest is authoritative for version, platform, size, hash, and asset URL.
- Downloads are restricted to the fixed update repository and a bounded set of GitHub HTTPS asset hosts, with no HTTP downgrade, credentials, `.netrc`, or arbitrary redirects. ZIP timeouts are 10 seconds to connect and 30 seconds without data.
- Added a no-Qt windowed external updater with strict archive ownership validation, same-volume candidate switching, transaction journals, known-good backup, health handshake, and rollback.
- Capabilities are gated as `CHECK_ONLY`, `DOWNLOAD_AND_VERIFY`, or `AUTO_INSTALL`. Source and validation-only builds cannot replace an installation; production auto-install still requires a separately approved public trust root and public update repository.
- Ed25519 authenticates application updates but is not Windows Authenticode. Existing v0.3.0 and older executables still require one manual upgrade.

## 已完成验证

- 完整自动化测试：`253 passed`（最终本地候选）。
- 已覆盖 VP9 WebM 精确总量、VP9/HLS 估算总量、AV1/VP9 共用进度路径及失败任务重试交互。
- 已完成 Light/Dark、100%/125%/150%/200% 缩放和最小窗口 GUI 验证。
- 已完成 validation-only Windows 双 EXE 构建、严格所有权校验及解压后独立启动 smoke test。
- 已使用仓库外临时测试密钥完成 frozen `0.4.0 → 0.4.1` 安装事务演练；事务为 `COMMITTED`，旧版本备份及用户数据均保留。测试密钥和测试构建不会进入正式信任根或发布物。
- 公开仓库匿名访问、真实弱网/VPN 下载与生产密钥仪式仍是明确的上线门槛；当前验证包不是正式 v0.4.0 发布物。
- 详细诊断与验证记录见 [VP9 下载进度与失败任务重试修复记录](vp9-progress-retry-fix.md)。

## 后续正式发布门槛

获得单独授权并完成生产信任配置后，再执行：

1. 在仓库外完成加密 Ed25519 生产私钥仪式，并把公钥以新 `key_id` 预置到受信 keyring；
2. 创建并匿名验证公开更新仓库及 GitHub 官方资源重定向链；
3. 用真实弱网/VPN 验证 10 秒连接与 30 秒停滞策略；
4. 生成正式 ZIP，完成独立启动验收后再签 manifest；
5. 经单独授权后执行 merge、tag、push 与 Release 上传。

在上述流程开始前，不覆盖 v0.3.0 发布物，不提前生成 v0.4.0 标签或 Release。
