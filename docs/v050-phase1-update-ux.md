# v0.5.0 Phase 1 — Update UX and About

## Scope and source

Implemented on develop after `d7a639ad9a3909c34b763f0bd2a4236d4868b104`.
Runtime/package version remains **0.4.2** until the later packaging phase.
The bridge was already merged; this phase does not merge it again.

- About owns manual checks and shows the actual runtime version.
- Settings retains automatic checking and the stable channel.
- Manual discovery opens one update dialog; automatic discovery shows a banner.
- The dialog displays versions, package size, plain-text Chinese/English notes,
  downloaded bytes, percentage, average transfer speed and ETA.
- Closing the dialog does not cancel its download. About can reopen current
  progress or the verified pending package. Explicit cancellation is separate.
- Download completion never installs automatically. The user confirms restart.
- A pending verified package cannot be replaced by a new check. New checks
  clear stale candidates. Retry follows the failed operation, including install
  preparation and helper launch failures.
- Existing media-task shutdown, signed package verification, staging helper,
  transaction, rollback, trust roots and health timing remain unchanged.

## Verification

The implementation used executable RED/GREEN slices for About entry, manual vs
automatic discovery, stale candidates, dialog reopening, explicit confirmation,
progress, preparation failures and frozen acceptance identity.

Final full regression: **322 passed in 115.06 seconds** (baseline: 298).
This includes schema 1 legacy parsing, schema 2, protocol 2, old/internal-layout
staging helpers, transactions/recovery, UI motion and settings/history tests.
The changed-file privacy audit and `git diff --check` passed.

Source GUI smoke and startup health succeeded with receipt version **0.4.2**.
Metadata process self-test returned zero and exercised cancellation and timeout.
It also logged Windows Job Object assignment `Access denied`, including a
repeat outside the sandbox. This is a retained verification limitation in the
unchanged metadata process infrastructure, not a claim of clean Job Object
acceptance.

`scripts/verify_update_ux.py` passed in light/dark themes at actual device pixel
ratios **1.25, 1.5 and 2.0**, recording 36 screenshots with no QML warnings.
Checks include About, the settings update section, long plain-text notes,
scrolling, keyboard language selection, Escape, hover, reduced motion and
preparation failure recovery. The script requires `--expected-dpr` because
`QT_SCALE_FACTOR` multiplies the native desktop scale; the environment variable
alone does not prove the effective scale.

Example (set the scale factor to target DPR divided by native DPR):

```powershell
python scripts/verify_update_ux.py --expected-dpr 1.5 --output <NEW_OUTPUT_DIRECTORY>
```

Frozen GUI verification now requires explicit identity:

```powershell
python scripts/verify_quick_package.py --exe <PACKAGE_DIRECTORY>/YTDownloader.exe --expected-version <VERSION> --expected-source-commit <COMMIT> --output <NEW_OUTPUT_DIRECTORY>
```

It checks BUILD-INFO before starting the executable, binds a fresh health receipt
to the expected version and transaction, records the EXE SHA256, and rejects
executable/metadata changes during acceptance. Output directories must be new
to prevent stale reports from appearing to describe a failed run.

## Deferred gates

This source/UI acceptance is **not** a new frozen A–F or public-network upgrade
acceptance. Full frozen chains belong to Phase 7/8. Main-application dispatch to
the existing recovery helper still requires integration and acceptance there.
Future v0.5 packages use internal helper layout and schema 2; release discovery
continues to use the Releases list and highest compatible stable version.

No production package was built or signed, no release was created or changed,
and no production private key was read. Old tags, main and published assets
remain frozen. GitHub Latest remains reserved for the v0.4.2 legacy bridge.
