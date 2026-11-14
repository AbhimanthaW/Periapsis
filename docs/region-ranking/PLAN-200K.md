# Plan for objective screening over 196,608 HEALPix cells

**Periapsis · Workstream B · 14 November 2026, Colombo**

Cell screening uses the lexicon and objective parser from the [region-ranking design](README.md). The HEALPix Nside-128 cells (`HPX128:<n>`) are map and screening units. The versioned candidate-region registry remains the unit for regional assessment and selection, with the 56 entries as the current research cohort.

## 1 · Establish the inputs

- Inventory structured sources with Yumeth. Pin their versions, licences, spatial resolution and coverage. Document the concepts each source can evaluate, the footprint in which that evaluation is valid and the meaning of zero support.
- Have Isath review the layer-to-concept mappings, reliability weights and hierarchy expansion. Cell text is not a prerequisite. Registry text may contribute as regional context only after the region has a reviewed AOI and the text's evidence links are available.
- Use nested HEALPix ranges for source footprints and region AOIs. Record unknown coverage explicitly, including where a source has detections but no verified observation footprint.

## 2 · Build and query the offline index

- Write sorted sparse positive-score postings and direct-evidence bits per concept. Store coverage separately for each layer and concept following the reviewed mapping. For a given concept, combine coverage across eligible layers and combine support using the maximum reliability-weighted score.
- Compute document frequency from covered cells with positive support and use the covered-cell count as the population for each concept's IDF. Mark a concept with no covered cells as unavailable.
- For each requested concept and cell, distinguish positive support, covered with zero support and not evaluated. A cell with no covered query concept is not evaluated. For partial coverage, display which concepts are unknown. Do not report a full-query score for that cell or include it in the full-coverage ranking.
- Compute evidence tiers from direct-evidence bits. Among fully evaluated cells, order by tier, score and cell ID. Load postings and coverage masks together. Apply location filters separately. Method compatibility also requires the applicable profile access or imagery evidence.
- Pin the lexicon and source digests, coverage and mapping rules, IDF, score scales and file checksums in the index manifest. Retain evidence references by cell and concept so displayed hits can be traced to their sources.

## 3 · Connect screening to regional assessment

- Group neighbouring hits for display and show the strongest hit and its evidence. Preserve coverage gaps on the map, including when reducing to coarser zoom levels.
- Intersect hit groups with versioned candidate-region AOIs. Attach linked hits as screening evidence. Send groups outside existing AOIs for review as possible new candidates.
- Keep availability, scientific value and suitability as separate assessment records. A screened hit does not select a candidate or modify route weights. Shortlist selection uses the independently reviewed objectives, regions and assessment revisions described in the [architecture](../../web/src/pipeline-data.ts).
- A Direct match in a Low or Very Low Records area can inform the demo-site decision. Validate the underlying evidence and the Records classification before advancing a candidate.

## 4 · Validate before Explore integration

- Test positive support, covered zero and absent coverage for the same concept. Include an ice query outside SWIM coverage, plus a two-concept query where only one concept is covered. Verify gap and partial-coverage states survive indexing, querying and map aggregation.
- Compare parser and ranking results against shared fixtures. Check build determinism, measure file sizes and query timing with the pinned inputs, and compare ranking sensitivity against a reviewed set of objectives and judged areas.
- Have Isath review the lexicon, evidence rules and validation set. Confirm the cell-to-region handoff with Abhimantha before integrating with Explore.
