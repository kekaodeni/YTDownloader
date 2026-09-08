# v0.4.0 封面、UI 与清理验收（2026-09-07）

> 2026-09-08 更新：此前 MKV 的 Explorer 显示问题已解决；最新结果、有效备份与恢复方法见 [最终验收](MATROSKA_CONTROL_VALIDATION.md)。下文保留历史阶段记录。

最新本地包：[`release/YTDownloader-0.4.0-ui-local-validation-win64.zip`](../release/YTDownloader-0.4.0-ui-local-validation-win64.zip)。完整解压后运行 `YTDownloader.exe`，不要单独移动 EXE。这是本地验证构建，版本仍为 0.4.0，生产更新源及发布状态未变；未提交或推送 Git。

后续开发继续使用项目根目录当前 `codex/ui-quick-rebuild` 工作区，不需要旧构建副本。`.git` 和所有原 release 文件保留。

## 已完成

- 历史封面按图片实际比例完整显示；统一缩略图列与行高，竖屏不裁切，窄窗口仍显示封面且状态下移。
- 封面预览完整显示横竖屏图片，历史缩略图随成功写入刷新。
- 修复透明按钮悬停时先变暗再变亮：底色与透明度分开动画。真实鼠标采样覆盖两种主题及五种按钮样式。历史菜单保持单个高亮。
- MP4/M4V/MKV 内嵌封面写入并验证；JPEG/PNG、重复写入、Unicode 路径、取消和失败回滚均覆盖。
- WebM/MOV 另存 MKV 并写入封面，保留原文件，不重新编码；历史指向新 MKV。目标重名不覆盖。
- FFprobe 验证流、时长、章节、元数据和封面数量；FFmpeg 提取写入的封面，SHA-256 与输入图片逐字节比较。错图会阻止替换原视频。
- 保留字幕、文字附件、非正面图片附件；预览明确选择真正的视频流，不误取旧封面。

## 测试与实际构建

- 完整回归 **258 passed / 113.20 s**，无跳过：[构建日志](validation-current/build-final.log)。
- 最终 EXE：双主题各五个页面入口、历史缩略图、更新启动健康检查通过：[包验证](validation-current/package-verification.json)。
- 真实 UI Automation：历史/设置/关于导航、无效链接错误、弹窗关闭、原生文件夹选择取消通过：[交互记录](validation-current/accessibility-results.json)。
- 独立 ZIP 解压：清单、自检、解析子进程、GUI 启动、updater 子系统及更新健康检查六项通过：[记录](validation-current/archive-acceptance.json)。
- 包大小 **389,014,623 字节**；SHA-256 **5f3a428c65f2e30bd98582bfd3514a3e289f8338019387d7b2e07aea7cd8896c**。
- 先前 165/60 Hz 渲染采样与录屏见 [UI 迁移记录](UI_QUICK_REBUILD.md)；不是对本轮所有场景重新进行帧率测量的声明。

## 尚未通过：本机 MKV 在资源管理器中采用内嵌封面

最新真实结果：[重启 Explorer 后验证](validation-current/explorer-after-restart.json)。蓝色视频 + 红色封面为合成测试素材，不含用户视频。

| 容器 | 提取封面字节等于输入 | 文件保持不变 | Windows Shell 返回选中封面 |
| --- | --- | --- | --- |
| MP4 | 是 | 是 | 是 |
| M4V | 是 | 是 | 是 |
| MKV | 是 | 是 | **否，仍为视频帧** |

直接调用 Icaros 标准缩略图接口可得到正确封面，但标准隔离 Shell 路径未通过。已排除简单旧文件缓存：新生成媒体、强制单文件提取、重启资源管理器仍复现。因此不将此项标为完成，也不将 Icaros 的视频帧回退作为封面成功证据。后续需继续调查隔离宿主读取行为；整机重启后的结果尚未验证。

经用户授权，官方 Icaros 3.3.6 组件放置在 `C:\Program Files\YTDownloader Shell\Icaros-3.3.6`，标准 64 位 COM 注册；仅当前用户 `.mkv` 缩略图关联，原 PotPlayer 打开方式未改变。`UseCoverArt=1`，进程隔离保持开启。没有为 MP4/M4V 或其他用户改缩略图关联。

自动审批拒绝了持续设置 `DisableProcessIsolation=1` 的方案，理由是未经授权的持续安全削弱；没有应用该方案。之后使用用户授权的标准注册及 Explorer 重启。

备份：

- 当前用户：`%LOCALAPPDATA%\YTDownloader\shell\icaros-registration.json`
- 系统 COM：`C:\Program Files\YTDownloader Shell\machine-registration.json`

恢复当前用户缩略图关联：

```powershell
.\.venv\Scripts\python.exe -B scripts/manage_explorer_cover.py --disable
```

随后如需恢复本轮系统 COM 注册，在管理员 PowerShell 运行：

```powershell
.\.venv\Scripts\python.exe -B scripts/manage_explorer_cover.py --unregister-server
```

恢复逻辑保留安装后其他工具或用户做出的配置更改。恢复注册不自动删除组件文件。

复测完整读取链路（只读媒体，输出 JSON；MKV 未通过时退出码非零）：

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_explorer_cover.py --report docs/validation-current/explorer-recheck.json
```

官方说明：[Icaros 注册与内嵌封面配置](https://github.com/Xanashi/Icaros)、[Windows 强制缩略图提取](https://learn.microsoft.com/en-us/windows/win32/api/thumbcache/ne-thumbcache-wts_flags)。

## 清理范围

删除旧 `.tool-stage`、build/dist、重复 validation-only 输出、工具下载缓存、测试 runtime/preview/smoke 数据及项目字节码缓存。保留当前源码、测试、脚本、资源、文档、`.git`、开发 `.venv`、必要 vendor 工具与全部原 release。仅新增上述一个最新本地 ZIP。

原 release 六个文件 SHA-256 清单：[清理前](validation-current/release-before.json)。删除目标：[第一轮](validation-current/cleanup-targets-first.json)、[最终轮](validation-current/cleanup-targets-final.json)。磁盘总量见 [清理后统计](validation-current/disk-summary.json)。

实际统计：清理前 18,106,324,728 字节，清理后 2,323,798,756 字节，释放 15,782,525,972 字节（约 15.78 GB）。.pytest_cache 因目录 ACL 拒绝访问而保留，未修改其权限；统计未能读取其中内容。git diff --check 通过。
