from artiq.experiment import *


class Test_ttl(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl0")


    @kernel
    def run(self):
        dict_obj = {"ttl0" : self.get_device("ttl0")}
        self.core.reset()
        self.ttl0.input()

        for i in range(10):
            self.ttl0.on()
            delay(1000 * ms)
            self.ttl0.off()
            delay(1000 * ms)
            print(self.ttl0.sample_input())

            print(dict_obj["ttl0"].sample_input)

