# Mars Tobler pace model (proposal)

**Periapsis · Runtime · Senula · 14 November 2026, Colombo · Status: proposal for review, revision 2**

This note proposes the human walking-time model for `runtime.marswalk`. It keeps the shape of Tobler's hiking function, adds a walk-to-run speed limit, and proposes a slower pace for the return-home check. **No runtime code changes.** The current default stays at 0.50 m/s until the team selects a pace from the sensitivity evidence below.

**Revision 2 responds to review:**

- 0.75 m/s is now a **candidate**, not the proposed default.
- A pace and reserve sensitivity study shows which recommendations change.
- The speed limit now has one behaviour. A profile whose fastest speed exceeds the limit is **rejected at validation**. The equation no longer clamps.

## The equation

Walking speed:

$$
v(g) = v_{\text{flat}} \cdot e^{-k\left(|g + c| - c\right)}
$$

Time for one step:

$$
t = \frac{L}{v(g)}
$$

Grade of the step:

$$
g = \frac{\Delta z}{L}
$$

The engine refuses the step if the ground slope θ > 15°.

Profile validation, checked once before planning:

$$
v_{\max} = v_{\text{flat}} \cdot e^{k c} \;\le\; v_{\text{cap}} \qquad \text{otherwise the profile is rejected (INVALID\_PROFILE)}
$$

| Symbol | Meaning | Value | Status |
| --- | --- | --- | --- |
| $v$ | walking speed | m/s | calculated |
| $v_{\text{flat}}$ | flat-ground speed | **0.50 m/s** current default; candidates 0.40–0.75 | assumption, see sensitivity |
| $f_{\text{return}}$ | return-home pace factor, home pace = $f_{\text{return}} \cdot v_{\text{flat}}$ | **1.0** current; candidate **0.7** | assumption |
| $k$ | slope penalty | **3.5** | Tobler (1993), Earth hikers |
| $c$ | downhill offset (fastest grade) | **0.05** | Tobler (1993) |
| $v_{\max}$ | fastest speed on the curve, at $g = -c$ | $v_{\text{flat}} \cdot e^{0.175}$ ≈ 1.19 × $v_{\text{flat}}$ | calculated |
| $v_{\text{cap}}$ | walk-to-run limit | **1.16 m/s** | Froude estimate, see below |
| $g$ | signed grade, + uphill, − downhill | none | from the DTM |
| $\Delta z$ | height change of the step | m | from the DTM |
| $L$ | horizontal step length | m | from the DTM cell size |
| θ | ground slope | degrees | Horn 3×3, from the DTM |
| — | slope limit | **15°** | policy assumption, source TBD (Isath) |

The walk-to-run limit:

$$
v_{\text{cap}} = \sqrt{Fr^{*} \cdot g_{\text{Mars}} \cdot L_{\text{leg}}} = \sqrt{0.36 \times 3.721 \times 1.0} \approx 1.16 \text{ m/s}
$$

$g_{\text{Mars}}$ is gravity, a different quantity from the grade $g$. The validation accepts any $v_{\text{flat}} \le 1.16 / 1.19 \approx 0.97$ m/s. Every candidate below passes.

### Why reject instead of clamp

- **Clamping hides a bad profile.** A profile above the walk-to-run limit is a configuration error. Clamping would silently flatten the top of the curve, and the plan would still look valid. Rejecting fails closed with a reason code, which matches how the runtime treats other invalid inputs.
- **No candidate needs it.** All candidate paces stay below the limit, so rejecting removes nothing in normal use.
- **One rule, checked once.** The check runs at profile validation, not on every edge, and the edge-time formula stays a single expression.

## Comparison with the original Tobler function

| | Tobler (1993), Earth | Mars Tobler (proposed) |
| --- | --- | --- |
| Formula | $6\, e^{-3.5\,\lvert g + 0.05\rvert}$ km/h | $v_{\text{flat}}\, e^{-3.5(\lvert g + 0.05\rvert - 0.05)}$ m/s |
| Flat speed | 5 km/h ≈ 1.39 m/s | $v_{\text{flat}}$ (0.50 m/s current default) |
| Fastest | 6 km/h at about −2.9° | 1.19 × $v_{\text{flat}}$ at about −2.9°; profiles above 1.16 m/s rejected |
| Steep ground | slower and slower, never refused | refused above 15° |

The `− c` term normalises the curve so that $v(0) = v_{\text{flat}}$ exactly. The curve shape is unchanged.

## Speeds at selected slopes

| Slope | Grade $g$ | 0.50 m/s (current) | 0.75 m/s (candidate) | 0.525 m/s (0.75 × 0.7 home) |
| ---: | ---: | ---: | ---: | ---: |
| −15° | −0.27 | 0.28 | 0.42 | 0.29 |
| −10° | −0.18 | 0.38 | 0.57 | 0.40 |
| −5° | −0.09 | 0.52 | 0.78 | 0.55 |
| −2.9° | −0.05 | **0.60** | **0.89** | 0.63 |
| 0° | 0 | 0.50 | 0.75 | 0.53 |
| +5° | +0.09 | 0.37 | 0.55 | 0.39 |
| +10° | +0.18 | 0.27 | 0.40 | 0.28 |
| +15° | +0.27 | 0.20 | 0.29 | 0.21 |
| > 15° | | refused | refused | refused |

Raising $v_{\text{flat}}$ from 0.50 to 0.75 m/s cuts every modelled walking time by one-third. On the demo terrain, the direct return takes 8.9 min at 0.50 m/s, 5.9 min at 0.75 m/s and 8.4 min at 0.525 m/s.

## Evidence for the pace values

### Tobler's shape, $k = 3.5$ and $c = 0.05$

Tobler's function is fitted to Eduard Imhof's hiking data, and the fit reports no accuracy statistics. Suited Apollo crews showed the same qualitative pattern: slow uphill, faster on gentle descents. On Apollo 14, Shepard and Mitchell struggled up a ten-degree slope near Cone Crater, then doubled their average speed going downhill on the return. On Apollo 12, Conrad and Bean covered 300 m up a 3 % grade at about 4 km/h, then had to rest to recover their heart rate and breathing.

The Apollo accounts suggest slopes may cost suited walkers more than Earth hikers. No measured Mars-suit coefficient exists to replace 3.5. The 15° limit and the `steep_exposure_s` objective handle risky slopes instead.

### What the speed sources measure

| Value | Source | What it describes | Fit for our use |
| --- | --- | --- | --- |
| 1.1, 1.6, 2.2 km/h (0.3–0.6 m/s) | Apollo 15, ALSJ | **short movements** around the LM and at geology stops | Work-site pace. Not a traverse speed. |
| 2.7 km/h (0.75 m/s) | Apollo planners, ALSJ | assumed **average for emergency walkbacks** of more than an hour after a rover failure | A planning assumption for a contingency, not a measured nominal pace. |
| 4 km/h | 1970 NASA EVA baseline | nominal walking before derating for loads, slopes and surface | An undegraded upper reference. |

None of these is a measured Mars traverse pace. 0.75 m/s is therefore a **candidate assumption**, not evidence that crews will walk that fast.

### Return-home factor, candidate × 0.7

This is a safety asymmetry, not a claim that crews physically walk slower on the way back.

| Speed error | Consequence |
| --- | --- |
| Outbound assumed too slow | A feasible science stop is skipped. |
| Return assumed too fast | The crew is told it can get home when it cannot. |

The 15-minute reserve $R$ is a fixed buffer. A return factor adds a buffer that grows with the length of the return walk. Using one pace both ways with only $R$ is also defensible. This is a team decision.

### Walk-to-run limit, 1.16 m/s

The walk-to-run transition occurs at a roughly constant Froude number $Fr = v^2 / (g L)$. Carr and McGee (2009) estimated $Fr^{*} \approx 0.36$ for suited Apollo astronauts. They found space suits lower $Fr^{*}$ compared with unsuited walkers. **Assumption:** the 0.36 value comes from lunar suits and gravity. It has not been measured for Mars.

### Slope limit, 15°

Apollo 14's ten-degree climb was the hardest traverse of the programme. The limit stays a labelled policy assumption until Isath provides a source.

## Sensitivity study

[`tobler_sensitivity.py`](tobler_sensitivity.py) runs the synthetic Marswalk demo (160 × 160 cells at 5 m, scarp with two ramps, two tasks) through the real `TerrainGraph`, `Router` and Dijkstra fields. The outbound field uses $v_{\text{flat}}$. The home field uses $f_{\text{return}} \cdot v_{\text{flat}}$. Selection follows the single-stop runtime rule. With $f_{\text{return}} = 1$, the script reproduces `plan_marswalk` at the current default before it runs.

```sh
python runtime/docs/tobler_sensitivity.py
```

**Grid:** $v_{\text{flat}}$ ∈ {0.40, 0.50, 0.60, 0.75} m/s × $f_{\text{return}}$ ∈ {1.0, 0.7} × reserve ∈ {10, 15, 20, 30} min × remaining time ∈ {45, 60, 75, 90} min × north ramp {open, closed} = 256 settings.

### How often the next action changes

Compared with the current pace (0.50 m/s, symmetric) at the same reserve and situation (32 situations each):

| Setting | Actions changed | Science instead of a return | Return instead of science |
| --- | ---: | ---: | ---: |
| 0.40 m/s | 3 | 0 | 0 |
| 0.40 m/s, home × 0.7 | 7 | 0 | 0 |
| **0.50 m/s (current)** | **0** | **0** | **0** |
| 0.50 m/s, home × 0.7 | 3 | 0 | 0 |
| 0.60 m/s | 3 | 0 | 0 |
| 0.60 m/s, home × 0.7 | 0 | 0 | 0 |
| **0.75 m/s** | **10** | **2** | 0 |
| 0.75 m/s, home × 0.7 | 3 | 0 | 0 |

### Findings

1. **0.75 m/s on both legs is the outlier.** It changes 10 of 32 actions, the most of any setting. It is the only setting that recommends a science stop where the current default returns: remaining time 45 min, reserve 30 min, ramp open or closed.
2. **0.75 m/s outbound with a × 0.7 home pace behaves close to the current default.** It changes 3 of 32 actions and never trades a return for science. Its home pace (0.525 m/s) is close to today's 0.50 m/s, and the direct-return gate depends only on the home pace.
3. **Changes sit at decision boundaries.** They occur when the budget is tight (45–60 min remaining) or the reserve is large (30 min). With the ramp open and 75–90 min remaining, almost every setting picks the same task.
4. **Reserve matters as much as pace.** At 0.50 m/s, raising the reserve from 15 to 30 min changes the action in 4 of 8 situations (20 min: 1 of 8; 10 min: 0 of 8). At a 15 min reserve, changing the pace to 0.75 m/s changes 2 of 8, and 0.40 m/s changes 1 of 8. Pace and reserve should be chosen together.
5. **A pessimistic setting can fail the safety gate.** At 45 min remaining with a 30 min reserve, 0.40 m/s with home × 0.7 reports `RETURN_OVER_RESERVE`, while the current default still finds a direct return. The direct-return verdict is therefore pace-sensitive close to the reserve.
6. **Scope.** This is synthetic terrain with two tasks. It shows how sensitive the decision is. It does not show which pace is correct.

## Recommendation

- **Keep $v_{\text{flat}} = 0.50$ m/s as the default** until Isath reviews the pace sources. The evidence does not justify changing which science stops fit.
- **List 0.40–0.75 m/s as declared candidate profiles** and treat the choice as a scenario assumption recorded in each plan.
- **If a faster outbound pace is adopted, pair it with the × 0.7 home pace.** The safety-relevant return check then stays close to today's behaviour.
- **Reject profiles above the walk-to-run limit** at validation. Do not clamp.
- A later runtime option could report when the next action would differ under the slowest candidate pace, so the crew sees decisions close to a boundary.

## Deliberately not modelled

- **Gravity scaling of the slope penalty.** Lower gravity reduces climbing work, but suit and backpack mass increase it. No data shows which effect wins.
- **Terrain-type multipliers.** Tobler's off-path factor (× 0.6) cannot be applied per cell without a surface classification. The hazard map handles terrain instead.
- **Fatigue or physiology models.** These are outside the project scope.

## Follow-up code changes (after a decision)

1. Add profile validation $v_{\text{flat}} e^{kc} \le 1.16$ m/s → `INVALID_PROFILE`. The default is unchanged.
2. If adopted: an optional `return_pace_factor` on `HumanProfile`. The transposed (home) Dijkstra uses the return pace, which needs a second priced graph.
3. Record the chosen pace, factor and sources in the plan's `assumptions` list.

## Decisions requested

- **Abhimantha:** does this replace the linear pace formula in the design review? One pace, or a separate home pace?
- **Isath:** confirm or replace the pace range, the 15° limit, the 15-minute reserve and the 0.7 return factor.

## Sources

- Tobler, W. (1993). *Three Presentations on Geographical Analysis and Modeling*, NCGIA Technical Report 93-1. Summary and sample values: [Tobler's hiking function](https://en.wikipedia.org/wiki/Tobler%27s_hiking_function)
- Campbell, M. J. et al. Review of travel-rate functions, noting Tobler's fit reports no accuracy statistics: [NSF PAR](https://par.nsf.gov/servlets/purl/10097294)
- Jones, E. M. *Lunar Gaits*, Apollo 11 Lunar Surface Journal (Apollo 15 work-site speeds; 2.7 km/h emergency walkback planning assumption): [NASA ALSJ](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11.gaits.html)
- Apollo surface operations and mobility, including Apollo 12 and 14 traverses: [OSTI 7168757](https://www.osti.gov/servlets/purl/7168757)
- Baseline costs of lunar surface EVA, 1970 (4 km/h nominal walking): [NTRS 19700009560](https://ntrs.nasa.gov/api/citations/19700009560/downloads/19700009560.pdf)
- Carr, C. E. and McGee, J. (2009). The Apollo Number: space suits, self-support, and the walk-run transition. *PLoS ONE* 4(8): e6614: [MIT DSpace](https://dspace.mit.edu/handle/1721.1/52418)
