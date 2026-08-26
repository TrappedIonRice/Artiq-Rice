from artiq.experiment import *

class ExpConfigAOMsOn(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")
        self.setattr_device("urukul0_ch1") # Doppler AOM

        self.setattr_argument("u0ch1_Doppler", BooleanValue(default=False), tooltip="Doppler")
        # self.setattr_argument("DopplerAmp",NumberValue(default=0.2, min=0, max=0.6, ndecimals=3))

    def prepare(self):
        # self.loadingDopplerAmp = self.get_dataset("Loading.DopplerAmp")
        # self.experimentDopplerAmp = self.get_dataset("Experiment_config.DopplerAmp")
        self.DopplerFrequency = self.get_dataset("Doppler.Frequency")
        self.DopplerAtt=self.get_dataset("Doppler.Attenuation")
        self.DopplerAmp = self.get_dataset("Experiment_config.DopplerAmp")

    @kernel
    def turn_on_nonRFDDS(self):
        self.urukul0_ch1.init()
        self.urukul0_ch1.set(frequency=self.DopplerFrequency, amplitude= self.DopplerAmp)
        self.urukul0_ch1.set_att(self.DopplerAtt * dB)
        if self.u0ch1_Doppler == True:
            self.urukul0_ch1.sw.on()
        else:
            self.urukul0_ch1.set_att(30 * dB)
            self.urukul0_ch1.sw.off()

        delay(1 * ms)

    @kernel
    def activateUrukul(self):
        self.core.reset()
        delay(1 * ms)
        self.turn_on_nonRFDDS()

    @rpc(flags={"async"})
    def check_termination(self):
        try:
            if self.scheduler.check_pause():
                self.core.comm.close()
                self.scheduler.pause()
        except TerminationRequested:
            print("Terminated gracefully")
            return

    def run(self):
        self.activateUrukul()







