""" White looking with the brand 'Angilent Technologies' """
from LiteInstru.driver.MXA import MXA

class N9020A(MXA):
    def __init__(self, address:str, name:str="Angilent_SA"):
        super().__init__(name,address=address)
    
    def return_model_type(self)->str:
        return "N9020A"
    
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
    

