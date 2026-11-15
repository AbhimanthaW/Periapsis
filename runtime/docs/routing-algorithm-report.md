# Periapsis routing algorithm

*Algorithm report · 15 November 2026*

## Summary

Periapsis plans local traverses for a crew on foot or in a crewed rover. It converts an elevation raster into a directed graph, removes movements through closures, then uses Dijkstra's algorithm to find minimum-time legs. A second stage checks whether those legs form a mission that preserves the time and resource reserves needed to reach shelter. For a rover mission, the crew must also be able to walk back from every sampled breakdown point, including after science dwell.

In the bundled storm replay, the direct return grew from **436 m to 1,070 m** at the same start position. The walking estimate rose from **867 s to 2,216 s**, and the rover estimate rose from **291 s to 714 s**. Both modes switched to recommending direct return when required weather data expired. These results verify replanning and constraint handling on simulated inputs. Terrain passability, travel-time accuracy and resource predictions on Mars remain unvalidated.

This report covers the integrated drill on `feature/final-routing-integration`. Its HTTP entry point is `POST /api/v1/routing/plan`, which runs Marswalk for both modes. [Reviewed commit `654cd57`](https://github.com/AbhimanthaW/Periapsis/tree/654cd57cb64406981a4cd9933f108a14ea2c2c88) · [Routing API](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/planning_api.py#L249) · [Integrated planner](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/final_routing.py#L287)

## 1. Terrain and the movement graph

The inputs are a versioned grid with elevation in metres, a validity mask and permanent exclusions, plus a mission snapshot with current cell, shelter cell, confirmed tasks, time budget, mobility profiles and current hazard reports. The drill uses a local 160 × 160 raster with 5 m spacing, covering 800 × 800 m. The baseline terrain screen excludes slopes above 15°. Unsupported terrain and known exclusions have separate statuses, so a failed search can distinguish some evidence gaps from known blockages. The analytical pack contract currently allows routing on synthetic terrain. Its site gate checks native and analytical grid spacing against a 20 m ceiling and caps the grid at one million cells. [Synthetic terrain](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/demo.py#L50) · [Baseline screen](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/traversability.py#L167) · [Site gate](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/site.py#L184)

Each vertex corresponds to a raster cell centre. A cell can connect to four cardinal neighbours or to eight neighbours including diagonals. The drill uses eight. A diagonal requires both adjacent cardinal cells to be open, preventing a route from cutting the corner of an exclusion. Active closures delete edges that touch the closed cells, including diagonals that use those cells as side neighbours. Each directed move from cell $u$ to cell $v$ has horizontal length $\ell$, elevation change $\Delta z$ and signed grade $g$.

$$
\ell=\sqrt{(\Delta c\,d_x)^2+(\Delta r\,d_y)^2},
\qquad
\Delta z=z_v-z_u,
\qquad
g=\frac{\Delta z}{\ell}.
$$

Here $d_x$ and $d_y$ are the column and row spacing in metres. The approximate surface length of the move is $\sqrt{\ell^2+\Delta z^2}$. The planner reports horizontal and surface distances separately. Reversing direction changes the sign of $g$, which can change walking time and rover energy. [Grid moves and edge construction](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/routing.py#L111-L172) · [Closure filtering](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/routing.py#L202-L234)

### Walking time

Marswalk scales Tobler's terrestrial hiking curve to a flat-ground scenario speed $v_f$. With grade dimensionless and $v_f$ in m/s, the edge time $t_h$ is in seconds.

$$
v(g)=v_f\exp[-3.5(|g+0.05|-0.05)],
\qquad
t_h=\frac{\ell}{v(g)}.
$$

The normalisation gives $v(0)=v_f$ and peak speed at a downhill grade of $-5\%$. The drill's two-person profile uses $v_f=0.50\ \mathrm{m/s}$ and a 15° slope limit. The model screens both the along-edge angle $\arctan|g|$ and the Horn slope estimated at each endpoint. Missing endpoint slope support excludes the edge. On a 5 m horizontal step with 0.50 m of rise, the model gives **14.19 s uphill** and **10.00 s downhill** on the reverse edge. A single undirected edge weight would lose that difference. [Walking model](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/mobility.py#L49-L98)

Tobler fitted the original curve to Earth walking data. The 0.50 m/s reference comes from a lunar planning example that fixed the value as an input. Goodwin, Hammett and Harris found that fitted slope response changed with sampling interval in an Earth analogue study. Their work used time-optimal routes to examine walkback contingencies and gives a reason to test pace assumptions at the resolution used for routing. [Tobler, NCGIA Technical Report 93-1](https://escholarship.org/content/qt05r820mz/qt05r820mz_noSplash_8f1f13a718ba4a0db0079773ffa4a7af.pdf) · [Broddrick et al., NASA NTRS 20240000165](https://ntrs.nasa.gov/citations/20240000165) · [Goodwin et al., Acta Astronautica](https://doi.org/10.1016/j.actaastro.2024.12.005)

### Rover time and energy

The rover model rejects edges with excessive incline, endpoint slope or local relief, or missing evidence needed for those checks. For an accepted edge, the rover travels its approximate surface length at the declared nominal speed. Gross electrical energy includes rolling resistance, change in gravitational potential energy, drivetrain losses and auxiliary power.

$$
t_r=\frac{\sqrt{\ell^2+\Delta z^2}}{v_r},
\qquad
E_r=\frac{\max(0,\,m g_M[\Delta z+C_{\mathrm{rr}}\ell])}{\eta}+P_{\mathrm{aux}}t_r.
$$

Here $m$ includes payload, $g_M=3.721\ \mathrm{m/s^2}$, $C_{\mathrm{rr}}$ is the rolling resistance coefficient, $\eta$ is drivetrain efficiency and $P_{\mathrm{aux}}$ is in watts. The work term and $P_{\mathrm{aux}}t_r$ are both in joules. The zero lower bound on mechanical work omits regenerative braking. The hypothetical drill rover uses 1.50 m/s, a 20° incline limit and 0.35 m clearance. The shared 15° terrain screen can still exclude cells the rover profile would otherwise allow. The clearance test uses a residual from a local plane fit to the raster, so it can miss a wheel-scale obstacle. [Rover mobility and profile](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/rover.py#L28-L108) · [Local relief calculation](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/traversability.py#L239)

## 2. Path search and route selection

Marswalk stores the open graph as a sparse adjacency matrix. Dijkstra repeatedly settles the lowest tentative travel time and relaxes its outgoing edges. Every usable edge has positive time. On this graph the settled time is therefore the minimum, since extending another unsettled path cannot reduce its cost. [Dijkstra, Numerische Mathematik (1959)](https://doi.org/10.1007/BF01386390) · [Python and SciPy backends](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/routing.py#L74-L108)

1. A forward search from the current position gives the fastest outbound leg to every reachable task cell.
2. One search from the shelter on the **transposed** graph gives the fastest return from every reachable cell. The transpose reverses each edge and retains its original weight. Each original path $x\rightarrow h$ therefore has an equally weighted path $h\rightarrow x$ in the transpose. Following the transpose search's predecessor pointers from $x$ gives the next moves towards shelter in the original graph.
3. A separate distance-weighted search gives the shortest horizontal return on the same admissible graph as a reference. Its geometry still needs the mission checks before use. A rover plan also uses a shelter search on the walking graph for the walkback check.

The forward and return fields are reused across tasks within the request. The Python heap implementation takes $O((V+E)\log V)$ worst-case time per search on this grid and $O(V+E)$ memory. An eight-neighbour grid has at most $8V$ directed edges. The integrated service rebuilds and filters the graph on each revision, and the rover energy fallback adds further solves when triggered. The complexity bound covers the search. API latency also includes graph construction, resource checks and serialisation. [Search fields and distance reference](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/routing.py#L252-L314) · [Planner graph construction](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/plan.py#L183-L204)

### Mission checks

The integrated drill always constructs a direct return. It adds a candidate for each confirmed unfinished task, using an outbound leg, dwell at the task and a return leg. With $B$ seconds remaining and $R$ seconds reserved, a candidate's time margin is

$$
M_t=B-R-\left(\sum_i t_i+\sum_j t_{\mathrm{dwell},j}\right).
$$

A negative margin refuses the candidate. A candidate must also pass its terrain, task prerequisite and applicable weather and resource checks. The objective classifier can suggest a catalogue task for confirmation. The path search takes the confirmed task's fixed approach cell. The walking resource checks estimate oxygen, cooling water, drinking water and suit battery use for each astronaut and compare their remaining stores with the reserve floors. The integrated recommendation requires a GREEN direct return and GREEN candidate under the simulated trade-off policy. An AMBER candidate can be displayed for review. [Candidate construction](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/optimization.py#L73-L86) · [Constraint rules](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/optimization.py#L218-L280) · [Human recommendation gate](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/final_routing.py#L186-L209)

The rover ledger checks battery reserve after consumption in each edge or dwell phase, then adds any permitted supply up to capacity. It also checks the phase-average discharge limit. For every sampled rover position $x$ at elapsed time $\tau_x$, including after dwell, the walkback check requires

$$
\tau_x + T_{\mathrm{walk}}(x,h)\le B-R .
$$

The drill checks both astronauts' consumables for that contingency. It combines estimated consumption before breakdown with the cost of the directed walk to shelter. When the rover's fastest candidate fails only on energy, the solver tries a bounded set of time, energy and mixed-weight routes and reruns the hard checks. Among feasible candidates, the planner compares elapsed time, reserve margin, science priority, steep-terrain exposure and rover energy where available. It selects a nondominated science option by priority and then margin, or recommends direct return if no science option passes. If direct return fails the applicable gates, the recommendation is empty and the candidate retains its failure reasons. [Battery ledger](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/resources.py#L109) · [Rover alternatives](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/optimization.py#L144-L164) · [Walkback timing](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/walkback.py#L61-L99) · [Walkback consumables](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/tradeoff/walkback.py#L11) · [Candidate ranking](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/optimization.py#L297-L335)

## 3. Replanning when conditions change

An accepted mission report supplies an updated position and clock. Manual closures stay active until an explicit clear event for the same hazard. For an observed moving storm at or above the drill's wind threshold of 20 m/s or dust optical depth of 2, the planner extrapolates its centre along its reported velocity for up to 1,800 s from observation. It rasterises the swept footprint for the planning window, expanding the radius by half a cell diagonal. Both modes and the walkback graph use the resulting closure mask. When the storm report becomes stale, the planner retains the modelled sweep from the observation and blocks new science. The drill uses a 600 s observation freshness limit for station and spatial inputs. The station forecast is advisory. Observed wind warnings, radiation alerts and stale required station data can block science, while high or unknown station dust can remove solar credit. [Storm mask](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/hazards/planning.py#L68) · [Storm extrapolation](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/hazards/live.py#L278) · [Observed weather policy](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/weather.py#L179-L260)

The local API validates pack identity and expected mission revision before publishing a replacement. On expiry, the feeder can advance the clock using the last reported position and task state. This causes the planner to recheck staleness even while it waits for a new observation. The planner session is held in memory and the included feed replays a simulated report log. [Revision and publication](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/final_routing.py#L279-L302) · [Report feeder](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/routing_feed.py#L119)

## 4. Verification results

I replayed the bundled JSONL feed through the local HTTP API with the simulated station model. The starting position was cell `[36, 109]`, the shelter was `[80, 40]`, and the initial time budget and reserve were 5,400 s and 900 s. The values below are horizontal distance and modelled travel time for the **direct return**. The recommendation column shows the mission decision after dwell and reserve checks. Values are rounded to the nearest metre or second. [Bundled input log](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/examples/routing-feed-simulated.jsonl)

| Revision and event | Direct return distance, both modes (m) | Walking (s) | Rover (s) | Recommendation, both modes |
| --- | ---: | ---: | ---: | --- |
| 1 · Clear baseline | 436 | 867 | 291 | Transect |
| 2 · Storm report, same start cell | 1,070 | 2,216 | 714 | Transect |
| 3 · Required station data expire | 1,070 | 2,216 | 714 | Direct return |
| 4 · Spatial observation also expires | 1,070 | 2,216 | 714 | Direct return |
| 5 · Clear report and updated start cell | 431 | 859 | 288 | Transect |

At revision 2, the current storm mask covered 80 cells and the swept planning mask covered 1,624. The walking direct-return margin at revision 2 was $5{,}130-900-2{,}215.95=2{,}014.05$ s. At revision 3 the direct route stayed the same while stale weather made science ineligible. Revision 5 includes a move by one grid cell, which accounts for the shorter return compared with the initial clear baseline.

**386 focused tests passed** on Windows with the repo's locked environment, Python 3.12.10 and the pure-Python solver. The suites cover directional return calculations, corner cutting, closure replans, resource and walkback vetoes, stale inputs, and revision conflicts. The HTTP tests include a closed shelter that publishes no path and a low-oxygen case where a geometric path exists but both recommendations are withheld. [Graph tests](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/tests/test_marswalk.py#L219-L272) · [Integrated API tests](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/tests/test_final_routing.py#L84-L191) · [Feed tests](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/tests/test_routing_feed.py#L25-L90)

## 5. Limits on the conclusions

- **Minimum travel time applies to the modelled graph.** The mission checks run on the generated candidates. A slower walking route with less climbing could preserve more oxygen and pass when the fastest path fails. The bounded rover alternative search can also miss a feasible route, especially when the initial failure is a walkback violation. A refused recommendation means the tested candidates failed.
- **The storm mask is conservative within its motion model.** A crossing may be clear when the crew reaches it and still be removed for the entire revision. A poorly predicted storm direction or speed could put hazards outside the modelled sweep. Caution exposure is a diagnostic metric. The edge weights for the fastest path remain travel time.
- **Grid resolution limits the terrain claims.** The model uses adjacent elevations and local raster derivatives. The largest terrain gaps for rover use are unresolved obstacles, wheel slip, traction and sinkage. The pace, threshold and resource assumptions need calibration with representative terrain and instrumented traverses before route margins can support field decisions.
- **The response has inconsistent walkback metadata.** In the replay, `rover.walkback.policy` reports the 0.50 m/s pace passed to the solver. The generic core assumptions list still describes the default 0.75 m/s walkback. Reproduction should use the policy field. [Active walkback policy](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/final_routing.py#L347-L355) · [Core assumptions text](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/marswalk/plan.py#L34-L46)

## Reproduction

Use the integrated branch at the commit above. Train the synthetic station model, start the local API and run `python -m runtime.routing_feed` to replay the bundled log. [Runtime instructions](https://github.com/AbhimanthaW/Periapsis/blob/654cd57cb64406981a4cd9933f108a14ea2c2c88/runtime/README.md#integrated-routing-drill)

With the repo's locked environment configured, run the focused suite with PowerShell.

```powershell
uv run --project documentation --locked python -m pytest -q `
  runtime/tests/test_marswalk.py runtime/tests/test_marswalk_rover_env.py `
  runtime/tests/test_marswalk_site_walkback_weather.py runtime/tests/test_live_hazards.py `
  runtime/tests/test_final_routing.py runtime/tests/test_routing_feed.py `
  runtime/tests/test_humancost.py runtime/tests/test_tradeoff_envelope.py `
  runtime/tests/test_tradeoff_invariants.py runtime/tests/test_tradeoff_redteam.py
```
