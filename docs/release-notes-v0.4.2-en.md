# YTDownloader v0.4.2

v0.4.2 is the bridge from the legacy updater protocol to the internal updater helper layout.

- Keeps the root `YTDownloaderUpdater.exe` and schema 1 package layout so unmodified v0.4.1 installs can upgrade directly.
- Adds schema 2, paginated stable-release discovery, and compatibility filtering after Ed25519 verification.
- The bridge helper runs from a transaction directory, verifies v0.5.0 internal-layout packages, and restores the previous installation when health confirmation fails.
- Download behavior, GUI layout, history, settings, and user-data directories are unchanged.

This release is intended for users installed on v0.4.1. Future standard packages place the helper under `_internal/updater/` and omit a root updater executable.
