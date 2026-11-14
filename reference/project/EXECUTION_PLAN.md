# Return Window execution plan

**Periapsis · 12–15 November 2026 · Colombo local time**

Build one demo that makes the evidence affect a crew decision. The release target is a **real, less-documented site with a live evidence-based decision** followed by a **clearly labeled offline mission simulation** that shows what a closure does to the return route and science task. Real tactical routing requires separate scientific and software qualification. Protect the last work block for validation, recording, rehearsal and submission.

[Project framework](PROJECT_FRAMEWORK.md) · [12 November implementation snapshot](CURRENT_STATE.md)

## Competition and eligibility

The Athlone organizer's mirror says the challenge resources are scheduled for Friday, November 13. The official global event page lists submission from **November 14 at 09:00 through November 15 at 23:59 local time**. Confirm Colombo's local pitch, cutoff and artifact format directly. Submit against the earlier applicable deadline. The canonical challenge tabs and Colombo page were unavailable during this audit. [Challenge mirror](https://hackathlone.com/challenges/interplanetary-survival-guide-martian-map) · [Global event](https://www.spaceappschallenge.org/2026/)

Abhimantha reports that the Colombo Local Lead explicitly permitted advance development. Use the foundation work authorized locally. The Global Organizing Team separately says advance project work can affect eligibility, and requires at least one NASA source listed for the selected challenge for Global Awards. On November 13, capture the local instruction and request written clarification of its scope for a Global Awards submission, with the current baseline and pre-event work disclosed. Record the answer alongside the release. Until confirmed, treat Global Awards eligibility as open. Map one listed NASA resource to an actual decision or data layer and cite all reused data, code, images and tools. [Global Organizing Team guidance](https://github.com/nasa/spaceapps/discussions/1827) · [2026 participant terms](https://www.spaceappschallenge.org/legal/)

## Owners and handoffs

Yumeth owns producers and Senula reviews the consumer. Isath owns evidence and scientific review. Abhimantha owns the integration decision. The coding assignments below follow the latest Git Workflow plan, with the science and data work updated for the less-documented site. They are audit recommendations where the linked chats show no teammate acceptance.

| Owner | Start from and completed work | Next output and acceptance |
| --- | --- | --- |
| **Abhimantha · integration and local API** | The merged baseline, shared validator, bounded Python runtime and documentation resolver. | Freeze one versioned HTTP contract with Senula and publish valid and refused examples from the actual fixture. Implement service endpoints and a single local launch path. Accept pack and evidence handoffs, confirm event eligibility and own submission. Accept when the real evidence decision and all four simulation states run on the release bundle. |
| **Senula · mission UI and runtime review** | Existing Vite/React/OpenLayers app, preserved routing contribution and merged fixture runtime. | Implement `/mission`, render exact route geometry, closure and reserve controls, task state, evidence and refusal reasons. Review runtime/consumer behavior and pack compatibility with Yumeth. Accept when the UI matches fixture outputs, retains completed work on replan/reload and discards stale results. |
| **Yumeth · source intake and producer** | Corrected MOLA v0.1.1, checked Jezero elevation assets, mission-pack/evidence contracts. | Produce one selected AOI's pinned source manifest, schema-valid evidence sidecar and checked local display assets. Include CRS, vertical reference, spacing, lineage, masks and scope. Hand the exact directory, release hashes and rebuild steps to Abhimantha and Senula. Accept when another teammate reproduces the control and checks a usable region plus an unsupported case. |
| **Isath · site, science and evidence review** | Regional survey, scientific model input and evidence schemas. | Shortlist at most two bounded AOIs, pin a real observation or geologic feature, write one science objective with a clear expected artifact and a defensible response to missing evidence. Review reference frames, coverage/scale, assumptions and labels. Accept when the chosen scenario has a reproducible allow/refuse query and an explanation of what observation would change the decision. |

Yumeth and Senula review any pack boundary change together. Isath reviews science and evidence. Abhimantha resolves architecture and integration. Use feature branches from live merged `main` and record acceptance on the relevant change. Atlas-wide enhancements, full-catalogue processing, arbitrary drawing, multiple profiles, consumables and deployment polish beyond the chosen replay are outside this event's critical path.

## Workstream schedule

| When | Priority and owner | Inputs → deliverable and acceptance | Fallback |
| --- | --- | --- | --- |
| **Nov 12 evening** | **P0 · Abhimantha + Senula** | Merged `main`, real fixture JSON and CLI output → one agreed API schema/examples, minimal service and first mission screen. Pass one baseline and one closure response using known fixture identities. | Use exact fixture outputs as frontend samples while the service is wired. Replace samples with live calls before acceptance. |
| **Nov 12 evening** | **P0 · Yumeth + Isath** | Evidence schema, Atlas and public catalogs → selected search bounds and candidate table with at most two AOIs, each with a credible science objective and candidate data. Keep Jezero reproduction available for engineering control. | Use existing catalogue tools and scope the search to one modality and region. Skip broad catalogue ingestion. |
| **Nov 13, when resources are accessible** | **P0 · Abhimantha + Isath** | Official resource list, organizer details and candidate table → exact NASA resource match, one decision that uses it, and recorded local cutoff and advance-work guidance. Verify local deliverables from the current organizer or Project tab. | If a listed resource misses the AOI, use the other bounded candidate or a supported role for a verified listed source. Keep eligibility open until confirmed. |
| **Nov 13, by evening** | **P0 · Isath + Yumeth** | Checked candidate product footprints and source metadata → one accepted AOI or a recorded qualification failure. Deliver `evidence-package.v1` sidecar, source and query IDs, small local layers, provenance, one supported output and one evidence refusal. | Use the narrowest real evidence decision available, such as a contextual view plus a justified refusal and a request for reconnaissance. Scope every absence claim to the searched inventory. |
| **Nov 13, by evening** | **P0 · Abhimantha + Senula** | API contract, fixture and built web app → browser fixture replay passes all four controls and stale-response test. | Keep predefined closure IDs and fixed checkpoint, shelter and reserve. Drop general route editing and variable task catalogues. |
| **Nov 14, first half of the build window** | **P0 · all four** | Qualified AOI assets, approved evidence query and synthetic browser replay → one local launch with the real decision and explicit simulation transition. Verify source layer support and refusal, closure, margin, completed task and no stale route. | If a new AOI misses the gate, keep the demo capability narrow and label the geographical and data limitations. Use Jezero only as a visibly labeled engineering control and the fixture for mission behavior. Record that the primary-site goal remains unmet. |
| **Nov 14, second half** | **P0 · Abhimantha + Senula**, Isath/Yumeth review | Exact runnable build, local assets and pre-provisioned dependencies → second-machine disconnected replay, recorded source and release checksums, signed capability/limitations review and packaged fallback. Freeze features after this pass. | Use the verified laptop for the live demo and record a same-build walkthrough. Keep offline and second-machine qualification claims scoped to the checks that actually passed. |
| **Nov 15, first work block before the local cutoff** | **P0 · all four** | Frozen build → rehearse two complete runs, capture a short walkthrough and screenshot backup, finalize project text, data citations and known limits. Abhimantha verifies links in an unauthenticated browser and submits before the earlier applicable cutoff. | If live execution fails at judging, use the same-build recording and show the evidence receipt and fixture outputs. Verify the submission status and save confirmation. |

### Critical path

The fixture API/UI can proceed while Yumeth and Isath qualify the real site. Both paths converge at the same local launch on November 14. Lock the supported decision by November 13 evening. A generic analytical producer or physical mobility model must never hold the event baseline hostage. Only attempt that broader path if the exact data, model, owner review and positive/negative handoff already meet the scientific gate with enough time left for offline rehearsal.

## Acceptance gates

### 1. Freeze the interface once

Use one local Python service over the existing modules and the existing web app. Keep pack directories and query templates in a server-owned registry. Run the same API schema examples on both sides of the boundary.

- `GET /healthz` indicates whether the locally configured service and packs are ready. `GET /api/v1/site` returns selected immutable pack/site version, capability, local layer references and coordinate metadata.
- `POST /api/v1/plan` uses a versioned full scenario request with request ID, pack ID/version, scenario ID, checkpoint and shelter IDs, supported time state, completed tasks and closure IDs. Use `rw-synthetic` as the fixture pack ID, `synthetic-fixture-v1` as its build ID and `synthetic-closure-v1` as its scenario ID. Existing runtime inputs accept closures and remaining time only. For fixed fields, validate equality with the scenario until the runtime explicitly supports changes. If new task completion is exposed, implement and test it in the consumer before sending mutable completed-task IDs. Existing completed work must survive replans and browser reloads either way.
- Return request and pack identity, status/reason, ordered route, declared coordinates, margin, task feasibility and recommendation. Either serialize metric pixel-center positions on the server or declare `row_col` and use the validated affine in one documented layer. Keep synthetic geometry in its own display.
- Define one evidence operation or site response in the same API review. For the chosen real AOI, load the versioned sidecar, run the existing resolver on the agreed geometry and display the actual result, supporting source and unknowns. Source-backed stand-alone evidence avoids broadening the pinned pack loader for this event.
- Gate unsupported capabilities and invalid IDs before planning. Suppress active recommendations on no path, over reserve, capability refusal, pack failure or superseded responses. Persist scenario state by pack/version and ignore late responses with a mismatched request or pack. Verify a delayed successful request cannot overwrite a later refusal.

### 2. Qualify the site and label the capabilities

Review the exact AOI, mission or instrument, product and version, native sampling, independent data type, original coordinate reference and transformed support. Record data licenses/credits, coverage semantics and hash controls. Build a **matched comparison** for one relevant evidence modality with the same query method at the selected site and a well-studied control. Allow one calculation or observation supported by the data and refuse one with a precise reason. Preserve observed footprint, usable support and inventory completeness independently. Use HEALPix summaries for planetary documentation and the local resolver for exact-site decisions. Use the named Atlas entries to find places and references. A small dataset with known coverage is enough.

For real tactical calculations, independently verify native resolution and effective scale, vertical reference and reprojection, usable cells and stencil/quality exclusions, directed physical mobility assumptions, full-route support and loader behavior. Validate through a reviewed analytical producer and a supported contract/capability, then record an external G10 receipt. The existing v1 consumer's real path is limited to the pinned Jezero preview. Changing a capability string cannot expand that release.

### 3. Prove the golden path

Use a fresh browser on a second machine with internet disconnected and a pre-provisioned local runtime. Test the release package, with its pinned assets and startup instructions.

1. Open the real site and show a NASA-derived layer and the science objective. Query an exact approach or area and show a calculation refused for the right evidence reason, the evidence source, and a supported next action.
2. Switch explicitly into fixture simulation. Initial result is 40 s home, 75 s for the science option and +10 s science margin. Apply the middle closure. Expect the changed path, 60 s home, 95 s for science and a direct-return recommendation.
3. Set 70 s remaining with the middle closure. Expect `RETURN_OVER_RESERVE`, −5 s and no recommendation. Close both corridors. Expect `NO_RETURN_ROUTE`, no path and no recommendation. Verify the prior route disappears where invalid and `survey-done` remains complete. Refresh and repeat.
4. Restart from the release folder and replay without external resource fetches. Keep the captured build, its version/digests, recording and source references together. On the judge-facing artifact, show evidence-derived results and simulation labels at the point where they are used.

### 4. Verify submission

Confirm four team registrations, correct project/challenge/event and current media rules. Verify that judges can open the project, demo and required links without team credentials. Include explicit NASA/partner asset IDs, roles, citations, attribution, prior-work disclosure as applicable, runnable build or access instructions, and clear limits of the terrain and mobility claims. Keep the public artifact's access separate from the private development repository until the submission format and intended release are confirmed.
