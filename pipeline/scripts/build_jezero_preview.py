"""Build the pinned Jezero elevation-preview pack in a new directory."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/jezero"
SOURCE_SHA = "ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2"
WINDOW_SHA = "020df24a32a2ab472db7c9ddb2538073130916308edcfb6830fe22d08c3e8903"
MANIFEST_SHA = "c19aa33379f5b588d9097ba591ccdeabc5ebedf92b740ade5875e7e7e24addc8"
VERTICAL_REFERENCE = "USGS CTX mosaic source elevations in metres with MOLA localization of added DEMs per catalogue"


def encode(document):
    return (json.dumps(document, indent=2, allow_nan=False) + "\n").encode()


def verified_window(path):
    with path.open("rb") as stream:
        raw = stream.read(4_194_305)
    if len(raw) != 4_194_304 or sha256(raw).hexdigest() != WINDOW_SHA:
        raise ValueError("Jezero Float32 window checksum or size differs")
    return raw


def build(window, destination):
    raw = verified_window(window)
    manifest_bytes = (EVIDENCE / "jezero.json").read_bytes()
    if sha256(manifest_bytes).hexdigest() != MANIFEST_SHA:
        raise ValueError("prepared Jezero manifest checksum differs")
    manifest = json.loads(manifest_bytes)
    evidence_bytes = (EVIDENCE / "jezero-evidence.json").read_bytes()
    evidence = json.loads(evidence_bytes)
    product, = evidence["products"]
    if (product["source_url"] != manifest["source"]["url"]
            or not any(WINDOW_SHA in item for item in product["provenance"])
            or not any(MANIFEST_SHA in item for item in product["provenance"])):
        raise ValueError("Jezero evidence source linkage differs")
    wkt = product["source_crs"]["definition"]
    source = dict(id=product["id"], version=product["version"], kind="source_backed", recipe_id="ctx-window-r1978-c732",
                  attribution="USGS Astrogeology / NASA MRO CTX", native_spacing_m=20, effective_scale_m=None,
                  limitations=["Elevation preview only", "Band has no unit tag. Prepared manifest declares metres."],
                  url=product["source_url"], source_sha256=SOURCE_SHA, window_sha256=WINDOW_SHA, native_crs_wkt=wkt,
                  vertical_reference=VERTICAL_REFERENCE, transform_policy="Native, unresampled pixel-is-area window")
    files = {"sources": ("source-manifest.json", encode(dict(schema_version=1, sources=[source]))),
             "evidence": ("evidence.json", evidence_bytes), "preview_grid": ("elevation.f32", raw)}
    site = dict(schema_version=1, pack_id="rw-jezero-preview", pack_version="1.0.0", region_id="43",
                classification="source_backed", build_id="ctx-window-r1978-c732",
                processed_at=manifest["source"]["prepared"], capabilities=["elevation_preview"],
                omissions=["Effective feature scale is unqualified", "Tactical terrain and routing are unsupported"],
                gates={f"G{i}": dict(state="unsupported" if i in (4, 7) else "not_evaluated",
                                    reason="Tactical capability unsupported" if i in (4, 7) else "No formal release receipt")
                       for i in range(1, 11)},
                preview=dict(dtype="<f4", order="C", shape=[1024, 1024], affine=[20,0,4343640,0,-20,1103860],
                             bounds_m=[4343640,1083380,4364120,1103860], pixel_reference="area",
                             row_order="north_to_south", index_order="row_col", position_order="easting_northing",
                             reference=dict(source_crs_wkt=wkt, local_crs_wkt=wkt, horizontal_unit="m", vertical_unit="m",
                                            vertical_reference=VERTICAL_REFERENCE, native_spacing_m=20)),
                artifacts={role: dict(path=name, sha256=sha256(data).hexdigest(), size_bytes=len(data))
                           for role, (name, data) in files.items()})
    destination.mkdir()
    try:
        for name, data in files.values():
            (destination / name).write_bytes(data)
        (destination / "site.json").write_bytes(encode(site))
    except OSError:
        shutil.rmtree(destination)
        raise
    return destination / "site.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("window", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(build(args.window, args.destination))
