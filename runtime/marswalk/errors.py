"""Stable error and status codes for the Human Marswalk pipeline."""

# Whole-plan status (aligned with runtime.mission where the meaning is the same)
OK = "OK"
NO_RETURN_ROUTE = "NO_RETURN_ROUTE"
RETURN_OVER_RESERVE = "RETURN_OVER_RESERVE"
INSUFFICIENT_TERRAIN_EVIDENCE = "INSUFFICIENT_TERRAIN_EVIDENCE"

# Per-leg status (Subsystem 09)
LEG_OK = "ok"
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
