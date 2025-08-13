from LiteInstru.driver import get_SA
from LiteInstru.DataContainer.DataCenter import Datar
import numpy as np
import tomlkit


def SA_linear_scan(request_loc:str, **kwargs):

    with open(request_loc, 'r') as file:
        content = file.read()
        config = tomlkit.parse(content)

    sa_ip = config["hardware"]["address"]
    
    sa_model = config["hardware"]["model"]
    

    measurements = config["measurement"]
    
    SA = get_SA(f"TCPIP0::{sa_ip}::inst0::INSTR", sa_model)


    for m_task in measurements:

        center_freq = 0.5*(m_task["frequency"]["start"] + m_task["frequency"]["stop"])
        span_freq = np.abs(m_task["frequency"]["start"] - m_task["frequency"]["stop"])
        sweep_point = m_task["frequency"]["points"]
        
        repeat = m_task["repeat"]
        res_bandwidth = m_task["res_bandwidth"]

        if "note" in m_task:
            additional_attris = m_task["note"]
        else:
            additional_attris = {}

        data = SA.span_freq_sweep(center_freq,span_freq,res_bandwidth,repeat,sweep_point)
        SA.shut_down()
    
        Dr = Datar()
        Dr.data = np.array(data["data"][0])
        Dr.file_name = m_task["label"]
        Dr.file_folder = m_task["output"]
        Dr.coordinates = {"frequency":np.array(data["freq"])}
        Dr.attributes = {"model":SA.return_model_type(),"IP":sa_ip,"repeat":repeat} 
        Dr.attributes.update(additional_attris)

        file_loc = Dr.save()

    SA.close()
    

if __name__ == "__main__":

    request = "/Users/ratiswu/Documents/GitHub/LiteVNA/LiteInstru/Job_request/SA_scan_request.toml"

    SA_linear_scan(request)
