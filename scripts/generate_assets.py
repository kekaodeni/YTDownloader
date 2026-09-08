"""Package the approved generated master as PNG and multi-resolution Windows ICO."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
master = ASSETS / "app-icon-master.png"
if not master.is_file():
    raise SystemExit("Missing approved app-icon-master.png; do not regenerate the artwork implicitly.")
with Image.open(master) as source:
    image = source.convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
    image.save(ASSETS / "app-icon.png")
    image.save(ASSETS / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(ASSETS / "app.ico")
