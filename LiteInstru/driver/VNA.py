from abc import ABC, abstractmethod
class VNA():


    def __init__( self ):
        pass
    
    @abstractmethod
    def lin_freq_sweep( self, start, stop, points, port:str="s21", power:float=-20, IF_bandwith=1000):
        pass


