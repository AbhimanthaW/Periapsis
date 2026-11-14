import { emptyAlgorithm, newComponent, newParameter, newVariable } from './schema'
import type { Algorithm, Architecture, Component, Connection, Group, ModelReview, Parameter, Reference, Variable } from './schema'

const physics = 'A · Physics, mobility & routing'
const planning = 'B · Science, optimization & decision intelligence'
const shared = 'Shared · Physics + planning'
const reviewDoc: Reference = {label:'Scientific Model Design Review',url:'',locator:'docs/scientific-model-design-review.md',evidenceType:'Design and regional research audit',verification:'Proposed specifications; scientific validation pending.'}
const reference = (label:string,url:string,evidenceType='Primary technical reference'): Reference =>
  ({label,url,locator:'',evidenceType,verification:'Source reviewed for applicability. Return Window model validation pending.'})
const refs = {
  eva:reference('NASA lunar science optimization proof of concept','https://ntrs.nasa.gov/citations/20240000165','Analog planning precedent'),
  rover:reference('JPL terrain-adaptive rover navigation','https://ntrs.nasa.gov/citations/20070034772'),
  traction:reference('Curiosity traction control design','https://ntrs.nasa.gov/citations/20210007638'),
  dtm:reference('USGS Jezero stereo DTM quality','https://www.usgs.gov/publications/evaluating-stereo-dtm-quality-jezero-crater-mars-hrsc-ctx-and-hirise-images'),
  crs:reference('USGS planetary projection conventions','https://astrogeology.usgs.gov/docs/concepts/camera-geometry-and-projections/learning-about-map-projections/'),
  meda:reference('NASA PDS MEDA observations','https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/retrieving_mars2020.html','Historical observation archive'),
  rad:reference('NASA PDS MSL and RAD archive','https://pds-geosciences.wustl.edu/missions/msl/','Historical observation archive'),
  sun:reference('JPL NAIF SPICE illumination','https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/IDL/icy/cspice_illumf.html'),
  stm:reference('NASA Science Traceability Matrix','https://hesto.smce.nasa.gov/focused-topics/'),
  spoc:reference('NASA/JPL SPOC terrain classification research','https://ntrs.nasa.gov/citations/20200000183','Research prototype'),
  graph:reference('SciPy directed Dijkstra','https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.dijkstra.html'),
  yen:reference('SciPy Yen loopless paths','https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.yen.html'),
  dstar:reference('Koenig and Likhachev, D* Lite','https://publications.ri.cmu.edu/d-lite'),
  rcsp:reference('Irnich and Desaulniers, resource-constrained paths','https://www2.imm.dtu.dk/courses/02735/rcsppchapter.pdf'),
  mer:reference('NASA Opportunity mission','https://science.nasa.gov/mission/mer-opportunity/','Comparative field evidence'),
  spirit:reference('NASA Spirit mission','https://science.nasa.gov/mission/mer-spirit/','Comparative field evidence'),
  places:reference('PDS Mars 2020 PLACES','https://pds.nasa.gov/ds-view/pds/viewBundle.jsp?identifier=urn:nasa:pds:mars2020_rover_places','Historical pose archive'),
}
const family = (id:string,name:string,summary:string,description:string,tone:Group['tone']='data'): Group =>
  ({id,name,summary,description,tone,phase:id==='uncertainty'?'assurance':'runtime'})
const families = [
  family('mission-models','Mission configuration','Profiles · scope · limits','Versioned mission state, tagged human/rover profiles, authorized constraints and distinct scenario/evidence inputs.','neutral'),
  family('geometry','Planetary geometry','Mars CRS · elevation · grade','Canonical pack geometry and local directed edge quantities. Geographic distance is for discovery; only valid local analytical geometry feeds detailed paths.'),
  family('surface','Traversability','Support · scale · exclusions','Coverage, resolution, supported derived roughness and mapped exclusions. Qualitative surface interpretation never supplies an uncalibrated cost.','constraint'),
  family('human-mobility','Human Marswalk','Directional pace · crew limits','Transparent illustrative walking time and authorized constraints, without physiological or individual health predictions.'),
  family('rover-mobility','Rover mobility','Vehicle limits · energy','Vehicle-specific feasibility, effective speed and electrical accounting. Quantitative wheel-ground mechanics require relevant data and validation.'),
  family('environment','Environmental models','Historical · scenario · enabled','Historical and simulated inputs are marked. Each environmental model needs purpose, valid domain and input evidence before affecting constraints.'),
  family('resources','Resource budgets','Outbound · dwell · return','Separate time, energy and authorized consumables with return reserves and prefix checks where required.','constraint'),
  family('science-models','Science value & tasks','Objectives · methods · evidence','Shared regional screening and evidence contracts, mission-specific priorities, prerequisites and distinct feature/approach/remote observation locations.'),
  family('replan','Dynamic replanning','Revision · closure · contingency','Validate updates, invalidate stale options and re-evaluate paths, budgets and science from the current state.','constraint'),
  family('uncertainty','Uncertainty & sensitivity','Evidence limits · abstention','Separate evidence gaps, model and scenario uncertainty. Scenario bounds and reason codes can limit or withhold recommendations.','constraint'),
  family('explanation','Decision explanation','Trade-offs · audit · UI','Show current feasible options, rejected alternatives, evidence, resource margins and changes from the previous plan.','decision'),
]

const additions: Component[] = []
type Spec = {
  group:string; id:string; name:string; tech:string; method:string; limits:string; test:string;
  owner?:string; priority?:Component['priority']; classification?:Component['classification']; category?:Component['category'];
  decision?:ModelReview['decision']; evidence?:Reference[]; availability?:string; difficulty?:string; value?:string;
  formula?:string; variables?:string; assumptions?:string; edgeCases?:string; alternatives?:string; complexity?:string; params?:Parameter[];
}
const model = (s:Spec) => {
  const category = s.category ?? 'Scientific model'
  const algorithm: Algorithm = {...emptyAlgorithm,name:s.name,family:s.tech,method:s.method,limitations:s.limits,validation:s.test,
    formula:s.formula ?? '',variables:s.variables ?? '',assumptions:s.assumptions ?? '',edgeCases:s.edgeCases ?? '',
    alternatives:s.alternatives ?? '',complexity:s.complexity ?? '',
  }
  const quantitative = category === 'Scientific model' || category === 'Algorithm'
  additions.push({
    ...newComponent(s.id,s.group,category,s.name),technology:[s.tech],purpose:s.value ?? s.name,description:s.method,
    classification:s.classification ?? 'Derived',priority:s.priority ?? 'P0',owner:s.owner ?? physics,risks:s.limits,
    ...(quantitative ? {algorithm} : {notes:s.test}),
    parameters:s.params ?? [],references:[reviewDoc,...(s.evidence ?? [])],
    review:{decision:s.decision ?? 'Proposed',foundation:s.evidence?.map(source=>source.label).join(' · ') || 'Return Window architecture and engineering design review',
      availability:s.availability ?? 'Requires the declared, versioned input contract. End-to-end execution not evaluated.',
      value:s.value ?? s.name,difficulty:s.difficulty ?? 'Moderate · verify against fixtures and applicable source data.',
      validationStatus:'Not evaluated',uncertainty:s.limits},
  })
}
const p = (name:string,symbol:string,unit:string,constraints:string,description:string,source='Authorized mission profile or explicit scenario'): Parameter =>
  ({...newParameter(),name,symbol,type:'number',unit,constraints,description,source,defaultValue:'TBD',scientificStatus:'Uncalibrated / not evaluated',provenance:'Assumption'})

model({group:'mission-models',id:'mission-snapshot',name:'Mission snapshot',tech:'Versioned scenario contract',category:'Backend service',owner:shared,classification:'Assumption',decision:'Adopted',
  method:'Freeze mission_id, region_id, pack and config versions, platform, objective, start/current and return locations, candidate destinations, completed task IDs, available budgets, authorized restrictions, evidence IDs, scenario ID and state revision. A request evaluates one immutable snapshot.',
  limits:'Unknown required values are not defaults. A simulated event is labeled and cannot overwrite source evidence.',
  test:'Reject mixed pack, bad positions, invalid units, negative reserves, invalid profiles and stale revisions.'})
model({group:'mission-models',id:'human-profile',name:'Human operating profile',tech:'Pace · duration · authorized limits',classification:'Assumption',decision:'Adopted',
  method:'Use a tagged human profile for baseline walking pace, directional penalties, mission time, required return reserve, authorized consumables and operating restrictions. The authorized operator supplies limits; model estimates do not assign personal medical suitability.',
  limits:'The demo pace and thresholds are illustrative; no physiological extrapolation.',
  test:'Check units, authorization and positive pace. Missing required consumables trigger abstention.',
  params:[p('Base pace','v','m/s','v > 0','Scenario baseline human pace.'),p('Required return-time reserve','R_t','s','R_t ≥ 0','Authorized remaining time after return.')]})
model({group:'mission-models',id:'rover-profile',name:'Rover operating profile',tech:'Tagged vehicle · power source',classification:'Assumption',decision:'Adopted',evidence:[refs.rover,refs.traction],
  method:'Use a hypothetical or explicitly sourced vehicle record with mass, wheel geometry, suspension/mobility, clearance, payload, incline limits, nominal speed, wheel-ground assumptions, source type, capacity, charge/discharge power and reserve. Generic, solar and non-solar profiles share this shape; generation remains conditional.',
  limits:'No assumed equivalence to NASA rover specs. Absent operating limits or power inputs block dependent claims.',
  test:'Validate tagged variants, mass/speed/efficiency units, energy versus power and explicit unknowns.',
  params:[p('Vehicle mass','m','kg','m > 0','Total modeled vehicle including payload.'),p('Effective segment speed','v_eff','m/s','v_eff > 0','Profile- and terrain-dependent scenario speed.'),p('Allowable inclination','θ_max','deg','Profile-authorized, per direction where applicable','Threshold requires scale and operating context.'),p('Usable storage','E_cap','J','E_cap ≥ E_initial ≥ 0','Available energy bound, distinct from power.'),p('Energy reserve','R_E','J','0 ≤ R_E ≤ E_cap','Required energy at return or stricter declared prefix rule.')]})
model({group:'mission-models',id:'operator-limits',name:'Authorized operating limits',tech:'Rules · scope · provenance',classification:'Assumption',owner:shared,
  method:'Record who authorized each hard restriction, its units, effective window, applicability, geographic scope and source. Distinguish operator rules from advisory context. Require explicit resolution of conflicting rules before generating a recommendation.',
  limits:'No medical suitability classification, automated crew ranking or delegated moral decision.',
  test:'Expired, contradictory and unsigned limits are rejected when required.'})

model({group:'geometry',id:'planet-distance',name:'Planetary distance',tech:'Declared Mars geodesic',evidence:[refs.crs],
  method:'Use the declared spherical or ellipsoidal Mars body and normalized coordinates for global discovery. Use the approved regional projected plane for local edge lengths. Preserve both units and scale validity.',
  limits:'No Earth CRS default. Geographic estimates cannot substitute for a supported regional grid.',
  test:'Check polar, wrapped, coincident and known control pairs against independent Mars geodesics.',
  alternatives:'Spherical great circle only with a documented spherical approximation.'})
model({group:'surface',id:'resolved-scale',name:'Terrain scale and support',tech:'Native vs analytical resolution',evidence:[refs.dtm],decision:'Adopted',
  method:'Record native post spacing, supported feature scale, masks, seams, observation footprint and analytical grid spacing from the validated pack. Keep unknown support separate from known exclusions.',
  limits:'Fine output spacing, CTX imagery and MOLA context do not supply missing fine elevation or resolved obstacles.',
  test:'Use coarse-only, seam, interpolation, partial support and unresolved scale fixtures.'})
model({group:'surface',id:'roughness',name:'Scale-aware roughness',tech:'Local detrended residuals',priority:'P1',decision:'Data dependent',evidence:[refs.dtm,refs.rover],
  method:'When native support and effective resolution justify it, fit a local reference plane and summarize the residual spread over a declared window. Record kernel support and window scale. Keep qualitative roughness descriptors as evidence notes.',
  formula:'R_q = sqrt(mean(r_i²)); r_i = z_i − fitted_plane(x_i,y_i)',
  variables:'R_q and r_i in metres. Window declared in metres and samples.',
  limits:'Does not estimate sub-pixel hazards, foothold quality, traction or slip.',
  test:'Flat and tilted planes, known perturbation, missing window samples and sensitivity to window scale.',
  params:[p('Roughness window','W','m','Window must exceed verified effective scale','Choose from supported native samples.','Pinned terrain processing configuration')]})
model({group:'surface',id:'surface-evidence',name:'Characterize surface evidence',tech:'Landforms · evidence and unknowns',priority:'P1',decision:'Proposed',classification:'Interpretation',evidence:[refs.dtm,refs.rover],
  method:'Compile source-backed polygons or observations for dunes, fractured rock, scarps, regolith, frost and suspected obstacles. Tag source type, native scale, uncertainty and applicable epoch. Derive scale-supported roughness and mapped dimensions only when evidence permits; otherwise keep an interpretive flag or unknown.',
  limits:'Surface class does not provide a traction, slip or sinkage coefficient. Combine only documented geometry and authorized policy for hard exclusions.',
  test:'Check conflicting sources, mixed pixels, time-varying frost, unverified obstacle dimensions and unknown classifications.'})
model({group:'surface',id:'barrier-mask',name:'Obstacles and exclusions',tech:'Known · unknown · excluded',classification:'Decision',decision:'Adopted',
  method:'Intersect reviewed mapped obstacles, operator exclusions and policy thresholds with supported analytical cells and edges. Distinguish known obstacles, insufficient evidence and conditional flags. Closures are applied separately at request time.',
  limits:'Mapped dunes, frost, rock abundance, fractures or geology indicate potential concerns; they do not alone prove passability, obstacle dimensions or calibrated cost.',
  test:'Check off-grid polygons, boundary overlap, mixed validity, known barriers and conservative diagonal masking.'})

model({group:'rover-mobility',id:'rover-travel',name:'Rover traversal time',tech:'Inclination · clearance · speed',classification:'Assumption',evidence:[refs.rover,refs.traction],
  method:'Check vehicle-specific terrain limits against supported directional inclination and obstacle geometry. If applicable evidence and authorized assumptions exist, use a strictly positive effective segment speed to estimate duration. Keep the human pace model independent.',
  formula:'s = hypot(d, Δz); t_edge = s / v_eff',variables:'d horizontal length, Δz rise and s segment length in metres; v_eff in m/s; t in seconds.',
  limits:'Slip, sinkage, speed and clearance depend on configuration and terrain. Geometry cannot establish traction or braking limits.',
  test:'Check finite time, zero/negative speed rejection, asymmetry, missing clearance evidence and invalid slopes.'})
model({group:'rover-mobility',id:'rover-energy',name:'Rover drive energy',tech:'Mechanical work → electrical J',classification:'Assumption',evidence:[refs.rover,refs.traction],
  method:'Estimate uphill work, rolling resistance and drivetrain losses, then add time-dependent auxiliary electrical loads. Downhill net-negative drive work is clipped to zero; regeneration is not credited. Compute stationary science energy from its own duration/load.',
  formula:'E_drive = max(0, m·g_Mars·Δz + F_rr·s) / η; E_edge = E_drive + P_aux·t; E_dwell = P_task·t_dwell',
  variables:'m kg; g_Mars m/s²; Δz and s m; F_rr N; η dimensionless; P W; t s; E J.',
  assumptions:'Steady segment approximation, prescribed rolling resistance, no regeneration. Power checks need a declared load model; E/t is only an average.',
  edgeCases:'Reject η ≤ 0 or > 1 and negative loads; handle stationary dwell without dividing by travel time.',
  limits:'No calibrated wheel-ground, braking, acceleration, thermal or battery model. Require declared coefficients and scope for numerical use.',
  test:'Flat, uphill, downhill, dwell and dimensional checks. Verify reserves, peak power and energy separately.',
  params:[p('Rolling resistance force','F_rr','N','F_rr ≥ 0','Scenario estimate with terrain and vehicle scope.'),p('Drive efficiency','η','1','0 < η ≤ 1','Scenario electrical-to-mechanical efficiency.'),p('Auxiliary load','P_aux','W','P_aux ≥ 0','Drive auxiliary draw; dwell modeled separately.'),p('Mars gravity','g_Mars','m/s²','g_Mars > 0','Use a declared body gravity approximation.','Pinned Mars body model')]})
model({group:'rover-mobility',id:'wheel-ground',name:'Traction, slip & sinkage',tech:'Instrumented calibration required',priority:'P2',decision:'Research required',evidence:[refs.rover,refs.traction],
  method:'Investigate calibrated terramechanics or bounded empirical response by wheel geometry, load and surface condition. Require relevant terrain measurements, matched vehicle trials and held-out site data. Baseline uses authorized limits and explicitly scoped assumptions.',
  limits:'No ground-truth mobility labels in the regional survey. No universal coefficients from orbital geology.',
  test:'Evaluate transfer across terrain and platforms, out-of-domain behavior and failure cases.',
  availability:'Operationally matched wheel–soil data and calibrated parameters TBD.'})
model({group:'routing',id:'mobility-interface',name:'Shared mobility contract',tech:'Tagged per-edge results',owner:shared,decision:'Adopted',
  method:'Select exactly the model matching the mission platform. Emit distance, duration, admissibility, applicable constraints, resource vector where supported, profile/revision IDs, evidence and reason codes. Keep unsupported metrics null. Use one valid nonnegative scalar per shortest-path search.',
  limits:'Human and rover are distinct evaluations. A generation credit never becomes a negative graph weight.',
  test:'Reject mixed profile legs, incompatible units, unsupported required quantities and invalid weights.'})

model({group:'environment',id:'environment-history',name:'Historical weather & RAD',tech:'MEDA · RAD · scoped observations',classification:'Observation',priority:'P2',decision:'Data dependent',evidence:[refs.meda,refs.rad],
  method:'Read pinned observations with time, location, sensor, unit and uncertainty. Historical pressure, wind, temperature, dust and radiation remain local context unless a supported scenario or model has been independently activated.',
  limits:'No live weather or geographic human dose inference. A dose scenario requires exposure time, spectrum, shielding and geometry.',
  test:'Reject out-of-period, missing coverage and incompatible units; confirm history is never mislabeled forecast.'})
model({group:'environment',id:'illumination',name:'Solar geometry & shadow',tech:'Pinned ephemeris · terrain horizon',priority:'P1',decision:'Data dependent',evidence:[refs.sun],
  method:'Compute Sun direction from an explicit Mars epoch and body-fixed frame with pinned kernels. Test terrain occlusion only where the horizon and terrain extent are resolved. Use incidence and horizon for a visibility estimate.',
  limits:'Unmodeled atmosphere, dust and hardware prevent translating geometry alone into electrical generation.',
  test:'Compare selected epochs and geometry with independent SPICE output; test polar night and unknown horizon.'})
model({group:'environment',id:'generation',name:'Power availability scenario',tech:'Solar / non-solar supply · W',priority:'P1',decision:'Data dependent',classification:'Assumption',evidence:[refs.sun],
  method:'Use an operator-declared supply curve or derive solar generation only with irradiance/attenuation assumptions, panel orientation and efficiency. Non-solar configurations use their own supply constraints. Preserve time dependence and unsupported fields.',
  limits:'Missing needed supply or capacity is explicit. A no-generation case is a declared scenario, not a guessed physical forecast.',
  test:'Check darkness, source switches, W to J conversion and sensitivity to declared dust/efficiency.',
  params:[p('Panel efficiency','η_panel','1','0 ≤ η_panel ≤ 1','Used only for declared solar configuration.')]})
model({group:'environment',id:'environment-gate',name:'Environmental activation',tech:'Purpose · domain · evidence',classification:'Decision',owner:shared,
  method:'Classify each variable as inactive, historical context, explicit scenario or supported prediction. Check declared use, spatial/temporal applicability, assumptions, provenance and validation. Only authorized applicable output can enter an operating constraint or budget.',
  limits:'No dummy-data forecasts or implicit use of historical records. Required unavailable context yields unverified_environment.',
  test:'Check out-of-domain and out-of-horizon model results, missing data, and a valid explicit scenario.'})
model({group:'environment',id:'comms-forecast',name:'Comms and forecast research',tech:'Future domain-validated adapters',priority:'P2',decision:'Deferred',classification:'Optional',
  method:'For communications, require relay ephemerides, antenna state, terrain line-of-sight and a link budget. Future weather adapter requires a verified forecast product, domain, horizon and uncertainty. Until then use authorized restrictions or display historical context.',
  limits:'Terrain elevation alone cannot predict communications, wind or landslides.',
  test:'Validate against independent relay geometry, applicable link measurements or held-out forecast observations before activation.'})

model({group:'resources',id:'resource-ledger',name:'Route resource ledger',tech:'Legs · dwell · return · reserve',owner:shared,decision:'Adopted',
  method:'Evaluate ordered outbound, science and return legs in one snapshot. Report initial, per-phase use, optional supported supply, remaining, required reserve and signed margin per resource. Human consumables use authorized input budgets and consumption rules only. Reuse the canonical return-time margin.',
  formula:'margin_r = available_r − net_use_r − reserve_r (additive case); E[k+1] = min(E_cap, E[k] + credited_generation_k − demand_k)',
  variables:'r has its own unit; time s; energy J; power W. Generation credit bounded by authorized charge limits and capacity.',
  assumptions:'Time-step model for time-dependent supply; constrain energy and power at applicable prefixes. Report lost/spilled energy separately.',
  limits:'A feasible end balance cannot rescue an earlier depletion or power violation. Unsupported required values are null and fail the affected check.',
  test:'Verify unit conversion, zero margin, prefix depletion with positive final balance, reserve, clipping and power threshold.'})

model({group:'science-models',id:'science-relevance',name:'Mission science relevance',tech:'Objective → evidence → artifact',owner:planning,decision:'Adopted',classification:'Interpretation',evidence:[refs.stm,refs.eva],
  method:'Map mission objective and hypothesis to required evidence, proposed observation methods and expected deliverables. Compare fulfillment using an explicit mission rubric. Intrinsic interest, current relevance, evidence quality and operational accessibility remain separate.',
  limits:'No universal score. A region ranking never contributes to per-cell route weights.',
  test:'Compare a climate objective with a volcanology objective, differing evidence classes, and a qualitative-only assessment.'})
model({group:'science-models',id:'task-eligibility',name:'Task & approach eligibility',tech:'Methods · prerequisites · instruments',owner:planning,classification:'Decision',evidence:[refs.stm,refs.eva],
  method:'Validate required instrument, task prerequisites and observed/completed state. Model alternative methods such as transect versus photographs. Distinguish feature, approach and remote viewpoint plus required visibility or measurement geometry. Emit eligible task records and specific deferral reasons.',
  limits:'No automatic transfer of historic rover positions into crew waypoints. A sight line does not prove the observation meets scientific requirements.',
  test:'Check completed tasks, unmet prerequisite, unsupported viewpoint, instrument mismatch and alternatives with different artifacts.'})

model({group:'routing',id:'candidate-routes',name:'Diverse candidate routes',tech:'Directed baseline · bounded Yen',category:'Algorithm',decision:'Adopted',evidence:[refs.graph,refs.yen,refs.rcsp],
  method:'Retain direct return and baseline legs, then generate bounded loopless alternatives per destination and authorized nonnegative scalar cost (time and energy where supported). Deduplicate ordered edge sequences and apply a declared overlap/diversity policy. Reconstruct original directions and preserve objective values and evidence. Route candidates still need mission feasibility checks.',
  limits:'K or wall-clock limits can miss feasible or nondominated routes. Mark search incomplete and distinguish no path from no feasible candidate found.',
  test:'Test alternate direction, closure, graph disconnection, duplicate paths and resource-feasible alternatives missed by fastest-only search.',
  alternatives:'A* for targeted pairs with a justified admissible heuristic; resource-label search for constrained paths; Yen for bounded loopless alternatives.',
  complexity:'Repeated scalar shortest-path searches depend on K and path length; cap by destination and benchmark.',
  params:[p('Alternative candidate cap','K','paths','Positive integer; benchmark and disclose','Upper bound per objective and leg.','Planner configuration'),p('Route overlap threshold','O_max','1','0 ≤ O_max ≤ 1','Declare ordered-edge overlap definition. Keep a pinned direct-return option.','Planner configuration')]})
model({group:'decision',id:'mission-candidates',name:'Compose candidate plans',tech:'Return · outbound · science · return',category:'Algorithm',owner:planning,decision:'Adopted',evidence:[refs.eva],
  method:'Pin direct return and combine bounded outbound/return legs with at most one eligible unfinished observation in P0. Use only matching mission snapshots. Record task artifacts, ordered legs, assumptions and objective fulfillment before constraints are checked.',
  limits:'Finite sampled candidates; no proof of global optimality or arbitrary multi-stop feasibility.',
  test:'Compare exhaustive tiny fixtures; ensure no mixed pack/profile, duplicate completed task, missing return or reversed leg.'})
model({group:'decision',id:'hard-filter',name:'Enforce hard constraints',tech:'Pass · fail · unknown by rule',owner:shared,classification:'Decision',decision:'Adopted',
  method:'Check valid supported terrain and profile, current and return positions, path existence, mission restrictions, prerequisites, supported required environment, time/energy/consumable margins and prefix/power constraints. Apply the independent direct-return gate before recommending science. Required unknowns block affected plans. Send only passing candidates to Pareto comparison.',
  assumptions:'For each applicable profile, test a direct-return candidate set against all required limits; do not assume the fastest return also fits energy. If search was capped, report that qualification.',
  limits:'Bounded search failure differs from graph disconnection and from missing evidence. No weighted objective can override a constraint.',
  test:'Reject high-value but over-reserve candidates, missing required inputs and all science when direct return is not admissible within reserve.'})
model({group:'decision',id:'pareto-front',name:'Compare Pareto alternatives',tech:'Constraint-first · finite candidate set',category:'Algorithm',owner:planning,decision:'Adopted',evidence:[refs.rcsp,refs.eva],
  method:'Compare only passing plans under one scenario and a common declared objective domain. Keep time, energy where supported, reserve margin, terrain exposure, uncertainty exposure and science fulfillment distinct. Orient objectives for minimization or maximization before comparing. Preserve distinct objective ties and route alternatives for review.',
  formula:'For minimization-normalized directions, a dominates b iff ∀k a_k ≤ b_k and ∃k a_k < b_k.',
  variables:'k is an applicable objective, with declared units, sense and tolerance. An optional unsupported metric is null and must not be treated as zero.',
  limits:'Frontier is over evaluated candidates. Different model applicability or scenarios are not directly comparable. Tolerance policy must preserve a deterministic comparison.',
  test:'Known dominance, ties, incomparable candidates, dominated points, missing objectives and rejection of infeasible plans.',
  alternatives:'Lexicographic selection from the frontier; explicit normalized weighted utility only after feasibility and with a sensitivity report.',
  complexity:'Pairwise dominance O(N²·M) for N bounded candidates and M objectives.',
  params:[p('Objective comparison tolerance','ε','per objective','Define unit-specific rounding/tie policy','Avoid treating floating-point noise as a meaningful improvement.','Versioned objective policy')]})
model({group:'decision',id:'multi-stop',name:'Bounded multi-stop planning',tech:'P1 · ordered tasks and leg cache',category:'Algorithm',owner:planning,priority:'P1',decision:'Proposed',evidence:[refs.eva,refs.rcsp],
  method:'Enumerate a declared small set of ordered one- and two-task sequences with directed leg caches, prerequisites, dwell and resources. Add time windows or state-dependent power through resource-labeled search, state expansion or a separately evaluated optimizer.',
  limits:'Combinations and labels grow with tasks and resources. Ordinary Dijkstra solves one scalar path problem, not resource-constrained multi-stop scheduling.',
  test:'Compare exhaustive fixtures, swapped task order, incompatible prerequisites and candidate cap behavior.',
  alternatives:'Bounded enumeration first; resource-constrained label search or orienteering/CP-SAT model after scale measurement.'})

model({group:'replan',id:'mission-update',name:'Validate mission updates',tech:'Revision · position · closure',category:'Backend service',owner:planning,classification:'Simulation',decision:'Adopted',evidence:[refs.eva],
  method:'Normalize closure, position, resource, priority, evidence and operator-limit changes against the current pack/revision. Preserve completed tasks. Distinguish operator report, simulated event and archived observation. Make outdated plans and responses non-actionable.',
  limits:'No assumed live telemetry. Stale or invalid events cannot mutate the current mission snapshot.',
  test:'Check stale/duplicate updates, completed-task retention, changed budgets, invalid geometry and concurrent response order.'})
model({group:'replan',id:'recompute-scope',name:'Invalidate and re-evaluate',tech:'Fresh inputs · affected caches',owner:planning,decision:'Adopted',evidence:[refs.dstar,refs.eva],
  method:'Key graph and route caches by pack, grid, platform, config and closure revision. After updates, revalidate cached routes and recompute affected candidates, resource ledgers, task eligibility and objective comparison against the fresh snapshot.',
  limits:'An old alternative is never presumed feasible. D* Lite is optional after profiling repeated sparse changes on an appropriate graph.',
  test:'Compare replan with full recompute and verify stale-cache rejection for affected routes.',
  alternatives:'Full deterministic recomputation baseline; incremental D* Lite if its prerequisites and a performance case are established.'})
model({group:'replan',id:'contingency',name:'Contingency outcomes',tech:'Continue · reroute · defer · return',owner:planning,classification:'Decision',
  method:'Compare old and current plans and return explicit continue, reroute, alternate task, defer, direct return, no admissible route, insufficient evidence or search incomplete. Preserve changed constraints, science artifacts, reserves and event identity. Use only preauthorized contingency options.',
  limits:'No safe-route claim through unknown terrain. Historical rover locations do not establish reachable rescue or salvage assets.',
  test:'Check blocked return, unchanged feasible plan, task substitution, and stale response presented only as history.'})

model({group:'uncertainty',id:'evidence-limits',name:'Uncertainty and evidence limits',tech:'Measurement · spatial · model',owner:planning,decision:'Adopted',
  method:'Track measurement, registration, resolved scale, model simplification, scenario and data availability separately. Carry interval or qualitative limitations and source/assumption IDs to each candidate. Propagate numerical bounds only where input uncertainty and dependence justify it.',
  limits:'No fabricated distributions, probabilities or confidence intervals. Coarse support cannot resolve microhazards.',
  test:'Check unknown inputs, correlated errors, coverage holes, frame disagreement and no silent promotion of qualitative values.'})
model({group:'uncertainty',id:'scenario-sensitivity',name:'Scenario and decision stability',tech:'P1 · parameter perturbation',owner:planning,priority:'P1',
  method:'Vary explicitly scoped pace, rover work parameters, reserves, evidence policy or mission priorities. Compare ledger margins and frontier/selection stability. Recompute candidate search when edge ordering or constraints change; use fixed-route sensitivity only when labeled.',
  limits:'Scenarios provide conditional comparisons. No probability of safety or calibrated predictive distribution.',
  test:'One-parameter and joint sweeps, zero-margin crossing, changed route ordering and inconsistent objective domains.'})

model({group:'validate',id:'model-tests',name:'Physics & optimization checks',tech:'Fixtures · independent enumerator',category:'Validation',owner:shared,
  method:'Use unit and dimensional tests, directed graph and masking fixtures, resource conservation, exhaustive small-set Pareto enumeration, deterministic ties, failed hard gates, unsupported values and stale replan checks. Benchmark candidates, grid size and cold/local latency.',
  limits:'Fixture correctness does not validate planetary mobility or mission safety. Report measured results by model version and evidence scope.',
  test:'Flat/up/down, zero edge, closure, power vs energy, prefix reserve, missing support, disconnected graph, exact ties and completed-task preservation.'})
model({group:'validate',id:'comparative-cases',name:'Historical comparative cases',tech:'Meridiani · Gale · Jezero · Gusev',category:'Validation',owner:shared,priority:'P1',decision:'Research required',evidence:[refs.mer,refs.spirit,refs.rad,refs.places],
  method:'Pin local observed rover segments and incident reports for terrain, frame and model comparison, including weak-soil and successful-drive cases. Verify vehicle and time applicability and preserve positive and negative observations.',
  limits:'Historical traverses are observational comparison, not optimal-path labels or validation of human mobility. Localized traces do not calibrate global models.',
  test:'Independently verify exact IDs, frame, source coverage, timestamps and vehicle state; withhold conclusions where unmatched.'})
model({group:'validate',id:'terrain-ml-study',name:'Terrain classification research',tech:'SPOC precedent · gated study',category:'Annotation',classification:'Optional',priority:'P2',decision:'Research required',evidence:[refs.spoc],
  method:'Candidate target is a terrain/material class or unknown from a declared image patch, using sourced rover labels and sensor-domain checks. Establish sample size and label quality; split by geography and traverse to avoid leakage; benchmark against a deterministic source-backed baseline. Require domain checks, independent validation, uncertain-class abstention and offline inference budget.',
  limits:'No active ML output. The 56 summaries are not labeled training examples. Class labels do not imply slip, safety or trafficability.',
  test:'Measure geographically held-out errors, class imbalance, unknown inputs, calibration and fallback behavior.'})
model({group:'explanation',id:'decision-record',name:'Mission decision contract',tech:'Objectives · ledger · reason codes',category:'Storage artifact',owner:shared,decision:'Adopted',classification:'Decision',
  method:'Expose versioned mission/pack/revision IDs, selected plan or abstention, direct return, feasible alternatives, objective directions and values, resource ledger, applied and violated constraints, reasons, evidence IDs, model assumptions and what changed. Keep unsupported values null. Runtime UI shows only matching current revisions.',
  limits:'Explicit modeled admissibility is not operational safety certification. Separate unsupported evidence, known disconnection, over-budget and bounded search incomplete.',
  test:'Check schema compatibility, stable reasons, evidence trace, null values, unchanged state and suppression of stale output.'})

type WireDetails = Partial<Connection> & { inputClass?:Component['classification']; required?:boolean }
const wires: (Connection & Pick<WireDetails,'inputClass'|'required'>)[] = []
function wire(source:string,target:string,label:string,kind:Connection['kind']='Data flow',details:WireDetails={}) {
  wires.push({id:'model-'+source+'--'+target,source,target,label,kind,payload:label,format:'Versioned model record',protocol:'Local planning contract',description:'',validation:'',dependencies:[],...details})
}
wire('request-check','mission-snapshot','Validated scenario request','Request')
wire('loader','mission-snapshot','Pack revision and capabilities')
wire('mission-snapshot','human-profile','Human-tagged configuration','Configuration',{inputClass:'Assumption'})
wire('mission-snapshot','rover-profile','Rover-tagged configuration','Configuration',{inputClass:'Assumption'})
wire('mission-snapshot','operator-limits','Authorization and restrictions','Configuration',{inputClass:'Assumption'})
wire('mission-snapshot','science-relevance','Objective and mission priorities','Configuration')
wire('mission-snapshot','resource-ledger','Budgets, reserves and completed tasks','Configuration',{units:'s, J or declared consumable units'})
wire('mission-snapshot','environment-gate','Scenario scope and time','Configuration',{inputClass:'Assumption'})
wire('mission-snapshot','hard-filter','Snapshot identity and policy','Configuration')
wire('mars-reference','planet-distance','Declared Mars reference','Configuration')
wire('planetary-normalize','planet-distance','Planetary geographic positions','Derived product',{units:'degrees'})
wire('projection','grade','Validated local grid reference','Configuration',{units:'m'})
wire('elevation','grade','Elevation and affine','Derived product',{units:'m'})
wire('gradient','resolved-scale','Stencil and native support','Derived product')
wire('coverage','resolved-scale','Valid footprint and mask','Derived product')
wire('terrain-file','resolved-scale','Published terrain and scale','Derived product')
wire('terrain-crop','roughness','Native supported heights','Derived product',{units:'m',required:false})
wire('roughness','barrier-mask','Optional resolved descriptor','Derived product',{required:false})
wire('display-files','surface-evidence','Mapped context, scale and attribution','Provenance',{required:false,inputClass:'Interpretation'})
wire('surface-evidence','barrier-mask','Source-backed flags and mapped barriers','Provenance',{required:false,inputClass:'Interpretation'})
wire('resolved-scale','barrier-mask','Support, resolved scale and gaps')
wire('screen','barrier-mask','Configured terrain screening','Configuration',{inputClass:'Assumption'})
wire('operator-limits','barrier-mask','Authorized exclusion geometry','Control')
wire('barrier-mask','graph','Known exclusions and unknown support','Control')
wire('resolved-scale','graph','Validated support and scale limits','Control')
wire('barrier-mask','traverse','Human candidate edge validity','Control')
wire('barrier-mask','rover-travel','Rover candidate edge validity','Control')
wire('grade','rover-travel','Signed grade and length','Derived product',{units:'m, dimensionless grade'})
wire('grade','rover-energy','Length and elevation change','Derived product',{units:'m'})
wire('human-profile','traverse','Illustrative pace assumptions','Configuration',{inputClass:'Assumption'})
wire('rover-profile','rover-travel','Vehicle and operating limits','Configuration',{inputClass:'Assumption'})
wire('rover-profile','rover-energy','Mass and drive parameters','Configuration',{inputClass:'Assumption'})
wire('rover-profile','generation','Tagged supply configuration','Configuration',{required:false})
wire('rover-travel','rover-energy','Segment duration','Derived product',{units:'s'})
wire('traverse','mobility-interface','Human edge estimate','Derived product',{required:false})
wire('rover-travel','mobility-interface','Rover edge estimate','Derived product',{required:false})
wire('rover-energy','mobility-interface','Rover electrical edge demand','Derived product',{units:'J',required:false})
wire('mobility-interface','graph','Admissible edges and scalar costs','Data flow',{format:'Directed edge records',units:'m, s, J where applicable',requiredMetadata:'Profile ID, pack/revision, admissibility, masks, evidence, applicable metrics',failure:'Block invalid edges and report unsupported required metrics.'})
wire('meda','environment-history','Archived weather observations','Provenance',{required:false,inputClass:'Observation'})
wire('environment-history','environment-gate','Historical context only','Provenance',{required:false,inputClass:'Observation'})
wire('projection','illumination','Body-fixed geometry and terrain','Configuration',{required:false})
wire('illumination','generation','Incidence and supported shadow','Derived product',{required:false})
wire('generation','environment-gate','Explicit supply scenario','Configuration',{required:false,inputClass:'Assumption'})
wire('environment-gate','resource-ledger','Authorized scoped supply inputs','Configuration',{required:false})
wire('environment-gate','hard-filter','Applicable conditions or unknown','Control')
wire('operator-limits','hard-filter','Authorized operating restrictions','Control')
wire('rover-energy','resource-ledger','Segment and stationary energy','Derived product',{units:'J',required:false})
wire('traverse','resource-ledger','Human traversal time','Derived product',{units:'s',required:false})
wire('budget','resource-ledger','Direct return reserve margin','Derived product',{units:'s'})
wire('rank-regions','science-relevance','Screened region and criteria','Configuration',{required:false,description:'Region priority is context for selecting investigations, never a per-cell cost.'})
wire('science-objectives','science-relevance','Objective and evidence requirements','Configuration')
wire('science-target','task-eligibility','Targets, approaches and viewpoints')
wire('science-task','task-eligibility','Instrument, dwell and artifact contract')
wire('tasks','task-eligibility','Candidate tasks and completions')
wire('science-relevance','task-eligibility','Declared mission rubric')
wire('task-eligibility','candidate-routes','Eligible destinations and methods','Configuration')
wire('task-eligibility','mission-candidates','Eligible unfinished science methods')
wire('science-relevance','pareto-front','Mission objective definitions','Configuration')
wire('legs','candidate-routes','Directed baseline legs','Derived product')
wire('closure','candidate-routes','Request-local graph constraints','Control')
wire('candidate-routes','mission-candidates','Distinct directed candidates','Data flow',{requiredMetadata:'Route geometry, endpoint, costs, constraints, profile and snapshot, search completeness and evidence.',failure:'Keep no path, insufficient evidence and bounded-search failure distinct.'})
wire('mission-candidates','resource-ledger','Ordered plans and dwell')
wire('resource-ledger','hard-filter','Per-resource ledger and prefix checks','Derived product',{units:'s, J, W or declared resource units'})
wire('feasibility','hard-filter','Human next-action timing check','Validation',{required:false})
wire('mission-candidates','hard-filter','Candidate plans and task evidence')
wire('hard-filter','pareto-front','Feasible plans only','Control',{failure:'Required unknowns, failed direct-return gate and invalid plans cannot reach objective comparison.'})
wire('hard-filter','abstain','Failures and unsupported requirements','Control')
wire('pareto-front','rank','Nondominated alternatives and objectives','Derived product')
wire('rank','decision-record','Selection and alternatives','Derived product')
wire('abstain','decision-record','Explicit abstention reasons','Control')
wire('resource-ledger','decision-record','Inspectable per-leg ledger','Derived product')
wire('decision-record','explain','Traceable outcome and rationale')
wire('decision-record','serialize','Proposed versioned planning response','Response')
wire('field','mission-update','Reported simulated or operator event','Request',{inputClass:'Simulation'})
wire('request-check','mission-update','Current revision and validation context','Configuration')
wire('mission-update','mission-snapshot','Fresh normalized mission state','Control')
wire('mission-update','recompute-scope','Affected position, rules and resources','Control')
wire('mission-update','freshness','Prior decision superseded','Control')
wire('recompute-scope','closure','Fresh closure geometry and revision','Control')
wire('recompute-scope','candidate-routes','Invalidate and regenerate route set','Control')
wire('recompute-scope','task-eligibility','Preserved completions and changed priorities','Control')
wire('rank','contingency','Updated admissible choice')
wire('abstain','contingency','No feasible or supported decision','Control')
wire('contingency','decision-record','Changed plan, margins and retained science','Derived product')
wire('resolved-scale','evidence-limits','Support and spatial limits','Provenance')
wire('rover-travel','evidence-limits','Model and calibration limits','Provenance',{required:false})
wire('traverse','evidence-limits','Illustrative pace domain','Provenance',{required:false})
wire('environment-gate','evidence-limits','Applicability and evidence gaps','Provenance')
wire('evidence-limits','hard-filter','Required evidence and uncertainty flags','Control')
wire('evidence-limits','abstain','Unsupported evidence classification','Control')
wire('pareto-front','scenario-sensitivity','Baseline evaluated objective set','Data flow',{required:false})
wire('sensitivity','scenario-sensitivity','Fixed-route pace sensitivity','Derived product',{required:false})
wire('evidence-limits','scenario-sensitivity','Declared uncertainty axes','Configuration',{required:false})
wire('scenario-sensitivity','decision-record','Sensitivity and scenario limits','Derived product',{required:false})
wire('multi-stop','mission-candidates','Optional bounded sequences','Configuration',{required:false})
for (const id of ['grade','rover-energy','resource-ledger','graph','hard-filter','pareto-front','contingency']) wire(id,'model-tests','Fixture or acceptance contract','Validation')
wire('comparative-cases','model-tests','Comparative source cases','Validation',{required:false})
wire('model-tests','evidence-limits','Validation findings and domain limits','Validation')
wire('science-relevance','multi-stop','Optional task values and prerequisites','Configuration',{required:false})

const projected: Record<string,string[]> = {
  geometry:['planetary-normalize','projection','terrain-crop','elevation','gradient','grade'],
  surface:['coverage','screen','routing-inputs'],
  'human-mobility':['traverse'],
  resources:['budget'],
  'science-models':['region-registry','rank-regions','science-objectives','science-target','science-task','tasks'],
  replan:['closure','freshness'],
  uncertainty:['sensitivity','abstain'],
  explanation:['explain','serialize','cards'],
}
const legacyFamilies = new Map(Object.entries(projected).flatMap(([group,ids])=>ids.map(id=>[id,group])))
const affected = new Set([...legacyFamilies.keys(),'graph','solve','legs','feasibility','rank','excluded','solver-test','scenario-test','gis-check','perf-test'])
const legacyDescriptions: Record<string,Partial<Component>> = {
  grade:{notes:'d = hypot(Δx,Δy) in the declared local metric plane; g = Δz/d for d > 0; θ = atan(g). Reverse grade changes sign. Keep local maximum slope separate.'},
  traverse:{name:'Human traversal time',notes:'Illustrative directional pace model from the Return Window report. The original Jezero parameters are scenario examples, not calibrated Mars walking assumptions.'},
  rank:{description:'Select from the evaluated nondominated, feasible set by declared mission priority, then reserve margin and stable candidate ID as configured. Keep alternatives and explain trade-offs. The earlier Jezero path is a one-next-action reference case.',technology:['Priority · margin · stable tie']},
  abstain:{description:'Distinguish invalid input, insufficient terrain evidence, unsupported mobility, missing required resource specification, unverified environment, no graph path, exceeded reserve and no feasible candidate within a bounded search. Mark scenario sensitivity separately. Never recommend a route through unknown support.'},
  excluded:{notes:'Excluded: opaque ML decision councils, universal safety scores, unvalidated forecasts, medical suitability/ranking, unsupported global routing and historical-vehicle rescue assumptions.'},
}

export function expandModels(base:Architecture): Architecture {
  const groups = [...base.groups.map(group=>group.id==='decision' ? {...group,name:'Mission optimization',summary:'Hard gates · Pareto · priorities',description:'Compose candidate plans, account for resources, filter hard constraints, then compare feasible alternatives and select by declared mission priorities.'} : group),...families]
  const all = [...base.components.map(item=>{
    if (!affected.has(item.id)) return item
    const modelFamily = legacyFamilies.get(item.id)
    const geo = ['geometry','surface','human-mobility','resources'].includes(modelFamily ?? '') || item.groupId === 'routing'
    const owner = item.owner || (geo ? physics : item.groupId==='validate' ? shared : planning)
    const references = [...item.references,reviewDoc]
    if (['grade','gradient','elevation','coverage','screen'].includes(item.id)) references.push(refs.dtm)
    if (['solve','graph','legs'].includes(item.id)) references.push(refs.graph)
    if (['rank','budget','feasibility','traverse','closure'].includes(item.id)) references.push(refs.eva)
    const algorithm = item.algorithm && {...item.algorithm}
    if (item.id==='grade' && algorithm) {
      algorithm.formula = 'd = hypot(Δx, Δy); g = Δz / d, d > 0; θ = atan(g)'
      algorithm.variables = 'Δx, Δy, Δz and d in m; grade dimensionless; θ radians unless converted.'
      algorithm.edgeCases = 'Reject coincident centres, invalid masks, inconsistent CRS or vertical references.'
    }
    if (item.id==='gradient' && algorithm) {
      algorithm.formula = 'θ_local = atan(hypot(∂z/∂x, ∂z/∂y))'
      algorithm.variables = 'Elevation and projected coordinates in m. Convert radians to degrees only at the documented boundary.'
    }
    if (item.id==='solve' && algorithm) {
      algorithm.alternatives = 'A* for targeted pairs with a proved admissible lower bound; bounded Yen candidates for distinct paths. Keep transposed Dijkstra for the baseline return search.'
      algorithm.edgeCases = 'Reject unsupported or negative weights; preserve unreachable predecessors, check closure masks and directed return geometry.'
    }
    if (item.id==='traverse' && algorithm) {
      algorithm.variables = 'Distance d in m, pace v in m/s, signed grade g and penalty coefficients dimensionless. Travel time in seconds.'
      algorithm.assumptions = 'Illustrative, profile-authorized pace and directional penalties. Values apply only within the declared scenario.'
      algorithm.edgeCases = 'Reject nonpositive pace, nonfinite input and blocked or unsupported edges.'
    }
    if (item.id==='rank' && algorithm) algorithm.method = 'Use the finite evaluated Pareto set under one scenario. Apply mission priority then declared margin tie-break and stable IDs. Keep direct return available. The Jezero reference uses a priority-then-margin next-action comparison.'
    return {...item,...legacyDescriptions[item.id],...(modelFamily ? {modelFamily} : {}),owner,references,...(algorithm ? {algorithm} : {}),
      review:{decision:item.id==='excluded'?'Rejected':item.priority==='P1'?'Proposed':'Adopted',
        foundation:'Return Window strategy and Scientific Model Design Review',
        availability:'Canonical versioned inputs. Source applicability and end-to-end validation pending.',
        value:legacyDescriptions[item.id]?.description ?? item.purpose,difficulty:'Verify with scoped fixtures and source evidence.',
        validationStatus:'Not evaluated',uncertainty:item.algorithm?.limitations || item.risks || 'Applicability depends on declared input, scale and configuration.',
      } satisfies ModelReview}
  }),...additions]
  const byId = new Map(all.map(item=>[item.id,item]))
  const edges = wires.map(({inputClass: _classification,required: _required,...edge})=>edge)
  const variable = (edge:typeof wires[number],output:boolean): Variable => ({
    ...newVariable(),name:edge.label,type:edge.format,unit:edge.units ?? '',description:edge.payload,
    componentId:output?edge.target:edge.source,required:edge.required ?? true,
    classification:edge.inputClass ?? byId.get(edge.source)?.classification ?? 'Architecture',
    availability:edge.required===false?'Optional or domain dependent':'Required within the applicable profile or stage',
    validRange:edge.validation || 'Use the applicable contract and declared units.',
    limitations:edge.failure || 'Retain applicability and evidence restrictions.',
  })
  // Keep walkthrough edges addressable by their original IDs. The general
  // planning view uses the explicit feasibility and Pareto stages.
  const referenceLinks = new Set(['traverse--graph','budget--rank','abstain--rank','rank--explain','feasibility--budget'])
  const previous = base.connections.map(edge=>referenceLinks.has(edge.id) ? {...edge,scope:'Jezero reference' as const} : edge)
  const inbound = Map.groupBy(wires.filter(edge=>edge.kind!=='Validation'),edge=>edge.target)
  const outbound = Map.groupBy(wires,edge=>edge.source)
  const enrich = new Set([...affected,...additions.map(item=>item.id)])
  return {...base,architectureVersion:'3.0.0',modelRevision:1,groups,connections:[...previous,...edges],
    components:all.map(item=>enrich.has(item.id)?{
      ...item,inputs:[...item.inputs,...(inbound.get(item.id)??[]).map(edge=>variable(edge,false))],
      outputs:[...item.outputs,...(outbound.get(item.id)??[]).map(edge=>variable(edge,true))],
    }:item),
  }
}
