import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import xarray as xr



file_path = "/home/ratiswu/liteVNA_test/TWPA_TuneUP_W23A5/TWPA_20250731_171114.nc"


# Analysis
dataset = xr.open_dataset(file_path)
data = np.array(dataset.s21.data) # shape (pump_freq, pump_power, repeat, ro_freq)
pump_freq = np.expand_dims(np.array(dataset.coords["pump_freq"]),-1)
pump_power = np.expand_dims(np.array(dataset.coords["pump_power"]),-1)
repeat = np.array(dataset.coords["repeat"])
all_data = []
for f_idx in range(pump_freq.shape[0]):
    p_data = []
    for p_idx in range(pump_power.shape[0]):
        amp = []
        for i in repeat:
            amps = []
            for k in np.array(data[f_idx][p_idx][i]):
                amps.append(20*np.log10(np.abs(k[0]+1j*k[1])))
            amp.append(np.average(amps).tolist())
        p_data.append(np.average(np.array(amp)).tolist())
    all_data.append(p_data)
        
power, freq = np.meshgrid( pump_power.flatten(),pump_freq.flatten()) 

matplotlib.use('TkAgg')
plt.pcolormesh(freq.transpose()*1e-6,power.transpose(),np.array(all_data).transpose(),shading='auto')
plt.title("Pump parameter mapping")
plt.xlabel("Frequency (MHz)")
plt.ylabel("Power (dBm)")
plt.colorbar(label='S21 (dB)')
plt.grid()
plt.tight_layout()
plt.savefig(os.path.join(os.path.split(file_path)[0],"TWPA_TuneUP.png"))
plt.show()
# plt.close()
