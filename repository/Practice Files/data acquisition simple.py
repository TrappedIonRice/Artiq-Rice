import sys
import os
import time
import numpy as np
import matplotlib.pyplot as plt
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay


class Simple633(EnvExperiment):
    def build(self):
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('ttl7')
        self.setattr_device('grabber0')
        self.setattr_argument("num_cycles", NumberValue(default=10000, step=1))

        self.target_count = int(self.num_cycles)
        self.num_rois = 16
        
        self.results_flat = [0] * (self.target_count * self.num_rois)
        # default time (update in kernel)
        self.measured_period_ms = 9.058

    def run(self):
        self.output_dir = "e:/文档/Artiq-Rice/captured_images" # results location
        os.makedirs(self.output_dir, exist_ok=True)

        print(f"Starting hardware kernel for data acquisition ({self.target_count} frames)...")
        start_time = time.time()
        
        
        self.run_kernel()

        
        execution_time = time.time() - start_time
        if self.target_count > 0:
            self.measured_period_ms = (execution_time / self.target_count) * 1000.0

        print("\nKernel acquisition finished. Exporting captured data...")

        total_pixels = 6 * 6
        results_2d = np.array(self.results_flat).reshape(self.target_count, self.num_rois)
        data_matrix = results_2d / total_pixels

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        all_csv_path = os.path.join(self.output_dir, f"all_frames_2d_rois_{timestamp}.csv")
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
            roi_counts = results_2d[i]
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

        means_raw = np.mean(results_2d, axis=0)
        stds_raw = np.std(results_2d, axis=0) / np.sqrt(self.target_count)  # Standard error of the mean
        
        means_avg = means_raw / total_pixels
        stds_avg = stds_raw / total_pixels
        stats_csv_path = os.path.join(self.output_dir, f"roi_statistics_{timestamp}.csv")
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

        roi16_data = data_matrix[:, 15]  
        group_size = 100
        num_groups = len(roi16_data) // group_size

        if num_groups > 0:
            roi16_reshaped = roi16_data[:num_groups * group_size].reshape(num_groups, group_size)
            
            group_means = np.mean(roi16_reshaped, axis=1)
            group_stds = np.std(roi16_reshaped, axis=1)/np.sqrt(group_size)  

            frame_period_s = self.measured_period_ms / 1000.0
            group_times_s = (np.arange(num_groups) * group_size + group_size / 2.0) * frame_period_s

            plt.figure(figsize=(10, 6))
            plt.errorbar(
                group_times_s, 
                group_means, 
                yerr=group_stds, 
                fmt='-o', 
                color='b', 
                ecolor='r', 
                capsize=4, 
                label='Mean ± Std (Every 100 frames)'
            )
            plt.title("ROI 16 Count Trend (100-Frame Grouped Average)")
            plt.xlabel("Time (s)")
            plt.ylabel("Average Count per Pixel")
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.legend()
            plot_path = os.path.join(self.output_dir, f"roi16_100frame_trend_{timestamp}.png")
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"\nROI 16 trend plot saved successfully to: {plot_path}")
        else:
            print("\nWarning: Total frames < 100, skipping 100-frame grouped plotting.")
        

        print("\n" + "=" * 65)
        print(f" 16 ROI  ({self.target_count} loops) statistics：")
        print("=" * 65)
        print(f"{'ROI Index':<10}{'Raw Total Mean ± Std':<28}{'PixelAvg Mean ± Std':<25}")
        print("-" * 65)
        for k in range(self.num_rois):
            print(f"ROI_{k:<6} {means_raw[k]:9.2f} ± {stds_raw[k]:<8.2f}     {means_avg[k]:8.2f} ± {stds_avg[k]:<8.2f}")
        print("=" * 65 + "\n")

        print(f"All data exported successfully! Matrix Shape: {data_matrix.shape}")
        print(f"Total execution time: {execution_time:.2f} seconds (Average Period: {self.measured_period_ms:.3f} ms)")

    @kernel
    def run_kernel(self):                           
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()

        
        for k in range(15):
            self.grabber0.setup_roi(k, 10 + k * 18, 5, 16 + k * 18, 11)
        self.grabber0.setup_roi(15, 110, 15, 116, 21)
        
        mask = 0b1111111111111111
        roi_buf = [0] * 16

        self.core.break_realtime()

        
        self.grabber0.gate_roi(mask)
        self.core.break_realtime()

        print("Starting precision-gated acquisition...")

        
        for count in range(self.target_count):
            self.core.break_realtime()

            
            self.grabber0.input_mu(roi_buf)

            
            offset = count * 16
            for k in range(16):
                self.results_flat[offset + k] = roi_buf[k]

        
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        self.ttl7.off()


if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()