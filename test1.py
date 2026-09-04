import sys
from artiq.experiment import *
from artiq.language.core import delay
from artiq.language.units import ms, us, s

class TestTTL7(EnvExperiment):
    def build(self):
        print("--> [1/3] initialize the environment...", flush=True)
        self.setattr_device("core")
        #ttl7
        self.setattr_device("ttl7")

    @kernel
    def run_ttl_test(self):
        self.core.reset()
        self.core.break_realtime()

        # Output
        self.ttl7.output()
        self.core.break_realtime()

        # 10 pulses
        for _ in range(100):
            self.ttl7.pulse(1000 * ms)  # high pulses
            delay(1 * s)             # 10ms

    def run(self):
        try:
            self.run_ttl_test()
            print("Successfully")
        except Exception as e:
            print(f"❌ : {type(e).__name__}: {e}")

if __name__ == "__main__":
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()