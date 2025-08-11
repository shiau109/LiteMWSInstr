from abc import ABC, abstractmethod
from qcodes.instrument.visa import VisaInstrument
from numpy import ndarray, linspace
import time
from numpy import array, mean, log10, sqrt

class MXA(VisaInstrument):

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)
        self.marker = None
        self.__ask_time = 0
        self.write_termination = '\n'
        self.read_termination = '\n'
    
    def set_center_frequency(self, freq_hz):
        self.write(f":FREQ:CENT {freq_hz}")
    
    
    def set_span(self, span_hz):
        self.write(f":FREQ:SPAN {span_hz}")
    
    def set_sweep_pts(self, pts:int):
        self.write(f":SWE:POIN {pts}")

    def set_rbw(self, rbw_hz):
        self.write(f":BAND {rbw_hz}")
    
    def auto_set_sweep_points(self):
        points = int(float(self.ask(":FREQ:SPAN?")) / float(self.ask(":BAND?"))) + 1
        if points > 100000:
            points = 100000
        print(f"Automatically set the sweep point = {points}")
        self.set_sweep_pts(points)

    def set_marker(self, freq_hz):
        self.write(":CALC:MARK1:MODE POS")
        self.write(f":CALC:MARK1:X {freq_hz}")
        self.marker = freq_hz

    def set_timeout(self):
        sweep_time = float(self.ask(":SWE:TIME?"))
        self.__ask_time = sweep_time/10
        print(f"total sweep time: {round(sweep_time,1)} secs.")
        self.visa_handle.timeout = int((sweep_time + 10) * 1000)

    def set_reference_level(self, ref_level_dbm):
        self.write(f":DISP:WIND:TRAC:Y:RLEV {ref_level_dbm}")

    def single_sweep(self) -> list:
        self.set_timeout()
        self.write(":INIT:CONT OFF")
        self.write(":INIT")

        # Wait for sweep to complete with progress printing
        print("Sweep started...")
        start_time = time.time()
        max_wait = self.visa_handle.timeout / 1000  # Convert ms to seconds
        poll_interval = self.__ask_time  # seconds between checks
        n = 0 

        while True:
            try:
                status = int(self.ask(":STAT:OPER:COND?"))
            except Exception as e:
                print(f"Status read failed: {e}")
                raise

            elapsed = time.time() - start_time
            print(f"{n} % Completed \r", end='',flush=True)
            n+=10

            if status==0:  # Bit 0 = 1 → operation complete
                print("Sweep complete.")
                break

            if elapsed > max_wait:
                raise TimeoutError(f"Sweep did not complete within {max_wait:.1f} s")

            time.sleep(poll_interval)

        return self.trace_data()

    def peak_search(self):
        self.write(":CALC:MARK:MAX")

    def get_peak_freq(self):
        return float(self.ask(":CALC:MARK:X?"))

    def get_peak_power(self):
        return float(self.ask(":CALC:MARK:Y?"))
    
    def get_marker_power(self):
        return float(self.ask(":CALC:MARK1:Y?"))

    def trace_data(self):
        data_str = self.ask(":TRAC:DATA? TRACE1")
        return [float(v) for v in data_str.split(',')]

    def get_freq_samples(self)->ndarray:
        f_start = float(self.ask(":FREQ:STAR?"))
        f_stop = float(self.ask(":FREQ:STOP?"))
        points = int(self.ask(":SWE:POIN?"))
        return linspace(f_start, f_stop, points)

    def shut_down(self):
        print("SA closed. ")
        self.close()

    def mean_traces_in_dBm(self, traces_dBm, mode:str='rms'):
        '''
        Turn the trace from dBm unit to Watt, then average it by the mode. 
        * mode = 'rms':root mean square. 'mean':mean
        ---
        * traces_dBm shape :(repeat, freqs)
        '''
        
        traces_dBm = array(traces_dBm)  # shape = (N_traces, N_points)
        traces_watt = 10 ** (traces_dBm / 10) * 1e-3  # 轉成 W
        if mode.lower() == 'rms':
            avg_watt = sqrt(mean(traces_watt**2, axis=0))
        else:
            avg_watt = mean(traces_watt, axis=0)
        avg_dBm = 10 * log10(avg_watt * 1e3)
        return avg_dBm
        
    @abstractmethod
    def span_freq_sweep(self, center_freq:float, span_freq:float, **kwargs):
        pass



