
from artiq.experiment import *
from artiq.coredevice.ad9910 import *
import numpy as np

class Gen_Urukul_Scan(EnvExperiment):
    """Gen_Urukul_Scan

    REPLACED BY ADJ_CAVITY_SCAN 9/22/21
    Written by Raffi, this experiment scans an urukul channel at a user given step size and speed based on start and end values specified by the user.
    It simultaneously logs the PMT counts at each step for a user specified bin size.
    For now, to change the laser that you scan Ctrl+H to find and replace.  The names and channels can be seen at the bottom of the ddb under aliases.
    """

    def build(self):
        self.setattr_device("core")

        self.setattr_device("ttl0")  # PMT Counts
        # self.setattr_device("ttl1") # Too much light

        self.setattr_device("urukul0_ch0")  # change urukul channel here

        # user specified arguments
        self.setattr_argument("Start", NumberValue(default=250, unit="MHz"))
        self.setattr_argument("End", NumberValue(default=20, unit='MHz'))
        self.setattr_argument("Step", NumberValue(default=1, unit='MHz'))
        self.setattr_argument("Speed", NumberValue(default=500, unit="ms"))
        self.setattr_argument("amplitude", NumberValue(default=0))
        self.setattr_argument("PMT_Bin_Size", NumberValue(default=0, ndecimals=0, step=1, unit="s"))


    @kernel
    def run(self):
        self.core.reset()

        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch0.set_phase_mode(PHASE_MODE_CONTINUOUS)

        # self.initialize_urukul()
        upper_bound = 550

        self.set_dataset("PMT_Counts", np.full(upper_bound, float(np.nan)), broadcast=True)

        self.core.break_realtime()

        att = 0.0
        amp = .26  # eventually need to make scannable for each laser
        step = self.Step
        freq = self.Start
        time_delay = self.Speed
        xpoint = 0

        while (freq >= self.End):  # Change order here > or <
            delay(100 * us)
            self.urukul0_ch0.set(frequency=freq, amplitude=amp)
            delay(60 * us)
            self.urukul0_ch0.cpld.get_att_mu()
            delay(60 * us)
            self.urukul0_ch0.set_att(att)
            self.urukul0_ch0.sw.on()
            delay(self.Speed * ms)
            with parallel:
                gate_end_mu = self.ttl0.gate_rising(self.PMT_Bin_Size * s)
                delay(self.PMT_Bin_Size * s)
            count = self.ttl0.count(gate_end_mu)
            delay(10 * ms)
            freq_422 = int(freq * 0.000001 + 83 + (freq * 0.000001 - 300))
            self.mutate_dataset("PMT_Counts", xpoint,
                                count)  # currently, I have it so you have to change the x-axis here when you change the laser
            xpoint += 1
            freq -= step  # += or -=
            # print(freq)
            # print(freq_422)

        # @Raffi I had to add all of this here instead of just the one commented out line or else the rf would drop out very briefly before its final position.
        delay(100 * us)
        self.urukul0_ch0.set(frequency=freq, amplitude=amp)
        delay(60 * us)
        self.urukul0_ch0.cpld.get_att_mu()
        delay(60 * us)
        self.urukul0_ch0.set_att(att)
        self.urukul0_ch0.sw.on()
        delay(self.Speed * ms)
        # self.sigma_422.set(frequency=freq - step, amplitude=amp) # This sets the frequency back to what you want it to be
        self.urukul0_ch0.sw.off()
        print("Done scanning")


    @kernel
    def initialize_urukul(self):
        self.core.reset()

        self.urukul0_ch0.cpld.init()

        #self.urukul1_ch0.cpld.init()

      #  self.urukul2_ch0.cpld.init()

        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.urukul0_ch3.init()

      #   self.urukul1_ch1.init()
      #  self.urukul1_ch2.init()
      #  self.urukul1_ch3.init()

      #  self.urukul2_ch0.init()
      #  self.urukul2_ch1.init()
      #  self.urukul2_ch2.init()
      #  self.urukul2_ch3.init()

        delay(5 * ms)

