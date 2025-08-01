import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np
import matplotlib.pyplot as plt
import xarray as xr
from datetime import datetime
from os import makedirs
from os.path import exists
import tomlkit
from driver import get_VNA
from driver.RSsgs100A import sgs100A

config_path = '/home/ratiswu/Documents/GitHub/LiteVNA/Worker/TWPA_tuneUp_request.toml'

# Assuming 'config.toml' is your file
with open(config_path, 'r') as file:
    content = file.read()
    sweepLF_config = tomlkit.parse(content)

vna_address = sweepLF_config["hardware"]["VNA"]["address"]
vna_model = sweepLF_config["hardware"]["VNA"]["model"]
vna_port = sweepLF_config["hardware"]["VNA"]["port"]

measurements = sweepLF_config["measurement"]
pumpings = sweepLF_config["pumping"]
attenuation = sweepLF_config["hardware"]["VNA"]["attenuation"]

pump_freqs = np.linspace(int(pumpings["frequency"]["start"]),int(pumpings["frequency"]["stop"]), int(pumpings["frequency"]["points"]))
pump_powers = np.linspace(int(pumpings["power"]["start"]),int(pumpings["power"]["stop"]), int(pumpings["power"]["points"]))

every_freq_data = [] # shape = (pump_freq, pump_power, repeat, ro_freq)
start_time = datetime.now()
vna = get_VNA(vna_address,vna_model)
vna.check_error()
SG = sgs100A(sweepLF_config["hardware"]["SG"]["address"])
for p_freq in pump_freqs:
    every_power_data = [] # shape = (pump_power, repeat, ro_freq)
    for p_power in pump_powers:
        print(f"Pumping: {round(p_freq*1e-6,1)} MHz, {round(p_power)} dBm")
        SG.CW_output(frequency_Hz=p_freq, power_dBm=p_power)
        
        every_raw_data = [] # shape (repeat, freq)
        for m_task in measurements: # ASSUME ONLY ONE TASK

            output_folder = m_task["output"]
            label = m_task["label"]

            freq_start = m_task["frequency"]["start"]
            freq_stop = m_task["frequency"]["stop"]
            sweep_point = m_task["frequency"]["points"]
            vna_power = m_task["power"]

            IF_bandwidth = m_task["frequency"]["points"]
            repeat = m_task["repeat"]
            IF_bandwidth = m_task["IF_bandwidth"]
            for i in range(repeat):
                print(f"measurement: {i}/{repeat}")
                # Set start and stop frequencies
                freq_array, s_params  = vna.lin_freq_sweep( freq_start, freq_stop, sweep_point, vna_port, power=vna_power, IF_bandwith=IF_bandwidth)
                s_params:np.ndarray
                every_raw_data.append(s_params.tolist())
        SG.CW_shutdown()       
                
        every_power_data.append(every_raw_data) 
    every_freq_data.append(every_power_data)  
end_time = datetime.now()
dataset = xr.Dataset(
    {"s21": ( ["pump_freq","pump_power","repeat","RO_frequency"],np.array(every_freq_data))},
    coords={ "pump_freq":pump_freqs, "pump_power":pump_powers, "repeat":np.arange(repeat), "RO_frequency": freq_array}
)

dataset.attrs["IF_bandwidth"] = IF_bandwidth
dataset.attrs["power"] = vna_power
dataset.attrs["attenuation"] = attenuation

dataset.attrs["start_time"] = str(start_time.strftime("%Y%m%d_%H%M%S"))
dataset.attrs["end_time"] = str(end_time.strftime("%Y%m%d_%H%M%S"))

if not exists(output_folder):
    makedirs(output_folder)
    print(f"Create subfolder {output_folder} in result!")

dataset.to_netcdf( f"{output_folder}\\{label}_{start_time.strftime('%Y%m%d_%H%M%S')}.nc",auto_complex=True)
dataset.close()


