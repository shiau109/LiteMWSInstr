import pyvisa
import numpy as np
import time
from .VNA import VNA
class VNA_E5080B( VNA ):

    def __init__(self, address):
        self.address = address
        # Initialize VISA resource manager
        rm = pyvisa.ResourceManager()

        try:
            self.__inst = rm.open_resource(address)
            idn_result = str(self.inst.query('*IDN?'))
            print(f'Connected to: {format(idn_result)}')
            self.__inst.timeout = 2000000

            # Perform a preset operation
            self.__inst.write('*RST')
            self.__inst.write(':SYST:PRES')
            stat = self.inst.write('*CLS')  # Clear buffer memory
            print(f'Clear Status: {stat}')
        except pyvisa.VisaIOError as e:
            print(f"VISA IO Error: {e}")

    @property
    def inst(self) -> pyvisa.resources.Resource:
        return self.__inst


    def _delete_trace(self, trace_name: str=None):
        self.__inst.write(f':CALC:PAR:DEL:ALL')

        # self.__inst.write(f':CALC:PAR:DEL {trace_name}')

    def check_error( self ):
        # Check for errors
        error = self.__inst.query('SYST:ERR?')
        if error != '+0,"No error"':
            print(f"Instrument Error: {error}")

    def _setup_measurement(self, parameter: str):
        self.__inst.write(f':CALC:PAR:DEF:EXT {parameter},{parameter}')
        self.__inst.write(f':CALC:PAR:SEL {parameter}')
        self.__inst.write(f':DISP:WIND:TRAC:FEED {parameter}')

    def _set_linfreq(self, start: float, stop: float):
        self.__inst.write('SENS:SWE:TYPE LINEAR')  # by default: Freq Sweep
        self.__inst.write(f':SENS:FREQ:START {start}')
        self.__inst.write(f':SENS:FREQ:STOP {stop}')

    def _set_data_format(self):
        self.__inst.write('FORMat:BORDer NORMal')
        self.__inst.write("FORMat:DATA real,64")

    def _set_sweep_points(self, points: int):
        self.__inst.write(f':SENS:SWE:POIN {points}')

    def _set_IFbandwidth(self, bandwidth : int):
        self.__inst.write(f':SENS:BANDwidth {bandwidth}')

    
    def _get_data(self):
        self._set_data_format()
        data = self.__inst.query_binary_values('CALC:MEAS:DATA:SDATA?', datatype='d', is_big_endian=True, container=np.array)
        return data

    def _set_power(self, power: float):
        self.__inst.write(f':SOUR:POW {power}')
    
    def _measure( self ):
        self.__inst.write(':TRIG:SOUR MAN')
        self.__inst.write(':INIT:IMM')


    def disconnect(self):
        self.__inst.close()
        print("VNA_E5080B object connection is closed.")

    def __del__(self):
        print("VNA_E5080B object has been deleted")
        try:
            self.disconnect()

        except AttributeError:
            # In case __inst was not initialized correctly
            print("self.disconnect() failed.")
            pass

    def show_all_traces(self):
        traces = self.__inst.query(':CALC:PAR:CAT?')
        print(traces)
        # trace_list = traces.strip().split(',')
        # trace_dict = {trace_list[i]: trace_list[i+1] for i in range(0, len(trace_list), 2)}
        # print("Current Traces in Memory:")
        # for trace, param in trace_dict.items():
        #     print(f"Trace: {trace}, Parameter: {param}")

    def lin_freq_sweep( self, start, stop, points:int, port:str="s21", power:float=-20, IF_bandwith:int=1000):

        self._delete_trace()
        self._setup_measurement(port)
        self._set_power(power)
        self._set_IFbandwidth( IF_bandwith )

        self._set_linfreq( start, stop )
        self._set_sweep_points( points )

        self._measure()
        ready = self.__inst.query("*OPC?")
        print(f"Sweep completed: {ready}")

        # # Read and print the measurement data
        data = self._get_data()

        start_freq = float(self.inst.query(':SENS:FREQ:START?'))
        stop_freq = float(self.inst.query(':SENS:FREQ:STOP?'))
        num_points = int(self.inst.query(':SENS:SWE:POIN?'))
        # # Generate the frequency array
        freq_array = np.linspace(start_freq, stop_freq, num_points)

        # print(freq_array.shape)
        # print(data.shape)    
        iqdata = data.reshape((2,freq_array.shape[-1]), order='F')
        s21_data = iqdata[0]+ 1j*iqdata[1]


        return freq_array, s21_data

if __name__ == '__main__':
    import matplotlib.pyplot as plt
    vna = VNA_E5080B("TCPIP0::192.168.1.78::inst0::INSTR")

    # Set start and stop frequencies
    vna.show_all_traces()
    vna._delete_trace()
    vna.show_all_traces()

    vna._setup_measurement("S21")
    vna.show_all_traces()

    freq, data = vna.lin_freq_sweep(5e9, 7e9, 1001)


    # Perform a single sweep and wait for completion
    # vna.inst.write(':ABOR;:TRIG:SOUR MAN;:INIT:IMM;')

    # Check for errors
    error = vna.inst.query('SYST:ERR?')
    if error != '+0,"No error"':
        print(f"Instrument Error: {error}")



    # # Generate the frequency array

    print(freq.shape)
    print(data.shape)    
    iqdata = data.reshape((2,freq.shape[-1]), order='F')
    iqdata = iqdata[0]+ 1j*iqdata[1]
    plt.plot(freq, 20*np.log10(np.abs(iqdata)))

    plt.show()

