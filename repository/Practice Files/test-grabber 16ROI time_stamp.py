import sys
import os
import time
import numpy as np
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay


class Simple66(EnvExperiment):
    def build(self):
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('ttl7')
        self.setattr_device('grabber0')
        self.setattr_argument("target_frames", NumberValue(default=4000, step=1))

        self.target_count = int(self.target_frames)
        self.num_rois = 16
        self.results = [[0] * self.num_rois for _ in range(self.target_count)]

    def run(self):
        self.output_dir = "e:/文档/Artiq-Rice/captured_images"
        os.makedirs(self.output_dir, exist_ok=True)

        print(f"Starting hardware kernel for data acquisition ({self.target_count} frames)...")
        start_time = time.time()
        self.run_kernel()

        print("\nKernel acquisition finished. Exporting captured data...")

        total_pixels = 6 * 6
        data_matrix = np.array(self.results)/total_pixels

        all_csv_path = os.path.join(self.output_dir, "all_frames_2d_rois.csv")
        headers = ",".join([f"ROI_{k}_Count" for k in range(self.num_rois)])
        np.savetxt(
            all_csv_path,
            data_matrix,
            fmt="%d",
            header=headers,
            delimiter=",",
        )

        export_single_limit = min(self.target_count, 10)
        fmt_list = ["%d", "%.2f"] * self.num_rois
        header_list = []
        for k in range(self.num_rois):
            header_list.extend([f"ROI{k}_Total", f"ROI{k}_Avg"])
        header_str = ",".join(header_list)

        for i in range(export_single_limit):
            roi_counts = self.results[i]
            row_data = []
            for k in range(self.num_rois):
                count_val = roi_counts[k]
                avg_val = count_val / total_pixels
                row_data.extend([count_val, avg_val])

            csv_path = os.path.join(self.output_dir, f"frame_{i + 1:02d}_roi_count.csv")
            np.savetxt(
                csv_path,
                np.array([row_data]),
                fmt=fmt_list,         
                header=header_str,     
                delimiter=",",
            )

        means_raw = np.mean(self.results, axis=0)
        stds_raw = np.std(self.results, axis=0)/np.sqrt(self.target_count)  # Standard error of the mean
        
        means_avg = means_raw / total_pixels
        stds_avg = stds_raw / total_pixels
        stats_csv_path = os.path.join(self.output_dir, "roi_statistics.csv")
        stats_data = np.column_stack((
            np.arange(self.num_rois), 
            means_raw, 
            stds_raw, 
            means_avg, 
            stds_avg
        ))
        np.savetxt(
            stats_csv_path,
            stats_data,
            fmt=["%d", "%.4f", "%.4f", "%.4f", "%.4f"],
            header="ROI_Index,Raw_Mean,Raw_Std,PixelAvg_Mean,PixelAvg_Std",
            delimiter=",",
        )
        print("\n" + "=" * 65)
        print(f" 16 ROI  ({self.target_count} loops) statistics：")
        print("=" * 65)
        print(f"{'ROI Index':<10}{ ' Mean ± Std':<28}{ ' Mean ± Std':<25}")
        print("-" * 65)
        for k in range(self.num_rois):
            print(f"ROI_{k:<6} {means_raw[k]:9.2f} ± {stds_raw[k]:<8.2f}     {means_avg[k]:8.2f} ± {stds_avg[k]:<8.2f}")
        print("=" * 65 + "\n")

        print(f"All data exported successfully! Matrix Shape: {data_matrix.shape}")
        end_time = time.time()
        print(f"Total execution time: {end_time - start_time:.2f} seconds")

    @kernel
    def run_kernel(self):       
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()


        for k in range(15):
            self.grabber0.setup_roi(k, 10 + k * 18, 5, 16 + k * 18, 11)
        
        self.grabber0.setup_roi(15, 107, 14, 113, 20)
        
        mask = 0b1111111111111111
        self.grabber0.gate_roi(0)
        self.core.break_realtime()

        roi_buf = [0] * 16
        align_window = 10 * ms
        self.ttl0.gate_falling(align_window)
        t_align = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(align_window))
        
        if t_align < 0:
            print("[Kernel ERROR] Initial alignment failed: No falling edge detected on TTL0!")
            return

        print("[Kernel] Initial TTL0 falling edge aligned successfully!")
        self.core.break_realtime()

        cal_window = 10 * ms
        
        self.ttl0.gate_rising(cal_window)
        t_rise_cal = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(cal_window))

    
        self.ttl7.on()
        self.grabber0.gate_roi(mask)

        self.ttl0.gate_falling(cal_window)
        t_fall_cal = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(cal_window))

        
        self.ttl7.off()
        self.grabber0.gate_roi(0)

       

        self.core.break_realtime()
        self.grabber0.input_mu(roi_buf)
        for k in range(16):
            self.results[0][k] = roi_buf[k]

        measured_width_mu = t_fall_cal - t_rise_cal
        measured_width_s = self.core.mu_to_seconds(measured_width_mu)
        
        
        rising_gate_dynamic = 1 * ms
        falling_gate_dynamic = measured_width_s -1 * ms - rising_gate_dynamic

        print("[Kernel Calibration] Dynamic falling gate set to:", falling_gate_dynamic * 1000, "ms")
        self.core.break_realtime()

    
        captured_count = 1  # first frame captured during calibration

        while captured_count < self.target_count:
            self.core.break_realtime()

            # wait for the rising edge with dynamic gate
            self.ttl0.gate_rising(rising_gate_dynamic)
            time_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(rising_gate_dynamic))
            if time_rise < 0:
                print("[Kernel WARN] Rising edge timeout! Retrying loop...")
                self.core.break_realtime()
                continue  # skip to the next iteration          

            # open TTL7 and gate the grabber for the ROI
            self.ttl7.on()
            self.grabber0.gate_roi(mask) 

            delay(1 * ms)  # small delay to ensure the grabber is gated before the falling edge
            self.ttl7.off()
            self.ttl0.gate_falling(falling_gate_dynamic )
        

           
    
            
            self.grabber0.gate_roi(0) 

            # read the grabber data into roi_buf
            self.core.break_realtime()
            self.grabber0.input_mu(roi_buf)
            
            for k in range(16):
                self.results[captured_count][k] = roi_buf[k]

            captured_count += 1

        print("[Kernel] Task completed: All target frames captured successfully!")


if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()