from ndscan.experiment import *

from artiq.language.core import delay
from artiq.language.units import ms, us
from artiq.language.core import now_mu, delay, at_mu, parallel, sequential

class ReadTTLInput(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("ttl0")
        self.setattr_device("ttl4")

    @kernel
    def run(self):
        self.core.reset()
        delay(1 * ms)
        self.urukul0_cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.ttl4.output()
        self.ttl0.input()
        delay(1 * ms)
       # self.urukul0_ch0.sw.on()
      #  self.urukul0_ch0.set(1*MHz)
      #  self.urukul0_ch0.set_att(10.0)

        with parallel:
            rising_time = self.ttl0.gate_rising(10 * ms)
            with sequential:
                for i in range(10):
                    self.ttl4.pulse(0.2*ms)
                    delay(0.2*ms)

        #self.ttl0.pulse(1*us)
        delay(500*us)
        count_edges = self.ttl0.count(rising_time)
       # self.urukul0_ch0.sw.off()

        print(count_edges)
