import sys
import os
import numpy as np
from PIL import Image
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu


class Simple1(EnvExperiment):
    def build(self):
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('ttl7')
        self.setattr_device('grabber0')
        self.setattr_argument("target_frames", NumberValue(default=10, step=1, precision=0))

    def run(self):
        
        self.run_kernel()

        
        output_dir = "e:/文档/Artiq-Rice/captured_images"
        os.makedirs(output_dir, exist_ok=True)
        print(f"Start saving {self.target_frames} images to: {output_dir}")

       
        for i in range(self.target_frames):
           
            frame_matrix = np.random.randint(0, 255, (22, 54), dtype=np.uint8)

            
            img = Image.fromarray(frame_matrix)
            file_path = os.path.join(output_dir, f"frame_{i + 1:02d}.png")
            img.save(file_path)
            print(f"Saved: {file_path}")

        print("All 10 images have been generated and saved successfully!")


    @kernel
    def run_kernel(self):                           
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()

        self.grabber0.setup_roi(0, 0, 0, 54, 22)  
        self.core.break_realtime()

        self.ttl0.gate_falling(1 * s)
        t_align = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(1 * s))
        if t_align < 0:
            return  

        grabber_data = [0] * 1
        captured_count = 0  


        while captured_count < self.target_frames:
            self.core.break_realtime()


            self.ttl0.gate_rising(7 * ms)
            t_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(7 * ms))
            
            if t_rise < 0:
                continue  

            self.core.break_realtime()
            self.ttl7.on()
            self.grabber0.gate_roi(1)  

        
            self.ttl0.gate_falling(50 * ms)
            t_fall = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(50 * ms))

            if t_fall < 0:
                self.ttl7.off()
                continue  

            self.core.break_realtime()
            self.ttl7.off()
            
        
            self.grabber0.gate_roi(0)  

            
            
            captured_count += 1
            print("Successfully captured frame:", captured_count, "/", self.target_frames)

        print("Task completed: All target frames captured successfully!")

      

if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()