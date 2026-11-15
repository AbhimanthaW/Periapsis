"""One-step Bayesian update of walking oxygen use for the simulated EVA."""
from math import exp, log, sqrt
from statistics import NormalDist

# Assumed spreads of the log rate relative to the deterministic flat-walking model.
PRIOR_SIGMA = 0.20
OBSERVATION_SIGMA = 0.15


def oxygen_belief(prepared, telemetry):
    """Use one quality-checked observation window per astronaut."""
    nominal = {item["id"]: item["rates_flat_per_h"]["oxygen"] / 3600 for item in prepared["astronauts"]}
    observation_precision = 1 / OBSERVATION_SIGMA**2
    posterior_precision = 1 / PRIOR_SIGMA**2 + observation_precision
    results = {}
    for reading in telemetry["astronauts"]:
        person = reading["id"]
        rate = reading["oxygen_used_g"] / reading["elapsed_s"] / nominal[person]
        posterior = NormalDist(log(rate) * observation_precision / posterior_precision, sqrt(1 / posterior_precision))
        results[person] = {"p50_factor": exp(posterior.mean), "p90_factor": exp(posterior.inv_cdf(0.9))}
    return results
