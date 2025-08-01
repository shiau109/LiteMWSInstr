import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from numpy import array, abs, log10
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import xarray as xr
import pandas as pd
from scipy.ndimage import gaussian_filter1d

baseline_data = '/home/ratiswu/liteVNA_test/QuantWareW23A5_NEWpumpoff/TWPA_20250731_173203.nc'
pump_data = '/home/ratiswu/liteVNA_test/QuantWareW23A5_7200MHz_m24dBm/TWPA_20250731_172957.nc'





pump_parameter = pump_data.split("/")[-2].split("_")[-1]
pump_freq = pump_parameter.lower().split("mhz")[0]
pump_power = pump_parameter.lower().split("mhz")[-1].split("dbm")[0].replace("m","-") if "m" in pump_parameter.lower().split("mhz")[-1].split("dbm")[0] else pump_parameter.lower().split("mhz")[-1].split("dbm")[0]
pump_power = str(int(pump_power)/10) if len(pump_power.replace("-",""))==3 else pump_power
ds_pump = xr.open_dataset(pump_data)
IQ_pump = array(ds_pump.s21.data)[0]+array(ds_pump.s21.data)[1]*1j
freq = array(ds_pump.s21.frequency)*1e-9
ds_pump.close()

ds_poff = xr.open_dataset(baseline_data)
IQ_poff = array(ds_poff.s21.data)[0]+array(ds_poff.s21.data)[1]*1j
ds_poff.close()

gain = 20*log10(abs(IQ_pump)) - 20*log10(abs(IQ_poff))
dicts = {}
for idx, fr in enumerate(freq):
    dicts[str(fr)] = float(gain[idx])

df = pd.DataFrame.from_dict(dicts,orient='index').to_csv(os.path.join(os.path.split(pump_data)[0],"gain.csv"))

fig, axes = plt.subplots(2,1)
ax0:Axes = axes[0]
ax0.plot(freq, 20*log10(abs(IQ_poff)), label='pump off', c='blue')
ax0.plot(freq, 20*log10(abs(IQ_pump)), label=f"pump by {pump_freq} MHz, {pump_power} dBm", c='red')
ax0.grid()
ax0.legend()
ax0.set_xlabel("Frequency (GHz)")
ax0.set_ylabel("Amplitude (dBm)")
ax1:Axes = axes[1]
ax1.plot(freq, 20*log10(abs(IQ_pump)) - 20*log10(abs(IQ_poff)),c='black')
ax1.plot(freq, gaussian_filter1d(gain, sigma=100),c='cyan')
ax1.set_xlabel("Frequency (GHz)")
ax1.set_ylabel("Differences (dB)")
ax1.grid()
plt.tight_layout()

plt.savefig(os.path.join(os.path.split(pump_data)[0],"diff.png"))
plt.close()