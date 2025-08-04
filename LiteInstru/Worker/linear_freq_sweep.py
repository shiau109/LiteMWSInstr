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

config_path = '/home/ratiswu/Documents/GitHub/LiteVNA/Job_request/measurement_LF.toml'

# Assuming 'config.toml' is your file
with open(config_path, 'r') as file:
    content = file.read()
    sweepLF_config = tomlkit.parse(content)

vna_address = sweepLF_config["hardware"]["address"]
print(vna_address)
vna_model = sweepLF_config["hardware"]["model"]
vna_port = sweepLF_config["hardware"]["port"]

measurements = sweepLF_config["measurement"]
attenuation = sweepLF_config["hardware"]["attenuation"]



vna = get_VNA(vna_address,vna_model)

vna.check_error()

for m_task in measurements:
    print(m_task)

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

        
        start_time = datetime.now()
        freq_array, s_params  = vna.lin_freq_sweep( freq_start, freq_stop, sweep_point, vna_port, power=vna_power, IF_bandwith=IF_bandwidth)
        end_time = datetime.now()
        # Creating an xarray dataset
        output_data = {
            "s21": ( ["s_params","frequency"],
                    np.array([s_params.real, s_params.imag]) )
        }
        dataset = xr.Dataset(
            output_data,
            coords={ "s_params":np.array(["real","imag"]), "frequency": freq_array })
        

        dataset.attrs["IF_bandwidth"] = IF_bandwidth
        dataset.attrs["power"] = vna_power
        dataset.attrs["attenuation"] = attenuation

        dataset.attrs["start_time"] = str(start_time.strftime("%Y%m%d_%H%M%S"))
        dataset.attrs["end_time"] = str(end_time.strftime("%Y%m%d_%H%M%S"))

        if not exists(output_folder):
            makedirs(output_folder)
            print(f"Create subfolder {output_folder} in result!")

        dataset.to_netcdf( f"{output_folder}\\{label}_{start_time.strftime('%Y%m%d_%H%M%S')}.nc")

        # # Generate the frequency array
        plt.plot(freq_array, 20*np.log10(np.abs(s_params)))
        plt.plot(freq_array, np.angle(s_params))
        plt.ylabel("Amp (dB)")
        plt.xlabel("Freq. (Hz)")
        plt.grid()
        plt.savefig(f"{output_folder}/linearSweep.png")
        plt.close()