"""Compare Explore, Ranked Areas and Investigation to their original 2x PNGs."""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageChops
from compare import side_by_side

STATES = [
    ("01-planetary-explore", "01 Planetary Explore.png", [
        (0, 0, 1440, 62), (307, 605, 1047, 884), (1081, 83, 1422, 565),
    ]),
    ("01b-ranked-areas", "01b Cell ranking from the service.png", [
        (45, 77, 1395, 425), (45, 823, 1395, 888),
    ]),
    ("02-region-investigation", "02 Region Investigation.png", [
        (971, 65, 1427, 625), (18, 78, 424, 275), (15, 819, 960, 886),
    ]),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("references", type=Path)
    parser.add_argument("review", type=Path)
    args = parser.parse_args()
    out = args.review / "comparisons"
    out.mkdir(parents=True, exist_ok=True)
    hashes = {}
    sections = []
    for slug, filename, crop_boxes in STATES:
        reference = args.references / filename
        hashes[filename] = hashlib.sha256(reference.read_bytes()).hexdigest()
        capture = args.review / "captures" / f"{slug}.png"
        with Image.open(reference) as raw, Image.open(capture) as rendered:
            if raw.size != (2880, 1800) or rendered.size != raw.size:
                raise ValueError(f"{slug}: expected 2880 × 1800, got {raw.size} and {rendered.size}")
            source, browser = raw.convert("RGB"), rendered.convert("RGB")
            side_by_side(source, browser, out / f"{slug}-side-by-side.jpg", 1080)
            for index, box in enumerate(crop_boxes, 1):
                crop = tuple(item * 2 for item in box)
                side_by_side(source.crop(crop), browser.crop(crop),
                             out / f"{slug}-detail-{index}.jpg", min(1040, box[2] - box[0]))
            diff = ImageChops.difference(source, browser)
            diff.save(out / f"{slug}-diff.png")
            diff.point(lambda value: min(255, value * 3)).save(out / f"{slug}-diff-amplified.png")
        if args.references.resolve() == (args.review / "originals").resolve():
            original = f'<a href="originals/{quote(filename)}">Original PNG</a>'
        else:
            original = ""
        details = " ".join(
            f'<a href="comparisons/{slug}-detail-{index}.jpg">Detail {index}</a>'
            for index in range(1, len(crop_boxes) + 1)
        )
        sections.append(f"""
        <section><h2>{escape(Path(filename).stem)}</h2>
          <nav>{original} <a href="captures/{slug}.png">Playwright PNG</a>
            <a href="comparisons/{slug}-diff.png">Pixel diff</a>
            <a href="comparisons/{slug}-diff-amplified.png">Amplified diff</a>
            {details}</nav>
          <a href="comparisons/{slug}-side-by-side.jpg"><img
            src="comparisons/{slug}-side-by-side.jpg" alt="Reference and browser capture side by side"></a>
        </section>""")
    (args.review / "index.html").write_text("""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Return Window · Explore slice review</title>
<style>
:root{color-scheme:dark;font:16px/1.5 system-ui;background:#120e0c;color:#f2e9e0}
body{max-width:1500px;margin:auto;padding:28px} h1,h2,p{margin:0 0 10px}
section{margin:32px 0} nav{display:flex;gap:10px 20px;flex-wrap:wrap;margin-bottom:12px}
a{color:#f0a276} a:focus-visible{outline:2px solid #f0a276}
img{display:block;width:100%;height:auto;border:1px solid #ffffff26;border-radius:7px}
.muted{color:#c1b3a8}
</style>
<h1>Return Window · Explore slice</h1>
<p class="muted">Chromium captured 1440 × 900 CSS pixels at 2×. Originals are 2880 × 1800 pixels.
The left image is the reference; the right image is the running app.</p>
<p><a href="design-qa.md">Review notes</a> · <a href="originals.sha256.json">Original file digests</a></p>
""" + "".join(sections) + "</html>\n")
    (args.review / "originals.sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")


if __name__ == "__main__":
    main()
