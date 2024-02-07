
from artiq.experiment import *
import numpy as np

class Loading(EnvExperiment):

    def build(self):
        # Devices
        self.setattr_device("core")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_cpld")

        self.rf_frequency = self.get_dataset("Loading.rf_frequency")
        self.all_y = self.get_dataset("Loading.all_y")
        self.all_z = self.get_dataset("Loading.all_z")
        self.attenuation = self.get_dataset("Loading.attenuation")
        self.endcap_avg = self.get_dataset("Loading.endcap_avg")
        self.target_amplitude = self.get_dataset("Loading.target_amplitude")
        self.num_points = self.get_dataset("Loading.num_points")
        self.ramp_rate = self.get_dataset("Loading.ramp_rate")
        self.time_step = self.get_dataset("Loading.time_step")
        self.trap_mid_cent_twist = self.get_dataset("Loading.trap_mid_cent_twist")
        self.wait_time = self.get_dataset("Loading.wait_time")
        self.amplitude = self.get_dataset("Loading.urukul_ch0_RF_amp")

        # for the creation of applets (plotting of results)
        self.setattr_device("ccb")

    def prepare(self):
        self.set_dataset("Amplitude", np.full(int(self.num_points), float(np.nan)), broadcast=True, archive=False)
        self.set_dataset("Time", np.full(int(self.num_points), float(np.nan)), broadcast=True, archive=False)
        self.int_points = int(self.num_points)
        command = "${artiq_applet}plot_xy Amplitude --x Time --fit Amplitude"
        self.ccb.issue("create_applet", "Loading Amplitude Ramp", command)

    @kernel
    def initialize_urukul(self):
        self.core.reset()
        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        delay(1 * ms)


    @kernel
    def turn_on(self):
        self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=self.amplitude)
        self.urukul0_ch0.set_att(0 * dB)
        self.urukul0_ch0.sw.on()
        delay(1 * ms)

    @kernel
    def turn_off(self):
        self.urukul0_ch0.sw.off()
        delay(1 * ms)

    @kernel
    def krun(self, loading_amplitude):

        amp = self.amplitude
        delay(2 * ms)
        idx = 0
        time = 0.0
        if loading_amplitude > amp:
            while amp < loading_amplitude:

                ampplus = (amp + self.ramp_rate)
                self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=ampplus)
                delay(2 * ms)
                self.set_dataset("UrukulCh0_RFamp", ampplus, broadcast=True, persist=True)
                # for multiple points
                if (idx % self.dataReprate == 0):
                    self.changeDataset(ampplus, time, self.dataReprate, idx)
                amp = ampplus
                delay(self.time_step)
                time += (self.time_step)  # * 1000
                idx += 1
                delay(2 * ms)

        else:

            while amp > self.target_amplitude:

                ampminus = (amp - self.ramp_rate)
                self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=ampminus)
                delay(2 * ms)
                self.set_dataset("UrukulCh0_RFamp", ampminus, broadcast=True, persist=True)
                if (idx % self.dataReprate == 0):
                    self.changeDataset(ampminus, time, self.dataReprate, idx)
                amp = ampminus
                delay(self.time_step)
                time += self.time_step  # * 1000
                idx += 1
                delay(2 * ms)

        print("Ramp complete")
        delay(4 * ms)
        self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=self.target_amplitude)
        delay(1 * ms)
        self.set_dataset("UrukulCh0_RFamp", self.target_amplitude, broadcast=True, persist=True)
        delay(1 * ms)


    @kernel
    def changeDataset(self, amp, tm, mod, idx):
        self.mutate_dataset("Amplitude", idx // mod, amp)
        self.mutate_dataset("Time", idx // mod, tm)


    def run(self):
        self.activateUrukul()









