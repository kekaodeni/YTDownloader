# Phase 2 — Generic yt-dlp metadata resolution

Base: develop `2635f0678ae026f8f0c016e7c401276fce7fd28d`.
This phase changes metadata resolution and its presentation, not updater
protocols or release assets. The runtime version remains 0.4.2 during development.

## Audit and implementation files

| Area | Files | Finding / change |
| --- | --- | --- |
| URL input | `core/url.py`, `ui/quick_download.py` | Removed the active YouTube allowlist and 11-character ID requirement. HTTP(S), hostname, port, credential and control-character validation precede yt-dlp. Query and fragment semantics are preserved. |
| Models | `core/models.py` | `ResolvedMedia` / `MediaInfo` with extractor identity, original/canonical URL, media type, author, date, description, thumbnail, normalized formats, typed subtitle tracks and playlist summary. |
| Resolver | `services/media_resolver.py`, `media_metadata.py`, `media_errors.py`, `youtube_service.py` | Generic extractor service and conservative error taxonomy; old service name remains a compatibility import. |
| Call chain | `app.py`, `workers/metadata_process.py` | Generic resolver used in the real worker process and thumbnail path. Successful original input is retained for download/retry. |
| Presentation | `ui/quick_download.py`, `ui/quick_cover.py`, `ui/qml/DownloadView.qml`, `ui/qml/AboutView.qml` | Generic wording, nonblocking Experimental hint, safe cross-site thumbnail identity and safe preview filenames. |
| Diagnostics | `services/error_report_service.py`, `services/download_service.py`, `core/filename.py` | Generic messages/default filename; copied reports redact URL credentials and signature parameters. |
| Dependency | `pyproject.toml`, `requirements.txt`, `requirements-dev-snapshot.txt`, `YTDownloader.spec`, `scripts/collect_runtime_licenses.py` | Pin curl-cffi 0.16.0, collect it in the future app build, include its license notice. |
| Verification | `tests/test_generic_media.py`, `test_media_boundaries.py`, `test_media_runtime_licenses.py`, `test_youtube_service.py`, `test_filename.py`, `scripts/smoke_media_metadata.py`, `scripts/verify_media_ui.py` | Deterministic contracts, legacy behavior, public smoke and source UI acceptance. |
| Record | `docs/v050-phase2-generic-media.md` | Audit, implementation and verification limits. |

Additional audited files needed no implementation changes: `core/formats.py`
and `services/format_resolver.py` already operate on generic format IDs;
`services/history_service.py` treats its old `video_id` column as opaque text;
request-gate, metadata-process, download and history fixtures remain in regression.
The settings network probe still uses YouTube robots.txt as its existing probe
target, not as an input allowlist. Legacy YouTube canonicalization functions in
`core/url.py` remain for old callers/tests but are not in the runtime resolver,
clipboard or error-report path.

## Contracts and boundaries

- QML consumes Python presentation state, never raw yt-dlp dictionaries.
  `VideoInfo` is a compatibility alias of `ResolvedMedia`; the legacy `video_id`
  field is an opaque extractor ID. `media_key` hashes extractor, canonical page
  and opaque ID for cross-site matching. The compatibility `raw` field stays empty.
- `url` retains the successful original input; `webpage_url` records yt-dlp's
  canonical page independently. They must not be conflated: a public Vimeo
  player can succeed while the ordinary page requires login.
- YouTube, BiliBili and Vimeo are reference (`VERIFIED`) integrations. Other
  successful extractors are `EXPERIMENTAL`, with a lightweight hint that never
  disables an otherwise valid download. This is not a website allowlist and
  does not promise every URL/account/region on a reference site is accessible.
- Error codes: `UNSUPPORTED_URL`, `NETWORK_ERROR`, `AUTH_REQUIRED`,
  `COOKIE_REQUIRED`, `GEO_RESTRICTED`, `PRIVATE_MEDIA`, `DRM_UNSUPPORTED`,
  `TEMPORARY_EXTRACTOR_ERROR`. Typed causes and explicit evidence take priority;
  ambiguous 403/extraction failures are not guessed to be authentication failures.
- JavaScript support is still supplied to yt-dlp. A global missing-Deno gate no
  longer rejects metadata from unrelated sites. Remote components remain disabled.
- Playlist results retain only summary metadata, not entries. Flat/lazy extraction
  is bounded to at most one flat entry; there is no batch queue or playlist selection.
  The UI explains the deferred feature and cannot enqueue a playlist.
- Subtitle and automatic-caption tracks are typed metadata only. No subtitle
  download, audio-only, cookie import or login workflow was added.

## History compatibility

**No database migration.** SQLite `user_version` remains 1; settings schema stays 4.
Existing records retain their original values. New records reuse the old opaque
identity column and the successful input URL; recognized secret query values
are redacted before persistence. A signed URL whose credentials expire or are
redacted may need a fresh link for retry. Extractor/source-site persistence is
deferred to the later history migration phase, which must include backup and
failure recovery. The regression fixture verifies old/new records coexist.

## Public metadata smoke — 2026-09-18 UTC

Environment: yt-dlp **2026.08.19**, curl-cffi **0.16.0**, existing system network
policy, no user Cookie/login/netrc. No video/audio files were downloaded.

| Site | Public input | Duration | Format options | Thumbnail bytes | Result |
| --- | --- | ---: | ---: | ---: | --- |
| YouTube | `https://www.youtube.com/watch?v=aqz-KE-bpKQ` | 635 s | 8 | 135454 | PASS |
| Bilibili | `https://www.bilibili.com/video/BV13x41117TL` | 554.117 s | 4 | 146227 | PASS |
| Vimeo | `https://player.vimeo.com/video/76979871` | 62 s | 4 | 41730 | PASS |

All final samples returned a nonempty title and usable normalized formats.
These results do not replace fixture tests or establish download acceptance.

Vimeo limitations retained from earlier attempts:

- Normal pages `https://vimeo.com/56015672` and `https://vimeo.com/76979871`
  required login in this yt-dlp version and mapped to `COOKIE_REQUIRED`.
- Before curl-cffi was installed, a public player sample reported a TLS
  fingerprint block. A separate direct-network attempt timed out and correctly
  mapped to `NETWORK_ERROR`.
- After the supported TLS dependency was installed, the final public player
  sample passed. No HTTPS downgrade, cookie retrieval or login workaround was used.

The dependency choice follows [yt-dlp's official impersonation documentation](https://github.com/yt-dlp/yt-dlp#impersonation)
and the installed yt-dlp version's `pin-curl-cffi` metadata. The installed package
passed `pip check`; the license-collection test and PyInstaller collection probe
passed. A full frozen package build remains a later acceptance gate.

## Local acceptance

Final full pytest: **362 passed in 125.18 seconds**, up from the Phase 1 baseline
of 322. The final focused resolver/boundary/YouTube/metadata-process/history/license
run passed **52 tests**. Secret/path audit and `git diff --check` passed.

Source GUI smoke and startup health passed, with health version 0.4.2.
Light/dark UI verification produced eight screenshots without QML warnings:
generic URL keyboard submission, Verified display, nonblocking Experimental
hint, disabled playlist download and generic About wording.

No changes were made to main, old tags, GitHub Releases/Latest, updater protocols
or production trust roots; no production private key was read.
