import time

import sipyco.pc_rpc as RPC
from artiq.experiment import *
import time

class ExperimentSchedule(EnvExperiment):
        ''' Experiment Schedule'''
        def build(self):
                self.setattr_device("core")
                self.setattr_device("scheduler")

                self.target_amp = self.get_dataset("Experiment_config.RFramp_targetamp")
                self.ramp_rate = self.get_dataset("Experiment_config.RFramp_ramprate")
                self.time_step = self.get_dataset("Experiment_config.RFramp_timestep")
                self.num_points = self.get_dataset("Experiment_config.RFramp_numpoints")
                self.experiment_DopplerAmp = self.get_dataset("Experiment_config.DopplerAmp")
                self.target_ULE369freq_Experiment = self.get_dataset("Experiment_config.ULE369_freq")
                self.target_ULE369freq_idle = self.get_dataset("Experiment_config.ULE369_freq_idle")

                self.default_Raman_time = float(self.get_dataset("355_RamanB1.Time(ms)")) * ms
                self.default_SBCtime = float(self.get_dataset("SBC.tone1.Time(ms)")) * ms


               # self.target_min_amp = self.get_dataset("Loading.target_min_amplitude")

        def prepare(self):
                # Terminate any running Idler jobs before setting up the experiment schedule
                for rid, job in self.scheduler.get_status().items():
                        if job["expid"]["class_name"] == "Idle369On355Pulsed":
                                print(f"[EXP SCHEDULE] Found active idler (RID {rid}). Requesting termination...")
                                self.scheduler.request_termination(rid)
                time.sleep(0.5)
                pass

        def run(self):

                expid_set_exp_DCs = {
                        "file": "RFandDC/dc_assign_for_experiment.py",
                        "class_name": "ExpConfig",
                        "arguments": {},
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }
                expid_apply_exp_DCs = {
                        "file": "RFandDC/DCelectrodes.py",
                        "class_name": "DC_Control",
                        "arguments": {},
                        "log_level": self.scheduler.expid["log_level"],
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_exp_rf_ramp = {
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

                expid_ULE369controlExperiment = {
                        "file": "Manual Control/ULE369_Ramp.py",
                        "class_name": "ULE369_control",
                        "arguments": {"ramp_rate": 2.0 * MHz,
                                      "target_frequency": self.target_ULE369freq_idle,
                                      "time_step": 100 * ms
                                      },
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_AOMchangeExp = {
                        "file": "Manual Control/AOM_Change.py",
                        "class_name": "AOMChange",
                        "arguments": {
                                "u0ch1_Doppler": True,  # 25/12/17 gt: turn on Doppler (loading)
                                "DopplerAmp": self.experiment_DopplerAmp,
                                "checkRaman2": False
                        },
                        "log_level": 0,
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }

                expid_idleExp = {
                        "file": "Experiments/idle_369_on_355_pulsed.py",
                        "class_name": "Idle369On355Pulsed",
                        "arguments": {"SBCTime_1": self.get_dataset("SBC.Times.Time1"),
                              "SBCTime_2": self.get_dataset("SBC.Times.Time2"),
                              "timeRaman": 0.001 * ms},
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


                print(self.scheduler.expid)

                self.scheduler.submit("main", expid_exp_rf_ramp)
                self.scheduler.submit("main", expid_set_exp_DCs)
                self.scheduler.submit("main", expid_apply_exp_DCs)


                self.scheduler.submit("main", expid_ULE369controlExperiment)
                # self.scheduler.submit("main", expid_AOMcontrolExp)
                time.sleep(0.1) # 26/07/05 gt: needed so 935 AOM doesnt turn off momentarily after
                                # it turns on when running the experiment config scheduler
                self.scheduler.submit("main", expid_AOMchangeExp)

                self.scheduler.submit("main", expid_buffer)

                time.sleep(1.0)

                self.scheduler.submit("main", expid_idleExp)
