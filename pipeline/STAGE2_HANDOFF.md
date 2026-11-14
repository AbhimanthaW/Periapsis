# Stage 2 handoff checklist

**Next milestone** · Produce one offline Jezero preview fixture that the actual mission loader accepts while enforcing the preview's capability limits. The Stage 1 source record schema is independent of both the site pack and the documentation-engine evidence schema.

## Requirements already in the architecture

- [ ] **Regional job.** Pin stable region and pack IDs, a versioned AOI with CRS, required capability, source product IDs and versions, lineage, processing configuration and objective. The Gazetteer supplies discovery anchors. Select an explicit AOI within usable support. Treat optical and terrain products separately.
- [ ] **Native terrain.** Pin the selected DTM, authoritative horizontal and vertical references, native posting and evidence of effective scale. Record actual usable support, nodata, quality and alignment. A 20 m CTX sample is an elevation-preview input. Tactical eligibility requires independent terrain evidence for the selected objective.
- [ ] **Analytical grid.** Where routing is supported, produce `terrain.npz` with Float32 `z_m`, matching Boolean validity and screening masks, and optional slope on the declared local metric grid. Positions are `[easting,northing]` in metres and indices are `[row,col]`. Record grid shape, full affine, orientation, centers, bounds and native and output spacing. Read a buffered native window, apply vertical units/scaling, require complete stencil support, and compute native-supported gradient before coarsening. Keep the slope screen and directed edge grade separate. Omit analytical terrain from display-only packs and state the reason.
- [ ] **Site manifest.** `site.json` declares schema version, region and pack/version, processing date/config, native and local CRS and vertical reference, grid geometry, capabilities, gates, layer availability, coverage, source versions, checksums, attribution and omissions. Display layers carry exact bounds and credits. Keep baseline masks immutable and closure exclusions request-scoped.
- [ ] **Documentation engine evidence.** Use the existing v1 evidence-package and query schemas. Reuse stable source IDs/versions, split optical and terrain product identities, retain native references and canonical transform provenance. Separate observation and usable-support shapes, split product records when variable masks differ, and assert inventory or geometry closure only with evidence. Pin the sidecar hash in the pack manifest. Use the engine resolver for the requested variable, native spacing, effective scale and support. Its scores describe documentation availability.
- [ ] **Stations and tasks, if enabled.** `stations.json` carries stable IDs, objective, target, reviewed approach node, positional certainty, evidence, dwell minutes, priority, expected artifact and limitations. Convert minutes to seconds at the runtime boundary. An observed feature and a proposed approach are separate entities. Omit invalid or unsupported tasks.
- [ ] **Gates and offline runtime.** Record applicable G1–G6 evidence (integrity, coordinates, coverage, terrain support, alignment and observation provenance), G7 capability readiness, G8 schema, G9 package hashes and G10 real-loader compatibility. Publish only validated capabilities. Exercise a bad affine, inverted mask, missing artifact and preview-as-tactical rejection. Test a mission replay with a predefined simulated closure, separate directed outbound/return calculations, completed-task retention, reserve and the hard direct-return gate before additional science.

## Freeze with the real consumer before expanding the producer

| Agreement needed | Acceptance evidence |
|---|---|
| Mission-runtime repository/version and owner | A real loader consumes the positive fixture and rejects the negative fixtures offline. No consumer implementation was available in the supplied workspace. |
| Exact manifest and terrain serialization | Freeze mask keys and polarity, schema types, affine coefficient order and tolerance, invalid payload semantics, bounds conventions and evidence-sidecar path/hash field names. The blueprint defines their meanings. These exact wire details still need producer/consumer agreement. |
| AOI and capability | Approve a source-backed Jezero window, intended preview or tactical capability, use-specific native/effective scale and vertical datum. Agree on stencil, aggregation, slope/aspect convention, screening assumptions, and alignment controls before a tactical claim. |
| API and session behavior | Blueprint names `GET /api/v1/site`, `GET /healthz`, and `POST /api/v1/plan`. The proposed plan request carries `pack_id`, `request_id`, `checkpoint_id`, `shelter_id`, `completed_task_ids`, `remaining_s`, `reserve_s`, `scenario_id`, `closure_ids`. Confirm the actual wire format, response/failure behavior, profile parameters and authorized reserves in the implementation. |
| Science | Science and geospatial owners agree evidence, verified approach node and dwell for the one selected task, or leave tasks disabled. |

This checklist describes the handoff at the time of delivery. See the [offline readiness report](../docs/offline-readiness.md) for the current preview and simulation status.

Monorepo references:

- [Pipeline and gate definitions](../reference/engineering-workspace/src/pipeline-data.ts)
- [Mission pack and API blueprint](../reference/engineering-workspace/src/initial.ts)
- [Evidence sidecar contract](../documentation/CONTRACT.md)
- [Jezero evidence fixture validation and limits](../documentation/VALIDATION.md)
