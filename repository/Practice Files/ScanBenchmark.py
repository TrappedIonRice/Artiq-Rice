import time
import numpy as np
from artiq.experiment import *

# --- BENCHMARK CONFIGURATION ---
# Set False for "Old Way" (Loop on FPGA)
# Set True for "New Way" (Loop on PC)
SCAN_OUTSIDE_KERNEL = False


class ScanBenchmark(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")

        # --- FIX: Initialize iter here so the kernel knows about it ---
        self.iter = 0

        # Define mock scan parameters for the test
        self.scan_arr = np.linspace(-5, 5, 20)  # 20 points
        self.num_repeat = 100  # 100 reps per point
        self.scan_param_name = "Test_Param"

    def run(self):
        # 1. Setup
        num_points = len(self.scan_arr)
        print(f"--- STARTING BENCHMARK: {'OUTSIDE' if SCAN_OUTSIDE_KERNEL else 'INSIDE'} KERNEL ---")
        print(f"Points: {num_points}, Reps: {self.num_repeat}")

        # 2. Execute & Time
        t_start = time.time()

        if SCAN_OUTSIDE_KERNEL:
            self.run_outside_kernel()
        else:
            self.run_inside_kernel()

        t_end = time.time()

        # 3. Calculate & Report
        total_time = t_end - t_start
        avg_per_point = total_time / num_points

        print("\n" + "=" * 40)
        print(f"RESULTS ({'Loop on PC' if SCAN_OUTSIDE_KERNEL else 'Loop on FPGA'})")
        print("=" * 40)
        print(f"Total Time per Full Scan:   {total_time:.4f} s")
        print(f"Total Time per Scan Point:  {avg_per_point:.4f} s")

        if SCAN_OUTSIDE_KERNEL:
            print("-" * 40)
            print("To find overhead, subtract the 'Inside Kernel' per-point time")
            print("from the 'Outside Kernel' per-point time above.")

    # ---------------------------------------------------------
    # CASE A: Loop on Host (New Way)
    # ---------------------------------------------------------
    def run_outside_kernel(self):
        # We perform the loop here in Python
        for i, scan_val in enumerate(self.scan_arr):
            self.krun_single_point(scan_val, i)

    @kernel
    def krun_single_point(self, scan_val, iter_index):
        self.core.reset()
        self.iter = iter_index
        self.rid_termination()

        # Simulate Physics
        self.mock_physics(scan_val)

    # ---------------------------------------------------------
    # CASE B: Loop in Kernel (Old Way)
    # ---------------------------------------------------------
    def run_inside_kernel(self):
        # We just call the kernel once
        self.krun_all_points(self.scan_arr)

    @kernel
    def krun_all_points(self, scan_arr):
        self.core.reset()
        self.iter = 0

        for scan_val in scan_arr:
            self.rid_termination()
            self.mock_physics(scan_val)
            self.iter += 1

    # ---------------------------------------------------------
    # Shared Helper Functions
    # ---------------------------------------------------------
    @kernel
    def mock_physics(self, val):
        """
        Simulates the actual work done in run_scan_point.
        Delay approximates the physics duration.
        """
        delay(10 * ms)  # Change this to match your real experiment duration roughly

    @rpc(flags={"async"})
    def rid_termination(self):
        rid = self.scheduler.rid
        if self.scheduler.check_termination(rid):
            self.scheduler.delete(rid)