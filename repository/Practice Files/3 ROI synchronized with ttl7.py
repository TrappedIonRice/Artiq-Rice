import sys
import os
import numpy as np
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu


class Simple66(EnvExperiment):
    def build(self):
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('ttl7')
        self.setattr_device('grabber0')
        self.setattr_argument("target_frames", NumberValue(default=10, step=1, precision=0))

        self.target_count = int(self.target_frames)
        # 1.  3 ROI 
        self.num_rois = 3
        self.results = [[0] * self.num_rois for _ in range(self.target_count)]

    def run(self):
        self.output_dir = "e:/文档/Artiq-Rice/captured_images"
        os.makedirs(self.output_dir, exist_ok=True)

        print("Starting hardware kernel for data acquisition...")
        self.run_kernel()

        print("\nKernel acquisition finished. Exporting captured data to Laptop...")

        total_pixels = 5 * 5
        data_matrix = np.array(self.results)
        
        
        all_csv_path = os.path.join(self.output_dir, "all_frames_2d_rois.csv")
        np.savetxt(
            all_csv_path,
            data_matrix,
            fmt="%d",
            header="ROI_0_Count,ROI_1_Count,ROI_2_Count",
            delimiter=",",
        )

        # mean
        for i, roi_counts in enumerate(self.results):
            roi0_val = roi_counts[0]
            roi1_val = roi_counts[1]
            roi2_val = roi_counts[2]
            avg0 = roi0_val / total_pixels
            avg1 = roi1_val / total_pixels
            avg2 = roi2_val / total_pixels

            csv_path = os.path.join(self.output_dir, f"frame_{i + 1:02d}_roi_count.csv")
            np.savetxt(
                csv_path,
                np.array([[roi0_val, avg0, roi1_val, avg1, roi2_val, avg2]]),
                fmt=["%d", "%.2f", "%d", "%.2f", "%d", "%.2f"],
                header="ROI0_Total,ROI0_Avg,ROI1_Total,ROI1_Avg,ROI2_Total,ROI2_Avg",
                delimiter=",",
            )

            print(
                f"Frame {i + 1:02d}/{self.target_count} saved | "
                f"ROI0: {roi0_val} (Avg: {avg0:.2f}) | "
                f"ROI1: {roi1_val} (Avg: {avg1:.2f}) | "
                f"ROI2: {roi2_val} (Avg: {avg2:.2f})"
            )

        print(f"All 2D data exported successfully! Matrix Shape: {data_matrix.shape}")

    @kernel
    def run_kernel(self):                           
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()

        
        self.grabber0.setup_roi(0, 0, 0, 5, 5)
        self.grabber0.setup_roi(1, 6, 0, 11, 5)
        self.grabber0.setup_roi(2, 12, 0, 17, 5)
        
        
        mask = 0b111
        self.grabber0.gate_roi(0)
        self.core.break_realtime()

        print("[Kernel] Aligning initial TTL0 falling edge (1s gate)...")
        self.core.break_realtime()

        self.ttl0.gate_falling(1 * s)
        t_align = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(1 * s))
        if t_align < 0:
            print("[Kernel ERROR] Initial TTL0 alignment timed out!")
            return  

        print("[Kernel] Initial TTL0 aligned successfully. Starting acquisition loop...")
        self.core.break_realtime()

        roi_buf = [0] * self.num_rois
        captured_count = 0  

        while captured_count < self.target_count:
            self.core.break_realtime()

            print("[Kernel] Waiting for Rising Edge... Frame:", captured_count + 1)
            self.core.break_realtime()

            self.ttl0.gate_rising(7 * ms)
            t_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(7 * ms))
            
            if t_rise < 0:
                print("[Kernel WARN] Rising edge timeout! Retrying loop...")
                self.core.break_realtime()
                continue  

            self.core.break_realtime()
            self.ttl7.on()
            
        
            self.grabber0.gate_roi(mask) 

            print("[Kernel] Rising edge detected! Waiting for Falling Edge (100ms)...")
            self.core.break_realtime()

            self.ttl0.gate_falling(100 * ms)
            t_fall = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(100 * ms))

            if t_fall < 0:
                print("[Kernel WARN] Falling edge timeout! Turning off TTL7 & Retrying loop...")
                self.core.break_realtime()
                self.ttl7.off()
                self.grabber0.gate_roi(0)
                continue  

            self.core.break_realtime()
            self.ttl7.off()
            self.grabber0.gate_roi(0)  

            print("[Kernel] Acquisition finished. Fetching Grabber data via input_mu()...")
            self.core.break_realtime()

            self.grabber0.input_mu(roi_buf)
            
            print("[Kernel SUCCESS] Grabber data read successfully! ROI0:", roi_buf[0], "ROI1:", roi_buf[1], "ROI2:", roi_buf[2])
            self.core.break_realtime()
            
            
            self.results[captured_count][0] = roi_buf[0]
            self.results[captured_count][1] = roi_buf[1]
            self.results[captured_count][2] = roi_buf[2]
            
            captured_count += 1

        print("[Kernel] Task completed: All target frames captured successfully!")


if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()