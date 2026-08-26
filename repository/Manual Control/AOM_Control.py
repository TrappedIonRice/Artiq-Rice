from artiq.experiment import *
import numpy as np
import time as timelib

class AOMControl(EnvExperiment):
    def build(self):
        # Please make sure to enter the right units.
        self.setattr_device("core")
        #self.setattr_device("ttl0")
        self.setattr_device("urukul0_cpld")
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("urukul0_ch3")

        self.setattr_device("urukul1_cpld")
        self.setattr_device("urukul1_ch0")
        self.setattr_device("urukul1_ch1")
        self.setattr_device("urukul1_ch2")
        self.setattr_device("urukul1_ch3")

        self.setattr_device("urukul2_cpld")
        self.setattr_device("urukul2_ch0")
        self.setattr_device("urukul2_ch1")
        self.setattr_device("urukul2_ch2") # OP, not RR lock
        self.setattr_device("urukul2_ch3") # 369 ULE AOM

        self.setattr_device("ttl6") # new Raman2 switch
        self.setattr_device("ttl7")  # 26/07/13 gt; DET switch

        self.setattr_device("zotino0") # 26/07/13 gt; z0ch26 GOP switch

        # #channel dictionary (Modify assignments here) unfortunately dictionaries dont work well at the kernel level
        # self.chdict={0:[self.Amp435,self.Frequency435],1:[self.DopplerAmp,self.DopplerFrequency],2:[self.Amp935,self.Frequency935],3:[self.TicklingAmp,self.TicklingFrequency]}

        # self.setattr_device("scheduler")
        self.lowerlim=0.0001
        self.upperlim = 0.14
        self.dataReprate= 100

        self.setattr_argument("u0ch0_435_1", BooleanValue(default=False), tooltip="435_1/411")
        self.setattr_argument("u1ch0_435_2", BooleanValue(default=False), tooltip="435_2/976")
        self.setattr_argument("u0ch1_Doppler", BooleanValue(default=False), tooltip="Doppler")
        self.setattr_argument("u0ch2_935", BooleanValue(default=False), tooltip="935/760")
        self.setattr_argument("u0ch3_options", EnumerationValue(["Detection","Tickler"]), group="u0ch3")
        self.setattr_argument("u0ch3_Detection_or_Tickler", BooleanValue(default=False), tooltip="Detection or Tickler", group="u0ch3")
        self.setattr_argument("u2ch2_OP", BooleanValue(default=False), tooltip="OP")
        self.setattr_argument("u1ch1_LOP", BooleanValue(default=False), tooltip="LOP")
        self.setattr_argument("u1ch2_MW", BooleanValue(default=False), tooltip="MW")
        self.setattr_argument("u1ch3_355_RamanB2", BooleanValue(default=False), tooltip="355_RamanB2")
        self.setattr_argument("u2ch0_355_Raman1", BooleanValue(default=False), tooltip="355_Raman1")
        self.setattr_argument("u2ch1_355_RamanA16", BooleanValue(default=False), tooltip="355_RamanA16")
        self.setattr_argument("ttl6_355_Raman2", BooleanValue(default=False), tooltip="355_Raman2")
        #self.setattr_argument("u2ch3_355_RR_lock", BooleanValue(default=False), tooltip="355_RR_lock")

        self.setattr_argument("u2ch2_RR_lock", BooleanValue(default=True), tooltip="RR_lock")
        self.setattr_argument("u2ch3_369_ULE", BooleanValue(default=True), tooltip="369_ULE")


       # self.target_amplitude=round(self.target_amplitude

    def prepare(self):
        self.DopplerAmp = self.get_dataset("Doppler.Amp")
        self.DopplerFrequency = self.get_dataset("Doppler.Frequency")
        self.DopplerAtt=self.get_dataset("Doppler.Attenuation")


        self.DetectionAmp = self.get_dataset("Detection.Amp")
        self.DetectionFrequency = self.get_dataset("Detection.Frequency")
        self.DetectionAtt=self.get_dataset("Detection.Attenuation")


        self.OPAmp = self.get_dataset("OP.Amp")
        self.OPFrequency = self.get_dataset("OP.Frequency")
        self.OPAtt=self.get_dataset("OP.Attenuation")

        self.LOPAmp = self.get_dataset("LOP.Amp")
        self.LOPFrequency = self.get_dataset("LOP.Frequency")
        self.LOPAtt = self.get_dataset("LOP.Attenuation")

        self.MWAmp = self.get_dataset("MW.Amp")
        self.MWFrequency = self.get_dataset("MW.Frequency")
        self.MWAtt = self.get_dataset("MW.Attenuation")


        self.Amp435_1 = self.get_dataset("435_1.Amp")
        self.Frequency435_1 = self.get_dataset("435_1.Frequency")
        self.Att435_1=self.get_dataset("435_1.Attenuation")

        self.Amp435_2 = self.get_dataset("435_2.Amp")
        self.Frequency435_2 = self.get_dataset("435_2.Frequency")
        self.Att435_2 = self.get_dataset("435_2.Attenuation")


        self.Amp935 = self.get_dataset("935.Amp")
        self.Frequency935 = self.get_dataset("935.Frequency")
        self.Att935=self.get_dataset("935.Attenuation")


        self.TicklingAmp = self.get_dataset("Tickling.Amp")
        self.TicklingFrequency = self.get_dataset("Tickling.Frequency")
        self.TicklingAtt=self.get_dataset("Tickling.Attenuation")

        # self.Protection369Amp = self.get_dataset("369_protection.Amp")
        # self.Protection369Frequency = self.get_dataset("369_protection.Frequency")
        # self.Protection369Att = self.get_dataset("369_protection.Attenuation")

        # self.RrLock355Amp = self.get_dataset("355_RR_lock.Amp")
        # self.RrLock355Frequency = self.get_dataset("355_RR_lock.Frequency")
        # self.RrLock355Att = self.get_dataset("355_RR_lock.Attenuation")

        self.Raman1_355Amp = self.get_dataset("355_Raman1.Amp")
        self.Raman1_355Frequency = self.get_dataset("355_Raman1.Frequency")
        self.Raman1_355Att = self.get_dataset("355_Raman1.Attenuation")

        self.RamanB2_355Amp = self.get_dataset("355_RamanB2.Amp")
        self.RamanB2_355Frequency = self.get_dataset("355_RamanB2.Frequency")
        self.RamanB2_355Att = self.get_dataset("355_RamanB2.Attenuation")

        self.RamanA16_355Amp = self.get_dataset("355_RamanA16.Amp")
        self.RamanA16_355Frequency = self.get_dataset("355_RamanA16.Frequency")
        self.RamanA16_355Att = self.get_dataset("355_RamanA16.Attenuation")

        self.RR_lock_Amp = self.get_dataset("355_RR_lock.Amp")
        self.RR_lock_Frequency = self.get_dataset("355_RR_lock.Frequency")
        self.RR_lock_Att = self.get_dataset("355_RR_lock.Attenuation")

        self.ULE_369_Amp = self.get_dataset("369_ULE.Amp")
        self.ULE_369_Frequency = self.get_dataset("369_ULE.Frequency")
        self.ULE_369_Att = self.get_dataset("369_ULE.Attenuation")

        # self.Raman2_355Amp = self.get_dataset("355_Raman2.Amp")
        # self.Raman2_355Frequency = self.get_dataset("355_Raman2.Frequency")
        # self.Raman2_355Att = self.get_dataset("355_Raman2.Attenuation")


    # @kernel
    # def initialize_urukul(self):
    #     self.core.reset()
    #     #self.urukul0_cpld.init()
    #     self.urukul0_ch0.cpld.init()
    #     self.urukul0_ch0.init()
    #
    #     delay(1 * ms)

    @kernel
    def turn_on_nonRFDDS(self):

        self.urukul0_ch0.init()
        self.urukul0_ch0.set(frequency=self.Frequency435_1,  amplitude=self.Amp435_1)
        self.urukul0_ch0.set_att( self.Att435_1 * dB)
        if self.u0ch0_435_1 == True:
            self.urukul0_ch0.sw.on()
        else:
            self.urukul0_ch0.set_att(30*dB)
            self.urukul0_ch0.sw.off()

        self.urukul1_ch0.init()
        self.urukul1_ch0.set(frequency=self.Frequency435_2, amplitude=self.Amp435_2)
        self.urukul1_ch0.set_att(self.Att435_2 * dB)
        if self.u1ch0_435_2 == True:
            self.urukul1_ch0.sw.on()
        else:
            self.urukul1_ch0.set_att(30 * dB)
            self.urukul1_ch0.sw.off()


        self.urukul0_ch1.init()
        self.urukul0_ch1.set(frequency=self.DopplerFrequency, amplitude= self.DopplerAmp)
        self.urukul0_ch1.set_att(self.DopplerAtt * dB)
        if self.u0ch1_Doppler == True:
            self.urukul0_ch1.sw.on()
        else:
            self.urukul0_ch1.set_att(30 * dB)
            self.urukul0_ch1.sw.off()

        self.urukul0_ch2.init()
        self.urukul0_ch2.set(frequency= self.Frequency935, amplitude= self.Amp935)
        self.urukul0_ch2.set_att(self.Att935 * dB)
        if self.u0ch2_935 == True:
            self.urukul0_ch2.sw.on()
        else:
            self.urukul0_ch2.set_att(30 * dB)
            self.urukul0_ch2.sw.off()

        self.urukul0_ch3.init()
        if self.u0ch3_options=="Tickler":
            self.urukul0_ch3.init()
            self.urukul0_ch3.set(frequency=self.TicklingFrequency, amplitude=self.TicklingAmp)
            self.urukul0_ch3.set_att(self.TicklingAtt * dB)
            if self.u0ch3_Detection_or_Tickler == True:
                self.urukul0_ch3.sw.on()
            else:
                self.urukul0_ch3.set_att(30 * dB)
                self.urukul0_ch3.sw.off()
            delay(1 * ms)
        elif self.u0ch3_options=="Detection":
            self.ttl7.output() # 26/07/13 gt: for DET switch
            self.urukul0_ch3.set(frequency= self.DetectionFrequency, amplitude=self.DetectionAmp)
            self.urukul0_ch3.set_att(self.DetectionAtt * dB)
            if self.u0ch3_Detection_or_Tickler == True:
                self.ttl7.on()
                self.urukul0_ch3.sw.on()
            else:
                self.urukul0_ch3.set_att(30 * dB)
                self.urukul0_ch3.sw.off()
                self.ttl7.off()
            delay(1*ms)

        self.urukul2_ch2.init()
        self.zotino0.init() # for OP switch
        self.urukul2_ch2.set(frequency=self.OPFrequency, amplitude=self.OPAmp)
        self.urukul2_ch2.set_att(self.OPAtt * dB)
        if self.u2ch2_OP == True:
            self.zotino0.write_dac(26, 5.0)
            self.zotino0.load()
            self.urukul2_ch2.sw.on()
        else:
            self.urukul2_ch2.set_att(30 * dB)
            self.urukul2_ch2.sw.off()
            self.zotino0.write_dac(26, 0.0)
            self.zotino0.load()

        self.urukul1_ch1.init()
        self.urukul1_ch1.set(frequency=self.LOPFrequency, amplitude=self.LOPAmp)
        self.urukul1_ch1.set_att(self.LOPAtt * dB)
        if self.u1ch1_LOP == True:
            self.urukul1_ch1.sw.on()
        else:
            self.urukul1_ch1.set_att(30 * dB)
            self.urukul1_ch1.sw.off()

        self.urukul1_ch2.init()
        self.urukul1_ch2.set(frequency=self.MWFrequency, amplitude=self.MWAmp)
        self.urukul1_ch2.set_att(self.MWAtt * dB)
        if self.u1ch2_MW == True:
            self.urukul1_ch2.sw.on()
        else:
            self.urukul1_ch2.set_att(30 * dB)
            self.urukul1_ch2.sw.off()

        self.urukul1_ch3.init()
        self.urukul1_ch3.set(frequency=self.RamanB2_355Frequency, amplitude=self.RamanB2_355Amp)
        self.urukul1_ch3.set_att(self.RamanB2_355Att * dB)
        if self.u1ch3_355_RamanB2 == True:
            self.urukul1_ch3.sw.on()
        else:
            self.urukul1_ch3.set_att(30 * dB)
            self.urukul1_ch3.sw.off()


        self.urukul2_ch0.init()
        self.urukul2_ch0.set(frequency=self.Raman1_355Frequency, amplitude=self.Raman1_355Amp)
        self.urukul2_ch0.set_att(self.Raman1_355Att * dB)
        if self.u2ch0_355_Raman1 == True:
            self.urukul2_ch0.sw.on()
        else:
            self.urukul2_ch0.set_att(30 * dB)
            self.urukul2_ch0.sw.off()

        self.urukul2_ch1.init()
        self.urukul2_ch1.set(frequency=self.RamanA16_355Frequency, amplitude=self.RamanA16_355Amp)
        self.urukul2_ch1.set_att(self.RamanA16_355Att * dB)
        if self.u2ch1_355_RamanA16 == True:
            self.urukul2_ch1.sw.on()
        else:
            self.urukul2_ch1.set_att(30 * dB)
            self.urukul2_ch1.sw.off()

        # # RR lock
        # # self.urukul2_ch2.init()
        # self.urukul2_ch2.set(frequency=self.RR_lock_Frequency, amplitude=self.RR_lock_Amp)
        # self.urukul2_ch2.set_att(self.RR_lock_Att * dB)
        # if self.u2ch2_RR_lock == True:
        #     self.urukul2_ch2.sw.on()
        # else:
        #     self.urukul2_ch2.set_att(30 * dB)
        #     self.urukul2_ch2.sw.off()

        # 369 ULE
        self.urukul2_ch3.set(frequency=self.ULE_369_Frequency, amplitude=self.ULE_369_Amp)
        self.urukul2_ch3.set_att(self.ULE_369_Att * dB)
        if self.u2ch3_369_ULE == True:
            self.urukul2_ch3.sw.on()
        else:
            self.urukul2_ch3.set_att(30 * dB)
            self.urukul2_ch3.sw.off()


        # New Raman2 config with RF switch
        self.ttl6.output()
        if self.ttl6_355_Raman2 == True:
            self.ttl6.on()
        else:
            self.ttl6.off()


        # self.urukul2_ch3.init()
        # self.urukul2_ch3.set(frequency=self.RrLock355Frequency, amplitude=self.RrLock355Amp)
        # self.urukul2_ch3.set_att(self.RrLock355Att * dB)
        # if self.u2ch3_355_RR_lock == True:
        #     self.urukul2_ch3.sw.on()
        # else:
        #     self.urukul2_ch3.set_att(30 * dB)
        #     self.urukul2_ch3.sw.off()

        delay(1 * ms)


    @kernel
    def activateUrukul(self):

        # sequence of commands is very important to hold ions
        self.core.reset()
        #self.urukul0_cpld.init()
        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        self.urukul1_ch0.cpld.init()
        self.urukul1_ch0.init()
        self.urukul1_ch3.cpld.init()
        self.urukul1_ch3.init()
        self.urukul2_ch0.cpld.init()
        self.urukul2_ch0.init()
        self.urukul2_ch1.cpld.init()
        self.urukul2_ch1.init()

        #self.zotino0.init()
        delay(1*ms)
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

    #@kernel
    def run(self):
        self.activateUrukul()
        #print("Ramp complete")

       # self.krun()







