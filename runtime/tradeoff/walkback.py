"""Apply the walking consumables model to every rover breakdown point."""
from runtime.humancost import prepare
from runtime.humancost.calculator import RESOURCES, _initial, _use
from runtime.marswalk.errors import FAIL, PASS, UNKNOWN
from runtime.marswalk.walkback import _timeline

from .classify import _current_stores
from .envelope import reserve_floors


def crew_walkback_check(crew, policy, envelope, stores, oxygen_factors, timing=None):
    prepared = prepare(crew, policy)
    floors = reserve_floors(envelope, crew, policy, prepared)
    walkers = [person for person in crew.astronauts if person.id != crew.reference_id]
    balances = ({p.id: _initial(p) for p in walkers} if stores is None else _current_stores(stores, walkers))
    factor = envelope.consumption_margin_factor
    legs = {}

    def check(plan, snapshot, rover_router, walk_router):
        for cell, elapsed_s in _timeline(plan, rover_router):
            if cell not in legs:
                legs[cell] = walk_router.leg_return(cell, snapshot.return_cell)
            leg = legs[cell]
            if not leg.ok:
                return UNKNOWN, f"walkback consumables unavailable from {list(cell)}"
            if timing is not None and not timing.clear_leg(leg, walk_router, elapsed_s):
                return FAIL, f"a storm overlaps the walkback from {list(cell)}"
            for person in walkers:
                # The prototype uses the human model's flat rate during occupied rover
                # travel and science dwell, plus directed walking cost after breakdown.
                spent, *_ = _use(person, policy, elapsed_s, 0)
                walking, energy, *_ = _use(person, policy, leg.seconds, leg.ascent_m)
                if leg.seconds and energy / leg.seconds > person.peak_metabolic_w:
                    return FAIL, f"{person.id} exceeds the walkback workload limit from {list(cell)}"
                for resource in RESOURCES:
                    multiplier = oxygen_factors.get(person.id, factor) if resource == "oxygen" else factor
                    balance = balances[person.id][resource] - multiplier * (spent[resource] + walking[resource])
                    if balance < floors[person.id]["l1"][resource] - 1e-12:
                        return FAIL, f"{person.id} would breach the {resource} reserve walking back from {list(cell)}"
        return PASS, "each breakdown point has a walkback within both astronauts' resource reserves"

    return check
