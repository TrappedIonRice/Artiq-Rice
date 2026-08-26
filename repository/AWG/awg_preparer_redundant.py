
# 25/11/03 gt

# 26/07/28: redundant; jsut run preparer

import numpy as np
from artiq.experiment import *
from sipyco import pyon
import os
import socket
from typing import Dict, List

HOST = "127.0.0.1"
PORT = 5000


class awgPreparer(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl5")  # To scope & AWG
        # self.setattr_device("ttl4")  # To AWG

        # --- Scan Mode Selection ---
        self.setattr_argument("live_update_scan",
                              BooleanValue(False), tooltip="Enable step-by-step (slower) scan")

        # --- AWG Scan Target ---
        # This string determines WHAT on the AWG is scanned.
        # It also determines WHICH Scannable argument below is used.
        self.setattr_argument("scan_variables_csv",
                              StringValue("AWG.ch1.T0"),
                              tooltip="Variable(s) to scan (e.g., 'AWG.ch1.T0', 'AWG.ch1.V0', 'AWG.ch1.f00')")

        # --- 3 Distinct Scannables ---
        self.setattr_argument("ramanTime_ms",
                              Scannable(default=RangeScan(0.0, 0.001, 5),
                                        global_min=0.00001 * ms, global_step=1.0e-5 * ms, unit='ms'),
                              group="AWG Scan")

        self.setattr_argument("ramanFreq_MHz",
                              Scannable(NoScan(value=self.get_dataset('AWG.ch1.f00')),
                                        global_min=0.001 * MHz, global_max=250.0 * MHz,
                                        global_step=1.0e-9 * MHz, unit="MHz", ndecimals=6),
                              group='AWG Scan')

        self.setattr_argument("ramanAmp",
                              Scannable(NoScan(value=self.get_dataset('AWG.ch1.V0')),
                                        global_min=0.0, global_max=0.8,
                                        global_step=1.0e-9, unit="", ndecimals=3),
                              group='AWG Scan')

        self.awg_group = 'AWG'

        # Kernel timing variables
        self.t_start_mu = np.int64(0)
        self.t_end_mu = np.int64(0)
        self.t_reps = np.int64(0)

    def prepare(self):
        self.num_reps = int(self.get_dataset("Repetitions"))

        # --- 1. Parse the Scan Target ---
        self.scan_variable_list = [v.strip() for v in self.scan_variables_csv.split(',')]
        self.scan_var_name = self.scan_variable_list[0]

        # --- 2. Switch Logic: Select the correct Scannable based on the name ---
        # This maps the string "T0" -> ramanTime_ms, "V0" -> ramanAmp, etc.


        if "T" in self.scan_var_name:
            # Time Scan: Dashboard (ms) -> AWG (s)
            active_scannable = self.ramanTime_ms
            self.scan_units = 's'
            print(f"[ARTIQ] Mode: TIME SCAN (Target: {self.scan_var_name}) | Converting ms -> s")

        elif "V" in self.scan_var_name or "Amp" in self.scan_var_name:
            # Amplitude: Dashboard (V) -> AWG (V)
            active_scannable = self.ramanAmp
            self.scan_units = 'V'
            print(f"[ARTIQ] Mode: AMPLITUDE SCAN (Target: {self.scan_var_name}) | Units: V")

        elif "f" in self.scan_var_name or "Hz" in self.scan_var_name:
            # Frequency: Dashboard (MHz) -> AWG (Hz)
            active_scannable = self.ramanFreq_MHz
            self.scan_units = 'Hz'
            print(f"[ARTIQ] Mode: FREQUENCY SCAN (Target: {self.scan_var_name}) | Converting MHz -> Hz")

        else:
            # Fallback
            active_scannable = self.ramanAmp
            self.scan_units = '?'
            print(f"[ARTIQ] WARNING: Unrecognized scan variable '{self.scan_var_name}'. Defaulting to Amp (Scale 1.0).")

        # --- 3. Extract Points & Apply Scaling ---
        # list(active_scannable) gives the raw numbers from the GUI (e.g. 100 for 100MHz)
        # We multiply by scale_factor to get the physical values (e.g. 100e6 Hz)
        raw_points = np.array(list(active_scannable))
        self.scan_points = raw_points
        print('Scan pts', self.scan_points)
        self.num_pts = int(len(self.scan_points))

        # --- 4. Broadcast Datasets (CRITICAL for Plotting & Run Logic) ---
        # This pushes the data so 'run()' can pick it up via self.get_dataset
        self.set_dataset('AWG.Scan_Parameter.name', self.scan_variables_csv, broadcast=True)
        self.set_dataset('AWG.Scan_Parameter.array', self.scan_points, broadcast=True)
        self.set_dataset('AWG.Scan_Parameter.units', self.scan_units, broadcast=True)

        # --- 5. Package scan info ---
        self.scan_info = {
            "scan_variables": self.scan_variable_list,
            "start": self.scan_points[0],
            "stop": self.scan_points[-1],
            "num_pts": self.num_pts,
            "num_reps": self.num_reps
        }

        # --- 6. Fetch LIVE globals ---
        ts = [f"T{i}" for i in range(4)]
        vs = [f"V{i}" for i in range(4)]
        fs = [f"f{i}{j}" for i in range(4) for j in range(2)]
        phs = [f"ph{i}" for i in range(4)]
        all_suffixes = ts + vs + fs + phs
        global_keys = [f"AWG.ch{ch}.{suffix}"
                       for ch in range(1, 5)
                       for suffix in all_suffixes]

        static_keys = [key for key in global_keys if key not in self.scan_variable_list]
        self.global_vars = self.get_awg_globals(static_keys)

        # Add placeholder for scanned var
        for key in self.scan_variable_list:
            self.global_vars[key] = 0.0

        # --- 7. T-Sum Logic (Determine Pulse Durations) ---
        # This logic needs to know if T is scanned or static.

        # ch = int(self.ttl_pulse_sum_channel) #include relevant logic when there are multiple waveforms per channel to be played sequentially
        ch = 1
        relevant_T_vars = [f"AWG.ch{ch}.T0", f"AWG.ch2.T0", f"AWG.ch3.T0", f"AWG.ch4.T0"]  # Extend list if summing multiple segments T1, T2...

        try:
            t_var_values_dict = self.get_awg_globals(relevant_T_vars)

            static_T_values_host_list = []
            is_T_var_scanned_host_list = []
            self.pulse_durations = []

            for var in relevant_T_vars:
                if var in self.scan_variable_list:
                    # This T-var is being scanned
                    is_T_var_scanned_host_list.append(np.int32(1))
                    static_T_values_host_list.append(0.0)
                else:
                    # This T-var is static
                    is_T_var_scanned_host_list.append(np.int32(0))
                    static_val = t_var_values_dict[var]
                    static_T_values_host_list.append(static_val)
                    print(f"[ARTIQ] Found static T-var: {var} = {static_val} s")

            self.static_T_values_list = np.array(static_T_values_host_list)
            self.is_T_var_scanned_list = np.array(is_T_var_scanned_host_list)

        except KeyError as e:
            print(f"[ARTIQ] FATAL ERROR: T-var {e} not found in fetched globals.")
            self.static_T_values_list = np.array([0.0])
            self.is_T_var_scanned_list = np.array([np.int32(0)])

        # Calculate actual pulse durations array
        self.pulse_durations = []
        min_pulse_duration = 1.0 * us

        for i in range(self.num_pts):
            pulse_duration = 0.0
            for j in range(len(self.is_T_var_scanned_list)):
                if self.is_T_var_scanned_list[j] == 1:
                    # If T is scanned, add the scan point value
                    pulse_duration += self.scan_points[i]
                else:
                    # If T is static, add the static value
                    pulse_duration += self.static_T_values_list[j]

            if pulse_duration <= 0.0:
                pulse_duration = min_pulse_duration

            self.pulse_durations.append(pulse_duration)

        self.pulse_durations = np.array(self.pulse_durations)

        # --- 8. Initialize AWG ---
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
            self.talk_to_awg()

    # 26/01/07 gt
    def run(self):
        pass
        # # add scan information to the AWG dataset to be fetched by barebones artiq for proper scan and plotting
        # # self.set_dataset(f"{self.awg_group}.{self.scan_param_name}.{'enable'}", self.enableAWG,
        # #                  broadcast=True, persist=True)
        # # self.set_dataset(f"{self.awg_group}.{self.scan_param_name}.{'type'}", self.scan_type,
        # #                  broadcast=True, persist=True)
        # self.set_dataset(f"{self.awg_group}.{self.scan_param_name}.{'array'}", self.scan_points,
        #                  broadcast=True, persist=True)
        # self.set_dataset(f"{self.awg_group}.{self.scan_param_name}.{'units'}", self.scan_units,
        #                  broadcast=True, persist=True)
        # self.set_dataset(f"{self.awg_group}.{self.scan_param_name}.{'name'}", self.scan_var_name,
        #                  broadcast=True, persist=True)


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
        print(awg_vars)
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

