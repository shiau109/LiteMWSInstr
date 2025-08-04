
from .E5080B import VNA_E5080B
from .dummy import VNA_DUMMY
from .VNA import VNA
from .ZNB import VNA_ZNB20
from .RSsgs100A import sgs100A, SG
def get_VNA( address, model=None )->VNA:
    match model:
        case "E5080B":
            return VNA_E5080B(address)
        case "ZNB":
            return VNA_ZNB20(address)
        case _:
            return VNA_DUMMY(address)
        
def get_SG( address, model:str=None )->SG:
    match model.lower():
        case "sgs100a"|"rssgs100a":
            return sgs100A(address)
        case _:
            raise NameError(f"Unsupported SG model: {model}")