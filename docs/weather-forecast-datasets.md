# Weather forecast: datasets and how the model uses them

**Status (15 Nov 2026):** code, tests and a SYNTHETIC example are in the repo. No real mission data has been trained on yet. The session that wrote this could not reach PDS, Zenodo or LMD. Every skill number in `pipeline/examples/weather/synthetic-forecast-report.md` comes from synthetic data and **must not be quoted as Mars skill**. Kit choice uses a separate selection block. The held-out test reports performance with clock fallback for missing input. The kit selection tolerance is a prototype setting and the stricter Weather Watch gate for a validated advisory still needs real-data evidence.

Labels: **verified** = checked against the cited page on 15 Nov 2026. **check** = needs confirming on the files before use.

## What the model does

- **Goal:** forecast pressure, air temperature, wind speed and dust optical depth 1, 3 and 6 Mars hours ahead at a site, with as few sensors as possible.
- **Free baseline:** climatology, meaning the mean for that local-time bin and season. It needs no sensors (the "clock" kit).
- **Sensor kits:** every combination of barometer, thermometer, anemometer and sky-opacity sensor is trained as a correction on top of climatology. If the kit includes the target's own sensor, it starts from anomaly persistence instead.
- **Bands and limits:** P10, P50 and P90 come from residuals on a held-out calibration block. The same residuals give the chance of crossing the caution and warning limits.
- **Selection:** for each target and horizon, the chosen kit is the smallest one that:
  - is within 0.02 skill of the best kit,
  - beats climatology by at least 0.02,
  - is not materially worse than persistence or anomaly persistence,
  - keeps P10–P90 coverage at or above 0.7.

  Otherwise that target ships as climatology.
- **ML contribution:** the report says separately whether the learned correction adds skill beyond plain persistence ("ML adds?"), so persistence never gets credited as ML.
- **Abstain rule:** inputs outside the training range, or a season missing from the training record, give climatology plus the reason.
- **Delivery:**
  - *Command centre* (`command_view`): every target and horizon with its band, base, correction, kit, track record, abstain reason, and warning-exceedance flags.
  - *Astronaut* (`crew_view`): at most three short lines, with the warning chance first if one exists.
  - *Advisory messages:* wind and dust forecasts also become `kind="forecast"` WeatherMessages. `assess_weather` shows these as ADVISORY, and they never change the plan.

**Training-length requirement (found while testing):** the training block must cover every season the model will be used in. With a record of 160 sols, test-season inputs fell outside the training range and the gate refused them, which is correct behaviour. In practice this means more than about 1.1 Mars years of data, because only the first 60% trains.

## Datasets

| Role | Dataset | Variables, cadence | Coverage | Size and format | Why here | Status |
|---|---|---|---|---|---|---|
| **Primary training** | Viking Lander 2 binned meteorology `VL1/VL2-M-MET-4-BINNED-P-T-V-V1.0` (file `vl_tbin.dat`) | Pressure, temperature, wind; 25 bins of equal duration per sol | VL2 sols 1–1050, major gap sols 561–625 | One table | Longest single-station record, already binned, roughly Arcadia's latitude (about 48° N, **check**) | Product and coverage **verified** ([PDS Atmospheres](https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/viking/surface_met.html), [NASA data catalog](https://data.nasa.gov/dataset/vl1-vl2-mars-meteorology-resampled-data-binned-p-t-v-v1-0-c2122)). Whether bins are LMST or LTST and whether an Ls column exists: **check** `VL_TBIN.CAT` |
| Training (second lander) | Viking Lander 1 corrected binned data `VL1-M-MET-4-BINNED-P-T-V-CORR-V1.0` (`vl_mbin.dat`) | P, T, V; 25 bins per sol | VL1 sols 1–350, gap 117–133 | One table | Second site for a transfer test | **verified** ([data.gov](https://catalog.data.gov/dataset/vl1-mars-meteorology-data-resampled-data-binned-p-t-v-v1-0-aa7a7)) |
| Dust input (Viking) | Viking lander camera optical depth `VL_OPAC` | Column dust optical depth from solar imaging | Sols 6–920 | Table | Real sky-opacity input for the dust kit | **verified** ([PDS Atmospheres Viking page](https://atmos-ah-vs.nmsu.edu/data_and_services/atmospheres_data/MARS/pathfinder/viking.html)) |
| Transfer test | InSight APSS: PS calibrated pressure, TWINS derived wind and temperature | One ASCII table per sol; TWINS high-rate (1 Hz) wind often only mid to late afternoon | Files sol 1 (30 Nov 2018) to sol 1188 (29 Mar 2022); gaps from Jan 2021 (power) | Very large: PS about 82 GB and TWINS over 18 GB to sol 477. Download a subset, or use the PDS search tool by date range | Equatorial site; tests how far corrections transfer | **verified** ([PDS Atmospheres InSight](https://atmos.nmsu.edu/data_and_services/atmospheres_data/INSIGHT/insight.html), [Lorenz et al. data notes](https://arxiv.org/pdf/2107.12456)). Column names: **check** the SIS |
| Transfer test | Curiosity REMS reduced data (MODRDR/ENVRDR) | 1 Hz; usually 5 minutes every hour plus extra 60-minute blocks; pressure in Pa, temperature in K; pressure uncertainty about 3.5 Pa | Sol 1 (7 Aug 2012, Ls 151, MY 31), ongoing | Per-sol tables | Long record in a crater; overlaps the dust masks in MY 31–32 | **verified** ([PDS Atmospheres REMS](https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html), [REMS pressure](https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems_pressure.html)) |
| Replay and demo | Perseverance MEDA | Pressure, temperature, wind, radiation and dust; about 1 Hz in blocks; cadence varied over the mission | Sol 36 record already in `documentation/marsdoc/eva/historical-v1.json`; processed data through sol 1450 described | PDS | The real Jezero storm replay; ingest pressure and temperature first | Cadence and the pending wind re-release **verified** ([EPSC-DPS 2025](https://meetingorganizer.copernicus.org/EPSC-DPS2025/EPSC-DPS2025-1461.html)). The Jan 2022 storm sols: **check** |
| Regional dust context | MDAD v1.1 storm masks (MY 28–32) | Per-sol storm masks | MY 28–32 | About 115 MB, NetCDF | Used by the dust outlook (PR #23), not by this station model | **verified** ([Zenodo 7480334](https://zenodo.org/records/7480334)) |
| Example (in repo) | `pipeline/examples/weather/synthetic-station.csv` | All four variables, 24 bins per sol, 3% gaps; sky opacity daytime only | 1050 synthetic sols | 1.1 MB CSV | Exercises every code path offline | **SYNTHETIC**, illustrative amplitudes |

## Running it on real data (Yumeth)

1. **Download and inspect.** Get the Viking binned table first; it's small. Read the catalog file for column order and local-time convention, then write a `station.json` like `pipeline/examples/weather/synthetic-station.json`, with `provenance: "measured"` and the PDS product IDs in `sources`.
2. **Map columns explicitly.** `ingest` never guesses:
   ```powershell
   python -m return_window_pipeline.forecast ingest vl_tbin.csv --map sol=<SOL COLUMN> --map ltst_h=<LOCAL TIME COLUMN> --map ls_deg=<LS COLUMN> --map pressure_pa=<P COLUMN> --map air_temp_k=<T COLUMN> --map wind_ms=<WIND COLUMN> --station vl2.json --out vl2-station.csv
   ```
   For UTC-stamped products (InSight, REMS, MEDA), use `--map time_utc=<UTC COLUMN>` instead of sol, local time and Ls. Use `--scale pressure_pa=100` if a file is in hPa.
3. **Train and report:**
   ```powershell
   python -m return_window_pipeline.forecast train vl2-station.csv --station vl2.json --artifact forecast-model.json --report forecast-report.md --bins 25
   ```
   Add `--transfer insight-station.csv --transfer-station insight.json` for the cross-site table.
4. **Run the views:** `python -m runtime.marswalk.forecast forecast-model.json observations.json` prints both the command-centre and astronaut views. `runtime/examples/forecast-observations-simulated.json` shows the input format.
5. **Report honestly.** Paste the "Selected kit" table into the PR. Rows that say climatology or "ML adds? no" are results, not failures.
