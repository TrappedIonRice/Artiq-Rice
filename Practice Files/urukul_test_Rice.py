
from artiq.coredevice.ad9910 import *
from artiq.coredevice.urukul import *
import numpy as np
#import oitg

from artiq.experiment import *

class UrukulTest_Rice(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")     # necessary for clock sync
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("urukul0_ch3")
        # self.setattr_device("_369_det")
        # self.setattr_device("MW")
        self.setattr_device("ttl4")
        self.t_pulse=100*us
    @kernel                                     # fpga commands nowonwards
    def run(self):
        self.core.reset()
        self.ttl4.output()
        self.core.break_realtime()

        delay(1 * ms)
        self.urukul0_cpld.init()
        self.ttl4.off()
        delay(2 * ms)
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        # self.urukul0_ch2.cfg_sw(True)
        self.urukul0_ch2.init()
        self.urukul0_ch3.init()

        delay(1 * ms)


        #ftw = self._369_pump.frequency_to_ftw(101 * MHz)
        #self.369dc.set_mu(ftw)
        #self._369_pump.set_mu(2*ftw)
        for i in range(4): self.urukul0_cpld.set_att(i,6.0*dB)
        self.urukul0_ch0.set(frequency=1 * MHz, amplitude= 1.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=0)
        #self.urukul0_ch0.set(frequency=2 * MHz, amplitude= 1.0, ref_time_mu=0)
        delay(1 * ms)
        self.urukul0_ch1.set(frequency=1 * MHz, amplitude=1.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=0)
        delay(1 * ms)


        #self.urukul0_ch0.set_amplitude(0.1)

        delay_mu(8)
        # self.urukul0_ch1.set(frequency=400 * kHz, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=0)

        # with sequential:
        #     # delay_mu(8)
        #     self.urukul0_ch0.set(frequency=2 * MHz,  phase_mode=PHASE_MODE_TRACKING,ref_time_mu=0)
        #     # delay_mu(8)
        #     self.urukul0_ch1.set(frequency=4 * MHz, phase_mode=PHASE_MODE_TRACKING,ref_time_mu=0)
        #     # delay_mu(8)
        #     # self._369_det.set(frequency=2 * MHz, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=0)
        #     # delay_mu(8)
        for i in range(10000):
            # with parallel:
            #     self.ttl4.pulse(self.t_pulse)
            #     self.urukul0_ch0.sw.pulse(self.t_pulse)
            #     self.urukul0_ch1.sw.pulse(self.t_pulse)
            #-mod----------
            #delay(1*us)
            #with parallel:
            # with sequential:
            #     self.urukul0_ch0.sw.pulse(self.t_pulse)
            #     self.urukul0_ch1.sw.pulse(self.t_pulse)
            self.urukul0_ch0.sw.on()
            self.urukul0_ch1.sw.on()
            delay(self.t_pulse)
            self.urukul0_ch0.sw.off()
            self.urukul0_ch1.sw.off()
            x = 7 * 49
            y = float(x)
            for i in range(1000):
                if y == x:
                    z = 5*7287487
            #delay(100*us)
            #---mod----------
                # self._369_pump.sw.pulse(self.t_pulse)
                # self._369_det.sw.pulse(self.t_pulse)
