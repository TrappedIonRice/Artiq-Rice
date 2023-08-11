from artiq.experiment import *
from artiq.coredevice.urukul import *

class Urukul_Output(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")
        self.setattr_device("urukul0_ch0")


    @kernel
    def run(self):
        print("-----------------")

        self.core.reset()
        delay(10*ms)
        self.urukul0_cpld.init()
        delay(10*ms)

        self.urukul0_ch0.init()
        delay(10*ms)


        freq = 1*MHz
        amp = 0.4
        attenuation = 1.0

        self.urukul0_ch0.set_att(attenuation)
        self.urukul0_ch0.sw.on()
        delay(10*ms)

        self.urukul0_ch0.set(freq, amplitude = amp)

        print("Kernellllll")

        delay(5*ms)
