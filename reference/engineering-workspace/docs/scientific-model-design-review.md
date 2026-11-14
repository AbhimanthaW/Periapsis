# Return Window Scientific Model Design Review

Adopt directed, constraint-first mission evaluation over a validated regional pack. Compare a bounded set of feasible plans on separate objectives, then apply the mission’s declared priorities. Use separate human and rover profiles. This design records proposed calculations and release tests. The Jezero corridor-closure walkthrough remains the original human reference case.

## Source audit

Scanned the full regional survey, including tables, regional records, source lists and cross-region comparisons. All 56 IDs are present. The document has 55 numbered region headings; Mawrth Vallis starts at the transition around line 10940 and has an explicit Region ID 47 in its record. A heading-only importer would omit it. The document is a research inventory. Its locations and ratings have not been independently validated as route inputs.

| Survey finding | Architecture consequence |
| --- | --- |
| All 56 entries mention slope, roughness, traction/slip/sinkage, dust, ice/frost, solar, communications and radiation. Many tables use qualitative, local, seasonal or undetermined classifications. | Use valid elevation-derived geometry where supported. Treat rock, sand, frost, slip and sinkage as scale- and platform-dependent evidence or unknowns. Qualitative labels stay out of per-cell time, energy and risk calculations. |
| All entries discuss MOLA and orbital imagery. Stereo/DTM mentions vary and do not establish usable co-coverage. Some cases have localized rover evidence, including Meridiani, Gale, Jezero and Gusev. | Use the pack’s native support, resolved scale, reference and coverage. Atlas layers and published imagery support context. Pin exact DTM and traverse assets before any comparative validation. |
| Polar deposits and midlatitude ice, volcanic flows and tectonic exposures, impact geology, water-altered mineralogy, fluvial deposits and stratigraphic contacts recur. | Record a mission-specific objective and required observation. Compare access to the feature, a separately validated remote viewpoint, or deferral. |
| Entries mix provinces, basins, chasmata and nested features. Ma’adim Vallis and Gusev, or the Valles Marineris system and individual chasmata, need explicit spatial relationships. Some named centers/extents and research envelopes have different meanings. | Preserve source labels and overlapping parent/child AOIs. Verify boundaries, frame and polygon semantics before spatial indexing. A center, extent or name is insufficient to construct a route pack. |
| “High” and similar words refer to different axes across tables. Regional and local assessments can appear contradictory, such as gentle basin floors alongside severe rims. Media proxy links and informal source labels appear alongside traceable citations. | Preserve scale, quoted assessment dimension, scenario, source and uncertainty. Require primary product IDs and citations for promoted inputs. Audit source-by-source claims during pack selection. No routing-ready statuses or calibrated numerical coefficients follow from these summaries. |

The mind map motivates deterministic traversal, auditable resource estimates, alternative plans, re-evaluation and science-specific priorities. Replace its generic model council and safety score with constraint results, separate margins and reasons. Historical MEDA/RAD and simulated conditions stay labeled. Exclude health-based crew ranking, medical predictions, dummy-data forecasts, autonomous ethical judgments and assumed salvage or rescue capability. A cataloged rover location provides no evidence that a vehicle is accessible or useful for contingency support.

## Model inventory and interfaces

The editor is the decision register. Each major model records source evidence, required inputs, method, alternatives, assumptions, limitations, validation, readiness and owner. Shared nodes retain their IDs across views.

| Family | Models and contract |
| --- | --- |
| Mission configuration | Versioned mission snapshot, tagged human/rover profiles and operator-authorized limits. Inputs include region/pack, start/current/return locations, objective, completed tasks, budgets, evidence and scenario revision. |
| Planetary geometry | Reuse Mars normalization, regional projection, elevation and native gradient. Distinguish planetary geodesic distance from local metric edge length and signed grade. |
| Traversability | Canonical coverage, scale and screen; derive roughness only at supported scale; distinguish known barriers, explicit exclusions and unknown support. Terrain → mobility carries geometry, source IDs, masks, scale and uncertainty. |
| Human mobility | Directional pace and crew time; operator-supplied limits and optional authorized consumables. |
| Rover mobility | Configuration-specific inclination, clearance and speed; separate traction/slip/sinkage research; electrical drive energy and auxiliary loads; explicit source, capacity, reserve and power limits. |
| Environment | Historical MEDA/RAD context, separately enabled solar geometry and shadowing, conditional generation, future communications and forecasts. |
| Resources | Outbound, dwell and return ledger with distinct units; per-segment prefix checks when capacity, power or generation is active. |
| Science | Shared region ranking, objectives, targets and tasks; current mission relevance, achievable observation method, prerequisites and evidence-supported deliverable. |
| Pathfinding | Masked directed graph, asymmetric costs, outbound and return distances, reconstruction and diverse candidate alternatives. |
| Optimization | Hard filter, objective vector, finite-set Pareto comparison and deterministic mission-priority tie-break. Bounded optional multi-stop extension. |
| Replanning | Validate updates, preserve completed work, invalidate stale candidates, recompute costs and budgets and compare fresh options with the previous plan. |
| Uncertainty | Separate measurement, spatial, resolution, model, scenario and availability limits. Sensitivity and explicit abstention. |
| Validation | Unit, dimensional and exhaustive small-graph checks; comparative rover cases and performance budget. |
| Explanation | Versioned outcome, reason codes, constraints, trade-offs, ledger, changed science and source trace; linked to the existing response and crew UI. |

## Formulations and boundaries

- **Geometry.** In the verified local metric plane, horizontal distance is `d = hypot(Δx, Δy)`, signed grade is `g = Δz/d` for `d > 0`, and along-route inclination is `atan(g)`. Reverse grade changes sign. A local slope from a valid gradient stencil uses `atan(hypot(∂z/∂x, ∂z/∂y))`. The two slope quantities answer different questions. Use the declared Mars body/frame for geodesic discovery. Carry vertical reference, original post spacing and independently supported feature scale. [USGS planetary projection guidance](https://astrogeology.usgs.gov/docs/concepts/camera-geometry-and-projections/learning-about-map-projections/) · [USGS stereo DTM study](https://www.usgs.gov/publications/evaluating-stereo-dtm-quality-jezero-crater-mars-hrsc-ctx-and-hirise-images)
- **Human.** Use the project’s illustrative `t = (d/v) × [1 + k_up max(g,0) + k_down max(-g,0)]` with positive speed, nonnegative coefficients and explicit exclusions. Crew limits and time/reserve come from the authorized profile. No Mars EVA gait, physiology or safety validation follows from the approximation. NASA’s lunar work is a precedent for mapping science actions to constraints and reprioritizing after changes. [NASA lunar optimization proof of concept](https://ntrs.nasa.gov/citations/20240000165) · [NASA EVA informatics review](https://ntrs.nasa.gov/citations/20250011652)
- **Rover.** Use a declared effective speed and separate platform-specific exclusions. On accepted edges, the proposed illustration is `E_drive = [max(0, m·g_Mars·Δz + F_rr·s)]/η` with rolling resistance force in N, segment length in m and `0 < η ≤ 1`. Electrical energy adds auxiliary `P_aux·t`; stationary load uses its own dwell and power. This is a simplified steady-motion work balance, with no downhill regeneration credit, acceleration, slip prediction or validated braking/thermal model. If resistance, efficiency or speed is unsupported, require an explicit scenario or abstain from required energy feasibility. Check W and J separately. [JPL terrain-adaptive navigation](https://ntrs.nasa.gov/citations/20070034772) · [Curiosity traction control](https://ntrs.nasa.gov/citations/20210007638)
- **Energy and time.** Maintain separate ledgers in seconds, joules or a declared consumable unit. With generation enabled, check state at each leg/dwell boundary and within time steps where power or reserve can bind. Cap credited generation at modeled charge/storage limits, track spilled energy and enforce instantaneous power. A generation credit never becomes a negative shortest-path weight. Use pinned local illumination kernels and terrain where supported. Solar incidence alone provides no electrical generation. [JPL SPICE illumination](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/IDL/icy/cspice_illumf.html)
- **Science.** Link objective → required observation → eligible method and approach → expected artifact. Score relevance only within the mission’s declared rubric. Keep evidence quality, intrinsic interest and operational reach distinct. Region ranking is a shared screening model. Its output never enters edge weights. [NASA Science Traceability Matrix](https://hesto.smce.nasa.gov/focused-topics/)

## Optimization and replanning

1. Form one immutable snapshot of pack/config, authorized limits, current and return locations, completed tasks and scenario revision. Reject invalid IDs and unsupported required inputs. Apply validity and barrier masks before evaluating directed edges. No diagonal corner cuts.
2. Use Dijkstra on nonnegative scalar weights for baseline legs. Search the transpose from the return site to find directed return costs. A* is an optional point-to-point accelerator with a proved lower bound such as local distance divided by a validated upper speed. Generate bounded loopless alternatives, compare time and modeled energy scalar searches where both are supported, deduplicate by ordered edges, and check overlap/diversity. Pin direct return. Bounded candidate search can miss an admissible or nondominated path. [SciPy directed shortest paths](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.dijkstra.html) · [SciPy Yen](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.yen.html)
3. Form direct return and compatible outbound/task/return combinations. Evaluate availability, evidence, path, task prerequisites, budgets and reserve, before objectives. Apply the original Return Window direct-return gate. If the return gate fails, withhold science recommendations. Distinguish unsupported evidence, graph disconnection, over-budget candidates and a bounded search with no feasible candidate.
4. Minimize time/energy/terrain exposure where applicable and maximize objective fulfillment/margin. Dominance requires no worse on every comparable objective and strictly better on at least one. Compare under the same snapshot, units and evidence policy. Exclude unsupported required metrics; show optional unavailable fields as null. Lexicographic priorities and stable IDs choose an explainable option from the evaluated frontier. Optional weights require explicit normalization, domains and sensitivity tests. Constraints remain non-compensatory. P1 two-stop enumeration uses directed leg caches and explicit prerequisites. More general time windows, energy dynamics or resource-constrained paths need resource labels, state expansion or a separate optimizer and benchmark. [Irnich and Desaulniers, resource-constrained shortest paths](https://www2.imm.dtu.dk/courses/02735/rcsppchapter.pdf)
5. On closure, position, resource, evidence or priority update, reject stale revisions, preserve completed tasks and revalidate all affected alternatives. Apply closure to a request-scoped graph and recompute with the current state. Cached alternatives are only candidates until rechecked. A fixed graph with frequent sparse updates may justify D* Lite after profiling. Its use would not replace budget checks or justify travel through unknown terrain. [Koenig and Likhachev, D* Lite](https://publications.ri.cmu.edu/d-lite)

## Evidence and validation decisions

- **Adopted in the design.** Pack-bound geometry, distinct profiles, deterministic directed routing, bounded alternatives, ledgers, feasibility-first Pareto comparison and traceable replanning. Validate flat, reversed, zero-length, nodata, seam and disconnected cases. Exhaustively enumerate small fixtures to verify dominance, ties, completed-task retention and hard exclusions. Benchmark graph size, candidates and update latency before committing a target.
- **Data dependent.** Footing and traction, resolved roughness, weather, radiation and communications. Local archive records can support historical context. A forecast needs a validated product, domain and horizon. Dose requires duration, spectrum, shielding/transport and exposure geometry. Communications needs a relay trajectory, terrain horizon, antenna geometry and link budget. [PDS MEDA](https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/retrieving_mars2020.html) · [PDS Curiosity instruments and RAD](https://pds-geosciences.wustl.edu/missions/msl/)
- **Comparative tests.** Select exact source-backed route segments and labels. Opportunity at Meridiani and Spirit in Gusev are candidate weak-soil cases. Gale and Jezero provide localized mission observations and terrain/pose checks. Evaluate along observed segments with matched platform, time and evidence, including failure cases. These traces establish neither globally optimal routes nor human traversability. [NASA Opportunity](https://science.nasa.gov/mission/mer-opportunity/) · [NASA Spirit](https://science.nasa.gov/mission/mer-spirit/) · [PDS MSL archives](https://pds-geosciences.wustl.edu/missions/msl/) · [PDS Mars 2020 PLACES](https://pds.nasa.gov/ds-view/pds/viewBundle.jsp?identifier=urn:nasa:pds:mars2020_rover_places)
- **Deferred or rejected.** SPOC supports investigating image-patch terrain classification. Before activation, define target classes and sample/label counts, verify label quality, pin sensor/domain, split by site and traverse to avoid leakage, benchmark against source-backed rules, and require unknown-class abstention and a deterministic fallback. Hazard/material labels do not supply mobility coefficients. The 56 qualitative entries are not labels for this purpose. Exclude generic AI decision-making, learned moral rules, medical ranking and unsupported weather or safety forecasts. [NASA/JPL SPOC](https://ntrs.nasa.gov/citations/20200000183)

P0 is the bounded next-action decision with both profile contracts and an illustrative rover energy ledger that activates only with declared inputs. P1 adds multi-stop planning, richer sensitivity, illumination and stronger alternative search. P2 contains domain-dependent environment and terrain mechanics or classification. Before implementation, agree on source windows, profile constants, authorized reserves, stage-wise availability, candidate cap/diversity and mission priorities. Workstream A owns physics, mobility and routing. Workstream B owns science, optimization and decision intelligence. Both own the mission, terrain, resource, constraint and outcome contracts.

## Region index
Source locations in the supplied regional survey. Entry 47 starts in a transition paragraph.

| ID | Entry | Source line |
| --- | --- | ---: |
| 01 | Planum Boreum | 1 |
| 02 | Vastitas Borealis | 117 |
| 03 | Arcadia Planitia | 235 |
| 04 | Amazonis Planitia | 378 |
| 05 | Tharsis Montes | 542 |
| 06 | Olympus Mons | 725 |
| 07 | Elysium Planitia | 943 |
| 08 | Utopia Planitia | 1146 |
| 09 | Acidalia Planitia | 1358 |
| 10 | Chryse Planitia | 1569 |
| 11 | Arabia Terra | 1766 |
| 12 | Meridiani Planum | 1972 |
| 13 | Syrtis Major Planum | 2183 |
| 14 | Isidis Planitia | 2399 |
| 15 | Hellas Planitia | 2636 |
| 16 | Noachis Terra | 2865 |
| 17 | Terra Sabaea | 3097 |
| 18 | Tyrrhena Terra | 3301 |
| 19 | Hesperia Planum | 3510 |
| 20 | Terra Cimmeria | 3725 |
| 21 | Promethei Terra | 3935 |
| 22 | Planum Australe | 4148 |
| 23 | Aonia Terra | 4351 |
| 24 | Argyre Planitia | 4572 |
| 25 | Solis Planum | 4802 |
| 26 | Sinai Planum | 5025 |
| 27 | Daedalia Planum | 5241 |
| 28 | Icaria Planum | 5467 |
| 29 | Terra Sirenum | 5676 |
| 30 | Margaritifer Terra | 5916 |
| 31 | Xanthe Terra | 6168 |
| 32 | Lunae Planum | 6409 |
| 33 | Valles Marineris | 6639 |
| 34 | Tempe Terra | 6892 |
| 35 | Alba Mons | 7132 |
| 36 | Elysium Mons and the Elysium volcanic rise | 7374 |
| 37 | Medusae Fossae Formation (MFF) | 7676 |
| 38 | Cerberus Fossae | 7976 |
| 39 | Ares Vallis | 8286 |
| 40 | Mangala Valles | 8621 |
| 41 | Ma’adim Vallis | 8923 |
| 42 | Athabasca Valles | 9239 |
| 43 | Jezero Crater | 9565 |
| 44 | Gale Crater | 9884 |
| 45 | Gusev Crater | 10268 |
| 46 | Nili Fossae | 10592 |
| 47 | Mawrth Vallis | 10940 |
| 48 | Holden Crater | 11235 |
| 49 | Aram Chaos | 11577 |
| 50 | Noctis Labyrinthus | 11937 |
| 51 | Juventae Chasma | 12276 |
| 52 | Hebes Chasma | 12618 |
| 53 | Maja Valles | 12972 |
| 54 | Tiu Valles | 13335 |
| 55 | Nilosyrtis Mensae | 13705 |
| 56 | Deuteronilus Mensae | 14034 |
