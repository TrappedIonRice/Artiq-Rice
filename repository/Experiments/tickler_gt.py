from artiq.experiment import *
import numpy as np

class Tickle(EnvExperiment):

    def build(self):
        # Devices
        self.setattr_device("core")
        # user arguments
        urukuls = ["0"]  # the list of the urukuls availible
        channels = ["0", "1"]  # list of channel on a given urukul; only use channel 0

        # To set all channels of the urukul (device drivers) as attributes
        for i in ["0", "1"]:
            self.setattr_device("urukul0" + "_ch" + i)

        self.setattr_device("ttl0") # PMT counter input to DIO
        self.setattr_device("ttl4") # output of false signal
        self.setattr_device("urukul0_cpld") # What for?

        # EnumerationValue specifies an argument that can take a string value among a set of string values
        self.setattr_argument("urukul_num", EnumerationValue(urukuls, default="0")) # specify urukul
        self.setattr_argument("channel_num", EnumerationValue(channels, default="0")) # specify channel

        self.setattr_argument("ch0", BooleanValue(default=False)) # toggle to turn on and off the channel
        self.setattr_argument("frequency", NumberValue(default=37.097 * MHz, unit="MHz", ndecimals=6), group='channel0')
        self.setattr_argument("amplitude", NumberValue(default=1, min=0, max=1, ndecimals=6), group='channel0')
        self.setattr_argument("attenuation", NumberValue(default=0, unit="dB", min=0, max=10), group='channel0')

        self.setattr_argument("ch1", BooleanValue(default=False))
        self.setattr_argument("frequency1", NumberValue(default=195 * MHz, unit="MHz", ndecimals=6), group='channel1')
        self.setattr_argument("amplitude1", NumberValue(default=1, min=0, max=1, ndecimals=6), group='channel1')
        self.setattr_argument("attenuation1", NumberValue(default=0, unit="dB", min=0, max=10), group='channel1')

        self.setattr_argument("Turn_all_channels_off", BooleanValue(default=False)) # toggle to turn on and off all channels

        # What for?
        self.dict_freq = {"0": self.frequency, "1": self.frequency1}
        self.dict_amp = {"0": self.amplitude, "1": self.amplitude1}
        self.dict_att = {"0": self.attenuation, "1": self.attenuation1}

        # Bools corresponding to on/off channels
        set_channel = [self.ch0, self.ch1]

        self.channels = [] # Will contain 'on' channels
        self.frequencies = {}
        self.amplitudes = {}
        self.attenuations = {}
        self.x_vals = []
        self.y_vals = []
        self.count = 0
        self.time_stmp = 0

        for i in range(len(set_channel)):
            if set_channel[i]: # determines whether ch is on or off
                self.channels.append(str(i))

        # counter attributes
        self.setattr_argument("Bin_Size", NumberValue(default=0.1, ndecimals=4, unit="s"))
        self.setattr_argument("num_exp", NumberValue(default=1000, ndecimals=0, step=1))
        self.setattr_argument("num_scan_pts", NumberValue(default=1000, ndecimals=0, step=1))

    def prepare(self):

        # broadcast: the data is sent in real-time to the master, which dispatches it.
        # archive: the data is saved into the local storage of the current run (archived as a HDF5 file).
        self.set_dataset("Tickler_counts_freq", np.full(self.num_points, float(np.nan)), broadcast=True, archive=True)
        self.set_dataset("PMT_counts_y", np.full(self.num_points, float(np.nan)), broadcast=True, archive=True)

        # creates applet to plot the results
        command = "${artiq_applet}plot_xy PMT_counts_y --x PMT_counts_x"
        self.ccb.issue("create_applet", "Tickler", command)

    # borrowed from pmt_counter.py file
    @kernel # following method is run in kernel
    def krun(self):
        # next four lines identical to code from set_urukul_pmt_counter.py
        self.core.reset()
        delay(500 * us)
        self.urukul0_cpld.init() # what is the purpose of this?
        delay(500 * us)

        # DDS0 Doppler cooler "on"; we want it to run continuously through the run
        self.urukul0_ch0.set(self.frequency, amplitude=self.amplitude, phase_mode=2)
        self.urukul0_ch0.sw.on()

        delay(10 * us)  # arbitrary; consider lower bound

        # with no delay, run counter, tickler, false signal in parallel
        # borrowed from method 3 from pmt_counter.py
        '''
            To run the PMT counter, signal pulse, and TTL4 false output signal
            in parallel, use the following construct within @kernel
                                                            def krun(self):

            with parallel:
                <counter>
                <tickler>
                <false signal>

        '''

        tracker1 = 0
        while (tracker1 < self.num_scan_pts):

            tracker2 = 0
            self.urukul0_ch1.set(self.frequency, amplitude=self.amplitude, phase_mode=2) # with index of tracker1
            while (tracker2 < self.num_exp):

                # run the contents in parallel

                with parallel:
                    # PMT counter
                    # What do the next three lines do?
                    countstime = self.ttl0.gate_rising(self.Bin_Size * s)
                    delay(self.Bin_Size * s)
                    self.count = self.ttl0.count(countstime)  # for ttl0_counter type only
                    delay(10 * us)

                    # Tickler
                    self.urukul0_ch1.pulse(self.Bin_Size*s + 10*ms + 1*ms)

                    # False output signal from ttl4
                    self.ttl4.pulse(self.Bin_Size*s + 10*ms + 1 * ms)

            self.mutate_dataset("PMT_counts_x", tracker2, tracker2 * self.Bin_Size)
            self.mutate_dataset("PMT_counts_y", tracker2, self.count / self.Bin_Size)

                tracker2 += 1

            tracker1 += 1

        # DDS0 Doppler cooler "off"
        self.urukul0_ch0.sw.off()