from abc import ABC, abstractmethod
class SG():


    def __init__( self ):
        pass
    
    @abstractmethod
    def CW_output( self, frequency_Hz, power_dBm):
        pass
    
    @abstractmethod
    def CW_shutdown( self ):
        pass
