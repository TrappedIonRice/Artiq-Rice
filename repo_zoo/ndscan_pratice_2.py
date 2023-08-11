from ndscan.experiment import *
import time

#This program will pulse ttl based on num inputted and plot output

class assignTTL(Fragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_device("ttl4")
        self.setattr_result("ttl_status")
    @kernel
    def ON(self):
        self.core.reset()
        self.ttl4.on()
        self.ttl_status.push(10)
        with parallel:
            delay(1000 * ms)
            time.sleep(1.0)
        self.ttl_status.push(10)
    @kernel
    def OFF(self):
        self.core.reset()
        self.ttl4.off()
        self.ttl_status.push(0)
        with parallel:
            delay(1000 * ms)
            time.sleep(1.0)
        self.ttl_status.push(0)
    """
    def assign_ttl_output(self, count):
        self.core.reset()
        self.ttl0.output()
        
        for i in range(count):
            self.ttl0.on()
            self.ttl_status.push(1)
            delay(1000 * ms)
            self.ttl0.off()
            self.ttl_status.push(0)
            delay(1000 * ms)
        """
class runTTL(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("setTTL", assignTTL)
        self.setattr_param("num_pulse", IntParam, "Number of Pulses", 5)
    """
    def build_fragment(self):
        self.setattr_fragment("setTTL", assignTTL)
        self.setattr_param("num_pulse", IntParam, "Number of Pulses", 5)
    """
    def run_once(self):
        for i in range(self.num_pulse.get()):
            self.setTTL.ON()
            print("ON")
            self.setTTL.OFF()
            print("OFF")
            """
            if i % 2 == 0:
                self.setTTL.ON()
                print("ON")
            else:
                self.setTTL.OFF()
                print("OFF")
            """
        print("EXPERIMENT DONE")
        print(self.num_pulse.get())
        #self.setTTL.assign_ttl_output(self.num_pulse.get())

TTLPracticeScan = make_fragment_scan_exp(runTTL)





