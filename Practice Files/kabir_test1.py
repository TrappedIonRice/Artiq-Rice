from artiq.experiment import *

class Test_ttl(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl4")

    @kernel
    def run(self):
        self.core.reset()
        self.ttl4.output()
        for i in range(100):
            delay(2*us)
            self.ttl4.pulse(2*us) #sends pulse for 2us
            delay(2*us)
            self.ttl4.pulsemu(2*us) #sends high pulse for 2us
