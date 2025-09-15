from artiq.experiment import *

class LEDTest(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("led0")

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()  # 避免 underflow
        self.led0.on()
        delay(500*ms)
        self.led0.off()
