import sys
import os
import time, math
import numpy as np
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay, at_mu, parallel, sequential


class DynamicSizeROIFpga3(EnvExperiment):
    def build(self):
        
        self.setattr_device('core')
        self.setattr_device('ttl0')     
        self.setattr_device('grabber0') 
        self.setattr_device('ttl3')     
        self.setattr_device('ttl5')      

       
        self.setattr_argument("num_cycles", NumberValue(default=5100, step=1))
        self.setattr_argument("threshold_val", NumberValue(default=520, step=1)) 

        # 
        self.setattr_argument("roi14_x0", NumberValue(default=75, step=1))
        self.setattr_argument("roi14_y0", NumberValue(default=13, step=1))
        self.setattr_argument("roi14_x1", NumberValue(default=81, step=1))
        self.setattr_argument("roi14_y1", NumberValue(default=19, step=1))

        # R
        self.setattr_argument("roi15_x0", NumberValue(default=154, step=1))
        self.setattr_argument("roi15_y0", NumberValue(default=4, step=1))
        self.setattr_argument("roi15_x1", NumberValue(default=160, step=1))
        self.setattr_argument("roi15_y1", NumberValue(default=10, step=1))

    def setup_dashboard_plotting(self):
       
        self.set_dataset("ROI_Plot_Blue.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Blue.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Blue.yerr_vals", [], broadcast=True, archive=True, persist=True)

        self.set_dataset("ROI_Plot_Red.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Red.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Red.yerr_vals", [], broadcast=True, archive=True, persist=True)

        self.set_dataset("ROI_Plot_Purple.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Purple.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Plot_Purple.yerr_vals", [], broadcast=True, archive=True, persist=True)

        self.blue_x, self.blue_y, self.blue_yerr = [], [], []
        self.red_x, self.red_y, self.red_yerr = [], [], []
        self.purple_x, self.purple_y, self.purple_yerr = [], [], []

        self.t0_avg_mu = None
        self.point_count = 0

    @rpc(flags={"async"})
    def update_roi_batch(self, avg_pixel_count: TFloat, std_err: TFloat, batch_avg_t_mu: TInt64, cnt_roi15: TInt32, cnt_roi14: TInt32, ttl3_sum: TInt32):
        
        if self.t0_avg_mu is None:
            self.t0_avg_mu = batch_avg_t_mu

        rel_time_s = float(self.core.mu_to_seconds(batch_avg_t_mu - self.t0_avg_mu))
        ttl3_avg = float(ttl3_sum) / 100.0
        self.point_count += 1

        if cnt_roi15 > 50:
            tag = "BLUE (ROI15 > 50%)"
            self.blue_x.append(rel_time_s)
            self.blue_y.append(avg_pixel_count)
            self.blue_yerr.append(std_err)
            self.set_dataset("ROI_Plot_Blue.x_vals", self.blue_x, broadcast=True)
            self.set_dataset("ROI_Plot_Blue.y_vals", self.blue_y, broadcast=True)
            self.set_dataset("ROI_Plot_Blue.yerr_vals", self.blue_yerr, broadcast=True)

        elif cnt_roi14 > 50:
            tag = "RED (ROI14 > 50%)"
            self.red_x.append(rel_time_s)
            self.red_y.append(avg_pixel_count)
            self.red_yerr.append(std_err)
            self.set_dataset("ROI_Plot_Red.x_vals", self.red_x, broadcast=True)
            self.set_dataset("ROI_Plot_Red.y_vals", self.red_y, broadcast=True)
            self.set_dataset("ROI_Plot_Red.yerr_vals", self.red_yerr, broadcast=True)

        else:
            tag = "PURPLE (50% / 50%)"
            self.purple_x.append(rel_time_s)
            self.purple_y.append(avg_pixel_count)
            self.purple_yerr.append(std_err)
            self.set_dataset("ROI_Plot_Purple.x_vals", self.purple_x, broadcast=True)
            self.set_dataset("ROI_Plot_Purple.y_vals", self.purple_y, broadcast=True)
            self.set_dataset("ROI_Plot_Purple.yerr_vals", self.purple_yerr, broadcast=True)

        print(
            f"[Plot Point #{self.point_count:03d}] Time: {rel_time_s:6.3f}s | Avg Count: {avg_pixel_count:6.2f} | "
            f"Class: {tag:<20} | ROI 15: {cnt_roi15:2d}%, ROI 14: {cnt_roi14:2d}% | "
            f"TTL3 Pulses (100f sum/avg): {ttl3_sum}/{ttl3_avg:.2f}",
            flush=True
        )

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
        self.ttl3_counts = [0] * self.target_count
        self.actual_completed_frames = 0

        self.output_dir = "e:/Artiq-Rice/captured_images"
        os.makedirs(self.output_dir, exist_ok=True)

        self.setup_dashboard_plotting()

        print(f"Starting hardware kernel for data acquisition ({self.target_count} frames)...", flush=True)
        print(f"ROI 14 Size: {self.pixels_roi14} px | ROI 15 Size: {self.pixels_roi15} px", flush=True)

        self.run_kernel()
        time.sleep(0.2)

        print(f"\nKernel acquisition finished. Total actual frames acquired: {self.actual_completed_frames}", flush=True)
        total_ttl3_pulses = sum(self.ttl3_counts[:self.actual_completed_frames])
        print(f" Total TTL3 pulses recorded across all frames: {total_ttl3_pulses}", flush=True)

    
    @kernel
    def run_kernel(self):
        self.core.reset()
        self.core.break_realtime()

        self.ttl3.input()

        for k in range(14):
            self.grabber0.setup_roi(k, 10 + k * 18, 5, 16 + k * 18, 11)
        self.grabber0.setup_roi(14, int(self.roi14_x0), int(self.roi14_y0), int(self.roi14_x1), int(self.roi14_y1))
        self.grabber0.setup_roi(15, int(self.roi15_x0), int(self.roi15_y0), int(self.roi15_x1), int(self.roi15_y1))

        mask = 0b1111111111111111
        roi_buf = [0] * 16
       
        raw_threshold_14 = int(self.threshold_val) * self.pixels_roi14
        raw_threshold_15 = int(self.threshold_val) * self.pixels_roi15

        active_roi = 15

        self.grabber0.gate_roi(mask)
        
        
        self.core.break_realtime()
        batch_sum_t_mu = np.int64(0)
        batch_count = 0
        batch_sum_pixel = 0.0
        batch_cnt_15 = 0
        batch_cnt_14 = 0
        batch_ttl3_sum = 0
        batch_first_t_mu = np.int64(0)
        batch_sq_sum_pixel = 0.0
        
        variance = 0.0
        std_dev = 0.0
        std_err = 0.0
        t_gate_end = np.int64(0)
        pulse_cnt = 0
        px_val = 0.0

        for count in range(self.target_count):
            
            self.grabber0.input_mu(roi_buf)

            
            t_mu = now_mu()
            self.timestamps_mu[count] = t_mu

           
            

            offset = count * 16
            for k in range(16):
                self.results_flat[offset + k] = roi_buf[k]
            
            raw14 = roi_buf[14]
            raw15 = roi_buf[15]

            # 
            if active_roi == 15:
                if raw15 > raw_threshold_15:
                    active_roi = 14
            else:
                if raw14 < raw_threshold_14:
                    active_roi = 15

            
            self.core.break_realtime()

           
            with parallel:
                t_gate_end = self.ttl3.gate_rising(20 * us)
                with sequential:
                    delay(1 * us)  #
                    if active_roi == 15:
                        chosen_raw = raw15
                        self.ttl5.off()
                    else:
                        chosen_raw = raw14
                        self.ttl5.pulse(10 * us)  # 

            # 
            pulse_cnt = self.ttl3.count(t_gate_end)
            self.ttl3_counts[count] = pulse_cnt

            #
            if active_roi == 15:
                px_val = chosen_raw / float(self.pixels_roi15)
                batch_cnt_15 += 1
            else:
                px_val = chosen_raw / float(self.pixels_roi14)
                batch_cnt_14 += 1

            batch_sum_pixel += px_val
            batch_sq_sum_pixel += px_val * px_val  # square
            batch_ttl3_sum += pulse_cnt

            if batch_count == 0:
                batch_first_t_mu = t_mu
            batch_sum_t_mu += t_mu
            batch_count += 1

            if batch_count == 100:
                avg_pixel = batch_sum_pixel / 100.0
                variance =(batch_sq_sum_pixel / 99.0) - (100.0*avg_pixel * avg_pixel)/99.0
                if variance < 0.0: variance = 0.0
                std_dev = (variance)**0.5
                std_err = std_dev / 10.0
                batch_avg_t_mu = batch_sum_t_mu // np.int64(100)
                self.update_roi_batch(avg_pixel, std_err, batch_avg_t_mu, batch_cnt_15, batch_cnt_14, batch_ttl3_sum)
                
                batch_count = 0
                batch_sum_pixel = 0.0
                batch_cnt_15 = 0
                batch_cnt_14 = 0
                batch_ttl3_sum = 0
                batch_sq_sum_pixel = 0.0
                batch_sum_t_mu = np.int64(0)

            self.actual_completed_frames = count + 1

        self.core.break_realtime()
        self.grabber0.gate_roi(0)
