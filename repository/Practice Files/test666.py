import sys
import os
import numpy as np
from PIL import Image
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
        self.results = [0] * self.target_count

    def run(self):
        self.output_dir = "e:/文档/Artiq-Rice/captured_images"
        os.makedirs(self.output_dir, exist_ok=True)

        print("Starting hardware kernel for data acquisition...")
        self.run_kernel()

        print("\nKernel acquisition finished. Exporting captured data to Laptop...")

        total_pixels = 1 * 1

        for i, count_val in enumerate(self.results):
           
            avg_count = count_val / total_pixels

            
            csv_path = os.path.join(self.output_dir, f"frame_{i + 1:02d}_roi_count.csv")
            np.savetxt(
                csv_path,
                np.array([[count_val, avg_count]]),
                fmt=["%d", "%.2f"],
                header="Total_Count,Avg_Count_Per_Pixel",
                delimiter=",",
            )

           
            print(
                f"Frame {i + 1:02d}/{self.target_count} saved | Total: {count_val} | Avg: {avg_count:.2f} -> {csv_path}"
            )

        print("All frames exported successfully!")

    @kernel
    def run_kernel(self):                           
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()

        self.grabber0.setup_roi(0, 203, 5, 204, 6)
        self.core.break_realtime()

        print("[Kernel] Aligning initial TTL0 falling edge (20ms gate)...")
       
        self.core.break_realtime()

        self.ttl0.gate_falling(20 * ms)
        t_align = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(20 * ms))
        if t_align < 0:
            print("[Kernel ERROR] Initial TTL0 alignment timed out!")
            return  

        print("[Kernel] Initial TTL0 aligned successfully. Starting acquisition loop...")
        self.core.break_realtime()

        roi_buf = [0] 
        captured_count = 0  

        while captured_count < self.target_count:
            self.core.break_realtime()

            print("[Kernel] Waiting for Rising Edge... Frame:", captured_count + 1)
            self.core.break_realtime()

            self.ttl0.gate_rising(8 * ms)
            t_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(8 * ms))
            
            if t_rise < 0:
                print("[Kernel WARN] Rising edge timeout! Retrying loop...")
                self.core.break_realtime()
                continue  

            self.core.break_realtime()
            self.ttl7.on()
            self.grabber0.gate_roi(1) 

            print("[Kernel] Rising edge detected! Waiting for Falling Edge (9ms)...")
            self.core.break_realtime()

            self.ttl0.gate_falling(9 * ms)
            t_fall = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(9 * ms))

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
            
            print("[Kernel SUCCESS] Grabber data read successfully! Value:", roi_buf[0])
            self.core.break_realtime()
            
            self.results[captured_count] = roi_buf[0]
            captured_count += 1

        print("[Kernel] Task completed: All target frames captured successfully!")

    
if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()