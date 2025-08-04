import pyvisa
import numpy as np
import time
from .VNA import VNA
class VNA_DUMMY( VNA ):

    def __init__(self, address):
        self.address = address
        print(f'Connected to: {format(address)}')

    @property
    def inst(self) -> str:
        return "dummy"


    def disconnect(self):
        print("VNA_E5080B object connection is closed.")

    def __del__(self):
        print("VNA_E5080B object has been deleted")
        try:
            self.disconnect()

        except AttributeError:
            # In case __inst was not initialized correctly
            print("self.disconnect() failed.")
            pass


    def lin_freq_sweep( self, start, stop, points:int, port:str="s21", power:float=-20):



        start_freq = start
        stop_freq = stop
        num_points = points
        # # Generate the frequency array
        freq_array = np.linspace(start_freq, stop_freq, num_points)
        sim_data = np.exp( (-1e-9+1e-8j)*freq_array)
        # iqdata = np.array([sim_data.real,sim_data.imag])
        return freq_array, sim_data