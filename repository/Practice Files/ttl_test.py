from artiq.experiment import *


class Test_ttl(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl0")

    @kernel
    def run(self):
        self.core.reset()
        self.ttl0.output()
        
        for i in range(10):
        	self.ttl0.on()
        	delay(1000*ms)
        	self.ttl0.off()
        	delay(1000*ms)
        """
        for i in range(1000000):
            delay(2*us)
            self.ttl0.pulse(2*us)
        """
