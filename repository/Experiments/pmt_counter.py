from artiq.experiment import *
import numpy as np
import time as tm
#import include

class PMTCounts(EnvExperiment):

    # \/ \/ \/ \/ \/ \/ build \/ \/ \/ \/ \/ \/
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl1")  #PMT Counts
        self.setattr_device("ttl1_counter")
        self.setattr_argument("Bin_Size", NumberValue(default=0.1, ndecimals=4, unit="s"))
        self.setattr_device("scheduler")
        self.setattr_argument("num_points", NumberValue(default=1000, ndecimals=0, step=1))
        self.setattr_device("ccb")  # needed to make plots displaying the counts
        self.count = 0
    # /\ /\ /\ /\ /\ /\ build /\ /\ /\ /\ /\ /\


    # \/ \/ \/ \/ \/ \/ prepare \/ \/ \/ \/ \/ \/
    def prepare(self):

        self.set_dataset("PMT_Counts.Y_vals", np.full(self.num_points, float(np.nan)), broadcast=True, archive=True)
        self.set_dataset("PMT_Counts.X_vals", np.full(self.num_points, float(np.nan)), broadcast=True, archive=True)

        command = "${artiq_applet}plot_xy PMT_Counts.Y_vals" \
                  " --x PMT_Counts.X_vals" \
                  " --fit PMT_Counts.Y_vals"
        self.ccb.issue("create_applet", "PMT Counts", command)
    # /\ /\ /\ /\ /\ /\ prepare /\ /\ /\ /\ /\ /\


    # \/ \/ \/ \/ \/ \/ run \/ \/ \/ \/ \/ \/
    @kernel
    def krun(self):
        self.core.reset()

        # method 1
        #with parallel:
        #gate_end_mu = self.ttl0.gate_rising(self.Bin_Size*s)
        #self.ttl0.gate_rising(self.Bin_Size * s)
        #delay(self.Bin_Size*s)
        #self.count = self.ttl0.count(gate_end_mu)
        #delay(10*ms)

        # method 2
        # self.ttl0_counter.gate_rising(self.Bin_Size * s)
        # delay(self.Bin_Size*s)
        # self.count=self.ttl0_counter.fetch_count()
        # delay(10*ms)

        #method 3

        time=0
        delay(1*ms)
        # while(time<self.num_points):
        #
        #     self.ttl0_counter.gate_rising(self.Bin_Size * s)
        #     delay(self.Bin_Size*s)
        #     self.count=self.ttl0_counter.fetch_count()
        #     delay(10*ms)
        #     #t1=tm.perf_counter()
        #     self.mutate_dataset("PMT_Counts.X_vals", time, time*self.Bin_Size)
        #     self.mutate_dataset("PMT_Counts.Y_vals", time, self.count / self.Bin_Size)
        #     delay(1*ms)
        #     time += 1

        while True:

            # t1=tm.perf_counter()
            for i in range(1, self.num_points + 1, 1):
                self.ttl1_counter.gate_rising(self.Bin_Size * s)
                delay(self.Bin_Size * s)
                self.count = self.ttl1_counter.fetch_count()
                delay(10 * ms)
                # self.mutate_dataset("PMT_Counts.X_vals", self.num_points-i, time * self.Bin_Size)
                # self.mutate_dataset("PMT_Counts.Y_vals", self.num_points-i, self.count / self.Bin_Size)
                self.update_dataset(i,time)
                delay(1 * ms)
                time += 1

    #@rpc(flags={"async"})
    @kernel
    def update_dataset(self,i,time):
        self.mutate_dataset("PMT_Counts.X_vals", self.num_points - i, time * self.Bin_Size)
        self.mutate_dataset("PMT_Counts.Y_vals", self.num_points - i, self.count / self.Bin_Size)

    def run(self):


        self.krun()
        #self.core.reset()
        #self.set_dataset("PMT_Counts", np.full(self.upper_bound, float(np.nan)), broadcast=True, archive=True)

        '''
        time = 0
        start_time = tm.perf_counter()
        self.krun()
        while True:
            try:
                if self.scheduler.check_pause():
                    self.core.comm.close()
                    self.scheduler.pause()
            except TerminationRequested:
                print("Terminated gracefully")
                return
            self.krun()
            self.mutate_dataset("PMT_Counts.X_vals", time, tm.perf_counter() - start_time)
            self.mutate_dataset("PMT_Counts.Y_vals", time, self.count/self.Bin_Size)
            time += 1
            print(tm.perf_counter() - start_time)
            
        '''

    # /\ /\ /\ /\ /\ /\ run /\ /\ /\ /\ /\ /\