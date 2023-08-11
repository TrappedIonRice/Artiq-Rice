from artiq.experiment import *

#Don't implement this code.

def input_led_state():# -> TBool:
    print("Check")
    #return input("Enter desired LED state: ") =="1"

class LED2(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("led0")

    @kernel
    def run(self):
        self.core.reset()
        input_led_state()
        s=self.led0.output()# input_led_state()
        self.core.break_realtime()

        #self.led0.off()
        if s==1:
            self.led0.on()
            #delay(1000*ms)
        else:
            self.led0.off()