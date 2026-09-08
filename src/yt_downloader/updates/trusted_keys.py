"""Production update trust roots.

This mapping intentionally remains empty until a separately approved production
key ceremony. Remote manifests can never add keys to this trust root.
"""

PRODUCTION_TRUSTED_KEYS: dict[str, bytes] = {}
