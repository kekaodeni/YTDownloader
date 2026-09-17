# YTDownloader v0.4.2

v0.4.2 是从旧更新协议到内部 updater helper 架构的桥接版本。

- 保留根目录 `YTDownloaderUpdater.exe` 和 schema 1 包布局，确保 v0.4.1 可以直接升级。
- 新增 schema 2、分页稳定版本发现、Ed25519 验签后的兼容性筛选。
- 桥接 helper 可以从事务目录外运行，校验 v0.5.0 内部布局包，并在健康确认失败时恢复旧安装。
- 不改变下载、GUI、历史记录、设置和用户数据目录。

此版本面向已安装 v0.4.1 的用户。后续标准包将把 helper 放在 `_internal/updater/`，根目录不再包含 updater helper。
