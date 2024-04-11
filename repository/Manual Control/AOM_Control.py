from artiq.experiment import *
import numpy as np
import time as timelib

class AmplitudeRamp(EnvExperiment):
    def build(self):
        # Please make sure to enter the right units.
        self.setattr_device("core")
        #self.setattr_device("ttl0")
        self.setattr_device("urukul0_cpld")
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("urukul0_ch3")

        self.DopplerAmp=self.get_dataset("Doppler.Amp")
        self.DopplerFrequency=self.get_dataset("Doppler.Frequency")
        self.DetectionAmp=self.get_dataset("Detection.Amp")
        self.DetectionFrequency=self.get_dataset("Detection.Frequency")
        self.OPAmp=self.get_dataset("OP.Amp")
        self.OPFrequency=self.get_dataset("OP.Frequency")
        self.435Amp = self.get_dataset("435.Amp")
        self.435Frequency = self.get_dataset("435.Frequency")
        self.935Amp = self.get_dataset("935.Amp")
        self.935Frequency = self.get_dataset("935.Frequency")



        # self.setattr_device("scheduler")
        self.lowerlim=0.0001
        self.upperlim = 0.14
        self.dataReprate= 100

        self.setattr_argument("ch0", BooleanValue(default=False), tooltip="435")
        self.setattr_argument("ch1", BooleanValue(default=False), tooltip="Doppler")
        self.setattr_argument("ch2", BooleanValue(default=False), tooltip="935")
        self.setattr_argument("ch3", BooleanValue(default=False), tooltip="Tickler")

       # self.target_amplitude=round(self.target_amplitude

    def prepare(self):
        pass


    @kernel
    def initialize_urukul(self):
        self.core.reset()
        #self.urukul0_cpld.init()
        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()

        delay(1 * ms)

    @kernel
    def turn_on_nonRFDDS(self):

        self.urukul0_ch0.init()
        self.urukul0_ch0.set(frequency=self.435Frequency, amplitude=self.435Amp)
        self.urukul0_ch0.set_att(0 * dB)
        if self.ch0 == True:
            self.urukul0_ch0.sw.on()
        else:
            self.urukul0_ch0.sw.off()


        self.urukul0_ch1.init()
        self.urukul0_ch1.set(frequency=self.DopplerFrequency, amplitude=self.DopplerAmp)
        self.urukul0_ch1.set_att(0 * dB)
        if self.ch1 == True:
            self.urukul0_ch1.sw.on()
        else:
            self.urukul0_ch1.sw.off()

        self.urukul0_ch2.init()
        self.urukul0_ch2.set(frequency=self.935Frequency, amplitude=self.935Amp)
        self.urukul0_ch2.set_att(0 * dB)
        if self.ch2 == True:
            self.urukul0_ch2.sw.on()
        else:
            self.urukul0_ch2.sw.off()

        self.urukul0_ch3.init()
        self.urukul0_ch3.set(frequency=self.TicklingFrequency, amplitude=self.TicklingAmp)
        self.urukul0_ch3.set_att(0 * dB)
        if self.ch3 == True:
            self.urukul0_ch3.sw.on()
        else:
            self.urukul0_ch3.sw.off()
        delay(1*ms)


    @kernel
    def activateUrukul(self):

        # sequence of commands is very important to hold ions
        self.core.reset()
        # self.urukul0_cpld.init()
        self.urukul0_ch0.cpld.init()
        #self.zotino0.init()
        delay(1*ms)
        self.turn_on_nonRFDDS()


    # @rpc(flags={"async"})
    # def check_termination(self):
    #     try:
    #         if self.scheduler.check_pause():
    #             self.core.comm.close()
    #             self.scheduler.pause()
    #     except TerminationRequested:
    #         print("Terminated gracefully")
    #         return

    #@kernel
    def run(self):
        self.activateUrukul()
        #print("Ramp complete")

       # self.krun()







