# Return Window offline launch

The default URL opens the mission interface. One local process serves the UI, planetary imagery, ranking, region evidence, synthetic Marswalk planner and hazard replay.

## Prepare and launch

Use Node.js 22.12 or later in the Node 22 series and uv. Clone the repository or extract the GitHub ZIP. From the repository root, run:

```sh
uv run --project documentation --locked --python 3.12 python -m runtime.release launch
```

Open [Return Window](http://127.0.0.1:8000/). The first run downloads and verifies the pinned ranking inputs, builds the local frontend assets, and trains the station model on the synthetic fixture. Run the same command to reuse a bundle under `data/launch/` for these source files. Add `--port 8017` to use another loopback port.

Prepare the bundle and locked Python environment online on each presentation machine. For a network-disconnected launch, add `--offline` to the uv options before `python`. The server verifies the recorded source files and packaged hashes before binding to loopback. External source links are optional.

## Run a prebuilt bundle

A successful GitHub Actions push run publishes an offline bundle for its commit. Extract it to `data/offline-release` alongside the matching source checkout, install the locked environment with `uv sync --project documentation --locked --python 3.12`, then run:

```sh
uv run --project documentation --locked --offline python -m runtime.release serve data/offline-release
```

Use `runtime.release build` with a new destination to create a standalone bundle from already installed frontend dependencies. Use `--ranking-inputs PATH` for the downloaded input files or `--ranking-pack PATH` for a previously built sourced release pack. Keep the source, manifest and bundle together.

## Release acceptance

1. Use a fresh browser profile on a second machine with networking disconnected.
2. Open [Return Window](http://127.0.0.1:8000/) and choose **Demo**. Inspect regional MOLA context and the refusal of 20 m stereo elevation. Enter the synthetic Marswalk, approve the proposed route in Monitor, record departure, report a crew position and close the middle corridor. Verify the recomputed return reaches the same synthetic base and awaits approval. Compare the Jezero control, HPX128:96848, with a sparse cell such as HPX128:0. Sparse cells should show regional evidence and uncertainty while withholding unsupported local calculations.
3. Rank “ancient lakes with hydrothermal activity” in Ranked areas. Confirm that the result states which terms were evaluated and which were skipped.
4. Open the fixed-fixture regression at `/legacy/mission?view=simulation`. Confirm baseline return and science times of 40 s and 75 s, then 60 s and 95 s after closing the middle corridor. With 70 s remaining, expect an over-reserve refusal. Close both corridors and expect no route. Completed work must remain visible.
5. Open the separate hazard drill. Advance to the closure and check that the active route only changes after explicit operator approval. Verify that stale readings prevent approval. The seasonal MDAD outlook and the synthetic station model do not grant terrain or hazard qualification.
6. Record the tested commit, manifest digest, machine, results, and timing. Same-machine browser tests block external requests and cover the integration. The disconnected second-machine receipt is required for offline release acceptance.

Use these claims in the demo and slides:

- The atlas uses 196,608 HEALPix cells. Named landmarks help orient the operator. Evidence coverage varies by cell.
- Ranking is exploratory. The sensitivity sweep retained 9–10 of 20 shallow-ice results and 14 of 20 young-volcanism results in the failing cases, below the 16-of-20 threshold.
- Arcadia has regional MOLA context. The reviewed footprint lacks qualifying data for the requested 20 m stereo calculation, so tactical routing is withheld.
- The Marswalk route and hazard drill use synthetic inputs. The planner recomputes the return after a closure, and the operator approves the proposed change.

Suggested narration: “I’ll open Arcadia with Demo. We can see the regional topography from MOLA, but this footprint lacks the terrain data needed for a 20 metre calculation. In the labeled rehearsal, I’ll approve a route, close a corridor after departure and check the return to the same base before approving the change.”

The [Jezero Float32 producer/consumer check](../evidence/jezero/README.md) is an independent archive control. The [moving-storm, SEP and emergency-hold scenarios](../runtime/docs/live-hazard-map.md) are separate CLI rehearsals. Neither control qualifies tactical routing.

## Direct links

- `/` opens Planetary Explore with no cell selected.
- `/#ranking` opens Ranked Areas. Select a result to investigate its HEALPix cell.
- `/#demo/arcadia` opens the Arcadia evidence walkthrough. **Enter simulated Marswalk** loads the rehearsal with the preset base.
- `/marswalk?demo=1&walk=monitor` opens the rehearsal directly at Monitor. Refreshing opens the same stage and starts a new simulation.
- `/#monitor/rover/43/hazards` opens the dedicated hazard drill.
- `/legacy/` opens the earlier Explore and Atlas UI.
