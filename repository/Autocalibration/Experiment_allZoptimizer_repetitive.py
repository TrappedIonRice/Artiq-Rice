from artiq.experiment import *
from ndscan.experiment import *
#from repository.Experiments.ScanAOM355_v1_DC_DMA_optimizer import *
from repository.Analysis.AnalysisGUI.FitFunctions import FIT_DICTIONARY
from artiq.language.environment import HasEnvironment
import numpy as np
from oitg.results import *
from oitg.errorbars import binom_onesided,binom_twosided
from matplotlib import pyplot as plt
import json
import time
from datetime import datetime


# this is how the fragment wrapper is created.
'''
NDSCAN WRAPPER TO USE SCHEDULER
1. Make a class object using make_fragment_scan_exp out of the ExpFragment from an ndscan script.
        Update: Turns out you call the ExpFragment object ScanForTime from the ndscan script and the result is the same. Switches to defaults all the time.
2. Call this new object as the class_name in the exp_id for the scheduler
3. Pass filename as the scheduler script where this new object was created
4. Pass arguments as required ... format shown below. More complicated than regular artiq but doable

'''

#scanAOM355_ndscan=make_fragment_scan_exp(executeScan)



class ExperimentOptimizerSchedule(EnvExperiment):
        ''' Experiment Optimizer Schedule'''
        def build(self):
                self.setattr_device("core")
                self.setattr_device("scheduler")

                self.referenceRID = self.get_dataset("Calibrations.reference_rid") # takes arguments globally settable rid

                self.calibrationNum=3 #self.get_dataset("Calibrations.Number") # STICKING WITH 3 CALIBRATIONS FOR NOW
                self.fullExpNum=self.calibrationNum+1 # +1 because the very last scan number is the main experiment

                # self.param_dict elements { <param name>: [units, range_start, range_stop, gstart, gstop]}
                self.param_dict={
                            "allZ":["",-0.2,0.1,-0.2,0.1],
                            "Frequency355_Raman1": ["Hz"],
                            "RamanTime":["ms",0.0,0.03,0.0,1000],
                            "TimeMW":["ms",0.0,0.6,0.0,1000],
                            "Amplitude355_Raman1":[""]
                            }

                # self.param_choice_list=[]
                # extracting json file with all calibration configs.
                self.calibration_configs={}
                self.config_path = os.path.join(os.path.dirname(__file__), "calibration_configs.json")
                with open(self.config_path,"r") as f:
                    self.calibration_configs= json.load(f)

                self.calib_list= list(self.calibration_configs['calib_config'].keys())

                fit_types=list(FIT_DICTIONARY.keys())
                #self.setattr_argument("Parameter",EnumerationValue(param_list, default=param_list[2]))
                # probably need some conditions per parameter type

                self.setattr_argument("Global_calib_check", BooleanValue(default=True))
                for n in range(self.fullExpNum):

                        if n < self.calibrationNum:

                                self.setattr_argument("CheckThresholding"+str(n+1), BooleanValue(default=True), group="Calibration "+str(n+1))
                                self.setattr_argument("Use"+str(n+1),BooleanValue(default=False), group="Calibration "+str(n+1))
                                self.setattr_argument("Parameter"+str(n+1), EnumerationValue(list(self.param_dict.keys()),
                                                                                             default=list(self.param_dict.keys())[n]),group="Calibration "+str(n+1))
                                self.setattr_argument("CalibrationConfig"+str(n+1),EnumerationValue(self.calib_list,
                                                                                             default=self.calib_list[n]),group="Calibration "+str(n+1) )

                                self.setattr_argument("Parameter_scan"+str(n+1),
                                                      Scannable(default=RangeScan(0,0.6 ,21),
                                                                global_min=-1,
                                                                global_max=1,
                                                                global_step=1e-8,
                                                                unit="",
                                                                ndecimals=9
                                                                ),
                                                      group="Calibration "+str(n+1))
                                self.setattr_argument("Fit" + str(n + 1), BooleanValue(default=False),
                                                      group="Calibration " + str(n + 1))
                                self.setattr_argument("Fit_type" + str(n + 1), EnumerationValue(fit_types, default=fit_types[0]),
                                                      group="Calibration " + str(n + 1))
                        else:
                                self.setattr_argument("CheckThresholding", BooleanValue(default=True),group="Main Experiment")
                                self.setattr_argument("Use",BooleanValue(default=False),group="Main Experiment")
                                self.setattr_argument("Parameter", EnumerationValue(list(self.param_dict.keys()),
                                                                                             default=list(self.param_dict.keys())[2]),group="Main Experiment")

                                self.setattr_argument("Parameter_scan",
                                                      Scannable(default=RangeScan(0, 0.6, 21),
                                                                global_min=-1,
                                                                global_max=1,
                                                                global_step=1e-8,
                                                                unit="",
                                                                ndecimals=9
                                                                ),
                                                      group="Main Experiment")
                                self.setattr_argument("Fit" + str(n + 1), BooleanValue(default=False),
                                                      group="Main Experiment")
                                self.setattr_argument("Fit type" + str(n + 1),
                                                      EnumerationValue(fit_types, default=fit_types[0]),
                                                      group="Main Experiment")

                # self.param_choice_list.append(param)
                # ndscan scan parameter doesn't work in barebones artiq as it cannot be stably integrated into this class double inheritance:
                # both EnvExperiment and ExpFragment
                #self.setattr_param("Parameter_scan",FloatParam,"Parameter scan", unit="", default=0.0, min=-1.0, max=1.0 )

                #self.setattr_argument("CheckThresholding", BooleanValue(default=False))


        def prepare(self):

                # extracting json file AGAIN  to use updated latest json file parameters, without triggering "recompute all arguments" which loses scan config.
                # prepare() stage is the right place to do this.

                with open(self.config_path, "r") as g:
                    self.calibration_configs = json.load(g)

                self.rids_filename=r"C:/Users/TrappedIonRice4/Documents/Artiq-Rice/ridsFile_allZ.txt"
                # self.wait_time=30
                # self.max_wait_time=100

                self.repetitions_rids=1#30*3
                self.current_time= time.time() # machine time from eons
                self.time_interval=0#2*60 # seconds
                self.time_arr=[ self.current_time+n*self.time_interval for n in range(self.repetitions_rids)]

                pass



        def get_args_rid(self):
            '''
            Supposed to extract latest rid based on executeScan automatically but there are some functional challenges.
            Not working.
            '''
            val=list(self.get_dataset("ndscan.rid_"+str(self.referenceRID)+".online_analyses"))[-1]
            return str(val)

 #       def calibration_attributes(self):



        def run(self):

                '''
                # template
                ndscan_params_dict={
                        "scan": {
                                "axes": [{
                                        "fqn": "ScanAOM355_v1_DC_DMA_optimizer.executeScan."+str(self.Parameter),
                                        "path": "",
                                        "type": "linear",
                                        "range": self.scanparams_json
                                }],
                                "num_repeats": 1,
                                "no_axes_mode": "single",
                                "randomise_order_globally": False
                        }
                }

                scanAOM355_ndscan_id1 = {
                        "file": "Experiments\ScanAOM355_v1_DC_DMA_optimizer.py",
                        "class_name": "ScanForTime",
                        "arguments": {
                                "INPUT_TTL": "ttl1_counter",
                                "ndscan_params": json.dumps(ndscan_params_dict)  # <-- convert dict to string
                        },
                        "repo_rev": "N/A",
                        "log_level": 0
                        # no overrrides section as that was causing problems
                }
                '''
                self.core.reset()


                for rep in range(self.repetitions_rids):  # change 10 to however many times you want
                    for n in range(self.fullExpNum):
                        if self.Global_calib_check:
                            if n<self.calibrationNum:
                                #if n==0: # first calibration is allZ scan

                                useVal=getattr(self,"Use"+str(n+1))
                                thresholdval=getattr(self,"CheckThresholding"+str(n+1))

                                if useVal:

                                    # set threshold value in dataset temporarily to new value
                                    new_thresh=bool(thresholdval)

                                    # set the following time parameters
                                    paramScanObj=getattr(self,"Parameter_scan"+str(n+1))
                                    self.scanparams_json = {"start": paramScanObj.start,
                                                            "stop": paramScanObj.stop,
                                                            "num_points": paramScanObj.npoints,
                                                            "randomise_order": paramScanObj.randomize}  # assumes always linear for now

                                    # set scan parameter

                                    ndscan_params_dict = {

                                        # scan variable
                                        "scan": {
                                            "axes": [{
                                                "fqn": "ScanAOM355_v1_DC_DMA_optimizer.executeScan." + str(getattr(self,"Parameter"+str(n+1))),
                                                "path": "",
                                                "type": "linear",
                                                "range": self.scanparams_json
                                            }],
                                            "num_repeats": 1,
                                            "no_axes_mode": "single",
                                            "randomise_order_globally": False
                                        },
                                        #fixing parameters
                                        "overrides":{
                                            "ScanAOM355_v1_DC_DMA_optimizer.executeScan." + "CheckThresholding":[{
                                                "path":"",
                                                "value":new_thresh
                                            }]

                                        }
                                    }

                                    # looping through selected configurations's elements and assigning variables.
                                    calib_config_val=getattr(self, "CalibrationConfig" + str(n + 1))
                                    calib_params_dict=self.calibration_configs['calib_config'][calib_config_val]
                                    for key, value in calib_params_dict.items():
                                        ndscan_params_dict["overrides"]["ScanAOM355_v1_DC_DMA_optimizer.executeScan." + key]=[{
                                                "path":"",
                                                "value":value
                                            }]

                                    scanAOM355_ndscan_id1 = {
                                        "file": "Experiments\ScanAOM355_v1_DC_DMA_optimizer.py",
                                        "class_name": "ScanForTime",
                                        "arguments": {
                                            "INPUT_TTL": "ttl1_counter",
                                            "ndscan_params": json.dumps(ndscan_params_dict)  # <-- convert dict to string
                                        },
                                        "repo_rev": "N/A",
                                        "log_level": 0
                                        # no overrrides section as that was causing problems
                                    }


                                    # execute rids
                                    exp_rid1=self.scheduler.submit("main", scanAOM355_ndscan_id1, due_date=self.time_arr[rep])
                                    #print(exp_rid)

                                    # fit rids for the experiment performed earlier
                                    if getattr(self,"Fit" + str(n + 1)):
                                        fit_id1 = {
                                            "file": r"Autocalibration\fitFunction_expid.py",
                                            "class_name": "fitFunctionScheduler",
                                            "arguments": {
                                                "RIDtoFit": exp_rid1 ,
                                                "ScanParam": str(getattr(self,"Parameter"+str(n+1))),
                                                "Fit_type": getattr(self,"Fit_type" + str(n + 1)),
                                                "Param_init":{"sequence":[1, 0.1, 0.09, 0], "ty": "ExplicitScan"}
                                            },
                                            "repo_rev": "N/A",
                                            "log_level": 0
                                            # no overrrides section as that was causing problems
                                        }
                                        fit_rid1 = self.scheduler.submit("main", fit_id1)


                                    # # wait time buffer
                                    #
                                    # waitbuffer_id1={
                                    #     "file":r"Manual control\bufferScheduler_Time.py",
                                    #     "class_name":"bufferSchedulerTime",
                                    #     "arguments": {
                                    #             "Waittime":self.wait_time
                                    #                 },
                                    #     "repo_rev": "N/A",
                                    #     "log_level": 0
                                    # }

                                    #writing to file
                                    # with open(self.rids_filename, "a") as f:
                                    #     f.write(str(exp_rid1)+","+str(self.time_arr[rep])+f"\n")
                                    #     f.flush()  # force the text to be written immediately


                                    #delay(10)
                                    #self.scheduler.submit("main", waitbuffer_id1)
                                    #time.sleep(2)  # wait 2 seconds before the next write

                                #time.sleep(5) # need at least 5 seconds delay for the new datasets to kick in,
                                # while having the scan ready for the old values

                                # # set threshold value back to old value
                                # self.set_dataset("PMTCheckThreshold", old_thresh, broadcast=True, archive=True, persist=True)
                                # self.set_dataset("SBC.Check", old_SBCcheck, broadcast=True, archive=True, persist=True)



                # # execute rid
                # for j in range (1):
                #         self.scheduler.submit("main", scanAOM355_ndscan_id1)
                        #self.scheduler.submit("main", allZoptimizerID)
                        #self.scheduler.submit("main", allZoptimizerID2)

