""" White looking with the brand 'Angilent Technologies' """
from LiteInstru.driver.MXA import MXA

class N9020A(MXA):
    def __init__(self, address:str):
        super().__init__(name="Angilent_SA",address=address)
        
    
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
    ip = "192.168.1.21"
    address = f'TCPIP0::{ip}::inst0::INSTR'
    SA = N9020A(address)
    data = SA.span_freq_sweep(center_freq=6e9,span_freq=1e9,res_bandwidth=0.8e4)
    SA.shut_down()
    Dr = Datar()
    Dr.data = data["data"]
    Dr.file_name = "test"
    Dr.file_folder = "."
    Dr.coordinates = {"frequency":array(data["freq"]), "repeat":arange(data["repeat"])}
    Dr.attributes = {"note":"This is a dataset only for test."}
    file_loc = Dr.save()
    print(file_loc)

    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('TkAgg')
    plt.plot(data['freq'], data['data'][0])
    plt.show()
