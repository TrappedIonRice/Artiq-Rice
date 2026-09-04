import sys
import time
import numpy as np
from artiq.experiment import * 

from artiq.language.core import delay
from artiq.language.units import ms, us

class TestGrabberContinuous(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("grabber0")

    @kernel
    def init_grabber(self):
        self.core.reset()
        self.core.break_realtime()
        # ROI dimensions: adjust to your camera/grabber setup if needed
        self.grabber0.setup_roi(0, 0, 0, 54, 22)
        # Keep ROI gate disabled here; we'll gate per-capture to avoid RTIO overflow
        self.grabber0.gate_roi(0)
        self.core.break_realtime()

    @kernel
    def gate_once(self):
        self.core.reset()
        self.core.break_realtime()
        # open gate for a short fixed window to let one frame be enqueued
        self.grabber0.gate_roi(0x01)
        delay(150 * ms)
        self.grabber0.gate_roi(0)

    def run(self):
        print("--> TestGrabberContinuous: initializing grabber...", flush=True)
        self.init_grabber()
        buf = np.zeros(1, dtype=np.int32)
        for i in range(10):
            try:
                # gate in kernel, then host reads the frame
                self.gate_once()
                try:
                    self.grabber0.input_mu(buf, timeout_mu=int(300 * 1000))
                except Exception as e:
                    print(f"frame {i}: read error: {type(e).__name__}: {e}", flush=True)
                    buf[0] = -1
            except Exception as e:
                print(f"frame {i}: kernel call error: {type(e).__name__}: {e}", flush=True)
                buf[0] = -1
            print(f"frame {i}: {buf[0]}", flush=True)
            time.sleep(0.5)

if __name__ == "__main__":
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()
