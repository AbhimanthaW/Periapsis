# Human cost for walking EVAs

The human-cost model tracks 12 variables. Marswalk supplies the route measurements. The calculator uses the simulated [crew preset](../examples/crew-human-factors.json) and [policy preset](../examples/human-cost-policy.json) for starting resources, reserve thresholds, and workload estimates.

| Variable | Source and use |
|---|---|
| Duration | Pass leg travel time or scheduled dwell as `time_s`. Include the return and all stops. |
| Uphill elevation gain | Pass leg `ascent_m` as `gain_m`. Use total positive climb in meters and zero for dwell. |
| Maximum slope | Pass leg `max_slope_deg` for each walking phase. The calculator checks the crew's slope limit when this value is supplied. |
| Oxygen remaining | Tracked in grams for each astronaut and checked against their oxygen reserve. |
| Cooling water remaining | Tracked in kilograms for each astronaut and checked against their suit cooling reserve. |
| Drinking water remaining | Tracked in liters for each astronaut and checked against their drinking water reserve. |
| Battery charge remaining | Tracked in watt-hours for each astronaut and checked against their suit battery reserve. |
| Heart rate | Optional simulated `heart_rate_bpm` in each astronaut's phase observations. |
| CO₂ accumulation | Estimated in grams as the sum of phase production above the suit's removal capacity. This proxy describes excess CO₂ load. |
| Suit temperature | Optional simulated `suit_temperature_c` inside the suit in each astronaut's phase observations. |
| Walking speed | Average in meters per second, derived from the leg's `distance_m` and `time_s` when distance and positive duration are available. |
| Visibility distance | Optional simulated `visibility_distance_m` in the phase's environment. |

Pass phases in traversal order. Heart rate, suit temperature, and visibility are supplied readings. Walking speed and CO₂ excess are calculated for display. These five values are informational. The calculator uses workload estimates internally to calculate the four resource balances and enforce the existing peak workload limit.

```python
from runtime.humancost import Phase, evaluate, prepare

crew = "runtime/examples/crew-human-factors.json"
policy = "runtime/examples/human-cost-policy.json"

planning = prepare(crew, policy)["routing_inputs"]
planning_allowance_s = max(0, planning["remaining_s"] - planning["reserve_s"])
result = evaluate(crew, policy, [
    Phase("outbound", "outbound", 3600, 40, distance_m=1800, max_slope_deg=12,
          environment={"data_status": "simulated", "visibility_distance_m": 100},
          observations={"EV1": {"data_status": "simulated",
                                "heart_rate_bpm": 106, "suit_temperature_c": 21.5}}),
    Phase("dwell", "dwell", 1800, 0),
    Phase("return", "return", 3300, 12, distance_m=1800, max_slope_deg=12),
])
```

Use the planning allowance and crew walking profile from `prepare()` in Marswalk. Use `evaluate()` to check the resource reserves and workload for complete route candidates. On a pass, `route.risk` is the highest share of a usable resource budget spent, scaled to 0–100. On a failure, `route.breach` identifies the check and phase.

The report includes duration, gain, and visibility in `phase_context`. Each astronaut's `remaining_resources` gives the four balances after the route. Their `phase_metrics` include slope, walking speed, CO₂ excess, and any supplied observations. Missing readings stay unknown. Only visibility is accepted in `environment`, and only heart rate and suit temperature are accepted in `observations`.
