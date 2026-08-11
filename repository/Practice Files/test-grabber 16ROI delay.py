import sys
import os
import time
import numpy as np
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay


class Simple633(EnvExperiment):
    def build(self):
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('ttl7')
        self.setattr_device('grabber0')
        self.setattr_argument("num_cycles", NumberValue(default=100, step=1, precision=0))

        self.target_count = int(self.num_cycles)
        self.num_rois = 16
        self.results = [[0] * self.num_rois for _ in range(self.target_count)]

    def run(self):
        self.output_dir = "e:/文档/Artiq-Rice/captured_images" #results location
        os.makedirs(self.output_dir, exist_ok=True)

        print(f"Starting hardware kernel for data acquisition ({self.target_count} frames)...")
        start_time = time.time()
        self.run_kernel()

        print("\nKernel acquisition finished. Exporting captured data...")

        total_pixels = 1 * 1
        data_matrix = np.array(self.results) / total_pixels

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
        stds_raw = np.std(self.results, axis=0) / np.sqrt(self.target_count)  # Standard error of the mean
        
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
        print(f"{'ROI Index':<10}{'Raw Total Mean ± Std':<28}{'PixelAvg Mean ± Std':<25}")
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

        # ROI（loop）

        for k in range(15):
            self.grabber0.setup_roi(k, 10 + k * 18, 0, 11 + k * 18, 1)
        self.grabber0.setup_roi(15, 124, 0, 125, 1)
        
        mask = 0b1111111111111111
        self.grabber0.gate_roi(0)
        roi_buf = [0] * 16
        
        

        self.core.break_realtime()

        
        self.ttl0.gate_falling(1 * s)
        t_align = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(1 * s))
        if t_align < 0:
            return  

        self.core.break_realtime()
        self.ttl0.gate_rising(9 * ms)
        t_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(9 * ms))
        if t_rise < 0:
            return

        self.ttl0.gate_falling(1 * s)
        t_fall = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(1 * s))
        if t_fall < 0:
            return

        duration = self.core.mu_to_seconds(t_fall - t_rise)
        time_ms = duration * 1000  
        print("Measured duration between rising and falling edges:", time_ms, "ms")
        if time_ms > 8.0:
            while time_ms > 8.0:
                time_ms = time_ms -1
        
        
        print("Adjusted measured duration:", time_ms, "ms")
        self.core.break_realtime()

        self.ttl0.gate_rising(20 * ms)
        t_rise1 = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(20 * ms))
        if t_rise1 < 0:
            return

        self.ttl7.on()
        self.grabber0.gate_roi(mask)

        for count in range(self.target_count):
            self.core.break_realtime()

            delay(50 * ms)
            
            self.ttl7.off()
            
            self.grabber0.gate_roi(0)

            self.grabber0.input_mu(roi_buf)
            for k in range(16):
                self.results[count][k] = roi_buf[k]

            delay(time_ms * ms)
            
            self.ttl7.on()
            self.grabber0.gate_roi(mask)


        self.ttl7.off()
        self.grabber0.gate_roi(0)

if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()
