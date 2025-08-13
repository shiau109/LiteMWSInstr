from abc import ABC, abstractmethod
from qcodes.instrument.visa import VisaInstrument
from numpy import ndarray, linspace
import time
from numpy import array, mean, log10, sqrt, ndarray

class MXA(VisaInstrument):

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)
        self.marker = None
        self.__ask_time = 0
        self.repeat = 1
        self.print_time:bool = True
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
        if self.print_time:
            print(f"Automatically set the sweep point = {points}")
        self.set_sweep_pts(points)

    def set_marker(self, freq_hz):
        self.write(":CALC:MARK1:MODE POS")
        self.write(f":CALC:MARK1:X {freq_hz}")
        self.marker = freq_hz

    def set_timeout(self, ):
    
        sweep_time = float(self.ask(":SWE:TIME?"))
        self.__ask_time = sweep_time/10
        if self.print_time:
            print(f"total sweep time: {round(self.repeat*sweep_time,1)} secs.")
        self.visa_handle.timeout = int(self.repeat*(sweep_time + 10) * 1000)
        

    def set_reference_level(self, ref_level_dbm):
        self.write(f":DISP:WIND:TRAC:Y:RLEV {ref_level_dbm}")

    def single_sweep(self) -> list:
        self.set_timeout()
        self.write(":INIT:CONT OFF")
        self.write(":INIT")

        # Wait for sweep to complete with progress printing
        if self.print_time:
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
            if self.print_time:
                print(f"{n} % Completed \r", end='',flush=True)
            n+=10

            if status==0:  # Bit 0 = 1 → operation complete
                if self.print_time:
                    print("Sweep complete.")
                break

            if elapsed > max_wait:
                raise TimeoutError(f"Sweep did not complete within {max_wait:.1f} s")

            time.sleep(poll_interval)

        return self.trace_data()
    
    def power_averaged_scan(self, avg_counts:int=10):
        """
        Configure MXA and run averaged sweep, return (freqs, power_dbm).

        Parameters
        ----------
        avg_count : int
            Number of averages for :AVER:COUN
        Returns
        -------
        trace
        """
        
        try:
            self.repeat = avg_counts
            self.set_timeout()
            # Output units: dBm (so trace_data will be in dBm)
            self.write(":UNIT:POWer DBM")

            # Averaging: power average
            self.write(":AVER:TYPE POW")       # use power averaging
            self.write(":AVER:COUN {}".format(avg_counts))
            self.write(":AVER:STAT ON")        # enable averaging
            self.write(":AVER:CLE")            # clear previous averaged data
            
            # Use single-shot mode (non-continuous)
            self.write(":INIT:CONT OFF")

            # Start sweep (in average mode the instrument will perform avg_count sweeps)
            self.write(":INIT")

            # Wait until operation complete.
            # *OPC? blocks until the instrument has finished processing queued commands.
            # For averaged sweeps it's usually reliable. If not supported, use polling of :STAT:OPER:COND?
            self.write("*WAI")

            # Optional small pause to ensure buffer is ready

            values = self.trace_data()

            # turn averaging off if you want subsequent sweeps to be single
            self.write(":AVER:STAT OFF")
            return values
        except Exception as e:
            self.close()
            print("An error was caught as the following: ")
            import traceback
            traceback.print_exc() 

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

        
    @abstractmethod
    def span_freq_sweep(self, center_freq:float, span_freq:float, **kwargs):
        pass
    @abstractmethod
    def return_model_type(self)->str:
        pass


def mean_traces_in_dBm( traces_dBm, mode:str='rms')->ndarray:
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
