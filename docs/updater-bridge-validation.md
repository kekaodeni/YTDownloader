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
