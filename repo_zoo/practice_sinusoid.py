from ndscan.experiment import *
from math import sin, pi
import time

class Readout(Fragment):
    def build_fragment(self):
        self.setattr_param("freq", FloatParam, "Frequency", 1.0)
        self.setattr_param("num", IntParam, "Number", 10)
        self.setattr_result("val")
    def assign_sin_val(self):
        count = 0.0
        for i in range(0, self.num.get()):
            self.val.push(sin(self.freq.get()*count))
            count+= pi/2
            time.sleep(0.05)

class sinPrac(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("readout", Readout)
    def run_once(self):
        self.readout.assign_sin_val()


PracticeSinScan = make_fragment_scan_exp(sinPrac)