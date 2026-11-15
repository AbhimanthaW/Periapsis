# Human cost for walking EVAs

The MVP needs **three route measurements** to estimate the human cost of a walking EVA. Marswalk supplies them; the app does not ask the crew to enter them. Use the simulated [crew preset](../examples/crew-human-factors.json) and [policy preset](../examples/human-cost-policy.json) for suit and crew settings.

| Keep | Source | What it changes |
|---|---|---|
| Duration (`time_s`) | Leg travel time or scheduled dwell, in seconds | Longer phases use more consumables. Include the return and all stops. |
| Uphill gain (`gain_m`) | Leg `ascent_m`, in meters; zero for dwell | Adds metabolic work. Use total positive climb, even if the leg ends at its starting elevation. |
| Maximum slope (`max_slope_deg`) | Leg maximum slope, in degrees; omit for dwell | Checks the steepest part of the leg against the crew's slope limit. Supply it for walking legs; omitting it skips this check in the calculator. |

Pass phases in traversal order: outbound, any dwell or transfer, and return. Phase names and kinds identify where a check fails; they are bookkeeping fields.

## Router and app handoff

1. Use `prepare()` to get the crew's walking profile and time budget. Subtract `reserve_s` from `remaining_s` for the planning allowance. The budget comes from the limiting astronaut and consumable at a flat rate.
2. Use `evaluate()` to check complete route candidates using their actual phase times and climbs. It checks each astronaut's oxygen, cooling water, drinking water, and battery reserves, as well as slope and phase-mean metabolic power limits. Keep the four reserves as internal checks; they do not need four app controls. Enforce the time allowance and any walk-back checks in the planner.
3. Show the check result and the limiting astronaut. For a pass, show the highest share of a usable consumable budget spent (the API field `route.risk`, scaled to 0–100). For a failure, show `route.breach` with the failed check and phase. The score is a simulated budget measure, not a probability or safety clearance.

```python
from runtime.humancost import Phase, evaluate, prepare

crew = "runtime/examples/crew-human-factors.json"
policy = "runtime/examples/human-cost-policy.json"

planning = prepare(crew, policy)["routing_inputs"]
planning_allowance_s = max(0, planning["remaining_s"] - planning["reserve_s"])
summary = evaluate(crew, policy, [
    Phase("outbound", "outbound", 3600, 40, max_slope_deg=12),
    Phase("dwell", "dwell", 1800, 0),
    Phase("return", "return", 3300, 12, max_slope_deg=12),
])["route"]
```

## Leave out of the MVP interface

- **Telemetry and environmental observations:** Skip the optional `environment` and `observations` fields. For example, radiation, temperature, dust, visibility, heart rate, and suit pressure do not change human-cost estimates today. Apply weather or communication rules in their own planner checks where configured.
- **Extra measurements and diagnostics:** Distance and derived walking speed can stay in route details. Metabolic power, cooling demand, CO₂ load, and per-resource ledgers are calculator details. They need no additional inputs from the app's route form.

The calculator still accepts its existing fields. This contract describes the smaller set the app and router need for human cost.
