import os, json
import numpy as np
from xarray import open_dataset
import matplotlib as mat
from os import makedirs

def fastTWPAcali_ana(description_path:str):

    warning:bool = False
    with open(description_path, 'r', encoding='utf-8') as f:
        sum_info = json.load(f)

    expected_file_name = ["power_pump_off", "power_pump_on", "noise_pump_off", "noise_pump_on"]
    ROf_dSNR = []

    for readout in sum_info:
        description = sum_info[readout]
        pump_freq, pump_power = [], []
        gain, noise = [], []
        pic_save_folder = os.path.join(os.path.split(description_path)[0],readout)
        if not os.path.exists(pic_save_folder):
            makedirs(pic_save_folder)

        for name in expected_file_name:  
            # Signal part
            ds = open_dataset(os.path.join(os.path.split(description_path)[0],description[name]))
            if name.split("_")[0].lower() == 'power':
                RO_target_idx = list(ds.coords['frequency']).index(ds.attrs["RO_freq"]) 
                ROin_power = ds.attrs["RO_power"]
                if name.split("_")[-1].lower() == 'off':
                    gain_off = np.array(ds.data_vars['data'])[RO_target_idx] - ROin_power
                else:
                    
                    for f_idx, pp_freq in enumerate(np.array(ds.coords["pump_freqs"])):
                        temp = []
                        for p_idx, pp_power in enumerate(np.array(ds.coords["pump_powers"])):
                            temp.append(np.array(ds.data_vars['data'])[f_idx][p_idx][RO_target_idx] - ROin_power - gain_off)
                        gain.append(temp)

                    pump_freq, pump_power = np.array(ds.coords["pump_freqs"]), np.array(ds.coords["pump_powers"])
                    power, freq = np.meshgrid( np.array(ds.coords["pump_powers"]).flatten(),np.array(ds.coords["pump_freqs"]).flatten()) 
                    # search a max gain
                    flat_index = np.argmax(np.array(gain))
                    # Convert to 2D coordinates (row, col)
                    row, col = np.unravel_index(flat_index, np.array(gain).shape)

                    mat.use('TkAgg')
                    import matplotlib.pyplot as plt
                    plt.pcolormesh(freq.transpose()*1e-6,power.transpose(),np.array(gain).transpose(),shading='auto')
                    
                    plt.title(f"{readout} Pump parameter mapping for gain")
                    plt.xlabel("Frequency (MHz)")
                    plt.ylabel("Power (dBm)")
                    plt.colorbar(label='S21 (dB)')
                    plt.scatter(np.array(ds.coords["pump_freqs"])[row]*1e-6, np.array(ds.coords["pump_powers"])[col], marker="*", c='red')
                    plt.annotate(
                        f"({round(np.array(ds.coords['pump_freqs'])[row]*1e-6,1)}, {round(np.array(ds.coords['pump_powers'])[col],1)})",       # text
                        (np.array(ds.coords["pump_freqs"])[row]*1e-6, np.array(ds.coords["pump_powers"])[col]),              # position
                        textcoords="offset points",
                        xytext=(5, 5),          # offset in pixels
                        ha='left',              # horizontal alignment
                        fontsize=10
                    )
                    plt.grid()
                    plt.tight_layout()
                    plt.savefig(os.path.join(pic_save_folder,"Gain_mapping.png"))
                    plt.close()
                

            # Noise part
            elif name.split("_")[0].lower() == 'noise':
                if name.split("_")[-1].lower() == 'off':
                    noise_off = np.mean(np.array(ds.data_vars['data']))
                else:
                    for f_idx, pp_freq in enumerate(np.array(ds.coords["pump_freqs"])):
                        temp = []
                        for p_idx, pp_power in enumerate(np.array(ds.coords["pump_powers"])):
                            temp.append(np.mean(np.array(ds.data_vars['data'])[f_idx][p_idx]) - noise_off )
                        noise.append(temp)
                    
                    power, freq = np.meshgrid( np.array(ds.coords["pump_powers"]).flatten(),np.array(ds.coords["pump_freqs"]).flatten()) 
                    # search a max gain
                    flat_index = np.argmin(np.array(noise))
                    # Convert to 2D coordinates (row, col)
                    row, col = np.unravel_index(flat_index, np.array(noise).shape)

                    mat.use('TkAgg')
                    import matplotlib.pyplot as plt
                    plt.pcolormesh(freq.transpose()*1e-6,power.transpose(),np.array(noise).transpose(),shading='auto')
                    
                    plt.title(f"{readout} Pump parameter mapping for noise")
                    plt.xlabel("Frequency (MHz)")
                    plt.ylabel("Power (dBm)")
                    plt.colorbar(label='S21 (dB)')
                    plt.scatter(np.array(ds.coords["pump_freqs"])[row]*1e-6, np.array(ds.coords["pump_powers"])[col], marker="*", c='red')
                    plt.annotate(
                        f"({round(np.array(ds.coords['pump_freqs'])[row]*1e-6,1)}, {round(np.array(ds.coords['pump_powers'])[col],1)})",       # text
                        (np.array(ds.coords["pump_freqs"])[row]*1e-6, np.array(ds.coords["pump_powers"])[col]),              # position
                        textcoords="offset points",
                        xytext=(5, 5),          # offset in pixels
                        ha='left',              # horizontal alignment
                        fontsize=10
                    )
                    plt.grid()
                    plt.tight_layout()
                    plt.savefig(os.path.join(pic_save_folder,"Noise_mapping.png"))
                    plt.close()


            else:
                warning = True
            
            ds.close() 

        # SNR differences
        dSNR = np.array(gain)-np.array(noise)
        ROf_dSNR.append(dSNR.tolist())
        power, freq = np.meshgrid( pump_power.flatten(),pump_freq.flatten()) 
        # search a max gain
        flat_index = np.argmax(dSNR)
        # Convert to 2D coordinates (row, col)
        row, col = np.unravel_index(flat_index, dSNR.shape)

        mat.use('TkAgg')
        import matplotlib.pyplot as plt
        plt.pcolormesh(freq.transpose()*1e-6,power.transpose(),dSNR.transpose(),shading='auto')

        plt.title(f"{readout} Pump parameter mapping for dSNR")
        plt.xlabel("Frequency (MHz)")
        plt.ylabel("Power (dBm)")
        plt.colorbar(label='Differences (dB)')
        plt.scatter(pump_freq[row]*1e-6, pump_power[col], marker="*", c='red')
        plt.annotate(
            f"({round(pump_freq[row]*1e-6,1)}, {round(pump_power[col],1)})",       # text
            (pump_freq[row]*1e-6, pump_power[col]),              # position
            textcoords="offset points",
            xytext=(5, 5),          # offset in pixels
            ha='left',              # horizontal alignment
            fontsize=10
        )
        plt.grid()
        plt.tight_layout()
        plt.savefig(os.path.join(pic_save_folder,"dSNR_mapping.png"))
        plt.close()

    min_dSNR = np.min(np.array(ROf_dSNR), axis=0)
    power, freq = np.meshgrid( pump_power.flatten(),pump_freq.flatten()) 
    # search a max dSNR
    flat_index = np.argmax(min_dSNR)
    # Convert to 2D coordinates (row, col)
    row, col = np.unravel_index(flat_index, min_dSNR.shape)

    mat.use('TkAgg')
    import matplotlib.pyplot as plt
    plt.pcolormesh(freq.transpose()*1e-6,power.transpose(),min_dSNR.transpose(),shading='auto')

    plt.title("All RO guaranteed dSNR pumping mapping")
    plt.xlabel("Frequency (MHz)")
    plt.ylabel("Power (dBm)")
    plt.colorbar(label='Differences (dB)')
    plt.scatter(pump_freq[row]*1e-6, pump_power[col], marker="*", c='red')
    plt.annotate(
        f"({round(pump_freq[row]*1e-6,1)}, {round(pump_power[col],1)})",       # text
        (pump_freq[row]*1e-6, pump_power[col]),              # position
        textcoords="offset points",
        xytext=(5, 5),          # offset in pixels
        ha='left',              # horizontal alignment
        fontsize=10
    )
    plt.grid()
    plt.tight_layout()
    plt.savefig(os.path.join(os.path.split(description_path)[0],"guarantee_dSNR_mapping.png"))
    plt.show()


if __name__ == "__main__":
    file_description = "/home/ratiswu/test/DR3K2/SNR/data_descriptions.json"
    fastTWPAcali_ana(file_description)
