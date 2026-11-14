# Mission frontend plan

**Scope.** `/` and `/mission` open the astronaut workflow. The crew inspects a real site and its evidence. They then switch explicitly into a labeled simulated Marswalk, where a corridor closure changes the return route and the science decision. Isath's operations UI mockups set the visual language: warm dark panels, mono labels, `OBS` / `CALC` / `SIM` provenance badges, a persistent `SIMULATION` tag and a travel / dwell / reserve timeline. The mockups' consumables, slope values, rover mode and synthetic routes drawn over real imagery are out of scope here.

## Site selection

The primary demo site is a qualified, less-documented area. It stays **unset** until Isath and Yumeth qualify it and Abhimantha approves it. `VITE_RW_SITE` selects a site from the registry in [`src/mission/site.ts`](../src/mission/site.ts).

| `VITE_RW_SITE` | State shown |
| --- | --- |
| empty (default) | Unset. Primary site awaiting qualification and approval. |
| `jezero-control` | Engineering control only, labeled as such everywhere. Not the demo site. |
| any other value | Invalid. Shown explicitly, never treated as unset or as Jezero. |

Add a primary entry to the registry only after approval.

## First screens

Screens 1–3 are implemented in `src/mission/`. Screen 4 is not started. Evidence is accepted only when its `package_id@package_version` matches the selected site's registry entry. The simulation discards superseded or mismatched plan responses and stores closures and remaining time under `return-window-mission/scenario/v1/<pack_id>@<pack_version>`.

1. **Site evidence.** Site header from config plus the evidence panel from `GET /api/v1/evidence`: product, native sampling, usable support, missing requirement, supported fallback and the `provenance_unverified` label. Show distinct states for an unset site, an invalid site, evidence not configured (503) and service unavailable.
2. **Simulation switch.** One explicit action, "Enter simulated Marswalk". From that point the `SIMULATION` tag stays visible. The real-site view and the simulation never share a map.
3. **Simulated Marswalk.** The fixture's 3×5 grid in its own SVG panel, placed with the `/site` shape, `row_col` order and pixel-centre affine. Includes checkpoint and shelter, closure toggles (`mid`, `north`), remaining-time control, return-margin card, travel / dwell / reserve timeline and the task list with `survey-done` retained. Show the recommendation, or the refusal `RETURN_OVER_RESERVE` or `NO_RETURN_ROUTE` with no recommendation.
4. **Later: closure trade-off.** A before/after comparison of direct return and the science option, following the 07a mockup pattern. Use only values from plan responses.

Acceptance for screen 3 uses the golden-path values in [EXECUTION_PLAN §3](../../reference/project/EXECUTION_PLAN.md#3-prove-the-golden-path): 40 s / 75 s / +10 s at baseline; 60 s / 95 s with direct return after the middle closure; −5 s over reserve at 70 s; and no route with both corridors closed.

## API bindings

All calls use same-origin relative paths. In development, Vite proxies `/api` and `/healthz` to the loopback planning service (`RW_PLANNING_API_ORIGIN`, default `http://127.0.0.1:8000`).

| Endpoint | Use in the UI |
| --- | --- |
| `GET /healthz` | Gate the mission view on `{"status":"ready"}`. |
| `GET /api/v1/site` | **Synthetic fixture identity only** (`rw-synthetic`, `classification: synthetic`): pack and scenario IDs, fixed inputs, closures, checkpoint and shelter cells, grid shape and affine. It does not describe the real site. |
| `POST /api/v1/plan` | Build from the `/site` identity. Vary only `closure_ids` and `remaining_s`. Use a monotonic `request_id`, drop responses that are superseded or have a mismatched pack, and clear the recommendation on any refusal or error. Persist closures and time under `pack_id@pack_version`. |
| `GET /api/v1/evidence` | Real-site evidence. A 503 with `EVIDENCE_NOT_CONFIGURED` means the operator has not started the service with an approved package and query. |

Errors use `{schema_version, request_id, error, message}`. Map them as follows: 400 means invalid request or closure, 409 means the request differs from the fixed scenario, 413/415 means a client bug and 503 means not configured.

### Where the docs and the running code differ

- The [November 12 snapshot](../../reference/project/CURRENT_STATE.md) lists the planning HTTP service as not implemented. It runs: `runtime/planning_api.py`, tested in `runtime/tests/test_planning_api.py`.
- The framework describes `/api/v1/site` as the selected real pack. The running service serves only the synthetic fixture, so the real site's identity comes from frontend config and `/api/v1/evidence`.
- Evidence is a parameterless `GET`. The client sends no query geometry. The operator configures the query when starting the service.

## Unavailable in this release

Real-site routing and tactical calculations · slope, roughness and footing · oxygen, water, food and EVA-duration modeling · rover profile · editing the checkpoint, shelter, reserve or completed tasks (the service returns 409) · Analysis and Monitor views · region ranking and suitability scores · 3D · offline release packaging · synthetic geometry drawn on real Mars geography.
