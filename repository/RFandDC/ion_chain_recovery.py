import time

import sipyco.pc_rpc as RPC
from artiq.experiment import *

class RecoverySchedule(EnvExperiment):
        ''' Ion Recovery Schedule'''
        def build(self):
                self.setattr_device("core")
                self.setattr_device("scheduler")

                self.target_amp_Exp = self.get_dataset("Experiment_config.RFramp_targetamp")
                self.ramp_rate_Exp = self.get_dataset("Experiment_config.RFramp_ramprate")
                self.time_step_Exp = self.get_dataset("Experiment_config.RFramp_timestep")
                self.num_points_Exp = self.get_dataset("Experiment_config.RFramp_numpoints")

                self.target_amp_Loading = self.get_dataset("Loading.RFramp_targetamp")
                self.ramp_rate_Loading = self.get_dataset("Loading.RFramp_ramprate")
                self.time_step_Loading = self.get_dataset("Loading.RFramp_timestep")
                self.num_points_Loading = self.get_dataset("Loading.RFramp_numpoints")
                self.wait_time= self.get_dataset("Loading.wait_time") # seconds

                self.target_ULE369freq_Loading= self.get_dataset("Loading.ULE369_freq")
                self.target_ULE369freq_Experiment = self.get_dataset("Experiment_config.ULE369_freq")

                self.experiment_DopplerAmp = self.get_dataset("Experiment_config.DopplerAmp")  # 25/12/17 gt
                self.loading_DopplerAmp = self.get_dataset("Loading.DopplerAmp")


               # self.target_min_amp = self.get_dataset("Loading.target_min_amplitude")

        # @kernel()
        # def wait_function(self):
        #     self.core.reset()
        #     delay(self.wait_time*s)

        def prepare(self):
                pass
                # self.experiment_DopplerAmp = self.get_dataset("Doppler.Amp") # not doing anything
                # self.experiment_DopplerAmp = self.get_dataset("Experiment_config.DopplerAmp") # 25/12/17 gt (not working)
                # self.loading_DopplerAmp = self.get_dataset("Loading.DopplerAmp") # not doing anything

        def run(self):
            # self.experiment_DopplerAmp = self.get_dataset("Doppler.Amp")
            # self.loading_DopplerAmp = self.get_dataset("Loading.DopplerAmp")
                expid_assignDCExp = {
                        "file": "RFandDC/dc_assign_for_experiment.py",
                        "class_name": "ExpConfig",
                        "arguments": {},
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }
                expid_assignDCLoading = {
                    "file": "RFandDC/dc_assign_for_loading.py",
                    "class_name": "Loading",
                    "arguments": {},
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_setDC = {
                        "file": "RFandDC/DCelectrodes.py",
                        "class_name": "DC_Control",
                        "arguments": {},
                        "log_level": self.scheduler.expid["log_level"],
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_setRFExp = {
                        "file": "RFandDC/RFramp.py",
                        "class_name": "RFControl_Arduino",
                        "arguments": {"ramp_rate": self.ramp_rate_Exp,
                                      "target_amplitude": self.target_amp_Exp,
                                      "time_step": self.time_step_Exp,
                                       "num_points": self.num_points_Exp
                                      },
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_setRFLoading = {
                    "file": "RFandDC/RFramp.py",
                    "class_name": "RFControl_Arduino",
                    "arguments": {"ramp_rate": self.ramp_rate_Loading,
                                  "target_amplitude": self.target_amp_Loading,
                                  "time_step": self.time_step_Loading,
                                  "num_points": self.num_points_Loading
                                  },
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_AOMcontrolLoading = {
                    "file": "Manual Control/AOM_Control.py",
                    "class_name": "AOMControl",
                    "arguments": {
                        "u0ch1_Doppler":True,
                        "u0ch3_options": "Detection",
                        "u0ch3_Detection_or_Tickler":True,
                        "u1ch3_369_protection":True,
                        "u2ch0_355_Raman1":True,
                        "ttl6_355_Raman2":True,
                        "u2ch3_369_ULE": True,
                        "u2ch2_RR_lock": True
                    },
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_AOMcontrolExp = {
                    "file": "Manual Control/AOM_Control.py",
                    "class_name": "AOMControl",
                    "arguments": {
                        "u0ch1_Doppler": True, # 25/12/17 gt: will turn it on when setting the different Doppler AOM frequencies below
                        "u0ch3_options": "Detection",
                        "u0ch3_Detection_or_Tickler": False,
                        "u1ch3_369_protection": True,
                        "u2ch0_355_Raman1": False,
                        "ttl6_355_Raman2": False,
                        "u2ch3_369_ULE":True,
                        "u2ch2_RR_lock":True
                    },
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_AOMchangeLoad = {
                    "file": "Manual Control/AOM_Change.py",
                    "class_name": "AOMChange",
                    "arguments": {
                        "u0ch1_Doppler": True, # 25/12/17 gt: turn on Doppler (loading)
                        "DopplerAmp": self.loading_DopplerAmp
                    },
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_AOMchangeExp = {
                    "file": "Manual Control/AOM_Change.py",
                    "class_name": "AOMChange",
                    "arguments": {
                        "u0ch1_Doppler": True,# 25/12/17 gt: turn on Doppler (exp)
                        "DopplerAmp": self.experiment_DopplerAmp
                    },
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_ULE369controlLoading = {
                    "file": "Manual Control/ULE369_Ramp.py",
                    "class_name": "ULE369_control",
                     "arguments": {"ramp_rate": 0.5*MHz,
                                  "target_frequency": self.target_ULE369freq_Loading,
                                  "time_step": 100*ms
                                  },
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_ULE369controlExperiment= {
                    "file": "Manual Control/ULE369_Ramp.py",
                    "class_name": "ULE369_control",
                     "arguments": {"ramp_rate": 0.5*MHz,
                                  "target_frequency": self.target_ULE369freq_Experiment,
                                  "time_step": 100*ms
                                  },
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }


                # included buffer, b/c when two back to back ramps are implemented, after ramp down
                # is complete, ramp up jumps to target amplitude without ramping

                expid_buffer = {
                        "file": "Manual Control/bufferScheduler.py",
                        "class_name": "bufferScheduler",
                        "arguments": {},
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }
                expid_wait_buffer = {
                    "file": "Manual Control/waitingBuffer.py",
                    "class_name": "RecoveryWaitBuffer",
                    "arguments": {},
                    "log_level": 0,
                    "repo_rev": self.scheduler.expid["repo_rev"],
                }



                print(self.scheduler.expid)


                # Sequence:
                # 1) (Detune 369: ...877THz to ...817THz on laser lock program)
                # 2) Turn on detection, Raman 1,2, Protection
                # 3) Ramp RF down to loading or recovery config
                # 4) Assign DCs
                # 5) Wait
                # 6) Ramp RF back to exp config
                # 7) Assign DCs
                # 8) Turn off detection, Raman 1,2. Leave Protection on

                # self.scheduler.submit("main",expid_ULE369controlLoading)
                #self.set_dataset("Doppler.Amp", self.loading_DopplerAmp, broadcast=True, persist=True) # currently this needs ot be reconfigured as another schedule
                # or else all direct commands of this program are executed before any of the expid's
                self.scheduler.submit("main", expid_buffer)

                self.scheduler.submit("main", expid_AOMcontrolLoading)
                self.scheduler.submit("main", expid_AOMchangeLoad)  # Turn on Doppler with the loading amplitude

                self.scheduler.submit("main", expid_setRFLoading)
                self.scheduler.submit("main", expid_assignDCLoading)
                self.scheduler.submit("main", expid_setDC)
                self.scheduler.submit("main", expid_wait_buffer)
                self.scheduler.submit("main", expid_setRFExp)
                self.scheduler.submit("main", expid_assignDCExp)
                self.scheduler.submit("main", expid_setDC)
                #self.set_dataset("Doppler.Amp", self.experiment_DopplerAmp, broadcast=True, persist=True)

                self.scheduler.submit("main", expid_AOMcontrolExp)
                self.scheduler.submit("main", expid_AOMchangeExp) # Turn on Doppler with the experiment amplitude

                self.scheduler.submit("main", expid_buffer)
                # self.scheduler.submit("main", expid_ULE369controlExperiment)


