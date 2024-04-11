import sipyco.pc_rpc as RPC
from artiq.experiment import *

class SchedulerTest(EnvExperiment):
        def build(self):
                self.setattr_device("core")
                self.setattr_device("scheduler")

        def run(self):
                expid_1 = {
                        "file": "RFandDC/DCelectrodes.py",
                        "class_name": "DC_Control",
                        "arguments": {},
                        "log_level": 0,#self.scheduler.expid["log_level"],
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }
                expid_2 = {
                        "file": "Manual Control/zotino_control.py",
                        "class_name": "SetZotino",
                        "arguments": {"channel":0,"value":0.8,"reset":False},
                        "log_level": self.scheduler.expid["log_level"],
                        "repo_rev": self.scheduler.expid["repo_rev"],
                }
                print(self.scheduler.expid)
                self.scheduler.submit("main", expid_1)
                self.scheduler.submit("main", expid_2)


#
#
# expid = {
#         "class_name": "DC_Control",
#         "file": "DCelectrodes.py",
#         "arguments": {"arg_name": 0},
#         "log_level": 10,
#         "repo_rev": "N/A",
# }
# scheduler = RPC.Client("192.168.1.70" ,1384 , "master_schedule")
# scheduler.submit(pipeline_name="main", expid=expid, priority=0, due_date=None, flush=False)