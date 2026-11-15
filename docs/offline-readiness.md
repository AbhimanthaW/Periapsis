# Return Window offline launch

The release serves Explore, Operations, region evidence, scoped ranking and both rehearsals from one loopback process. Source products and the synthetic scenarios retain independent identities. No internet service or external credentials are required at launch.

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

The builder checks the pinned input digests, compiles a sourced ranking pack, builds the two web clients, and trains the station model on the deterministic synthetic fixture. `--ranking-pack PATH` accepts an already verified sourced release pack when rebuilding the launcher. The output directory must be new. Its `manifest.json` records the source revision, checkout and bundle file hashes, ranking pack digest and station model ID. Keep the manifest with the bundle and distribute both from a trusted checkout. A passing push run also publishes the bundle as a GitHub Actions artifact for that commit.

On the presentation machine, keep the matching checkout and provision its locked Python environment before disconnecting. A virtual environment contains machine-specific paths and binaries. Prepare it on each machine.

## Start offline

```sh
uv run --project documentation --locked --offline python -m runtime.release serve data/offline-release
```

Open [Explore](http://127.0.0.1:8000/explore) or [the Operations UI](http://127.0.0.1:8000/demo/). To use another loopback port, pass `--port`. Launch verifies the checkout and every packaged file before binding the port. Local API failures return JSON errors. External citations are optional links.

## Release acceptance

1. Use a fresh browser profile on a second machine with networking disconnected.
2. Open the Operations UI and choose **Demo**. Inspect regional MOLA context and the refusal of 20 m stereo elevation. Enter the synthetic Marswalk, approve the proposed route in Monitor, record departure, report a crew position and close the middle corridor. Verify the recomputed return reaches the same synthetic base and awaits approval. Compare the Jezero control, HPX128:96848, with a sparse cell such as HPX128:0. Sparse cells should show regional evidence and uncertainty while withholding unsupported local calculations.
3. Rank “ancient lakes with hydrothermal activity” in Ranked cells. Confirm that the result states which terms were evaluated and which were skipped.
4. Open the fixed-fixture regression at `/mission?view=simulation`. Confirm baseline return and science times of 40 s and 75 s, then 60 s and 95 s after closing the middle corridor. With 70 s remaining, expect an over-reserve refusal. Close both corridors and expect no route. Completed work must remain visible.
5. Open the separate hazard drill. Advance to the closure and check that the active route only changes after explicit operator approval. Verify that stale readings prevent approval. The seasonal MDAD outlook and the synthetic station model do not grant terrain or hazard qualification.
6. Record the tested commit, manifest digest, machine, results, and timing. Same-machine browser tests block external requests and cover the integration. The disconnected second-machine receipt is required for offline release acceptance.

Use these claims in the demo and slides:

- The atlas uses 196,608 HEALPix cells. Named landmarks help orient the operator. Evidence coverage varies by cell.
- Ranking is exploratory. The sensitivity sweep retained 9–10 of 20 shallow-ice results and 14 of 20 young-volcanism results in the failing cases, below the 16-of-20 threshold.
- Arcadia has regional MOLA context. The reviewed footprint lacks qualifying data for the requested 20 m stereo calculation, so tactical routing is withheld.
- The Marswalk route and hazard drill use synthetic inputs. The planner recomputes the return after a closure, and the operator approves the proposed change.

Suggested narration: “I’ll open Arcadia with Demo. We can see the regional topography from MOLA, but this footprint lacks the terrain data needed for a 20 metre calculation. In the labeled rehearsal, I’ll approve a route, close a corridor after departure and check the return to the same base before approving the change.”

The [Jezero Float32 producer/consumer check](../evidence/jezero/README.md) is an independent archive control. The [moving-storm, SEP and emergency-hold scenarios](../runtime/docs/live-hazard-map.md) are separate CLI rehearsals. Neither control qualifies tactical routing.

## Cell-first Explore and selectable-base rehearsal

Open [Explore](http://127.0.0.1:8000/explore). Rotate the globe by dragging or
with the arrow keys, then select a point or enter an HPX128 cell ID. Switch
between Viking colour and MOLA relief without losing the selected cell or base.
Use Ranked cells for the sourced ranking API. Named features are approximate
orientation aids.

Use **Demo** to fill the objective and select the Arcadia cell and its pinned
local evidence review. Inspect the supported MOLA fallback and the withheld
20 m calculation. Choose **Enter simulated Marswalk** to submit the preset
synthetic sortie for operator review. The preset starts at local row 1, column 1 with
130 seconds, and both inputs can be changed. Approve a route in Monitor,
record departure, report a simulated crew position and apply a closure.
Recalculate from that position to the same base. The separate hazard replay
shows local compute or bundled playback and requires operator approval.

The original four-answer regression remains available in the fixed-fixture
Mission simulation. For a second-machine acceptance, run both workflows
with networking disconnected.
