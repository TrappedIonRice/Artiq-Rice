from artiq.experiment import *

class SetZotino(EnvExperiment):

    def build(self):

        self.setattr_device("core")
        self.setattr_device("zotino0")
        self.setattr_argument("channel",NumberValue(default=0,max=31,min=0, ndecimals=0,  scale=1, step=1, type="int"))
        self.setattr_argument("value", NumberValue(default=0.000, max=9.999, min=-10.000,ndecimals=3))
        self.setattr_argument("reset", BooleanValue(default=False))
        self.setattr_argument("reset_value", NumberValue(default=0.000, max=9.999, min=-10.000,ndecimals=5))
    @kernel
    def initialize(self):
        self.core.reset()
        self.zotino0.init()
        delay(1*ms)


    @kernel
    def krun(self):
        self.initialize()


        #self.zotino0.calibrate(self.channel,-9.999,9.999)
        # self.zotino0.write_offset(self.channel,-0.012)
        # self.zotino0.load()
        delay(200 * us)
        self.zotino0.write_dac(self.channel,self.value)
        self.zotino0.load()


        delay(100*us)
        if self.reset:
            for i in range(32):

                self.zotino0.write_dac(i,self.reset_value)
                self.zotino0.load()
                delay(100*us)


    def run(self):
        self.krun()
        print("Set DAC {0:d} to value {1:0.3f}V".format(self.channel,self.value))


