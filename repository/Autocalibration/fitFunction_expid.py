import time

import sipyco.pc_rpc as RPC
from artiq.experiment import *
from repository.Analysis.AnalysisGUI.FitFunctions import FIT_DICTIONARY
from oitg.results import *
import numpy as np
import matplotlib.pyplot as plt


class fitFunctionScheduler(EnvExperiment):

    def build(self):
        fit_types_list=list(FIT_DICTIONARY.keys())
        self.setattr_argument("RIDtoFit", NumberValue(default=106702,ndecimals=0,min=0,scale=1,step=1, type='int'))
        self.setattr_argument("ScanParam", StringValue(default="allZ")) # maybe unnecessary
        self.setattr_argument("Fit_type",EnumerationValue(fit_types_list, default=fit_types_list[0]))
        self.setattr_argument("Param_init", Scannable(default=ExplicitScan([]),
                                                                global_min=-1e9,
                                                                global_max=1e9,
                                                                global_step=1e-8,
                                                                unit="",
                                                                ndecimals=9
                                                                ))
        pass

    def prepare(self):


        # preparing fit parameters
        fit_init_params=self.Param_init.sequence
        self.fitObj=FIT_DICTIONARY[self.Fit_type]
        #if self.ScanParam=="allZ":
        for n in range(self.fitObj.num_params):
            self.fitObj.params2Dlist[n][2]=fit_init_params[n]

        self.paramSetting_dict={
            "allZ":["Experiment_config.all_z", 2,3]
        }

        pass

    def run(self):
        dataset=self.extract_rid_data(self.RIDtoFit)
        best_fitY,bestfitParams=self.fitObj.activateFit(dataset[0],dataset[1])
        dataset.append(best_fitY)
        self.plot_rid_fit(self.RIDtoFit,dataset)

        for key in list(self.paramSetting_dict.keys()):
            if key==self.ScanParam:
                self.set_dataset(self.paramSetting_dict[key][0],
                                 bestfitParams[self.paramSetting_dict[key][1]][self.paramSetting_dict[key][2]],
                                 broadcast=True, archive= True, persist=True)

        # based on ScanParam value- compare with other strings in param list.
        # set_dataset(" corresponding dataset to ", fit value)
        pass

    def extract_rid_data(self,rid):
        #rid=int(rid)
        dict_test = find_results("", rid=int(rid),
                                 root_path="C:/Users/TrappedIonRice4/Documents/Artiq-Rice/results")  # returns dict of results, used to find file path
        dict_hdf5 = load_hdf5_file(dict_test[int(rid)][0])  # returns file as dict
        dict_datasets = dict_hdf5["datasets"]  # dict key where all points are stored in a nested dict

        # extracting xlabel
        scanparam_axis0 = json.loads(dict_datasets['ndscan.rid_' + str(rid) + '.axes'])[0]
        unit = ""
        if 'unit' in scanparam_axis0['param']['spec'].keys():
            unit = '(' + scanparam_axis0['param']['spec']['unit'] + ')'
        xlabel_axis0 = scanparam_axis0['param']['description'] + unit
        # assign data for exp 1 and switch point
        key_name_x = "ndscan.rid_" + str(rid) + ".points.axis_0"  # key name for duration parameter points
        key_name_y = "ndscan.rid_" + str(rid) + ".points.channel_counts"  # key name for result parameter points
        key_name_err = "ndscan.rid_" + str(rid) + ".points.channel_res_err"  # key name for error parameter points
        # print(dict_datasets)
        x_vals_1 = np.array(list(dict_datasets[key_name_x]), dtype=float)
        # for i in range(len(x_vals_1)):
        #     x_vals_1[i]=x_vals_1[i]*10**6
        y_vals_1 = np.array(list(dict_datasets[key_name_y]), dtype=float)
        err_vals_1 = np.array(list(dict_datasets[key_name_err]), dtype=float)
        # x_vals_1 = np.array(x_vals_1) * 1e-3
        #plt.errorbar(x_vals_1, y_vals_1, color='blue', yerr=err_vals_1, fmt="-o", label="{0:d}".format(rid))
        return [x_vals_1, y_vals_1, err_vals_1, xlabel_axis0]

    def plot_rid_fit(self,rid, dataset):

        plt.close('all')
        fig1,ax1=plt.subplots(1,1,figsize=(8,6))
        if "(ms)" in dataset[3].lower() :
            timescale=1e3
        else:
            timescale=1

        ax1.errorbar(dataset[0]*timescale, dataset[1], color='blue', yerr=dataset[2], fmt="-o", label="{0:d}".format(rid))
        ax1.plot(dataset[0]*timescale, dataset[4], color='blue', linestyle="-", label="Fit: {0:d}".format(rid))
        ax1.set_xlabel(dataset[3] , fontsize=14)
        ax1.set_ylabel("Counts", fontsize=14)
        plt.tight_layout()
        ax1.grid(True)
        plt.show()



