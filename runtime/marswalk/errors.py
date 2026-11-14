"""Stable error and status codes for the Human Marswalk pipeline."""

# Whole-plan status (aligned with runtime.mission where the meaning is the same)
OK = "OK"
NO_RETURN_ROUTE = "NO_RETURN_ROUTE"
RETURN_ENVIRONMENT_UNVERIFIED = "RETURN_ENVIRONMENT_UNVERIFIED"
RETURN_ENERGY_UNVERIFIED = "RETURN_ENERGY_UNVERIFIED"
RETURN_ENERGY_SEARCH_EXHAUSTED = "RETURN_ENERGY_SEARCH_EXHAUSTED"
RETURN_OVER_RESERVE = "RETURN_OVER_RESERVE"
INSUFFICIENT_TERRAIN_EVIDENCE = "INSUFFICIENT_TERRAIN_EVIDENCE"
RETURN_WALKBACK_EXCEEDED = "RETURN_WALKBACK_EXCEEDED"     # rover: the crew could not walk home from the route

# Site gate refusals (Phase 0). Raised before any terrain is routed.
NO_TERRAIN_EVIDENCE = "NO_TERRAIN_EVIDENCE"         # documentation engine: requested local DTM not eligible
TERRAIN_TOO_COARSE = "TERRAIN_TOO_COARSE"           # analytical cell larger than the routing ceiling
GRID_TOO_LARGE = "GRID_TOO_LARGE"                   # more analytical cells than the processing limit
TERRAIN_NOT_AVAILABLE = "TERRAIN_NOT_AVAILABLE"     # eligible evidence but no routable terrain payload

# Per-leg status (Subsystem 09)
LEG_OK = "ok"
LEG_SEARCH_LIMIT = "outbound_search_limit"
LEG_NO_PATH = "no_path_under_constraints"
LEG_NO_EVIDENCE = "insufficient_terrain_evidence"
LEG_ENDPOINT_EXCLUDED = "endpoint_excluded"
LEG_OUT_OF_BOUNDS = "out_of_bounds"

# Constraint outcomes (Subsystem 10)
PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"


class MarswalkError(ValueError):
    """Refused input. `code` is stable and machine-readable."""

    def __init__(self, code, detail):
        self.code = code
        super().__init__(f"{code}: {detail}")
