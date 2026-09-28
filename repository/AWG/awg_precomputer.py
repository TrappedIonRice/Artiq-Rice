

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
#         self.setattr_argument("enable_awg_scan", BooleanValue(True),
#                               tooltip="Uncheck when the AWG configuration is fixed this run (e.g. scanning allZ/endcapX), "
#                                       "so no AWG variable is wrongly excluded from the fixed-duration total.",
#                               group="X-Axis Scan")
#         self.setattr_argument("scan_variables_csv", StringValue("AWG.ch1.T0"),
#                               tooltip="Variable(s) for X-axis (e.g. AWG.ch1.T0, AWG.ch1.T_pulse)", group="X-Axis Scan")
#         self.setattr_argument("ramanTime_ms",
#                               Scannable(default=RangeScan(0.0, 0.001, 5), global_min=0.0 * ms, global_step=1e-5 * ms,
#                                         unit='ms', ndecimals=6), group="X-Axis Scan")
#         self.setattr_argument("ramanPh2_2pi",
#                               Scannable(NoScan(value=0.5), global_min=-100.0, global_max=100.0, global_step=1e-6, unit="",
#                                         ndecimals=6), group="X-Axis Scan")
#         self.setattr_argument("ramanFreq_MHz",
#                               Scannable(NoScan(value=100.0), global_min=-400.0 * MHz, global_max=400.0 * MHz,
#                                         global_step=1e-9 * MHz, unit="MHz", ndecimals=6), group="X-Axis Scan")
#         self.setattr_argument("ramanAmp",
#                               Scannable(NoScan(value=0.5), global_min=-1.0, global_max=1.0, global_step=1e-9, unit="",
#                                         ndecimals=6), group="X-Axis Scan")
#
#         # --- Y-Axis Targets ---
#         self.setattr_argument("scan_variables_y_csv", StringValue(""),
#                               tooltip="Variable(s) for Y-axis", group="Y-Axis Scan")
#         self.setattr_argument("ramanTime_y_ms",
#                               Scannable(default=RangeScan(0.0, 0.001, 5), global_min=0.0 * ms, global_step=1e-5 * ms,
#                                         unit='ms', ndecimals=6), group="Y-Axis Scan")
#         self.setattr_argument("ramanPh2_y_2pi",
#                               Scannable(NoScan(value=0.5), global_min=-100.0, global_max=100.0, global_step=1e-4, unit="",
#                                         ndecimals=6), group="Y-Axis Scan")
#         self.setattr_argument("ramanFreq_y_MHz",
#                               Scannable(NoScan(value=100.0), global_min=-400.0 * MHz, global_max=400.0 * MHz,
#                                         global_step=1e-9 * MHz, unit="MHz", ndecimals=6), group="Y-Axis Scan")
#         self.setattr_argument("ramanAmp_y",
#                               Scannable(NoScan(value=0.5), global_min=-1.0, global_max=1.0, global_step=1e-9, unit="",
#                                         ndecimals=6), group="Y-Axis Scan")
#
#     def _parse_scannable(self, scan_var_name, is_y=False):
#         """Helper to fetch active scannable based on variable leaf prefix"""
#         suffix = "_y" if is_y else ""
#         leaf = scan_var_name.split(".")[-1].strip()
#
#         if leaf.startswith(("T", "t")):
#             return getattr(self, f"ramanTime{suffix}_ms"), 's'
#         elif leaf.startswith(("V", "v", "Amp", "amp")):
#             return getattr(self, f"ramanAmp{suffix}"), 'V'
#         elif leaf.startswith(("f", "F", "Freq", "freq")) or "Hz" in leaf:
#             return getattr(self, f"ramanFreq{suffix}_MHz"), 'Hz'
#         elif leaf.startswith(("ph", "Ph", "phase", "Phase")):
#             return getattr(self, f"ramanPh2{suffix}_2pi"), '2pi'
#
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
#     def _discover_awg_dataset_keys(self) -> List[str]:
#         """
#         Dynamically discovers all dataset keys starting with 'AWG.ch' in ARTIQ.
#         Catches custom dataset variables (fT, fDet, fBz, Vglo, Vrel, etc.) automatically.
#         """
#         discovered_keys = set()
#
#         # 1. Inspect live ARTIQ dataset manager store if accessible
#         if hasattr(self, "_dataset_mgr") and hasattr(self._dataset_mgr, "data"):
#             for key in self._dataset_mgr.data.keys():
#                 if key.startswith("AWG.ch"):
#                     discovered_keys.add(key)
#
#         # 2. Comprehensive fallback set (defaults + common custom variables)
#         ts = [f"T{i}" for i in range(10)]
#         vs = [f"V{i}" for i in range(10)] + ["Vglo", "Vrel"]
#         fs = [f"f{i}{j}" for i in range(10) for j in range(10)] + ["fT", "fDet", "fBz", "fCar"]
#         phs = [f"ph{i}" for i in range(10)]
#
#         fallback_keys = [f"AWG.ch{ch}.{suffix}" for ch in range(1, 5) for suffix in (ts + vs + fs + phs)]
#         discovered_keys.update(fallback_keys)
#
#         return list(discovered_keys)
#
#     def prepare(self):
#         self.num_reps = int(self.get_dataset("Repetitions", default=100))
#
#         # --- 1. Parse X Axis ---
#         # self.scan_var_x_list = [v.strip() for v in self.scan_variables_csv.split(',') if v.strip()]
#         # scannable_x, self.scan_units_x = self._parse_scannable(self.scan_var_x_list[0], is_y=False)
#         # self.scan_points_x = np.sort(np.array(list(scannable_x)))
#         #
#         # if type(scannable_x).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
#         #     self.scan_points_x = self._apply_center_out(self.scan_points_x)
#         if self.enable_awg_scan:
#             self.scan_var_x_list = [v.strip() for v in self.scan_variables_csv.split(',') if v.strip()]
#             scannable_x, self.scan_units_x = self._parse_scannable(self.scan_var_x_list[0], is_y=False)
#             self.scan_points_x = np.sort(np.array(list(scannable_x)))
#             if type(scannable_x).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
#                 self.scan_points_x = self._apply_center_out(self.scan_points_x)
#         else:
#             self.scan_var_x_list = []
#             self.scan_points_x = np.array([0.0])
#             self.scan_units_x = ""
#
#         # --- 2. Process 2D Logic and Unroll Grid ---
#         self.awg_unrolled_array = []
#
#         if self.enable_2D_scan:
#             self.scan_var_y_list = [v.strip() for v in self.scan_variables_y_csv.split(',') if v.strip()]
#             scannable_y, self.scan_units_y = self._parse_scannable(self.scan_var_y_list[0], is_y=True)
#             self.scan_points_y = np.sort(np.array(list(scannable_y)))
#
#             if type(scannable_y).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
#                 self.scan_points_y = self._apply_center_out(self.scan_points_y)
#
#             # Create unrolled grid
#             # x_grid, y_grid = np.meshgrid(self.scan_points_x, self.scan_points_y, indexing='ij')
#             x_grid, y_grid = np.meshgrid(self.scan_points_x, self.scan_points_y, indexing='xy') # AM 2026/8/27
#             flat_x, flat_y = x_grid.flatten(), y_grid.flatten()
#
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
#             self.scan_points_y = np.array([0.0])
#             self.scan_units_y = ""
#
#         # --- 3. Broadcast Datasets for ARTIQ Plotting ---
#         self.set_dataset('AWG.Scan_Parameter.is_2D', self.enable_2D_scan, broadcast=True, persist=True)
#         # self.set_dataset('AWG.Scan_Parameter.name', self.scan_variables_csv, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.name',
#                          self.scan_variables_csv if self.enable_awg_scan else "",
#                          broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.array', self.scan_points_x, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.units', self.scan_units_x, broadcast=True, persist=True)
#
#         # self.set_dataset('AWG.Scan_Parameter.name_y', getattr(self, "scan_variables_y_csv", ""), broadcast=True,
#         #                  persist=True)
#         self.set_dataset('AWG.Scan_Parameter.name_y',
#                          (getattr(self, "scan_variables_y_csv", "") if self.enable_awg_scan else ""),
#                          broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.array_y', self.scan_points_y, broadcast=True, persist=True)
#         self.set_dataset('AWG.Scan_Parameter.units_y', self.scan_units_y, broadcast=True, persist=True)
#
#         self.set_dataset('AWG.Scan_Parameter.unrolled_grid', self.awg_unrolled_array, broadcast=True, persist=True)
#
#         # --- 4. Fetch LIVE Globals (Dynamic Discovery) ---
#         all_awg_keys = self._discover_awg_dataset_keys()
#
#         # Include discovered keys PLUS any custom scanned variables
#         global_keys = list(set(all_awg_keys + self.master_scan_var_list))
#         static_keys = [key for key in global_keys if key not in self.master_scan_var_list]
#
#         self.global_vars = self.get_awg_globals(static_keys)
#
#         # Add placeholders for scanned variables so step evaluation succeeds
#         for key in self.master_scan_var_list:
#             self.global_vars[key] = 0.0
#
#         # --- 5. T-Sum Logic (Determine Pulse Durations) ---
#         relevant_T_vars = ["AWG.ch1.T0", "AWG.ch2.T0", "AWG.ch3.T0", "AWG.ch4.T0"]
#         for var_name in self.master_scan_var_list:
#             leaf = var_name.split(".")[-1]
#             if leaf.startswith(("T", "t")) and var_name not in relevant_T_vars:
#                 relevant_T_vars.append(var_name)
#
#         pulse_durations = []
#         min_pulse_duration = 1.0 * us
#
#         for step_vals in self.awg_unrolled_array:
#             total_duration = 0.0
#             step_dict = self.global_vars.copy()
#             for i, var_name in enumerate(self.master_scan_var_list):
#                 step_dict[var_name] = step_vals[i]
#
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
#
#         print("\n[ARTIQ DEBUG] Static Globals fetched from Datasets:")
#         for k, v in self.global_vars.items():
#             print(f"   '{k}' = {v}")
#
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
#                 # Use default=None so non-existent keys are safely omitted
#                 val = self.get_dataset(key, default=None)
#                 if val is not None and isinstance(val, (int, float)):
#                     awg_vars[key] = float(val)
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
#                 if resp.get("status") != "READY_FOR_PARAMS":
#                     raise RuntimeError(f"Handshake Failed: {resp}")
#
#                 s.sendall(pyon.encode(payload).encode())
#
#                 resp = pyon.decode(s.recv(1024 * 1024).decode())
#                 if resp.get("status") != "PRECOMPUTATION_DONE":
#                     # raise RuntimeError("Precomputation Failed")
#                     raise RuntimeError(f"Precomputation Failed: {resp.get('message', resp)}") # to display actual error log
#                 # 2026/9/1 AM: for proper account of time in sequences
#                 self.set_dataset("AWG.ch1.FixedOffset", resp.get("ch1_fixed_offset", 0.0), broadcast=True, persist=True)
#
#                 print("[ARTIQ RPC] AWG confirmed: Waveforms Cached in Software.")
#         except Exception as e:
#             print(f"[ARTIQ RPC] Error in trigger_precomputation: {e}")
#             raise



# 26/09/14 gt: to integrate arbitrary names of variables
import re
import numpy as np
from artiq.experiment import *
from sipyco import pyon
import socket
from typing import Dict, List, Tuple

HOST = "127.0.0.1"
PORT = 5000


class awgPrecomputer(EnvExperiment):
    """
    AWG Precomputer
    Generates scan arrays, handles multi-channel scanning, autodetects arbitrary
    variable names directly from ARTIQ's master DDB, and sends alias-mapped globals to the AWG server.
    """

    def build(self):
        self.setattr_device("core")

        # --- Scan Setup ---
        self.setattr_argument("enable_2D_scan", BooleanValue(False), group="Scan Setup")
        self.setattr_argument("CenterScanMode", EnumerationValue(['Linear Center', 'Center Out']), group="Scan Setup")

        # --- X-Axis Targets ---
        self.setattr_argument("enable_awg_scan", BooleanValue(True),
                              tooltip="Uncheck when the AWG configuration is fixed this run.",
                              group="X-Axis Scan")
        self.setattr_argument("scan_variables_csv", StringValue("AWG.ch1.T0"),
                              tooltip="Variable(s) for X-axis (e.g. AWG.ch1.Tgate, AWG.ch2.fRsb)", group="X-Axis Scan")
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
                              Scannable(NoScan(value=0.5), global_min=-1.0, global_max=1.0, global_step=1e-9, unit="",
                                        ndecimals=6), group="X-Axis Scan")

        # --- Y-Axis Targets ---
        self.setattr_argument("scan_variables_y_csv", StringValue(""), tooltip="Variable(s) for Y-axis", group="Y-Axis Scan")
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
                              Scannable(NoScan(value=0.5), global_min=-1.0, global_max=1.0, global_step=1e-9, unit="",
                                        ndecimals=6), group="Y-Axis Scan")

    # def _resolve_awg_var_info(self, dataset_name: str) -> Tuple[str, str, str]:
    #     """Extracts channel, base name, and type from any dot/underscore AWG variable."""
    #     m = re.search(r"AWG[\._]ch([1-4])[\._](\w+)", dataset_name, re.IGNORECASE)
    #     if not m:
    #         return "1", dataset_name, "unknown"
    #
    #     channel, base_name = m.group(1), m.group(2)
    #     b_low = base_name.lower()
    #
    #     if b_low.startswith('t'):
    #         var_type = 'time'
    #     elif b_low.startswith(('v', 'amp')):
    #         var_type = 'voltage'
    #     elif b_low.startswith('f') or 'freq' in b_low:
    #         var_type = 'frequency'
    #     elif b_low.startswith('ph'):
    #         var_type = 'phase'
    #     else:
    #         var_type = 'unknown'
    #
    #     return channel, base_name, var_type

    #26/09/14 gt
    def _resolve_awg_var_info(self, dataset_name: str) -> Tuple[str, str, str]:
        # Requires channel (e.g. ch1 or AWG.ch1) but allows any number and custom name
        m = re.search(r"(?:AWG[\._])?ch(\d+)[\._]([a-zA-Z0-9_]+)", dataset_name, re.IGNORECASE)
        if not m:
            return "1", dataset_name, "unknown"

        channel, base_name = m.group(1), m.group(2)
        b_low = base_name.lower()

        if b_low.startswith('t'): var_type = 'time'
        elif b_low.startswith(('v', 'amp')): var_type = 'voltage'
        elif b_low.startswith('f') or 'freq' in b_low: var_type = 'frequency'
        elif b_low.startswith('ph'): var_type = 'phase'
        else: var_type = 'unknown'

        return channel, base_name, var_type

    def _parse_scannable(self, scan_var_name: str, is_y: bool = False):
        suffix = "_y" if is_y else ""
        _, _, var_type = self._resolve_awg_var_info(scan_var_name)

        if var_type == 'time':
            return getattr(self, f"ramanTime{suffix}_ms"), 's'
        elif var_type == 'voltage':
            return getattr(self, f"ramanAmp{suffix}"), 'V'
        elif var_type == 'frequency':
            return getattr(self, f"ramanFreq{suffix}_MHz"), 'Hz'
        elif var_type == 'phase':
            return getattr(self, f"ramanPh2{suffix}_2pi"), '2pi'

        return getattr(self, f"ramanAmp{suffix}"), '?'

    def _apply_center_out(self, arr: np.ndarray) -> np.ndarray:
        n = len(arr)
        mid = n // 2
        indices = []
        left, right = mid - 1, mid
        while right < n or left >= 0:
            if right < n:
                indices.append(right)
                right += 1
            if left >= 0:
                indices.append(left)
                left -= 1
        return arr[np.array(indices)]

    # def _discover_awg_dataset_keys(self) -> List[str]:
    #     """Queries ARTIQ's master DatasetDB directly for all registered AWG keys."""
    #     keys = set(getattr(self, "master_scan_var_list", []))
    #     try:
    #         ddb_data = self._dataset_mgr.ddb.get_data()
    #         keys.update(k for k in ddb_data if re.match(r"^AWG[\._]ch[1-4][\._]\w+$", k, re.IGNORECASE))
    #     except Exception:
    #         pass
    #     return list(keys)

    #26/09/14 gt
    # 26/09/14 gt - FIXED to include live memory
    # def _discover_awg_dataset_keys(self) -> List[str]:
    #     keys = set(getattr(self, "master_scan_var_list", []))
    #
    #     # Helper to search any dataset dictionary with our flexible regex
    #     def search_dict(d):
    #         if not isinstance(d, dict): return
    #         for k in d.keys():
    #             if isinstance(k, str) and re.search(r"(?:AWG[\._])?ch\d+[\._][a-zA-Z0-9_]+", k, re.IGNORECASE):
    #                 keys.add(k)
    #
    #     try:
    #         # 1. Search persistent on-disk database
    #         if hasattr(self._dataset_mgr, "ddb"):
    #             search_dict(self._dataset_mgr.ddb.get_data())
    #
    #         # 2. Search ACTIVE live in-memory datasets (This catches your new variables!)
    #         if hasattr(self._dataset_mgr, "data"):
    #             search_dict(self._dataset_mgr.data)
    #
    #         # 3. Search local dataset overrides (just in case)
    #         if hasattr(self._dataset_mgr, "local"):
    #             search_dict(self._dataset_mgr.local)
    #
    #     except Exception as e:
    #         print(f"[AWG Precomputer] Warning finding datasets: {e}")
    #
    #     return list(keys)

    def _discover_awg_dataset_keys(self) -> List[str]:
        """
        Generates candidate AWG dataset keys to query from ARTIQ Master over IPC.
        Reads standard fallback arrays AND the dynamic registry maintained by SetDataset.
        """
        discovered_keys = set()

        # 1. Standard indexed variables (the defaults)
        ts = [f"T{i}" for i in range(10)]
        vs = [f"V{i}" for i in range(10)]
        fs = [f"f{i}{j}" for i in range(10) for j in range(10)]
        phs = [f"ph{i}" for i in range(10)]

        fallback_keys = [f"AWG.ch{ch}.{suffix}" for ch in range(1, 5) for suffix in (ts + vs + fs + phs)]
        discovered_keys.update(fallback_keys)

        # 2. Fetch the dynamic registry created by SetDataset!
        try:
            custom_registry = self.get_dataset("AWG.Custom_Variables")
            if isinstance(custom_registry, list):
                discovered_keys.update(custom_registry)
        except Exception:
            pass  # Registry doesn't exist yet, safely ignore

        return list(discovered_keys)

    # def _format_aliases(self, key: str, val: float) -> Dict[str, float]:
    #     """Maps values across dot, underscore, and bare channel formats (e.g. ch1_fHarr)."""
    #     aliases = {key: val}
    #     m = re.search(r"AWG[\._]ch([1-4])[\._](\w+)", key, re.IGNORECASE)
    #     if m:
    #         ch, name = m.group(1), m.group(2)
    #         aliases[f"AWG.ch{ch}.{name}"] = val
    #         aliases[f"AWG_ch{ch}_{name}"] = val
    #         aliases[f"ch{ch}_{name}"] = val
    #     return aliases

    #26/09/14 gt
    def _format_aliases(self, key: str, val: float) -> Dict[str, float]:
        aliases = {key: val}
        m = re.search(r"(?:AWG[\._])?ch(\d+)[\._]([a-zA-Z0-9_]+)", key, re.IGNORECASE)
        if m:
            ch, name = m.group(1), m.group(2)
            aliases[f"AWG.ch{ch}.{name}"] = val
            aliases[f"AWG_ch{ch}_{name}"] = val
            aliases[f"ch{ch}_{name}"] = val
        return aliases

    def prepare(self):
        self.num_reps = int(self.get_dataset("Repetitions", default=100))

        # --- 1. Parse X Axis Target(s) ---
        if self.enable_awg_scan:
            self.scan_var_x_list = [v.strip() for v in self.scan_variables_csv.split(',') if v.strip()]
            scannable_x, self.scan_units_x = self._parse_scannable(self.scan_var_x_list[0], is_y=False)
            self.scan_points_x = np.sort(np.array(list(scannable_x)))
            if type(scannable_x).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
                self.scan_points_x = self._apply_center_out(self.scan_points_x)
        else:
            self.scan_var_x_list = []
            self.scan_points_x = np.array([0.0])
            self.scan_units_x = ""

        # --- 2. Parse Y Axis Target(s) and Build Grid ---
        self.awg_unrolled_array = []

        if self.enable_2D_scan:
            self.scan_var_y_list = [v.strip() for v in self.scan_variables_y_csv.split(',') if v.strip()]
            scannable_y, self.scan_units_y = self._parse_scannable(self.scan_var_y_list[0], is_y=True)
            self.scan_points_y = np.sort(np.array(list(scannable_y)))

            if type(scannable_y).__name__ == "CenterScan" and self.CenterScanMode == "Center Out":
                self.scan_points_y = self._apply_center_out(self.scan_points_y)

            x_grid, y_grid = np.meshgrid(self.scan_points_x, self.scan_points_y, indexing='xy')
            flat_x, flat_y = x_grid.flatten(), y_grid.flatten()

            for x_val, y_val in zip(flat_x, flat_y):
                step_array = [x_val] * len(self.scan_var_x_list) + [y_val] * len(self.scan_var_y_list)
                self.awg_unrolled_array.append(step_array)

            self.master_scan_var_list = self.scan_var_x_list + self.scan_var_y_list
            self.num_pts = len(flat_x)
        else:
            for x_val in self.scan_points_x:
                self.awg_unrolled_array.append([x_val] * len(self.scan_var_x_list))

            self.master_scan_var_list = self.scan_var_x_list
            self.num_pts = len(self.scan_points_x)
            self.scan_points_y = np.array([0.0])
            self.scan_units_y = ""

        # --- 3. Broadcast Parameters to ARTIQ Applets ---
        self.set_dataset('AWG.Scan_Parameter.is_2D', self.enable_2D_scan, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.name',
                         self.scan_variables_csv if self.enable_awg_scan else "",
                         broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.array', self.scan_points_x, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.units', self.scan_units_x, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.name_y',
                         (getattr(self, "scan_variables_y_csv", "") if self.enable_awg_scan else ""),
                         broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.array_y', self.scan_points_y, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.units_y', self.scan_units_y, broadcast=True, persist=True)
        self.set_dataset('AWG.Scan_Parameter.unrolled_grid', self.awg_unrolled_array, broadcast=True, persist=True)

        # --- 4. Fetch Live Static Globals ---
        all_awg_keys = self._discover_awg_dataset_keys()
        global_keys = list(set(all_awg_keys + self.master_scan_var_list))
        static_keys = [key for key in global_keys if key not in self.master_scan_var_list]

        self.global_vars = self.get_awg_globals(static_keys)

        for key in self.master_scan_var_list:
            self.global_vars.update(self._format_aliases(key, 0.0))

        # --- 5. Dynamic Time Summation ---
        relevant_T_vars = [key for key in global_keys if self._resolve_awg_var_info(key)[2] == 'time']
        pulse_durations = []
        min_pulse_duration = 1.0 * us

        for step_vals in self.awg_unrolled_array:
            step_dict = self.global_vars.copy()
            for i, var_name in enumerate(self.master_scan_var_list):
                step_dict.update(self._format_aliases(var_name, step_vals[i]))

            total_duration = sum(step_dict.get(t_var, 0.0) for t_var in relevant_T_vars)
            pulse_durations.append(max(total_duration, min_pulse_duration))

        self.set_dataset('AWG.Scan_Parameter.pulse_durations', np.array(pulse_durations), broadcast=True, persist=True)

        # --- 6. Precomputation Request ---
        self.scan_info = {
            "scan_variables": self.master_scan_var_list,
            "scan_array": self.awg_unrolled_array,
            "num_reps": self.num_reps,
            "is_2d": self.enable_2D_scan
        }

        print(f"[ARTIQ] Targets: {self.master_scan_var_list}")
        print(f"[ARTIQ] Total Grid Points: {self.num_pts}")
        print("[ARTIQ] Sending PRECOMPUTE request to AWG Server...")

        self.trigger_precomputation(self.scan_info, self.global_vars)

    def run(self):
        print("-" * 50)
        print("[ARTIQ] AWG Precomputation COMPLETE.")
        print("-" * 50)

    # def get_awg_globals(self, global_keys: List[str]) -> Dict[str, float]:
    #     """Fetches static dataset values and formats all key aliases in one step."""
    #     awg_vars = {}
    #     for key in global_keys:
    #         val = self.get_dataset(key, default=None)
    #         if val is not None and isinstance(val, (int, float, np.number)):
    #             awg_vars.update(self._format_aliases(key, float(val)))
    #     return awg_vars

    #26/09/14 gt
    # def get_awg_globals(self, global_keys: List[str]) -> Dict[str, float]:
    #     awg_vars = {}
    #     print("\n[ARTIQ DEBUG] --- Fetching Datasets ---")
    #     for key in global_keys:
    #         try:
    #             val = self.get_dataset(key, default=None)
    #             print(f"[ARTIQ DEBUG] > Key: '{key}' | Value: {val} | Type: {type(val)}")
    #
    #             # If val fails this check, it gets skipped and defaults to 0 on the server!
    #             if val is not None and isinstance(val, (int, float, np.number)):
    #                 awg_vars.update(self._format_aliases(key, float(val)))
    #             elif val is not None:
    #                 print(f"[ARTIQ DEBUG]   ! Ignored '{key}' because type {type(val)} is not a float/int.")
    #         except Exception as e:
    #             print(f"[ARTIQ DEBUG]   ! Error getting '{key}': {e}")
    #
    #     return awg_vars

    #26/09/14 gt: debugging
    # def get_awg_globals(self, global_keys: List[str]) -> Dict[str, float]:
    #     awg_vars = {}
    #     for key in global_keys:
    #         val = self.get_dataset(key, default=None)
    #
    #         # ---> ADD THIS PRINT HERE <---
    #         if "fCar" in key:  # Replace fDet with your new custom name!
    #             print(f"[DEBUG] Found {key} in dataset! Value: {val}")
    #
    #         if val is not None and isinstance(val, (int, float, np.number)):
    #             awg_vars.update(self._format_aliases(key, float(val)))
    #     return awg_vars

    def get_awg_globals(self, global_keys: List[str]) -> Dict[str, float]:
        awg_vars = {}
        print("\n" + "=" * 40)
        print("[AWG Precomputer] EXTRACTING VARIABLES")
        print("=" * 40)

        for key in global_keys:
            try:
                # Get the raw value from the dataset manager
                val = self.get_dataset(key, default=None)

                # Check if this is one of our custom variables (e.g., fDet, fCar, etc.)
                is_custom = "f" in key or "T" in key or "v" in key

                if is_custom:
                    print(f"Found Key: '{key}'")
                    print(f"Raw Value: {val} (Type: {type(val)})")

                if val is not None and isinstance(val, (int, float, np.number)):
                    aliases = self._format_aliases(key, float(val))
                    if is_custom:
                        print(f"Created Aliases: {aliases}")
                    awg_vars.update(aliases)
                elif val is not None:
                    print(f"REJECTED '{key}': Value {val} is type {type(val)}, not float/int!")
            except Exception as e:
                print(f"ERROR reading '{key}': {e}")

        # CRITICAL CHECK: Are we overwriting it to zero because it's being scanned?
        for key in getattr(self, "master_scan_var_list", []):
            if "f" in key or "T" in key or "v" in key:
                print(f"OVERWRITING '{key}' to 0.0 because it is in the scan list!")
                awg_vars.update(self._format_aliases(key, 0.0))

        print("=" * 40 + "\n")
        return awg_vars

    def trigger_precomputation(self, scan_info: dict, static_globals: dict):
        """Host-side TCP socket handler."""
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
                    raise RuntimeError(f"Precomputation Failed: {resp.get('message', resp)}")

                self.set_dataset("AWG.ch1.FixedOffset", resp.get("ch1_fixed_offset", 0.0), broadcast=True, persist=True)
                print("[ARTIQ] AWG confirmed: Waveforms Cached in Software.")
        except Exception as e:
            print(f"[ARTIQ] Error in trigger_precomputation: {e}")
            raise