import sys
import os
import time
import numpy as np
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay


class DynamicSizeROIFpga(EnvExperiment):
    def build(self):
        # Hardware
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('grabber0')
        self.setattr_device('ttl3')
        self.setattr_device('ttl4')

        # Dashboard 
        self.setattr_argument("num_cycles", NumberValue(default=5100, step=1))
        self.setattr_argument("threshold_val", NumberValue(default=520, step=1))  # 单像素平均 Count 阈值

        # ROI 14 on dashboard
        self.setattr_argument("roi14_x0", NumberValue(default=75, step=1))
        self.setattr_argument("roi14_y0", NumberValue(default=13, step=1))
        self.setattr_argument("roi14_x1", NumberValue(default=81, step=1))
        self.setattr_argument("roi14_y1", NumberValue(default=19, step=1))

        # ROI 15 on dashboard
        self.setattr_argument("roi15_x0", NumberValue(default=154, step=1))
        self.setattr_argument("roi15_y0", NumberValue(default=4, step=1))
        self.setattr_argument("roi15_x1", NumberValue(default=160, step=1))
        self.setattr_argument("roi15_y1", NumberValue(default=10, step=1))

    def setup_dashboard_plotting(self):
        
        # blue (ROI 15 > 50%)
        self.set_dataset("ROI_Plot_Blue.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Blue.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Blue.yerr_vals", [], broadcast=True, archive=True, persist=True)

        # red (ROI 14 > 50%)
        self.set_dataset("ROI_Plot_Red.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Red.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Red.yerr_vals", [], broadcast=True, archive=True, persist=True)

        # purple (各 50%)
        self.set_dataset("ROI_Plot_Purple.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Purple.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Purple.yerr_vals", [], broadcast=True, archive=True, persist=True)

        
        self.blue_x, self.blue_y, self.blue_yerr = [], [], []
        self.red_x, self.red_y, self.red_yerr = [], [], []
        self.purple_x, self.purple_y, self.purple_yerr = [], [], []

        self.buf_counts = []
        self.buf_times = []
        self.t0_mu = None

        self.cnt_roi15 = 0
        self.cnt_roi14 = 0
        self.point_count = 0

    @rpc(flags={"async"})
    def update_roi_realtime(self, chosen_raw_count: TInt32, active_roi_id: TInt32, timestamp_mu: TInt64):
        
        if self.t0_mu is None:
            self.t0_mu = timestamp_mu

        rel_time_s = self.core.mu_to_seconds(timestamp_mu - self.t0_mu)

        if active_roi_id == 15:
            pixel_avg = chosen_raw_count / float(self.pixels_roi15)
            self.cnt_roi15 += 1
        else:
            pixel_avg = chosen_raw_count / float(self.pixels_roi14)
            self.cnt_roi14 += 1

        self.buf_counts.append(pixel_avg)
        self.buf_times.append(rel_time_s)

        if len(self.buf_counts) == 100:
            mean_val = float(np.mean(self.buf_counts))
            std_val = float(np.std(self.buf_counts) / np.sqrt(100))
            time_val = float(np.mean(self.buf_times))
            self.point_count += 1

            
            if self.cnt_roi15 > 50:
                tag = "BLUE (ROI15 > 50%)"
                self.blue_x.append(time_val)
                self.blue_y.append(mean_val)
                self.blue_yerr.append(std_val)
                self.set_dataset("ROI_Plot_Blue.x_vals", self.blue_x, broadcast=True)
                self.set_dataset("ROI_Plot_Blue.y_vals", self.blue_y, broadcast=True)
                self.set_dataset("ROI_Plot_Blue.yerr_vals", self.blue_yerr, broadcast=True)

            elif self.cnt_roi14 > 50:
                tag = "RED (ROI14 > 50%)"
                self.red_x.append(time_val)
                self.red_y.append(mean_val)
                self.red_yerr.append(std_val)
                self.set_dataset("ROI_Plot_Red.x_vals", self.red_x, broadcast=True)
                self.set_dataset("ROI_Plot_Red.y_vals", self.red_y, broadcast=True)
                self.set_dataset("ROI_Plot_Red.yerr_vals", self.red_yerr, broadcast=True)

            else:  # cnt_roi15 == 50 and cnt_roi14 == 50
                tag = "PURPLE (50% / 50%)"
                self.purple_x.append(time_val)
                self.purple_y.append(mean_val)
                self.purple_yerr.append(std_val)
                self.set_dataset("ROI_Plot_Purple.x_vals", self.purple_x, broadcast=True)
                self.set_dataset("ROI_Plot_Purple.y_vals", self.purple_y, broadcast=True)
                self.set_dataset("ROI_Plot_Purple.yerr_vals", self.purple_yerr, broadcast=True)

            print(
                f"[Plot Point #{self.point_count:03d}] Avg Count: {mean_val:6.2f} | "
                f"Class: {tag:<20} | ROI 15: {self.cnt_roi15:2d}%, ROI 14: {self.cnt_roi14:2d}%",
                flush=True
            )

            # 清空单组缓存
            self.buf_counts = []
            self.buf_times = []
            self.cnt_roi15 = 0
            self.cnt_roi14 = 0

    def prepare_roi_dimensions(self):
        
        self.pixels_roi14 = abs(int(self.roi14_x1 - self.roi14_x0) * int(self.roi14_y1 - self.roi14_y0))
        self.pixels_roi15 = abs(int(self.roi15_x1 - self.roi15_x0) * int(self.roi15_y1 - self.roi15_y0))
        
        if self.pixels_roi14 == 0: self.pixels_roi14 = 1
        if self.pixels_roi15 == 0: self.pixels_roi15 = 1

    def run(self):
        self.prepare_roi_dimensions()
        
        self.target_count = int(self.num_cycles)
        self.num_rois = 16
        self.results_flat = [0] * (self.target_count * self.num_rois)
        self.timestamps_mu = [np.int64(0)] * self.target_count
        self.actual_completed_frames = 0

        self.output_dir = "e:/Artiq-Rice/captured_images"
        os.makedirs(self.output_dir, exist_ok=True)

        self.setup_dashboard_plotting()

        print(f"Starting hardware kernel for data acquisition ({self.target_count} frames)...", flush=True)
        print(f"ROI 14 Size: {self.pixels_roi14} px | ROI 15 Size: {self.pixels_roi15} px", flush=True)

        start_time = time.time()
        self.run_kernel()
        time.sleep(0.2) 

        print(f"\nKernel acquisition finished. Total actual frames acquired: {self.actual_completed_frames}", flush=True)

        if self.actual_completed_frames == 0:
            return

        valid_results = self.results_flat[:self.actual_completed_frames * self.num_rois]
        results_2d = np.array(valid_results).reshape(self.actual_completed_frames, self.num_rois)

        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        all_csv_path = os.path.join(self.output_dir, f"all_frames_2d_rois_{timestamp}.csv")
        headers = ",".join([f"ROI_{k}_Count" for k in range(self.num_rois)])
        np.savetxt(all_csv_path, results_2d, fmt="%d", header=headers, delimiter=",")

        pixel_counts = np.array([36] * 16)
        pixel_counts[14] = self.pixels_roi14  #  14
        pixel_counts[15] = self.pixels_roi15  #  15

        means_raw = np.mean(results_2d, axis=0)
        stds_raw = np.std(results_2d, axis=0) / np.sqrt(self.actual_completed_frames)
        means_avg = means_raw / pixel_counts
        stds_avg = stds_raw / pixel_counts

        print("\n" + "=" * 65, flush=True)
        print(f" 16 ROI ({self.actual_completed_frames} loops) statistics:", flush=True)
        print("=" * 65, flush=True)
        print(f"{'ROI Index':<10}{'Raw Total Mean ± Std':<28}{'PixelAvg Mean ± Std':<25}", flush=True)
        print("-" * 65, flush=True)
        for k in range(self.num_rois):
            print(f"ROI_{k:<6} {means_raw[k]:9.2f} ± {stds_raw[k]:<8.2f}     {means_avg[k]:8.2f} ± {stds_avg[k]:<8.2f}", flush=True)
        print("=" * 65 + "\n", flush=True)

    @kernel
    def run_kernel(self):
        self.core.reset()
        self.core.break_realtime()

        #  0~15
        for k in range(14):
            self.grabber0.setup_roi(k, 10 + k * 18, 5, 16 + k * 18, 11)
        self.grabber0.setup_roi(14, int(self.roi14_x0), int(self.roi14_y0), int(self.roi14_x1), int(self.roi14_y1))
        self.grabber0.setup_roi(15, int(self.roi15_x0), int(self.roi15_y0), int(self.roi15_x1), int(self.roi15_y1))

        mask = 0b1111111111111111
        roi_buf = [0] * 16

        raw_threshold_14 = int(self.threshold_val) * self.pixels_roi14
        raw_threshold_15 = int(self.threshold_val) * self.pixels_roi15

        active_roi = 15

        self.core.break_realtime()
        self.grabber0.gate_roi(mask)
        self.ttl0.gate_rising(200 * s)#ttl0 gate
        self.core.break_realtime()

        for count in range(self.target_count):
            self.core.break_realtime()

            
            t_mu = self.ttl0.timestamp_mu(now_mu())
            self.timestamps_mu[count] = t_mu
            self.grabber0.input_mu(roi_buf)

            offset = count * 16
            for k in range(16):
                self.results_flat[offset + k] = roi_buf[k]

            raw14 = roi_buf[14]
            raw15 = roi_buf[15]

            if active_roi == 15:
                if raw15 > raw_threshold_15:
                    active_roi = 14
            else:
                if raw14 < raw_threshold_14:
                    active_roi = 15

           
            
            if active_roi == 15:
                chosen_raw = raw15
                
                
            else:
                chosen_raw = raw14
                self.ttl4.on()
                
         

            
            self.update_roi_realtime(chosen_raw, active_roi, t_mu)
            self.actual_completed_frames = count + 1

        self.core.break_realtime()
        self.grabber0.gate_roi(0)