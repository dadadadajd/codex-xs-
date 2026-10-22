#!/usr/bin/env python3
"""Reproduce repository-owned synthetic shapes; never load customer photographs."""
from pathlib import Path
from PIL import Image, ImageDraw


def generate(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name, size in [("square-2000.png", (2000, 2000)), ("square-1600.jpg", (1600, 1600)),
                       ("desktop.png", (1464, 600)), ("original.png", (600, 300)),
                       ("wrong-size.png", (300, 300)), ("brand-story.png", (362, 453))]:
        image = Image.new("RGB", size, "#f0ebe2")
        draw = ImageDraw.Draw(image)
        w, h = size
        draw.rounded_rectangle((w*.35, h*.15, w*.65, h*.85), radius=12, fill="#333333")
        draw.rectangle((w*.4, h*.2, w*.6, h*.32), fill="#111111")
        draw.text((w*.44, h*.23), "95", fill="white")
        for ratio in (.4, .48, .56, .64, .72):
            draw.line((w*.4, h*ratio, w*.6, h*ratio), fill="#999999", width=3)
        draw.rectangle((w*.72, h*.55, w*.8, h*.85), fill="#444444")
        draw.text((10, 10), "SYNTHETIC TEST ONLY", fill="#333333")
        image.save(destination / name)
    with Image.open(destination / "original.png") as source:
        expanded = Image.new("RGB", (600, 450), "#f0ebe2")
        expanded.paste(source, (0, 75))
        expanded.save(destination / "expanded.png")


if __name__ == "__main__":
    generate(Path(__file__).resolve().parent / "fixtures/images")
