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
        self.setattr_argument("target_frames", NumberValue(default=10000, step=1, precision=0))

        self.target_count = int(self.target_frames)
        self.num_rois = 16
        self.results = [[0] * self.num_rois for _ in range(self.target_count)]

    def run(self):
        self.output_dir = "e:/文档/Artiq-Rice/captured_images"
        os.makedirs(self.output_dir, exist_ok=True)

        print(f"Starting hardware kernel for data acquisition ({self.target_count} frames)...")
        self.run_kernel()

        print("\nKernel acquisition finished. Exporting captured data...")

        total_pixels = 6 * 6
        data_matrix = np.array(self.results)

        
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

        print(f"All data exported successfully! Matrix Shape: {data_matrix.shape}")

    @kernel
    def run_kernel(self):       
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()

        for roi_index in range(self.num_rois):
            x_start = 10 + roi_index * 18
            x_end = x_start + 6
            self.grabber0.setup_roi(roi_index, x_start, 5, x_end, 11)
        
        
        mask = 0b1111111111111111
        self.grabber0.gate_roi(0)
        self.core.break_realtime()

        
        self.ttl0.gate_falling(20 * ms)
        t_align = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(20 * ms))
        if t_align < 0:
            return  

        roi_buf = [0] * 16
        captured_count = 0  

        while captured_count < self.target_count:
            self.core.break_realtime()


            self.ttl0.gate_rising(8 * ms)
            t_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(8 * ms))
            if t_rise < 0:
                continue  

        
            self.ttl7.on()
            self.grabber0.gate_roi(mask) 

    
            self.ttl0.gate_falling(5 * ms)
            t_fall = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(5 * ms))

            if t_fall < 0:
                self.ttl7.off()
                self.grabber0.gate_roi(0)
                continue  

            self.ttl7.off()
            self.grabber0.gate_roi(0) 


            self.core.break_realtime()
            self.grabber0.input_mu(roi_buf)
        
            for k in range(16):
                self.results[captured_count][k] = roi_buf[k]

            captured_count += 1


if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()