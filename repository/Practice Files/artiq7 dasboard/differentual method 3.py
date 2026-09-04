import sys
import os
import time, math
import numpy as np
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay, at_mu, parallel, sequential


class Differentual3(EnvExperiment):
    def build(self):
        
        self.setattr_device('core')
        self.setattr_device('ttl0')      # trigger
        self.setattr_device('grabber0')  # grabber
        self.setattr_device('ttl3')      # input
        self.setattr_device('ttl5')      # output

        # 2. Dashboard parameter
        self.setattr_argument("num_cycles", NumberValue(default=5100, step=1))
        self.setattr_argument("threshold_val", NumberValue(default=520, step=1))  #  Count threshold

        # range
        self.setattr_argument("diff_lower_limit", NumberValue(default=-50.0, step=1.0))
        self.setattr_argument("diff_upper_limit", NumberValue(default=50.0, step=1.0))

        # ROI 14 
        self.setattr_argument("roi14_x0", NumberValue(default=75, step=1))
        self.setattr_argument("roi14_y0", NumberValue(default=13, step=1))
        self.setattr_argument("roi14_x1", NumberValue(default=81, step=1))
        self.setattr_argument("roi14_y1", NumberValue(default=19, step=1))

        # ROI 15 
        self.setattr_argument("roi15_x0", NumberValue(default=154, step=1))
        self.setattr_argument("roi15_y0", NumberValue(default=4, step=1))
        self.setattr_argument("roi15_x1", NumberValue(default=160, step=1))
        self.setattr_argument("roi15_y1", NumberValue(default=10, step=1))

    def setup_dashboard_plotting(self):
        
        #  ROI14 average
        self.set_dataset("ROI14_Plot.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI14_Plot.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI14_Plot.yerr_vals", [], broadcast=True, archive=True, persist=True)

        # ROI15 average
        self.set_dataset("ROI15_Plot.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI15_Plot.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI15_Plot.yerr_vals", [], broadcast=True, archive=True, persist=True)

        # ROI14 - ROI15 
        self.set_dataset("ROI_Diff_Plot.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Diff_Plot.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ROI_Diff_Plot.yerr_vals", [], broadcast=True, archive=True, persist=True)

        self.roi14_x, self.roi14_y, self.roi14_yerr = [], [], []
        self.roi15_x, self.roi15_y, self.roi15_yerr = [], [], []
        self.diff_x, self.diff_y, self.diff_yerr = [], [], []

        self.t0_avg_mu = None
        self.point_count = 0
        self.total_out_of_bounds_count = 0

    @rpc(flags={"async"})
    def update_roi_batch(self, avg14: TFloat, err14: TFloat, 
                         avg15: TFloat, err15: TFloat, 
                         avg_diff: TFloat, err_diff: TFloat, 
                         batch_avg_t_mu: TInt64, batch_out_of_bounds: TInt32, ttl3_sum: TInt32):
        
        if self.t0_avg_mu is None:
            self.t0_avg_mu = batch_avg_t_mu

        rel_time_s = float(self.core.mu_to_seconds(batch_avg_t_mu - self.t0_avg_mu))
        self.point_count += 1
        self.total_out_of_bounds_count += batch_out_of_bounds

         
        self.roi14_x.append(rel_time_s)
        self.roi14_y.append(avg14)
        self.roi14_yerr.append(err14)
        self.set_dataset("ROI14_Plot.x_vals", self.roi14_x, broadcast=True)
        self.set_dataset("ROI14_Plot.y_vals", self.roi14_y, broadcast=True)
        self.set_dataset("ROI14_Plot.yerr_vals", self.roi14_yerr, broadcast=True)

        # ROI 15 Live Plot
        self.roi15_x.append(rel_time_s)
        self.roi15_y.append(avg15)
        self.roi15_yerr.append(err15)
        self.set_dataset("ROI15_Plot.x_vals", self.roi15_x, broadcast=True)
        self.set_dataset("ROI15_Plot.y_vals", self.roi15_y, broadcast=True)
        self.set_dataset("ROI15_Plot.yerr_vals", self.roi15_yerr, broadcast=True)

        # ROI Diff Live Plot
        self.diff_x.append(rel_time_s)
        self.diff_y.append(avg_diff)
        self.diff_yerr.append(err_diff)
        self.set_dataset("ROI_Diff_Plot.x_vals", self.diff_x, broadcast=True)
        self.set_dataset("ROI_Diff_Plot.y_vals", self.diff_y, broadcast=True)
        self.set_dataset("ROI_Diff_Plot.yerr_vals", self.diff_yerr, broadcast=True)

        
        print(
            f"[Pt #{self.point_count:03d}] Time:{rel_time_s:6.3f}s | "
            f"ROI14:{avg14:6.2f} | ROI15:{avg15:6.2f} | Diff:{avg_diff:6.2f} | "
            f"Batch Out-of-Bounds:{batch_out_of_bounds:2d} (Total:{self.total_out_of_bounds_count}) | "
            f"TTL3 Sum:{ttl3_sum:3d}",
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

        self.output_dir = "E:/Artiq-Rice/captured_images"
        os.makedirs(self.output_dir, exist_ok=True)

        self.setup_dashboard_plotting()

        print(f"Starting hardware kernel for data acquisition ({self.target_count} frames)...", flush=True)
        print(f"ROI 14 Size: {self.pixels_roi14} px | ROI 15 Size: {self.pixels_roi15} px", flush=True)
        print(f"Difference Bounds: [{self.diff_lower_limit:.2f}, {self.diff_upper_limit:.2f}]", flush=True)

        self.run_kernel()
        time.sleep(0.2)

        print(f"\nKernel acquisition finished. Total actual frames acquired: {self.actual_completed_frames}", flush=True)
        total_ttl3_pulses = sum(self.ttl3_counts[:self.actual_completed_frames])
        print(f"Total TTL3 pulses recorded across all frames: {total_ttl3_pulses}", flush=True)

        
        if self.actual_completed_frames > 0:
            valid_results = self.results_flat[:self.actual_completed_frames * self.num_rois]
            results_2d = np.array(valid_results).reshape(self.actual_completed_frames, self.num_rois)
            
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            csv_path = os.path.join(self.output_dir, f"roi_data_{timestamp_str}.csv")
            
            headers = [f"ROI_{k}" for k in range(16)]
            headers.extend(["ROI14_Avg", "ROI15_Avg", "Diff", "TTL3_Count"])
            
            px14_arr = results_2d[:, 14] / float(self.pixels_roi14)
            px15_arr = results_2d[:, 15] / float(self.pixels_roi15)
            diff_arr = px14_arr - px15_arr
            ttl3_arr = np.array(self.ttl3_counts[:self.actual_completed_frames])
            
            combined_data = np.column_stack((results_2d, px14_arr, px15_arr, diff_arr, ttl3_arr))
            np.savetxt(csv_path, combined_data, fmt="%.4f", header=",".join(headers), delimiter=",")
            print(f"Data saved to: {csv_path}", flush=True)

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

        self.grabber0.gate_roi(mask)
        self.core.break_realtime()

        # variable
        batch_count = 0
        batch_sum_t_mu = np.int64(0)
        
        batch_sum_14 = 0.0
        batch_sq_sum_14 = 0.0
        
        batch_sum_15 = 0.0
        batch_sq_sum_15 = 0.0
        
        batch_sum_diff = 0.0
        batch_sq_sum_diff = 0.0
        
        batch_out_of_bounds = 0
        batch_ttl3_sum = 0
        
        t_gate_end = np.int64(0)
        pulse_cnt = 0
        
        px14 = 0.0
        px15 = 0.0
        diff_val = 0.0
        is_out_of_bounds = False

        self.ttl0.gate_rising(200 * s)#this is for the time.If it gets stuck, just delete it  
        self.core.break_realtime()

        for count in range(self.target_count):
            self.grabber0.input_mu(roi_buf)
            
             
    
            t_trigger = self.ttl0.timestamp_mu(t_gate_end)

    
            self.timestamps_mu[count] = t_trigger

            offset = count * 16
            for k in range(16):
                self.results_flat[offset + k] = roi_buf[k]
            
            raw14 = roi_buf[14]
            raw15 = roi_buf[15]

            # average and difference of single pixel
            px14 = raw14 / float(self.pixels_roi14)
            px15 = raw15 / float(self.pixels_roi15)
            diff_val = px14 - px15

            
            is_out_of_bounds = (diff_val < self.diff_lower_limit) or (diff_val > self.diff_upper_limit)

            self.core.break_realtime()

            
            with parallel:
                t_gate_end = self.ttl3.gate_rising(20 * us)
                with sequential:
                    delay(1 * us)
                    if is_out_of_bounds:
                        self.ttl5.pulse(10 * us)
                    else:
                        self.ttl5.off()

            
            pulse_cnt = self.ttl3.count(t_gate_end)
            self.ttl3_counts[count] = pulse_cnt

            
            batch_sum_14 += px14
            batch_sq_sum_14 += px14 * px14

            batch_sum_15 += px15
            batch_sq_sum_15 += px15 * px15

            batch_sum_diff += diff_val
            batch_sq_sum_diff += diff_val * diff_val

            if is_out_of_bounds:
                batch_out_of_bounds += 1

            batch_ttl3_sum += pulse_cnt
            batch_sum_t_mu += t_mu
            batch_count += 1

            #  Host 
            if batch_count == 100:
                #  ROI14
                avg14 = batch_sum_14 / 100.0
                var14 = (batch_sq_sum_14 / 99.0) - (100.0 * avg14 * avg14) / 99.0
                err14 = ((var14 if var14 > 0.0 else 0.0) ** 0.5) / 10.0

                # ROI15
                avg15 = batch_sum_15 / 100.0
                var15 = (batch_sq_sum_15 / 99.0) - (100.0 * avg15 * avg15) / 99.0
                err15 = ((var15 if var15 > 0.0 else 0.0) ** 0.5) / 10.0

                # Diff
                avg_diff = batch_sum_diff / 100.0
                var_diff = (batch_sq_sum_diff / 99.0) - (100.0 * avg_diff * avg_diff) / 99.0
                err_diff = ((var_diff if var_diff > 0.0 else 0.0) ** 0.5) / 10.0

                batch_avg_t_mu = batch_sum_t_mu // np.int64(100)

                #  Dashboard
                self.update_roi_batch(avg14, err14, avg15, err15, avg_diff, err_diff, 
                                     batch_avg_t_mu, batch_out_of_bounds, batch_ttl3_sum)

                
                batch_count = 0
                batch_sum_14 = 0.0
                batch_sq_sum_14 = 0.0
                batch_sum_15 = 0.0
                batch_sq_sum_15 = 0.0
                batch_sum_diff = 0.0
                batch_sq_sum_diff = 0.0
                batch_out_of_bounds = 0
                batch_ttl3_sum = 0
                batch_sum_t_mu = np.int64(0)

            self.actual_completed_frames = count + 1

        self.core.break_realtime()
        self.grabber0.gate_roi(0)
