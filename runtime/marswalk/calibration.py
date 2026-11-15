"""Fit pace or uniform drive slip, then score independent traverse groups."""
from argparse import ArgumentParser
from dataclasses import replace
import json
from math import hypot, isfinite
from pathlib import Path
from statistics import mean, median

import numpy as np

from runtime.humancost import load_crew, load_policy
from runtime.humancost.calculator import _use

from .errors import MarswalkError
from .mobility import ToblerScaled
from .profiles import load_profile, profile_to_dict
from .rover import drive_cost


def number(row, key, *, positive=False):
    value = row[key]
    if type(value) not in (int, float) or not isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{key} needs a finite {'positive ' if positive else ''}measurement")
    return float(value)


def metrics(predicted, observed):
    errors = [p - o for p, o in zip(predicted, observed, strict=True)]
    return {"n": len(errors), "mean_error": mean(errors), "mean_absolute_error": mean(map(abs, errors))}


def validate_traverses(data, *, crew=None, policy=None):
    """Rows represent individual approximately uniform grades, grouped by traverse."""
    if data.get("classification") not in {"simulated", "analog", "measured"} or not data.get("source"):
        raise ValueError("traverses need a source and classification")
    profile = load_profile(data["profile"])
    fit, held = [], []
    groups = {}
    for row in data["segments"]:
        part, group = row["split"], row["group"]
        if part not in {"fit", "holdout"} or not isinstance(group, str) or not group:
            raise ValueError("each segment needs a traverse group and fit or holdout split")
        if groups.setdefault(group, part) != part:
            raise ValueError(f"group {group!r} overlaps fit and holdout")
        item = (row, number(row, "horizontal_m", positive=True), number(row, "dz_m"),
                number(row, "elapsed_s", positive=True))
        (fit if part == "fit" else held).append(item)
    if not fit or not held:
        raise ValueError("both fit and holdout segments are required")

    if profile.platform == "human":
        if profile.pace_model != "tobler_scaled" or profile.pace_scenario != "nominal":
            raise ValueError("fit a nominal Tobler profile")
        pace = median(ToblerScaled(v_flat_mps=1).seconds(length, dz) / elapsed for _, length, dz, elapsed in fit)
        fitted = replace(profile, v_flat_mps=float(pace))
        times = [float(ToblerScaled(fitted.v_flat_mps).seconds(length, dz)) for _, length, dz, _ in held]
        result = {"time_s": metrics(times, [elapsed for _, _, _, elapsed in held])}
        if crew is not None:
            people = {p.id: p for p in crew.astronauts if p.id != crew.reference_id}
            predicted_o2 = [_use(people[row["astronaut_id"]], policy, seconds, max(dz, 0))[0]["oxygen"]
                            for (row, _, dz, _), seconds in zip(held, times, strict=True)]
            result["oxygen_g"] = metrics(predicted_o2, [number(row, "oxygen_g", positive=True) for row, *_ in held])
    else:
        slip = [1 - hypot(length, dz) / (elapsed * number(row, "wheel_speed_mps", positive=True))
                for row, length, dz, elapsed in fit]
        if any(not -1e-9 <= fraction < 1 for fraction in slip):
            raise ValueError("rover segments must have a drive slip ratio in [0, 1)")
        fitted = replace(profile, drive_slip_fraction=max(0.0, median(slip)))
        if any(not np.isclose(number(row, "wheel_speed_mps", positive=True), fitted.nominal_speed_mps, rtol=.01)
               for row, *_ in (*fit, *held)):
            raise ValueError("uniform slip calibration needs wheel speed within 1% of the profile speed")
        costs = [drive_cost(fitted, length, dz) for _, length, dz, _ in held]
        result = {"time_s": metrics([float(time) for time, _ in costs], [row[3] for row in held]),
                  "drive_energy_j": metrics([float(energy) for _, energy in costs],
                                            [number(row, "drive_energy_j", positive=True) for row, *_ in held])}
    return {"source": data["source"], "classification": data["classification"],
            "fitted_profile": profile_to_dict(fitted), "holdout": result}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path)
    parser.add_argument("--crew", type=Path)
    parser.add_argument("--human-policy", type=Path)
    args = parser.parse_args()
    if bool(args.crew) != bool(args.human_policy):
        parser.error("supply --crew and --human-policy together for oxygen validation")
    crew = None if args.crew is None else load_crew(args.crew)
    policy = None if args.human_policy is None else load_policy(args.human_policy)
    try:
        result = validate_traverses(json.loads(args.measurements.read_text(encoding="utf-8")), crew=crew, policy=policy)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, KeyError, ValueError, MarswalkError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
