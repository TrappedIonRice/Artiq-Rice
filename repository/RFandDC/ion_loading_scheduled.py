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

               # self.target_min_amp = self.get_dataset("Loading.target_min_amplitude")

        def run(self):

                expid_1 = {
                        "file": "RFandDC/dc_assign_for_loading.py",
                        "class_name": "Loading",
                        "arguments": {},
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }
                expid_2 = {
                        "file": "RFandDC/DCelectrodes.py",
                        "class_name": "DC_Control",
                        "arguments": {},
                        "log_level": self.scheduler.expid["log_level"],
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_3 = {
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

                expid_AOMcontrolLoad = {
                        "file": "Manual Control/AOM_Control.py",
                        "class_name": "AOMControl",
                        "arguments": {
                                "u0ch1_Doppler": True,
                                "u0ch3_options": "Detection",
                                "u0ch3_Detection_or_Tickler": False,
                                "u2ch2_OP": False,
                                "u1ch1_LOP": False,
                                "u1ch2_MW": False,
                                "u1ch3_355_RamanB2": False,
                                "u2ch0_355_Raman1": False,
                                "u2ch1_355_RamanA16": False,
                                "ttl6_355_Raman2": True,
                                "u2ch3_369_ULE": False,
                                "u2ch2_RR_lock": False
                        },
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_AOMchangeLoad = {
                        "file": "Manual Control/AOM_Change.py",
                        "class_name": "AOMChange",
                        "arguments": {
                                "u0ch1_Doppler": True,  # 25/12/17 gt: turn on Doppler (loading)
                                "DopplerAmp": self.loading_DopplerAmp
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

                self.scheduler.submit("main", expid_1)
                self.scheduler.submit("main", expid_2)
                self.scheduler.submit("main", expid_3)
                self.scheduler.submit("main", expid_AOMcontrolLoad)
                self.scheduler.submit('main', expid_AOMchangeLoad)

                #self.scheduler.submit("main", expid_4)
