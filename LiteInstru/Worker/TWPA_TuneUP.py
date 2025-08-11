import os
import numpy as np
import xarray as xr
from datetime import datetime
from os import makedirs
from os.path import exists
import tomlkit
from LiteInstru.driver import get_SA, get_SG 


config_path = '/Users/ratiswu/Documents/GitHub/LiteVNA/LiteInstru/Job_request/TWPA_tuneUp_request.toml'

# Assuming 'config.toml' is your file
with open(config_path, 'r') as file:
    content = file.read()
    config = tomlkit.parse(content)

info = config["Job_info"]

SA_address, SA_model = config["Hardware"]["SA"]["address"], config["Hardware"]["SA"]["model"]
ROSG_address, ROSG_model = config["Hardware"]["ROSG"]["address"], config["Hardware"]["ROSG"]["model"]
PPSG_address, PPSG_model = config["Hardware"]["PPSG"]["address"], config["Hardware"]["PPSG"]["model"]

SA = get_SA(SA_address, SA_model, name = "SA")
PPSG = get_SG(PPSG_address, PPSG_model, name = "ppsg")
ROSG = get_SG(ROSG_address, ROSG_model, name = "rosg")

measurements = config["Readout"]

pumping_conds = config["Pumping"]
pump_freqs = np.linspace(pumping_conds["frequency"]['start'],pumping_conds["frequency"]['stop'],pumping_conds["frequency"]['points'])
pump_power = np.linspace(pumping_conds["power"]['start'],pumping_conds["power"]['stop'],pumping_conds["power"]['points'])

for ro_location in config["Readout"]:
    ro_freq, ro_power = config["Readout"][ro_location]['RO_freq'], config["Readout"][ro_location]['power']
    raw_data_folder = os.path.join(config["Readout"][ro_location]['output'],config["Readout"][ro_location]['label'])
    if not exists(raw_data_folder):
        makedirs(raw_data_folder)

    ### Gain ###
    ## pump off
    ROSG.CW_output(ro_freq, ro_power)
    SA.set_rbw(config["Readout"][ro_location]['res_band'])
    SA.span_freq_sweep(ro_freq, span_freq=config["Readout"][ro_location]['span_freq'])



    ### Noise ###




"""
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


"""