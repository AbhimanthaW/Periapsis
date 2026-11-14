# Simulated human cost calculator

`runtime.humancost` prices a proposed EVA route for each astronaut. It does not read the synthetic geology fields, alter the routing graph, or make medical or mission safety decisions. The example crew and policy are invented test inputs. The numerical "risk" is the worst fraction of a usable consumable budget spent, scaled to 0–100; it is **not** a failure probability.

```python
from runtime.humancost import Phase, evaluate, prepare, serialize

crew = "runtime/examples/crew-human-factors.json"
policy = "runtime/examples/human-cost-policy.json"
before_routing = prepare(crew, policy)
route = evaluate(crew, policy, [
    Phase("outbound", "outbound", 3600, 40),
    Phase("dwell", "dwell", 1800, 0),
    Phase("return", "return", 3300, 12),
])
wire_bytes = serialize(route)
```

`gain_m` is total positive elevation change in a walking phase, not net elevation change. `prepare()` returns a flat-rate planning estimate and a `HumanProfile` compatible with `load_profile`. `evaluate()` uses the route's actual phase durations and gains. Integrating either result with Marswalk requires a separate contract and review. The 900-second time reserve is additional to the individual consumable reserves.

| Feature | Included now | Possible later addition and required evidence |
|---|---|---|
| Crew inputs | Strict versioned JSON, per-astronaut masses, metabolic parameters and four initial consumable stores; simulated provenance | Suit-specific measured inputs, with calibration, units, timestamps and uncertainty |
| Metabolic work | Flat baseline plus positive elevation gain and joint work; constant flat-power dwell | Per-task dwell workload and local ascent profile, measured or justified for the suit and terrain |
| Resource estimates | O₂, cooling water, drinking water and battery; CO₂ production reported | CO₂ scrubber capacity and partial pressure, leakage, purge, heat storage and suit thermal dynamics |
| Personalisation | Demand ratio to a reference fixture, flat endurance, conservative crew pace and slope choice | Tested individual pace and metabolic response; separate profiles only if the routing contract permits them |
| Route checks | Ordered per-resource ledgers, reserve breach with resource and phase, worst-utilisation index | Calibrated uncertainty and probability of exhaustion, supported by empirical distributions |
| Routing handoff | `remaining_s`, `reserve_s`, `crew_status`, and a validated human profile in an unwired payload | Runtime integration with an explicit rule for reconciling the flat estimate with route-specific consumable checks |
| Live conditions | No live input | Timestamped telemetry, drift handling and replan triggers after sensor quality and authority rules are defined |
| Scientific context | Separate from `SYNTHETIC-SCIENCE.md` | Use source-backed context only after the repository's production-qualification steps; do not mix those fields into life-support rates without a causal model |

The fixture in `documentation/marsdoc/eva/scenario-v1.json` supplies the formula and units for the constant-activity cross-check. `documentation/SYNTHETIC-SCIENCE.md` instead describes invented spatial fields for deltas, fans, valley networks, glacial landforms, magnetic vectors and olivine. Those fields do not contain astronaut physiological or suit-consumables data.
