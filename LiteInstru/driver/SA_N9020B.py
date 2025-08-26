""" Black looking with the brand 'Keysight' """
from LiteInstru.driver.MXA import MXA, mean_traces_in_dBm

class N9020B(MXA):
    def __init__(self, address:str, name:str="Keysight_SA"):
        super().__init__(name,address=address)
    
    def return_model_type(self)->str:
        return "N9020B"
    
    def span_freq_sweep(self, center_freq:float|int, span_freq:float|int, res_bandwidth:float|int, sweep_pts:int|str="auto", repeat:int=1)->dict:
        repeat_data = []
        try:
            # safety & clear states
            self.write("*CLS")      # clear errors
            self.write(":ABOR")     # abort any ongoing operation
            self.write("*WAI")      # wait previous ops
            self.set_center_frequency(center_freq)
            self.set_rbw(res_bandwidth)
            self.set_span(span_freq)
            if isinstance(sweep_pts,int):
                self.set_sweep_pts(sweep_pts)
            else:
                self.auto_set_sweep_points()

            if repeat == 1:
                trace = self.single_sweep()
                repeat_data.append(trace)
            else:
                trace = self.power_averaged_scan(avg_counts=repeat)
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
    
    file_name = 'pumpon_noise'
    folder = "/home/ratiswu/Kaohy_TWPA/SilentWave_A1823/pumpingOn"
    pumping_attr = {"pumping_freq":7010.3e6, "pumping_power":-10.23}
    repeat = 100


    ip = "192.168.1.20"
    address = f'TCPIP0::{ip}::inst0::INSTR'
   
    SA = N9020B(address)
    data = SA.span_freq_sweep(center_freq=6e9,span_freq=6e9,res_bandwidth=1e6,repeat=repeat,sweep_pts=6001)
    

    ################################################################################################################

    SA.shut_down()
    Dr = Datar()
    Dr.data = array(data["data"][0])
    Dr.file_name = file_name
    Dr.file_folder = folder
    Dr.coordinates = {"frequency":array(data["freq"])}
    Dr.attributes = {"model":"N9020B","IP":"192.168.1.20","repeat":repeat} 
    Dr.attributes.update(pumping_attr)
    file_loc = Dr.save()

    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('TkAgg')
    plt.plot(array(data['freq'])*1e-9, data['data'][0])
    
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("Power (dBm)")
    plt.title(file_name)
    plt.grid()
    plt.savefig(os.path.join(Dr.file_folder,f"{file_name}.png"))
    plt.close()
