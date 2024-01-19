from artiq.experiment import *
import numpy as np
import time as tm
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


class SetAllUrukul(EnvExperiment):
    def build(self):
        # Devices
        self.setattr_device("core")
        # user arguments
        urukuls = ["0"]  # the list of the urukuls availible
        channels = ["0", "1", "2", "3"]  # the channel on a given urukul
        #channels=["1","2","3"]
        self.setattr_argument("urukul_num", EnumerationValue(urukuls, default="0"))
        self.setattr_argument("channel_num", EnumerationValue(channels, default="0"))

        self.setattr_argument("ch0", BooleanValue(default=True))
        self.setattr_argument("frequency", NumberValue(default=36.916*MHz, unit="MHz", ndecimals=6), group = 'channel0')
        #self.setattr_argument("amplitude", NumberValue(default=0.0001, min=0, max=0.9, ndecimals=6), group = 'channel0')
        # exclusively setting urukul0, connected to RF, to RFamp dataset variable
        #self.amplitude=self.get_dataset("UrukulCh0_RFamp")
        self.setattr_dataset("UrukulCh0_RFamp")
        self.setattr_argument("attenuation", NumberValue(default=0, unit="dB", min=0, max=10), group = 'channel0')

        self.DopplerAmp = self.get_dataset("Doppler.Amp")
        self.DopplerFrequency = self.get_dataset("Doppler.Frequency")
        self.DetectionAmp = self.get_dataset("Detection.Amp")
        self.DetectionFrequency = self.get_dataset("Detection.Frequency")
        self.OPAmp = self.get_dataset("OP.Amp")
        self.OPFrequency = self.get_dataset("OP.Frequency")



        self.setattr_argument("ch1", BooleanValue(default=False))
        #self.setattr_argument("frequency1", NumberValue(default=195*MHz, unit="MHz", ndecimals=6), group='channel1')
        #self.setattr_argument("amplitude1", NumberValue(default=0.8, min=0, max=0.9, ndecimals=6), group='channel1')
        self.setattr_argument("attenuation1", NumberValue(default=0, unit="dB", min=0, max=10), group='channel1')

        self.setattr_argument("ch2", BooleanValue(default=False))
        #self.setattr_argument("frequency2", NumberValue(default=225*MHz, unit="MHz", ndecimals=6), group='channel2')
        #self.setattr_argument("amplitude2", NumberValue(default=0.9, min=0, max=0.9, ndecimals=6), group='channel2')
        self.setattr_argument("attenuation2", NumberValue(default=0, unit="dB", min=0, max=10), group='channel2')

        self.setattr_argument("ch3", BooleanValue(default=False))
        #self.setattr_argument("frequency3", NumberValue(default=225*MHz, unit="MHz", ndecimals=6), group='channel3')
        #self.setattr_argument("amplitude3", NumberValue(default=0, min=0, max=0.9, ndecimals=6), group='channel3')
        self.setattr_argument("attenuation3", NumberValue(default=0, unit="dB", min=0, max=10), group='channel3')

        self.setattr_argument("Turn_all_channels_off", BooleanValue(default=False))

        self.dict_freq = {"0": self.frequency,
                        "1":  self.DopplerFrequency, "2": self.DetectionFrequency, "3": self.OPFrequency}
        self.dict_amp = {"0": self.UrukulCh0_RFamp,
                         "1": self.DopplerAmp, "2": self.DetectionAmp, "3":  self.OPAmp}
        self.dict_att = {"0": self.attenuation,
                         "1": self.attenuation1, "2": self.attenuation2, "3": self.attenuation3}
        set_channel = [self.ch0, self.ch1, self.ch2, self.ch3]
        #set_channel = [self.ch1, self.ch2, self.ch3]
        self.channels = []
        self.frequencies = {}
        self.amplitudes= {}
        self.attenuations = {}
        self.x_vals = []
        self.y_vals = []
        self.count = 0
        self.time_stmp = 0

        for i in ["0", "1", "2", "3"]:
       # for i in ["1", "2", "3"]:
            self.setattr_device("urukul0" + "_ch" + i)
        for i in range(len(set_channel)):
            if set_channel[i]:
                self.channels.append(str(i))
                #self.channels.append(str(i+1))

        self.setattr_device("urukul0_cpld")


    def prepare(self):
        print("Preparing " + self.__class__.__name__)

        # prepare all children
        super().prepare()  # ensures the prepare method of any children (e.g. StdInlcude methods) are called by running the EnvEnvironment prepare() method
        # print(self.amplitude)
        # delay(1*ms)
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
        delay(500* us)
        for channel in range(len(self.channels)):
            if self.channels[channel]=="0":
                delay(10 * us)
                self.urukul0_ch0.set(self.frequency, amplitude=self.UrukulCh0_RFamp, phase_mode=2)
                # self.urukul0_ch0.cpld.get_att_mu()
                self.urukul0_ch0.set_att(self.attenuation)
                self.urukul0_ch0.sw.on()
                #print("RFamp: ", end='')
                #print(self.UrukulCh0_RFamp)
            if self.channels[channel]=="1":
                delay(10 * us)
                self.urukul0_ch1.set( self.DopplerFrequency, amplitude = self.DopplerAmp, phase_mode=2)
               # self.urukul0_ch1.cpld.get_att_mu()
                self.urukul0_ch1.set_att(self.attenuation1)
                self.urukul0_ch1.sw.on()
            if self.channels[channel]=="2":
                delay(10 * us)
                self.urukul0_ch2.set( self.DetectionFrequency, amplitude = self.DetectionAmp, phase_mode=2)
                self.urukul0_ch2.set_att(self.attenuation2)
                self.urukul0_ch2.sw.on()
            if self.channels[channel]=="3":
                delay(10 * us)
                self.urukul0_ch3.set( self.OPFrequency, amplitude = self.OPAmp, phase_mode=2)
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
        #Does not turn off RF
        #self.urukul0_ch0.sw.off()
        self.urukul0_ch1.sw.off()
        self.urukul0_ch2.sw.off()
        self.urukul0_ch3.sw.off()
        delay(1*ms)

        print("All Urukul switches turned off")

    @kernel
    def initialize_urukul(self):
        self.core.reset()
        #self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.urukul0_ch3.init()
        delay(1 * ms)




