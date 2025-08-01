import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from numpy import array, abs, log10
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import pandas as pd
from scipy.ndimage import gaussian_filter1d

baseline_data = '/home/ratiswu/liteVNA_test/QuantWareW23A5_NEWpumpoff/no5_noise_pumpoff.csv'
pump_data = '/home/ratiswu/liteVNA_test/QuantWareW23A5_7200MHz_m24dBm/no5_noise_pumpon.csv'

df:dict = pd.read_csv(pump_data,skiprows=range(43)).to_dict()["DATA"]
freq = array(list(df.keys()))*1e-9
power_on = array(list(df.values()))

df_off:dict = pd.read_csv(baseline_data,skiprows=range(43)).to_dict()["DATA"]
power_off = array(list(df_off.values()))


pump_parameter = pump_data.split("/")[-2].split("_")[-1]
pump_freq = pump_parameter.lower().split("mhz")[0]
pump_power = pump_parameter.lower().split("mhz")[-1].split("dbm")[0].replace("m","-") if "m" in pump_parameter.lower().split("mhz")[-1].split("dbm")[0] else pump_parameter.lower().split("mhz")[-1].split("dbm")[0]
pump_power = str(int(pump_power)/10) if len(pump_power.replace("-",""))==3 else pump_power

noise_diff = power_on - power_off
dicts = {}
for idx, fr in enumerate(freq):
    dicts[str(fr)] = float(noise_diff[idx])

pd.DataFrame.from_dict(dicts,orient='index').to_csv(os.path.join(os.path.split(pump_data)[0],"noise_diff.csv"))

fig, axes = plt.subplots(2,1)
ax0:Axes = axes[0]
ax0.plot(freq, power_off, label='pump off', c='blue')
ax0.plot(freq, power_on, label=f"pump by {pump_freq} MHz, {pump_power} dBm", c='red')
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

