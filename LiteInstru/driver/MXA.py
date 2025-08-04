from abc import ABC, abstractmethod
from qcodes.instrument.visa import VisaInstrument
from numpy import ndarray, linspace
class MXA(VisaInstrument):

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)
        self.marker = None
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
    
    def set_marker(self, freq_hz):
        self.write(":CALC:MARK1:MODE POS")
        self.write(f":CALC:MARK1:X {freq_hz}")
        self.marker = freq_hz

    def set_reference_level(self, ref_level_dbm):
        self.write(f":DISP:WIND:TRAC:Y:RLEV {ref_level_dbm}")

    def single_sweep(self):
        self.write(":INIT:CONT OFF")
        self.write(":INIT")
        self.write("*WAI")

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
    

