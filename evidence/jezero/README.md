# Jezero CTX elevation preview

The committed `jezero.json` is the exact manifest in Martian Map's preserved browser ZIP. Its SHA-256 is `c19aa33379f5b588d9097ba591ccdeabc5ebedf92b740ade5875e7e7e24addc8`. The external `jezero-elevation.f32` is the 4,194,304-byte archive member `data/jezero-elevation.f32`, SHA-256 `020df24a32a2ab472db7c9ddb2538073130916308edcfb6830fe22d08c3e8903`. It contains the 1,024×1,024 USGS window at row 1978, column 732, with a 20 m native posting. The evidence sidecar contains the usable support inset by one pixel.

From the repository root, obtain the pinned USGS GeoTIFF at the URL in `jezero.json`. Its expected size is 90,345,300 bytes and SHA-256 is `ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2`. Then run:

```sh
window="$(mktemp -d)"
cp evidence/jezero/jezero.json "$window/"
uv run --project documentation --locked --group archive-check python pipeline/scripts/verify_jezero.py "$window" --source /path/to/pinned.tif --reconstruct > "$window/evidence.json"
cmp "$window/evidence.json" evidence/jezero/jezero-evidence.json
python3 pipeline/scripts/build_jezero_preview.py "$window/jezero-elevation.f32" "$window/preview-pack"
```

For the offline source path, extract just the two known members from the verified original browser ZIP into a fresh external directory and use the same pack builder. The output directory must be new. The builder checks the immutable input window and its lineage. Preview release acceptance still requires independent review. [USGS catalogue](https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic)
