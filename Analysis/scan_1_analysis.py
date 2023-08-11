from ndscan.experiment import *
from oitg.results import *
import oitg.fitting
import numpy as np

class executeScanAnalyses(ExpFragment):
    def build_fragment(self):
        print("built")
        self.setattr_param("duration", FloatParam, "duration", unit = "us", default = 1.0*us)
        self.setattr_result("results")
        self.setattr_result("error_vals", display_hints={"error_bar_for": self.results.path})
        self.setattr_result("results2")
        self.setattr_result("error_vals2", display_hints={"error_bar_for": self.results2.path})
        self.array_x = []
        self.array_y = []
        self.array_err = []
        self.fit = ''
        self.dict_constants = {}
        self.index_val = 0

    def run_once(self):
        list_x = self.array_x.tolist() #must do to use .index function
        self.index_val = list_x.index(self.duration.get()) #used to match index values within array_y and array_err

        # if self.index_val >= 16:
        #     print(self.duration.get())
        #     self.results2.push(self.array_y[self.index_val])
        #     print(self.array_y[self.index_val])
        #     self.error_vals2.push(self.array_err[self.index_val])
        # else:
        self.results.push(self.array_y[self.index_val])
        self.error_vals.push(self.array_err[self.index_val] )

    def get_default_analyses(self): #returns fit
     #   lst_param = [self.x0, self.y0, self.y_inf, self.tau]
        param_names = ['x0', 'y0', 'y_inf', 'tau']
        dict_constants = {}
        if self.fit != "None":
            self.fitclass=OnlineFit(self.fit,
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

                          #,constants = self.dict_constants,
                        #  initial_values= {'x' : 0},
                        )

           # print(self.fitclass.get_analysis_results(AnnotationContext(ParamHandle("executeScanAnalysis", "duration", ), ))
            return[ self.fitclass ]
        else:
            return []

class analyzeScan(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("analyze_scan", executeScanAnalyses)
        self.setattr_param("date", StringParam, "EXPERIMENT DATE (YYYY-MM-DD)", default = None)
        self.setattr_param("rid", IntParam, "RUN ID (RID) NUMBER", default = None)
        fits = ["cos", "decaying_sinusoid", "detuned_square_pulse", "exponential_decay",
                "gaussian", "line", "lorentzian", "rabi_flop", "sinusoid", "v_function", "parabola", "None"]
        self.setattr_argument("CHOOSE_FIT", EnumerationValue(fits, default="None"))
        self.setattr_argument("Set_x0", BooleanValue(default=False), group = "SET FIT")
        self.setattr_argument("x0", NumberValue(default=0 * us, unit = "us", ndecimals=6), group="SET FIT")
        self.setattr_argument("Set_y0", BooleanValue(default=False), group = "SET FIT")
        self.setattr_argument("y0", NumberValue(default=0, ndecimals=6), group="SET FIT")
        self.setattr_argument("Set_y_inf", BooleanValue(default=False), group = "SET FIT")
        self.setattr_argument("y_inf", NumberValue(default=0, ndecimals=6), group="SET FIT")
        self.setattr_argument("Set_tau", BooleanValue(default=False), group = "SET FIT")
        self.setattr_argument("tau", NumberValue(default=0 * us, unit="us", ndecimals=6), group="SET FIT")
        setattr_subscan(self, "scan", self.analyze_scan, [(self.analyze_scan, "duration")],
                        expose_analysis_results=True)

    def run_once(self):
        #extract data from hdf5
        dict_test = find_results(self.date.get(), rid=self.rid.get(),
                root_path="C:/Artiq/artiq_new_installation/results")  #returns dict of results, used to find file path
        dict_hdf5 = load_hdf5_file(dict_test[self.rid.get()][0]) #returns file as dict
        dict_datasets = dict_hdf5["datasets"] #dict key where all points are stored in a nested dict
        key_name_x = "ndscan.rid_" + str(self.rid.get()) + ".points.axis_0" #key name for duration parameter points
        self.lst_duration = dict_datasets[key_name_x]
        print(type(self.lst_duration))

        #self.lst_duration.append(np.array([1.0 * us,2.0 * us,3.0* us,4.0* us,5.0* us,6.0* us,7.0* us,8.0* us,9.0* us,10.0* us,11.0* us,12.0* us,13.0* us,14.0* us,15.0* us,16.0* us]))
       # print(self.lst_duration)
        self.analyze_scan.array_x = np.append(self.lst_duration, [1.0 * us,2.0 * us,3.0* us,4.0* us,5.0* us,6.0* us,7.0* us,8.0* us,9.0* us,10.0* us,11.0* us,12.0* us,13.0* us,14.0* us,15.0* us,16.0* us])
        #delete line below this comment if you want normal plot
  #      self.lst_duration = self.analyze_scan.array_x
      #  print(self.analyze_scan.array_x)
        key_name_y = "ndscan.rid_" + str(self.rid.get()) + ".points.channel_result" #key name for result parameter points
        self.analyze_scan.array_y = np.append(dict_datasets[key_name_y], [1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0,11.0,12.0,13.0,14.0,15.0,16.0])

        key_name_err = "ndscan.rid_" + str(self.rid.get()) + ".points.channel_res_err" #key name for error parameter points

        #set class variables in subscan
        self.analyze_scan.array_err = np.append(dict_datasets[key_name_err], dict_datasets[key_name_err])
        self.analyze_scan.fit = self.CHOOSE_FIT
        lst_param_bool = [self.Set_x0, self.Set_y0, self.Set_y_inf, self.Set_tau]
        lst_param = [self.x0, self.y0, self.y_inf, self.tau]
        lst_param_name = ['x0', 'y0', 'y_inf', 'tau']
        for i in range(len(lst_param)):
            if lst_param_bool[i]:
                self.analyze_scan.dict_constants[lst_param_name[i]] = lst_param[i]


        #run subscan
        self.scan.run([(self.analyze_scan.duration, ListGenerator(self.lst_duration, False))])#runs subscan iterating for each element in list
        print(oitg.fitting.exponential_decay.fit(dict_datasets[key_name_x], dict_datasets[key_name_y], dict_datasets[key_name_err], evaluate_function=True, evaluate_n=2))
        # print(oitg.fitting.FitBase.FitBase.fit(self, x = self.lst_duration, y = dict_datasets[key_name_y], y_err = dict_datasets[key_name_err], x_limit=[-np.inf, np.inf], y_limit=[-np.inf, np.inf],
        #     constants={}, initialise={},
        #     calculate_residuals=False,
        #     evaluate_function=False,
        #     evaluate_x_limit=[None, None],
        #     evaluate_n=1000))
        # self.analyze_scan.array_x = np.array([1.0 * us,2.0 * us,3.0* us,4.0* us,5.0* us,6.0* us,7.0* us,8.0* us,9.0* us,10.0* us,11.0* us,12.0* us,13.0* us,14.0* us,15.0* us,16.0* us])
        # self.analyze_scan.array_y = np.array([100.0 * us,2.0 * us,3.0* us,4.0* us,5.0* us,60.0* us,7.0* us,8.0* us,94.0* us,10.0* us,11.0* us,12.0* us,13.0* us,14.0* us,15.0* us,16.0* us])
        # self.scan.run([(self.analyze_scan.duration, ListGenerator([1.0 * us,2.0 * us,3.0* us,4.0* us,5.0* us,6.0* us,7.0* us,8.0* us,9.0* us,10.0* us,11.0* us,12.0* us,13.0* us,14.0* us,15.0* us,16.0* us], False))])



AnalyzeScanExp1 = make_fragment_scan_exp(analyzeScan)