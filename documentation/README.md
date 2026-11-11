# Planetary Documentation Engine

The Python core is verified with synthetic controls and one archive-checked Jezero CTX elevation window. It computes evidence availability and model support for Return Window. The existing atlas and site-pack boundaries are described in the [audit](AUDIT.md) and [pipeline contract](CONTRACT.md). Measured results and the acceptance checklist are in [validation](VALIDATION.md).

## Run the offline example

From this directory with Python 3.12 and uv:

```sh
uv sync --locked --python 3.12
uv run --locked pytest -q
uv run --locked marsdoc ../evidence/jezero/jezero-evidence.json --point 77.44 18.45
uv run --locked marsdoc ../evidence/jezero/jezero-evidence.json --query ../evidence/jezero/jezero-route.json
```

The point selects cell `HPX128:96848`. The verified 20 m-posted stereo terrain occupies about **48.12%** of that cell. The terrain axis spans **12.03–100**, and the science/environment axis spans **0–100**. Both are unclassified because the sample leaves the broader catalogues open. The 60 m-wide sample route corridor is fully inside the verified support. Its 2 m-posted elevation requirement is unsupported, and the explicitly requested 20 m-posted elevation fallback is eligible. Effective feature scale and tactical slope support are unset. The route is a demonstration geometry. [USGS source catalogue](https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic)

For a caller in the proposed Python runtime, install this project and reuse its immutable evidence index:

```python
from pathlib import Path
from marsdoc import CapabilityQuery, DocumentationEngine, Package

engine = DocumentationEngine(
    Package.model_validate_json(Path("../evidence/jezero/jezero-evidence.json").read_bytes())
)
cell = engine.grid.cell_at((77.44, 18.45))
summary = engine.summarize(cell.id)
request = CapabilityQuery.model_validate_json(Path("../evidence/jezero/jezero-route.json").read_bytes())
decision = engine.resolve(request)
```

## Method

- **Index.** `Grid` provides vectorized coordinate assignment, centroid and boundary lookup, stable IDs, hierarchy and exact equal-area spherical cell areas. It uses Astropy HEALPix NESTED and a 3,389,500 m sphere. Nside 128 is the default. Summary overlays require Nside ≥ 2. Angular normalization and physical measurement are separate. Pole coordinates use one canonical longitude.
- **Overlay.** In a spherical gnomonic chart, great-circle edges are straight. Shapely computes topology and intersections there. Overlay rings are inverse-projected for spherical area via PROJ. Unbuffered route segments use great-circle lengths, with clipped intervals unioned in metres along the route. Buffered queries use a conservative polygonal envelope accounting for gnomonic scale and round-buffer chord error. The benchmark and tests include seam, polar, and overlapping cases.
- **Coverage.** Union geometry within each modality. Report observed and usable coverage fractions separately. In the default policy, documentation utility is one for verified usable support and zero for known unusable or pending preprocessing, with bounds for unresolved support. An optional logarithmic native-spacing ramp changes utility while preserving the observed and usable fractions. For overlaps, integrate the maximum utility at each location by accumulating nested unions from highest to lowest utility.
- **Uncertainty.** The lower bound uses verified usable support. The upper bound allows unresolved evidence in unsearched portions and in the plausible extent of unresolved products. Verified absence requires catalogue and observation closure where queried. These are bounds under the stated evidence and method. They represent neither positional-error bars nor predictive calibration.
- **Classification.** Each axis is the normalized weighted mean of its modality intervals on a 0–100 scale. `scoring-v1.json` pins equal modality weights, 16 samples per HEALPix edge and five provisional bands. A score exactly at a cut enters the higher tier. The default tolerance moves the effective cut by at most `1e-9` points. Both interval endpoints must be in the same tier. A noncollapsed interval has no scalar score. Results carry the method version, policy version and policy digest.
- **Capability.** Resolve verified spatial support, allowed product class, variable, readiness, native spacing, effective scale and time as required by the model. Report candidate sources, support fractions, unmet requirements and independently evaluated fallbacks. There is no hazard multiplier or scientific-interest inference in the engine API.

## Boundaries and remaining integration

Footprint pieces must fit within a 25° angular cap, query polygons and routes within 35°, and buffered corridors within 2°. Split larger inputs upstream, then combine decisions under the model's declared rules. `Global` is reserved for explicit whole-sphere applicability. Acquisition tracks and in-situ point products need a separate support representation before promotion. Source edges require upstream densification when their real geometry differs from great-circle arcs. GEOS overlays are floating-point operations and very thin or near-coincident boundaries require numerical review. The HEALPix boundary approximation and its observed convergence are separate from the catalogue bounds.

Yumeth's production sidecars, a full catalogue run, and application wiring are pending. Start with the Jezero asset IDs and independently verified variable masks. Expose evidence status in the Atlas and gate model execution through the resolver plus the existing site-pack checks. Keep the provisional documentation tiers separate from the survey labels and the route graph. The underlying evidence records and computations are ready for that integration. Global performance and scientific calibration of bands or modality weights still need source-backed evaluation.

## Files delivered

| Files | Purpose |
| --- | --- |
| `AUDIT.md`, `CONTRACT.md`, `VALIDATION.md` | Architecture decisions, pipeline handshake and measured verification |
| `marsdoc/grid.py`, `spatial.py` | Mars normalization, HEALPix and bounded spherical geometry |
| `marsdoc/catalogue.py`, `engine.py` | Sparse lookup, missingness, scoring, classification and local eligibility |
| `marsdoc/contracts.py`, `schemas.py`, `scoring-v1.json`, `schemas/` | Runtime and wire contracts plus versioned policy |
| `marsdoc/__init__.py`, `__main__.py`, `pyproject.toml`, `uv.lock`, `.gitignore` | Public API, CLI and reproducible project setup |
| `examples/` | Jezero package and query, bounded archive verification, benchmark script and measured results |
| `tests/` | Unit, integration and scientific controls |
| Parent `README.md` | Link from the isolated copy of the existing architecture |
