"""Build the reference gallery from the final Playwright captures."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageChops, ImageDraw

QA = Path(__file__).resolve().parent
DEFAULT_REFERENCES = QA.parents[3] / "Return Window — UI References"


def side_by_side(original, capture, output, width):
    height = round(original.height * width / original.width)
    composite = Image.new("RGB", (width * 2 + 12, height + 29), "#201a16")
    labels = ImageDraw.Draw(composite)
    labels.text((10, 8), "ORIGINAL", fill="#f5eee7")
    labels.text((width + 22, 8), "PLAYWRIGHT", fill="#f5eee7")
    for x, source in [(0, original), (width + 12, capture)]:
        composite.paste(source.resize((width, height), Image.Resampling.LANCZOS), (x, 29))
    composite.save(output, quality=93, subsampling=0)


def build_gallery(references):
    comparison_dir = QA / "comparisons"
    comparison_dir.mkdir(exist_ok=True)
    index = [
        "# Return Window reference gallery", "",
        "Start the app on port 4173 before opening a state link. Set 03d to 768 × 1024 CSS pixels in the browser. All other states use 1440 × 900. Each browser PNG was captured at 2×.",
        "", "| Reference | App state | Browser capture | Comparison | Difference |",
        "| --- | --- | --- | --- | --- |",
    ]
    focused = {
        "01": [(307,605,1047,884),(1081,83,1422,565)],
        "01a": [(46,84,1394,412)],
        "02": [(971,65,1427,624),(18,78,424,275)],
        "02a": [(39,229,489,674)], "02b": [(1013,84,1395,544)],
        "03": [(1080,64,1423,650)], "03a": [(340,97,991,545)],
        "03b": [(24,642,1416,877)], "03c": [(36,275,1405,634)],
        "03d": [(12,704,760,1015)], "03e": [(18,70,500,670)],
        "04": [(15,67,350,422)], "04a": [(243,239,1195,659)],
        "05": [(225,83,1008,560)], "05a": [(225,81,968,484)],
        "05b": [(1031,75,1421,557)], "05c": [(229,168,1055,628)],
        "05d": [(1005,77,1420,534)], "06": [(1111,52,1426,504)],
        "06a": [(15,66,338,485)], "06b": [(1010,164,1345,425)],
        "06c": [(844,75,1420,587)], "07": [(1128,105,1424,457)],
        "07a": [(84,221,1359,507)],
    }
    for code, filename, state, *extra in json.loads((QA / "states.json").read_text()):
        slug = extra[0] if extra else code
        css_size = extra[1] if len(extra) > 1 else (1440, 900)
        source_path = references / filename
        capture_path = QA / "captures" / f"{slug}.png"
        with Image.open(source_path) as source, Image.open(capture_path) as browser:
            target_size = tuple(pixel * 2 for pixel in css_size)
            if source.size != target_size or browser.size != target_size:
                raise ValueError(f"{code} expected {target_size}, got {source.size} and {browser.size}")
            source = source.convert("RGB")
            browser = browser.convert("RGB")
            side_by_side(source, browser, comparison_dir / f"{slug}-side-by-side.jpg", 1152 if code != "03d" else 768)
            for number, box in enumerate(focused[code], 1):
                crop = tuple(position * 2 for position in box)
                side_by_side(source.crop(crop), browser.crop(crop), comparison_dir / f"{slug}-detail-{number}.jpg", min(1050, box[2]-box[0]))
            ImageChops.difference(source, browser).point(lambda value: min(255,value * 3)).save(comparison_dir / f"{slug}-diff.png")
        reference_link = quote(os.path.relpath(source_path, QA))
        index.append(f"| [{filename[:-4]}]({reference_link}) | [Open](http://127.0.0.1:4173/#{state}) | [PNG](captures/{slug}.png) | [Side by side](comparisons/{slug}-side-by-side.jpg) · [Detail](comparisons/{slug}-detail-1.jpg) | [Pixel diff](comparisons/{slug}-diff.png) |")
    (QA / "gallery.md").write_text("\n".join(index) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("references", type=Path, default=DEFAULT_REFERENCES, nargs="?")
    build_gallery(parser.parse_args().references.resolve())
