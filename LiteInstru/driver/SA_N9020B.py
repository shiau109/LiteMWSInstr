""" Black looking with the brand 'Keysight' """
from LiteInstru.driver.MXA import MXA

class N9020B(MXA):
    def __init__(self, address:str, name:str="Keysight_SA"):
        super().__init__(name,address=address)
        
    
    def span_freq_sweep(self, center_freq:float|int, span_freq:float|int, res_bandwidth:float|int, sweep_pts:int|str="auto", repeat:int=1)->dict:
        repeat_data = []
        try:
            self.set_center_frequency(center_freq)
            self.set_rbw(res_bandwidth)
            self.set_span(span_freq)
            if isinstance(sweep_pts,int):
                self.set_sweep_pts(sweep_pts)
            else:
                self.auto_set_sweep_points()

            for re in range(repeat):
                print(f"Starting to sweep {re+1}/{repeat}")
                trace = self.single_sweep()
                repeat_data.append(trace)

            freqs = self.get_freq_samples()
        except Exception as e:
            freqs = []
            self.shut_down()
            print("An error was caught as the following: ")
            import traceback
            traceback.print_exc()

        return {"freq":freqs, "data":repeat_data, "repeat":repeat}
    
    
    


if __name__ == "__main__":
    from LiteInstru.DataContainer.DataCenter import Datar
    from numpy import array, arange
    import os
    
    file_name = 'Bypass'
    folder = "/home/ratiswu/Kaohy_TWPA/Bypass1"


    ip = "192.168.1.20"
    address = f'TCPIP0::{ip}::inst0::INSTR'
    
    SA = N9020B(address)
    data = SA.span_freq_sweep(center_freq=6e9,span_freq=6e9,res_bandwidth=1e6,repeat=10,sweep_pts=6001)

    ################################################################################################################



    SA.shut_down()
    Dr = Datar()
    Dr.data = data["data"]
    Dr.file_name = file_name
    Dr.file_folder = folder
    Dr.coordinates = {"repeat":arange(data['repeat']),"frequency":array(data["freq"])}
    Dr.attributes = {"model":"N9020B","IP":"192.168.1.20"}
    file_loc = Dr.save()

    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('TkAgg')
    if array(data['data']).shape[0] > 1:
        plt.plot(array(data['freq'])*1e-9, SA.mean_traces_in_dBm(data['data']))
    else:
        plt.plot(array(data['freq'])*1e-9, data['data'][0])
    
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("Power (dBm)")
    plt.title(file_name)
    plt.grid()
    plt.savefig(os.path.join(Dr.file_folder,f"{file_name}.png"))
    plt.close()
