"""Interactively sign a formal update package with a repository-external key."""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path

from yt_downloader.updates.signing import create_signed_release_assets
from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--private-key', required=True, type=Path)
    parser.add_argument('--key-id', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--minimum-auto-update-version', default='0.4.0')
    parser.add_argument('--schema-version', type=int)
    parser.add_argument('--minimum-updater-version')
    parser.add_argument('--notes-zh', required=True, type=Path)
    parser.add_argument('--notes-en', required=True, type=Path)
    parser.add_argument('--acceptance-report', required=True, type=Path)
    args = parser.parse_args()
    password = getpass('Encrypted Ed25519 private-key password: ').encode('utf-8')
    create_signed_release_assets(
        package=args.package, private_key_path=args.private_key, password=password,
        key_id=args.key_id, trusted_keys=PRODUCTION_TRUSTED_KEYS,
        repo_root=Path(__file__).resolve().parents[1], version=args.version,
        minimum_auto_update_version=args.minimum_auto_update_version,
        notes_zh_cn=args.notes_zh.read_text(encoding='utf-8'),
        notes_en=args.notes_en.read_text(encoding='utf-8'),
        acceptance_report_path=args.acceptance_report,
        schema_version=args.schema_version,
        minimum_updater_version=args.minimum_updater_version,
    )
    print('Created update-manifest.json and update-manifest.sig beside the package.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
