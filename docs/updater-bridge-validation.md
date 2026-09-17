# Updater bridge validation

## Baseline (2026-09-17)

- Branch: `release/v0.4.2-updater-bridge`, created from stable `main`.
- Main commit: `f8bbf018e74e59878ced8a0b4e3c0bf017ff5606`.
- v0.4.1 commit: `199c72606b3ca28b510246b22860c57e69bddeb6`.
- Application, tests, dependency requirements and packaging specs match v0.4.1.
- Python 3.12.8; restored the exact development dependency snapshot; `pip check` passed.
- `python -B scripts/run_isolated_regression.py bridge-baseline -q`: **269 passed**, 94.37 seconds, no skips.
- This suite includes real local FFmpeg integration. Windows Shell thumbnail checks and notifications are deliberately isolated; it does not prove Explorer integration.
- Offscreen Qt Quick check: 27 screenshots, no QML warnings. Offscreen fonts displayed missing glyphs, so this is not native visual acceptance.
- Native Windows Qt Quick check: 27 screenshots, no QML warnings, 150% scaling, software renderer. Settings screenshot inspected: Chinese glyphs and layout render correctly.

Only the existing development staging, build and verification support needed by this work was brought from develop. No application behavior was changed for the baseline. Main, develop and published tags were not modified. No production private key was accessed.

Production-key, published-binary upgrade verification remains a separate release gate. Test-key frozen upgrades must never be reported as production-signature verification.

## Phase 1: protocols and discovery

- Captured v0.4.1 parser and discovery source verbatim with commit/hash provenance; exercised them dynamically.
- Observed RED then GREEN for schema 2 acceptance, list discovery/compatible selection, official pagination transport, and invalid schema/protocol rejection.
- Targeted tests cover signature failure without fallback, minimum app/helper versions, unsupported protocol, prerelease/draft filtering, incomplete pagination and the legacy Latest bridge.
- Full isolated regression: **286 passed**, 89.84 seconds, no skips.
- Native Windows Qt Quick regression: 27 screenshots, zero QML warnings, 150% scaling.

## Phase 2: preparation, layout and recovery

- Added independent installation preparation and helper staging under the transaction directory.
- Legacy root-helper and internal-helper trees are validated separately; mixed layouts, links, reparse points, path escape, package tampering and transaction binding changes are rejected.
- The external helper revalidates the signed manifest, package size/hash, installed tree and staged helper before creating a candidate directory. Recovery accepts both schema 1 journals and the new schema 2 journal metadata.
- Restored staged packages are gated again by the current application/helper protocol capability after a restart.
- Targeted bridge, transaction, fault-matrix and helper-entry tests: **24 passed**.
- Full regression after the implementation: **298 passed**.

## Phase 3: validation candidate

- Validation-only build: `release/YTDownloader-0.4.2-validation-only-win64.zip`.
- Archive SHA-256: `4d77b2d6b1db58acc0f7510e885a8eba55f62a55616471b599e81639c67fcb5b`.
- Archive size: `379399281` bytes; extracted file size: `891400083` bytes.
- `BUILD-INFO.json` reports app `0.4.2`, `legacy-root`, protocol `1`, and helper protocols `[1, 2]`; the root helper is present as required for the bridge package.
- Independent archive acceptance passed ownership, packaged self-test, metadata helper, GUI smoke, windowed updater and startup health checks.
- Native Windows Qt Quick regression after implementation: 27 screenshots, zero QML warnings, 150% scaling, software renderer.

Formal production signing, publication, merge and tag creation remain intentionally unperformed and require separate authorization.
