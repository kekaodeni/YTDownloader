# Qt Quick UI 重构与本地验收记录

日期：2026-09-06。基线：`fba9d3d4be7c1d29945b0f60f0fc6a3fe4d8377b`。
工作分支：`codex/ui-quick-rebuild`。版本保持 **0.4.0**，交付为本地 validation-only 构建，未推送、发布或启用生产更新源。

## 实现范围

使用 QQmlApplicationEngine、ApplicationWindow 和 Qt Quick Controls Basic 重建下载、历史、设置、关于和应用弹窗。保留 Windows 原生标题栏、窗口按钮、拖动、缩放和 Snap；默认 1200×800，最小 500×560，窄窗口采用紧凑导航和纵向内容。

Python 展示适配层通过 QObject 属性、信号、槽和 QAbstractListModel 提供状态。QML 提交用户操作，既有 Controller、Worker、服务和存储继续执行功能。旧 Widgets 页面、弹窗、截图过渡及对应的私有实现测试已移除，功能断言迁移到新展示层。

已核对基线差异：`core/`、`services/`、`workers/`、`infrastructure/`、`updates/` 和独立 updater 的实现均未修改。app.py 的变更为窗口构造、展示方法和异步弹窗接线；新增历史封面缓存位于 UI 目录，只读取媒体并写入可再生成的展示缓存。

| 路径 | 保持的契约 | 验证方式 |
| --- | --- | --- |
| 解析 | 独立进程、取消、超时、请求令牌和迟到结果隔离 | metadata process、request gate、UI states |
| 格式与入队 | 索引映射原始 FormatOption；参数、默认值和手动目录语义不变 | format service、UI states、retry |
| 下载与进度 | 单活动队列、真实阶段和数值、取消后等待清理；不预测进度 | queue、progress、task artifacts、removal |
| 历史 | 稳定 task_id、只删除记录、终态批量选择、重试回解析、键盘与右键操作 | history、context menu、retry |
| 设置 | 原有选项、500 ms 文本自动保存、即时选择保存、失败反馈、主题预览 | settings service、UI states |
| 封面与更新 | 现有 FFmpeg 写入/验证/取消流程、更新能力限制和忙时退出 | cover、FFmpeg integration、update suite |

输入框响应真实输入及辅助功能 ValuePattern 更新；展示层过滤相同值，避免绑定回显被误认为手动修改。页面常驻以保留输入、选择和滚动状态。任务列表增量更新并复用委托。

## 最新反馈修复

### 菜单和字体

历史菜单采用统一圆角、阴影、图标、语义颜色及焦点状态，取消全窗灰幕。鼠标与键盘共用 Menu 的单一当前项；移除“hovered 或 highlighted”双重来源及透明黑色到实色的背景插值，避免相邻条目同时变暗。调色板各颜色直接绑定语义前景色，消除相互引用造成的循环绑定。

中文采用 Microsoft YaHei UI / Microsoft YaHei，英文及数字优先 Segoe UI，明确日文、韩文和 Emoji 回退。普通按钮和历史标题使用常规字重，避免合成中等字重显得突兀。空输入框依据占位文字选择字体，英文输入的字体栈也包含中文回退。

### 历史封面

已完成的视频异步读取内嵌封面；没有内嵌封面时，提取真实视频画面。封面写入成功后失效对应展示缓存并刷新原列表行，保持选择状态。

缓存使用媒体绝对路径、修改时间和文件大小生成内容版本键；拒绝已删除记录、活动记录及旧版本的迟到结果。后台最多一个工作任务，最近待处理请求最多 32 个，派生 JPEG 最多 256 张。缓存位于应用数据目录的 `cache/history-previews/`，不改写媒体、历史表结构或业务存储规则。不可读取的文件保留本地占位提示并记录诊断，不伪造封面。

真实 FFmpeg 集成检查覆盖：无内嵌封面的视频画面、连续两次替换内嵌封面、刷新后新旧 URL 不同、颜色内容正确、选择不丢失，以及缩略图读取前后媒体 SHA-256 完全一致。

### 横竖屏预览和图标

封面弹窗读取预览图片的实际比例，按可用宽高计算容器，并使用 PreserveAspectFit；横屏、竖屏、方形均完整显示，不裁切。只更改预览布局，封面提取、写入、取消和临时文件清理保持既有流程。

应用图标由内置图像生成工具重新设计。可追溯原图为 `assets/app-icon-master.png`；`scripts/generate_assets.py` 仅将已选原图转换为展示 PNG 和 16/24/32/48/64/128/256 px 的 Windows ICO，不再用旧绘图脚本覆盖设计。窗口、导航品牌区和 EXE 共用新资源。

## 测试与视觉证据

本次完整构建回归 **243 项通过，88.89 秒**，包括本地 FFmpeg 音视频和封面集成测试。构建日志：`.tool-stage/ui-followup/build-final.log`。菜单真实鼠标连续移动、Escape、Shift+F10、批量键盘操作、快速切页、反向滚轮、像素滚动、减少动态效果、主题和尺寸切换均有对应功能断言。

真实封面界面检查生成 12 张双主题截图，覆盖两种画面方向、历史封面及三个连续悬停位置，QML 警告为零。录屏使用 QQuickWindow.grabWindow，只采集验证应用自身；60 fps 是文件编码帧率，包含采集过程产生的重复帧，不能作为 165 Hz 性能证明。所有视频、记录、图片和数据库为隔离验收样例，未使用用户真实历史作为交付素材。

曾在混合 GUI 测试宿主中出现偶发 Qt 原生中止，发生在后续下载线程测试；单独队列连续五次正常，保留原生日志的前置序列连续五次（每次 17 项）正常，最终全量 243 项正常。测试夹具明确完成 GUI 线程中的 DeferredDelete 与对象回收。**原生中止根因仍未得到确定证据，不能宣称仅凭重跑通过已修复。** 原始记录位于 `.tool-stage/ui-followup/native-diagnostic-0.log`；正式发布前应继续观察该测试宿主问题。本次仍按约定仅交付本地验证版本。

中文输入覆盖 QInputMethodEvent 预编辑/提交与辅助功能写入；操作系统中文输入法候选窗的主观观感不属于自动化结论。性能采样只证明本机指定场景，不代表所有显卡、外部网络或满负载环境。

## 可复现入口

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .tool-stage\ui-check-new
.\scripts\build.ps1 -ValidationOnly -ValidationName ui-local-new
.\.venv\Scripts\python.exe scripts\verify_quick_ui.py --output .tool-stage\visual-new --motion-seconds 17
.\.venv\Scripts\python.exe scripts\verify_quick_cover_ui.py --output .tool-stage\cover-new
```

每次使用新的输出目录，保留已有验证包。刷新率验证脚本先检查系统支持的模式，临时切换并在 finally 中恢复原模式。不要同时运行多个 GUI 验证进程；遮挡窗口会干扰渲染与截图。

渲染方法依据 [Qt 场景图说明](https://doc.qt.io/qt-6/qtquick-visualcanvas-scenegraph.html)；导航追踪使用 [SmoothedAnimation](https://doc.qt.io/qt-6/qml-qtquick-smoothedanimation.html)。帧提交间隔与 GUI 定时器延迟分别记录。

## 最终渲染和缩放验收

Windows 11、Qt/PySide6 6.11.2、D3D11、150% 缩放。连续导航每 160 ms 改变目标，采样 17 秒、排除前 2 秒热身；使用渲染线程直接记录 QQuickWindow.frameSwapped。P95 不超过两个刷新周期，P99 不超过三个刷新周期。

| 实际刷新率 | 间隔样本数 | P95 | P99 | 最大间隔 | 超过 50 ms | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 165.019 Hz | 2462 | 6.669 ms | 9.829 ms | 14.173 ms | 0 | 通过 |
| 60.008 Hz | 898 | 17.353 ms | 20.161 ms | 21.615 ms | 0 | 通过 |

以上两个连续动画采样区间均达到门槛；60 Hz 检查后已恢复 165.019 Hz。GUI 定时器延迟另存原始 JSON，不作为帧率证明。100%、150%、200% 缩放均完成双主题、四页面和三种窗口宽度检查；100% 和 200% 各 27 张截图，QML 警告为零。最小 500×560 窗口另完成 12 张封面/菜单截图，横竖屏封面比例及祖先裁切边界断言通过。

## 最新本地交付（2026-09-07）

之前的阶段构建已按用户要求清理。当前完整 ZIP 为 `release/YTDownloader-0.4.0-ui-local-validation-win64.zip`，最新测试、封面功能范围及待验收事项见 [COVER_AND_CLEANUP.md](COVER_AND_CLEANUP.md)。

上文为 UI 迁移阶段的历史验收；后续用户明确授权修复封面业务，因此“业务目录未变化”不再适用于最新版本。最新构建完整回归 258 项通过，实际包验证记录保存在 `docs/validation-current/`。版本、生产更新源及发布状态未改变。
