import sys
import time
from artiq.experiment import *
from artiq.language.core import at_mu, delay
from artiq.language.units import ms, s


class TTL7ToggleOnTTL0(EnvExperiment):
    def build(self):
        print("--> [1/3] Building experiment environment...", flush=True)
        self.setattr_device("core")
        self.setattr_device("ttl0_counter")  # Camera fire trigger input
        self.setattr_device("ttl7")
        # grabber removed from this simplified experiment

    @kernel
    def setup_output(self, width: TInt32, height: TInt32):
        self.core.reset()
        self.core.break_realtime()
        self.ttl7.output()
        self.ttl7.off()
        self.core.break_realtime()

    @kernel
    def wait_and_toggle(self, state: TInt32):
        """Wait for TTL0 rising gate, toggle TTL7, capture grabber frame.

        Returns (state, timestamp, count) so host can inspect trigger info.
        """
        self.core.reset()
        self.core.break_realtime()
        gate_end = self.ttl0_counter.gate_rising(10 * ms)
        timestamp, count = self.ttl0_counter.fetch_timestamped_count()
        at_mu(gate_end)
        self.core.break_realtime()

        # treat any detected edges as trigger (count>0)
        if count > 0:
            if state == 0:
                self.ttl7.on()
                delay(50*ms)
                self.ttl7.off()
                delay(6.379*ms)
                state = 1
            # else:
            #     self.ttl7.off()
            #     state = 0
            # Do not modify grabber gate here; host will read frames after trigger.

        # return state and trigger info for host-side logging
        return state, int(timestamp), int(count)

    def run(self):
        print("--> [2/3] Starting TTL0-triggered TTL7 toggle loop...", flush=True)
        state = 0
        max_attempts = 100000
        width = 54
        height = 22
        # initialize outputs
        self.setup_output(width, height)

        for attempt in range(1, max_attempts + 1):
            print(f"  [Attempt {attempt}/{max_attempts}] Waiting for TTL0 rising edge...", flush=True)
            result = self.wait_and_toggle(state)
            # kernel returns (state, timestamp, count)
            if isinstance(result, tuple):
                state, ts, cnt = result
            else:
                state = result
                ts = -1
                cnt = 0
            print(f"  └─ TTL7 output is now {'HIGH' if state else 'LOW'}", flush=True)
            print(f"    Trigger timestamp: {ts}, count: {cnt}", flush=True)
            state=0

if __name__ == "__main__":
    from artiq.frontend.artiq_run import main
    if len(sys.argv) == 1:
        sys.argv.append(__file__)
    main()