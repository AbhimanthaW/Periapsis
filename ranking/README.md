# Cell ranking: input gate

The ranker targets all 196,608 `HPX128:<nested_index>` cells. Before building a
support matrix, place these release assets in the ignored `data/ranking-inputs/`
directory:

- `mars-cell-map-v0.1.0`: `cells-enriched.ndjson.gz`
- `mars-cell-map-v0.2.0`: `cell-ranking.ndjson.gz`,
  `ranking-features.json.gz`, `cells-enriched-sourced.ndjson.gz`,
  `sourced-catalogue-manifest.json`

Run `python -m ranking.inputs data/ranking-inputs` from the repository root.
The verifier checks every SHA-256 before parsing, checks the sourced manifest's
baseline digest, enforces NESTED row order, and prints observed counts. It
does not generate a pack or interpret missing catalogue records as absence.

The published group totals count each cell's **first** geologic unit. Four
boundary cells have two unit records; counting both group associations gives
different totals. The input gate reports the number of two-unit cells so this
choice stays explicit.

This is phase 1 of the ranking build. The concept ledger, parser, layer
compiler, pack, query engine, and HTTP endpoints are not yet implemented.
