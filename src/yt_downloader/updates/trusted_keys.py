"""Production update trust roots.

Only public Ed25519 keys approved through the release-key ceremony belong here.
Remote manifests can never add keys to this trust root.
"""

PRODUCTION_TRUSTED_KEYS: dict[str, bytes] = {
    "yt-downloader-prod-2026": bytes.fromhex(
        "794218ec979f166eeeadd958f5c4572563762ab7bc402f5801fd112d8ccae820"
    ),
}
