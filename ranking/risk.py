"""Regional terrain screening from sourced geologic unit classifications."""

import numpy as np


SOURCE = "https://pubs.usgs.gov/sim/3292/"
INDICATORS = (
    ("mass-wasting", "Mapped mass-wasting unit (Aa)"),
    ("polar-dunes", "Mapped polar dune unit (lApd)"),
)


class TerrainRisk:
    """Score the share of evaluated cells with either mapped terrain indicator."""

    def __init__(self, engine):
        self.evaluated = engine._coverage(engine.ids["mass-wasting"])
        self.indicators = np.stack([
            engine.real_support[engine.ids[concept]] >= 128
            for concept, _ in INDICATORS
        ])
        self.flagged = self.evaluated & self.indicators.any(axis=0)

    def assess(self, cells):
        evaluated = self.evaluated[cells]
        count = int(evaluated.sum())
        flagged = int(self.flagged[cells].sum())
        claims = []
        for (_, label), indicator in zip(INDICATORS, self.indicators):
            hits = cells[evaluated & indicator[cells]]
            if hits.size:
                claims.append({
                    "label": label,
                    "cells": int(hits.size),
                    "example_cell": f"HPX128:{hits[0]}",
                    "source": "USGS SIM 3292",
                    "source_url": SOURCE,
                })
        return {
            "score": round(100 * flagged / count, 1) if count else None,
            "flagged_cells": flagged,
            "evaluated_cells": count,
            "total_cells": int(cells.size),
            "claims": claims,
        }
