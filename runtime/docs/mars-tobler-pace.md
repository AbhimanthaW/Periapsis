# Mars Tobler pace model (proposal)

**Periapsis · Runtime · Senula · 14 November 2026, Colombo · Status: proposal for review**

This note proposes the human walking-time model for `runtime.marswalk`. It keeps the shape of Tobler's hiking function. It changes the speed scale, adds a walk-to-run speed cap and uses a slower pace for the return-home check. **No code changes yet.** Abhimantha and Isath should confirm it before it replaces the current default or the linear formula in the [Scientific Model Design Review](../../reference/architecture/scientific-model-design-review.md).

## The equation

Walking speed:

$$
v(g) = \min\Big(v_{\text{cap}},\; v_{\text{flat}} \cdot e^{-k\left(|g + c| - c\right)}\Big)
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

| Symbol | Meaning | Value | Status |
| --- | --- | --- | --- |
| $v$ | walking speed | m/s | calculated |
| $v_{\text{flat}}$ | flat-ground speed, outbound and science legs | **0.75 m/s** | Apollo planning value, see below |
| $v_{\text{flat}}$ | flat-ground speed, return-home check | **0.53 m/s** (0.75 × 0.7) | assumption, inside the Apollo measured range |
| $k$ | slope penalty | **3.5** | Tobler (1993), Earth hikers |
| $c$ | downhill offset (fastest grade) | **0.05** | Tobler (1993) |
| $v_{\text{cap}}$ | walk-to-run limit | **1.16 m/s** | Froude estimate, see below |
| $g$ | signed grade, + uphill, − downhill | none | from the DTM |
| $\Delta z$ | height change of the step | m | from the DTM |
| $L$ | horizontal step length | m | from the DTM cell size |
| θ | ground slope | degrees | Horn 3×3, from the DTM |
| — | slope limit | **15°** | policy assumption, source TBD (Isath) |

With the numbers filled in:

- Outbound: $v(g) = \min\big(1.16,\; 0.75 \cdot e^{-3.5(|g + 0.05| - 0.05)}\big)$
- Return home: $v(g) = \min\big(1.16,\; 0.53 \cdot e^{-3.5(|g + 0.05| - 0.05)}\big)$

The walk-to-run cap:

$$
v_{\text{cap}} = \sqrt{Fr^{*} \cdot g_{\text{Mars}} \cdot L_{\text{leg}}} = \sqrt{0.36 \times 3.721 \times 1.0} \approx 1.16 \text{ m/s}
$$

$g_{\text{Mars}}$ is gravity, a different quantity from the grade $g$.

## Comparison with the original Tobler function

| | Tobler (1993), Earth | Mars Tobler (proposed) |
| --- | --- | --- |
| Formula | $6\, e^{-3.5\,|g + 0.05|}$ km/h | $v_{\text{flat}}\, e^{-3.5(|g + 0.05| - 0.05)}$ m/s |
| Flat speed | 5 km/h ≈ 1.39 m/s | 0.75 m/s out, 0.53 m/s home |
| Fastest | 6 km/h at about −2.9° | 0.89 m/s at about −2.9°, never above 1.16 m/s |
| Steep ground | slower and slower, never refused | refused above 15° |

The `− c` term normalises the curve so that $v(0) = v_{\text{flat}}$ exactly. The curve shape is unchanged.

## Speeds at selected slopes

| Slope | Grade $g$ | Outbound (m/s) | Return home (m/s) | Note |
| ---: | ---: | ---: | ---: | --- |
| −15° | −0.27 | 0.42 | 0.29 | steep descent |
| −10° | −0.18 | 0.57 | 0.40 | |
| −5° | −0.09 | 0.78 | 0.55 | |
| −2.9° | −0.05 | **0.89** | 0.63 | fastest grade |
| 0° | 0 | 0.75 | 0.53 | flat |
| +5° | +0.09 | 0.55 | 0.39 | |
| +10° | +0.18 | 0.40 | 0.28 | Apollo 14 climb |
| +15° | +0.27 | 0.29 | 0.21 | slope limit |
| > 15° | | refused | refused | |

Worked example: a 5 m step on flat ground takes 5 ÷ 0.75 = 6.7 s outbound. A 5 m step up a 10° slope takes about 12.4 s.

## Justification

### 1. Keep Tobler's shape, $k = 3.5$ and $c = 0.05$

Tobler's function is fitted to Eduard Imhof's hiking data. Suited Apollo crews showed the same pattern: slow uphill, faster on gentle descents. On Apollo 14, Shepard and Mitchell struggled up a ten-degree slope near Cone Crater, then doubled their average speed going downhill on the return. On Apollo 12, Conrad and Bean covered 300 m up a 3 % grade at about 4 km/h, then had to stop for a few minutes to get their heart rate and breathing under control.

The Apollo accounts suggest slopes may cost suited walkers more than Earth hikers. No measured Mars-suit coefficient exists to replace 3.5. Inventing one would be less defensible than a published value. The 15° limit and the `steep_exposure_s` objective (time above 10°) handle risky slopes instead. Tobler's own fit reported no goodness-of-fit statistics, so even the Earth parameters are approximate.

### 2. Flat outbound speed 0.75 m/s

Apollo planners assumed an average of **2.7 km/h (0.75 m/s)** for walkbacks longer than an hour. A Marswalk is a long excursion, so this is the most directly relevant operational value. For comparison:

- Apollo 15 measured walking speeds of 1.1, 1.6 and 2.2 km/h (0.3–0.6 m/s) for short moves around the LM and geology stops.
- A 1970 NASA baseline used 4 km/h for nominal walking, derated for loads, slopes and surface properties.

0.75 m/s sits between the measured working pace and the undegraded baseline.

### 3. Slower pace for the return-home check (× 0.7 → 0.53 m/s)

This is a safety asymmetry, not a claim that crews physically walk slower on the way back. The two errors cost different amounts:

| Speed error | Consequence |
| --- | --- |
| Outbound assumed too slow | A feasible science stop is skipped. |
| Return assumed too fast | The crew is told it can get home when it cannot. |

The return check therefore assumes a tired crew at the end of the EVA. 0.53 m/s lies inside the Apollo 15 measured range. The ×0.7 factor is the existing `slow` pace scenario.

The 15-minute reserve $R$ is already a buffer, so this is a second safety layer:

| | Same speed both ways + reserve | Slower return + reserve |
| --- | --- | --- |
| Pro | simpler; one priced graph | the margin grows with the length of the return walk |
| Con | a fixed 15 min may be too little for a long return | slightly fewer feasible science stops; two priced graphs |

The main advantage is scaling. A 900 m flat return takes 20 min at 0.75 m/s and about 29 min at 0.53 m/s. The plan keeps about 9 extra minutes on top of $R$. A short return keeps only a small extra buffer. Long returns are where failures are most costly. Using 0.75 m/s both ways with only $R$ is also defensible. This is a team decision.

### 4. Walk-to-run cap 1.16 m/s

The walk-to-run transition occurs at a roughly constant Froude number $Fr = v^2 / (g L)$. Carr and McGee (2009) estimated $Fr^{*} \approx 0.36$ for suited Apollo astronauts. They found space suits lower $Fr^{*}$ compared with unsuited walkers. With Mars gravity and a 1 m leg, this gives about 1.16 m/s.

With $v_{\text{flat}} = 0.75$, the fastest speed is 0.89 m/s, so the cap does not bind today. It guards against a later configuration that sets $v_{\text{flat}}$ too high. **Assumption:** the 0.36 value comes from lunar suits and gravity. It has not been measured for Mars.

### 5. Keep the 15° slope limit

Apollo 14's ten-degree climb was the hardest traverse of the programme. Slopes above 15° are outside the suited-walking experience available here. The limit stays a labelled policy assumption until Isath provides a source.

## Deliberately not modelled

- **Gravity scaling of the slope penalty.** Lower gravity reduces climbing work, but suit and backpack mass increase it. No data shows which effect wins.
- **Terrain-type multipliers.** Tobler's off-path factor (×0.6) cannot be applied per cell without a surface classification. The hazard map handles terrain instead.
- **Fatigue or physiology models.** These are outside the project scope. The return pace is the only fatigue allowance.

## Required code changes (follow-up PR, after review)

1. `ToblerScaled.v_flat_mps`: 0.5 → **0.75**.
2. Add `max_speed_cap_mps = 1.16` and check at profile validation that the fastest speed never exceeds it.
3. Price the return graph with the return pace. The outbound Dijkstra uses the nominal pace. The transposed (home) Dijkstra uses the return pace. This means two priced graphs instead of one.
4. Record every value and its source in the plan's `assumptions` list.

## Decisions requested

- **Abhimantha:** does this replace the linear pace formula in the design review? Use one speed or two (out and home)?
- **Isath:** confirm or replace the 15° limit, the 15-minute reserve and the 0.7 return factor.

## Sources

- Tobler, W. (1993). *Three Presentations on Geographical Analysis and Modeling*, NCGIA Technical Report 93-1. Summary and sample values: [Tobler's hiking function](https://en.wikipedia.org/wiki/Tobler%27s_hiking_function)
- Campbell, M. J. et al. Review of travel-rate functions, noting Tobler's fit reports no accuracy statistics: [NSF PAR](https://par.nsf.gov/servlets/purl/10097294)
- Jones, E. M. *Lunar Gaits*, Apollo 11 Lunar Surface Journal (Apollo 15 speeds; 2.7 km/h walkback planning): [NASA ALSJ](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11.gaits.html)
- Apollo surface operations and mobility, including Apollo 12 and 14 traverses: [OSTI 7168757](https://www.osti.gov/servlets/purl/7168757)
- Baseline costs of lunar surface EVA, 1970 (4 km/h nominal walking): [NTRS 19700009560](https://ntrs.nasa.gov/api/citations/19700009560/downloads/19700009560.pdf)
- Carr, C. E. and McGee, J. (2009). The Apollo Number: space suits, self-support, and the walk-run transition. *PLoS ONE* 4(8): e6614: [MIT DSpace](https://dspace.mit.edu/handle/1721.1/52418)
