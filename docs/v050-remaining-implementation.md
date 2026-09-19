# v0.5.0 remaining implementation evidence

## Scope and baseline

Continue Phase 3–8 on develop, beginning at cbc5f71. Baseline rerun:
362 passed in 123.24 seconds. main, existing tags, releases, production
artifacts and trust roots remain frozen. No production signing or publishing.
Version stays 0.4.2 until RC. Large artifacts belong in isolated temporary sessions.

## Phase 3 — media modes

The structured request owns media mode, audio codec and target quality. The
download option adapter selects independent streams, preserves original audio,
and uses yt-dlp's FFmpeg audio postprocessor for requested conversions. Compatible
M4A/Opus streams are preferred. No video transcoding is introduced. A mode with
no independent source stream is explicitly unavailable; it never silently saves
sound in a video-only output. Actual output streams are checked with ffprobe.

History schema 2 adds mode, audio codec, target bitrate and container. The
pre-migration SQLite backup is retained outside the repository, DDL runs in one
transaction, and injected migration failure preserves schema 1 and its records.
Phase 6 will extend this migration for batch data. The stored bitrate is a user
target, not a claim of improved source quality. Original audio is the default.

Observed RED/GREEN tests cover video-only selection, audio outputs and
postprocessors, pure-audio metadata, UI mode switching and old-history migration.
Additional regression covers rollback of failed migration and mode-specific
stream validation. Local real HTTP + FFmpeg tests verify merged audio/video,
silent video, original audio, MP3 and FLAC files, rather than just option values.

Source GUI smoke and startup health passed (receipt version 0.4.2).
Metadata process self-test returned 0; sandbox Job Object assignment logged
WinError 5, so that environment limitation is not presented as full process
containment acceptance. Light/dark screenshots cover all three media modes;
the QML warning list is empty. Secret/path scan and diff whitespace check passed.
Frozen packages and public download acceptance are not claimed in this phase.
Final full regression: **383 passed in 127.96 seconds**.

## Phase 4 — subtitles

Manual and explicitly enabled automatic captions use typed tracks and original
language codes, with friendly common-language names. The UI provides virtualized
language selection, SRT/VTT, and explicit standalone/embedded policy. Audio-only
and incompatible containers cannot silently enable embedding. An embed failure
is disclosed and keeps independent subtitles plus the successful media. Optional
subtitle errors do not turn successful media into total failure.

Schema 3 adds subtitle policy and actual embed/automatic results, using the same
backup-before-transaction migration mechanism. Local HTTP and real FFmpeg tests
verify VTT preservation, SRT conversion and embedded subtitle tracks; video codec
remains H.264 in the stream-copy embedding fixture. Light/dark subtitle screenshots
and source GUI/startup health passed without QML warnings.

Full regression: **396 passed in 135.13 seconds**. Final subtitle-focused run:
**13 passed**. Public anonymous samples from yt-dlp's official subtitle tests:
QRS8MkLhQmM manual English → SRT (2231 bytes), 8YoUxe5ncPo automatic English →
SRT (48087 bytes), both PASS. Initial sandbox YouTube networking timed out; the
authorized ordinary network environment succeeded. Bilibili BV13x41117TL metadata
passed but returned no subtitles: Bilibili subtitle transfer is NOT VERIFIED.
No Cookie/login was used. Tests downloaded only subtitle text, not public videos.

## Remaining phases

Phase 6
playlist selection, global scheduling and history extension; Phase 7 external
updater recovery dispatch; Phase 8 version bump, RC builds and frozen A–F matrix.
Each phase requires its own focused and full regression before commit.

## Phase 5 — Cookie profiles

Profiles store references only in the local application data directory, separate
from general settings and history. Browser sources use yt-dlp's own loader. File
sources validate Netscape structure without echoing rows; a YoutubeDL adapter
disables cookiefile writeback. Default selection remains none, recommendations
never activate credentials, and profiles can be switched or disabled. Cookie
requirements preserve the URL and expose settings/retry while retaining copyable
technical error details. Names and domain hints are user-owned configuration.

Deterministic tests cover browser options, file options, missing/invalid files,
domain boundaries, persistence, read-only cookiejar lifetime, browser lock/read/
decrypt classifications and retry UI. Real local HTTP confirms a selected fixture
cookie reaches the request without changing its source file. Browser credential
stores and real accounts were not opened during acceptance.

Injected Cookie/Bearer/session/SAPISID values are absent from formatted logs and
copy reports. User profile paths and Netscape rows are redacted. Light/dark Cookie
UI, source GUI smoke and startup health passed; QML warnings were empty. No real
Cookie, browser database, token or private key was used or committed.
Final full regression: **416 passed in 136.11 seconds**.


## Phase 6 — Playlist and shared batch scheduling

Playlist extraction now enumerates flat entries without downloading children.
Selection is explicit, including channel-like collections; unavailable items
remain placeholders. Enumeration is bounded at 1000 displayed entries with a
visible truncation notice. Virtualized selection and deferred thumbnails avoid
creating images for the entire list. Selected children reuse the existing worker
and resolve their actual formats only after receiving a shared queue slot.
Individual child downloads retain the single-item guard to prevent an extractor
from expanding a selected child URL into an unselected playlist.

All tasks share a persisted 1–4 limit (default 2), independently of fragment
concurrency. Pausing stops new starts without interrupting FFmpeg. Cancellation
and retries are per child or per batch; failed-only retry preserves successes.
Modes, subtitle policy and the explicitly selected Cookie profile are frozen in
each batch request. Count/progress UI, expandable children and actual output
metadata are persisted without raw extractor dictionaries or Cookie contents.

Observed RED tests exposed three concurrency defects: a global download lock,
a single pending GUI progress slot, and same-title output replacement. Fixes use
thread-local cancellation dispatch, per-task progress, and non-overwriting atomic
output rename. Qt workers are joined before releasing their owned references.
Eight simultaneous same-title commits now preserve eight distinct payloads.

History migration backs up first, then changes all columns transactionally.
Extension revision 4 adds extractor/site/playlist/batch fields. The legacy core
PRAGMA user_version stays 1: immutable v0.4.2 repository code actually opens,
reads and writes this extended database after simulated installation rollback.
This supersedes Phase 3/4 development-only PRAGMA versions 2/3, which would have
prevented the old application from opening history. Failed migrations preserve
old rows and schema. Existing settings schema 4 accepts the optional concurrency
field; no destructive user-data migration is required.

Focused queue, selection, controller retry and preservation checks passed.
Source GUI smoke and startup health returned app_version 0.4.2. Light/dark
playlist selection and completed-with-errors screenshots were inspected; QML
warnings were empty. Changed-source key/token/local-path scan and diff whitespace
checks passed. These are source/fixture results; public playlist transfer and
frozen updater acceptance remain Phase 8 gates, not claims of this phase.

Final Phase 6 full regression: **431 passed in 138.02 seconds**.
