import time

import sipyco.pc_rpc as RPC
from artiq.experiment import *

class LoadingSchedule(EnvExperiment):
        ''' Loading Schedule'''
        def build(self):
                self.setattr_device("core")
                self.setattr_device("scheduler")

                self.target_amp = self.get_dataset("Loading.RFramp_targetamp")
                self.ramp_rate = self.get_dataset("Loading.RFramp_ramprate")
                self.time_step = self.get_dataset("Loading.RFramp_timestep")
                self.num_points = self.get_dataset("Loading.RFramp_numpoints")
                self.loading_DopplerAmp = self.get_dataset("Loading.DopplerAmp")
                self.target_ULE369freq_Loading = self.get_dataset("Loading.ULE369_freq")

               # self.target_min_amp = self.get_dataset("Loading.target_min_amplitude")

        def prepare(self):
                # Terminate any running Idler jobs before setting up the experiment schedule
                for rid, job in self.scheduler.get_status().items():
                        if job["expid"]["class_name"] == "Idle369On355Pulsed":
                                print(f"[EXP SCHEDULE] Found active idler (RID {rid}). Requesting termination...")
                                self.scheduler.request_termination(rid)

        def run(self):

                expid_ULE369controlLoading = {
                        "file": "Manual Control/ULE369_Ramp.py",
                        "class_name": "ULE369_control",
                        "arguments": {"ramp_rate": 2.0 * MHz,
                                      "target_frequency": self.target_ULE369freq_Loading,
                                      "time_step": 100 * ms
                                      },
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_AOMchangeLoad = {
                        "file": "Manual Control/AOM_Change.py",
                        "class_name": "AOMChange",
                        "arguments": {
                                "u0ch1_Doppler": True,  # 25/12/17 gt: turn on Doppler (loading)
                                "DopplerAmp": self.loading_DopplerAmp,
                                "checkRaman2": True
                        },
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_set_loading_DCs = {
                        "file": "RFandDC/dc_assign_for_loading.py",
                        "class_name": "Loading",
                        "arguments": {},
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }
                expid_apply_DCs = {
                        "file": "RFandDC/DCelectrodes.py",
                        "class_name": "DC_Control",
                        "arguments": {},
                        "log_level": self.scheduler.expid["log_level"],
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_loading_RF_ramp = {
                        "file": "RFandDC/RFramp.py",
                        "class_name": "RFControl_Arduino",
                        "arguments": {"ramp_rate": self.ramp_rate,
                                      "target_amplitude": self.target_amp,
                                      "time_step": self.time_step,
                                       "num_points": self.num_points
                                      },
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                # included buffer, b/c when two back to back ramps are implemented, after ramp down
                # is complete, ramp up jumps to target amplitude without ramping
                '''
                expid_4 = {
                        "file": "Manual Control/bufferScheduler.py",
                        "class_name": "bufferScheduler",
                        "arguments": {},
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }
                '''

                print(self.scheduler.expid)

                self.scheduler.submit("main", expid_ULE369controlLoading)
                self.scheduler.submit('main', expid_AOMchangeLoad)
                self.scheduler.submit("main", expid_set_loading_DCs)
                self.scheduler.submit("main", expid_apply_DCs)
                self.scheduler.submit("main", expid_loading_RF_ramp)


                #self.scheduler.submit("main", expid_4)
