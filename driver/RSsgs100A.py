from qcodes.instrument_drivers.rohde_schwarz.SGS100A import RohdeSchwarzSGS100A
from .SG import SG

class sgs100A(SG):

    def __init__( self, address:str ):
        self.__sgs = RohdeSchwarzSGS100A('sgs', address=address)
    
    
    def CW_output( self, frequency_Hz:float=6e9, power_dBm:float=-20):
        self.__sgs.frequency(frequency_Hz)
        self.__sgs.power(power_dBm)
        self.__sgs.on()
    
    
    def CW_shutdown( self ):
        self.__sgs.off()
