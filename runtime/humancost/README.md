# Simulated human cost calculator

`runtime.humancost` prices a proposed EVA route for each astronaut. It does not read the synthetic geology fields, alter the routing graph, or make medical or mission safety decisions. The example crew and policy are invented test inputs. The numerical "risk" is the worst fraction of a usable consumable budget spent, scaled to 0–100; it is **not** a failure probability.

```python
from runtime.humancost import Phase, evaluate, prepare, serialize

crew = "runtime/examples/crew-human-factors.json"
policy = "runtime/examples/human-cost-policy.json"
before_routing = prepare(crew, policy)
route = evaluate(crew, policy, [
    Phase("outbound", "outbound", 3600, 40,
          distance_m=1800, max_slope_deg=12,
          environment={"data_status": "simulated",
                       "radiation_dose_rate_mgy_day": 0.25,
                       "temperature_k": 238},
          observations={"EV1": {"data_status": "simulated",
                                "heart_rate_bpm": 106}}),
    Phase("dwell", "dwell", 1800, 0),
    Phase("return", "return", 3300, 12),
])
wire_bytes = serialize(route)
```

`gain_m` is total positive elevation change in a walking phase, not net elevation change. Marswalk's `Leg` calls this `ascent_m`; its `length_m` and `max_slope_deg` can supply the optional phase fields after a separate integration review. `prepare()` returns a flat-rate planning estimate and a `HumanProfile` compatible with `load_profile`. `evaluate()` uses the route's actual phase durations and gains. The 900-second time reserve is additional to the individual consumable reserves.

Optional `environment` values are phase samples, except `radiation_dose_rate_mgy_day`, which is explicitly treated as the phase-average rate for integration. `observations` is keyed by walking astronaut ID. Both require `data_status: "simulated"`; missing values stay unknown. The dose integral is an **ambient absorbed-dose proxy**, not a shielded astronaut dose. Vitals are reported observations, not inferred from metabolic energy. Values without a causal response law never change resource use or the risk index. A supplied `max_slope_deg` above the personal limit or phase-mean metabolic power above the declared peak produces a hard route failure; it does not produce a numerical risk score.

| Feature | Included now | Possible later addition and required evidence |
|---|---|---|
| Crew inputs | Strict versioned JSON, per-astronaut masses, metabolic parameters and four initial consumable stores; simulated provenance | Suit-specific measured inputs, with calibration, units, timestamps and uncertainty |
| Metabolic work | Flat baseline plus positive elevation gain and joint work; constant flat-power dwell | Per-task dwell workload and local ascent profile, measured or justified for the suit and terrain |
| Resource estimates | O₂, cooling water, drinking water and battery; CO₂ production and excess over declared removal rate | CO₂ partial pressure, leakage, purge, heat storage and suit thermal dynamics |
| Personalisation | Demand ratio to a reference fixture, flat endurance, conservative crew pace and slope choice | Tested individual pace and metabolic response; separate profiles only if the routing contract permits them |
| Route checks | Ordered per-resource ledgers, slope and mean-peak checks, reserve breach with resource and phase, worst-utilisation index | Calibrated uncertainty and probability of exhaustion, supported by empirical distributions |
| Routing handoff | `remaining_s`, `reserve_s`, `crew_status`, and a validated human profile in an unwired payload | Runtime integration with an explicit rule for reconciling the flat estimate with route-specific consumable checks |
| Environmental and human observations | Optional simulated phase context, ambient dose proxy, and per-person vital samples | Timestamped telemetry, validated environmental response laws, drift handling and replan triggers |
| Scientific context | Separate from `SYNTHETIC-SCIENCE.md` | Use source-backed context only after the repository's production-qualification steps; do not mix those fields into life-support rates without a causal model |

The fixture in `documentation/marsdoc/eva/scenario-v1.json` supplies the formula and units for the constant-activity cross-check. `documentation/SYNTHETIC-SCIENCE.md` instead describes invented spatial fields for deltas, fans, valley networks, glacial landforms, magnetic vectors and olivine. Those fields do not contain astronaut physiological or suit-consumables data.

## Screenshot variable inventory

The screenshots show rows 1–22 and 25–28. Rows 23 and 24 are cropped out; `documentation/EVA-CONTEXT.md` identifies them as core body temperature and spacesuit internal pressure. All 28 concern the human EVA in some way. Their roles in this calculator are different:

| # | Variable | Treatment in `evaluate()` |
|---:|---|---|
| 1 | Radiation dose rate | Integrate a supplied phase-average rate into an ambient dose proxy; unknown when any phase lacks a rate |
| 2 | Temperature | Validated simulated phase observation; no thermal multiplier without a suit heat-transfer model |
| 3 | Wind speed | Validated simulated phase observation; no walking-force or dust model |
| 4 | Atmospheric pressure | Validated simulated phase observation; not a suit-pressure measurement |
| 5 | Energy consumption | Calculated battery use in Wh, by phase |
| 6 | Oxygen consumption | Calculated O₂ use in grams, by phase |
| 7 | Water consumption | Calculated drinking and cooling water separately |
| 8 | CO₂ accumulation/removal load | Calculated production and excess over each astronaut's declared removal rate; no ppCO₂ claim |
| 9 | Metabolic expenditure | Calculated energy in kJ and phase-mean power in W |
| 10 | Suit battery charge | Remaining Wh in the battery ledger |
| 11 | Suit cooling demand | Calculated phase-mean W from the declared heat balance |
| 12 | Dust concentration | Validated simulated phase observation; no visibility conversion without optical parameters |
| 13 | Solar illumination | Validated simulated phase observation; no heat input without irradiance and suit geometry |
| 14 | Terrain slope | `gain_m` adds uphill work; optional maximum slope checks the personal route limit |
| 15 | Surface traction | Validated simulated phase observation; no slip or walking-cost coefficient |
| 16 | Regolith sinkage | Validated simulated phase observation; no locomotion penalty without a terrain model |
| 17 | Obstacle density | Validated simulated phase observation; route duration already governs consumption |
| 18 | Suit mobility resistance | Declared joint power contributes to metabolic energy and is reported per phase |
| 19 | Communication signal availability | Validated simulated phase observation; no automatic mission decision without a communication rule |
| 20 | Visibility distance | Validated simulated phase observation; no arbitrary speed penalty |
| 21 | Walking speed | `distance_m / time_s` when distance is supplied; duration drives consumables |
| 22 | Heart rate | Per-astronaut simulated observation; no inferred medical state |
| 23 | Core body temperature | Per-astronaut simulated observation; no inferred heat illness |
| 24 | Spacesuit internal pressure | Per-astronaut simulated observation; no inferred decompression status |
| 25 | Suit oxygen reserve | Remaining grams and margin in the O₂ ledger |
| 26 | Suit cooling-water reserve | Remaining kilograms and margin in the cooling-water ledger |
| 27 | Remaining EVA duration | Flat-rate remaining consumable estimate after the route, explicitly labelled estimated |
| 28 | Communication latency | Validated simulated phase observation; no automatic coordination penalty |
