import os, json
import numpy as np
import xarray as xr
from datetime import datetime
from os import makedirs
from os.path import exists
import tomlkit
from LiteInstru.driver import get_VNA, get_SG 
from LiteInstru.DataContainer.DataCenter import Datar

def TWPA_GainMap(request:str, **kwargs)->str:
    # Assuming 'config.toml' is your file
    with open(request, 'r') as file:
        content = file.read()
        sweepLF_config = tomlkit.parse(content)

    vna_address = sweepLF_config["hardware"]["address"]
    vna_model = sweepLF_config["hardware"]["model"]
    vna_port = sweepLF_config["hardware"]["port"]

    measurements = sweepLF_config["measurement"]
    attenuation = sweepLF_config["hardware"]["attenuation"]

    pump_freqs = np.linspace(sweepLF_config["pumping"][0]["frequency"]['start'], sweepLF_config["pumping"][0]["frequency"]['stop'], sweepLF_config["pumping"][0]["frequency"]['points'])
    pump_powers = np.linspace(sweepLF_config["pumping"][0]["power"]['start'], sweepLF_config["pumping"][0]["power"]['stop'], sweepLF_config["pumping"][0]["power"]['points'])
    five_percent = int(sweepLF_config["pumping"][0]["frequency"]['points'] * sweepLF_config["pumping"][0]["power"]['points']*0.05)

    vna = get_VNA(vna_address,vna_model)
    vna.check_error()
    SG = get_SG(sweepLF_config["pumping"][0]["address"], sweepLF_config["pumping"][0]["SG_model"], sweepLF_config["pumping"][0]["clock"].lower().replace(" ",""))

    every_freq_data = [] # shape = (pump_freq, pump_power, repeat, ro_freq)
    start_time = datetime.now()
    n = 0

    for p_freq in pump_freqs:
        every_power_data = [] # shape = (pump_power, repeat, ro_freq)
        for p_power in pump_powers:
        
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
                    # Set start and stop frequencies
                    freq_array, s_params  = vna.lin_freq_sweep( freq_start, freq_stop, sweep_point, vna_port, power=vna_power, IF_bandwith=IF_bandwidth)
                    s_params:np.ndarray
                    every_raw_data.append(s_params.tolist())
            
            SG.CW_shutdown()  
            
            n += 1     
            if int(n%five_percent) == 0:
                print(f"\r Elapse ~{int(n/five_percent)*5}%", end='', flush=True)
            every_power_data.append(every_raw_data) 
        every_freq_data.append(every_power_data) 
    SG.close_connection() 
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

    file_loc = os.path.join(output_folder,f"{label}_{start_time.strftime('%Y%m%d_%H%M%S')}.nc")
    dataset.to_netcdf( file_loc,auto_complex=True)
    dataset.close()

    return file_loc


if __name__ == "__main__":

    from LiteInstru.TWPA_ana.TWPA_GainSearchAna import TWPA_GainSearch_ana
    request = '/home/ratiswu/Documents/GitHub/LiteVNA/LiteInstru/Job_request/TWPA_GainSearch_request.toml'

    TWPA_GainSearch_ana(TWPA_GainMap(request))
