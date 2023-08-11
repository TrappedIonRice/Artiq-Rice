from ndscan.experiment import *
from oitg.results import *
import oitg.fitting
import numpy as np
import matplotlib
#%matplotlib tk
import matplotlib.pyplot as plt
class executeScanAnalyses(ExpFragment):
    def build_fragment(self):
        print("built")
        self.setattr_param("duration", FloatParam, "duration", unit = "us", default = 1.0*us)
        self.setattr_result("results")
        self.setattr_result("error_vals", display_hints={"error_bar_for": self.results.path})
        self.setattr_result("results2", display_hints={"share_axis_with": self.results.path})
        self.setattr_result("error_vals2", display_hints={"error_bar_for": self.results2.path})
        self.array_x = []
        self.array_y = []
        self.array_y2 = []
        self.array_err = []
        self.fit = 'None'
        self.fit2 = 'None'
        self.dict_constants_1 = {}
        self.dict_constants_2 = {}
        self.index_val = 0
        self.index_val2 = 0
        self.switch_point = 0

    def run_once(self):
        if self.index_val < self.switch_point:
            self.results.push(self.array_y[self.index_val])
            self.error_vals.push(self.array_err[self.index_val])
        else:
            self.results2.push(self.array_y[self.index_val])
            self.error_vals2.push(self.array_err[self.index_val])
            self.index_val2 +=1

        # else:
        #     self.results.push(0)
        #     self.results2.push(self.index_val)
        # print(self.index_val)
        # print(str(self.duration.get()) + " , " + str(self.array_y[self.index_val]))
     #   print(self.duration.get())
    # else:
        #     self.results2.push(self.array_y[self.index_val])
        #     self.error_vals2.push(self.array_err[self.index_val])
        #     print("pushed : " + str(self.array_y[self.index_val]))
        #     print("duration" + " : " + str(self.duration.get()))
        # else:
        #     self.results2.push(self.array_y[self.index_val])
        #     self.error_vals2.push(self.array_err[self.index_val])
        self.index_val += 1

    def get_default_analyses(self): #returns fit
        OnlineFit1 = OnlineFit("none", data={})
        OnlineFit2 = OnlineFit("none", data={})
        #have to instatiate this because for some reason gives key error when self.fit is none for onlinefit1, but no key error when self.fit2 is none for online fit2

        if self.fit == self.fit2 == "None": #for some reason using and operator does not work
            return []
        if self.fit != "None":
            print("building fit 1")
            OnlineFit1 = OnlineFit(self.fit,
                          data={
                              "x": self.duration,
                              "y": self.results,
                              #"y_err": self.error_vals
                          },
                          annotations = {"x0" :
                                      {
                                      "x": 'x0'
                                      },
                                      "tau":
                                      {
                                        "x": "tau"
                                      },
                                      "y_inf":
                                      {
                                        "y": "y_inf"
                                      },
                                      "y0":
                                      {
                                        "results": "y0"
                                      },
                          }

                          ,constants = self.dict_constants_1,
                        #  initial_values= {'x' : 0},
                        )
        if self.fit2 != "None":
            print("building fit 2")
            OnlineFit2 = OnlineFit(self.fit2,
                              data={
                                  "x": self.duration,
                                  "y": self.results2,
                                  # "y_err": self.error_vals
                              },
                              annotations={"x0":
                                  {
                                      "x": 'x0'
                                  },
                                  "tau":
                                      {
                                          "x": "tau"
                                      },
                                  "y_inf":
                                      {
                                          "y": "y_inf"
                                      },
                                  "y0":
                                      {
                                          "results": "y0"
                                      },
                              }

                              ,constants = self.dict_constants_2,
                              #  initial_values= {'x' : 0},
                              )

        if self.fit and self.fit2 != "None":
            return [OnlineFit1, OnlineFit2]
        elif self.fit != "None":
            return [OnlineFit1]
        return [OnlineFit2]

class analyzeMultipleScan(ExpFragment):
    def build_fragment(self):
        """exp 1"""
        self.setattr_fragment("analyze_scan", executeScanAnalyses)
        self.setattr_param("date", StringParam, "EXPERIMENT DATE (YYYY-MM-DD)", default = None)
        self.setattr_param("rid", IntParam, "RUN ID (RID) NUMBER", default = None)

        """exp 2"""

        self.setattr_param("date_2", StringParam, "EXPERIMENT 2 DATE (YYYY-MM-DD)", default=None)
        self.setattr_param("exp2", BoolParam, "INCLUDE 2ND EXPERIMENT", default=False)
        self.setattr_param("rid_2", IntParam, "EXPERIMENT 2 RUN ID (RID) NUMBER", default=None)

        fits = ["cos", "decaying_sinusoid", "detuned_square_pulse", "exponential_decay",
                "gaussian", "line", "lorentzian", "rabi_flop", "sinusoid", "v_function", "parabola", "None"]

        self.setattr_argument("CHOOSE_FIT_1", EnumerationValue(fits, default="None"))
        self.setattr_argument("Set_x0_1", BooleanValue(default=False), group = "SET FIT 1")
        self.setattr_argument("x0_1", NumberValue(default=0 * us, unit = "us", ndecimals=6), group="SET FIT 1")
        self.setattr_argument("Set_y0_1", BooleanValue(default=False), group = "SET FIT 1")
        self.setattr_argument("y0_1", NumberValue(default=0, ndecimals=6), group="SET FIT 1")
        self.setattr_argument("Set_y_inf_1", BooleanValue(default=False), group = "SET FIT 1")
        self.setattr_argument("y_inf_1", NumberValue(default=0, ndecimals=6), group="SET FIT 1")
        self.setattr_argument("Set_tau_1", BooleanValue(default=False), group = "SET FIT 1")
        self.setattr_argument("tau_1", NumberValue(default=0 * us, unit="us", ndecimals=6), group="SET FIT 1")

        self.setattr_argument("CHOOSE_FIT_2", EnumerationValue(fits, default="None"))
        self.setattr_argument("Set_x0_2", BooleanValue(default=False), group="SET FIT 2")
        self.setattr_argument("x0_2", NumberValue(default=0 * us, unit="us", ndecimals=6), group="SET FIT 2")
        self.setattr_argument("Set_y0_2", BooleanValue(default=False), group="SET FIT 2")
        self.setattr_argument("y0_2", NumberValue(default=0, ndecimals=6), group="SET FIT 2")
        self.setattr_argument("Set_y_inf_2", BooleanValue(default=False), group="SET FIT 2")
        self.setattr_argument("y_inf_2", NumberValue(default=0, ndecimals=6), group="SET FIT 2")
        self.setattr_argument("Set_tau_2", BooleanValue(default=False), group="SET FIT 2")
        self.setattr_argument("tau_2", NumberValue(default=0 * us, unit="us", ndecimals=6), group="SET FIT 2")

        setattr_subscan(self, "scan", self.analyze_scan, [(self.analyze_scan, "duration")],
                        expose_analysis_results=True)


    def run_once(self):
        #extract data from hdf5 for exp 1
        dict_test = find_results(self.date.get(), rid=self.rid.get(),
                root_path="C:/Artiq/artiq_new_installation/results")  #returns dict of results, used to find file path
        dict_hdf5 = load_hdf5_file(dict_test[self.rid.get()][0]) #returns file as dict
        dict_datasets = dict_hdf5["datasets"] #dict key where all points are stored in a nested dict

        # extract data from hdf5 for exp 2
        dict_test_2 = find_results(self.date_2.get(), rid=self.rid_2.get(),
                                 root_path="C:/Artiq/artiq_new_installation/results")  # returns dict of results, used to find file path
        dict_hdf5_2 = load_hdf5_file(dict_test_2[self.rid_2.get()][0])  # returns file as dict
        dict_datasets_2 = dict_hdf5_2["datasets"]  # dict key where all points are stored in a nested dict

        #assign data for exp 1 and switch point
        key_name_x = "ndscan.rid_" + str(self.rid.get()) + ".points.axis_0" #key name for duration parameter points
        #self.lst_duration = np.sort(dict_datasets[key_name_x])
        self.lst_duration = dict_datasets[key_name_x]
        self.analyze_scan.switch_point = len(self.lst_duration)
        self.analyze_scan.array_x = self.lst_duration
        key_name_y = "ndscan.rid_" + str(self.rid.get()) + ".points.channel_result" #key name for result parameter points
        #self.analyze_scan.array_y = np.sort(dict_datasets[key_name_y])[::-1]
        self.analyze_scan.array_y = dict_datasets[key_name_y]
        print(dict_datasets[key_name_y])
        key_name_err = "ndscan.rid_" + str(self.rid.get()) + ".points.channel_res_err" #key name for error parameter points
        #self.analyze_scan.array_err = np.sort(dict_datasets[key_name_err])[::-1]
        self.analyze_scan.array_err = dict_datasets[key_name_err]
        self.analyze_scan.fit = self.CHOOSE_FIT_1
        lst_param_bool = [self.Set_x0_1, self.Set_y0_1, self.Set_y_inf_1, self.Set_tau_1]
        lst_param = [self.x0_1, self.y0_1, self.y_inf_1, self.tau_1]
        lst_param_name = ['x0', 'y0', 'y_inf', 'tau']
        for i in range(len(lst_param)):
            if lst_param_bool[i]:
                self.analyze_scan.dict_constants_1[lst_param_name[i]] = lst_param[i]
        data_dict = {"exponential_decay": oitg.fitting.exponential_decay.fit(dict_datasets[key_name_x],
                                                                             dict_datasets[key_name_y],
                                                                             dict_datasets[key_name_err],
                                                                             evaluate_function=True, evaluate_n=2)}
        data = data_dict["exponential_decay"]
        print("FIT PARAMETERS FOR EXP 1: " + str(data[0]))

        #assign data for exp2
        if self.exp2.get() == True:
            #assign data for exp 2 by appending to lists in exp 1. By appending instead of creating new list, streamlines exp.
            key_name_x2 = "ndscan.rid_" + str(self.rid_2.get()) + ".points.axis_0"  # key name for duration parameter points
            self.lst_duration = dict_datasets_2[key_name_x2]
            self.analyze_scan.array_x = np.append(self.analyze_scan.array_x, self.lst_duration)
            self.lst_duration = self.analyze_scan.array_x
            key_name_y2 = "ndscan.rid_" + str(self.rid_2.get()) + ".points.channel_result"  # key name for result parameter points
            self.analyze_scan.array_y = np.append(self.analyze_scan.array_y, dict_datasets_2[key_name_y2])
           #self.analyze_scan.array_y2 = dict_datasets_2[key_name_y2]
            key_name_err2 = "ndscan.rid_" + str(self.rid_2.get()) + ".points.channel_res_err"  # key name for error parameter points
            self.analyze_scan.array_err = np.append(self.analyze_scan.array_err, dict_datasets_2[key_name_err2])
            self.analyze_scan.fit2 = self.CHOOSE_FIT_2
            lst_param_bool = [self.Set_x0_2, self.Set_y0_2, self.Set_y_inf_2, self.Set_tau_2]
            lst_param = [self.x0_2, self.y0_2, self.y_inf_2, self.tau_2]
            lst_param_name = ['x0', 'y0', 'y_inf', 'tau']
            for i in range(len(lst_param)):
                if lst_param_bool[i]:
                    self.analyze_scan.dict_constants_2[lst_param_name[i]] = lst_param[i]
            data_dict["exponential_decay2"] = oitg.fitting.exponential_decay.fit(dict_datasets_2[key_name_x2],
                                                                                 dict_datasets_2[key_name_y2],
                                                                                 dict_datasets_2[key_name_err2],
                                                                                 evaluate_function=True,
                                                                                 evaluate_n=2)
            data_2 = data_dict["exponential_decay2"]
            print("FIT PARAMETERS FOR EXP 2: " + str(data_2[0]))

        print(self.lst_duration)
        print(self.analyze_scan.array_y)
        self.scan.run([(self.analyze_scan.duration, ListGenerator(self.lst_duration, False))])#runs subscan iterating for each element in list



MultipleScanTest = make_fragment_scan_exp(analyzeMultipleScan)