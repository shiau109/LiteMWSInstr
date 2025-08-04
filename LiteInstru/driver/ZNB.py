import numpy as np
import matplotlib.pyplot as plt
from qcodes.instrument_drivers.rohde_schwarz import (
    RohdeSchwarzZNB20,
    RohdeSchwarzZNBChannel,
)
from qcodes.dataset.measurements import Measurement

class VNA_ZNB20:
    def __init__(self, address: str):
        self.address = address
        try:
            self.vna = RohdeSchwarzZNB20('VNA', address, timeout=300)
            print(f'Connected to: {self.vna.IDN()}')
        except Exception as e:
            print(f"Connection error: {e}")
    
    def check_error(self):
        # Check for errors
        pass

    def delete_all_traces(self):
        self.vna.clear_channels()
    
    def setup_measurement(self, parameter: str):
        self.vna.add_channel(parameter)
        self.current_channel = parameter

    def set_linfreq(self, start: float, stop: float):
        getattr(self.vna.channels, self.current_channel).start(start)
        getattr(self.vna.channels, self.current_channel).stop(stop)

    def set_data_format(self):
        self.vna.write('FORMAT:DATA REAL,64')

    def set_sweep_points(self, points: int):
        getattr(self.vna.channels, self.current_channel).npts(points)

    def set_IF_bandwidth(self, bandwidth: int):
        getattr(self.vna.channels, self.current_channel).bandwidth(bandwidth)

    def get_data(self):
        magnitude_phase_data = getattr(self.vna.channels, self.current_channel).trace_db_phase.get()
        magnitudes_db = magnitude_phase_data[0]
        phases = magnitude_phase_data[1]
        magnitudes_linear = 10**(magnitudes_db/20)

        real_parts = magnitudes_linear * np.cos(phases)
        imaginary_parts = magnitudes_linear * np.sin(phases)
        data = real_parts + 1j*imaginary_parts
        return data

    def set_power(self, power: float):
        getattr(self.vna.channels, self.current_channel).power(power)

    def measure(self):
        self.vna.rf_on()
        self.vna.channels.avg(1)
        meas = Measurement()
        meas.register_parameter(getattr(self.vna.channels, self.current_channel).trace_db_phase)

    def lin_freq_sweep(self, start, stop, points: int, port, power: float = -20, IF_bandwith: int = 1000):
        
        self.delete_all_traces()
        self.setup_measurement(port)
        self.set_power(power)
        self.set_IF_bandwidth(IF_bandwith)
        self.set_linfreq(start, stop)
        self.set_sweep_points(points)

        self.measure()
        data = self.get_data()

        start_freq = getattr(self.vna.channels, self.current_channel).start()
        stop_freq = getattr(self.vna.channels, self.current_channel).stop()
        num_points = getattr(self.vna.channels, self.current_channel).npts()
        
        freq_array = np.linspace(start_freq, stop_freq, num_points)
        s21_data = data
        return freq_array, s21_data

    def disconnect(self):
        self.vna.close()
        print("VNA_ZNB20 object connection is closed.")

    def __del__(self):
        print("VNA_ZNB20 object has been deleted")
        try:
            self.disconnect()
        except AttributeError:
            print("self.disconnect() failed.")
            pass

if __name__ == '__main__':
    address = 'TCPIP0::192.168.50.249::inst0::INSTR'
    vna = VNA_ZNB20(address)

    start_freq = 5e9
    stop_freq = 7e9
    points = 1001
    port = "S21"
    power = -20
    IF_bandwidth = 1000

    freq, data = vna.lin_freq_sweep(start_freq, stop_freq, points, port, power, IF_bandwidth)

    plt.plot(freq, 20 * np.log10(np.abs(data)))
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Magnitude (dB)')
    plt.title('S21 Magnitude')
    plt.show()

    vna.disconnect()
