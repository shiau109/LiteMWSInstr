import os
from LiteInstru.driver.MXA import mean_traces_in_dBm
from numpy import array
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import pandas as pd
from xarray import open_dataset
from scipy.ndimage import gaussian_filter1d

baseline_data = '/home/ratiswu/liteVNA_test/QuantWareW23A5_NEWpumpoff/no5_noise_pumpoff.csv'
pump_data = '/home/ratiswu/liteVNA_test/QuantWareW23A5_7200MHz_m24dBm/no5_noise_pumpon.csv'

pp_ds = open_dataset(pump_data)
pump_freq = pp_ds.attrs["pumping_freq"]
pump_power = pp_ds.attrs["pumping_power"]
power_on = mean_traces_in_dBm(array(pp_ds.data['data']))  # dBm -> W -> RMS average -> dBm
freq = array(pp_ds.coords["frequency"])
pp_ds.close()

bp_ds = open_dataset(baseline_data)
power_off = mean_traces_in_dBm(array(bp_ds.data['data']))
bp_ds.close()


noise_diff = power_on - power_off
dicts = {}
for idx, fr in enumerate(freq):
    dicts[str(fr)] = float(noise_diff[idx])

pd.DataFrame.from_dict(dicts,orient='index').to_csv(os.path.join(os.path.split(pump_data)[0],"noise_diff.csv"))

fig, axes = plt.subplots(2,1)
ax0:Axes = axes[0]
ax0.plot(freq, power_off, label='pump off', c='blue')
ax0.plot(freq, power_on, label=f"pump by {round(pump_freq*1e-6,1)} MHz, {pump_power} dBm", c='red')
ax0.grid()
ax0.legend()
ax0.set_xlabel("Frequency (GHz)")
ax0.set_ylabel("Power (dBm)")
ax1:Axes = axes[1]
ax1.plot(freq, power_on - power_off,c='black')
ax1.plot(freq, gaussian_filter1d(noise_diff, sigma=100),c='cyan')
ax1.set_xlabel("Frequency (GHz)")
ax1.set_ylabel("Differences (dB)")
ax1.grid()
plt.tight_layout()

plt.savefig(os.path.join(os.path.split(pump_data)[0],"Noise_diff.png"))
plt.close()

