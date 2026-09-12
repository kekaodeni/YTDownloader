# YTDownloader v0.4.0 Public Release Audit

Audit date: 2026-09-12
Scope: public-visibility preparation only. No Git history, existing tag, release, or `main` history was rewritten.

## Repository information

```text
Repository: kekaodeni/YTDownloader
Branch: main
Commit: 598d43d7ca3053b4560df39054fa91c4bc464efd
Release: v0.4.0
Default branch: main
```

## Check results

| Check | Result | Evidence / action |
| --- | --- | --- |
| Git history sensitive information | PASS for secrets / CONDITIONAL for environment text | No tracked credential filenames, private-key markers, GitHub token patterns, or cloud-key patterns were found in the current tree or reachable history. Generic application terms such as `token`, `secret`, and `credential` are implementation vocabulary, not secret values. Historical development-environment text is documented below and cannot be removed without rewriting history. |
| Personal and local-environment information | CONDITIONAL | No user-specific Windows home or workspace path is tracked. The machine-specific validation reports and development logs were moved to ignored local `docs/internal/`; the deletion of their tracked public copies is still uncommitted. |
| Release artifact | FAIL | The ZIP contains only the application tree, updater, licenses, and build metadata; it contains no `.git`, tests, private docs, or Codex logs. However, `YTDownloader/BUILD-INFO.json` contains `validation_only: true`, which must not be exposed as a production-public artifact. The current source has zero production trusted keys, so the normal production build correctly refuses to generate a non-validation package. The published asset and its SHA-256 must remain unchanged until a replacement production build is approved. |
| README and homepage content | PASS (pending commit) | The working-tree README uses repository-relative screenshots, accurately states that automatic updating and installation-directory replacement are disabled, contains no private URL or user path, and no longer links to internal validation reports. |
| Release v0.4.0 | PASS | Authenticated GitHub read confirmed the non-draft, non-prerelease latest release `v0.4.0`, its two uploaded assets, the ZIP size `388157728` bytes, and SHA-256 `8574efaddd7d9dc0e6d439acd546df48292c3ed17b9120f2fe8889a25a095aef`. |
| License and third-party notices | PASS | `LICENSE`, `THIRD_PARTY_NOTICES.md`, and the `licenses/` directory are present. FFmpeg, yt-dlp/PySide6 runtime licensing references and bundled license files were found. |
| Git status / ignore protection | CONDITIONAL | The audit added ignore rules for `*.tmp`, local `docs/validation-*/`, `docs/workspace-audit-*/`, and `docs/internal/` records. Existing local validation/audit directories were not deleted and are now protected from accidental staging. The working tree intentionally contains the audit changes, tracked-doc deletions, and this report pending review. |

## Historical release audit

The four remote releases are published and non-draft/non-prerelease. Their uploaded ZIP hashes match the local archives. The following public-content issues were found without changing any historical tag or Release:

| Release | ZIP result | Public issue |
| --- | --- | --- |
| v0.1.0 | 238,263,575 bytes; SHA-256 matches the published asset; no `BUILD-INFO.json` | The published checksum sidecar contains an absolute local Windows workspace path. |
| v0.2.1 | 245,716,358 bytes; SHA-256 matches the published asset; `validation_only` is `false` | The published checksum sidecar contains an absolute local Windows workspace path. |
| v0.3.0 | 245,751,999 bytes; SHA-256 matches the published asset; `validation_only` is `false` | The published checksum sidecar contains an absolute local Windows workspace path. |
| v0.4.0 | 388,157,728 bytes; SHA-256 matches the published asset; `validation_only` is `true` | The ZIP exposes the validation-only marker. Its checksum sidecar is sanitized. |

All four ZIPs contain an application executable and no `.git`, test tree, internal-doc tree, or log directory by archive-name inspection. Existing Release assets and their sidecars were not replaced.

### Historical environment residue

The no-secret result does not mean the historical tree is free of development-environment text. Older reachable commits contain generic application-data paths, host-runtime filtering text, and v0.4 validation documentation mentioning local staging and desktop integration details. No user-specific home path or credential was found. Removing those historical strings would require rewriting commits, which this audit explicitly does not permit; the current branch cleanup only prevents them from being present in the next public tree.

## History and tag preservation

- Reachable history contains 55 commits; no history rewrite was performed.
- Existing tags `v0.1.0`, `v0.2.1`, `v0.3.0`, and `v0.4.0` were left unchanged.
- No force push, tag deletion, release deletion, or `main` history rewrite was performed.

## Post-cleanup verification

- Full test suite: **267 passed in 112.10s**; no failures or errors.
- `git diff --check`: passed.
- The public working tree no longer contains the moved validation reports, draft release notes, implementation log, or the host-specific Codex runtime marker. Their local copies remain under ignored `docs/internal/` for review.
- `docs/release-production-checklist.md` records the production key, trust-root, build-flag, and manifest requirements without containing credentials.
- Local v0.1.0–v0.3.0 checksum sidecars were rewritten to contain only the hash and package filename. The already-published remote sidecars were not changed.
- The production build command stopped before modifying build outputs because the approved production trust root is not configured (`PRODUCTION_TRUSTED_KEYS` count: 0).

## Public blockers to resolve

1. Configure an approved production trust root, build a production package whose metadata does not expose a validation-only marker, and update the v0.4.0 asset and checksum through the normal reviewed release process. Do not change the marker manually in an existing ZIP.
2. Regenerate sanitized checksum sidecars for v0.1.0–v0.3.0 if those historical assets are to be downloadable from a public repository. Otherwise, keep the historical Releases unchanged and label them as historical/development artifacts before publication.
3. Review and commit the removal of machine-specific Icaros/COM registration details, local validation-log paths, and internal test-host notes from the public tree. The original records remain locally under ignored `docs/internal/`.
4. Commit and push the reviewed audit fixes before changing repository visibility. The build configuration now uses a neutral, opt-in host-runtime marker instead of naming the Codex host.

## Conclusion

The repository is **not yet ready for public visibility**. No credential or private-key exposure was detected, but the validation-only build marker and internal environment details in tracked documentation/configuration must be resolved first. No release history modification is required.
