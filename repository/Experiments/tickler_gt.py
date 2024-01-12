from artiq.experiment import *
import numpy as np
from ndscan import *
import time

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

        self.setattr_device("ttl0") # PMT counter received signal to DIO
        self.setattr_device("ttl4") # output trigger to sync with tickle time
        self.setattr_device("urukul0_cpld") # What for?

        # EnumerationValue specifies an argument that can take a string value among a set of string values

        self.setattr_argument("frequency", NumberValue(default=37.097 * MHz, unit="MHz", ndecimals=6), group='channel0')
        self.setattr_argument("amplitude", NumberValue(default=1, min=0, max=1, ndecimals=6), group='channel0')
        self.setattr_argument("attenuation", NumberValue(default=0, unit="dB", min=0, max=10), group='channel0')

        self.setattr_argument("amplitude1", NumberValue(default=0.5, min=0, max=0.8, ndecimals=6), group='channel1')

        self.setattr_argument("cooling_time", NumberValue(default=10*us, ndecimals=4, unit="us"))
        self.setattr_argument("tickle_time", NumberValue(default=1*ms, ndecimals=4, unit="ms"))
        self.setattr_argument("num_exp", NumberValue(default=10, ndecimals=0, step=1))

        # atributes for frequency scanning
        self.setattr_argument("min_freq", NumberValue(default=1*MHz, unit="MHz", step=0.1, ndecimals=3))
        self.setattr_argument("max_freq", NumberValue(default=10*MHz, unit="MHz", step=0.1, ndecimals=3))
        self.setattr_argument("num_freq_pts", NumberValue(default=10, unit=None, scale=1, step=1, ndecimals=0, type='int'))

        # for the creation of applets (plotting of results)
        self.setattr_device("ccb")

    def prepare(self):

        # broadcast: the data is sent in real-time to the master, which dispatches it.
        # archive: the data is saved into the local storage of the current run (archived as a HDF5 file).
        # Creates frequency range
        self.freq_range=np.linspace(self.min_freq, self.max_freq, self.num_freq_pts)

        # sets freq_range as a dataset
        self.set_dataset("freq_range",  self.freq_range, broadcast=True, archive=True)
        # setts datasets for plotting
        self.set_dataset("Tickler_counts_freq", np.full(self.num_freq_pts, float(np.nan)), broadcast=True, archive=True)
        self.set_dataset("Tickler_counts_y", np.full(self.num_freq_pts, float(np.nan)), broadcast=True, archive=True)

        # creates applet to plot the results
        command = "${artiq_applet}plot_xy Tickler_counts_y --x Tickler_counts_freq"
        self.ccb.issue("create_applet", "Tickler", command)


    @kernel # following method is run in kernel
    def krun(self):
        self.core.reset()
        delay(500 * us)
        self.urukul0_ch0.cpld.init()
        self.urukul0_cpld.init() # what is the purpose of this?
        delay(500 * us)

        # DDS0 Doppler cooler "on"; we want it to run continuously through the run
        self.urukul0_ch0.set(frequency=self.frequency, amplitude=self.amplitude, phase_mode=2)
        self.urukul0_ch0.sw.on()

        # scans through frequencies
        tracker1 = 0
        while (tracker1 < len(self.freq_range)):
            # set tickler frequency
            self.urukul0_ch1.set(frequency=self.freq_range[tracker1], amplitude=self.amplitude1, phase_mode=2)

            # runs num_exp experiments with the same tickle frequency
            tracker2 = 0
            counts = 0 # collects total counts over num_exp experiments
            while (tracker2 < self.num_exp):
                delay(self.cooling_time)  # cooling time
                self.ttl4.on() # turn on trigger signal from ttl4
                delay(-100*ns) # to offset internal delays; the two signals start at the same time
                self.urukul0_ch1.sw.on() # turn on tickler
                countstime = self.ttl0.gate_rising(self.tickle_time)
                # turn off tickler, false signal
                self.urukul0_ch1.sw.off()
                self.ttl4.off()
                delay(50*us) # final delay to prevent underflow during experiment. Delay between shots should not cause problems esp since dds is in phase tracking mode.

                counts += self.ttl0.count(countstime) # add to total counts
                tracker2 += 1 # advance freq_range counter by 1

            self.mutate_dataset("Tickler_counts_freq", tracker1, self.freq_range[tracker1])

            # constant tickle time
            self.mutate_dataset("Tickler_counts_y", tracker1, (counts / self.num_exp / self.tickle_time)) # average counts per second

            tracker1 += 1

        # DDS0 Doppler cooler "off"
        # self.urukul0_ch0.sw.off()

    def run(self):
        self.krun()
