import sys
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay

#exposure time 50 ms
class Simple3(EnvExperiment):
    def build(self):
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('ttl7')
        self.setattr_argument("num_cycles", NumberValue(default=1000, step=1, precision=0))

    def run(self):
        print("Starting hardware kernel for data acquisition...")
        self.run_kernel()

        print("\nKernel acquisition finished.")

    @kernel
    def run_kernel(self):                           
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()
        self.core.break_realtime()

       
        self.ttl0.gate_falling(20 * ms)
        t_align = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(1 * s))
        if t_align < 0:
            return  

       
        for _ in range(self.num_cycles):
            self.core.break_realtime()

           
            self.ttl0.gate_rising(7 * ms)
            t_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(7 * ms))
            
            if t_rise < 0:
                continue

            
            self.core.break_realtime()
            self.ttl7.on()
    
            
            self.ttl0.gate_falling(50 * ms)
            t_fall = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(50 * ms))

            if t_fall < 0:
                self.ttl7.off()
                continue

            self.core.break_realtime()
            self.ttl7.off()

if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()