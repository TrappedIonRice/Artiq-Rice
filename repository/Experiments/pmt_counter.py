from artiq.experiment import *
import numpy as np
import time as tm
import include

class PMTCounts(EnvExperiment):

    # \/ \/ \/ \/ \/ \/ build \/ \/ \/ \/ \/ \/
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl0")  #PMT Counts
        self.setattr_argument("Bin_Size", NumberValue(default=0.1, ndecimals=0, step=1, unit="ms"))
        self.setattr_device("scheduler")
        self.setattr_argument("upper_bound", NumberValue(default=1000, ndecimals=0, step=1))
        self.setattr_device("ccb")  # needed to make plots displaying the counts
        self.count = 0
    # /\ /\ /\ /\ /\ /\ build /\ /\ /\ /\ /\ /\


    # \/ \/ \/ \/ \/ \/ prepare \/ \/ \/ \/ \/ \/
    def prepare(self):

        self.set_dataset("PMT_Counts.Y_vals", np.full(self.upper_bound, float(np.nan)), broadcast=True, archive=True)
        self.set_dataset("PMT_Counts.X_vals", np.full(self.upper_bound, float(np.nan)), broadcast=True, archive=True)

        command = "${artiq_applet}plot_xy PMT_Counts.Y_vals --x PMT_Counts.X_vals"
        self.ccb.issue("create_applet", "PMT Counts", command)
    # /\ /\ /\ /\ /\ /\ prepare /\ /\ /\ /\ /\ /\


    # \/ \/ \/ \/ \/ \/ run \/ \/ \/ \/ \/ \/
    @kernel
    def krun(self):
        self.core.reset()

        with parallel:
            gate_end_mu = self.ttl0.gate_rising(self.Bin_Size*s)
            delay(self.Bin_Size*s)
        self.count = self.ttl0.count(gate_end_mu)
        delay(10*ms)

    def run(self):

        self.core.reset()
        #self.set_dataset("PMT_Counts", np.full(self.upper_bound, float(np.nan)), broadcast=True, archive=True)

        time = 0
        start_time = tm.perf_counter()
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
            self.mutate_dataset("PMT_Counts.Y_vals", time, self.count)
            time += 1
            print(tm.perf_counter() - start_time)
    # /\ /\ /\ /\ /\ /\ run /\ /\ /\ /\ /\ /\