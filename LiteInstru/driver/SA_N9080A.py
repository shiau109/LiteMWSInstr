from LiteInstru.driver.MXA import MXA
import pyvisa

class N9080A(MXA):
    def __init__(self, address:str):
        super().__init__(name="Keysight_SAA",address=address)
        
    
    def span_freq_sweep(self, center_freq:float|int, span_freq:float|int, res_bandwidth:float|int, sweep_pts:int, repeat:int=1):
        try:
            self.set_center_frequency(center_freq)
            self.set_rbw(res_bandwidth)
            self.set_span(span_freq)
            self.set_sweep_pts(sweep_pts)

            repeat_data = []
            for re in range(repeat):
                print(f"Starting to sweep {re+1}/{repeat}")
                trace = self.single_sweep()
                repeat_data.append(trace)

            
            print(repeat_data)
            freqs = self.get_freq_samples()
        except pyvisa.errors.VisaIOError as e:
            print(f"Connection failed: {e}")

        self.shut_down()
        return freqs, repeat_data, 


if __name__ == "__main__":
    ip = "192.168.1.21"
    address = f'TCPIP0::{ip}::inst0::INSTR'
    SA = N9080A(address)
    x, y = SA.span_freq_sweep(center_freq=6e9,span_freq=1e9,res_bandwidth=0.8e4,sweep_pts=501)
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('TkAgg')
    plt.plot(x, y[0])
    plt.show()
