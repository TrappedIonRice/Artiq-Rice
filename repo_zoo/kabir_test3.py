from artiq.experiment import *
from artiq.coredevice.ad9910 import RAM_MODE_CONT_RAMPUP
from artiq.coredevice.urukul import *
import numpy as np

class Test_ttl_freq_amp(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl4")
        self.setattr_device("urukul0_cpld")
        self.setattr_device("urukul0_ch0")
        #self.amplitude = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        #self.pulse_length = 6.0 * us
    @kernel
    def run(self):
        self.core.reset()
        self.urukul0_cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch0.cfg_sw(True)
        self.urukul0_ch0.set_att(3.*dB)
        self.ttl4.output()
        #self.ttl4.on()
        self.core.break_realtime()
        x_t1 = 0.1
        #x_t1 = int(input("Set t1:"))
        x_t1_amp = 0.3
        x_t2 = 0
        x_t2_amp = 0.0
        x_t3 = 0.2
        x_t3_amp = 0.6
        x_time1 = 1
        x_time2 = 2
        for i in range(1000):
            #delay(2*ms)	
            with parallel:
            	self.ttl4.on() 
            	self.urukul0_ch0.set(x_t1*MHz, amplitude = x_t1_amp, ref_time_mu=0) #adjusts frequency + amplitude
            delay(x_time2*ms)
            with parallel:
            	self.ttl4.off() 
            	self.urukul0_ch0.set(x_t2*MHz, amplitude = x_t2_amp, ref_time_mu=0)
            delay(x_time2*ms)
            with parallel:
            	self.ttl4.on() 
            	self.urukul0_ch0.set(x_t3*MHz, amplitude = x_t3_amp, ref_time_mu=0)
            delay(x_time2*ms)
            with parallel:
            	self.ttl4.off() 
            	self.urukul0_ch0.set(x_t2*MHz, amplitude = x_t2_amp, ref_time_mu=0)
            delay(x_time2*ms)
            #self.ttl4.set(0*MHz, amplitude=0)
            #delay(2*ms)
            #self.ttl4.set(frequency = 2*MHz, amplitude = 2.0)
            #delay(2*ms)
            #self.ttl4.set(frequency=0 * MHz, amplitude=0)
            #delay(2*ms)
   from artiq.applets.simple import SimpleApplet

class MyApplet(SimpleApplet):
    def build(self):
        # Code to create the UI elements goes here
        pass

    def run(self):
        # Code to run the applet goes here
        pass

if __name__ == "__main__":
    applet = MyApplet()
    applet.run()

