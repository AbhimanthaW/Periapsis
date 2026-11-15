# Forecast evaluation: SYNTHETIC example station (northern mid-latitude)

Model `station-forecast-7a4048bd8aab7aef` · provenance **simulated** · blocks: 630 train / 157 calibration / 103 selection / 157 held-out test sols

## Selected kit per target and horizon

| Target | Horizon | Status | Kit (fewest sensors) | Skill vs climatology | Skill vs best baseline | ML adds? | P10–P90 coverage | Test n |
|---|---|---|---|---:|---:|---|---:|---:|
| pressure_pa | 1h | climatology | clock | 0.000 | -3.926 | no, persistence | 0.811 | 3585 |
| pressure_pa | 3h | climatology | clock | 0.000 | -2.335 | no, persistence | 0.810 | 3582 |
| pressure_pa | 6h | model | barometer | 0.536 | 0.092 | yes | 0.831 | 3577 |
| air_temp_k | 1h | climatology | clock | 0.000 | -1.336 | no, persistence | 0.786 | 3538 |
| air_temp_k | 3h | model | thermometer | 0.266 | -0.014 | no, persistence | 0.792 | 3538 |
| air_temp_k | 6h | climatology | clock | 0.000 | 0.000 | no, persistence | 0.788 | 3535 |
| wind_ms | 1h | climatology | clock | 0.000 | 0.000 | no, persistence | 0.813 | 3563 |
| wind_ms | 3h | climatology | clock | 0.000 | 0.000 | no, persistence | 0.814 | 3557 |
| wind_ms | 6h | climatology | clock | 0.000 | 0.000 | no, persistence | 0.813 | 3556 |
| dust_tau | 1h | climatology | clock | 0.000 | -5.632 | no, persistence | 0.827 | 942 |
| dust_tau | 3h | climatology | clock | 0.000 | -5.723 | no, persistence | 0.825 | 628 |
| dust_tau | 6h | climatology | clock | 0.000 | -5.868 | no, persistence | 0.822 | 157 |

## Every kit and baseline on the common held-out test set

Kits use the clock fallback when sensors are missing or outside the training range.

| Target | Horizon | Kit | Sensors | MAE | Skill vs climatology | Skill vs best baseline | Coverage | Abstain |
|---|---|---|---:|---:|---:|---:|---:|---:|
| pressure_pa | 1h | baseline:climatology | 0 | 5.793 | 0.000 | -3.926 | — | — |
| pressure_pa | 1h | baseline:persistence | 0 | 2.054 | 0.645 | -0.747 | — | — |
| pressure_pa | 1h | baseline:anomaly_persistence | 0 | 1.176 | 0.797 | 0.000 | — | — |
| pressure_pa | 1h | clock | 0 | 5.793 | 0.000 | -3.926 | 0.811 | 0.000 |
| pressure_pa | 1h | barometer | 1 | 1.232 | 0.787 | -0.047 | 0.813 | 0.024 |
| pressure_pa | 1h | thermometer | 1 | 5.785 | 0.001 | -3.919 | 0.815 | 0.060 |
| pressure_pa | 1h | anemometer | 1 | 5.789 | 0.001 | -3.923 | 0.818 | 0.054 |
| pressure_pa | 1h | sky opacity | 1 | 5.788 | 0.001 | -3.921 | 0.815 | 0.747 |
| pressure_pa | 1h | barometer+thermometer | 2 | 1.477 | 0.745 | -0.256 | 0.816 | 0.082 |
| pressure_pa | 1h | barometer+anemometer | 2 | 1.481 | 0.744 | -0.259 | 0.811 | 0.077 |
| pressure_pa | 1h | barometer+sky opacity | 2 | 4.645 | 0.198 | -2.950 | 0.807 | 0.752 |
| pressure_pa | 1h | thermometer+anemometer | 2 | 5.785 | 0.001 | -3.919 | 0.815 | 0.111 |
| pressure_pa | 1h | thermometer+sky opacity | 2 | 5.786 | 0.001 | -3.920 | 0.813 | 0.760 |
| pressure_pa | 1h | anemometer+sky opacity | 2 | 5.788 | 0.001 | -3.922 | 0.809 | 0.759 |
| pressure_pa | 1h | barometer+thermometer+anemometer | 3 | 1.712 | 0.704 | -0.456 | 0.816 | 0.133 |
| pressure_pa | 1h | barometer+thermometer+sky opacity | 3 | 4.697 | 0.189 | -2.994 | 0.807 | 0.765 |
| pressure_pa | 1h | barometer+anemometer+sky opacity | 3 | 4.696 | 0.189 | -2.993 | 0.807 | 0.763 |
| pressure_pa | 1h | thermometer+anemometer+sky opacity | 3 | 5.787 | 0.001 | -3.921 | 0.808 | 0.771 |
| pressure_pa | 1h | barometer+thermometer+anemometer+sky opacity | 4 | 4.747 | 0.181 | -3.036 | 0.809 | 0.776 |
| pressure_pa | 3h | baseline:climatology | 0 | 5.793 | 0.000 | -2.335 | — | — |
| pressure_pa | 3h | baseline:persistence | 0 | 5.164 | 0.109 | -1.973 | — | — |
| pressure_pa | 3h | baseline:anomaly_persistence | 0 | 1.737 | 0.700 | 0.000 | — | — |
| pressure_pa | 3h | clock | 0 | 5.793 | 0.000 | -2.335 | 0.810 | 0.000 |
| pressure_pa | 3h | barometer | 1 | 1.757 | 0.697 | -0.012 | 0.804 | 0.024 |
| pressure_pa | 3h | thermometer | 1 | 5.780 | 0.002 | -2.328 | 0.818 | 0.059 |
| pressure_pa | 3h | anemometer | 1 | 5.790 | 0.000 | -2.334 | 0.822 | 0.054 |
| pressure_pa | 3h | sky opacity | 1 | 5.788 | 0.001 | -2.333 | 0.809 | 0.747 |
| pressure_pa | 3h | barometer+thermometer | 2 | 1.972 | 0.660 | -0.136 | 0.811 | 0.082 |
| pressure_pa | 3h | barometer+anemometer | 2 | 1.966 | 0.661 | -0.132 | 0.805 | 0.077 |
| pressure_pa | 3h | barometer+sky opacity | 2 | 4.754 | 0.179 | -1.737 | 0.804 | 0.752 |
| pressure_pa | 3h | thermometer+anemometer | 2 | 5.781 | 0.002 | -2.329 | 0.814 | 0.111 |
| pressure_pa | 3h | thermometer+sky opacity | 2 | 5.785 | 0.001 | -2.331 | 0.808 | 0.759 |
| pressure_pa | 3h | anemometer+sky opacity | 2 | 5.789 | 0.001 | -2.333 | 0.807 | 0.758 |
| pressure_pa | 3h | barometer+thermometer+anemometer | 3 | 2.171 | 0.625 | -0.250 | 0.813 | 0.132 |
| pressure_pa | 3h | barometer+thermometer+sky opacity | 3 | 4.800 | 0.171 | -1.764 | 0.803 | 0.765 |
| pressure_pa | 3h | barometer+anemometer+sky opacity | 3 | 4.796 | 0.172 | -1.762 | 0.805 | 0.763 |
| pressure_pa | 3h | thermometer+anemometer+sky opacity | 3 | 5.787 | 0.001 | -2.332 | 0.805 | 0.770 |
| pressure_pa | 3h | barometer+thermometer+anemometer+sky opacity | 4 | 4.841 | 0.164 | -1.788 | 0.803 | 0.775 |
| pressure_pa | 6h | baseline:climatology | 0 | 5.791 | 0.000 | -0.956 | — | — |
| pressure_pa | 6h | baseline:persistence | 0 | 8.673 | -0.498 | -1.929 | — | — |
| pressure_pa | 6h | baseline:anomaly_persistence | 0 | 2.961 | 0.489 | 0.000 | — | — |
| pressure_pa | 6h | clock | 0 | 5.791 | 0.000 | -0.956 | 0.810 | 0.000 |
| pressure_pa | 6h | barometer | 1 | 2.688 | 0.536 | 0.092 | 0.831 | 0.024 |
| pressure_pa | 6h | thermometer | 1 | 5.768 | 0.004 | -0.948 | 0.813 | 0.060 |
| pressure_pa | 6h | anemometer | 1 | 5.790 | 0.000 | -0.956 | 0.817 | 0.055 |
| pressure_pa | 6h | sky opacity | 1 | 5.788 | 0.001 | -0.955 | 0.814 | 0.748 |
| pressure_pa | 6h | barometer+thermometer | 2 | 2.847 | 0.508 | 0.038 | 0.826 | 0.083 |
| pressure_pa | 6h | barometer+anemometer | 2 | 2.835 | 0.510 | 0.043 | 0.831 | 0.078 |
| pressure_pa | 6h | barometer+sky opacity | 2 | 4.981 | 0.140 | -0.682 | 0.814 | 0.752 |
| pressure_pa | 6h | thermometer+anemometer | 2 | 5.771 | 0.004 | -0.949 | 0.816 | 0.113 |
| pressure_pa | 6h | thermometer+sky opacity | 2 | 5.783 | 0.001 | -0.953 | 0.813 | 0.761 |
| pressure_pa | 6h | anemometer+sky opacity | 2 | 5.789 | 0.000 | -0.955 | 0.813 | 0.759 |
| pressure_pa | 6h | barometer+thermometer+anemometer | 3 | 2.986 | 0.484 | -0.008 | 0.829 | 0.134 |
| pressure_pa | 6h | barometer+thermometer+sky opacity | 3 | 5.014 | 0.134 | -0.693 | 0.814 | 0.766 |
| pressure_pa | 6h | barometer+anemometer+sky opacity | 3 | 5.020 | 0.133 | -0.695 | 0.816 | 0.763 |
| pressure_pa | 6h | thermometer+anemometer+sky opacity | 3 | 5.783 | 0.001 | -0.953 | 0.812 | 0.772 |
| pressure_pa | 6h | barometer+thermometer+anemometer+sky opacity | 4 | 5.053 | 0.128 | -0.706 | 0.816 | 0.777 |
| air_temp_k | 1h | baseline:climatology | 0 | 2.176 | 0.000 | -1.336 | — | — |
| air_temp_k | 1h | baseline:persistence | 0 | 3.977 | -0.827 | -3.269 | — | — |
| air_temp_k | 1h | baseline:anomaly_persistence | 0 | 0.931 | 0.572 | 0.000 | — | — |
| air_temp_k | 1h | clock | 0 | 2.176 | 0.000 | -1.336 | 0.786 | 0.000 |
| air_temp_k | 1h | barometer | 1 | 2.171 | 0.003 | -1.330 | 0.789 | 0.049 |
| air_temp_k | 1h | thermometer | 1 | 0.971 | 0.554 | -0.043 | 0.809 | 0.031 |
| air_temp_k | 1h | anemometer | 1 | 2.177 | -0.000 | -1.337 | 0.778 | 0.052 |
| air_temp_k | 1h | sky opacity | 1 | 2.061 | 0.053 | -1.212 | 0.786 | 0.747 |
| air_temp_k | 1h | barometer+thermometer | 2 | 1.016 | 0.533 | -0.091 | 0.812 | 0.077 |
| air_temp_k | 1h | barometer+anemometer | 2 | 2.172 | 0.002 | -1.331 | 0.783 | 0.099 |
| air_temp_k | 1h | barometer+sky opacity | 2 | 2.059 | 0.054 | -1.211 | 0.786 | 0.757 |
| air_temp_k | 1h | thermometer+anemometer | 2 | 1.030 | 0.527 | -0.105 | 0.807 | 0.082 |
| air_temp_k | 1h | thermometer+sky opacity | 2 | 1.839 | 0.155 | -0.974 | 0.785 | 0.754 |
| air_temp_k | 1h | anemometer+sky opacity | 2 | 2.061 | 0.053 | -1.213 | 0.784 | 0.758 |
| air_temp_k | 1h | barometer+thermometer+anemometer | 3 | 1.073 | 0.507 | -0.152 | 0.809 | 0.127 |
| air_temp_k | 1h | barometer+thermometer+sky opacity | 3 | 1.851 | 0.149 | -0.987 | 0.784 | 0.764 |
| air_temp_k | 1h | barometer+anemometer+sky opacity | 3 | 2.060 | 0.053 | -1.212 | 0.784 | 0.768 |
| air_temp_k | 1h | thermometer+anemometer+sky opacity | 3 | 1.848 | 0.151 | -0.984 | 0.785 | 0.765 |
| air_temp_k | 1h | barometer+thermometer+anemometer+sky opacity | 4 | 1.859 | 0.146 | -0.996 | 0.785 | 0.775 |
| air_temp_k | 3h | baseline:climatology | 0 | 2.163 | 0.000 | -0.381 | — | — |
| air_temp_k | 3h | baseline:persistence | 0 | 11.526 | -4.328 | -6.357 | — | — |
| air_temp_k | 3h | baseline:anomaly_persistence | 0 | 1.567 | 0.276 | 0.000 | — | — |
| air_temp_k | 3h | clock | 0 | 2.163 | 0.000 | -0.381 | 0.788 | 0.000 |
| air_temp_k | 3h | barometer | 1 | 2.158 | 0.002 | -0.378 | 0.788 | 0.048 |
| air_temp_k | 3h | thermometer | 1 | 1.589 | 0.266 | -0.014 | 0.792 | 0.030 |
| air_temp_k | 3h | anemometer | 1 | 2.163 | 0.000 | -0.381 | 0.779 | 0.054 |
| air_temp_k | 3h | sky opacity | 1 | 2.071 | 0.043 | -0.322 | 0.790 | 0.748 |
| air_temp_k | 3h | barometer+thermometer | 2 | 1.613 | 0.255 | -0.029 | 0.792 | 0.076 |
| air_temp_k | 3h | barometer+anemometer | 2 | 2.159 | 0.002 | -0.378 | 0.786 | 0.100 |
| air_temp_k | 3h | barometer+sky opacity | 2 | 2.072 | 0.042 | -0.322 | 0.789 | 0.759 |
| air_temp_k | 3h | thermometer+anemometer | 2 | 1.614 | 0.254 | -0.030 | 0.794 | 0.084 |
| air_temp_k | 3h | thermometer+sky opacity | 2 | 1.975 | 0.087 | -0.261 | 0.783 | 0.755 |
| air_temp_k | 3h | anemometer+sky opacity | 2 | 2.075 | 0.041 | -0.325 | 0.788 | 0.759 |
| air_temp_k | 3h | barometer+thermometer+anemometer | 3 | 1.639 | 0.242 | -0.046 | 0.792 | 0.128 |
| air_temp_k | 3h | barometer+thermometer+sky opacity | 3 | 1.984 | 0.083 | -0.266 | 0.781 | 0.765 |
| air_temp_k | 3h | barometer+anemometer+sky opacity | 3 | 2.076 | 0.040 | -0.325 | 0.787 | 0.769 |
| air_temp_k | 3h | thermometer+anemometer+sky opacity | 3 | 1.979 | 0.085 | -0.263 | 0.785 | 0.766 |
| air_temp_k | 3h | barometer+thermometer+anemometer+sky opacity | 4 | 1.988 | 0.081 | -0.269 | 0.784 | 0.776 |
| air_temp_k | 6h | baseline:climatology | 0 | 2.167 | 0.000 | 0.000 | — | — |
| air_temp_k | 6h | baseline:persistence | 0 | 21.281 | -8.821 | -8.821 | — | — |
| air_temp_k | 6h | baseline:anomaly_persistence | 0 | 2.258 | -0.042 | -0.042 | — | — |
| air_temp_k | 6h | clock | 0 | 2.167 | 0.000 | 0.000 | 0.788 | 0.000 |
| air_temp_k | 6h | barometer | 1 | 2.159 | 0.004 | 0.004 | 0.786 | 0.048 |
| air_temp_k | 6h | thermometer | 1 | 2.253 | -0.040 | -0.040 | 0.803 | 0.032 |
| air_temp_k | 6h | anemometer | 1 | 2.168 | -0.000 | -0.000 | 0.779 | 0.054 |
| air_temp_k | 6h | sky opacity | 1 | 2.158 | 0.004 | 0.004 | 0.780 | 0.749 |
| air_temp_k | 6h | barometer+thermometer | 2 | 2.238 | -0.033 | -0.033 | 0.801 | 0.077 |
| air_temp_k | 6h | barometer+anemometer | 2 | 2.161 | 0.003 | 0.003 | 0.786 | 0.100 |
| air_temp_k | 6h | barometer+sky opacity | 2 | 2.155 | 0.006 | 0.006 | 0.782 | 0.759 |
| air_temp_k | 6h | thermometer+anemometer | 2 | 2.252 | -0.040 | -0.040 | 0.802 | 0.085 |
| air_temp_k | 6h | thermometer+sky opacity | 2 | 2.160 | 0.003 | 0.003 | 0.790 | 0.756 |
| air_temp_k | 6h | anemometer+sky opacity | 2 | 2.160 | 0.003 | 0.003 | 0.781 | 0.759 |
| air_temp_k | 6h | barometer+thermometer+anemometer | 3 | 2.239 | -0.033 | -0.033 | 0.799 | 0.129 |
| air_temp_k | 6h | barometer+thermometer+sky opacity | 3 | 2.158 | 0.004 | 0.004 | 0.791 | 0.766 |
| air_temp_k | 6h | barometer+anemometer+sky opacity | 3 | 2.156 | 0.005 | 0.005 | 0.781 | 0.769 |
| air_temp_k | 6h | thermometer+anemometer+sky opacity | 3 | 2.159 | 0.004 | 0.004 | 0.788 | 0.767 |
| air_temp_k | 6h | barometer+thermometer+anemometer+sky opacity | 4 | 2.156 | 0.005 | 0.005 | 0.791 | 0.776 |
| wind_ms | 1h | baseline:climatology | 0 | 1.080 | 0.000 | 0.000 | — | — |
| wind_ms | 1h | baseline:persistence | 0 | 1.538 | -0.424 | -0.424 | — | — |
| wind_ms | 1h | baseline:anomaly_persistence | 0 | 1.514 | -0.402 | -0.402 | — | — |
| wind_ms | 1h | clock | 0 | 1.080 | 0.000 | 0.000 | 0.813 | 0.000 |
| wind_ms | 1h | barometer | 1 | 1.079 | 0.000 | 0.000 | 0.813 | 0.049 |
| wind_ms | 1h | thermometer | 1 | 1.080 | -0.000 | -0.000 | 0.812 | 0.061 |
| wind_ms | 1h | anemometer | 1 | 1.230 | -0.139 | -0.139 | 0.818 | 0.027 |
| wind_ms | 1h | sky opacity | 1 | 1.080 | 0.000 | 0.000 | 0.808 | 0.746 |
| wind_ms | 1h | barometer+thermometer | 2 | 1.080 | -0.000 | -0.000 | 0.812 | 0.106 |
| wind_ms | 1h | barometer+anemometer | 2 | 1.219 | -0.129 | -0.129 | 0.817 | 0.075 |
| wind_ms | 1h | barometer+sky opacity | 2 | 1.080 | 0.000 | 0.000 | 0.810 | 0.756 |
| wind_ms | 1h | thermometer+anemometer | 2 | 1.217 | -0.127 | -0.127 | 0.820 | 0.086 |
| wind_ms | 1h | thermometer+sky opacity | 2 | 1.081 | -0.001 | -0.001 | 0.810 | 0.759 |
| wind_ms | 1h | anemometer+sky opacity | 2 | 1.121 | -0.038 | -0.038 | 0.807 | 0.752 |
| wind_ms | 1h | barometer+thermometer+anemometer | 3 | 1.208 | -0.119 | -0.119 | 0.818 | 0.131 |
| wind_ms | 1h | barometer+thermometer+sky opacity | 3 | 1.080 | -0.001 | -0.001 | 0.811 | 0.769 |
| wind_ms | 1h | barometer+anemometer+sky opacity | 3 | 1.119 | -0.036 | -0.036 | 0.807 | 0.762 |
| wind_ms | 1h | thermometer+anemometer+sky opacity | 3 | 1.119 | -0.036 | -0.036 | 0.807 | 0.765 |
| wind_ms | 1h | barometer+thermometer+anemometer+sky opacity | 4 | 1.116 | -0.034 | -0.034 | 0.809 | 0.775 |
| wind_ms | 3h | baseline:climatology | 0 | 1.078 | 0.000 | 0.000 | — | — |
| wind_ms | 3h | baseline:persistence | 0 | 1.808 | -0.677 | -0.677 | — | — |
| wind_ms | 3h | baseline:anomaly_persistence | 0 | 1.524 | -0.415 | -0.415 | — | — |
| wind_ms | 3h | clock | 0 | 1.078 | 0.000 | 0.000 | 0.814 | 0.000 |
| wind_ms | 3h | barometer | 1 | 1.078 | -0.000 | -0.000 | 0.812 | 0.049 |
| wind_ms | 3h | thermometer | 1 | 1.079 | -0.001 | -0.001 | 0.815 | 0.061 |
| wind_ms | 3h | anemometer | 1 | 1.239 | -0.150 | -0.150 | 0.810 | 0.026 |
| wind_ms | 3h | sky opacity | 1 | 1.078 | -0.000 | -0.000 | 0.814 | 0.747 |
| wind_ms | 3h | barometer+thermometer | 2 | 1.079 | -0.001 | -0.001 | 0.814 | 0.105 |
| wind_ms | 3h | barometer+anemometer | 2 | 1.230 | -0.141 | -0.141 | 0.807 | 0.074 |
| wind_ms | 3h | barometer+sky opacity | 2 | 1.077 | 0.000 | 0.000 | 0.813 | 0.756 |
| wind_ms | 3h | thermometer+anemometer | 2 | 1.229 | -0.140 | -0.140 | 0.812 | 0.085 |
| wind_ms | 3h | thermometer+sky opacity | 2 | 1.078 | -0.000 | -0.000 | 0.816 | 0.760 |
| wind_ms | 3h | anemometer+sky opacity | 2 | 1.119 | -0.038 | -0.038 | 0.813 | 0.753 |
| wind_ms | 3h | barometer+thermometer+anemometer | 3 | 1.221 | -0.133 | -0.133 | 0.809 | 0.129 |
| wind_ms | 3h | barometer+thermometer+sky opacity | 3 | 1.077 | 0.000 | 0.000 | 0.815 | 0.770 |
| wind_ms | 3h | barometer+anemometer+sky opacity | 3 | 1.117 | -0.037 | -0.037 | 0.812 | 0.762 |
| wind_ms | 3h | thermometer+anemometer+sky opacity | 3 | 1.115 | -0.034 | -0.034 | 0.814 | 0.766 |
| wind_ms | 3h | barometer+thermometer+anemometer+sky opacity | 4 | 1.113 | -0.033 | -0.033 | 0.813 | 0.775 |
| wind_ms | 6h | baseline:climatology | 0 | 1.079 | 0.000 | 0.000 | — | — |
| wind_ms | 6h | baseline:persistence | 0 | 2.277 | -1.109 | -1.109 | — | — |
| wind_ms | 6h | baseline:anomaly_persistence | 0 | 1.505 | -0.394 | -0.394 | — | — |
| wind_ms | 6h | clock | 0 | 1.079 | 0.000 | 0.000 | 0.813 | 0.000 |
| wind_ms | 6h | barometer | 1 | 1.079 | 0.000 | 0.000 | 0.812 | 0.049 |
| wind_ms | 6h | thermometer | 1 | 1.080 | -0.000 | -0.000 | 0.812 | 0.062 |
| wind_ms | 6h | anemometer | 1 | 1.242 | -0.150 | -0.150 | 0.818 | 0.027 |
| wind_ms | 6h | sky opacity | 1 | 1.079 | 0.000 | 0.000 | 0.812 | 0.748 |
| wind_ms | 6h | barometer+thermometer | 2 | 1.079 | 0.000 | 0.000 | 0.813 | 0.107 |
| wind_ms | 6h | barometer+anemometer | 2 | 1.227 | -0.137 | -0.137 | 0.818 | 0.075 |
| wind_ms | 6h | barometer+sky opacity | 2 | 1.079 | 0.000 | 0.000 | 0.813 | 0.758 |
| wind_ms | 6h | thermometer+anemometer | 2 | 1.228 | -0.138 | -0.138 | 0.817 | 0.087 |
| wind_ms | 6h | thermometer+sky opacity | 2 | 1.079 | 0.000 | 0.000 | 0.810 | 0.761 |
| wind_ms | 6h | anemometer+sky opacity | 2 | 1.117 | -0.034 | -0.034 | 0.816 | 0.754 |
| wind_ms | 6h | barometer+thermometer+anemometer | 3 | 1.214 | -0.125 | -0.125 | 0.820 | 0.131 |
| wind_ms | 6h | barometer+thermometer+sky opacity | 3 | 1.079 | 0.000 | 0.000 | 0.811 | 0.771 |
| wind_ms | 6h | barometer+anemometer+sky opacity | 3 | 1.116 | -0.034 | -0.034 | 0.814 | 0.764 |
| wind_ms | 6h | thermometer+anemometer+sky opacity | 3 | 1.114 | -0.032 | -0.032 | 0.815 | 0.767 |
| wind_ms | 6h | barometer+thermometer+anemometer+sky opacity | 4 | 1.113 | -0.031 | -0.031 | 0.814 | 0.777 |
| dust_tau | 1h | baseline:climatology | 0 | 0.157 | 0.000 | -5.632 | — | — |
| dust_tau | 1h | baseline:persistence | 0 | 0.024 | 0.849 | 0.000 | — | — |
| dust_tau | 1h | baseline:anomaly_persistence | 0 | 0.024 | 0.848 | -0.012 | — | — |
| dust_tau | 1h | clock | 0 | 0.157 | 0.000 | -5.632 | 0.827 | 0.000 |
| dust_tau | 1h | barometer | 1 | 0.157 | 0.001 | -5.628 | 0.829 | 0.040 |
| dust_tau | 1h | thermometer | 1 | 0.142 | 0.097 | -4.992 | 0.806 | 0.062 |
| dust_tau | 1h | anemometer | 1 | 0.157 | -0.000 | -5.632 | 0.827 | 0.043 |
| dust_tau | 1h | sky opacity | 1 | 0.043 | 0.728 | -0.801 | 0.781 | 0.167 |
| dust_tau | 1h | barometer+thermometer | 2 | 0.142 | 0.094 | -5.007 | 0.808 | 0.101 |
| dust_tau | 1h | barometer+anemometer | 2 | 0.157 | 0.001 | -5.623 | 0.828 | 0.084 |
| dust_tau | 1h | barometer+sky opacity | 2 | 0.046 | 0.707 | -0.944 | 0.777 | 0.199 |
| dust_tau | 1h | thermometer+anemometer | 2 | 0.142 | 0.096 | -4.993 | 0.802 | 0.104 |
| dust_tau | 1h | thermometer+sky opacity | 2 | 0.054 | 0.657 | -1.273 | 0.769 | 0.214 |
| dust_tau | 1h | anemometer+sky opacity | 2 | 0.048 | 0.697 | -1.007 | 0.775 | 0.204 |
| dust_tau | 1h | barometer+thermometer+anemometer | 3 | 0.142 | 0.094 | -5.006 | 0.807 | 0.143 |
| dust_tau | 1h | barometer+thermometer+sky opacity | 3 | 0.057 | 0.636 | -1.412 | 0.767 | 0.245 |
| dust_tau | 1h | barometer+anemometer+sky opacity | 3 | 0.051 | 0.676 | -1.151 | 0.776 | 0.236 |
| dust_tau | 1h | thermometer+anemometer+sky opacity | 3 | 0.058 | 0.630 | -1.453 | 0.771 | 0.251 |
| dust_tau | 1h | barometer+thermometer+anemometer+sky opacity | 4 | 0.061 | 0.609 | -1.592 | 0.774 | 0.281 |
| dust_tau | 3h | baseline:climatology | 0 | 0.157 | 0.000 | -5.723 | — | — |
| dust_tau | 3h | baseline:persistence | 0 | 0.023 | 0.851 | 0.000 | — | — |
| dust_tau | 3h | baseline:anomaly_persistence | 0 | 0.024 | 0.848 | -0.021 | — | — |
| dust_tau | 3h | clock | 0 | 0.157 | 0.000 | -5.723 | 0.825 | 0.000 |
| dust_tau | 3h | barometer | 1 | 0.157 | 0.002 | -5.713 | 0.825 | 0.045 |
| dust_tau | 3h | thermometer | 1 | 0.146 | 0.072 | -5.236 | 0.790 | 0.065 |
| dust_tau | 3h | anemometer | 1 | 0.158 | -0.006 | -5.760 | 0.828 | 0.046 |
| dust_tau | 3h | sky opacity | 1 | 0.054 | 0.654 | -1.326 | 0.817 | 0.250 |
| dust_tau | 3h | barometer+thermometer | 2 | 0.147 | 0.068 | -5.266 | 0.790 | 0.110 |
| dust_tau | 3h | barometer+anemometer | 2 | 0.158 | -0.004 | -5.751 | 0.826 | 0.091 |
| dust_tau | 3h | barometer+sky opacity | 2 | 0.058 | 0.629 | -1.492 | 0.819 | 0.282 |
| dust_tau | 3h | thermometer+anemometer | 2 | 0.146 | 0.071 | -5.249 | 0.801 | 0.110 |
| dust_tau | 3h | thermometer+sky opacity | 2 | 0.068 | 0.570 | -1.893 | 0.810 | 0.295 |
| dust_tau | 3h | anemometer+sky opacity | 2 | 0.060 | 0.619 | -1.563 | 0.826 | 0.287 |
| dust_tau | 3h | barometer+thermometer+anemometer | 3 | 0.147 | 0.066 | -5.282 | 0.796 | 0.154 |
| dust_tau | 3h | barometer+thermometer+sky opacity | 3 | 0.072 | 0.545 | -2.059 | 0.809 | 0.326 |
| dust_tau | 3h | barometer+anemometer+sky opacity | 3 | 0.064 | 0.594 | -1.730 | 0.828 | 0.319 |
| dust_tau | 3h | thermometer+anemometer+sky opacity | 3 | 0.072 | 0.539 | -2.096 | 0.814 | 0.330 |
| dust_tau | 3h | barometer+thermometer+anemometer+sky opacity | 4 | 0.076 | 0.515 | -2.263 | 0.806 | 0.361 |
| dust_tau | 6h | baseline:climatology | 0 | 0.157 | 0.000 | -5.868 | — | — |
| dust_tau | 6h | baseline:persistence | 0 | 0.023 | 0.854 | -0.001 | — | — |
| dust_tau | 6h | baseline:anomaly_persistence | 0 | 0.023 | 0.854 | 0.000 | — | — |
| dust_tau | 6h | clock | 0 | 0.157 | 0.000 | -5.868 | 0.822 | 0.000 |
| dust_tau | 6h | barometer | 1 | 0.157 | -0.000 | -5.871 | 0.828 | 0.051 |
| dust_tau | 6h | thermometer | 1 | 0.156 | 0.006 | -5.826 | 0.739 | 0.083 |
| dust_tau | 6h | anemometer | 1 | 0.158 | -0.008 | -5.926 | 0.822 | 0.038 |
| dust_tau | 6h | barometer+thermometer | 2 | 0.155 | 0.009 | -5.803 | 0.733 | 0.134 |
| dust_tau | 6h | barometer+anemometer | 2 | 0.158 | -0.008 | -5.926 | 0.834 | 0.089 |
| dust_tau | 6h | thermometer+anemometer | 2 | 0.156 | 0.004 | -5.839 | 0.752 | 0.121 |
| dust_tau | 6h | barometer+thermometer+anemometer | 3 | 0.156 | 0.005 | -5.831 | 0.745 | 0.172 |

## Limitations

- One training site: corrections are local and degrade elsewhere (see transfer rows when provided).
- Dust storms are rare in any station record; storm-time skill is not established unless reported separately.
- Bands come from calibration-block residuals and assume the test period behaves like it.
- Advisory only: in the runtime a forecast never changes the plan; observed values do.
