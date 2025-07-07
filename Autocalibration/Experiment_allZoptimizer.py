import time

import sipyco.pc_rpc as RPC
from artiq.experiment import *

class ExperimentOptimizerSchedule(EnvExperiment):
        ''' Experiment Optimizer Schedule'''
        def build(self):
                self.setattr_device("core")
                self.setattr_device("scheduler")

                self.target_amp = self.get_dataset("Experiment_config.RFramp_targetamp")
                self.ramp_rate = self.get_dataset("Experiment_config.RFramp_ramprate")
                self.time_step = self.get_dataset("Experiment_config.RFramp_timestep")
                self.num_points = self.get_dataset("Experiment_config.RFramp_numpoints")

               # self.target_min_amp = self.get_dataset("Loading.target_min_amplitude")

        def run(self):

                expid_1 = {
                        "file": "RFandDC/dc_assign_for_experiment.py",
                        "class_name": "ExpConfig",
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

                self.scheduler.submit("main", expid_3)
                self.scheduler.submit("main", expid_1)
                self.scheduler.submit("main", expid_2)
                #self.scheduler.submit("main", expid_4)
