"""Compose portable extensions from the single checked-in asset source."""
from pathlib import Path

BROWSER_FOLDERS = {'chrome': 'Chrome', 'edge': 'Edge', 'firefox': 'Firefox'}


def bundle_extensions(resources, destination):
    """Write missing build assets; refuse to overwrite any different content.

    Runtime frozen installations never call this builder. Repeated build hooks
    are safe when their output is identical; unknown/user-modified files stay.
    """
    resources, destination = Path(resources), Path(destination)
    shared = resources / 'shared'
    if not (shared / 'popup.html').is_file():
        raise FileNotFoundError('Browser extension source assets missing')
    outputs = {}
    for browser, name in BROWSER_FOLDERS.items():
        for source in shared.rglob('*'):
            if source.is_file():
                outputs[destination / name / source.relative_to(shared)] = source.read_bytes()
        outputs[destination / name / 'manifest.json'] = (resources / 'manifests' / (browser + '.json')).read_bytes()
    # Preflight every destination before writing, including later browsers.
    for path, content in outputs.items():
        if path.exists() and (not path.is_file() or path.read_bytes() != content):
            raise FileExistsError('Existing extension assets differ; use a fresh build directory')
    for path, content in outputs.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return destination


def bundle_portable_extensions(resources, package):
    resources, package = Path(resources), Path(package)
    bundle_extensions(resources, package / 'BrowserExtensions')
    readme = package / 'README.md'
    content = (resources / 'README.md').read_bytes()
    if readme.exists() and readme.read_bytes() != content:
        raise FileExistsError('Existing portable README differs; use a fresh build directory')
    if not readme.exists():
        readme.write_bytes(content)
