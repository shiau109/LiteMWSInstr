from qcodes.instrument_drivers.rohde_schwarz.SGS100A import RohdeSchwarzSGS100A
from .SG import SG

class sgs100A(SG):

    def __init__( self, address:str , name:str="sgs", clock:str="int"):
        self.__sgs = RohdeSchwarzSGS100A(name, address=address)
        try:
            self.set_clock_ref(clock)
        except:
            raise NameError("Clock setting error")
        

    def set_clock_ref( self, clock:str='int'):
        self.__sgs.ref_osc_source(clock)
    
    def CW_output( self, frequency_Hz:float=6e9, power_dBm:float=-20):
        
        self.__sgs.frequency(frequency_Hz)
        self.__sgs.power(power_dBm)
        self.__sgs.on()
    
    def CW_shutdown( self ):
        self.__sgs.off()

    def close_connection( self ):
        self.__sgs.close()