
# 25/11/03 gt
import numpy as np
from artiq.experiment import *
from sipyco import pyon
import os
import socket
from typing import Dict, List

HOST = "127.0.0.1"
PORT = 5000

class awgTriggerer(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl5")  # To scope
        self.setattr_device("ttl4")  # To AWG

        # --- Scan Mode Selection ---
        self.setattr_argument("live_update_scan",
                              BooleanValue(False),
                              "AWG Scan", "Enable step-by-step (slower) scan")

        # --- AWG Scan Group ---
        self.setattr_argument("scan_variables_csv",
                              StringValue("AWG.ch1.V0, AWG.ch2.V0, AWG.ch3.V0, AWG.ch4.V0"),
                              "AWG Scan",
                              "Variable(s) to scan (e.g., 'AWG.ch1.T0' or 'AWG.ch2.T0')")
        self.setattr_argument("start (V, s, or Hz)",
                              NumberValue(0.01, ndecimals=6),
                              "AWG Scan", "Start value (in V, s, or Hz)")
        self.setattr_argument("stop (V, s, or Hz)",
                              NumberValue(0.3, ndecimals=6),
                              "AWG Scan", "Stop value (in V, s, or Hz)")
        self.setattr_argument("num_pts",
                              NumberValue(5, ndecimals=0, step=1), "AWG Scan")

        # --- Triggering Group ---
        self.setattr_argument("delay_t",  # delay between pulses
                              NumberValue(2.0 * ms, unit="ms"),
                              "Triggering", "Delay between triggers")

        self.setattr_argument("ttl_pulse_sum_channel",
                              NumberValue(1, ndecimals=0, step=1, min=1, max=4),
                              "Triggering", "Which CH T0-T3 sum to use for pulse")

        # We will store the kernel start/end times here
        self.t_start_mu = np.int64(0) # to match kernel function
        self.t_end_mu = np.int64(0)
        self.t_reps = np.int64(0)

    def prepare(self):
        # --- 1. Get ARTIQ parameters ---
        self.num_reps = int(self.get_dataset("Repetitions"))
        self.num_pts_int = int(self.num_pts)
        self.scan_points = np.linspace(getattr(self, "start (V, s, or Hz)"),
                                       getattr(self, "stop (V, s, or Hz)"),
                                       self.num_pts_int)
        self.scan_variable_list = [v.strip() for v in self.scan_variables_csv.split(',')]

        # self.channel_status = self.get_channel_status()

        # --- 2. Package scan info (needed for both modes) ---
        self.scan_info = {
            "scan_variables": self.scan_variable_list,
            "start": getattr(self, "start (V, s, or Hz)"),
            "stop": getattr(self, "stop (V, s, or Hz)"),
            "num_pts": self.num_pts_int,
            "num_reps": self.num_reps
        }

        # --- 3. Fetch LIVE globals from GUI (The single source of truth) ---
        ts = [f"T{i}" for i in range(4)]
        vs = [f"V{i}" for i in range(4)]
        fs = [f"f{i}{j}" for i in range(4) for j in range(2)]
        phs = [f"ph{i}" for i in range(4)]
        all_suffixes = ts + vs + fs + phs
        global_keys = [f"AWG.ch{ch}.{suffix}"
                       for ch in range(1, 5)
                       for suffix in all_suffixes]

        # Fetch all static (non-scanned) keys
        static_keys = [key for key in global_keys if key not in self.scan_variable_list]
        self.global_vars = self.get_awg_globals(static_keys)

        # Also add the scanned keys to self.global_vars (with a placeholder)
        # so the T-Sum logic can find them.
        for key in self.scan_variable_list:
            self.global_vars[key] = 0.0  # Placeholder, value doesn't matter

        # --- 4. Prepare T-Sum Logic (for the kernel) ---
        # This logic now reads from self.global_vars, NOT get_dataset()

        ch = int(self.ttl_pulse_sum_channel)
        relevant_T_vars = [f"AWG.ch{ch}.T0", f"AWG.ch{ch}.T1", f"AWG.ch{ch}.T2", f"AWG.ch{ch}.T3"]

        print("[ARTIQ] Building T-Sum lists for kernel...")
        try:
            # Fetch the LIVE values for the 4 T-vars
            t_var_values_dict = self.get_awg_globals(relevant_T_vars)

            static_T_values_host_list = []
            is_T_var_scanned_host_list = []
            self.pulse_durations = []

            for var in relevant_T_vars:
                if var in self.scan_variable_list:
                    # This T-var is being scanned
                    is_T_var_scanned_host_list.append(np.int32(1))
                    static_T_values_host_list.append(0.0)  # Add 0.0 as a placeholder
                else:
                    # This T-var is static. Get its value from the dict we just fetched.
                    is_T_var_scanned_host_list.append(np.int32(0))
                    static_val = t_var_values_dict[var]
                    static_T_values_host_list.append(static_val)
                    print(f"[ARTIQ]   > Found static T-var: {var} = {static_val} s")

            self.static_T_values_list = np.array(static_T_values_host_list)
            self.is_T_var_scanned_list = np.array(is_T_var_scanned_host_list)

        except KeyError as e:
            print(f"[ARTIQ] FATAL ERROR: T-var {e} not found in fetched globals.")
            print("[ARTIQ] Check that the variable exists in the GUI.")
            self.static_T_values_list = np.array([0.0, 0.0, 0.0, 0.0])
            self.is_T_var_scanned_list = np.array([np.int32(0), np.int32(0), np.int32(0), np.int32(0)])

        # --- End T-Sum Logic ---

        if np.sum(self.is_T_var_scanned_list) > 0:
            print(
                f"[ARTIQ] TTL pulse sum will use SCAN VALUE for T-vars at indices: {np.where(self.is_T_var_scanned_list)[0]}")
        else:
            total_static_sum = np.sum(self.static_T_values_list) * 1e6
            print(f"[ARTIQ] TTL pulse sum will use STATIC sum for CH{ch}: {total_static_sum:.2f} us")

        self.pulse_durations = []
        min_pulse_duration = 1.0 * us  # Minimum duration in seconds

        for i in range(self.num_pts_int):
            pulse_duration = 0.0
            for j in range(len(self.is_T_var_scanned_list)):
                if self.is_T_var_scanned_list[j] == 1:
                    # If this T-var is scanned, use the value from scan_points
                    pulse_duration += self.scan_points[i]
                else:
                    # If it's static, use the value from the static list
                    pulse_duration += self.static_T_values_list[j]

            if pulse_duration <= 0.0:
                pulse_duration = min_pulse_duration

            self.pulse_durations.append(pulse_duration)

        # Convert to a numpy array for the kernel
        self.pulse_durations = np.array(self.pulse_durations)

        # --- 5. Branching Logic: Call the AWG Server ---
        if self.live_update_scan:
            print("[ARTIQ] Initializing AWG for LIVE UPDATE scan...")
            self.init_awg_live_scan(self.scan_info, self.global_vars)
        else:
            print("[ARTIQ] Initializing AWG for FULL PRELOAD scan...")
            self.payload = {
                "command": "PRELOAD_ALL_SCAN",
                "scan_info": self.scan_info,
                "globals": self.global_vars
            }
            # You must have a function like this that makes the RPC call
            self.talk_to_awg()

    @rpc
    def get_awg_globals(self, global_keys: list[str]) -> Dict[str, float]:
        """ Gathers all 'AWG.*' variables from the ARTIQ dataset """
        print("[ARTIQ RPC] Gathering all AWG_* dataset variables...")
        awg_vars = {}
        for key in global_keys:
            try:
                value = self.get_dataset(key)
                if isinstance(value, (int, float)):
                    awg_vars[key] = float(value)
                else:
                    print(f"[ARTIQ RPC] Warning: Skipping non-numeric AWG var: {key}")
            except Exception as e:
                print(f"[ARTIQ RPC] Error getting dataset key {key}: {e}")
        return awg_vars

    # for preloading from beginning
    @rpc
    def talk_to_awg(self):
        """
        Connects, sends the *full* payload, and waits for "WAVEFORMS_LOADED".
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))

                # 1. RECEIVE "READY_FOR_PARAMS"
                data = s.recv(4096).decode('utf-8')
                reply = pyon.decode(data)
                if reply.get("status") != "READY_FOR_PARAMS":
                    raise Exception(f"Unexpected initial reply from AWG: {reply}")

                # 2. SEND PAYLOAD
                s.sendall(pyon.encode(self.payload).encode('utf-8'))
                scanned_vars_str = ", ".join(self.payload['scan_info']['scan_variables'])
                print(f"[ARTIQ] Sent scan info for: {scanned_vars_str}")
                print(f"[ARTIQ] Sent {len(self.payload['globals'])} global variables.")

                # 3. RECEIVE "WAVEFORMS_LOADED"
                data = s.recv(4096).decode('utf-8')
                reply = pyon.decode(data)
                if reply["status"] == "WAVEFORMS_LOADED":
                    print("[ARTIQ] AWG waveforms loaded. Proceeding to kernel.")
                    return
                else:
                    error_msg = reply.get("message", "Unknown error from AWG")
                    raise Exception(f"AWG failed to prepare: {error_msg}")

        except ConnectionRefusedError:
            print("[ARTIQ] Error: Connection refused. Is the AWG server running?")
            raise
        except Exception as e:
            print(f"[ARTIQ] Error in talk_to_awg: {e}")
            raise

    @rpc
    def init_awg_live_scan(self, scan_info, static_globals):
        """Tells the AWG to set static globals and prepare for a live scan."""
        payload = {
            "command": "INIT_LIVE_SCAN",
            "scan_info": scan_info,
            "globals": static_globals
        }
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))

                # 1. RECEIVE "READY_FOR_PARAMS"
                data = s.recv(4096).decode('utf-8')
                reply = pyon.decode(data)
                if reply.get("status") != "READY_FOR_PARAMS":
                    raise Exception(f"AWG did not send READY_FOR_PARAMS. Got: {reply}")

                # 2. SEND "INIT_LIVE_SCAN" COMMAND
                s.sendall(pyon.encode(payload).encode('utf-8'))

                # 3. RECEIVE "READY_FOR_LIVE_SCAN"
                data = s.recv(4096).decode('utf-8')
                reply = pyon.decode(data)
                if reply.get("status") != "READY_FOR_LIVE_SCAN":
                    raise Exception(f"AWG failed to initialize live scan: {reply.get('message')}")

            print("[ARTIQ] AWG is ready for live scan.")
        except Exception as e:
            print(f"[ARTIQ] Error in init_awg_live_scan: {e}")
            raise

    @rpc
    def load_awg_scan_step(self, step_index, num_reps, num_pts):
        """Tells the AWG to load and queue the waveform for a precomputed step."""

        # print(f"[ARTIQ/RPC] load_awg_scan_step received num_reps: {num_reps}")

        payload = {
            "command": "LOAD_STEP",
            "step_index": step_index,
            "num_reps": num_reps,
            "num_pts": num_pts
        }
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))

                # 1. RECEIVE "READY_FOR_PARAMS"
                data = s.recv(4096).decode('utf-8')
                reply = pyon.decode(data)
                if reply.get("status") != "READY_FOR_PARAMS":
                    raise Exception(f"AWG did not send READY_FOR_PARAMS. Got: {reply}")

                # 2. SEND "LOAD_STEP" COMMAND
                s.sendall(pyon.encode(payload).encode('utf-8'))

                # 3. RECEIVE "STEP_LOADED"
                data = s.recv(4096).decode('utf-8')
                reply = pyon.decode(data)
                if reply.get("status") != "STEP_LOADED":
                    raise Exception(f"AWG failed to load step: {reply.get('message')}")

        except Exception as e:
            print(f"[ARTIQ] Error in load_awg_scan_step: {e}")
            raise

    @rpc
    def end_awg_live_scan(self):
        """Tells the AWG the scan is over, so it can restore original values."""
        payload = {"command": "END_SCAN"}
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))

                # 1. RECEIVE "READY_FOR_PARAMS"
                data = s.recv(4096).decode('utf-8')
                reply = pyon.decode(data)
                if reply.get("status") != "READY_FOR_PARAMS":
                    raise Exception(f"AWG did not send READY_FOR_PARAMS. Got: {reply}")

                # 2. SEND "END_SCAN" COMMAND
                s.sendall(pyon.encode(payload).encode('utf-8'))

                # 3. RECEIVE "SCAN_ENDED"
                data = s.recv(4096).decode('utf-8')
                reply = pyon.decode(data)
                if reply.get("status") != "SCAN_ENDED":
                    print(f"[ARTIQ] Warning: AWG did not confirm scan end. Got: {reply}")

        except Exception as e:
            print(f"[ARTIQ] Error in end_awg_live_scan: {e}")

    @kernel
    def run(self):
        # This flag tracks if cleanup is needed (i.e., on termination)
        cleanup_needed = True

        try:
            # --- This is your existing run logic ---
            self.core.reset()

            # 25/11/03 gt: timer start
            self.t_start_mu = self.core.get_rtio_counter_mu()
            self.t_reps = 0

            self.ttl5.output()
            self.ttl4.output()
            delay(20 * ms)

            for i in range(self.num_pts_int): # Loop `num_pts` times

                if self.live_update_scan:
                    self.load_awg_scan_step(i, self.num_reps, self.num_pts_int)
                    self.core.break_realtime() # needed to allow for the slow process of above rpc function

                pulse_duration = self.pulse_durations[i]

                t_j_start_mu = self.core.get_rtio_counter_mu()
                for j in range(self.num_reps):
                    delay(self.delay_t)
                    self.ttl5.on()
                    self.ttl4.on()
                    delay(pulse_duration)
                    self.ttl5.off()
                    self.ttl4.off()
                t_j_end_mu = self.core.get_rtio_counter_mu()
                self.t_reps += (t_j_end_mu - t_j_start_mu) # probably not working

            # If we finished the loop normally (not terminated):
            if self.live_update_scan:
                # 1. It was a live scan, so clean up.
                print("ARTIQ kernel: Live scan finished. Sending cleanup command...")
                self.end_awg_live_scan()
            else:
                # 2. It was a preload scan. DO NOT clean up.
                #    The cache is valid for the next run.
                print("ARTIQ kernel: Preload scan finished. Cache is valid.")

            # 25/11/03/gt: end of timer
            self.t_end_mu = self.core.get_rtio_counter_mu()

            # We finished normally, so no cleanup is needed in the 'finally' block.
            cleanup_needed = False
            # --- END NEW LOGIC ---

        finally:
            # This block runs on normal completion OR on termination.
            # If we get here from termination, cleanup_needed will still be True.
            if cleanup_needed:
                print("ARTIQ kernel: Terminated. Sending cleanup command...")
                self.end_awg_live_scan()

    # def analyze(self):
    #     """
    #     This method runs on the host *after* the kernel finishes.
    #     We use it to print the timing results.
    #     """
    #     if self.t_end_mu > self.t_start_mu:
    #         elapsed_mu = self.t_end_mu - self.t_start_mu
    #         elapsed_s = self.core.mu_to_seconds(elapsed_mu)
    #         reps_t = self.core.mu_to_seconds(self.t_reps)
    #
    #         if self.live_update_scan:
    #             mode = "Live Scan"
    #         else:
    #             mode = "Preload"
    #
    #         print("\n" + "=" * 50)
    #         print(f"      ARTIQ KERNEL RUNTIME ({mode})")
    #         print(f"       Scan points: {self.num_pts_int}")
    #         print(f"       Repetitions: {self.num_reps}")
    #         print(f"       Total time:  {elapsed_s:.4f} s")
    #
    #         # --- ADD THIS BLOCK ---
    #         rep_loop_s = self.core.mu_to_seconds(self.t_reps)
    #         print(f"    Time in Rep Loop: {rep_loop_s:.4f} s")
    #         # --- END ADD ---
    #
    #         print("=" * 50 + "\n")
    #     else:
    #         print("Kernel did not run long enough to get timing.")
