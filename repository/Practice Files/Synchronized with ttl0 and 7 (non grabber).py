import sys
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, at_mu

class Simple1(EnvExperiment):
    def build(self):
        self.setattr_device('core')
        self.setattr_device('ttl0')
        self.setattr_device('ttl7')
        self.setattr_argument("num_cycles", NumberValue(default=1000, step=1, precision=0))

   

    @kernel
    def run(self):                           
        self.core.reset()
        self.core.break_realtime()
        
        self.ttl7.output()
        self.ttl7.off()
        self.core.break_realtime()

        self.ttl0.gate_falling(1*s)
        t_0 = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(1*s))  # Wait for falling edge with a timeout of 1 second
        if t_0 <0 :
            return

        self.core.break_realtime()
        

        for _ in range(self.num_cycles):


            self.core.break_realtime()
            self.ttl0.gate_rising(1 * ms)
            
            t_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(1 * ms))  # Wait for rising edge with a timeout of 1 second
            
            
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