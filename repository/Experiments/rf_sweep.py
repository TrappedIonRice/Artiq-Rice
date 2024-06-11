

from artiq.experiment import *
import numpy as np

class RfSweeper(EnvExperiment):

    def build(self):
        # Devices
        self.setattr_device("core")
        self.setattr_device("urukul0_ch3") # RF channel is very imp
        self.setattr_device("urukul0_cpld")

        self.setattr_argument("amp", NumberValue(default=0.8, min=0, max=0.8, ndecimals=6), group='channel3')
        self.setattr_argument("min_freq", NumberValue(default=0.264*MHz, unit="MHz", step=0.1, ndecimals=3), group='channel3')
        self.setattr_argument("max_freq", NumberValue(default=0.270*MHz, unit="MHz", step=0.1, ndecimals=3), group='channel3')
        self.setattr_argument("num_freq_pts", NumberValue(default=61, unit=None, scale=1, step=1, ndecimals=0, type='int'), group='channel3')


    def prepare(self):
        # Creates frequency range
        self.freq_range=np.linspace(self.min_freq, self.max_freq, self.num_freq_pts)
        self.set_dataset("freq_range",  self.freq_range, broadcast=True, archive=True)


    @kernel # following method is run in kernel
    def krun(self):
        delay(1 * ms)
        self.core.reset()
        delay(50 * us)
        self.urukul0_cpld.init()
        delay(50 * us)
        self.urukul0_ch3.init()
        self.urukul0_ch3.set_att(0*dB)

        exp_num = 0
        while True: # repeat for num_exp
            scan_direction = exp_num % 2 == 0
            if scan_direction:
                freq_num = 0
            else:
                freq_num = len(self.freq_range) - 1

            while (scan_direction and freq_num < len(self.freq_range)) or ((not scan_direction) and freq_num >= 0): # scan through frequencies
                delay(1 * ms)
                self.urukul0_ch3.set(frequency=self.freq_range[freq_num], amplitude=self.amp, phase_mode=2)
                delay(1 * ms)
                self.urukul0_ch3.sw.on()

                delay(50*ms) # time for which signal of specified frequency is generated

                self.urukul0_ch3.sw.off()
                delay(50 * us)

                if scan_direction:
                    freq_num += 1
                else:
                    freq_num -= 1

            exp_num += 1


    def run(self):
        self.krun()

