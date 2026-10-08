"""Build complete Chrome/Edge/Firefox directories; no JS build runtime required."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from yt_downloader.browser_companion.distribution import bundle_portable_extensions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    bundle_portable_extensions(args.resources, args.package)


if __name__ == '__main__':
    main()
