# Return Window: flowcharts for the technical paper

Companion figures for *Return Window: Scientific evidence and return planning for a Mars EVA* (Team Periapsis, 15 November 2026).

Every chart was drawn from the code at `main@aa5537a`, the baseline the paper audits, and each one names the paper section and the source files it follows. Constants shown are the values in the code. Where the paper's wording and the code differ, the chart follows the code and the difference is listed in [Validation notes](#validation-notes).

Charts are Mermaid and render on GitHub.

| # | Chart | Paper section |
|---|---|---|
| 1 | [Two-decision workflow](#1-two-decision-workflow) | Decision and experimental design |
| 2 | [Evidence check and refusal](#2-evidence-check-and-refusal) | Arcadia Planitia: evidence and refusal |
| 3 | [Documentation score](#3-documentation-score) | Planetary data: documentation model |
| 4 | [Deterministic science ranking](#4-deterministic-science-ranking) | Planetary data: deterministic science ranking |
| 5 | [Terrain graph and edge cost](#5-terrain-graph-and-edge-cost) | Local mobility: terrain graph, walking, rover |
| 6 | [Search and selection](#6-search-and-selection) | Local mobility: search and selection |
| 7 | [Rover battery ledger and walkback](#7-rover-battery-ledger-and-walkback) | Local mobility: rover, search and selection |
| 8 | [Weather and moving hazards](#8-weather-and-moving-hazards) | Local mobility: weather and moving hazards |
| 9 | [Crew cost](#9-crew-cost) | Crew cost: human cost |
| 10 | [Trade-off envelope](#10-trade-off-envelope) | Crew cost: trade-off envelope |
| 11 | [Closure experiment](#11-closure-experiment) | Crew cost: closure experiment |
| 12 | [Station forecast](#12-station-forecast) | Weather models: station forecasts |
| 13 | [Regional dust outlook](#13-regional-dust-outlook) | Weather models: regional dust outlook |

---

## 1. Two-decision workflow

The paper's central claim: choose an observation the evidence supports, then compare routes against a return budget. The two decisions never share a score.

```mermaid
flowchart TD
    Q["Crew objective and exact area"] --> D1{"Decision 1<br/>Does archived evidence support<br/>the requested calculation?"}
    D1 -->|"No"| REF["Refuse the calculation<br/>Offer the declared coarse fallback<br/>Withhold tactical routing"]
    D1 -->|"Yes"| PACK["Qualified local evidence pack<br/>projected metre grid"]
    PACK --> D2{"Decision 2<br/>Can the task be done and<br/>shelter still be reached?"}
    D2 --> G["Directed terrain graph"]
    G --> S["Fastest out and return paths"]
    S --> V["Time, weather, energy<br/>and walkback vetoes"]
    V --> OUT["Recommend one science option<br/>or return now"]

    DISC["Regional discovery<br/>HEALPix cell ranking"] -.->|"suggests where to look"| Q
    WX["Weather models<br/>advisory only"] -.->|"never define closures"| V
    CREW["Crew cost and<br/>trade-off envelope"] -.->|"GREEN, AMBER or RED"| OUT
```

Arcadia Planitia stops at the refusal. The closure experiment in chart 11 runs decision 2 on a separate synthetic grid.

---

## 2. Evidence check and refusal

Sources: `pipeline/evidence/arcadia-planitia/`, `documentation/marsdoc/engine.py`, `runtime/marswalk/site.py`.

```mermaid
flowchart TD
    A["Query polygon, about 4 x 4 km<br/>centre 49.02 N, 171.85 W"] --> B["Pinned MOLA MEG004<br/>0.25 deg posts, about 14.8 km<br/>centre -4,036 m, count 555"]
    A --> C["Saved USGS CTX stereo catalogue search"]
    C --> C1{"Intersecting records?"}
    C1 -->|"Arcadia: 0"| R1["Local 20 m stereo elevation<br/>REFUSED"]
    C1 -->|"Jezero control: 24"| J["Verified CTX 20 m DTM window"]
    B --> F["Coarse context fallback<br/>ACCEPTED"]
    J --> K["Local elevation query<br/>SUPPORTED at requested posting"]

    R1 --> G0
    K --> G0
    subgraph G0 ["Site gate before any routing"]
        direction TB
        G1{"Eligible local<br/>terrain evidence?"} -->|"yes"| G2{"Native and grid<br/>posting at most 20 m?"}
        G2 -->|"yes"| G3{"Grid at most<br/>1,000,000 cells?"}
        G3 -->|"yes"| G4{"Analytical terrain<br/>payload present?"}
    end
    G1 -->|"no"| W["Tactical routing WITHHELD"]
    G2 -->|"no"| W
    G3 -->|"no"| W
    G4 -->|"no"| W
    G4 -->|"yes"| OK["Routing may run"]
```

A catalogue count is not a coverage claim. Passing the posting test does not establish effective resolution, obstacle clearance or route safety.

---

## 3. Documentation score

Source: `documentation/marsdoc/engine.py`, policy in `documentation/marsdoc/scoring-v1.json`.

```mermaid
flowchart TD
    P["Catalogue products over the window"] --> M["Group by modality<br/>4 terrain, 3 science and environment"]
    M --> U{"Native posting s<br/>against the modality ramp"}
    U -->|"s at most s_good"| U1["utility = 1"]
    U -->|"s at least s_poor"| U0["utility = 0"]
    U -->|"between"| UR["utility = log(s_poor / s) / log(s_poor / s_good)"]
    U -->|"posting unknown"| UB["bounds 0 to 1"]
    U1 --> SM
    U0 --> SM
    UR --> SM
    UB --> SM
    SM["Spatial maximum per modality<br/>integrate best utility at each location<br/>overlap earns no double credit"]
    SM --> LB["Lower bound<br/>verified usable support"]
    SM --> UPB["Upper bound<br/>possible or unsearched support"]
    LB --> AX["Weighted mean per axis, scaled 0 to 100"]
    UPB --> AX
    AX --> T{"Lower and upper bound<br/>in the same tier?"}
    T -->|"yes"| TC["Tier: Very Low, Low, Moderate,<br/>High or Very High<br/>boundaries at 20, 40, 60, 80"]
    T -->|"no"| TU["Unclassified"]

    E["Calculation eligibility<br/>is a separate test"] -.-> EE["Exact polygon or buffered route needs<br/>compatible usable support per variable"]
```

---

## 4. Deterministic science ranking

Sources: `ranking/lexicon.py`, `ranking/build.py`, `ranking/engine.py`, `ranking/risk.py`.

```mermaid
flowchart TD
    subgraph BUILD ["Build time, once per pack"]
        direction TB
        L["Layer rules give byte support 0 to 255<br/>and a covered mask per concept"] --> PR["Propagate child to broader concept at 0.8<br/>ice concepts excluded"]
        PR --> N["n_j = cells with covered support at least 128"]
        N --> WJ["w_j = round(65536 x a_j x ln(1 + (N - n_j + 0.5) / (n_j + 0.5)))<br/>a_j = 0.35 for age concepts, else 1<br/>N = 196,608"]
    end
    subgraph QUERY ["Query time"]
        direction TB
        O["Objective text"] --> PA["Lexicon parse: positive concepts<br/>and negations, 72-concept ledger"]
        PA --> AB{"Any concept<br/>recognised?"}
        AB -->|"no"| ABS["Abstain"]
        AB -->|"yes"| UJ["u_ji = covered exact support, or<br/>max with 0.35 x broader support"]
        UJ --> SC["S_i = sum over concepts of w_j x u_ji"]
        SC --> TI{"Present hits among<br/>selected concepts"}
        TI -->|"all"| DI["Direct"]
        TI -->|"some"| PT["Partial"]
        TI -->|"none, S_i above 0"| TH["Thematic"]
        DI --> EX
        PT --> EX
        TH --> EX
        EX["Remove requested exclusions<br/>and negated concepts"] --> BT["Keep the best tier available"]
        BT --> GR["Group by 8-neighbour adjacency<br/>split at Nside 32 tile boundaries"]
        GR --> RK["Rank areas by mean score"]
    end
    WJ --> SC
    RK --> TS["Separate terrain screen<br/>percent of evaluated cells with mapped<br/>mass-wasting or polar dunes<br/>no score when nothing was evaluated"]
```

Present, weak, absent and unreported or unevaluated stay distinct states. Record counts and method compatibility do not enter `S_i`.

---

## 5. Terrain graph and edge cost

Sources: `runtime/marswalk/traversability.py`, `routing.py`, `mobility.py`, `rover.py`.

```mermaid
flowchart TD
    Z["Elevation grid, validity mask,<br/>pack screen, authorised exclusions"] --> H["Horn 3 x 3 slope = atan of gradient magnitude<br/>only where all 9 cells are valid"]
    Z --> RG["Detrended relief about a fitted local plane<br/>RMS residual for roughness<br/>largest residual for rover clearance"]
    H --> CL["Classify each cell:<br/>routable, known excluded, or unknown"]
    RG --> CL
    CL --> ED["Directed edges, 4 or 8 neighbours<br/>no corner cutting through blocked cells"]
    ED --> MODE{"Platform"}

    MODE -->|"walking"| WS{"Edge grade or either end<br/>slope above the limit?"}
    WS -->|"yes"| WR["Edge refused"]
    WS -->|"slope unknown"| WU["Edge unsupported"]
    WS -->|"no"| WT["q = dz / l<br/>v = v_flat x exp(-3.5 x (abs(q + 0.05) - 0.05))<br/>t = l / v<br/>v_flat 0.50 m/s, slow scenario x 0.7"]

    MODE -->|"rover"| RS{"Grade or slope above 20 deg,<br/>or relief above 0.35 m?"}
    RS -->|"yes"| RR["Edge refused"]
    RS -->|"property unknown"| RU["Edge unsupported"]
    RS -->|"no"| RT["t = sqrt(l^2 + dz^2) / 1.5 m/s<br/>E = max(m g (dz + C_rr l), 0) / eta + P_aux t<br/>m 1,150 kg, g 3.721, C_rr 0.15,<br/>eta 0.70, P_aux 400 W"]

    WT --> OUT["Positive directed edge times<br/>rover edges also carry joules"]
    RT --> OUT
```

Uphill and downhill costs differ, so the graph is directed. Worked example: a 5 m edge rising 0.5 m takes 14.19 s uphill and 10.00 s in reverse. Downhill rover work earns no regeneration.

---

## 6. Search and selection

Sources: `runtime/marswalk/plan.py`, `optimization.py`, `resources.py`.

```mermaid
flowchart TD
    SNAP["Snapshot: position, shelter, tasks,<br/>remaining clock B, reserve R, closures"] --> RTR["Request graph = baseline graph minus closures"]
    RTR --> D1["Dijkstra forward from the crew cell<br/>gives outbound legs"]
    RTR --> D2["Dijkstra from shelter on the transposed graph<br/>gives correctly directed return times"]
    D1 --> CAND
    D2 --> CAND
    CAND["Candidates:<br/>return now, always present<br/>out, dwell, return per unfinished task<br/>bounded two-task sequences"] --> LED["Time ledger per phase<br/>margin = B - R - elapsed<br/>checked after every phase"]
    LED --> HC{"Hard constraints"}
    HC --> C1["Positions supported"]
    HC --> C2["Path exists on verified terrain"]
    HC --> C3["Prerequisites met"]
    HC --> C4["Time budget"]
    HC --> C5["Weather and environment"]
    HC --> C6["Rover only: energy and walkback"]
    C1 --> DR
    C2 --> DR
    C3 --> DR
    C4 --> DR
    C5 --> DR
    C6 --> DR
    DR{"Direct return<br/>passes?"}
    DR -->|"no"| NONE["No recommendation<br/>status names the failing gate"]
    DR -->|"yes"| PF["Pareto front over passing plans:<br/>total time, margin, task priority,<br/>steep exposure, energy"]
    PF --> SEL{"Science plan on the front<br/>and crew status ok?"}
    SEL -->|"yes"| BEST["Pick by priority, then margin, then id"]
    SEL -->|"no"| HOME["Recommend return now"]
```

An unknown required value blocks a plan; it is never defaulted. A rejected candidate does not prove that every slower route fails.

---

## 7. Rover battery ledger and walkback

Sources: `runtime/marswalk/resources.py` (`energy_ledger`), `runtime/marswalk/walkback.py`.

```mermaid
flowchart TD
    subgraph BAT ["Battery ledger, per edge and per dwell"]
        direction TB
        B0["Charge starts at 16 kWh<br/>capacity 20 kWh, floor 4 kWh"] --> B1["Subtract phase consumption"]
        B1 --> B2{"Mean discharge power<br/>at most 4 kW?"}
        B2 -->|"no"| BF["FAIL: discharge power exceeded"]
        B2 -->|"yes"| B3{"Charge still at or<br/>above the floor?"}
        B3 -->|"no"| BF2["FAIL: reserve breached"]
        B3 -->|"yes"| B4["Credit declared or modelled supply"]
        B4 --> B5["Cap charge at capacity"]
        B5 -->|"next phase"| B1
    end
    subgraph WB ["Walkback check for every rover plan"]
        direction TB
        W0["Third Dijkstra from shelter on the walking graph<br/>0.75 m/s flat pace, 15 deg limit"] --> W1["T_walk for every cell"]
        W1 --> W2["For each cell x on the rover route<br/>and after each dwell, elapsed time tau_x"]
        W2 --> W3{"T_walk finite?"}
        W3 -->|"no"| WF["FAIL: no walkable route home"]
        W3 -->|"yes"| W4{"tau_x + T_walk at most B - R<br/>at every point?"}
        W4 -->|"no"| WF2["FAIL: walkback exceeds budget"]
        W4 -->|"yes"| WP["PASS: report the tightest cell"]
    end
    BF --> ALT["Bounded search over time and energy<br/>weighted alternative legs"]
    BF2 --> ALT
```

Missing consumption or supply makes the ledger unknown. High observed dust removes solar credit before the ledger runs.

---

## 8. Weather and moving hazards

Sources: `runtime/marswalk/weather.py`, `runtime/hazards/live.py`, `route.py`, `monitor.py`.

```mermaid
flowchart TD
    MSG["Timestamped message"] --> K{"Kind"}
    K -->|"forecast"| ADV["Advisory only<br/>never changes the plan"]
    K -->|"observed"| FR{"Fresh and in range?"}
    FR -->|"no"| ST["Stale or rejected<br/>can stop science, restrictions stay"]
    FR -->|"yes"| LV{"Level"}
    LV -->|"wind at least 20 m/s<br/>or particle event alert"| RN["Stop science: return now"]
    LV -->|"optical depth at least 2"| NS["Remove solar credit"]
    LV -->|"wind at least 15 m/s<br/>or optical depth at least 1"| CA["Caution shown to crew"]
    LV -->|"below caution"| NO["Nominal"]

    subgraph MOV ["Synthetic moving-hazard backend"]
        direction TB
        S0["Observed storm centre x0, velocity v"] --> S1["Position = x0 + v x dt<br/>carried forward at most 1,800 s"]
        S1 --> S2["Close cells blocked now and plan"]
        S2 --> S3["Check each route cell at its arrival time t<br/>window = max(60 s, 0.2 x t)"]
        S3 --> S4{"Hazard inside<br/>the window?"}
        S4 -->|"yes, retries left"| S5["Close that footprint and replan"]
        S5 --> S3
        S4 -->|"yes, retries used"| S6["Close the union of hazards<br/>over the lookahead and plan once more"]
        S4 -->|"no"| GO["Route accepted"]
        S6 --> S7{"Return route exists?"}
        S7 -->|"yes"| GO
        S7 -->|"no"| S8{"Reachable cell that<br/>stays clear?"}
        S8 -->|"yes"| HOLD["Move to hold cell, alert base"]
        S8 -->|"no"| WH["Withhold movement"]
    end
```

No live Mars feed is shipped. The moving-hazard backend is separate from the scripted replay in chart 11.

---

## 9. Crew cost

Source: `runtime/humancost/calculator.py`, policy in `runtime/examples/human-cost-policy.json`.

```mermaid
flowchart TD
    IN["Per astronaut, per ordered phase<br/>duration t, positive climb H<br/>dwell uses H = 0"] --> W["Mechanical work<br/>W = m g_M H"]
    W --> E["Metabolic energy<br/>E = (P0 + P_joint / eta_h) t + W / eta_h"]
    E --> Q["Heat to reject<br/>Q = E - W + P_ext t, P_ext 25 W"]
    E --> O2["Oxygen, Weir<br/>V = E / (4184 x (3.941 + 1.106 RER)) litres<br/>mass = 31.998 / 22.414 x V grams"]
    Q --> CW["Cooling water = Q / 2.4 MJ/kg"]
    IN --> DW["Drinking water = declared L/h x t / 3600"]
    Q --> BA["Suit battery = (115 W x t + 0.12 x Q) / 3600 Wh"]
    O2 --> CO["CO2 produced = V x RER x 44.01 / 22.414 g<br/>excess = production minus declared removal"]

    O2 --> CK
    CW --> CK
    DW --> CK
    BA --> CK
    CK{"After each phase"}
    CK --> K1["Each resource at or above its floor"]
    CK --> K2["Phase slope within the personal limit"]
    CK --> K3["Mean phase power within declared peak"]
    K1 --> RES
    K2 --> RES
    K3 --> RES
    RES{"Any breach?"}
    RES -->|"yes"| F["Fail at the first breaching phase and resource"]
    RES -->|"no"| P["Pass: report the driving resource<br/>and utilisation band"]
    P --> FL["Route-level flags:<br/>workload above sustainable<br/>CO2 above declared removal"]
```

CO2 excess is a mass balance, not suit CO2 partial pressure. Heart rate, suit temperature and visibility readings are informational.

---

## 10. Trade-off envelope

Sources: `runtime/tradeoff/envelope.py`, `classify.py`, `accept.py`, `audit.py`.

```mermaid
flowchart TD
    OPT["Option with its crew-cost ledgers"] --> MF["Scale cumulative use by margin factor f<br/>f = 1.30 in the preset"]
    MF --> PRE["For every astronaut, resource r and phase prefix k:<br/>I_r - f x sum of U_ir up to k"]
    PRE --> HARD{"All planner hard<br/>constraints pass?"}
    HARD -->|"no"| RED["RED<br/>with the first failing rule"]
    HARD -->|"yes"| L1{"Every prefix at or above<br/>nominal floor L1?"}
    L1 -->|"yes"| GREEN["GREEN"]
    L1 -->|"no"| RN{"Is the option<br/>return now?"}
    RN -->|"yes"| RED
    RN -->|"no"| EXC{"Pre-signed exception for<br/>this science class?"}
    EXC -->|"no"| RED
    EXC -->|"yes"| L2{"Every prefix at or above<br/>relaxed floor L2?<br/>L2 never below L0, 10 percent<br/>drinking water has no exception"}
    L2 -->|"no"| RED
    L2 -->|"yes"| GATES{"All AMBER gates open?<br/>return is GREEN<br/>weather assessed, no warning<br/>telemetry fresh and plausible<br/>envelope unexpired<br/>authority reachable<br/>exception count remains"}
    GATES -->|"no"| RED
    GATES -->|"yes"| AMBER["AMBER<br/>needs acceptance"]
    AMBER --> ACC["Role checks and crew consent, no veto<br/>remote authority must fit the decision window<br/>after round trip and response allowance,<br/>else the habitat delegate"]
    ACC --> AUD["Scoped, expiring, withdrawable acceptance<br/>written to a verifiable audit chain"]
```

The module estimates no breach probability and approves no real EVA.

---

## 11. Closure experiment

Sources: `runtime/hazards/replay.py`, bundled data in `web/mission-preview/src/hazards/replay.json`. Synthetic 160 x 160 grid at 5 m posting. Clock starts at 5,400 s with a 900 s reserve. Path A is 436 m, path B is 834 m.

```mermaid
stateDiagram-v2
    direction TB
    [*] --> Clear
    Clear: Clear, clock 0 s
    Clear: Route A open. Walk 867 s, margin 3,633 s. Rover 291 s, margin 4,209 s
    Caution: Caution, clock 90 s
    Caution: A crosses 42 m of footprint, B crosses 0 m
    Caution: Walk A 867 s or B 1,773 s. Margins 3,543 s or 2,637 s
    Closure: Closure, clock 270 s
    Closure: A blocked. Walk B 1,773 s, margin 2,457 s. Rover 557 s, margin 3,673 s
    Stale: Stale, clock 871 s
    Stale: Closure kept, new approvals suspended
    Stale: Walk B margin 1,856 s. Rover margin 3,072 s
    Reopened: Reopened, clock 1,110 s
    Reopened: A available again. Walk 867 s, margin 2,523 s. Rover 291 s, margin 3,099 s

    Clear --> Caution: dust pocket reaches the northern crossing
    Caution --> Closure: optical depth 2.4 passes the warning limit of 2
    Closure --> Stale: last dust message older than 600 s
    Stale --> Reopened: fresh reading, optical depth 0.68
    Reopened --> [*]: display keeps the approved route
```

The bundle has six frames; the frame at 180 s repeats the caution state with slightly higher dust and is omitted here, as in the paper's table. Each margin is `5,400 - 900 - clock - travel`.

---

## 12. Station forecast

Sources: `pipeline/src/return_window_pipeline/forecast/model.py`, `station.py`, `marstime.py`.

```mermaid
flowchart TD
    OBS["Quality-screened station samples<br/>pressure, air temperature, wind, dust optical depth"] --> GRID["24 local-time bins per sol<br/>with solar longitude Ls"]
    GRID --> SPLIT["Chronological blocks with one-sol gaps<br/>train, calibration, selection, test"]
    SPLIT --> CLIM["Clock baseline C<br/>bin means in circular Ls windows<br/>plus or minus 10 deg, centres every 5 deg, interpolated"]
    CLIM --> BASE{"Kit includes the<br/>target sensor?"}
    BASE -->|"yes"| AP["b = C(t + h) + (y_t - C(t))<br/>anomaly persistence"]
    BASE -->|"no"| CO["b = C(t + h)"]
    AP --> RIDGE
    CO --> RIDGE
    RIDGE["Ridge correction per kit, target and horizon<br/>standardised features, lambda = 1, free intercept<br/>anomalies and tendencies over 3 bins<br/>sine and cosine of target time and Ls"]
    RIDGE --> CAL["Calibration block residuals<br/>give P10, P50, P90 offsets"]
    CAL --> SELK["Selection block: fewest sensors with<br/>competitive skill and band coverage"]
    SELK --> INF{"At inference:<br/>features present and in range?"}
    INF -->|"yes"| FC["Forecast at +1, +3, +6 Mars hours<br/>with P10 to P90 band"]
    INF -->|"no"| FB["Lower-ranked kit, then climatology,<br/>or abstain on thin support"]
    FC --> USE["Advisory display only<br/>never defines a corridor closure"]
    FB --> USE
```

Synthetic-station result quoted in the paper: 630, 157, 103 and 157 sols by block; six-hour pressure with the barometer kit has test MAE 2.688 Pa against 2.961 Pa for the best baseline, with 83.1 percent band coverage over 3,577 bins. A Mars hour is 88,775.244 s / 24.

---

## 13. Regional dust outlook

Sources: `pipeline/src/return_window_pipeline/dust/extract.py`, `model.py`, manifest in `pipeline/evidence/mdad-v1.1/`.

```mermaid
flowchart TD
    MD["MDAD v1.1 daily storm masks<br/>Mars years 28 to 32"] --> FP["Per region and sol: storm fraction of observed pixels<br/>core disc 100 km, ring out to 800 km"]
    FP --> AN{"Anchor sol has at least<br/>50 percent core coverage?"}
    AN -->|"no"| DROP["Sample dropped"]
    AN -->|"yes"| LAB{"At least 5 of the next<br/>7 sols observed?"}
    LAB -->|"no"| DROP
    LAB -->|"yes"| Y["Label = 1 if any observed sol has a mapped storm<br/>over at least 10 percent of core pixels"]
    Y --> CL["Seasonal baseline<br/>event rate in a circular plus or minus 15 deg Ls window<br/>shrunk toward the pooled seasonal rate"]
    CL --> LOG["L2 logistic model fitted by IRLS<br/>inputs: baseline logit, core and ring coverage<br/>now and recent, missing-ring flag, season harmonics"]
    LOG --> CV["Leave one Mars year out<br/>baseline and model refitted without that year"]
    CV --> G1{"Pooled Brier skill<br/>1 - BS_model / BS_clim<br/>at least 0.02 and positive<br/>in most held-out years?"}
    G1 -->|"no"| CLO["Show climatology only"]
    G1 -->|"yes"| G2{"Independent storm-outline check<br/>agrees with the NetCDF<br/>coordinate reading?"}
    CLO --> G2
    G2 -->|"no, all five years"| WH["WITHHELD<br/>no regional probabilities published"]
    G2 -->|"yes"| PUB["Publish as historical<br/>conditional context"]
```

The current release takes the withheld branch. Ring features are used only when at least 30 percent of ring pixels were observed.

---

## Validation notes

The paper's equations, constants and reported numbers were checked against `main@aa5537a`. The uploaded archive is byte-identical to that commit apart from Python cache folders.

**Confirmed against the code and by independent recomputation**

- Scaled Tobler pace and the worked example (14.19 s up, 10.00 s down).
- Rover time and energy equations and every hypothetical-profile value.
- Horn slope, detrended roughness and clearance proxy, site-gate limits.
- Dijkstra on forward and transposed graphs, margin `B - R - elapsed`, Pareto objectives, selection order.
- Battery ledger order of operations and the walkback inequality with 0.75 m/s and 15 degrees.
- Weather thresholds, 1,800 s extrapolation, `max(60 s, 0.2t)` window.
- Crew-cost equations including the Weir conversion and all four consumables.
- Envelope prefix inequality, margin factor 1.30, L0 at 10 percent.
- All ten closure-table values regenerate from the runtime and match a by-hand re-timing of both paths.
- HEALPix count and cell area, IDF weight formula, 0.35 age multiplier, 128 of 255 threshold, 72 concepts.
- Documentation utility ramp, forecast baseline and ridge setup, dust label and release gate.
- All quoted data values: Arcadia MOLA sample, catalogue counts 0 and 24, MEDA sol 36, Horizons light-time, RAD dose rate, synthetic forecast metrics.

**Differences between the paper and the code**

| # | Paper says | Code does | Suggested fix |
|---|---|---|---|
| 1 | One symbol `g_M`, given as 3.721 m/s2 in the rover paragraph and reused in the crew-cost equation | Rover uses 3.721 (`runtime/marswalk/rover.py`). Crew cost and the EVA context fixture use 3.71 (`human-cost-policy.json`, `scenario-v1.json`) | State both values, or align the policy files to 3.721. The effect on crew work is 0.3 percent |
| 2 | `u_ji` is exact covered support, or the larger of it and 35 percent of broader support | Also true, but the stored support already includes a build-time step that lifts each broader concept to 0.8 of its child, sedimentary to 0.6 of polar deposits, and sets habitability to the smaller of water and age support (`ranking/build.py`, `propagate`). `n_j` is counted after this step | Add one sentence on build-time propagation |
| 3 | Clock baseline uses plus or minus 10 degree Ls windows | Same, and it widens to 20 degrees, 40 degrees, then an all-season mean when a window has too few samples (`forecast/model.py`, `Climatology`) | Mention the fallback |
| 4 | Areas are ranked by mean score | Integer floor of the mean, ties broken by cell count then lowest cell index | Optional footnote for reproducibility |

None of these changes a number reported in the paper.

**Not reproduced here**

The paper's test counts (574 passed and 10 skipped, 28 ranking tests, 12 branch tests) could not be re-run in full: the check environment lacked `shapely`, `pyproj`, `affine` and the ranking input assets. Of the tests that could be collected, 355 passed, and every failure was a missing-package import. The `feature/final-routing-integration@2dd7388` branch was not examined.
