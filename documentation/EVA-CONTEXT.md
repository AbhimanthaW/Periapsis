# EVA context for the planetary documentation engine

The engine supplies examples for the 28 requested fields through an opt-in cell query. Each value has a unit, method and data status. The inputs describe a single illustrative activity, a historical rover record, or a source-derived estimate. Crew and suit quantities belong to an EVA timeline. The HEALPix cell is a discovery key for each example.

## Research and calculation plan

| # | Field | Implemented model and production evidence |
|---:|---|---|
| 1 | Radiation dose rate | The synthetic example integrates a constant absorbed dose rate over elapsed Earth seconds. The Gale case substitutes the published MSL/RAD E-detector tissue-like GCR absorbed dose rate of 0.210 ± 0.040 mGy/day over the first ~300 sols. A future crew-dose calculation needs particle spectra, space weather, shielding and a dose-transport model. [Hassler et al., table 1](https://doi.org/10.1126/science.1244797) · [RAD product specification](https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/DOCUMENT/RAD_RDR_SIS.PDF) |
| 2 | Temperature | Direct replacement with the Jezero MEDA ATS mast thermocouple in the historical case. The sample is local air temperature in K. Forecasting or interpolating needs time, position, sensor height and a qualified model. [MEDA archive](https://pdsatmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html) |
| 3 | Wind speed | Direct replacement with MEDA derived horizontal wind in m/s. The selected rover record is stationary and the row leaves measurement uncertainty and boom status blank. Gusts and head-height wind need their own measurement support. [MEDA meteorology](https://doi.org/10.1038/s41561-022-01084-0) |
| 4 | Atmospheric pressure | Direct replacement with MEDA derived pressure in Pa, transducer 1. The row leaves uncertainty blank. A spatial/temporal pressure model needs independent validation. [MEDA archive](https://pdsatmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html) |
| 5 | Energy consumption | Integrate declared base electrical power plus an illustrative cooling load coefficient. Output Wh is electrical draw. A real estimate needs calibrated equipment-mode power traces, duty cycles and battery losses. [NASA spacesuit requirements](https://www.nasa.gov/reference/11-0-spacesuits-vol-2/) |
| 6 | Oxygen consumption | Invert the non-protein Weir relation at the declared respiratory exchange ratio. Convert dry gas volume at 0 °C and 1 atmosphere to mass. Real suits require measured metabolic demand, leakage and purge rates. [Weir](https://doi.org/10.1113/jphysiol.1949.sp004363) · [NASA metabolic design loads](https://ntrs.nasa.gov/citations/20205010692) |
| 7 | Water consumption | Multiply an assumed drinking rate by elapsed time and report cooling-water draw separately. Real hydration and coolant budgets depend on crew, duty cycle and suit hardware. [NASA spacesuit requirements](https://www.nasa.gov/reference/11-0-spacesuits-vol-2/) |
| 8 | CO₂ removal load | Multiply oxygen volume rate by the respiratory exchange ratio, convert to CO₂ mass, then integrate production and the excess over a declared constant removal rate. A real ppCO₂ model needs loop inventory, flow, scrubber response and suit telemetry. [NASA spacesuit requirements](https://www.nasa.gov/reference/11-0-spacesuits-vol-2/) |
| 9 | Metabolic expenditure | Integrate base workload plus positive uphill mechanical power and suit joint power divided by an illustrative efficiency. Establish real rates with suited activity tests and indirect calorimetry. [NASA metabolic design loads](https://ntrs.nasa.gov/citations/20205010692) |
| 10 | Suit battery charge | Subtract cumulative demand from the initial electrical energy. A real estimate needs state of charge telemetry, usable capacity, temperature and discharge limits. [NASA spacesuit requirements](https://www.nasa.gov/reference/11-0-spacesuits-vol-2/) |
| 11 | Suit cooling demand | Use a steady thermal balance with metabolic power, external work and declared net external heat load. A real model needs suit insulation, radiation, internal storage, circulation and heat rejection. [NASA spacesuit design brief](https://www.nasa.gov/wp-content/uploads/2025/09/ochmo-tb-050-spacesuits.pdf) |
| 12 | Dust concentration | Accept a declared local mass concentration in mg/m³. Published MEDA aerosol optical depth describes a column. To derive local mass concentration, qualify the vertical aerosol profile and wavelength-dependent mass extinction. [MEDA aerosol optical depth](https://doi.org/10.1029/2022JE007560) |
| 13 | Solar illumination | Compute solar elevation from latitude, declination and hour angle in the fixture. The Jezero case uses solar zenith from MEDA ancillary geometry and converts it to elevation. Irradiance and surface shading require atmospheric transmission, surface orientation and terrain horizon. [NASA Mars24](https://www.giss.nasa.gov/tools/mars24/help/algorithm.html) · [MEDA geometry](https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_derived_env/sol_0000_0089/sol_0036/) |
| 14 | Terrain slope | Use magnitude of the synthetic grade angle, or a local Horn 3×3 gradient from the archive-verified USGS CTX DEM at 20 m posting. A single gradient describes the sampled DEM scale. A route requires continuous verified terrain and a directional grade calculation. [USGS CTX DEM](https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic) |
| 15 | Surface traction | Declare a dimensionless boot-to-soil friction coefficient for the fixture. A measured value requires representative boot contact geometry, soil and load. InSight penetration results characterize specific tools and site materials. [InSight soil study](https://doi.org/10.1007/s11214-022-00941-z) |
| 16 | Regolith sinkage | Invert a synthetic plate pressure–sinkage power law. Contact pressure uses one planted foot and static Martian weight. Real parameters depend on loaded area, soil history, density and material tests. [InSight soil study](https://doi.org/10.1007/s11214-022-00941-z) |
| 17 | Obstacle density | Divide a declared mapped obstacle count by surveyed area and preserve the height cutoff in the output. Production needs a validated high-resolution object inventory with a stated detection threshold and survey polygon. [USGS landing site products](https://astrogeology.usgs.gov/search/map/mars-2020-jezero-crater-landing-site-products) |
| 18 | Suit mobility resistance | Joint resisting torque times angular speed yields mechanical W. A real suit model needs joint-by-joint torque, velocity, pressure and duty-cycle tests. [NASA spacesuit design brief](https://www.nasa.gov/wp-content/uploads/2025/09/ochmo-tb-050-spacesuits.pdf) |
| 19 | Communication signal availability | For the fictional local link, check sampled terrain against 60% of the first Fresnel zone and compare a free-space receive margin to the declared receiver minimum. A real link needs a path survey, antenna patterns, obstructions, relay schedule and a qualified link budget. [ITU-R P.525](https://www.itu.int/rec/R-REC-P.525-5-202411-I/en) |
| 20 | Visibility distance | Solve Beer–Lambert contrast attenuation in a homogeneous medium using declared dust mass, mass extinction and contrast threshold. This is optical contrast range. Terrain occlusion, light levels and eyewear need separate modelling. [MEDA dust observations](https://doi.org/10.1029/2023GL107975) |
| 21 | Walking speed | Evaluate the existing Marswalk Tobler shape using the declared horizontal speed and signed grade. A controlled suited trial is required to calibrate it. [Marswalk pace proposal](../runtime/docs/mars-tobler-pace.md) |
| 22 | Heart rate | Interpolate a declared synthetic telemetry series between samples. Actual values require subject-specific measurements. [NASA human-system design](https://www.nasa.gov/reference/4-0-physical-characteristics-and-capabilities-vol-2/) |
| 23 | Core body temperature | Interpolate a declared synthetic telemetry series. Real values need qualified sensors or a validated human thermal model. [NASA spacesuit design brief](https://www.nasa.gov/wp-content/uploads/2025/09/ochmo-tb-050-spacesuits.pdf) |
| 24 | Spacesuit internal pressure | Interpolate a declared absolute pressure telemetry series. Real data needs suit instrumentation and the identified suit and operating mode. [NASA spacesuit requirements](https://www.nasa.gov/reference/11-0-spacesuits-vol-2/) |
| 25 | Suit oxygen reserve | Subtract cumulative fixture O₂ use from initial mass. A real resource ledger needs gas inventory, regulator limits, leakage and reserves. [NASA spacesuit requirements](https://www.nasa.gov/reference/11-0-spacesuits-vol-2/) |
| 26 | Suit cooling-water reserve | Subtract simulated heat rejection divided by a declared effective evaporation energy per kg. Real data requires coolant inventory and the specific heat rejection architecture. [NASA spacesuit design brief](https://www.nasa.gov/wp-content/uploads/2025/09/ochmo-tb-050-spacesuits.pdf) |
| 27 | Remaining EVA duration | Take the smallest time-to-exhaustion from the declared clock, oxygen, battery, coolant and drinking-water budgets. This is constant-workload bookkeeping. Production needs the direct-return, reserve, contingency and authorized-limit checks from Marswalk. [Marswalk runtime](../runtime/README.md) |
| 28 | Communication latency | Use `distance / c` for the fixture. The Jezero example substitutes Horizons' Mars-centre to Earth-centre one-way down-leg light-time at the selected epoch, 859.3018308 s. Operations latency additionally requires surface/relay geometry, network schedule and processing. [JPL Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html) |

## How the inputs and outputs are scoped

- [Scenario inputs](marsdoc/eva/scenario-v1.json) are the exact, versioned toy assumptions. They use one constant activity and a default elapsed time of 1,200 s. Draw quantities report cumulative demand. Reserves floor at zero and remaining modelled time floors at zero. Output contains no prediction beyond the declared synthetic telemetry interval.
- The metabolic model uses `P_met = P_base + (P_up + P_joint)/efficiency`. The Weir conversion uses `kcal/min = 3.941 VO₂ + 1.106 VCO₂`, with volumes in L/min at the documented standard condition. Whole-suit O₂ draw may differ. The CO₂ excess output is a mass imbalance. A suit volume and mixing model would be required to express concentration or partial pressure.
- The synthetic solar model outputs geometric elevation above the local horizontal. The visibility metric is `−ln(contrast)/extinction`, and extinction is the explicitly assumed local dust mass concentration times the visible mass extinction coefficient in consistent SI units. The link budget evaluates provided terrain samples on a local planar ray. Between-sample obstruction, multipath and system reliability need additional evidence.
- The **Jezero** example selects SCLK `670144481`, LMST `00036M14:42:55.471`. Four PDS tables and their labels were verified by SHA-256 and the archive-specified MD5. A JPL SPICE clock conversion gives `2021-03-27T19:16:36.423Z`. Horizons is evaluated at the nearest whole second. The MEDA position approximation uses a published landing anchor and a reported horizontal displacement of roughly 16 m. The CTX pixel is sampled at that approximate position. The cell indexes these local records. [Sources and hashes](examples/eva-source-receipt.json) · [Landing location](https://ntrs.nasa.gov/api/citations/20230016428/downloads/Bell%20et%20al%202022sciadv.pdf?attachment=true)
- The **Gale** example is a published historical aggregate. Bradbury Landing indexes the statistic for discovery. The RAD measurement period includes a rover traverse. No per-cell coverage mask or global extrapolation follows from it. [MSL traverse overview](https://doi.org/10.1002/2014JE004622)
- A selected historical case replaces only the corresponding display fields in its anchor cell. The scenario calculations still use their versioned toy inputs. No MEDA weather, CTX slope or historical dose value enters the toy resource ledger. Unrelated cells carry `null` values. The catalogue, documentation scores, route costs and capability resolver use their existing inputs.

## Run and verify

From the repository root:

```sh
uv run --project documentation --locked marsdoc evidence/jezero/jezero-evidence.json \
  --point 77.45 18.44 --eva-context jezero-sol36

uv run --project documentation --locked marsdoc evidence/jezero/jezero-evidence.json \
  --point 137.4417 -4.5895 --eva-context gale-rad

uv run --project documentation --locked marsdoc evidence/jezero/jezero-evidence.json \
  --point 77.45 18.44 --eva-context synthetic --eva-elapsed-s 1200
```

Python callers use `DocumentationEngine.eva_context(cell_id, case=..., elapsed_s=...)`. The CLI attaches the result as a sibling of `documentation`. It can also return the earlier `synthetic_science_context` in the same response. The existing application endpoints and offline cell map do not request the EVA example.

[The historical snapshot](marsdoc/eva/historical-v1.json) ships with the engine. To regenerate it, save the pinned MEDA files and NAIF kernels by original basename and the Horizons response as `horizons.txt` in one directory. Obtain the verified [Jezero elevation window](../evidence/jezero/README.md). Then run:

```sh
uv run --project documentation --locked --with spiceypy==8.4.0 \
  python -m documentation.examples.build_eva_examples \
  /absolute/path/to/source-snapshots /absolute/path/to/jezero-elevation.f32 \
  /absolute/path/to/historical-v1.json
```

The builder verifies digests, joins the four sensor/geometry records by exact spacecraft-clock key and verifies the UTC conversion. Horizons' retrieval timestamp is ignored for its canonical digest. Its target, observer, output quantity and epoch are checked. The Gale paper value is a documented transcription. Real-data qualification for broader use requires richer time series, qualified terrain and model-scale support, and independently reviewed suit and crew inputs.

## Verified examples

| Case | Cell | Verified replacement values |
|---|---|---|
| Jezero sol 36 | `HPX128:96848` | 238.71 K, 9.08 m/s horizontal wind, 737.47 Pa, 55.49° solar elevation, 2.77° local CTX slope, 859.30 s centre-to-centre one-way light-time |
| Early Gale traverse | `HPX128:163685` | 0.210 ± 0.040 mGy/day published tissue-like GCR absorbed dose rate |

The checked Jezero source-window verification reproduced the committed evidence record. Rebuilding the EVA snapshot produced identical bytes. The documentation, contracts and runtime suites passed 295 tests with the verified Jezero Float32 window available.
