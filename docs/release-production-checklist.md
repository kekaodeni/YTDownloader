# YTDownloader v0.4.1 Production Release Checklist

This document describes the required production release configuration. It does not contain a private key, key password, token, or other credential. Production signing material must remain outside the repository and outside build logs.

## Release key

- Key algorithm: Ed25519.
- Key ID: **yt-downloader-prod-2026**.
- Private key: encrypted PKCS#8 file stored in an external controlled directory supplied by the release custodian. Use the redacted form `<EXTERNAL_RELEASE_KEY_DIR>\yt-downloader-prod-2026.pem` in public documentation; pass the actual path only to the interactive signing command. Never commit it, place it under `release/`, or write its password to an environment variable or log.
- Public key fingerprint: **d7ed7bd453f35861dee0453d9f805e595e9797cbc1626a8bb59b7488fa037152**. Record only the approved fingerprint and key ID, never the private key.
- Key rotation: add a new approved public key before signing with it; do not trust a key supplied by a remote manifest.

## Trust root

The application trust root is `src/yt_downloader/updates/trusted_keys.py` and contains the approved Ed25519 production key `yt-downloader-prod-2026`.

Required review evidence:

1. The key ID and public-key bytes were approved independently of the build machine.
2. The public-key fingerprint matches the key ceremony record.
3. The private key remains outside the repository and is encrypted.
4. The trust-root change is covered by the update-signature tests.

## Build flag

Production build command:

```powershell
.\scripts\build.ps1
```

Required result:

- Do not pass `-ValidationOnly`.
- `YTDownloader/BUILD-INFO.json` contains `"validation_only": false`.
- `YTDownloader/BUILD-INFO.json` records the exact source commit used for the build.
- The build must run the complete pytest suite, packaged self-tests, ownership validation, license collection, and archive creation.
- The existing validation ZIP must not be overwritten before the new package has been independently hashed and reviewed. Use a separate output directory or filename during review, then copy the approved artifact to the release location.

Validation-only command, for comparison only:

```powershell
.\scripts\build.ps1 -ValidationOnly -ValidationName production-candidate-review
```

This command is not a production release and must not be uploaded as the formal v0.4.1 asset.

## Manifest

After a production package is built and accepted:

- `release/YTDownloader-0.4.1-win64.zip` is hashed with SHA-256.
- `release/YTDownloader-0.4.1-win64.zip.sha256.txt` contains only the hash and package filename; it must not contain an absolute local path.
- `scripts/sign_update.py` is run only with the approved external private key, key ID `yt-downloader-prod-2026`, bilingual release notes, and the independent acceptance report.
- `update-manifest.json` and `update-manifest.sig` are inspected for version, platform, package size, SHA-256, release URL, key ID, and signature before any upload.
- The manifest signature is checked with the public key from the trust root.

## Stop conditions

Stop without creating or uploading a production package if any of these conditions is true:

- `PRODUCTION_TRUSTED_KEYS` is empty or does not contain the approved key ID.
- The private key is inside the repository, build output, or command log.
- `BUILD-INFO.json` reports `validation_only: true`.
- The checksum sidecar contains a machine-specific absolute path.
- The package contains tests, internal validation documents, logs, `.git`, or private environment data.
- The manifest, signature, package hash, or release URL does not match exactly.
