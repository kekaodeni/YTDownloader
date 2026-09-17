# Updater bridge protocol

The v0.4.2 bridge is built from stable main. It does not include v0.5 media features.

## Release discovery

Keep v0.4.2 as GitHub Latest permanently: unmodified v0.4.1 only calls `/releases/latest`. Publish subsequent stable releases with `make_latest=false` and verify the Latest endpoint after publishing. README downloads must link to an explicit current stable version, not Latest.

Starting with v0.4.2, enumerate the official repository's releases (100 per page, at most 20 pages, 60 second enumeration deadline). Ignore drafts, prereleases, invalid versions and non-upgrades, then order by SemVer. Verify each candidate's detached Ed25519 signature before applying minimum application/helper versions and protocol capabilities. A signed incompatible candidate may be skipped; a bad signature, bad supported schema or failed request must not silently fall back. Incomplete enumeration is an error. Only a selected compatible version advances the persisted anti-rollback floor.

## Two package contracts

| Target | Manifest | Required installer protocol | Layout | Helper capabilities |
|---|---|---|---|---|
| 0.4.2 | schema 1, unchanged field set | 1 | root helper | 1 and 2 |
| 0.5.0+ | schema 2 | 2 | internal-v1 | 2 |

Both use `YTDownloader-{version}-win64.zip`, `update-manifest.json` and `update-manifest.sig`. Signature is Base64 Ed25519 over the exact UTF-8 JSON bytes. Each layout gets its own complete SHA256SUMS at build time. Never delete a root helper after installation or rewrite installed ownership manifests.

Schema 2 retains every schema 1 top-level field and adds:

- `minimum_updater_version`: minimum installed helper SemVer, initially `0.4.2`.
- `helper_layout`: `internal-v1`, mapped only to `_internal/updater/YTDownloaderUpdater.exe`.
- `package.kind`: `standard`.

`minimum_auto_update_version` initially equals `0.4.2`; it is separate from the helper version. `updater_protocol` is the target package requirement, not a remote grant of helper capability. Both schemas reject duplicate keys, missing/unknown fields, wrong identity, unsafe URLs, non-positive sizes and malformed hashes. Unknown newer protocol numbers can be authenticated but cannot be selected by an incapable client. Schema 2 cannot request protocol 1.

## Execution boundary

The bridge copies its **installed root helper** to owned transaction staging; it does not execute code from the candidate package. From v0.5 onward the installed internal helper is staged instead. Reverify signature, package and helper before launch and again inside the helper. Candidate and backup are same-volume siblings of the installation; user data stays outside these trees.

Source/validation builds cannot auto-install. Test trust roots and transport hooks exist only in isolated frozen test builds, never in production source or distributable validation packages. Production signing and publication require separate authorization.
