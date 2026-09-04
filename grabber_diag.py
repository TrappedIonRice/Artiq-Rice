import sys
import time
import numpy as np
from artiq.experiment import *

class GrabberDiag(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("grabber0")

    @kernel
    def init_grabber(self):
        self.core.reset()
        self.core.break_realtime()
        # start with gate closed
        self.grabber0.gate_roi(0)
        self.core.break_realtime()

    @kernel
    def set_roi(self, x0: TInt32, y0: TInt32, x1: TInt32, y1: TInt32):
        # setup roi on device (ensure RTIO slack)
        self.core.reset()
        self.core.break_realtime()
        self.grabber0.setup_roi(0, x0, y0, x1, y1)
        self.core.break_realtime()

    @kernel
    def gate_once(self, duration_ms: TInt32):
        self.core.reset()
        self.core.break_realtime()
        self.grabber0.gate_roi(0x01)
        delay(duration_ms * ms)
        self.grabber0.gate_roi(0)

    def run(self):
        print('--> GrabberDiag: init', flush=True)
        self.init_grabber()
        buf = np.zeros(1, dtype=np.int32)

        # ROI list: (x0,y0,x1,y1)
        rois = [
            (0, 0, 54, 22),
            (0, 0, 27, 11),
            (0, 0, 10, 10),
            (0, 0, 100, 100),
        ]
        durations = [50, 100, 200, 500]  # ms

        for roi in rois:
            x0, y0, x1, y1 = roi
            print(f"Testing ROI {roi}", flush=True)
            try:
                self.set_roi(x0, y0, x1, y1)
                # small host-side pause to give the core time to settle
                time.sleep(0.05)
            except Exception as e:
                print(f"set_roi error: {type(e).__name__}: {e}", flush=True)
                continue
            for d in durations:
                try:
                    self.gate_once(int(d))
                    try:
                        self.grabber0.input_mu(buf, timeout_mu=int((d + 300) * 1000))
                    except Exception as e:
                        print(f"ROI {roi} dur {d}ms: read error: {type(e).__name__}: {e}", flush=True)
                        val = -1
                    else:
                        val = int(buf[0])
                except Exception as e:
                    print(f"ROI {roi} dur {d}ms: kernel error: {type(e).__name__}: {e}", flush=True)
                    val = -1
                print(f"ROI {roi} dur {d}ms: value={val}", flush=True)
                time.sleep(0.2)

if __name__ == '__main__':
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()
