"""Deterministically generate the Windows application icon."""

from pathlib import Path
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
size = 1024
image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((72, 72, 952, 952), radius=224, fill="#0067C0")
draw.rounded_rectangle((104, 104, 920, 920), radius=194, fill="#0F78D1")
draw.polygon(((512, 220), (512, 585), (365, 438), (292, 511), (512, 731), (732, 511), (659, 438), (512, 585)), fill="white")
draw.rounded_rectangle((265, 735, 759, 806), radius=34, fill="white")
png_path = ASSETS / "app-icon.png"
ico_path = ASSETS / "app.ico"
image.save(png_path)
image.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(ico_path)

