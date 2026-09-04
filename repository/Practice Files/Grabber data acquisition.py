import sys
import os
import time
import numpy as np
import matplotlib.pyplot as plt
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay


class Simple33(EnvExperiment):
    def build(self):
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('ttl7')
        self.setattr_device('grabber0')
        self.setattr_argument("num_cycles", NumberValue(default=10000, step=1))

    def setup_dashboard_plotting(self):
        """仿照第二个文件的语言风格，初始化 ARTIQ Dashboard 绘图数据集"""
        self.set_dataset("ROI16_Plot.x_label", "Time (s)", broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI16_Plot.y_label", "Average Count per Pixel", broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI16_Plot.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI16_Plot.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI16_Plot.yerr_vals", [], broadcast=True, archive=True, persist=True)

        
        self.buf_counts = []
        self.buf_times = []
        self.realtime_x = []
        self.realtime_y = []
        self.realtime_yerr = []
        self.t0_mu = None

    @rpc(flags={"async"})
    def update_roi16_realtime(self, raw_count: TInt32, timestamp_mu: TInt64):
        
        if self.t0_mu is None:
            self.t0_mu = timestamp_mu

        # relative time
        rel_time_s = self.core.mu_to_seconds(timestamp_mu - self.t0_mu)
        
        # Average Count (6 * 6 像素)
        pixel_avg = raw_count / 36.0

        self.buf_counts.append(pixel_avg)
        self.buf_times.append(rel_time_s)

        #  Dashboard
        if len(self.buf_counts) == 100:
            mean_val = float(np.mean(self.buf_counts))
            std_val = float(np.std(self.buf_counts) / np.sqrt(100))  
            time_val = float(np.mean(self.buf_times))

            self.realtime_x.append(time_val)
            self.realtime_y.append(mean_val)
            self.realtime_yerr.append(std_val)

        
            self.set_dataset("ROI16_Plot.x_vals", self.realtime_x, broadcast=True)
            self.set_dataset("ROI16_Plot.y_vals", self.realtime_y, broadcast=True)
            self.set_dataset("ROI16_Plot.yerr_vals", self.realtime_yerr, broadcast=True)

            
            self.buf_counts = []
            self.buf_times = []

    def run(self):
        self.target_count = int(self.num_cycles)
        self.num_rois = 16
        self.results_flat = [0] * (self.target_count * self.num_rois)
        self.timestamps_mu = [np.int64(0)] * self.target_count
        self.measured_period_ms = 9.058
        
        self.output_dir = "e:/Artiq-Rice/captured_images"
        os.makedirs(self.output_dir, exist_ok=True)

        
        self.setup_dashboard_plotting()

        print(f"Starting hardware kernel for data acquisition ({self.target_count} frames)...")
        start_time = time.time()
        
        self.run_kernel()

        execution_time = time.time() - start_time
        print("\nKernel acquisition finished. Processing hardware timestamps...")

        frame_abs_times_s = np.array([self.core.mu_to_seconds(t) for t in self.timestamps_mu])
        rel_frame_times_s = frame_abs_times_s - frame_abs_times_s[0]
        
        if self.target_count > 1:
            total_hardware_duration = rel_frame_times_s[-1]
            self.measured_period_ms = (total_hardware_duration / (self.target_count - 1)) * 1000.0
            print(f"Hardware Timestamps Processed! Measured Period: {self.measured_period_ms:.4f} ms")
        
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
            group_stds = np.std(roi16_reshaped, axis=1) / np.sqrt(group_size)  

            # time axis
            time_reshaped = rel_frame_times_s[:num_groups * group_size].reshape(num_groups, group_size)
            group_times_s = np.mean(time_reshaped, axis=1)

            
            self.set_dataset("ROI16_Plot.x_vals", group_times_s.tolist(), broadcast=True)
            self.set_dataset("ROI16_Plot.y_vals", group_means.tolist(), broadcast=True)
            self.set_dataset("ROI16_Plot.yerr_vals", group_stds.tolist(), broadcast=True)

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
            plt.title(f"ROI 16 Count Trend (Hardware Timed, Avg Period: {self.measured_period_ms:.4f} ms)")
            plt.xlabel("Time (s)")
            plt.ylabel("Average Count per Pixel")
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.legend()
            plot_path = os.path.join(self.output_dir, f"roi16_100frame_trend_{timestamp}.png")
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"ROI 16 trend plot saved successfully to: {plot_path}")
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
        print(f"Total execution time: {execution_time:.2f} s | Hardware Period: {self.measured_period_ms:.4f} ms")

    @kernel
    def run_kernel(self):                           
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()

        # 16 ROI
        for k in range(15):
            self.grabber0.setup_roi(k, 10 + k * 18, 5, 16 + k * 18, 11)
        self.grabber0.setup_roi(15, 75, 13, 81, 19)
        
        mask = 0b1111111111111111
        roi_buf = [0] * 16

        self.core.break_realtime()

        # Grabber ROI 
        self.grabber0.gate_roi(mask)

        
        self.ttl0.gate_rising(200 * s)

        self.core.break_realtime()
        print("Starting precision-gated acquisition with hardware time-tagging...")

        
        for count in range(self.target_count):
            self.core.break_realtime()

            
            self.grabber0.input_mu(roi_buf)
            self.ttl7.on()
            
            t_mu = self.ttl0.timestamp_mu(now_mu())
            self.timestamps_mu[count] = t_mu
            delay(1*ms)
            self.ttl7.off()
            
            offset = count * 16
            for k in range(16):
                self.results_flat[offset + k] = roi_buf[k]

            
            self.update_roi16_realtime(roi_buf[15], t_mu)

    
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        self.ttl7.off()