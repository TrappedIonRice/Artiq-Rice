from ndscan.experiment import *
from math import sin, pi
import oitg.fitting
import time


# This program will set urukul frequency and plot the sinusoid within artiq

class setUrukul(Fragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        self.setattr_device("urukul0_ch0")
        self.setattr_result("stat")

    @kernel
    def ON(self, amplitude, frequency, att, data):
        print("-----------------")

        self.core.reset()
        delay(10 * ms)
        self.urukul0_cpld.init()
        delay(10 * ms)

        self.urukul0_ch0.init()
        delay(10 * ms)

        freq = frequency * MHz
        amp = amplitude
        attenuation = att

        self.urukul0_ch0.set_att(attenuation)
        self.urukul0_ch0.sw.on()
        delay(10 * ms)

        self.urukul0_ch0.set(freq, amplitude=amp)
        print(data)

    @kernel
    def OFF(self):
        self.core.reset()
        delay(500 * us)
        self.urukul0_cpld.init()
        delay(500 * us)
        self.urukul0_ch0.init()
        delay(500 * us)
        self.urukul0_ch0.set(frequency = 0 * MHz)
        delay(500 * us)
        self.stat.push(0)
        print("OFF")

class scanUrukul(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("setUrukul", setUrukul)
        self.setattr_param("on_off", IntParam, "TYPE 1 FOR ON, 0 FOR OFF", 0)
        self.setattr_param("freq", FloatParam, "FREQUENCY", 0.0)
        self.setattr_param("amp", FloatParam, "AMPLITUDE", 0.0)
        self.setattr_param("att", FloatParam, "ATTENUATION", 0.0)
        self.setattr_param("times", IntParam, "NUMBER OF POINTS", 0)
        #retrieve data from datasets, set to urukul and ttl
        #self.setattr_param("on_off", StringParam, "TYPE : ON/OFF")
        print("BUILT FRAG")

    def run_once(self):
        if self.on_off.get() == 1:
            print("ABOUT TO EXECUTE 'ON'")

            data_lst = []
            count = 0.0
            for i in range(self.times.get()):
                num = self.amp.get()*((sin(self.freq.get()*count)))
                data_lst.append(num)
                count += pi / 2.0
            if len(data_lst) == 0:
                data_lst.append(0.0)
            #want to call on function for certain amount of time
            self.setUrukul.ON(self.amp.get(), self.freq.get(), self.att.get(), data_lst)
            print("EXECUTED 'ON'")
        else:
            print(self.on_off.get())
            print("ABOUT TO EXECUTE 'OFF'")
            self.setUrukul.OFF()
            print("EXECUTED 'OFF'")
        print("EXPERIMENT DONE")

UrukulPracticeScan = make_fragment_scan_exp(scanUrukul)

