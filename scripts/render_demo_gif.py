"""
Turn a recorded demo into the README GIF: the browser video with a caption strip under it.

    python examples/self_healing_demo.py --record
    python scripts/render_demo_gif.py visor_workspace/videos/self_healing.webm examples/self_healing.gif

Captions come from the .captions.json the demo writes next to the video, so they sit
below the page instead of on it (on the page, OCR would read them).
Needs ffmpeg and Pillow (pip install pillow).
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

FPS = 10
STRIP = 92  # caption strip height, px


def font(names, size):
    for name in names:
        for path in glob.glob(f"/System/Library/Fonts/{name}") + glob.glob(f"/usr/share/fonts/**/{name}", recursive=True):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


def main(video, out):
    with open(video.replace(".webm", ".captions.json")) as f:
        timeline = json.load(f)
    title = font(["Helvetica.ttc", "DejaVuSans-Bold.ttf"], 22)
    mono = font(["Menlo.ttc", "DejaVuSansMono.ttf"], 15)

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={FPS}", f"{tmp}/f%05d.png"], check=True)
        frames = sorted(glob.glob(f"{tmp}/f*.png"))
        for i, path in enumerate(frames):
            t = i / FPS
            caption, detail = "", ""
            for start, c, d in timeline:
                if start <= t:
                    caption, detail = c, d
            page = Image.open(path).convert("RGB")
            w, h = page.size
            frame = Image.new("RGB", (w, h + STRIP), (17, 21, 30))
            frame.paste(page, (0, 0))
            draw = ImageDraw.Draw(frame)
            draw.text((22, h + 14), caption, font=title, fill=(255, 255, 255))
            draw.multiline_text((22, h + 46), detail, font=mono, fill=(159, 227, 201), spacing=4)
            frame.save(path)

        palette = f"{tmp}/palette.png"
        subprocess.run(["ffmpeg", "-v", "error", "-i", f"{tmp}/f%05d.png", "-vf", "palettegen=max_colors=128", palette], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", f"{tmp}/f%05d.png", "-i", palette,
                        "-lavfi", "paletteuse=dither=none", "-loop", "0", out], check=True)
    print(f"{out}: {os.path.getsize(out) / 1e6:.1f} MB, {len(frames) / FPS:.0f} s")


if __name__ == "__main__":
    main(*sys.argv[1:3])
