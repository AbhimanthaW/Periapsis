# Forecast evaluation: SYNTHETIC example station (northern mid-latitude)

> **SYNTHETIC example.** These numbers come from generated data and show the report format only. They are not Mars forecast skill.

Model `station-forecast-f8163e63f6c1f406` · provenance **simulated** · blocks: 630 train / 209 calibration / 209 test sols

## Selected kit per target and horizon

| Target | Horizon | Status | Kit (fewest sensors) | Skill vs climatology | Skill vs best baseline | ML adds? | P10–P90 coverage | Test n |
|---|---|---|---|---:|---:|---|---:|---:|
| pressure_pa | 1h | model | barometer | 0.804 | 0.036 | yes | 0.803 | 1058 |
| pressure_pa | 3h | model | barometer | 0.715 | 0.048 | yes | 0.804 | 1061 |
| pressure_pa | 6h | model | barometer | 0.545 | 0.118 | yes | 0.808 | 1050 |
| air_temp_k | 1h | model | thermometer | 0.618 | 0.007 | no, persistence | 0.813 | 1047 |
| air_temp_k | 3h | model | thermometer | 0.367 | 0.002 | no, persistence | 0.816 | 1047 |
| air_temp_k | 6h | model | thermometer+sky opacity | 0.049 | 0.049 | yes | 0.814 | 1043 |
| wind_ms | 1h | climatology | clock | — | — | — | — | 1058 |
| wind_ms | 3h | climatology | clock | — | — | — | — | 1052 |
| wind_ms | 6h | climatology | clock | — | — | — | — | 1046 |
| dust_tau | 1h | model | sky opacity | 0.872 | 0.178 | yes | 0.767 | 891 |
| dust_tau | 3h | model | sky opacity | 0.868 | 0.174 | yes | 0.807 | 528 |
| dust_tau | 6h | climatology | clock | — | — | — | — | 171 |

## Every kit and baseline on the common test set

| Target | Horizon | Kit | Sensors | MAE | Skill vs climatology | Skill vs best baseline | Coverage | Abstain |
|---|---|---|---:|---:|---:|---:|---:|---:|
| pressure_pa | 1h | baseline:climatology | 0 | 5.767 | 0.000 | -3.927 | — | — |
| pressure_pa | 1h | baseline:persistence | 0 | 2.647 | 0.541 | -1.261 | — | — |
| pressure_pa | 1h | baseline:anomaly_persistence | 0 | 1.171 | 0.797 | 0.000 | — | — |
| pressure_pa | 1h | clock | 0 | 5.767 | 0.000 | -3.927 | 0.825 | 0.000 |
| pressure_pa | 1h | barometer | 1 | 1.129 | 0.804 | 0.036 | 0.803 | 0.000 |
| pressure_pa | 1h | thermometer | 1 | 5.769 | -0.000 | -3.928 | 0.835 | 0.000 |
| pressure_pa | 1h | anemometer | 1 | 5.766 | 0.000 | -3.926 | 0.836 | 0.000 |
| pressure_pa | 1h | sky opacity | 1 | 5.740 | 0.005 | -3.903 | 0.825 | 0.000 |
| pressure_pa | 1h | barometer+thermometer | 2 | 1.128 | 0.804 | 0.036 | 0.803 | 0.000 |
| pressure_pa | 1h | barometer+anemometer | 2 | 1.130 | 0.804 | 0.035 | 0.807 | 0.000 |
| pressure_pa | 1h | barometer+sky opacity | 2 | 1.127 | 0.804 | 0.037 | 0.795 | 0.000 |
| pressure_pa | 1h | thermometer+anemometer | 2 | 5.770 | -0.000 | -3.929 | 0.828 | 0.000 |
| pressure_pa | 1h | thermometer+sky opacity | 2 | 5.736 | 0.005 | -3.900 | 0.819 | 0.000 |
| pressure_pa | 1h | anemometer+sky opacity | 2 | 5.740 | 0.005 | -3.904 | 0.818 | 0.000 |
| pressure_pa | 1h | barometer+thermometer+anemometer | 3 | 1.129 | 0.804 | 0.036 | 0.806 | 0.000 |
| pressure_pa | 1h | barometer+thermometer+sky opacity | 3 | 1.127 | 0.805 | 0.037 | 0.797 | 0.000 |
| pressure_pa | 1h | barometer+anemometer+sky opacity | 3 | 1.128 | 0.804 | 0.036 | 0.801 | 0.000 |
| pressure_pa | 1h | thermometer+anemometer+sky opacity | 3 | 5.738 | 0.005 | -3.902 | 0.820 | 0.000 |
| pressure_pa | 1h | barometer+thermometer+anemometer+sky opacity | 4 | 1.127 | 0.805 | 0.037 | 0.803 | 0.000 |
| pressure_pa | 1h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 1.172 | 0.797 | -0.001 | — | — |
| pressure_pa | 3h | baseline:climatology | 0 | 5.798 | 0.000 | -2.335 | — | — |
| pressure_pa | 3h | baseline:persistence | 0 | 8.251 | -0.423 | -3.746 | — | — |
| pressure_pa | 3h | baseline:anomaly_persistence | 0 | 1.738 | 0.700 | 0.000 | — | — |
| pressure_pa | 3h | clock | 0 | 5.798 | 0.000 | -2.335 | 0.824 | 0.000 |
| pressure_pa | 3h | barometer | 1 | 1.655 | 0.715 | 0.048 | 0.804 | 0.000 |
| pressure_pa | 3h | thermometer | 1 | 5.793 | 0.001 | -2.332 | 0.825 | 0.000 |
| pressure_pa | 3h | anemometer | 1 | 5.794 | 0.001 | -2.332 | 0.830 | 0.000 |
| pressure_pa | 3h | sky opacity | 1 | 5.773 | 0.004 | -2.321 | 0.815 | 0.000 |
| pressure_pa | 3h | barometer+thermometer | 2 | 1.653 | 0.715 | 0.049 | 0.806 | 0.000 |
| pressure_pa | 3h | barometer+anemometer | 2 | 1.656 | 0.714 | 0.048 | 0.798 | 0.000 |
| pressure_pa | 3h | barometer+sky opacity | 2 | 1.656 | 0.714 | 0.048 | 0.789 | 0.000 |
| pressure_pa | 3h | thermometer+anemometer | 2 | 5.793 | 0.001 | -2.332 | 0.823 | 0.000 |
| pressure_pa | 3h | thermometer+sky opacity | 2 | 5.763 | 0.006 | -2.315 | 0.810 | 0.000 |
| pressure_pa | 3h | anemometer+sky opacity | 2 | 5.775 | 0.004 | -2.322 | 0.816 | 0.000 |
| pressure_pa | 3h | barometer+thermometer+anemometer | 3 | 1.653 | 0.715 | 0.049 | 0.803 | 0.000 |
| pressure_pa | 3h | barometer+thermometer+sky opacity | 3 | 1.651 | 0.715 | 0.050 | 0.787 | 0.000 |
| pressure_pa | 3h | barometer+anemometer+sky opacity | 3 | 1.661 | 0.714 | 0.045 | 0.787 | 0.000 |
| pressure_pa | 3h | thermometer+anemometer+sky opacity | 3 | 5.766 | 0.005 | -2.317 | 0.802 | 0.000 |
| pressure_pa | 3h | barometer+thermometer+anemometer+sky opacity | 4 | 1.656 | 0.714 | 0.048 | 0.783 | 0.000 |
| pressure_pa | 3h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 1.695 | 0.708 | 0.025 | — | — |
| pressure_pa | 6h | baseline:climatology | 0 | 5.851 | 0.000 | -0.938 | — | — |
| pressure_pa | 6h | baseline:persistence | 0 | 15.408 | -1.633 | -4.103 | — | — |
| pressure_pa | 6h | baseline:anomaly_persistence | 0 | 3.019 | 0.484 | 0.000 | — | — |
| pressure_pa | 6h | clock | 0 | 5.851 | 0.000 | -0.938 | 0.800 | 0.000 |
| pressure_pa | 6h | barometer | 1 | 2.662 | 0.545 | 0.118 | 0.808 | 0.000 |
| pressure_pa | 6h | thermometer | 1 | 5.845 | 0.001 | -0.936 | 0.791 | 0.000 |
| pressure_pa | 6h | anemometer | 1 | 5.846 | 0.001 | -0.936 | 0.798 | 0.000 |
| pressure_pa | 6h | sky opacity | 1 | 5.833 | 0.003 | -0.932 | 0.800 | 0.000 |
| pressure_pa | 6h | barometer+thermometer | 2 | 2.654 | 0.546 | 0.121 | 0.810 | 0.000 |
| pressure_pa | 6h | barometer+anemometer | 2 | 2.664 | 0.545 | 0.118 | 0.808 | 0.000 |
| pressure_pa | 6h | barometer+sky opacity | 2 | 2.660 | 0.545 | 0.119 | 0.801 | 0.000 |
| pressure_pa | 6h | thermometer+anemometer | 2 | 5.843 | 0.001 | -0.935 | 0.794 | 0.000 |
| pressure_pa | 6h | thermometer+sky opacity | 2 | 5.819 | 0.005 | -0.927 | 0.805 | 0.000 |
| pressure_pa | 6h | anemometer+sky opacity | 2 | 5.834 | 0.003 | -0.932 | 0.804 | 0.000 |
| pressure_pa | 6h | barometer+thermometer+anemometer | 3 | 2.655 | 0.546 | 0.121 | 0.809 | 0.000 |
| pressure_pa | 6h | barometer+thermometer+sky opacity | 3 | 2.644 | 0.548 | 0.124 | 0.806 | 0.000 |
| pressure_pa | 6h | barometer+anemometer+sky opacity | 3 | 2.661 | 0.545 | 0.118 | 0.803 | 0.000 |
| pressure_pa | 6h | thermometer+anemometer+sky opacity | 3 | 5.820 | 0.005 | -0.928 | 0.803 | 0.000 |
| pressure_pa | 6h | barometer+thermometer+anemometer+sky opacity | 4 | 2.645 | 0.548 | 0.124 | 0.808 | 0.000 |
| pressure_pa | 6h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 2.739 | 0.532 | 0.093 | — | — |
| air_temp_k | 1h | baseline:climatology | 0 | 2.378 | 0.000 | -1.597 | — | — |
| air_temp_k | 1h | baseline:persistence | 0 | 2.618 | -0.101 | -1.859 | — | — |
| air_temp_k | 1h | baseline:anomaly_persistence | 0 | 0.916 | 0.615 | 0.000 | — | — |
| air_temp_k | 1h | clock | 0 | 2.378 | 0.000 | -1.597 | 0.760 | 0.000 |
| air_temp_k | 1h | barometer | 1 | 2.376 | 0.001 | -1.594 | 0.759 | 0.000 |
| air_temp_k | 1h | thermometer | 1 | 0.909 | 0.618 | 0.007 | 0.813 | 0.000 |
| air_temp_k | 1h | anemometer | 1 | 2.378 | 0.000 | -1.597 | 0.750 | 0.000 |
| air_temp_k | 1h | sky opacity | 1 | 1.881 | 0.209 | -1.055 | 0.763 | 0.000 |
| air_temp_k | 1h | barometer+thermometer | 2 | 0.908 | 0.618 | 0.008 | 0.814 | 0.000 |
| air_temp_k | 1h | barometer+anemometer | 2 | 2.375 | 0.001 | -1.594 | 0.756 | 0.000 |
| air_temp_k | 1h | barometer+sky opacity | 2 | 1.874 | 0.212 | -1.046 | 0.761 | 0.000 |
| air_temp_k | 1h | thermometer+anemometer | 2 | 0.910 | 0.617 | 0.006 | 0.814 | 0.000 |
| air_temp_k | 1h | thermometer+sky opacity | 2 | 0.911 | 0.617 | 0.005 | 0.785 | 0.000 |
| air_temp_k | 1h | anemometer+sky opacity | 2 | 1.881 | 0.209 | -1.054 | 0.754 | 0.000 |
| air_temp_k | 1h | barometer+thermometer+anemometer | 3 | 0.910 | 0.618 | 0.006 | 0.814 | 0.000 |
| air_temp_k | 1h | barometer+thermometer+sky opacity | 3 | 0.912 | 0.617 | 0.004 | 0.784 | 0.000 |
| air_temp_k | 1h | barometer+anemometer+sky opacity | 3 | 1.875 | 0.212 | -1.048 | 0.754 | 0.000 |
| air_temp_k | 1h | thermometer+anemometer+sky opacity | 3 | 0.910 | 0.617 | 0.006 | 0.788 | 0.000 |
| air_temp_k | 1h | barometer+thermometer+anemometer+sky opacity | 4 | 0.911 | 0.617 | 0.005 | 0.794 | 0.000 |
| air_temp_k | 1h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 0.940 | 0.605 | -0.026 | — | — |
| air_temp_k | 3h | baseline:climatology | 0 | 2.308 | 0.000 | -0.576 | — | — |
| air_temp_k | 3h | baseline:persistence | 0 | 6.892 | -1.986 | -3.705 | — | — |
| air_temp_k | 3h | baseline:anomaly_persistence | 0 | 1.465 | 0.365 | 0.000 | — | — |
| air_temp_k | 3h | clock | 0 | 2.308 | 0.000 | -0.576 | 0.773 | 0.000 |
| air_temp_k | 3h | barometer | 1 | 2.305 | 0.001 | -0.574 | 0.774 | 0.000 |
| air_temp_k | 3h | thermometer | 1 | 1.461 | 0.367 | 0.002 | 0.816 | 0.000 |
| air_temp_k | 3h | anemometer | 1 | 2.307 | 0.001 | -0.575 | 0.762 | 0.000 |
| air_temp_k | 3h | sky opacity | 1 | 1.936 | 0.161 | -0.322 | 0.775 | 0.000 |
| air_temp_k | 3h | barometer+thermometer | 2 | 1.458 | 0.368 | 0.005 | 0.820 | 0.000 |
| air_temp_k | 3h | barometer+anemometer | 2 | 2.305 | 0.001 | -0.574 | 0.766 | 0.000 |
| air_temp_k | 3h | barometer+sky opacity | 2 | 1.933 | 0.162 | -0.320 | 0.774 | 0.000 |
| air_temp_k | 3h | thermometer+anemometer | 2 | 1.467 | 0.364 | -0.002 | 0.819 | 0.000 |
| air_temp_k | 3h | thermometer+sky opacity | 2 | 1.462 | 0.367 | 0.002 | 0.770 | 0.000 |
| air_temp_k | 3h | anemometer+sky opacity | 2 | 1.937 | 0.161 | -0.323 | 0.767 | 0.000 |
| air_temp_k | 3h | barometer+thermometer+anemometer | 3 | 1.463 | 0.366 | 0.001 | 0.817 | 0.000 |
| air_temp_k | 3h | barometer+thermometer+sky opacity | 3 | 1.463 | 0.366 | 0.001 | 0.764 | 0.000 |
| air_temp_k | 3h | barometer+anemometer+sky opacity | 3 | 1.935 | 0.162 | -0.321 | 0.762 | 0.000 |
| air_temp_k | 3h | thermometer+anemometer+sky opacity | 3 | 1.463 | 0.366 | 0.001 | 0.774 | 0.000 |
| air_temp_k | 3h | barometer+thermometer+anemometer+sky opacity | 4 | 1.463 | 0.366 | 0.001 | 0.775 | 0.000 |
| air_temp_k | 3h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 1.459 | 0.368 | 0.004 | — | — |
| air_temp_k | 6h | baseline:climatology | 0 | 2.104 | 0.000 | 0.000 | — | — |
| air_temp_k | 6h | baseline:persistence | 0 | 15.009 | -6.134 | -6.134 | — | — |
| air_temp_k | 6h | baseline:anomaly_persistence | 0 | 2.148 | -0.021 | -0.021 | — | — |
| air_temp_k | 6h | clock | 0 | 2.104 | 0.000 | 0.000 | 0.783 | 0.000 |
| air_temp_k | 6h | barometer | 1 | 2.091 | 0.006 | 0.006 | 0.786 | 0.000 |
| air_temp_k | 6h | thermometer | 1 | 2.138 | -0.016 | -0.016 | 0.827 | 0.000 |
| air_temp_k | 6h | anemometer | 1 | 2.107 | -0.001 | -0.001 | 0.778 | 0.000 |
| air_temp_k | 6h | sky opacity | 1 | 2.060 | 0.021 | 0.021 | 0.760 | 0.000 |
| air_temp_k | 6h | barometer+thermometer | 2 | 2.132 | -0.013 | -0.013 | 0.823 | 0.000 |
| air_temp_k | 6h | barometer+anemometer | 2 | 2.096 | 0.004 | 0.004 | 0.784 | 0.000 |
| air_temp_k | 6h | barometer+sky opacity | 2 | 2.051 | 0.025 | 0.025 | 0.757 | 0.000 |
| air_temp_k | 6h | thermometer+anemometer | 2 | 2.148 | -0.021 | -0.021 | 0.825 | 0.000 |
| air_temp_k | 6h | thermometer+sky opacity | 2 | 2.001 | 0.049 | 0.049 | 0.814 | 0.000 |
| air_temp_k | 6h | anemometer+sky opacity | 2 | 2.061 | 0.020 | 0.020 | 0.759 | 0.000 |
| air_temp_k | 6h | barometer+thermometer+anemometer | 3 | 2.141 | -0.018 | -0.018 | 0.823 | 0.000 |
| air_temp_k | 6h | barometer+thermometer+sky opacity | 3 | 1.999 | 0.050 | 0.050 | 0.815 | 0.000 |
| air_temp_k | 6h | barometer+anemometer+sky opacity | 3 | 2.053 | 0.024 | 0.024 | 0.757 | 0.000 |
| air_temp_k | 6h | thermometer+anemometer+sky opacity | 3 | 2.002 | 0.049 | 0.049 | 0.806 | 0.000 |
| air_temp_k | 6h | barometer+thermometer+anemometer+sky opacity | 4 | 1.996 | 0.051 | 0.051 | 0.806 | 0.000 |
| air_temp_k | 6h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 1.863 | 0.115 | 0.115 | — | — |
| wind_ms | 1h | baseline:climatology | 0 | 1.082 | 0.000 | 0.000 | — | — |
| wind_ms | 1h | baseline:persistence | 0 | 1.530 | -0.414 | -0.414 | — | — |
| wind_ms | 1h | baseline:anomaly_persistence | 0 | 1.509 | -0.395 | -0.395 | — | — |
| wind_ms | 1h | clock | 0 | 1.082 | 0.000 | 0.000 | 0.824 | 0.000 |
| wind_ms | 1h | barometer | 1 | 1.082 | 0.000 | 0.000 | 0.825 | 0.000 |
| wind_ms | 1h | thermometer | 1 | 1.082 | -0.000 | -0.000 | 0.823 | 0.000 |
| wind_ms | 1h | anemometer | 1 | 1.256 | -0.161 | -0.161 | 0.810 | 0.000 |
| wind_ms | 1h | sky opacity | 1 | 1.081 | 0.001 | 0.001 | 0.808 | 0.000 |
| wind_ms | 1h | barometer+thermometer | 2 | 1.082 | 0.000 | 0.000 | 0.824 | 0.000 |
| wind_ms | 1h | barometer+anemometer | 2 | 1.256 | -0.161 | -0.161 | 0.810 | 0.000 |
| wind_ms | 1h | barometer+sky opacity | 2 | 1.081 | 0.001 | 0.001 | 0.813 | 0.000 |
| wind_ms | 1h | thermometer+anemometer | 2 | 1.256 | -0.161 | -0.161 | 0.812 | 0.000 |
| wind_ms | 1h | thermometer+sky opacity | 2 | 1.085 | -0.003 | -0.003 | 0.817 | 0.000 |
| wind_ms | 1h | anemometer+sky opacity | 2 | 1.256 | -0.161 | -0.161 | 0.799 | 0.000 |
| wind_ms | 1h | barometer+thermometer+anemometer | 3 | 1.257 | -0.162 | -0.162 | 0.809 | 0.000 |
| wind_ms | 1h | barometer+thermometer+sky opacity | 3 | 1.083 | -0.001 | -0.001 | 0.818 | 0.000 |
| wind_ms | 1h | barometer+anemometer+sky opacity | 3 | 1.256 | -0.161 | -0.161 | 0.794 | 0.000 |
| wind_ms | 1h | thermometer+anemometer+sky opacity | 3 | 1.258 | -0.163 | -0.163 | 0.794 | 0.000 |
| wind_ms | 1h | barometer+thermometer+anemometer+sky opacity | 4 | 1.258 | -0.162 | -0.162 | 0.797 | 0.000 |
| wind_ms | 1h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 1.281 | -0.184 | -0.184 | — | — |
| wind_ms | 3h | baseline:climatology | 0 | 1.110 | 0.000 | 0.000 | — | — |
| wind_ms | 3h | baseline:persistence | 0 | 2.042 | -0.840 | -0.840 | — | — |
| wind_ms | 3h | baseline:anomaly_persistence | 0 | 1.548 | -0.395 | -0.395 | — | — |
| wind_ms | 3h | clock | 0 | 1.110 | 0.000 | 0.000 | 0.805 | 0.000 |
| wind_ms | 3h | barometer | 1 | 1.110 | -0.000 | -0.000 | 0.804 | 0.000 |
| wind_ms | 3h | thermometer | 1 | 1.110 | -0.001 | -0.001 | 0.808 | 0.000 |
| wind_ms | 3h | anemometer | 1 | 1.267 | -0.142 | -0.142 | 0.805 | 0.000 |
| wind_ms | 3h | sky opacity | 1 | 1.111 | -0.001 | -0.001 | 0.804 | 0.000 |
| wind_ms | 3h | barometer+thermometer | 2 | 1.110 | -0.001 | -0.001 | 0.804 | 0.000 |
| wind_ms | 3h | barometer+anemometer | 2 | 1.268 | -0.142 | -0.142 | 0.800 | 0.000 |
| wind_ms | 3h | barometer+sky opacity | 2 | 1.109 | 0.000 | 0.000 | 0.798 | 0.000 |
| wind_ms | 3h | thermometer+anemometer | 2 | 1.268 | -0.143 | -0.143 | 0.800 | 0.000 |
| wind_ms | 3h | thermometer+sky opacity | 2 | 1.111 | -0.001 | -0.001 | 0.801 | 0.000 |
| wind_ms | 3h | anemometer+sky opacity | 2 | 1.265 | -0.140 | -0.140 | 0.793 | 0.000 |
| wind_ms | 3h | barometer+thermometer+anemometer | 3 | 1.269 | -0.143 | -0.143 | 0.797 | 0.000 |
| wind_ms | 3h | barometer+thermometer+sky opacity | 3 | 1.109 | 0.001 | 0.001 | 0.794 | 0.000 |
| wind_ms | 3h | barometer+anemometer+sky opacity | 3 | 1.266 | -0.141 | -0.141 | 0.789 | 0.000 |
| wind_ms | 3h | thermometer+anemometer+sky opacity | 3 | 1.265 | -0.140 | -0.140 | 0.790 | 0.000 |
| wind_ms | 3h | barometer+thermometer+anemometer+sky opacity | 4 | 1.266 | -0.141 | -0.141 | 0.789 | 0.000 |
| wind_ms | 3h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 1.315 | -0.185 | -0.185 | — | — |
| wind_ms | 6h | baseline:climatology | 0 | 1.073 | 0.000 | 0.000 | — | — |
| wind_ms | 6h | baseline:persistence | 0 | 2.892 | -1.694 | -1.694 | — | — |
| wind_ms | 6h | baseline:anomaly_persistence | 0 | 1.487 | -0.386 | -0.386 | — | — |
| wind_ms | 6h | clock | 0 | 1.073 | 0.000 | 0.000 | 0.820 | 0.000 |
| wind_ms | 6h | barometer | 1 | 1.072 | 0.001 | 0.001 | 0.819 | 0.000 |
| wind_ms | 6h | thermometer | 1 | 1.071 | 0.002 | 0.002 | 0.818 | 0.000 |
| wind_ms | 6h | anemometer | 1 | 1.213 | -0.130 | -0.130 | 0.821 | 0.000 |
| wind_ms | 6h | sky opacity | 1 | 1.073 | 0.000 | 0.000 | 0.816 | 0.000 |
| wind_ms | 6h | barometer+thermometer | 2 | 1.071 | 0.002 | 0.002 | 0.817 | 0.000 |
| wind_ms | 6h | barometer+anemometer | 2 | 1.213 | -0.130 | -0.130 | 0.825 | 0.000 |
| wind_ms | 6h | barometer+sky opacity | 2 | 1.073 | -0.000 | -0.000 | 0.816 | 0.000 |
| wind_ms | 6h | thermometer+anemometer | 2 | 1.212 | -0.129 | -0.129 | 0.822 | 0.000 |
| wind_ms | 6h | thermometer+sky opacity | 2 | 1.072 | 0.001 | 0.001 | 0.811 | 0.000 |
| wind_ms | 6h | anemometer+sky opacity | 2 | 1.217 | -0.134 | -0.134 | 0.825 | 0.000 |
| wind_ms | 6h | barometer+thermometer+anemometer | 3 | 1.213 | -0.130 | -0.130 | 0.824 | 0.000 |
| wind_ms | 6h | barometer+thermometer+sky opacity | 3 | 1.073 | 0.001 | 0.001 | 0.807 | 0.000 |
| wind_ms | 6h | barometer+anemometer+sky opacity | 3 | 1.219 | -0.136 | -0.136 | 0.822 | 0.000 |
| wind_ms | 6h | thermometer+anemometer+sky opacity | 3 | 1.217 | -0.134 | -0.134 | 0.822 | 0.000 |
| wind_ms | 6h | barometer+thermometer+anemometer+sky opacity | 4 | 1.219 | -0.136 | -0.136 | 0.827 | 0.000 |
| wind_ms | 6h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 1.283 | -0.196 | -0.196 | — | — |
| dust_tau | 1h | baseline:climatology | 0 | 0.154 | 0.000 | -5.407 | — | — |
| dust_tau | 1h | baseline:persistence | 0 | 0.024 | 0.844 | 0.000 | — | — |
| dust_tau | 1h | baseline:anomaly_persistence | 0 | 0.024 | 0.842 | -0.010 | — | — |
| dust_tau | 1h | clock | 0 | 0.154 | 0.000 | -5.407 | 0.844 | 0.000 |
| dust_tau | 1h | barometer | 1 | 0.154 | 0.001 | -5.400 | 0.845 | 0.000 |
| dust_tau | 1h | thermometer | 1 | 0.137 | 0.112 | -4.693 | 0.826 | 0.000 |
| dust_tau | 1h | anemometer | 1 | 0.154 | 0.000 | -5.407 | 0.844 | 0.000 |
| dust_tau | 1h | sky opacity | 1 | 0.020 | 0.872 | 0.178 | 0.767 | 0.000 |
| dust_tau | 1h | barometer+thermometer | 2 | 0.137 | 0.113 | -4.686 | 0.822 | 0.000 |
| dust_tau | 1h | barometer+anemometer | 2 | 0.154 | 0.002 | -5.396 | 0.845 | 0.000 |
| dust_tau | 1h | barometer+sky opacity | 2 | 0.020 | 0.872 | 0.176 | 0.763 | 0.000 |
| dust_tau | 1h | thermometer+anemometer | 2 | 0.137 | 0.112 | -4.690 | 0.826 | 0.000 |
| dust_tau | 1h | thermometer+sky opacity | 2 | 0.020 | 0.872 | 0.177 | 0.759 | 0.000 |
| dust_tau | 1h | anemometer+sky opacity | 2 | 0.020 | 0.872 | 0.177 | 0.765 | 0.000 |
| dust_tau | 1h | barometer+thermometer+anemometer | 3 | 0.137 | 0.113 | -4.681 | 0.820 | 0.000 |
| dust_tau | 1h | barometer+thermometer+sky opacity | 3 | 0.020 | 0.871 | 0.176 | 0.758 | 0.000 |
| dust_tau | 1h | barometer+anemometer+sky opacity | 3 | 0.020 | 0.871 | 0.175 | 0.768 | 0.000 |
| dust_tau | 1h | thermometer+anemometer+sky opacity | 3 | 0.020 | 0.872 | 0.177 | 0.762 | 0.000 |
| dust_tau | 1h | barometer+thermometer+anemometer+sky opacity | 4 | 0.020 | 0.871 | 0.175 | 0.768 | 0.000 |
| dust_tau | 1h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 0.021 | 0.863 | 0.121 | — | — |
| dust_tau | 3h | baseline:climatology | 0 | 0.148 | 0.000 | -5.240 | — | — |
| dust_tau | 3h | baseline:persistence | 0 | 0.024 | 0.840 | 0.000 | — | — |
| dust_tau | 3h | baseline:anomaly_persistence | 0 | 0.024 | 0.837 | -0.017 | — | — |
| dust_tau | 3h | clock | 0 | 0.148 | 0.000 | -5.240 | 0.852 | 0.000 |
| dust_tau | 3h | barometer | 1 | 0.147 | 0.006 | -5.200 | 0.850 | 0.000 |
| dust_tau | 3h | thermometer | 1 | 0.136 | 0.082 | -4.729 | 0.822 | 0.000 |
| dust_tau | 3h | anemometer | 1 | 0.149 | -0.005 | -5.274 | 0.850 | 0.000 |
| dust_tau | 3h | sky opacity | 1 | 0.020 | 0.868 | 0.174 | 0.807 | 0.000 |
| dust_tau | 3h | barometer+thermometer | 2 | 0.136 | 0.084 | -4.713 | 0.822 | 0.000 |
| dust_tau | 3h | barometer+anemometer | 2 | 0.148 | 0.001 | -5.235 | 0.852 | 0.000 |
| dust_tau | 3h | barometer+sky opacity | 2 | 0.020 | 0.868 | 0.173 | 0.807 | 0.000 |
| dust_tau | 3h | thermometer+anemometer | 2 | 0.136 | 0.081 | -4.735 | 0.828 | 0.000 |
| dust_tau | 3h | thermometer+sky opacity | 2 | 0.020 | 0.867 | 0.172 | 0.811 | 0.000 |
| dust_tau | 3h | anemometer+sky opacity | 2 | 0.020 | 0.868 | 0.176 | 0.801 | 0.000 |
| dust_tau | 3h | barometer+thermometer+anemometer | 3 | 0.136 | 0.084 | -4.718 | 0.824 | 0.000 |
| dust_tau | 3h | barometer+thermometer+sky opacity | 3 | 0.020 | 0.867 | 0.171 | 0.807 | 0.000 |
| dust_tau | 3h | barometer+anemometer+sky opacity | 3 | 0.020 | 0.868 | 0.174 | 0.809 | 0.000 |
| dust_tau | 3h | thermometer+anemometer+sky opacity | 3 | 0.020 | 0.867 | 0.173 | 0.803 | 0.000 |
| dust_tau | 3h | barometer+thermometer+anemometer+sky opacity | 4 | 0.020 | 0.867 | 0.171 | 0.794 | 0.000 |
| dust_tau | 3h | challenger:gbm:barometer+thermometer+anemometer+sky opacity | 4 | 0.021 | 0.855 | 0.098 | — | — |
| dust_tau | 6h | baseline:climatology | 0 | 0.148 | 0.000 | -5.501 | — | — |
| dust_tau | 6h | baseline:persistence | 0 | 0.023 | 0.846 | 0.000 | — | — |
| dust_tau | 6h | baseline:anomaly_persistence | 0 | 0.023 | 0.846 | -0.004 | — | — |
| dust_tau | 6h | clock | 0 | 0.148 | 0.000 | -5.501 | 0.842 | 0.000 |
| dust_tau | 6h | barometer | 1 | 0.147 | 0.003 | -5.484 | 0.854 | 0.000 |
| dust_tau | 6h | thermometer | 1 | 0.144 | 0.023 | -5.350 | 0.754 | 0.000 |
| dust_tau | 6h | anemometer | 1 | 0.150 | -0.012 | -5.582 | 0.842 | 0.000 |
| dust_tau | 6h | barometer+thermometer | 2 | 0.145 | 0.021 | -5.366 | 0.754 | 0.000 |
| dust_tau | 6h | barometer+anemometer | 2 | 0.149 | -0.010 | -5.569 | 0.854 | 0.000 |
| dust_tau | 6h | thermometer+anemometer | 2 | 0.146 | 0.010 | -5.434 | 0.749 | 0.000 |
| dust_tau | 6h | barometer+thermometer+anemometer | 3 | 0.146 | 0.008 | -5.447 | 0.749 | 0.000 |
| dust_tau | 6h | challenger:gbm:barometer+thermometer+anemometer | 3 | 0.025 | 0.828 | -0.116 | — | — |

## Limitations

- One training site: corrections are local and degrade elsewhere (see transfer rows when provided).
- Dust storms are rare in any station record; storm-time skill is not established unless reported separately.
- Bands come from calibration-block residuals and assume the test period behaves like it.
- Advisory only: in the runtime a forecast never changes the plan; observed values do.
