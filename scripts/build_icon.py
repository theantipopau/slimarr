"""Convert images/icon.PNG to images/icon.ico (multi-size)."""
import sys
import pathlib
from PIL import Image

root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).parent.parent

src = root / "images" / "icon.PNG"
dst = root / "images" / "icon.ico"

img = Image.open(src).convert("RGBA")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
imgs = [img.resize(s, Image.LANCZOS) for s in sizes]
imgs[0].save(dst, format="ICO", sizes=sizes, append_images=imgs[1:])
print(f"icon.ico created -> {dst}")
