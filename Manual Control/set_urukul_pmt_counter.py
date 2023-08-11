from artiq.experiment import *
import numpy as np
import time as tm
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import include

class SetAllUrukul(EnvExperiment):
    def build(self):
        # Devices
        self.setattr_device("core")
        # user arguments
        urukuls = ["0"]  # the list of the urukuls availible
        channels = ["0", "1", "2", "3"]  # the channel on a given urukul
        self.setattr_argument("urukul_num", EnumerationValue(urukuls, default="0"))
        #self.setattr_argument("channel_num", EnumerationValue(channels, default="0"))

        self.setattr_argument("ch0", BooleanValue(default=False))
        self.setattr_argument("frequency", NumberValue(default=1, unit="MHz", ndecimals=6), group = 'channel0')
        self.setattr_argument("amplitude", NumberValue(default=1, min=0, max=1, ndecimals=6), group = 'channel0')
        self.setattr_argument("attenuation", NumberValue(default=0, unit="dB", min=0, max=10), group = 'channel0')

        self.setattr_argument("ch1", BooleanValue(default=False))
        self.setattr_argument("frequency1", NumberValue(default=1, unit="MHz", ndecimals=6), group='channel1')
        self.setattr_argument("amplitude1", NumberValue(default=1, min=0, max=1, ndecimals=6), group='channel1')
        self.setattr_argument("attenuation1", NumberValue(default=0, unit="dB", min=0, max=10), group='channel1')

        self.setattr_argument("ch2", BooleanValue(default=False))
        self.setattr_argument("frequency2", NumberValue(default=1, unit="MHz", ndecimals=6), group='channel2')
        self.setattr_argument("amplitude2", NumberValue(default=1, min=0, max=1, ndecimals=6), group='channel2')
        self.setattr_argument("attenuation2", NumberValue(default=0, unit="dB", min=0, max=10), group='channel2')

        self.setattr_argument("ch3", BooleanValue(default=False))
        self.setattr_argument("frequency3", NumberValue(default=1, unit="MHz", ndecimals=6), group='channel3')
        self.setattr_argument("amplitude3", NumberValue(default=1, min=0, max=1, ndecimals=6), group='channel3')
        self.setattr_argument("attenuation3", NumberValue(default=0, unit="dB", min=0, max=10), group='channel3')

        self.setattr_argument("Turn_all_channels_off", BooleanValue(default=False))

        self.dict_freq = {"0": self.frequency, "1": self.frequency1, "2": self.frequency2, "3": self.frequency3}
        self.dict_amp = {"0": self.amplitude, "1": self.amplitude1, "2": self.amplitude2, "3": self.amplitude3}
        self.dict_att = {"0": self.attenuation, "1": self.attenuation1, "2": self.attenuation2, "3": self.attenuation3}
        set_channel = [self.ch0, self.ch1, self.ch2, self.ch3]
        self.channels = []
        self.frequencies = {}
        self.amplitudes= {}
        self.attenuations = {}
        self.x_vals = []
        self.y_vals = []
        self.count = 0
        self.time_stmp = 0

        for i in ["0", "1", "2", "3"]:
            self.setattr_device("urukul0" + "_ch" + i)
        for i in range(len(set_channel)):
            if set_channel[i]:
                self.channels.append(str(i))

        self.setattr_device("urukul0_cpld")


    def prepare(self):
        print("Preparing " + self.__class__.__name__)

        # prepare all children
        super().prepare()  # ensures the prepare method of any children (e.g. StdInlcude methods) are called by running the EnvEnvironment prepare() method

        # Devices that can't be done in build()


    def run(self):
        self.initialize_urukul()

        print("---------xxx---------")

        if self.Turn_all_channels_off == False:
            self.urukul_on()
        else:
            self.urukul_off()

    @kernel
    def urukul_on(self):
        self.core.reset()
        delay(500 * us)
        self.urukul0_cpld.init()
        delay(500*us)
        for channel in self.channels:
            if channel == "0":
                delay(500 * us)
                self.urukul0_ch0.set(self.frequency, amplitude=self.amplitude, phase_mode=2)
                # self.urukul0_ch0.cpld.get_att_mu()
                self.urukul0_ch0.set_att(self.attenuation)
                self.urukul0_ch0.sw.on()
            if channel == "1":
                delay(500 * us)
                self.urukul0_ch1.set(self.frequency1, amplitude = self.amplitude1, phase_mode=2)
               # self.urukul0_ch1.cpld.get_att_mu()
                self.urukul0_ch1.set_att(self.attenuation1)
                self.urukul0_ch1.sw.on()
            if channel == "2":
                delay(500*us)
                self.urukul0_ch2.set(self.frequency2, amplitude = self.amplitude2, phase_mode=2)
                self.urukul0_ch2.set_att(self.attenuation2)
                self.urukul0_ch2.sw.on()
            if channel == "3":
                delay(500*us)
                self.urukul0_ch3.set(self.frequency3, amplitude = self.amplitude3, phase_mode=2)
                self.urukul0_ch3.set_att(self.attenuation3)
                self.urukul0_ch3.sw.on()

        # delay(500 * us)
        # for channel in self.channels:
        #     self.urukul0_ch0.cpld.get_att_mu()
        # delay(500 * us)
        # for channel in self.channels:
        #     self.urukul0_ch0.set_att(1*dB)
        # delay(500 * us)
        # for urukul_switch in self.urukul_switches:
        #     urukul_switch.on()

    @kernel
    def urukul_off(self):
        self.core.reset()
        self.urukul0_ch0.sw.off()
        self.urukul0_ch1.sw.off()
        self.urukul0_ch2.sw.off()
        self.urukul0_ch3.sw.off()

        print("All Urukul switches turned off")

    @kernel
    def initialize_urukul(self):
        self.core.reset()

        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.urukul0_ch3.init()

        delay(5 * ms)




