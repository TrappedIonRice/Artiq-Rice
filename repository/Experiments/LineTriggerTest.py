from artiq.experiment import *
import numpy as np
import time as timelib

class LineTriggerTest(EnvExperiment):
    def build(self):
        # Please make sure to enter the right units.
        self.setattr_device("core")
        #self.setattr_device("ttl0")

        self.setattr_device("ttl0_counter") # receives line triggers
        self.setattr_device("ttl5") # exp sync trigger


    def prepare(self):
        #self.data_arr=[]
        pass

    def run(self):
        self.krun()

    @kernel
    def exp_exec(self):
        self.ttl5.on()
        delay(0.5*ms)
        self.ttl5.off()
        delay(0.5*ms)

    @kernel
    def krun(self):
        self.core.reset()
        self.ttl5.output()

        probetime= 1*ms
        fc=0
        scanpoints=200
        outer_loop_max_time= 1*s
        outer_loop_iter_max=int(outer_loop_max_time/probetime)
        outer_loop_iter=outer_loop_iter_max

        while fc==0 and scanpoints>0:
            self.ttl0_counter.gate_rising(probetime)
            delay(1*us)
            fc=self.ttl0_counter.fetch_count()
            outer_loop_iter=outer_loop_iter-1
            if outer_loop_iter==0:
                print("Maximum time exceeded to receive triggers (sec):")
                print(outer_loop_max_time)
                break
            if fc==1:
                self.exp_exec()
                fc=0
                outer_loop_iter=outer_loop_iter_max
                scanpoints=scanpoints-1

        print("All scan points executed")
    # </editor-fold>

