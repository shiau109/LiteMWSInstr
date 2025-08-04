from numpy import array
from pandas import read_csv
import matplotlib.pyplot as plt
import os
from scipy.ndimage import gaussian_filter1d

gain_file = '/home/ratiswu/liteVNA_test/QuantWareW23A5_7200MHz_m24dBm/gain.csv'
noise_file = '/home/ratiswu/liteVNA_test/QuantWareW23A5_7200MHz_m24dBm/noise_diff.csv'

dict_gain = read_csv(gain_file,skiprows=0).to_dict(orient='series')
dict_noise = read_csv(noise_file,skiprows=0).to_dict(orient='series')
freq_g = array(dict_gain["Unnamed: 0"])
gain = array(dict_gain["0"])
freq_n = array(dict_noise["Unnamed: 0"])
noise = array(dict_noise["0"])

plt.plot(freq_g, gain-noise,c='black')
plt.plot(freq_n, gaussian_filter1d(gain-noise, sigma=100),c='cyan')
plt.grid()
plt.xlabel("Frequency (GHz)")
plt.ylabel("dSNR")
plt.tight_layout()
plt.savefig(os.path.join(os.path.split(noise_file)[0],"SN_ratio.png"))
plt.close()