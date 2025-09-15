from artiq.experiment import *

class LED(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("led0")

    @kernel
    def blink_once(self):
        self.led0.on()
        delay(1000*ms)
        self.led0.off()
        delay(1000*ms)

    def run(self):   # Host 端执行
        print("Starting LED test...")
        self.core.reset()
        for i in range(5):
            self.blink_once()   # 调用 kernel 函数
            print("Pulse", i+1)
