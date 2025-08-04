from driver.MXA import MXA

class N9080A(MXA):
    def __init__(self, address:str):
        super().__init__(name="Keysight_SAA",address=address)

    def span_freq_sweep(self, center_freq:float|int, span_freq:float|int, res_bandwidth:float|int, sweep_pts:int, repeat:int=1):
        self.set_center_frequency(center_freq)
        self.set_rbw(res_bandwidth)
        self.set_span(span_freq)
        self.set_sweep_pts(sweep_pts)

        repeat_data = []
        for re in range(repeat):
            self.single_sweep()
            repeat_data.append(self.trace_data())

        
        print(repeat_data)
        print(self.get_freq_samples())

        self.shut_down()


if __name__ == "__main__":
    ip = ""
    address = f'TCPIP0::{ip}::inst0::INSTR'
    SA = N9080A(address)
    SA.span_freq_sweep(center_freq=6e9,span_freq=1e6,res_bandwidth=0.5e6,sweep_pts=1001)