# Navigation and local pack runtime

`python_engine/` and its six original tests are byte-preserved from the delivered Senula routing source. Its A* uses dimensionless synthetic cell costs, eight neighbours and diagonal corner checks. It does not use elevation differences or directed travel seconds. Its plotting demo requires Matplotlib in a separate environment. The original server file is empty.

`mission.py` is a separate bounded consumer for pack v1. It uses the shared structural and semantic checks, including the external site hash when supplied. It loads source-backed Jezero as an elevation preview and runs the audited closure and reserve calculations in explicitly enabled fixture simulation. The fixture's four-neighbour edge model uses a fixed base of one second per metre plus two seconds per metre of ascent. These are software control values. This runtime keeps the legacy algorithm intact and leaves physical mobility and tactical routing unsupported.

From the repository root run:

```sh
uv run --project documentation --locked python -m pytest runtime/tests contracts/tests -q
uv run --project documentation --locked python -m runtime.mission inspect /path/to/preview-pack
uv run --project documentation --locked python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid
```

Add `--site-sha256` with an independently recorded digest when validating a released pack. Exit 2 reports a refused pack or request as structured JSON on stderr. A valid simulation that cannot return reports its decision state in JSON on stdout.

## Local planning HTTP foundation

From the repository root, provision the locked environment once with
`uv sync --project documentation --locked --python 3.12`, then start:

```sh
uv run --project documentation --locked --offline python -m runtime.planning_api
```

The service listens on `127.0.0.1:8000`. It validates the committed simulation
pack and resolves an evidence query at startup when explicitly configured. It requires no web
build or downloaded raster. The system architecture's loader, request
validation, response serialization and freshness boundaries apply here. Its
richer mission option fields describe future solver and UI integration.

| Endpoint | Contract |
| --- | --- |
| `GET /healthz` | HTTP 200 with `{"status":"ready"}` after startup validation. |
| `GET /api/v1/site` | Synthetic pack and scenario IDs, fixed inputs, initial remaining time, predefined closure cells, checkpoint and shelter cells, and grid shape and affine. |
| `POST /api/v1/plan` | Accepts a strict v1 JSON request. Returns the existing simulation output plus request ID, schema version and route index order. |
| `GET /api/v1/evidence` | Separate source-backed result from the documentation resolver, with provenance and supported fallbacks. Returns HTTP 503 with `EVIDENCE_NOT_CONFIGURED` until a package and query are configured. |

```sh
curl -sS http://127.0.0.1:8000/api/v1/site
curl -sS http://127.0.0.1:8000/api/v1/plan -H 'Content-Type: application/json' -d '{
  "schema_version": 1,
  "request_id": "closure-1",
  "pack_id": "rw-synthetic",
  "pack_version": "1.0.0",
  "scenario_id": "synthetic-closure-v1",
  "checkpoint_id": "crew",
  "shelter_id": "home",
  "closure_ids": ["mid"],
  "completed_task_ids": ["survey-done"],
  "remaining_s": 100,
  "reserve_s": 15
}'
curl -sS http://127.0.0.1:8000/api/v1/evidence
```

Only remaining time and predefined closures vary in the fixture. Time fields
are integer seconds. Pack version, checkpoint, shelter, completed tasks and
reserve must match site metadata. The result carries ordered `[row, col]` cell
pairs in `direct_return.cells` and the reverse-direction control. The affine
maps the center of cell `[r,c]` from `[c+0.5,r+0.5]` to local metres. Keep
fixture geometry off real Mars geography.

A valid scenario produces HTTP 200, including `NO_RETURN_ROUTE` and
`RETURN_OVER_RESERVE`. Both have a null recommendation. An over-reserve result
may still contain a computed return path for inspection. Malformed input or
unknown closures return 400. A mismatch with fixed scenario state returns
409. Errors use `{schema_version,request_id,error,message}`, with a null
request ID when unavailable. The eventual client must discard superseded
request IDs, clear stale recommendations and key session state by pack version.

### Integration handoffs

- **Senula:** Use the four HTTP replay outcomes in
  [test_planning_api.py](tests/test_planning_api.py) as regression controls.
  Keep the routing computation behind the adapter. Review any changes to
  route geometry, units, feasibility or refusal semantics before wiring a
  new solver. The fixture's travel times are test values.
- **Yumeth:** For a real site, hand over a schema-valid evidence package,
  capability query, source manifest, local display assets and checksums.
  Start with `--evidence-package PATH --evidence-query PATH` to test the
  approved pair through the same resolver. The response identifies this as
  operator-configured evidence. The primary demo targets a less-documented
  site and remains unqualified. Jezero is used as an explicit test control.
  Site qualification remains a scientific review. Changes to routing pack capabilities require producer/consumer
  review under [mission pack v1](../contracts/README.md).
- **Isath:** Use `site`, `plan` and `evidence` responses as inputs to the UI
  design. The service is ready for local contract checks. Same-origin web
  wiring, rendering, browser replay and second-machine offline rehearsal
  remain release work.

Run the headless acceptance checks with
`uv run --project documentation --locked --offline python -m pytest runtime/tests/test_planning_api.py -q`.
