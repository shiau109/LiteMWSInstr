import os, json
import numpy as np
import xarray as xr
from datetime import datetime
from os import makedirs
from os.path import exists
import tomlkit
from LiteInstru.driver import get_SA, get_SG 
from LiteInstru.DataContainer.DataCenter import Datar


config_path = '/Users/ratiswu/Documents/GitHub/LiteVNA/LiteInstru/Job_request/TWPA_tuneUp_request.toml'

# Assuming 'config.toml' is your file
with open(config_path, 'r') as file:
    content = file.read()
    config = tomlkit.parse(content)

info = config["Job_info"]

SA_address, SA_model = config["Hardware"]["SA"]["address"], config["Hardware"]["SA"]["model"]
ROSG_address, ROSG_model = config["Hardware"]["ROSG"]["address"], config["Hardware"]["ROSG"]["model"]
PPSG_address, PPSG_model = config["Hardware"]["PPSG"]["address"], config["Hardware"]["PPSG"]["model"]

SA = get_SA(f"TCPIP0::{SA_address}::inst0::INSTR", SA_model, name = "SA")
PPSG = get_SG(f"TCPIP0::{PPSG_address}::inst0::INSTR", PPSG_model, name = "ppsg")
ROSG = get_SG(f"TCPIP0::{ROSG_address}::inst0::INSTR", ROSG_model, name = "rosg")

pumping_conds = config["Pumping"]
pump_freqs = np.linspace(pumping_conds["frequency"]['start'],pumping_conds["frequency"]['stop'],pumping_conds["frequency"]['points'])
pump_power = np.linspace(pumping_conds["power"]['start'],pumping_conds["power"]['stop'],pumping_conds["power"]['points'])

for ro_location in config["Readout"]:
    ro_freq, ro_power = config["Readout"][ro_location]['RO_freq'], config["Readout"][ro_location]['power']
    raw_data_folder = os.path.join(config["Readout"][ro_location]['output'],config["Readout"][ro_location]['label'])
    data_path = {}
    
    if not exists(raw_data_folder):
        makedirs(raw_data_folder)

    Dr = Datar()
    Dr.file_folder = raw_data_folder
    
    ### Gain ###
    ## pump off
    ROSG.CW_output(ro_freq, ro_power)
    data = SA.span_freq_sweep(center_freq=ro_freq,span_freq=config["Readout"][ro_location]['span_freq'],res_bandwidth=config["Readout"][ro_location]['res_band'],repeat=config["Readout"][ro_location]['repeat'])
    
    Dr.data = data["data"]
    Dr.file_name = "pump_off_POWER"
    Dr.coordinates = {"repeat":np.arange(data['repeat']),"frequency":np.array(data["freq"])}
    Dr.attributes = {"SA_model":SA_model,"SA_IP":SA_address,"ROSG_model":ROSG_model,"ROSG_IP":ROSG_address,"RO_power":ro_power,"time":datetime.now().strftime('%y%m%d_%H%M%S')}
    data_path["power_pump_off"] = Dr.save()
    Dr.close_dataset()
    
    ## pump on
    every_freq_data = []
    for pp_freq in pump_freqs:
        every_power_data = []
        for pp_power in pump_power:
            PPSG.CW_output(pp_freq, pp_power)
            data = SA.span_freq_sweep(center_freq=ro_freq,span_freq=config["Readout"][ro_location]['span_freq'],res_bandwidth=config["Readout"][ro_location]['res_band'],repeat=config["Readout"][ro_location]['repeat'])
            PPSG.CW_shutdown()
            every_power_data.append(data['data'])
        every_freq_data.append(every_power_data)
    
    Dr.data = every_freq_data
    Dr.file_name = "pump_on_POWER"
    Dr.coordinates = {"pump_freqs":pump_freqs,"pump_powers":pump_power,"repeat":np.arange(data['repeat']),"frequency":np.array(data["freq"])}
    Dr.attributes = {"SA_model":SA_model,"SA_IP":SA_address,"ROSG_model":ROSG_model,"ROSG_IP":ROSG_address,"RO_power":ro_power,"PPSG_model":PPSG_model,"PPSG_IP":PPSG_address,"time":datetime.now().strftime('%y%m%d_%H%M%S')}
    data_path["power_pump_on"] = Dr.save()
    Dr.close_dataset()
    ROSG.CW_shutdown()
    
    ### Noise ###
    ## pump off
    data = SA.span_freq_sweep(center_freq=ro_freq,span_freq=config["Readout"][ro_location]['span_freq'],res_bandwidth=config["Readout"][ro_location]['res_band'],repeat=config["Readout"][ro_location]['repeat'])
    
    Dr.data = data["data"]
    Dr.file_name = "pump_off_NOISE"
    Dr.coordinates = {"repeat":np.arange(data['repeat']),"frequency":np.array(data["freq"])}
    Dr.attributes = {"SA_model":SA_model,"SA_IP":SA_address,"time":datetime.now().strftime('%y%m%d_%H%M%S')}
    data_path["noise_pump_off"] = Dr.save()
    Dr.close_dataset()

    ## pump on 
    every_freq_data = []
    for pp_freq in pump_freqs:
        every_power_data = []
        for pp_power in pump_power:
            PPSG.CW_output(pp_freq, pp_power)
            data = SA.span_freq_sweep(center_freq=ro_freq,span_freq=config["Readout"][ro_location]['span_freq'],res_bandwidth=config["Readout"][ro_location]['res_band'],repeat=config["Readout"][ro_location]['repeat'])
            PPSG.CW_shutdown()
            every_power_data.append(data['data'])
        every_freq_data.append(every_power_data)
    
    Dr.data = every_freq_data
    Dr.file_name = "pump_on_NOISE"
    Dr.coordinates = {"pump_freqs":pump_freqs,"pump_powers":pump_power,"repeat":np.arange(data['repeat']),"frequency":np.array(data["freq"])}
    Dr.attributes = {"SA_model":SA_model,"SA_IP":SA_address,"PPSG_model":PPSG_model,"PPSG_IP":PPSG_address,"time":datetime.now().strftime('%y%m%d_%H%M%S')}
    data_path["noise_pump_on"] = Dr.save()
    Dr.close_dataset()

    with open(os.path.join(raw_data_folder,"data_descriptions.json"), 'w', encoding='utf-8') as f:
        json.dump(data_path, f, ensure_ascii=False, indent=4)

SA.shut_down()
ROSG.close_connection()
PPSG.close_connection()
