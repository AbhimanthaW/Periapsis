# Mission frontend

`/mission?region=<atlas-id>&profile=<profile>` accepts the same 56 region IDs and profiles as the Atlas. Arcadia Planitia is the default evidence demo. Jezero is the engineering control. Other regions can be investigated using their Atlas research and the sourced cell record that contains their named anchor. The anchor cell is a discovery unit and the exact query geometry is a separate contract.

| Endpoint | Use in the UI |
| --- | --- |
| `GET /api/v1/regions/{id}` | Resolve the Atlas ID, HEALPix Nside 128 anchor cell, optional regional context and exact local evidence. Unknown regions return 404. The cell contains documentation bounds, observed and usable stereo coverage, and the sampled MOLA post when available. A zero native observation count labels the grid value as interpolated. No ranking pack means no cell context. |
| `POST /api/v1/rank` | Rank the supported objective concepts across the 196,608 cells. The UI shows unsupported and unrecognized terms from the parse result. |
| `GET /api/v1/site` | Identify the synthetic scenario, fixed crew and budgets, closures and geometry on its own metre grid. |
| `POST /api/v1/plan` | Recompute that scenario using the current fixture identity, closure and remaining time. The client rejects stale or mismatched responses and withholds recommendations on a refusal. |
| `GET /api/v1/hazard-replay/{step}` | Recompute the deterministic hazard rehearsal frame with a synthetic station artifact. The preview falls back to the bundled replay and requires operator approval for route changes. |

The [reviewed site registry](../../evidence/sites.v1.json) pins the package and exact query bytes. The Python service checks both digests before resolving with the documentation engine. The browser checks the selected region, both digests, and the package ID and version before displaying the local outcome or geometry. A generic operator-configured query remains available at `GET /api/v1/evidence` for existing tools and cannot satisfy the reviewed regional contract.

For a region with no reviewed local query, the page distinguishes qualitative survey estimates, cell-level context, and missing local support. Historic dust and station models supply advisory context under their own provenance gates. The capability gate withholds tactical calculations and live hazard assessment for every current region. Moving into the synthetic planner preserves the return link to the selected region. The simulation uses its own fixed profile, geometry and state.

See the [build, launch and release acceptance steps](../../docs/offline-readiness.md).

## Cell-first workflow

The packaged app opens the cell-first workflow at `/explore`. A cell is
addressable at `/explore?cell=HPX128:<index>`. The Research Atlas and older
named entries remain available for orientation and source citations. The
same-origin `GET /api/v1/cell-at?lon=&lat=` resolves a coordinate to the
canonical cell. `GET /api/v1/cell-context/{id}` returns regional cell context
and a pinned local query when that cell has one. Cell identity does not
establish eligibility for a local calculation.

`POST /api/v2/plan` accepts the Mars cell and exact base coordinates, plus
the scenario and pack identity, sortie ID and revision. For the synthetic
mode, send the local base and current positions as row/column indices.
The service verifies the Mars point against the cell, validates each
synthetic position and preserves the base and completed work across
revisions. A duplicate of the latest accepted request returns the same
result. The service retains sortie state for the lifetime of the loopback
process. Tactical mode requires a qualified analytical pack, which is
currently unavailable. The fixed-fixture v1 contract remains available.
