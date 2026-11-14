# Plan: objective ranking over 196,608 documented cells

**Periapsis · Workstream B · 14 November 2026, Colombo**

**Scope change.** The 56-region registry is retired. The ranked units are the 196,608 HEALPix Nside-128 cells (`HPX128:<n>`). Each cell has a metadata record with roughly the same amount of content as a former region record, or a marker that it has none. The model in the [design](README.md) carries over: concept lexicon, rule-based parser, saturated concept scoring, evidence tiers and separate criteria. What changes is the build, storage, query path and presentation, because the corpus is about 3,500 times larger.

## Size estimate

| Quantity | 56 regions (measured) | 196,608 cells (estimate) |
| --- | --- | --- |
| Text | ~49,800 words | ~170 M words, ~1 GB raw |
| Index build, one core, pure Python | 0.25 s | ~15 min. Parallel by cell range: a few minutes |
| Scored postings (doc × concept, after hierarchy expansion) | — | ~8–12 M at ~50 concepts per cell |
| Stored scores (`uint32` cell + `uint8` score, delta-coded) | — | ~15–40 MB in total, split per concept |
| Query (3–5 concepts + top-k) | 10 ms | ~1 ms in NumPy (synthetic benchmark already run) |

Raw text never ships to the browser. Only precomputed per-concept scores and the evidence quotes for displayed results do.

## Plan

### Step 0 · Profile the cell records (half a day, Abhimantha + Isath)
1. Freeze the record schema and version. Count field keys across all cells. Build the field-alias → role table from keys covering 99 % of the content. List the unmapped remainder explicitly.
2. Classify every cell as **documented**, **sparse** (below a minimum content threshold) or **no metadata**. Cells without metadata are *not evaluated*. They are never scored as zero, and they appear as a gap layer.
3. Audit a stratified random sample of about 200 cells (latitude band × content size) for sentence roles, duplicated boilerplate and source quality. Record the error rates.

### Step 1 · Lexicon from the corpus (1 day, Isath owns)
1. Run deterministic term mining: document frequency of unigrams, bigrams and trigrams in science-role fields across 196 k cells. Output a ranked candidate list.
2. Isath accepts each candidate, maps it to a concept and marks it generic or stop. Nothing enters the lexicon automatically. Target: 80–150 concepts, up from 48.
3. Swap the region-name cross-reference list for **gazetteer feature names**. Evidence such as "near Jezero delta" in a neighbouring cell becomes *via Jezero* and cannot make that cell a direct match.
4. Fold in stop phrases for citation venues and any boilerplate found in Step 0.

### Step 2 · Offline index build (1 day, Python, Yumeth reviews inputs)
1. Annotate each cell once (roles, negation, hedging, via), sharded by nested-index range across processes. Merge in cell-ID order so output is byte-identical between runs.
2. Compute `df` and `idf` over the documented cells.
3. For every concept *q* (with hierarchy expansion), precompute `idf(q) · S_q(cell)`. Quantise it to `uint8` with a stored scale. Write one posting file per concept, holding sorted cell IDs (delta-varint) and scores, plus a **direct-evidence bitset** per concept for tiers.
4. Write an evidence sidecar: for each `(cell, concept)`, the best quote span. Store it chunked by nested range and load it only for displayed results.
5. Write a manifest with the schema version, lexicon SHA, source digests, idf table and per-file SHA-256. Rebuild whenever the lexicon or metadata changes. Each rebuild is a new ranking revision.

### Step 3 · Query path (1 day, Senula + Abhimantha)
1. Parse the objective in TypeScript in the browser. The parser is small and has fixed rules. Check the port against golden fixtures from the Python reference.
2. Lazily load only the posting files for the parsed concepts. A typical query touches 2–5 small files.
3. Score by summing quantised posting arrays. Compute the tier from the bitsets: all concepts direct, some, or thematic only. Order by tier, score, then cell ID, and take top-k with a partial sort.
4. Apply filters as masks before ranking. Polar is now exact per cell, from the centroid latitude, with no AOI needed. Exclude volcanic uses the primary-theme concept. Method gates use concept bitsets.

### Step 4 · Present areas, not 196 k rows (1 day, Senula)
Adjacent cells often share sources, so raw results come in near-duplicate clusters.
1. **Group** top cells into connected areas with HEALPix neighbours. Show each area once, with its best cell, cell count and best quote.
2. **Map view:** aggregate the score to Nside 64/32/16 by max. Nested order makes this a contiguous reshape. This becomes the globe heat layer in the Explore page.
3. **Separate columns** as before: science interest conditional on the objective, Records from `marsdoc` cell summaries (with bounds, *Unclassified* when the bounds span tiers), traversal per profile, and local imagery. Columns are never summed.
4. **Less-documented site query:** a Direct match with a Records tier of Low or Very Low, grouped into areas. This feeds the open P0 demo-site decision.

### Step 5 · Validation (ongoing, Isath)
1. Gold set: about 25 objectives × judged cells or areas (graded 0–2). Track nDCG@10 per lexicon revision.
2. Re-run the determinism and ±20 % sensitivity checks at full scale.
3. Check that excluded cells, no-metadata cells and abstention each produce the right message.
4. Keep the six existing benchmark objectives as regression tests, re-expressed over cells.

## What carries over unchanged
Parser rules, role weights, relation weights, saturation, tiers, conditional science, method gates and the never-summed criteria. The prototype code is reused, with the region loader swapped for a cell-record loader.

## Decisions needed now
1. The record schema and its storage location. Is it one file per cell, a JSONL shard, or a database?
2. Where the query runs: browser with lazy per-concept files (recommended, works offline) or the local Python service.
3. The minimum content threshold for *sparse*.
4. Whether area grouping uses 4- or 8-neighbour connectivity, and the top-k per query.
