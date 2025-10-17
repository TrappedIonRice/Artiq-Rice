import time

import sipyco.pc_rpc as RPC
from artiq.experiment import *
import time

class bufferSchedulerTime(EnvExperiment):

    def build(self):
        self.setattr_argument("Waittime",NumberValue(default=0.0))
        pass
    def run(self):
        time.sleep(self.Waittime)
        pass
