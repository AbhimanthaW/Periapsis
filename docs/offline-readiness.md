# Return Window offline launch

The release serves the architecture workspace, Atlas, region evidence, scoped ranking and both rehearsals from one loopback process. Source products and the synthetic scenarios retain independent identities. No internet service or external credentials are required at launch.

## Build once with network access

Use Node 22, Python 3.12 and uv. From the repository root:

```sh
uv sync --project documentation --locked --python 3.12
npm ci --prefix web
npm ci --prefix web/mission-preview

gh release download mars-cell-map-v0.1.0 --repo AbhimanthaW/Periapsis \
  --dir data/ranking-inputs --pattern cells-enriched.ndjson.gz
gh release download mars-cell-map-v0.2.0 --repo AbhimanthaW/Periapsis \
  --dir data/ranking-inputs --pattern cell-ranking.ndjson.gz \
  --pattern ranking-features.json.gz --pattern cells-enriched-sourced.ndjson.gz \
  --pattern sourced-catalogue-manifest.json

uv run --project documentation --locked --offline python -m runtime.release build data/offline-release
```

The builder checks the pinned input digests, compiles a sourced ranking pack, builds the two web clients, and trains the station model on the deterministic synthetic fixture. `--ranking-pack PATH` accepts an already verified sourced release pack when rebuilding the launcher. The output directory must be new. Its `manifest.json` records the source revision, checkout and bundle file hashes, ranking pack digest and station model ID. Keep the manifest with the bundle and distribute both from a trusted checkout.

On the presentation machine, keep the matching checkout and provision its locked Python environment before disconnecting. A virtual environment contains machine-specific paths and binaries. Prepare it on each machine.

## Start offline

```sh
uv run --project documentation --locked --offline python -m runtime.release serve data/offline-release
```

Open [Return Window](http://127.0.0.1:8000/mission), [the Atlas](http://127.0.0.1:8000/atlas), or [the Arcadia showcase](http://127.0.0.1:8000/demo/#demo/arcadia). To use another loopback port, pass `--port`. Launch verifies the checkout and every packaged file before binding the port. Local API failures return JSON errors. External citations are optional links.

## Release acceptance

1. Use a fresh browser profile on a second machine with networking disconnected.
2. Open the Arcadia showcase. Inspect regional MOLA context and the refusal of 20 m stereo elevation. Switch to the evidence workspace and compare Jezero's reviewed 20 m elevation fallback with Solis Planum or Icaria Planum. Check that sparse regions show regional HEALPix context and uncertainty while withholding local calculations.
3. Rank “ancient lakes with hydrothermal activity” in the Atlas. Confirm that the result states which terms were evaluated and which were skipped.
4. Enter Simulated Marswalk. Confirm baseline return and science times of 40 s and 75 s, then 60 s and 95 s after closing the middle corridor. With 70 s remaining, expect an over-reserve refusal. Close both corridors and expect no route. Completed work must remain visible.
5. Open the separate hazard drill. Advance to the closure and check that the active route only changes after explicit operator approval. Verify that stale readings prevent approval. The seasonal MDAD outlook and the synthetic station model do not grant terrain or hazard qualification.
6. Record the tested commit, manifest digest, machine, results, and timing. Same-machine browser tests block external requests and cover the integration. The disconnected second-machine receipt is required for offline release acceptance.

The [Jezero Float32 producer/consumer check](../evidence/jezero/README.md) is an independent archive control. The [moving-storm, SEP and emergency-hold scenarios](../runtime/docs/live-hazard-map.md) are separate CLI rehearsals. Neither control qualifies tactical routing.
