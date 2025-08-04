from LiteInstru.driver.MXA import MXA
import pyvisa

class N9080A(MXA):
    def __init__(self, address:str):
        super().__init__(name="Keysight_SAA",address=address)
        
    
    def span_freq_sweep(self, center_freq:float|int, span_freq:float|int, res_bandwidth:float|int, sweep_pts:int|str="auto", repeat:int=1)->dict:
        repeat_data = []
        try:
            self.set_center_frequency(center_freq)
            self.set_rbw(res_bandwidth)
            self.set_span(span_freq)
            if str(sweep_pts).lower() == 'auto':
                self.auto_set_sweep_points()
            else:
                self.set_sweep_pts(sweep_pts)

            for re in range(repeat):
                print(f"Starting to sweep {re+1}/{repeat}")
                trace = self.single_sweep()
                repeat_data.append(trace)

            freqs = self.get_freq_samples()
        except Exception as e:
            freqs = []
            print("An error was caught like the following: ")
            import traceback
            traceback.print_exc()

        self.shut_down()


        return {"freq":freqs, "data":repeat_data}
    


if __name__ == "__main__":
    ip = "192.168.1.21"
    address = f'TCPIP0::{ip}::inst0::INSTR'
    SA = N9080A(address)
    x, y = SA.span_freq_sweep(center_freq=6e9,span_freq=1e9,res_bandwidth=0.8e4)
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('TkAgg')
    plt.plot(x, y[0])
    plt.show()
