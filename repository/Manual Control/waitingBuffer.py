import time

import sipyco.pc_rpc as RPC
from artiq.experiment import *

class RecoveryWaitBuffer(EnvExperiment):

    def build(self):
        #self.setattr_device("core")
        self.wait_time= self.get_dataset("Loading.wait_time")*s
    #@kernel
    def run(self):
        #self.core.reset()
        time.sleep(self.wait_time)
