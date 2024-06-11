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




        # #channel dictionary (Modify assignments here) unfortunately dictionaries dont work well at the kernel level
        # self.chdict={0:[self.Amp435,self.Frequency435],1:[self.DopplerAmp,self.DopplerFrequency],2:[self.Amp935,self.Frequency935],3:[self.TicklingAmp,self.TicklingFrequency]}

        # self.setattr_device("scheduler")
        self.lowerlim=0.0001
        self.upperlim = 0.14
        self.dataReprate= 100

        self.setattr_argument("u0ch0_435_1", BooleanValue(default=False), tooltip="435_1")
        self.setattr_argument("u1ch0_435_2", BooleanValue(default=False), tooltip="435_2")
        self.setattr_argument("u0ch1_Doppler", BooleanValue(default=False), tooltip="Doppler")
        self.setattr_argument("u0ch2_935", BooleanValue(default=False), tooltip="935")
        self.setattr_argument("u0ch3_options", EnumerationValue(["Detection","Tickler"]), group="ch3")
        self.setattr_argument("u0ch3_Detection_or_Tickler", BooleanValue(default=False), tooltip="Detection or Tickler", group="ch3")
        self.setattr_argument("u1ch1_OP", BooleanValue(default=False), tooltip="OP")
        self.setattr_argument("u1ch2_MW", BooleanValue(default=False), tooltip="MW")




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
            self.urukul0_ch0.sw.off()

        self.urukul1_ch0.init()
        self.urukul1_ch0.set(frequency=self.Frequency435_2, amplitude=self.Amp435_2)
        self.urukul1_ch0.set_att(self.Att435_2 * dB)
        if self.u1ch0_435_2 == True:
            self.urukul1_ch0.sw.on()
        else:
            self.urukul1_ch0.sw.off()
        


        self.urukul0_ch1.init()
        self.urukul0_ch1.set(frequency=self.DopplerFrequency, amplitude= self.DopplerAmp)
        self.urukul0_ch1.set_att(self.DopplerAtt * dB)
        if self.u0ch1_Doppler == True:
            self.urukul0_ch1.sw.on()
        else:
            self.urukul0_ch1.sw.off()

        self.urukul0_ch2.init()
        self.urukul0_ch2.set(frequency= self.Frequency935, amplitude= self.Amp935)
        self.urukul0_ch2.set_att(self.Att935 * dB)
        if self.u0ch2_935 == True:
            self.urukul0_ch2.sw.on()
        else:
            self.urukul0_ch2.sw.off()

        self.urukul0_ch3.init()

        if self.u0ch3_options=="Tickler":
            self.urukul0_ch3.init()
            self.urukul0_ch3.set(frequency=self.TicklingFrequency, amplitude=self.TicklingAmp)
            self.urukul0_ch3.set_att(self.TicklingAtt * dB)
            if self.u0ch3_Detection_or_Tickler == True:
                self.urukul0_ch3.sw.on()
            else:
                self.urukul0_ch3.sw.off()
            delay(1 * ms)
        elif self.u0ch3_options=="Detection":

            self.urukul0_ch3.set(frequency= self.DetectionFrequency, amplitude=self.DetectionAmp)
            self.urukul0_ch3.set_att(self.DetectionAtt * dB)
            if self.u0ch3_Detection_or_Tickler == True:
                self.urukul0_ch3.sw.on()
            else:
                self.urukul0_ch3.sw.off()
            delay(1*ms)

        self.urukul1_ch1.init()
        self.urukul1_ch1.set(frequency=self.OPFrequency, amplitude=self.OPAmp)
        self.urukul1_ch1.set_att(self.OPAtt * dB)
        if self.u1ch1_OP == True:
            self.urukul1_ch1.sw.on()
        else:
            self.urukul1_ch1.sw.off()

        self.urukul1_ch2.init()
        self.urukul1_ch2.set(frequency=self.MWFrequency, amplitude=self.MWAmp)
        self.urukul1_ch2.set_att(self.MWAtt * dB)
        if self.u1ch2_MW == True:
            self.urukul1_ch2.sw.on()
        else:
            self.urukul1_ch2.sw.off()


    @kernel
    def activateUrukul(self):

        # sequence of commands is very important to hold ions
        self.core.reset()
        #self.urukul0_cpld.init()
        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        self.urukul1_ch0.cpld.init()
        self.urukul1_ch0.init()

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







