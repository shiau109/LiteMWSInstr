import os, time
from datetime import datetime
from numpy import array
from xarray import Dataset
from pandas import DataFrame
from typing import Iterable, Union


class Datar():
    def __init__(self):
        self.__format:str = "nc"
        self.file_name:str = ""
        self.file_folder:str = ""
        self.data:Iterable = []
        self.coordinates:dict = {}
        self.attributes:dict = {}
        self.__dataset:Union[Dataset, DataFrame] = Dataset()
    
    @property
    def format(self):
        return self.__format
    @format.setter
    def to_form(self, form:str):
        if form.lower() in ["nc", "csv"]:
            self.__format = form.lower()
        else:
            raise TypeError("Now the data must be .nc or .csv !")
    @property
    def get_ds(self)->Union[Dataset, DataFrame]:
        return self.__dataset
    
    def __check_everything_ready__(self):
        issues = []
        
        if self.file_name == "":
            issues.append("file_name")
        if self.file_folder == "":
            issues.append("file_folder")
        if len(list(self.data)) == 0:
            issues.append("Raw data")
        if self.__format == "nc":
            if len(list(self.coordinates)) == 0:
                issues.append("Coordinates")
        elif self.__format == 'csv':
            if len(list(array(self.data).shape)) != 2:
                issues.append("Data dimension for csv")
        
        if len(issues) != 0:
            raise ValueError(f"The following values are empty: {issues}, which is not allowed !")
        else:
            if not os.path.exists(self.file_folder):
                os.makedirs(self.file_folder,exist_ok=True)
        
    def __NCcomposer__(self):
        output_data = {
            "data": ( list(self.coordinates.keys()),array(self.data) )
        }
        self.__dataset = Dataset(
            data_vars = output_data,
            coords = self.coordinates,
            attrs = self.attributes
        )
        
    def __CSVcomposer__(self):
        """ Only for 2D array, N-dim data need to be developed ..."""
        self.__dataset = DataFrame(self.data)

    def save(self, **kwargs)->str:
        """ 
            According to the givens, save your data. \n
            ---
            # Warning : Check every attributes was given if you want to save a nc file.\n
            ---
            * Return : File path in string.

        """
        self.__check_everything_ready__()
        file_loc = os.path.join(self.file_folder,f"{self.file_name}_{datetime.now().strftime('%y%m%d%H%M%S')}.{self.__format}")
        
        match self.__format:
            case "nc":
                self.__NCcomposer__()
                self.__dataset.to_netcdf(file_loc)
            case "csv":
                self.__CSVcomposer__()
                self.__dataset.to_csv(file_loc)
        


        

if __name__ == "__main__":
    D = Datar()
    D.to_form = "nc"

    
    

