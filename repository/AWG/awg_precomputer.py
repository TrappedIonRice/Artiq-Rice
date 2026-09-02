

# # 2026/08/13 gt: Added 2D scan capability, multi-channel parsing, and restored T-Sum logic
#
# import numpy as np
# from artiq.experiment import *
# from sipyco import pyon
# import socket
# from typing import Dict, List
#
# HOST = "127.0.0.1"
# PORT = 5000
#
#
# class awgPrecomputer(EnvExperiment):
#     """
#     AWG Precomputer
#     Generates scan arrays (1D or 2D unrolled), handles multi-channel simultaneous
#     scanning, applies Center-Out logic, and sends waveforms to cache.
#     """
#
#     def build(self):
#         self.setattr_device("core")
#
#         # --- Scan Setup ---
#         self.setattr_argument("enable_2D_scan", BooleanValue(False), group="Scan Setup")
#         self.setattr_argument("CenterScanMode", EnumerationValue(['Linear Center', 'Center Out']), group="Scan Setup")
#
#         # --- X-Axis Targets ---
#         self.setattr_argument("scan_variables_csv", StringValue("AWG.ch1.T0"),
#                               tooltip="Variable(s) for X-axis", group="X-Axis Scan")
#         self.setattr_argument("ramanTime_ms",
#                               Scannable(default=RangeScan(0.0, 0.001, 5), global_min=0.0 * ms, global_step=1e-5 * ms,
#                                         unit='ms', ndecimals=3), group="X-Axis Scan")
#         self.setattr_argument("ramanPh2_2pi",
#                               Scannable(NoScan(value=0.5), global_min=0.0, global_max=1.0, global_step=1e-4, unit="",
#                                         ndecimals=3), group="X-Axis Scan")
#         self.setattr_argument("ramanFreq_MHz",
#                               Scannable(NoScan(value=100.0), global_min=0.001 * MHz, global_max=400.0 * MHz,
#                                         global_step=1e-9 * MHz, unit="MHz", ndecimals=6), group="X-Axis Scan")
#         self.setattr_argument("ramanAmp",
#                               Scannable(NoScan(value=0.5), global_min=0.0, global_max=1.0, global_step=1e-9, unit="",
#                                         ndecimals=3), group="X-Axis Scan")
#
#         # --- Y-Axis Targets ---
#         self.setattr_argument("scan_variables_y_csv", StringValue(""),
#                               tooltip="Variable(s) for Y-axis", group="Y-Axis Scan")
#         self.setattr_argument("ramanTime_y_ms",
#                               Scannable(default=RangeScan(0.0, 0.001, 5), global_min=0.0 * ms, global_step=1e-5 * ms,
#                                         unit='ms', ndecimals=3), group="Y-Axis Scan")
#         self.setattr_argument("ramanPh2_y_2pi",
#                               Scannable(NoScan(value=0.5), global_min=0.0, global_max=1.0, global_step=1e-4, unit="",
#                                         ndecimals=3), group="Y-Axis Scan")
#         self.setattr_argument("ramanFreq_y_MHz",
#                               Scannable(NoScan(value=100.0), global_min=0.001 * MHz, global_max=400.0 * MHz,
#                                         global_step=1e-9 * MHz, unit="MHz", ndecimals=6), group="Y-Axis Scan")
#         self.setattr_argument("ramanAmp_y",
#                               Scannable(NoScan(value=0.5), global_min=0.0, global_max=1.0, global_step=1e-9, unit="",
#                                         ndecimals=3), group="Y-Axis Scan")
#
#     def _parse_scannable(self, scan_var_name, is_y=False):
#         """Helper to fetch the active scannable based on variable name"""
#         suffix = "_y" if is_y else ""
#         if "T" in scan_var_name:
#             return getattr(self, f"ramanTime{suffix}_ms"), 's'
#         elif "V" in scan_var_name or "Amp" in scan_var_name:
#             return getattr(self, f"ramanAmp{suffix}"), 'V'
#         elif "f" in scan_var_name or "Hz" in scan_var_name:
#             return getattr(self, f"ramanFreq{suffix}_MHz"), 'Hz'
#         elif "p" in scan_var_name or "ph" in scan_var_name:
#             return getattr(self, f"ramanPh2{suffix}_2pi"), '2pi'
#         return getattr(self, f"ramanAmp{suffix}"), '?'
#
#     def _apply_center_out(self, arr):
#         n = len(arr)
#         mid = n // 2
#         indices = []
#         left, right = mid - 1, mid
#         while right < n or left >= 0:
#             if right < n: indices.append(right); right += 1
#             if left >= 0: indices.append(left); left -= 1
#         return arr[np.array(indices)]
#
#     def prepare(self):
#         self.num_reps = int(self.get_dataset("Repetitions", default=100))
#
#         # --- 1. Parse X Axis ---
#         self.scan_var_x_list = [v.strip() for v in self.scan_variables_csv.split(',')]
#         scannable_x, self.scan_units_x = self._parse_scannable(self.scan_var_x_list[0], is_y=False)
#         self.scan_points_x = np.sort(np.array(list(scannable_x)))
#
#         if type(scannable_x).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
#             self.scan_points_x = self._apply_center_out(self.scan_points_x)
#
#         # --- 2. Process 2D Logic and Unroll Grid ---
#         self.awg_unrolled_array = []
#
#         if self.enable_2D_scan:
#             self.scan_var_y_list = [v.strip() for v in self.scan_variables_y_csv.split(',')]
#             scannable_y, self.scan_units_y = self._parse_scannable(self.scan_var_y_list[0], is_y=True)
#             self.scan_points_y = np.sort(np.array(list(scannable_y)))
#
#             if type(scannable_y).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
#                 self.scan_points_y = self._apply_center_out(self.scan_points_y)
#
#             # Create unrolled grid
#             x_grid, y_grid = np.meshgrid(self.scan_points_x, self.scan_points_y, indexing='ij')
#             flat_x, flat_y = x_grid.flatten(), y_grid.flatten()
#
#             # Map X values to ALL variables in x_list, and Y values to ALL variables in y_list
#             for x_val, y_val in zip(flat_x, flat_y):
#                 step_array = [x_val] * len(self.scan_var_x_list) + [y_val] * len(self.scan_var_y_list)
#                 self.awg_unrolled_array.append(step_array)
#
#             self.master_scan_var_list = self.scan_var_x_list + self.scan_var_y_list
#             self.num_pts = len(flat_x)
#         else:
#             # 1D fallback
#             for x_val in self.scan_points_x:
#                 self.awg_unrolled_array.append([x_val] * len(self.scan_var_x_list))
#
#             self.master_scan_var_list = self.scan_var_x_list
#             self.num_pts = len(self.scan_points_x)
#             self.scan_points_y = np.array([0.0])  # Dummy for datasets
#             self.scan_units_y = ""
#
#         # --- 3. Broadcast Datasets for ARTIQ Plotting ---
#         self.set_dataset('AWG.Scan_Parameter.is_2D', self.enable_2D_scan, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.name', self.scan_variables_csv, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.array', self.scan_points_x, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.units', self.scan_units_x, broadcast=True, persist=True)
#
#         self.set_dataset('AWG.Scan_Parameter.name_y', getattr(self, "scan_variables_y_csv", ""), broadcast=True,
#                          persist=True)
#         self.set_dataset('AWG.Scan_Parameter.array_y', self.scan_points_y, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.units_y', self.scan_units_y, broadcast=True, persist=True)
#
#         self.set_dataset('AWG.Scan_Parameter.unrolled_grid', self.awg_unrolled_array, broadcast=True, persist=True)
#
#         # --- 4. Fetch LIVE globals ---
#         ts = [f"T{i}" for i in range(4)]
#         vs = [f"V{i}" for i in range(4)]
#         fs = [f"f{i}{j}" for i in range(4) for j in range(2)]
#         phs = [f"ph{i}" for i in range(4)]
#         global_keys = [f"AWG.ch{ch}.{suffix}" for ch in range(1, 5) for suffix in (ts + vs + fs + phs)]
#
#         static_keys = [key for key in global_keys if key not in self.master_scan_var_list]
#         self.global_vars = self.get_awg_globals(static_keys)
#
#         # Add placeholders for scanned vars so T-Sum logic doesn't fail
#         for key in self.master_scan_var_list:
#             self.global_vars[key] = 0.0
#
#         # --- 5. T-Sum Logic (Determine Pulse Durations) ---
#         relevant_T_vars = ["AWG.ch1.T0", "AWG.ch2.T0", "AWG.ch3.T0", "AWG.ch4.T0"]
#         pulse_durations = []
#         min_pulse_duration = 1.0 * us
#
#         for step_vals in self.awg_unrolled_array:
#             total_duration = 0.0
#
#             # Temporarily apply this step's scanned variables
#             step_dict = self.global_vars.copy()
#             for i, var_name in enumerate(self.master_scan_var_list):
#                 step_dict[var_name] = step_vals[i]
#
#             # Sum durations (matching your previous logic)
#             for t_var in relevant_T_vars:
#                 total_duration += step_dict.get(t_var, 0.0)
#
#             if total_duration <= min_pulse_duration:
#                 total_duration = min_pulse_duration
#             pulse_durations.append(total_duration)
#
#         self.set_dataset('AWG.Scan_Parameter.pulse_durations', np.array(pulse_durations), broadcast=True, persist=True)
#
#         # --- 6. Package info and Send Precomputation Request ---
#         self.scan_info = {
#             "scan_variables": self.master_scan_var_list,
#             "scan_array": self.awg_unrolled_array,
#             "num_reps": self.num_reps,
#             "is_2d": self.enable_2D_scan
#         }
#
#         print(f"[ARTIQ] Targets: {self.master_scan_var_list}")
#         print(f"[ARTIQ] Total Grid Points: {self.num_pts}")
#         print("[ARTIQ] Sending PRECOMPUTE request to AWG Server...")
#         self.trigger_precomputation(self.scan_info, self.global_vars)
#
#     def run(self):
#         print("-" * 50)
#         print("[ARTIQ] AWG Precomputation COMPLETE.")
#         print("-" * 50)
#
#     @rpc
#     def get_awg_globals(self, global_keys: List[str]) -> Dict[str, float]:
#         awg_vars = {}
#         for key in global_keys:
#             try:
#                 val = self.get_dataset(key, default=0.0)
#                 if isinstance(val, (int, float)): awg_vars[key] = float(val)
#             except Exception:
#                 pass
#         return awg_vars
#
#     @rpc
#     def trigger_precomputation(self, scan_info, static_globals):
#         payload = {"command": "PRECOMPUTE_WAVEFORMS", "scan_info": scan_info, "globals": static_globals}
#         try:
#             with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#                 s.connect((HOST, PORT))
#                 resp = pyon.decode(s.recv(4096).decode())
#                 if resp.get("status") != "READY_FOR_PARAMS": raise RuntimeError(f"Handshake Failed: {resp}")
#
#                 s.sendall(pyon.encode(payload).encode())
#
#                 # 1MB buffer for the unrolled array
#                 resp = pyon.decode(s.recv(1024 * 1024).decode())
#                 if resp.get("status") != "PRECOMPUTATION_DONE": raise RuntimeError(f"Precomputation Failed")
#                 print("[ARTIQ RPC] AWG confirmed: Waveforms Cached in Software.")
#         except Exception as e:
#             print(f"[ARTIQ RPC] Error in trigger_precomputation: {e}")
#             raise

#
#
# # 2026/07/28 gt: final version of precomputer; the main experiment handles the choice of version (live of preload)
#
# import numpy as np
# from artiq.experiment import *
# from sipyco import pyon
# import socket
# from typing import Dict, List
#
# HOST = "127.0.0.1"
# PORT = 5000
#
#
# class awgPrecomputer(EnvExperiment):
#     """
#     AWG Precomputer
#     Generates scan arrays, applies Center-Out logic, and sends the
#     PRECOMPUTE_WAVEFORMS command to the AWG server to cache waveforms.
#     """
#
#     def build(self):
#         self.setattr_device("core")
#
#         # --- AWG Scan Target ---
#         self.setattr_argument("scan_variables_csv",
#                               StringValue("AWG.ch1.T0"),
#                               tooltip="Variable(s) to scan (e.g., 'AWG.ch1.T0', 'AWG.ch1.V0')")
#         self.setattr_argument("CenterScanMode", EnumerationValue(['Linear Center', 'Center Out']))
#
#         # --- Scannables (Units matter for the dashboard UX) ---
#         self.setattr_argument("ramanTime_ms",
#                               Scannable(default=RangeScan(0.0, 0.001, 5),
#                                         global_min=0.0 * ms, global_step=1.0e-5 * ms, unit='ms', ndecimals=3),
#                               group="AWG Scan (need only set scannable)")
#         self.setattr_argument("ramanPh2_2pi",
#                               Scannable(NoScan(value=0.5),
#                                         global_min=0.0, global_max=1.0,
#                                         global_step=1.0e-4, unit="", ndecimals=3),
#                               group='AWG Scan (need only set scannable)')
#         self.setattr_argument("ramanFreq_MHz",
#                               Scannable(NoScan(value=100.0),
#                                         global_min=0.001 * MHz, global_max=400.0 * MHz,
#                                         global_step=1.0e-9 * MHz, unit="MHz", ndecimals=6),
#                               group='AWG Scan (need only set scannable)')
#         self.setattr_argument("ramanAmp",
#                               Scannable(NoScan(value=0.5),
#                                         global_min=0.0, global_max=1.0,
#                                         global_step=1.0e-9, unit="", ndecimals=3),
#                               group='AWG Scan (need only set scannable)')
#
#     def prepare(self):
#         self.num_reps = int(self.get_dataset("Repetitions", default=100))
#
#         # --- 1. Parse the Scan Target ---
#         self.scan_variable_list = [v.strip() for v in self.scan_variables_csv.split(',')]
#         self.scan_var_name = self.scan_variable_list[0]
#
#         # --- 2. Select the correct Scannable ---
#         if "T" in self.scan_var_name:
#             active_scannable = self.ramanTime_ms
#             self.scan_units = 's'
#         elif "V" in self.scan_var_name or "Amp" in self.scan_var_name:
#             active_scannable = self.ramanAmp
#             self.scan_units = 'V'
#         elif "f" in self.scan_var_name or "Hz" in self.scan_var_name:
#             active_scannable = self.ramanFreq_MHz
#             self.scan_units = 'Hz'
#         elif "p" in self.scan_var_name or "ph" in self.scan_var_name:
#             active_scannable = self.ramanPh2_2pi
#             self.scan_units = '2pi'
#         else:
#             active_scannable = self.ramanAmp
#             self.scan_units = '?'
#
#         # --- 3. Generate Scan Points ---
#         self.scan_points = np.sort(np.array(list(active_scannable)))
#
#         # Apply Center-Out Logic if requested
#         is_center_scan = (type(active_scannable).__name__ == "CenterScan")
#         if is_center_scan and self.CenterScanMode == "Center Out":
#             self.scan_points = self._apply_center_out(self.scan_points)
#
#         self.num_pts = len(self.scan_points)
#
#         # --- 4. Broadcast Basic Datasets ---
#         self.set_dataset('AWG.Scan_Parameter.name', self.scan_variables_csv, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.array', self.scan_points, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.units', self.scan_units, broadcast=True, persist=True)
#
#         # --- 5. Package scan info for AWG Server ---
#         self.scan_info = {
#             "scan_variables": self.scan_variable_list,
#             "scan_array": self.scan_points.tolist(),
#             "num_reps": self.num_reps
#         }
#
#         # --- 6. Fetch LIVE globals from datasets ---
#         ts = [f"T{i}" for i in range(4)]
#         vs = [f"V{i}" for i in range(4)]
#         fs = [f"f{i}{j}" for i in range(4) for j in range(2)]
#         phs = [f"ph{i}" for i in range(4)]
#         all_suffixes = ts + vs + fs + phs
#         global_keys = [f"AWG.ch{ch}.{suffix}" for ch in range(1, 5) for suffix in all_suffixes]
#
#         static_keys = [key for key in global_keys if key not in self.scan_variable_list]
#         self.global_vars = self.get_awg_globals(static_keys)
#
#         # Add placeholder for scanned var
#         for key in self.scan_variable_list:
#             self.global_vars[key] = 0.0
#
#         # --- 7. T-Sum Logic (Determine Pulse Durations) ---
#         relevant_T_vars = ["AWG.ch1.T0", "AWG.ch2.T0", "AWG.ch3.T0", "AWG.ch4.T0"]
#         pulse_durations = []
#         min_pulse_duration = 1.0 * us
#
#         for i in range(self.num_pts):
#             total_duration = 0.0
#             for t_var in relevant_T_vars:
#                 if t_var in self.scan_variable_list:
#                     total_duration += self.scan_points[i]
#                 else:
#                     total_duration += self.global_vars.get(t_var, 0.0)
#
#             if total_duration <= min_pulse_duration:
#                 total_duration = min_pulse_duration
#             pulse_durations.append(total_duration)
#
#         self.set_dataset('AWG.Scan_Parameter.pulse_durations', np.array(pulse_durations), broadcast=True, persist=True)
#
#         # --- 8. Send Precomputation Request ---
#         print(f"[ARTIQ] Target: {self.scan_var_name} ({self.num_pts} points)")
#         print("[ARTIQ] Sending PRECOMPUTE request to AWG Server...")
#         self.trigger_precomputation(self.scan_info, self.global_vars)
#
#     def run(self):
#         # No kernel execution here.
#         print("--------------------------------------------------")
#         print("[ARTIQ] AWG Precomputation COMPLETE.")
#         print("[ARTIQ] Datasets updated and AWG Server Primed.")
#         print("[ARTIQ] You may now run the Main Experiment.")
#         print("--------------------------------------------------")
#
#     # --- Helper Methods ---
#
#     def _apply_center_out(self, arr):
#         """Reorders a linear array from the center point outward."""
#         n = len(arr)
#         mid = n // 2
#         indices = []
#         left, right = mid - 1, mid
#         while right < n or left >= 0:
#             if right < n:
#                 indices.append(right)
#                 right += 1
#             if left >= 0:
#                 indices.append(left)
#                 left -= 1
#         return arr[np.array(indices)]
#
#     @rpc
#     def get_awg_globals(self, global_keys: List[str]) -> Dict[str, float]:
#         """ Gathers AWG variables from the ARTIQ dataset system """
#         awg_vars = {}
#         for key in global_keys:
#             try:
#                 val = self.get_dataset(key, default=0.0)
#                 if isinstance(val, (int, float)):
#                     awg_vars[key] = float(val)
#             except Exception:
#                 pass
#         return awg_vars
#
#     @rpc
#     def trigger_precomputation(self, scan_info, static_globals):
#         """
#         Sends the data to the AWG and asks it to generate waveforms.
#         Waits until AWG returns 'PRECOMPUTATION_DONE'.
#         """
#         payload = {
#             "command": "PRECOMPUTE_WAVEFORMS",
#             "scan_info": scan_info,
#             "globals": static_globals
#         }
#
#         try:
#             with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#                 s.connect((HOST, PORT))
#
#                 # 1. Handshake
#                 resp = pyon.decode(s.recv(4096).decode())
#                 if resp.get("status") != "READY_FOR_PARAMS":
#                     raise RuntimeError(f"AWG Handshake Failed: {resp}")
#
#                 # 2. Send Data
#                 print(f"[ARTIQ RPC] Sending {len(static_globals)} globals and scan info...")
#                 s.sendall(pyon.encode(payload).encode())
#
#                 # 3. Wait for Calculation (Blocking)
#                 print("[ARTIQ RPC] Waiting for AWG software calculation...")
#                 resp = pyon.decode(s.recv(4096).decode())
#
#                 if resp.get("status") != "PRECOMPUTATION_DONE":
#                     error_msg = resp.get("message", "Unknown Error")
#                     raise RuntimeError(f"AWG Precomputation Failed: {error_msg}")
#
#                 print("[ARTIQ RPC] AWG confirmed: Waveforms Cached in Software.")
#
#         except ConnectionRefusedError:
#             print("[ARTIQ RPC] CRITICAL: Connection refused. Is the AWG Python Server running?")
#             raise
#         except Exception as e:
#             print(f"[ARTIQ RPC] Error in trigger_precomputation: {e}")
#             raise


# 2026/08/13 gt; for 2D scans

# 2026/08/13 gt: Added 2D scan capability (unrolled grid logic)

# 2026/08/13 gt: Added 2D scan capability, multi-channel parsing, and restored T-Sum logic

# 2026/08/14 gt: Clean descriptive variable support for AWG Precomputer

import numpy as np
from artiq.experiment import *
from sipyco import pyon
import socket
from typing import Dict, List

HOST = "127.0.0.1"
PORT = 5000


class awgPrecomputer(EnvExperiment):
    """
    AWG Precomputer
    Generates scan arrays (1D or 2D unrolled), handles multi-channel simultaneous
    scanning, applies Center-Out logic, and sends waveforms to cache.
    """

    def build(self):
        self.setattr_device("core")

        # --- Scan Setup ---
        self.setattr_argument("enable_2D_scan", BooleanValue(False), group="Scan Setup")
        self.setattr_argument("CenterScanMode", EnumerationValue(['Linear Center', 'Center Out']), group="Scan Setup")

        # --- X-Axis Targets ---
        self.setattr_argument("scan_variables_csv", StringValue("AWG.ch1.T0"),
                              tooltip="Variable(s) for X-axis (e.g. AWG.ch1.T0, AWG.ch1.T_pulse)", group="X-Axis Scan")
        self.setattr_argument("ramanTime_ms",
                              Scannable(default=RangeScan(0.0, 0.001, 5), global_min=0.0 * ms, global_step=1e-5 * ms,
                                        unit='ms', ndecimals=6), group="X-Axis Scan")
        self.setattr_argument("ramanPh2_2pi",
                              Scannable(NoScan(value=0.5), global_min=-100.0, global_max=100.0, global_step=1e-6, unit="",
                                        ndecimals=6), group="X-Axis Scan")
        self.setattr_argument("ramanFreq_MHz",
                              Scannable(NoScan(value=100.0), global_min=-400.0 * MHz, global_max=400.0 * MHz,
                                        global_step=1e-9 * MHz, unit="MHz", ndecimals=6), group="X-Axis Scan")
        self.setattr_argument("ramanAmp",
                              Scannable(NoScan(value=0.5), global_min=0.0, global_max=1.0, global_step=1e-9, unit="",
                                        ndecimals=6), group="X-Axis Scan")

        # --- Y-Axis Targets ---
        self.setattr_argument("scan_variables_y_csv", StringValue(""),
                              tooltip="Variable(s) for Y-axis", group="Y-Axis Scan")
        self.setattr_argument("ramanTime_y_ms",
                              Scannable(default=RangeScan(0.0, 0.001, 5), global_min=0.0 * ms, global_step=1e-5 * ms,
                                        unit='ms', ndecimals=6), group="Y-Axis Scan")
        self.setattr_argument("ramanPh2_y_2pi",
                              Scannable(NoScan(value=0.5), global_min=-100.0, global_max=100.0, global_step=1e-4, unit="",
                                        ndecimals=6), group="Y-Axis Scan")
        self.setattr_argument("ramanFreq_y_MHz",
                              Scannable(NoScan(value=100.0), global_min=-400.0 * MHz, global_max=400.0 * MHz,
                                        global_step=1e-9 * MHz, unit="MHz", ndecimals=6), group="Y-Axis Scan")
        self.setattr_argument("ramanAmp_y",
                              Scannable(NoScan(value=0.5), global_min=0.0, global_max=1.0, global_step=1e-9, unit="",
                                        ndecimals=6), group="Y-Axis Scan")

    def _parse_scannable(self, scan_var_name, is_y=False):
        """Helper to fetch active scannable based on variable leaf prefix"""
        suffix = "_y" if is_y else ""
        leaf = scan_var_name.split(".")[-1].strip()

        if leaf.startswith(("T", "t")):
            return getattr(self, f"ramanTime{suffix}_ms"), 's'
        elif leaf.startswith(("V", "v", "Amp", "amp")):
            return getattr(self, f"ramanAmp{suffix}"), 'V'
        elif leaf.startswith(("f", "F", "Freq", "freq")) or "Hz" in leaf:
            return getattr(self, f"ramanFreq{suffix}_MHz"), 'Hz'
        elif leaf.startswith(("ph", "Ph", "phase", "Phase")):
            return getattr(self, f"ramanPh2{suffix}_2pi"), '2pi'

        return getattr(self, f"ramanAmp{suffix}"), '?'

    def _apply_center_out(self, arr):
        n = len(arr)
        mid = n // 2
        indices = []
        left, right = mid - 1, mid
        while right < n or left >= 0:
            if right < n: indices.append(right); right += 1
            if left >= 0: indices.append(left); left -= 1
        return arr[np.array(indices)]

    def _discover_awg_dataset_keys(self) -> List[str]:
        """
        Dynamically discovers all dataset keys starting with 'AWG.ch' in ARTIQ.
        Catches custom dataset variables (fT, fDet, fBz, Vglo, Vrel, etc.) automatically.
        """
        discovered_keys = set()

        # 1. Inspect live ARTIQ dataset manager store if accessible
        if hasattr(self, "_dataset_mgr") and hasattr(self._dataset_mgr, "data"):
            for key in self._dataset_mgr.data.keys():
                if key.startswith("AWG.ch"):
                    discovered_keys.add(key)

        # 2. Comprehensive fallback set (defaults + common custom variables)
        ts = [f"T{i}" for i in range(10)]
        vs = [f"V{i}" for i in range(10)] + ["Vglo", "Vrel"]
        fs = [f"f{i}{j}" for i in range(10) for j in range(10)] + ["fT", "fDet", "fBz"]
        phs = [f"ph{i}" for i in range(10)]

        fallback_keys = [f"AWG.ch{ch}.{suffix}" for ch in range(1, 5) for suffix in (ts + vs + fs + phs)]
        discovered_keys.update(fallback_keys)

        return list(discovered_keys)

    def prepare(self):
        self.num_reps = int(self.get_dataset("Repetitions", default=100))

        # --- 1. Parse X Axis ---
        self.scan_var_x_list = [v.strip() for v in self.scan_variables_csv.split(',') if v.strip()]
        scannable_x, self.scan_units_x = self._parse_scannable(self.scan_var_x_list[0], is_y=False)
        self.scan_points_x = np.sort(np.array(list(scannable_x)))

        if type(scannable_x).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
            self.scan_points_x = self._apply_center_out(self.scan_points_x)

        # --- 2. Process 2D Logic and Unroll Grid ---
        self.awg_unrolled_array = []

        if self.enable_2D_scan:
            self.scan_var_y_list = [v.strip() for v in self.scan_variables_y_csv.split(',') if v.strip()]
            scannable_y, self.scan_units_y = self._parse_scannable(self.scan_var_y_list[0], is_y=True)
            self.scan_points_y = np.sort(np.array(list(scannable_y)))

            if type(scannable_y).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
                self.scan_points_y = self._apply_center_out(self.scan_points_y)

            # Create unrolled grid
            # x_grid, y_grid = np.meshgrid(self.scan_points_x, self.scan_points_y, indexing='ij')
            x_grid, y_grid = np.meshgrid(self.scan_points_x, self.scan_points_y, indexing='xy') # AM 2026/8/27
            flat_x, flat_y = x_grid.flatten(), y_grid.flatten()

            for x_val, y_val in zip(flat_x, flat_y):
                step_array = [x_val] * len(self.scan_var_x_list) + [y_val] * len(self.scan_var_y_list)
                self.awg_unrolled_array.append(step_array)

            self.master_scan_var_list = self.scan_var_x_list + self.scan_var_y_list
            self.num_pts = len(flat_x)
        else:
            # 1D fallback
            for x_val in self.scan_points_x:
                self.awg_unrolled_array.append([x_val] * len(self.scan_var_x_list))

            self.master_scan_var_list = self.scan_var_x_list
            self.num_pts = len(self.scan_points_x)
            self.scan_points_y = np.array([0.0])
            self.scan_units_y = ""

        # --- 3. Broadcast Datasets for ARTIQ Plotting ---
        self.set_dataset('AWG.Scan_Parameter.is_2D', self.enable_2D_scan, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.name', self.scan_variables_csv, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.array', self.scan_points_x, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.units', self.scan_units_x, broadcast=True, persist=True)

        self.set_dataset('AWG.Scan_Parameter.name_y', getattr(self, "scan_variables_y_csv", ""), broadcast=True,
                         persist=True)
        self.set_dataset('AWG.Scan_Parameter.array_y', self.scan_points_y, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.units_y', self.scan_units_y, broadcast=True, persist=True)

        self.set_dataset('AWG.Scan_Parameter.unrolled_grid', self.awg_unrolled_array, broadcast=True, persist=True)

        # --- 4. Fetch LIVE Globals (Dynamic Discovery) ---
        all_awg_keys = self._discover_awg_dataset_keys()

        # Include discovered keys PLUS any custom scanned variables
        global_keys = list(set(all_awg_keys + self.master_scan_var_list))
        static_keys = [key for key in global_keys if key not in self.master_scan_var_list]

        self.global_vars = self.get_awg_globals(static_keys)

        # Add placeholders for scanned variables so step evaluation succeeds
        for key in self.master_scan_var_list:
            self.global_vars[key] = 0.0

        # --- 5. T-Sum Logic (Determine Pulse Durations) ---
        relevant_T_vars = ["AWG.ch1.T0", "AWG.ch2.T0", "AWG.ch3.T0", "AWG.ch4.T0"]
        for var_name in self.master_scan_var_list:
            leaf = var_name.split(".")[-1]
            if leaf.startswith(("T", "t")) and var_name not in relevant_T_vars:
                relevant_T_vars.append(var_name)

        pulse_durations = []
        min_pulse_duration = 1.0 * us

        for step_vals in self.awg_unrolled_array:
            total_duration = 0.0
            step_dict = self.global_vars.copy()
            for i, var_name in enumerate(self.master_scan_var_list):
                step_dict[var_name] = step_vals[i]

            for t_var in relevant_T_vars:
                total_duration += step_dict.get(t_var, 0.0)

            if total_duration <= min_pulse_duration:
                total_duration = min_pulse_duration
            pulse_durations.append(total_duration)

        self.set_dataset('AWG.Scan_Parameter.pulse_durations', np.array(pulse_durations), broadcast=True, persist=True)

        # --- 6. Package info and Send Precomputation Request ---
        self.scan_info = {
            "scan_variables": self.master_scan_var_list,
            "scan_array": self.awg_unrolled_array,
            "num_reps": self.num_reps,
            "is_2d": self.enable_2D_scan
        }

        print(f"[ARTIQ] Targets: {self.master_scan_var_list}")
        print(f"[ARTIQ] Total Grid Points: {self.num_pts}")
        print("[ARTIQ] Sending PRECOMPUTE request to AWG Server...")

        print("\n[ARTIQ DEBUG] Static Globals fetched from Datasets:")
        for k, v in self.global_vars.items():
            print(f"   '{k}' = {v}")

        self.trigger_precomputation(self.scan_info, self.global_vars)

    def run(self):
        print("-" * 50)
        print("[ARTIQ] AWG Precomputation COMPLETE.")
        print("-" * 50)

    @rpc
    def get_awg_globals(self, global_keys: List[str]) -> Dict[str, float]:
        awg_vars = {}
        for key in global_keys:
            try:
                # Use default=None so non-existent keys are safely omitted
                val = self.get_dataset(key, default=None)
                if val is not None and isinstance(val, (int, float)):
                    awg_vars[key] = float(val)
            except Exception:
                pass
        return awg_vars

    @rpc
    def trigger_precomputation(self, scan_info, static_globals):
        payload = {"command": "PRECOMPUTE_WAVEFORMS", "scan_info": scan_info, "globals": static_globals}
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))
                resp = pyon.decode(s.recv(4096).decode())
                if resp.get("status") != "READY_FOR_PARAMS":
                    raise RuntimeError(f"Handshake Failed: {resp}")

                s.sendall(pyon.encode(payload).encode())

                resp = pyon.decode(s.recv(1024 * 1024).decode())
                if resp.get("status") != "PRECOMPUTATION_DONE":
                    # raise RuntimeError("Precomputation Failed")
                    raise RuntimeError(f"Precomputation Failed: {resp.get('message', resp)}") # to display actual error log
                # 2026/9/1 AM: for proper account of time in sequences
                self.set_dataset("AWG.ch1.FixedOffset", resp.get("ch1_fixed_offset", 0.0), broadcast=True, persist=True)

                print("[ARTIQ RPC] AWG confirmed: Waveforms Cached in Software.")
        except Exception as e:
            print(f"[ARTIQ RPC] Error in trigger_precomputation: {e}")
            raise