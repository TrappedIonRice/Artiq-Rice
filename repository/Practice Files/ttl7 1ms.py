import sys
from artiq.experiment import *
from artiq.language.units import ms, us, s
from artiq.language.core import now_mu, delay

#1 ms Exposure time
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
        t_align = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(20 * ms))
        if t_align < 0:
            return  

        self.core.break_realtime()
        self.ttl0.gate_rising(9 * ms)
        t_rise = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(9 * ms))
        if t_rise < 0:
            return

        self.ttl0.gate_falling(9 * ms)
        t_fall = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(9 * ms))
        if t_fall < 0:
            return

        duration = self.core.mu_to_seconds(t_fall - t_rise)
        time = duration * 1000  # Convert to milliseconds
        print("Measured duration between rising and falling edges:", time, "ms")
        if time > 8.0:
            time =time - 2.0
        if time > 7.0:
            time = time - 1.0

        print("Adjusted measured duration:", time, "ms")
        self.core.break_realtime()
        self.ttl0.gate_rising(20 * ms)
        t_rise1 = self.ttl0.timestamp_mu(now_mu() + self.core.seconds_to_mu(20 * ms))
        if t_rise1 < 0:
            return
        self.ttl7.on()
        for _ in range(self.num_cycles):
            self.core.break_realtime()


            delay(1 * ms)
            self.ttl7.off()
            delay(time*ms)
            self.ttl7.on()

        self.ttl7.off()
if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()