# Trade-off Envelope (P0)

`runtime.tradeoff` prices every option the Marswalk planner already produces and puts it in one of three classes. It **never decides and never executes**. Spec: `docs/tradeoff-model/plan.md` (PR #28). This is the deterministic P0 slice; the Monte Carlo and the burn-rate belief are P1 and are not here.

Assessment requires synthetic terrain. Crew, envelope, telemetry and any acceptance records are scoped to the simulated rehearsal. The runtime planner exposes no acceptance endpoint. Operational authorization of L2 exceptions remains an open design decision. The margin factor, floors and thresholds are **assumptions** awaiting review. Nothing in this package has been validated against flight data.

```python
from runtime.marswalk import plan_marswalk
from runtime.tradeoff import (accept, accepted_count, assess, is_executable, load_envelope,
                              record_assessment, record_decision, serialize)

plan = plan_marswalk(baseline, snapshot, multistop=True)          # unchanged planner
envelope = load_envelope("runtime/examples/tradeoff-envelope-simulated.json", now_utc=now)
result = assess(plan, "runtime/examples/crew-human-factors.json", "runtime/examples/human-cost-policy.json",
                envelope, now_utc=now, telemetry=telemetry, decision_window_s=900,
                one_way_light_time_s=light_time_s,                # an input; no value is built in
                accepted_amber_count=accepted_count(log, envelope.envelope_id))
record_assessment(log, result)
wire_bytes = serialize(result)                                    # same inputs, same bytes
```

## What it does

| Step | Module | Output |
|---|---|---|
| T0 Envelope contract | `envelope.py` | Validated `tradeoff-envelope-v1`, or a refusal with the reason |
| T1 Option table | `options.py` | Each `CandidatePlan` as ordered human-cost phases and per-astronaut ledgers at nominal rates |
| T4 Classifier | `classify.py` | `tradeoff-assessment-v1` per option: class, first failing rule, per-astronaut and per-resource margins |
| T5 Trade-off card | `card.py` | Each AMBER option against the best GREEN option: what it adds, what it costs |
| T6 Acceptance | `accept.py` | An `accepted` or `refused` record; `is_executable()` |
| T7 Audit log | `audit.py` | Append-only JSON lines with a hash chain; `verify()` |
| Telemetry gate | `telemetry.py` | Whether readings are fresh and plausible enough for AMBER to be offered |

## What it does not do

- It is not ML. Nothing is trained and no LLM is called.
- It does not predict health or medical events, and infers no medical state from any reading.
- It does not rank crew or choose who takes a risk. Astronauts are listed by id.
- It outputs no combined score across resources or people, and no probability of any kind in P0.
- It does not change `enforce_hard_constraints`, the weather rule or `EXCLUDED_FROM_CORE`, and it does not touch the plan, the snapshot or any authorised limit.
- It does not compute an exchange rate between science and reserve. The card lists both sides.

## Class rules

The nominal human-cost ledger is multiplied by one fixed `consumption_margin_factor` from the envelope. After every phase, `initial - factor x cumulative use` must stay at or above the reserve floor (the prefix rule, so a good end balance cannot hide an earlier breach).

| Class | Rule |
|---|---|
| **GREEN** | Every leg is admissible; every Marswalk hard constraint passes; no slope or peak-power limit is exceeded; every astronaut and resource holds its **L1** floor in every phase. |
| **AMBER** | Not GREEN only because an L1 floor is crossed, **and** every task in the option has a priority class with a pre-signed exception, **and** the **L2** floors for those classes hold in every phase, **and** all gates are open: direct return is GREEN; weather was assessed and no WARNING is active; the envelope has not expired; telemetry is present, fresh and plausible; an authority can answer inside the decision window; the risk budget has room. Executable **only** after an acceptance record. |
| **RED** | Anything else, with the first failing rule (`route:…`, `hard_constraint:…`, `human_cost:…`, `reserve_floor_l1:…`, `reserve_floor_l2:…`, `amber_gate:…`). Never executable. |

"Return now" is never AMBER. If it is not GREEN, `return_now.alert` says so in capitals and every option is RED.

Bad or missing inputs close the AMBER gates. They never change a GREEN, because GREEN rests only on the planner's own constraints and the factored ledger. A reading never lowers a consumption estimate.

### Floors

- **L0** (code constants in `envelope.py`): no exception may put a reserve floor below 10% of the starting oxygen, cooling water or battery. An envelope that tries is refused. *These numbers are assumptions.*
- **L1**: the human-cost policy reserve, already raised for higher-demand astronauts, tightened by any surgeon override in the envelope.
- **L2**: the exception fraction for the option's priority class. Both personal tightenings are kept: the raised-demand increment is added on top, and a surgeon override still binds. With several tasks, the tightest floor applies.
- A personal value looser than the mission value is refused. An exception floor *above* the mission reserve is also refused (tighten the mission policy instead).
- Drinking water has an absolute reserve and no L2 exception.

## Acceptance

AMBER needs signatures from `flight_director` and `crew_surgeon` (different people, each with a reason), consent from every walking astronaut (silence is not consent), and no veto. A `science_lead` signature is refused on the envelope and on an acceptance. An acceptance expires at the earliest of its validity duration, envelope expiry, decision deadline and telemetry expiry. Anyone can `withdraw()` it.

**Risk budget (P0 form):** a count of accepted AMBER options per EVA against `max_accepted_amber_per_eva`. The plan's probability-sum budget (`risk_budget_per_eva`) is validated and stored but needs P1 probabilities.

**Latency routing:** Earth roles are available only if `decision_window_s >= 2 x one_way_light_time_s + response_allowance_s`. Otherwise only the envelope's `habitat_delegate` may sign, and with no delegate the result is GREEN-only.

## Guardrails

| # | Guardrail | P0 status | Test |
|---|---|---|---|
| G1 | The model never executes | Enforced: pricing modules have no path that rewrites a plan | `test_model_reads_but_never_mutates_the_plan` |
| G2 | L0 floors cannot be relaxed in-app | Enforced by code constants | `test_envelope_that_relaxes_l0_is_refused` |
| G3 | Personal values may only tighten | Enforced | `test_personal_override_looser_than_the_mission_value_is_refused` |
| G4 | Two roles plus crew consent; anyone vetoes | Enforced | `test_missing_or_wrong_role_is_refused`, `test_crew_veto_or_silence_blocks_acceptance` |
| G5 | Fail closed on stale, missing or implausible input | Enforced | `test_stale_or_missing_telemetry_means_green_only` |
| G6 | No crew ranking, no single score | Enforced by the output shape | `test_output_has_no_crew_ranking_no_combined_score_and_no_forbidden_words` |
| G7 | Acceptances expire; trip-wires revert | **Partial**: expiry and withdrawal only. Trip-wires are P1 | `test_amber_is_not_executable_without_or_after_its_acceptance` |
| G8 | Risk budget per EVA | Enforced as a count (see above) | `test_ten_small_acceptances_cannot_exceed_the_risk_budget` |
| G9 | Value and acceptance roles separated | Enforced | `test_science_lead_signature_is_refused_everywhere` |
| G10 | Hash-chained audit | Enforced | `test_tampered_audit_line_breaks_verification` |
| G11 | A stuck-low O₂ sensor must not make an option look better | Enforced: rate bounds and O₂/CO₂ agreement. Heart-rate trends are not used | `test_stuck_low_oxygen_reading_never_makes_an_option_look_better` |
| G12 | Latency-aware authority | Enforced | `test_window_shorter_than_the_light_time_round_trip_with_no_delegate_is_green_only` |

## Limits

- **Deterministic only.** One fixed margin factor stands in for uncertainty. Every probability field in the output is `null`, as are trip-wires, the latest decision time and expected science.
- **All inputs simulated.** Crew, policy, envelope and telemetry are invented fixtures. The envelope's numbers and the L0 floors are assumptions for Isath to review (plan decision D3).
- **Starting stores are read as current stores.** The crew file's `initial_*` values are taken as the stores at the moment of assessment. Nothing reconciles them with consumption earlier in the EVA.
- **Telemetry is a gate, not an input to the ledger.** The plausibility check compares the observed O₂ rate with the *flat-walking* nominal rate, so a legitimate hard climb can close the AMBER gate. That errs toward GREEN-only.
- **An acceptance does not write a new snapshot revision.** The plan (section 5) has L3 write a revision whose authorised limits the hard-constraint pass then re-reads. Today `AuthorizedLimit` supports only `max_leg_s` and the planner does not read consumable reserves, so there is nothing for it to re-read. The acceptance record names the snapshot revision it applies to instead.
- **Signatures are hash checks, not cryptography.** Anyone who can write the file can sign it.
- **The audit chain cannot detect removal of its last lines.** Keep the head hash elsewhere if that matters.
- **Human walking plans only.** Rover plans are refused.
- `margin_s` is a flat-rate estimate of time left above the L1 floor.
