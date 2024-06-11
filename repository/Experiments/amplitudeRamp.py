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


        self.setattr_argument("activateRF", BooleanValue(default=True), tooltip="Urukul0Ch0")
        # self.setattr_device("scheduler")
        self.lowerlim=0.0001
        self.upperlim = 0.14
        self.dataReprate= 100
        self.setattr_argument("frequency", NumberValue(default=25.701*MHz, min = 25 * MHz, max = 27 * MHz, unit="MHz", ndecimals=6), tooltip="Urukul0Ch0")
        self.setattr_argument("ramp_rate", NumberValue(default=2e-5, ndecimals=6), tooltip="Urukul0Ch0")
        self.setattr_argument("target_amplitude", NumberValue(default=0, min=self.lowerlim, max=self.upperlim, ndecimals=6), tooltip="Urukul0Ch0")
        self.setattr_argument("attenuation", NumberValue(default=0, unit="dB", min=0, max=10), tooltip="Urukul0Ch0")
        self.setattr_argument("time_step", NumberValue(default=10 * ms, unit="ms", min=0*ms,ndecimals=6))
        self.setattr_argument("wait_time", NumberValue(default=1*s, unit="s", min=0 * s, ndecimals=6))
        self.setattr_argument("num_points", NumberValue(default = 1000))
        self.amplitude=self.get_dataset("UrukulCh0_RFamp")
        self.setattr_device("scheduler")
        self.setattr_device("ccb")  # needed to make plots displaying the counts

        self.setattr_argument("ch1", BooleanValue(default=False), tooltip="Doppler")
        self.setattr_argument("ch2", BooleanValue(default=False), tooltip="Detection")
        self.setattr_argument("ch3", BooleanValue(default=False), tooltip="OP")

       # self.target_amplitude=round(self.target_amplitude

    def prepare(self):
        self.set_dataset("Amplitude", np.full(int(self.num_points), float(np.nan)), broadcast=True, archive=False)
        #self.set_dataset("Time", np.linspace(0.0,1.1,int(self.num_points)), broadcast=True, archive=True)
        self.set_dataset("Time", np.full(int(self.num_points), float(np.nan)), broadcast=True, archive=False)
        self.int_points = int(self.num_points)
        command = "${artiq_applet}plot_xy Amplitude --x Time --fit Amplitude"
        self.ccb.issue("create_applet", "Amplitude Ramp", command)


    @kernel
    def initialize_urukul(self):
        self.core.reset()
        #self.urukul0_cpld.init()
        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        #self.urukul0_ch1.init()
        #self.urukul0_ch2.init()
        #self.urukul0_ch3.init()
        delay(1 * ms)

    @kernel
    def turn_on_nonRFDDS(self):
        self.urukul0_ch1.init()
        self.urukul0_ch1.set(frequency=self.DopplerFrequency, amplitude=self.DopplerAmp)
        self.urukul0_ch1.set_att(0 * dB)
        if self.ch1 == True:
            self.urukul0_ch1.sw.on()
        else:
            self.urukul0_ch1.sw.off()

        self.urukul0_ch2.init()
        self.urukul0_ch2.set(frequency=self.DetectionFrequency, amplitude=self.DetectionAmp)
        self.urukul0_ch2.set_att(0 * dB)
        if self.ch2 == True:
            self.urukul0_ch2.sw.on()
        else:
            self.urukul0_ch2.sw.off()

        self.urukul0_ch3.init()
        self.urukul0_ch3.set(frequency=self.OPFrequency, amplitude=self.OPAmp)
        self.urukul0_ch3.set_att(0 * dB)
        if self.ch3 == True:
            self.urukul0_ch3.sw.on()
        else:
            self.urukul0_ch3.sw.off()
        delay(1*ms)


    @kernel
    def turn_on(self):
        self.urukul0_ch0.set(frequency=self.frequency, amplitude=self.amplitude)
        self.urukul0_ch0.set_att(0*dB)
        self.urukul0_ch0.sw.on()

        delay(1*ms)


    @kernel
    def turn_off(self):
        self.urukul0_ch0.sw.off()
        delay(1 * ms)

    @kernel
    def activateUrukul(self):

        # sequence of commands is very important to hold ions
        self.core.reset()
        # self.urukul0_cpld.init()
        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        #self.zotino0.init()
        delay(1*ms)
        #delay(10 * ms)
        #self.initialize_urukul()

        if (self.activateRF):
            self.urukul0_ch0.set(frequency=self.frequency, amplitude=self.amplitude)
            self.urukul0_ch0.set_att(0 * dB)
            self.urukul0_ch0.sw.on()
           # self.zotino0.write_dac(12, self.zotino_amplitude)
           # self.zotino0.load()
            delay(0.1 * ms)

            print("Urukul0 ch0 on")
            print(self.amplitude)
            delay(1*ms)

            self.turn_on_nonRFDDS()
            # self.krun(self.target_amplitude)
            #self.krun(self.zotino_target)
            #self.zotino_amplitude = self.get_dataset("ZotinoCh12_RFamp")


        else:
            #self.target_amplitude=self.lowerlim # always will ramp to lower value before turning off
            self.turn_on_nonRFDDS()
            #self.krun(self.lowerlim)
            self.turn_off()

           # self.zotino0.write_dac(12, 0.0)
           # self.zotino0.load()
            delay(0.1 * ms)

            delay(1*ms)
            print("Urukul0 ch0 off")
        # self.urukul0_ch1.init()
        # self.urukul0_ch2.init()
        # self.urukul0_ch3.init()



    @kernel
    def krun(self,targetamp):
        self.core.reset()
        #self.ttl0.input()
        self.urukul0_cpld.init() #new
        self.urukul0_ch0.cpld.init()
        self.urukul0_ch0.init()
        amp = self.urukul0_ch0.get_amplitude()
        delay(1 * ms)
        self.urukul0_ch0.set(frequency=self.frequency,amplitude=self.amplitude)
        self.urukul0_ch0.sw.on()
        print(self.amplitude)
        delay(2*ms)


        self.urukul0_ch0.sw.on()
        amp=self.zotino_amplitude
        delay(2*ms)



        # sign = (self.target_amplitude - self.urukul0_ch0.get_amplitude()) / np.abs(
        #     self.target_amplitude - self.urukul0_ch0.get_amplitude())
        # self.ramp = np.array([self.urukul0_ch0.get_amplitude() + i * self.ramp_rate * sign for i in range(
        #     int(np.abs(self.urukul0_ch0.get_ampltiude() - self.target_amplitude) / self.ramp_rate))])
        # self.ramp[-1] = self.target_amplitude

        #delay(10000 * ms)

        #self.initialize_urukul()
        #self.urukul0_ch0.sw.off()
        idx = 0
        time = 0.0
        if targetamp > amp:
            #delay(10*ms)
            while amp < targetamp:
                #delay(10 * ms)
                # try:
                #     if self.scheduler.check_pause():
                #         self.core.comm.close()
                #         self.scheduler.pause()
                # except TerminationRequested:
                #     print("Terminated gracefully")
                #     return
            #    self.check_termination()

                ampplus=(amp + self.ramp_rate)
                # self.urukul0_ch0.set(frequency=self.frequency,amplitude=ampplus)
                delay(2*ms)

                #self.zotino0.write_dac(12, ampplus)
                #self.zotino0.load()
                delay(0.1 * ms)

                # self.set_dataset("UrukulCh0_RFamp", ampplus, broadcast=True, persist=True)
                self.set_dataset("ZotinoCh12_RFamp", ampplus, broadcast=True, persist=True)
                #print(amp)
                #for multiple points
                if (idx % self.dataReprate == 0):
                    self.changeDataset(ampplus, time,self.dataReprate,idx)
                # for testing a few points
                # self.mutate_dataset("Amplitude", idx, ampplus)
                # self.mutate_dataset("Time", idx, time)


                # for i in range(self.int_points):
                #     self.mutate_dataset("Amplitude", i, ampplus)
                #     self.mutate_dataset("Time", i, time + i)
                amp=ampplus
                delay(self.time_step)
                time += (self.time_step)# * 1000
                idx +=1
                delay(2 * ms)

        else:

            while amp > targetamp:
                # try:
                #     if self.scheduler.check_pause():
                #         self.core.comm.close()
                #         self.scheduler.pause()
                # except TerminationRequested:
                #     print("Terminated gracefully")
                #     return
             #   self.check_termination()
                ampminus=(amp - self.ramp_rate)
                # self.urukul0_ch0.set(frequency=self.frequency, amplitude=ampminus)
                delay(2 * ms)

                #self.zotino0.write_dac(12, ampminus)
                #self.zotino0.load()
                delay(0.1 * ms)
                # self.set_dataset("UrukulCh0_RFamp", ampminus, broadcast=True, persist=True)
                self.set_dataset("ZotinoCh12_RFamp", ampminus, broadcast=True, persist=True)
                #print(amp)
                # for multiple points
                if(idx % self.dataReprate == 0):
                    self.changeDataset(ampminus, time, self.dataReprate,idx)
                    # self.mutate_dataset("Amplitude", idx//5, ampminus)
                    # self.mutate_dataset("Time", idx//5, time)
                # for testing a few points
                # self.mutate_dataset("Amplitude", idx, ampminus)
                # self.mutate_dataset("Time", idx, time)
                amp = ampminus
                delay(self.time_step)
                time += self.time_step# * 1000
                idx += 1
                delay(2 * ms)
                # self.urukul0_ch0.sw.off()
                # delay(1*ms)
        print("Ramp complete")
        delay(4*ms)
        # self.urukul0_ch0.set(frequency=self.frequency,amplitude=targetamp)
        delay(1 * ms)

        #self.zotino0.write_dac(12, targetamp)
        #self.zotino0.load()
        delay(0.1 * ms)

        self.set_dataset("ZotinoCh12_RFamp",targetamp, broadcast=True, persist=True )
        delay(1 * ms)
        # Now setting the loop to wait.

        # time0=time+self.wait_time
        # idx=idx//self.dataReprate
        # A=0
        # while(time<time0):
        #     timelib.sleep(self.time_step*self.dataReprate)
        #     #if (idx % self.dataReprate == 0):
        #     #delay(self.time_step*self.dataReprate)
        #     #delay(2 *self.wait_time* ms) #  works only if this delay scales with the wait time
        #     #print(time)
        #     #A=self.ttl0.gate_rising(self.time_step)
        #     #delay(2*ms)
        #     #float(self.ttl0.count(A))
        #     self.changeDataset(self.target_amplitude, time, 1, idx)
        #     idx += 1
        #     time += self.time_step*self.dataReprate
        #     #delay(10*ms)10*ms

        #print("End of wait time")

        # Now also setting the loop to ramp back to previous value
        # better to complete ramp up down in a separate function


    #@rpc(flags={"async"})
    @kernel
    def changeDataset(self,amp,tm,mod,idx):
        self.mutate_dataset("Amplitude", idx // mod, amp)
        self.mutate_dataset("Time", idx // mod, tm)

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







