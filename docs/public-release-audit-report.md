# YTDownloader v0.4.0 Public Release Audit

Audit date: 2026-09-15. This audit does not rewrite Git history, move tags, or change repository visibility.

## Repository

- Repository: `kekaodeni/YTDownloader`
- Default branch: `main`
- Current main: `641dfcb1f6ea19d6ad8cc58eeb05943dd531b330`
- Frozen v0.4.0 tag commit: `4a499ef00cab09f17d8431a39c2ba6940f8d4565`
- Release: `v0.4.0`

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Git history secrets | PASS | No GitHub token, cloud credential, or complete private-key PEM pattern was found in reachable history. |
| Personal/local paths | PASS | No `<workspace>` or user-specific `<user-home>` path was found in reachable Git content, current source, README, or the final ZIP. |
| README images | PASS | Both published screenshots were visually reviewed after replacement; the output directory shows the neutral `Videos` label and no development path. |
| Historical checksum sidecars | PASS | v0.1.0, v0.2.1, and v0.3.0 Release sidecars contain only a SHA-256 and package filename. Historical ZIPs and tags were not changed. |
| Production package | PASS | `YTDownloader-0.4.0-win64.zip`, 388,164,192 bytes, SHA-256 `d5dc95ae1f4fa36a6f8b2866228aebf95cc41241715535061d03150b3f2ede1f`; `app_version=0.4.0`, `validation_only=false`. |
| Acceptance | PASS | Independent local and remote package reports: ownership, self-test, metadata helper, GUI smoke, updater windowed, and startup health all true. |
| Update source | PASS | Discovery, HTTP policy, service, signing, signature verification, updater entrypoint, tests, and manifest all use `kekaodeni/YTDownloader`. |
| Manifest/signature | PASS | key id `yt-downloader-prod-2026`; Ed25519 signature verifies with the embedded public key; manifest hash and package hash match. |
| Release assets | PASS | Final Release contains the formal ZIP, checksum, manifest, and signature; current-validation duplicates are removed. GitHub-generated Source code links remain available. |
| License notices | PASS | `LICENSE`, `THIRD_PARTY_NOTICES.md`, and bundled third-party license files are present. |
| Working tree | PASS | `git status --short` is clean and `git diff --check` passes. |

## Release verification

The formal ZIP and manifest were downloaded again from the GitHub Release. The downloaded ZIP size and SHA-256 matched the local artifact. The downloaded manifest was verified against the downloaded detached signature and `PRODUCTION_TRUSTED_KEYS`; the downloaded package then passed the independent EXE startup acceptance flow.

Windows Authenticode signing is not included. Windows Explorer display of embedded MKV covers depends on a compatible thumbnail provider and is not guaranteed on every Windows installation.

## Conclusion

Repository is ready for public visibility.

No sensitive information detected by the documented pattern checks. No release history modification was required. Repository visibility remains unchanged pending manual approval.
