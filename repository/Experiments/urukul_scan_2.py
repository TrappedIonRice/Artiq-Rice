from ndscan.experiment import *
from urukul_scan_1 import executeScan

class TestScan1Frag(ExpFragment):
    def build_fragment(self):
        self.setattr_param("repetitions", IntParam, "NUMBER OF SCAN REPETITIONS", default = 1)
        self.setattr_fragment("scan", executeScan)
        self.CHOOSE_FIT = "None"
    @kernel
    def run_once(self):
        self.scan.run.ON(10*us, 1*MHz, 0, [1*us, 1*us, 1*us], 100, 10*us, 1*MHz, 0.5)
        # self.run.ON(pulse_time, self.freq, self.channel.get(), const_time, self.num_repeat, self.detection_time,
        #             scanFreq,
        #             self.inputAmp.get())  # calls ON function in runScan fragment
        print("DONE")

ScanExp2 = make_fragment_scan_exp(TestScan1Frag)


