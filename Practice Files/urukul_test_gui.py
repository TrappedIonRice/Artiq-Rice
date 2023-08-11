from artiq.experiment import *
import numpy as np
import time as tm
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import include

class SetUrukul(EnvExperiment):
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
        self.urukul_channels = []
        self.urukul_switches = []


        ttl_params = ["ttl0_counter", "ttl1_counter", "ttl2_counter", "ttl3_counter"]
        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl0_counter"))
        self.setattr_device(str(self.INPUT_TTL))  # must typecast or NoneType error when recomputing args
        self.ttl = self.get_device(self.INPUT_TTL)
        self.setattr_argument("detection_time", NumberValue(default=1, unit="ms", ndecimals=6))
        self.setattr_argument("acquisition_rate", NumberValue(default=1, unit = "ms", ndecimals=6))
        self.setattr_argument("max_points", NumberValue(default=1000, ndecimals=0, step=1))
        self.setattr_device("ccb")
        self.setattr_device("scheduler")
        # AOMs = ["422 cavity", "461 cavity", "422 sigma", "422 sigma minus", "422 sigma plus", "1092 sigma plus",
        #         "1092 sigma minus", "422 cool", "1092 repump", "1092 cavity EOM", "1092 pi", "408 ion", "1033 ion",
        #         "1004 ion", "422 EOM"]
        # self.setattr_argument("AOMs", EnumerationValue(AOMs, default="422 sigma"))


        self.uruk = ''

    def prepare(self):
        print("Preparing " + self.__class__.__name__)

        # prepare all children
        super().prepare()  # ensures the prepare method of any children (e.g. StdInlcude methods) are called by running the EnvEnvironment prepare() method

        # Devices that can't be done in build()
        self.urukul_channels = {"0" : self.get_device("urukul0_ch0"), "1" : self.urukul0_ch1, "2" : self.urukul0_ch2, "3" : self.urukul0_ch3}
        for channel in self.channels:
            self.frequencies[channel] = self.dict_freq[channel]
            self.amplitudes[channel] = self.dict_amp[channel]
            self.attenuations[channel] = self.dict_att[channel]
        print(self.urukul_channels)
        print(self.channels)


        for channel in self.channels:
            self.urukul_switches.append(self.get_device("ttl_urukul0" + "_sw" + channel))


        self.set_dataset("PMT_Counts", np.full(self.max_points, float(np.nan)), broadcast=True, archive=True)

        command = "${artiq_applet}plot_xy PMT_Counts"
        self.ccb.issue("create_applet", "PMT counts", command)

        print("Finished preparing " + self.__class__.__name__)

    @kernel
    def krun(self, time):
        self.core.reset()

        with parallel:
            self.ttl.gate_rising(self.detection_time)
            delay(self.detection_time)
        count = self.ttl.fetch_count()
        self.count = count
        #self.mutate_dataset("PMT_Counts", time, count)
        delay(self.acquisition_rate)

        time += 1

        return time


    def run(self):
        start_time = tm.perf_counter()
        self.initialize_urukul()

        print("---------xxx---------")

        self.urukul_on()

#        self.urukul_off()
        self.core.reset()
        # self.set_dataset("PMT_Counts", np.full(self.upper_bound, float(np.nan)), broadcast=True, archive=True)

        time = 0

        while True:
            try:
                if self.scheduler.check_pause():
                    self.core.comm.close()
                    self.scheduler.pause()
            except TerminationRequested:
                print("Terminated gracefully")
                return
            time = self.krun(time)
            tm.sleep(self.acquisition_rate)
            self.mutate_dataset("PMT_Counts", int(tm.perf_counter() - start_time), self.count)

            print(int(tm.perf_counter() - start_time))






    @kernel
    def urukul_on(self):
        self.core.reset()
        delay(500 * us)
        for channel in self.channels:
            if channel == "0":
                self.urukul0_ch0.set(self.frequency, self.amplitude)
                delay(500*us)
                self.urukul0_ch0.cpld.get_att_mu()
                delay(500*us)
                self.urukul0_ch0.set_att(self.attenuation)
            if channel == "1":
                self.urukul0_ch1.set(self.frequency1, self.amplitude1)
                delay(500*us)
                self.urukul0_ch1.cpld.get_att_mu()
                delay(500*us)
                self.urukul0_ch1.set_att(self.attenuation1)
            if channel == "2":
                self.urukul0_ch2.set(self.frequency2, self.amplitude2)
                delay(500*us)
                self.urukul0_ch2.cpld.get_att_mu()
                delay(500*us)
                self.urukul0_ch2.set_att(self.attenuation2)
            if channel == "3":
                self.urukul0_ch3.set(self.frequency3, self.amplitude3)
                delay(500*us)
                self.urukul0_ch3.cpld.get_att_mu()
                delay(500*us)
                self.urukul0_ch3.set_att(self.attenuation3)

        # delay(500 * us)
        # for channel in self.channels:
        #     self.urukul0_ch0.cpld.get_att_mu()
        # delay(500 * us)
        # for channel in self.channels:
        #     self.urukul0_ch0.set_att(1*dB)
        # delay(500 * us)
        for urukul_switch in self.urukul_switches:
            urukul_switch.on()

    @kernel
    def urukul_off(self):
        self.core.reset()
        for urukul_switch in self.urukul_switches:
            urukul_switch.off()
        for key in self.urukul_channels:
            self.urukul_channels[key].set(frequency=0.0, amplitude=0.0)
        print("Frequency and Amplitude set to Zero")

    @kernel
    def initialize_urukul(self):
        self.core.reset()

        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.urukul0_ch3.init()

        delay(5 * ms)





