from artiq.experiment import*
# modified to pulse 5 times

class LED(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("led0")

    @kernel
    def run(self):
        self.core.reset()
       # self.led0.off()
       # self.led0.pulse_
        for i in range(5):
            self.led0.on()
            delay(1000*ms)
            self.led0.off()
            delay(1000*ms)
