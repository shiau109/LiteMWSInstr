
from .E5080B import VNA_E5080B
from .dummy import VNA_DUMMY
from .VNA import VNA
from .ZNB import VNA_ZNB20
from .RSsgs100A import sgs100A, SG
from .MXA import MXA
def get_VNA( address, model=None )->VNA:
    match model:
        case "E5080B":
            return VNA_E5080B(address)
        case "ZNB":
            return VNA_ZNB20(address)
        case _:
            return VNA_DUMMY(address)
        
def get_SG( address, model:str=None, name:str='sgs')->SG:
    match model.lower():
        case "sgs100a"|"rssgs100a":
            return sgs100A(address, name)
        case _:
            raise NameError(f"Unsupported SG model: {model}")
        
def get_SA( address, model:str=None, name:str="sa")->MXA:
    match model.lower():
        case 'n9020a':
            from .SA_N9020A import N9020A
            return N9020A(address, name)
        case 'n9020b':
            from .SA_N9020B import N9020B
            return N9020B(address, name)
        case _:
            raise NameError(f"Unsupported SA model: {model}")