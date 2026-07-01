#!/usr/bin/env python3
"""Create a local bitmap hero asset for the static dashboard."""
from PIL import Image, ImageDraw, ImageFilter


OUT = "assets/electronics-hero.png"
W, H = 1600, 900


def main():
    img = Image.new("RGB", (W, H), "#101318")
    draw = ImageDraw.Draw(img)
    for y in range(H):
        blend = int(18 + (y / H) * 28)
        draw.line([(0, y), (W, y)], fill=(blend, blend + 8, blend + 18))

    # TV panel
    tv_box = (650, 150, 1390, 570)
    draw.rounded_rectangle(tv_box, radius=24, fill="#0b1018", outline="#52627a", width=4)
    draw.rounded_rectangle((682, 184, 1358, 535), radius=16, fill="#172238")
    for x in range(700, 1340, 42):
        color = "#65a7ff" if (x // 42) % 3 else "#9be66d"
        draw.line([(x, 210), (x + 120, 500)], fill=color, width=3)
    draw.rectangle((970, 570, 1070, 615), fill="#263244")
    draw.rounded_rectangle((835, 615, 1205, 640), radius=12, fill="#263244")

    # Console
    draw.rounded_rectangle((330, 360, 500, 680), radius=38, fill="#edf2f7", outline="#9fb0c4", width=3)
    draw.polygon([(455, 365), (510, 398), (505, 650), (452, 677)], fill="#111827")
    draw.rounded_rectangle((375, 392, 438, 650), radius=22, fill="#f8fafc")
    draw.line([(466, 405), (470, 635)], fill="#65a7ff", width=4)

    # Controller
    draw.rounded_rectangle((520, 610, 760, 710), radius=42, fill="#e6edf6", outline="#9fb0c4", width=3)
    draw.ellipse((555, 640, 595, 680), fill="#172238")
    draw.ellipse((680, 640, 720, 680), fill="#172238")
    for x, y in [(648, 636), (668, 656), (648, 676), (628, 656)]:
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="#65a7ff")

    # Media console
    draw.rounded_rectangle((250, 700, 1450, 780), radius=18, fill="#273142")
    draw.rectangle((330, 780, 365, 855), fill="#1d2633")
    draw.rectangle((1335, 780, 1370, 855), fill="#1d2633")

    # Soft vignette
    mask = Image.new("L", (W, H), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rectangle((0, 0, W, H), fill=180)
    mask = mask.filter(ImageFilter.GaussianBlur(80))
    overlay = Image.new("RGB", (W, H), "#000000")
    img = Image.composite(img, overlay, Image.eval(mask, lambda p: max(0, p - 80)))
    img.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()

