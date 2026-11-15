"""T5 · Trade-off card (minimal P0 form).

For every AMBER option, compare it with the best GREEN option and show what it
adds (task ids, priority classes, science value) and what it costs (the change
in each astronaut's reserve margin, per resource, and the driving resource).

No exchange rate between science and risk is computed: the two sides are
listed, never divided or summed. Trip-wires and the latest decision time need
the P1 Monte Carlo and are absent here.
"""
GREEN, AMBER = "GREEN", "AMBER"


def best_green(assessments, options):
    """Planner's own order: highest science value, then greatest time margin, then stable id."""
    green = [a for a in assessments if a["class"] == GREEN]
    if not green:
        return None

    def key(assessment):
        option = options[assessment["option_id"]]
        margin = option.plan.margin_s
        return (-option.science_value, -(margin if margin is not None else float("-inf")), option.id)

    return min(green, key=key)


def tradeoff_cards(assessments, options):
    reference = best_green(assessments, options)
    if reference is None:
        return []
    cards = []
    ref_people = {p["id"]: p for p in reference["per_astronaut"]}
    for assessment in assessments:
        if assessment["class"] != AMBER:
            continue
        costs = []
        for person in assessment["per_astronaut"]:
            before = {r["resource"]: r for r in ref_people[person["id"]]["resources"]}
            costs.append({
                "astronaut": person["id"], "driver": person["driver"],
                "resources": [{
                    "resource": r["resource"], "unit": r["unit"],
                    "margin_l1": r["margin_l1"], "margin_l1_versus": before[r["resource"]]["margin_l1"],
                    "margin_l1_change": round(r["margin_l1"] - before[r["resource"]]["margin_l1"], 6),
                    "crosses_l1": r["reserve_breached_l1"], "margin_l2": r["margin_l2"],
                } for r in person["resources"]],
            })
        science, ref_science = assessment["science"], reference["science"]
        cards.append({
            "schema": "tradeoff-card-v1", "option_id": assessment["option_id"],
            "versus": {"option_id": reference["option_id"], "class": GREEN},
            "adds": {
                "task_ids": [t for t in science["task_ids"] if t not in ref_science["task_ids"]],
                "drops_task_ids": [t for t in ref_science["task_ids"] if t not in science["task_ids"]],
                "priority_classes": science["priority_classes"],
                "science_value": science["science_value"], "science_value_versus": ref_science["science_value"],
            },
            "costs": costs,
            "note": "Margins are consumable reserve left above the L1 floor after the consumption margin "
                    "factor. Science and reserve are listed side by side; no exchange rate is computed.",
        })
    return cards
