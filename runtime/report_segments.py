"""Read the selected candidates' edge costs and the actual rover battery ledger."""

from dataclasses import asdict
from math import hypot


def plan_segments(plan):
    graph = plan.router.graph
    rows = []
    for candidate in plan.plans:
        ledger = candidate.energy_ledger
        energy = {} if ledger is None else {phase.name: (phase, row)
                                           for phase, row in zip(ledger.energy_phases, ledger.rows)}
        dwell = dict(candidate.dwell)
        for leg_name, leg in candidate.legs:
            for index, (edge, start, end) in enumerate(zip(leg.edge_ids, leg.cells, leg.cells[1:]), start=1):
                length, rise = float(graph.length_m[edge]), float(graph.dz_m[edge])
                phase_name = f"{leg_name}:edge:{index}"
                rows.append({
                    "option_id": candidate.id, "phase": phase_name, "kind": "travel",
                    "start_cell": start, "end_cell": end,
                    "horizontal_m": length, "surface_m": hypot(length, rise), "rise_m": rise,
                    "duration_s": float(graph.times.seconds[edge]),
                    "gross_energy_j": None if graph.times.energy_j is None else float(graph.times.energy_j[edge]),
                    **_battery_fields(energy.get(phase_name)),
                })
            if leg_name in ("outbound", "transfer") and candidate.task_ids:
                task = candidate.task_ids[0 if leg_name == "outbound" else 1]
                phase_name = f"dwell:{task}"
                rows.append({
                    "option_id": candidate.id, "phase": phase_name, "kind": "dwell",
                    "start_cell": leg.goal, "end_cell": leg.goal, "horizontal_m": 0.0, "surface_m": 0.0,
                    "rise_m": 0.0, "duration_s": dwell[task],
                    "gross_energy_j": energy[phase_name][0].consumption_j if phase_name in energy else None,
                    **_battery_fields(energy.get(phase_name)),
                })
    return rows


def _battery_fields(pair):
    phase, row = pair if pair is not None else (None, None)
    return {
        "battery_phase": None if phase is None else asdict(phase),
        "mean_discharge_w": None if phase is None or not phase.duration_s or phase.consumption_j is None
        else phase.consumption_j / phase.duration_s,
        "remaining_j_after_supply": None if row is None else row.remaining_s,
        "power_and_reserve_passed": None if row is None else row.prefix_ok,
    }
