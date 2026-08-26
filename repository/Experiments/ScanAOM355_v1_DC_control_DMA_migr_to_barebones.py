

from artiq.experiment import *
import numpy as np
from oitg.errorbars import binom_onesided
from matplotlib import pyplot as plt
import json
import socket
import re
from sipyco import pyon
import inspect
import time

class BarebonesArtiqScanV1(EnvExperiment):
    # 26/01/12 gt: shortened build
    def build(self):
        self.setattr_device("core")
        self.setattr_device("core_dma")
        self.setattr_device("ccb")
        self.setattr_device("scheduler")

        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("urukul0_ch3")

        self.setattr_device("zotino0") # to switch from DDS (+5 V) to AWG (0 V)

        self.setattr_device("urukul1_cpld")  # Necessary for clock sync
        self.setattr_device("urukul1_ch0")
        self.setattr_device("urukul1_ch1")  # OP
        self.setattr_device("urukul1_ch2")  # MW
        self.setattr_device("urukul1_ch3")  # 369 protection beam

        self.setattr_device("urukul2_cpld")  # Necessary for clock sync
        self.setattr_device("urukul2_ch0")  # Raman 1 ch1
        self.setattr_device("urukul2_ch1")  # Raman 1 ch2
        self.setattr_device("urukul2_ch2")  # RR lock
        self.setattr_device("urukul2_ch3")  # ULE369

        self.setattr_device("ttl4")  # Camera Trigger
        self.setattr_device("ttl5")  # AWG trigger
        self.setattr_device("ttl6")  # Raman 2 shutter

        self.histpoints = np.zeros(self.get_dataset("Repetitions"), dtype=int)

        self.setattr_device("ttl0_counter")  # line trigger sync

        ttl_params = ["ttl1_counter"]
        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl1_counter"))
        self.setattr_device(str(self.INPUT_TTL))  # must typecast or NoneType error when recomputing args
        self.ttl = self.get_device(self.INPUT_TTL)

        self.sum_rising_edges = 0.0
        self.sum_rising_edges_cooling = 0.0
        self.points = [[0.0] * self.get_dataset("Repetitions"), [0.0] * self.get_dataset("Repetitions")]

        self.gate_end_mu = np.int64(0)  # necessary or type error when assigning new val
        self.mean_rising_edges = 0.0
        self.channel_num = [1]  # Doppler, Det, OP

        # --------------------------------------------#
        # Electrode config
        self.originalDCElectrodeValues = self.get_dataset("DC.ElectrodeValues")
        self.modDCElectrodeValues = self.get_dataset("DC.ElectrodeValues")  # to be modified
        self.DCElectrodeMapping = self.get_dataset("DC.ElectrodeMapping")
        self.originalEndcapX = self.get_dataset("Experiment_config.endcapX")
        self.originalAllY = self.get_dataset("Experiment_config.all_y")
        self.originalAllZ = self.get_dataset("Experiment_config.all_z")
        # -------------------------------------------#

        # -------------------------------------------#
        # Experiment parameters setup
        # setting defaults
        self.extract_dataset_defaults()

        # Initialize lists
        # (Auto-handled by add_scannable, but initialized here for clarity)
        self.scannable_names = []
        self.scannable_units = {}

        # Obtaining user-input parameters from GUI

        def add_scannable(name, argument, group=None, tooltip=None):
            """
            Smart wrapper for setattr_argument.
            1. Calls standard ARTIQ setattr_argument.
            2. Auto-populates self.scannable_names.
            3. Auto-populates self.scannable_units.
            """
            # --- Init Storage ---
            if not hasattr(self, "scannable_names"):
                self.scannable_names = []
            if not hasattr(self, "scannable_units"):
                self.scannable_units = {}

            # --- 1. Capture the Unit ---
            # We look at the 'argument' object BEFORE ARTIQ strips it down.
            # BooleanValue has no unit, Scannable/NumberValue do.
            unit = getattr(argument, "unit", "")
            self.scannable_units[name] = unit

            # --- 2. Update List ---
            if name not in self.scannable_names:
                self.scannable_names.append(name)

            # --- 3. Call Actual ARTIQ Method ---
            self.setattr_argument(name, argument, group=group, tooltip=tooltip)

        # ---------SBC---------#
        self.setattr_argument("SBCcheck", BooleanValue(default=self.default_SBCcheck), group='SBC')

        add_scannable("SBCFrequency355_1",
                           Scannable(NoScan(value=self.default_SBCFrequency355_1),
                                     global_min=0.0, global_max=250.0 * MHz, global_step=1.0e-9 * MHz,
                                     unit="MHz", ndecimals=7), group='SBC')

        add_scannable("SBCAmplitude355_1",
                           Scannable(NoScan(value=self.default_SBCAmplitude355_1),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='SBC')

        add_scannable("SBCFrequency355_2",
                           Scannable(NoScan(value=self.default_SBCFrequency355_2),
                                     global_min=0.0 * MHz, global_max=250.0 * MHz, global_step=1.0e-9 * MHz,
                                     unit="MHz", ndecimals=7), group='SBC')

        add_scannable("SBCAmplitude355_2",
                           Scannable(NoScan(value=self.default_SBCAmplitude355_2),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='SBC')

        add_scannable("SBCTime",
                           Scannable(NoScan(value=self.default_SBCtime),
                                     global_min=0.00001 * ms, global_step=1.0e-9 * ms,
                                     unit="ms", ndecimals=4), group='SBC')

        add_scannable("SBCAmplitude935",
                           Scannable(NoScan(value=0.00500),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='SBC')
        # ---------------------#

        # --------935---------#
        add_scannable("ClearoutPower935",
                           Scannable(NoScan(value=0.01),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='935Clearout')

        add_scannable("ClearoutTime935",
                           Scannable(NoScan(value=0.05 * ms),
                                     global_min=0.00001 * ms, global_step=1.0e-9 * ms,
                                     unit="ms", ndecimals=4), group='935Clearout')
        # ---------------------#

        # ----------OP---------#
        self.setattr_argument("StatePrepOP", BooleanValue(default=True), group='OP')

        add_scannable("prepfreqOP",
                           Scannable(NoScan(value=self.default_prepfreqOP),
                                     global_min=0.0 * MHz, global_max=250.0 * MHz, global_step=1.0e-9 * MHz,
                                     unit="MHz", ndecimals=7), group='OP')

        add_scannable("prepampOP",
                           Scannable(NoScan(value=self.default_prepampOP),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='OP')

        add_scannable("preptimeOP",
                           Scannable(NoScan(value=self.default_preptimeOP),
                                     global_min=0.00001 * ms,
                                     global_step=1.0e-9 * ms,
                                     unit="ms", ndecimals=4), group='OP')
        # --------------------#

        # ---------435-----------#
        self.setattr_argument("StatePrep", BooleanValue(default=False), group='435')

        add_scannable("prepfreq435",
                           Scannable(NoScan(value=234.1743 * MHz),
                                     global_min=0.0 * MHz, global_max=300.0 * MHz,
                                     global_step=1.0e-9 * MHz,
                                     unit="MHz", ndecimals=7), group='435')

        add_scannable("preptime",
                           Scannable(NoScan(value=2.0 * ms),
                                     global_min=0.00001 * ms,
                                     global_step=1.0e-9 * ms,
                                     unit="ms", ndecimals=4), group='435')

        add_scannable("choice435channel_1_2",
                           Scannable(NoScan(value=1),
                                     global_min=1, global_max=2,
                                     global_step=1,
                                     unit=""), group='435')

        add_scannable("Frequency435",
                           Scannable(NoScan(value=243.2854 * MHz),
                                     global_min=0.0 * MHz, global_max=300.0 * MHz,
                                     global_step=1.0e-9 * MHz,
                                     unit="MHz", ndecimals=7), group='435')

        add_scannable("Amplitude435",
                           Scannable(NoScan(value=0.0),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='435')

        add_scannable("Time435",
                           Scannable(NoScan(value=0.01 * us),
                                     global_min=0.00001 * ms,
                                     global_step=1.0e-9 * ms,
                                     unit="ms", ndecimals=4), group='435')
        # ---------------------#

        # ------Ramsey----------#
        self.setattr_argument("Ramseycheck", BooleanValue(default=False), group='Ramsey')

        add_scannable("WaitTime",
                           Scannable(NoScan(value=0.00001 * ms),
                                     global_min=0.00001 * ms,
                                     global_step=1.0e-9 * ms,
                                     unit="ms", ndecimals=4), group='Ramsey')

        add_scannable("Phase1",
                           Scannable(NoScan(value=0.0),
                                     global_min=-2 * np.pi, global_max=2 * np.pi,
                                     global_step=1.0e-9,
                                     unit="", ndecimals=3), group='Ramsey')

        add_scannable("Phase2",
                           Scannable(NoScan(value=0.0),
                                     global_min=-2 * np.pi, global_max=2 * np.pi,
                                     global_step=1.0e-9,
                                     unit="", ndecimals=3), group='Ramsey')
        # ---------------------#

        # ---------MW----------#
        add_scannable("FrequencyMW",
                           Scannable(NoScan(value=self.default_MWFrequency),
                                     global_min=0.0 * MHz, global_max=200.0 * MHz,
                                     global_step=1.0e-9 * MHz,
                                     unit="MHz", ndecimals=7), group='MW')

        add_scannable("TimeMW",
                           Scannable(NoScan(value=self.default_MWTime),
                                     global_min=0.00001 * ms,
                                     global_step=1.0e-9 * ms,
                                     unit="ms", ndecimals=4),group='MW')

        add_scannable("AmplitudeMW",
                           Scannable(NoScan(value=self.default_MWAmp),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='MW')
        # --------------------#

        # ------Raman---------#
        self.setattr_argument('EnableAWG', BooleanValue(default=False), group='Raman')
        self.setattr_argument("AWG_Mode", EnumerationValue(["preload", "live"], default="preload"),
                              group="Raman")

        add_scannable("Frequency355_Raman1",
                           Scannable(NoScan(value=self.default_Raman1_freq),
                                     global_min=100.0 * MHz, global_max=250.0 * MHz,
                                     global_step=1.0e-9 * MHz, unit="MHz", ndecimals=7), group='Raman')

        add_scannable("Amplitude355_Raman1",
                           Scannable(NoScan(value=self.default_Raman1_amp),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='Raman')

        add_scannable("Frequency355_Raman2",
                           Scannable(NoScan(value=self.default_Raman1_ch2_freq),
                                     global_min=100.0 * MHz, global_max=250.0 * MHz,
                                     global_step=1.0e-9 * MHz, unit="MHz", ndecimals=7), group='Raman')

        add_scannable("Amplitude355_Raman2",
                           Scannable(NoScan(value=self.default_Raman1_ch2_amp),
                                     global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                     unit="", ndecimals=3), group='Raman')

        add_scannable("RamanTime",
                           Scannable(NoScan(value=self.default_Raman_time),
                                     global_min=0.00001 * ms,
                                     global_step=1.0e-9 * ms, unit="ms", ndecimals=6), group='Raman')

        self.setattr_argument("checkLighShiftRSB_calib", BooleanValue(default=False), group='Raman')

        add_scannable("LighShiftFactor_BSB",
                           Scannable(NoScan(value=1.0), global_min=0.0, global_max=2.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Raman')

        add_scannable("GlobalSidebandAmpScale",
                           Scannable(NoScan(value=1.0), global_min=0.0, global_max=2.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Raman')

        add_scannable("Bz",
                           Scannable(NoScan(value=0.0 * kHz), global_min=-50.0 * kHz, global_max=50 * kHz,
                                     global_step=1.0e-9 * kHz, unit="kHz", ndecimals=3), group='Raman')
        # ---------------------#

        # -----Raman Piezos---#
        add_scannable("piezoR1H",
                           Scannable(NoScan(value=self.default_PiezoR1H), global_min=0.0, global_max=10.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Raman Piezos')

        add_scannable("piezoR1V",
                           Scannable(NoScan(value=self.default_PiezoR1V), global_min=0.0, global_max=10.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Raman Piezos')

        add_scannable("piezoR2H",
                           Scannable(NoScan(value=self.default_PiezoR2H), global_min=0.0, global_max=10.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Raman Piezos')

        add_scannable("piezoR2V",
                           Scannable(NoScan(value=self.default_PiezoR2V), global_min=0.0, global_max=10.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Raman Piezos')
        # ------------------#

        # -----Electrodes------#
        self.setattr_argument("checkAllZ_calib", BooleanValue(default=False), group='Electrodes')
        self.setattr_argument("AllZ_calib_start", NumberValue(0.0, unit = '', min = -0.3, max = 0.3, step = 0.001),
                              group='Electrodes')

        add_scannable("allZ",
                           Scannable(NoScan(value=self.default_allZ), global_min=-9.0, global_max=9.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Electrodes')

        add_scannable("endcapX",
                           Scannable(NoScan(value=self.default_endcapX), global_min=-9.0, global_max=9.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Electrodes')

        add_scannable("allY",
                           Scannable(NoScan(value=self.default_allY), global_min=-9.0, global_max=9.0,
                                     global_step=1.0e-9, unit="", ndecimals=3), group='Electrodes')
        # ---------------------#

        # -----Detection-------#
        self.setattr_argument("checkCameraDetection", BooleanValue(default=False), group='Detection')
        self.setattr_argument("checkGlobalCoolingShot", BooleanValue(default=False), group='Detection')
        self.setattr_argument("CheckThresholding", BooleanValue(default=self.default_ThresholdCheck), group='Detection')
        self.setattr_argument("checkLineTrigger", BooleanValue(default=False), group='Detection')
        add_scannable("DetTime369", Scannable(NoScan(value=self.default_detectionTime), global_min=0.00001 * ms,
                                     global_step=1.0e-9 * ms, unit="ms", ndecimals=4), group='Detection')
        # ---------------------#

        self.t_step_durations = []
        self.t_init_roundtrip = 0.0
        self.t_total_scan = 0.0

    def extract_dataset_defaults(self):
        self.default_SBCcheck = bool(self.get_dataset("SBC.Check"))
        self.default_SBCFrequency355_1 = self.get_dataset("SBC.tone1.Frequency")
        self.default_SBCAmplitude355_1 = self.get_dataset("SBC.tone1.Amplitude")
        self.default_SBCFrequency355_2 = self.get_dataset("SBC.tone2.Frequency")
        self.default_SBCAmplitude355_2 = self.get_dataset("SBC.tone2.Amplitude")
        self.default_SBCtime = self.get_dataset("SBC.tone1.Time(ms)") * ms
        self.default_prepfreqOP = self.get_dataset("OP.Frequency")
        self.default_prepampOP = self.get_dataset("OP.Amp")
        self.default_preptimeOP = self.get_dataset("OP.Time(ms)") * ms
        self.default_MWFrequency = self.get_dataset("MW.Frequency")
        self.default_MWAmp = self.get_dataset("MW.Amp")
        self.default_MWTime = self.get_dataset("MW.Time(ms)") * ms
        self.default_Raman1_freq = self.get_dataset("355_Raman1.Frequency")
        self.default_Raman1_amp = self.get_dataset("355_Raman1.Amp")
        self.default_Raman_time = self.get_dataset("355_Raman1.Time(ms)") * ms
        self.default_Raman1_ch2_freq = self.get_dataset("355_Raman1_ch2.Frequency")
        self.default_Raman1_ch2_amp = self.get_dataset("355_Raman1_ch2.Amp")
        self.default_ThresholdCheck = bool(self.get_dataset("PMTCheckThreshold"))
        self.default_detectionTime = self.get_dataset("Detection.Time(ms)") * ms
        self.default_endcapX = self.get_dataset("Experiment_config.endcapX")
        self.default_allY = self.get_dataset("Experiment_config.all_y")
        self.default_allZ = self.get_dataset("Experiment_config.all_z")
        self.default_PiezoR1H = self.get_dataset("355_Raman1.H1")
        self.default_PiezoR1V = self.get_dataset("355_Raman1.V1")
        self.default_PiezoR2H = self.get_dataset("355_Raman2.H2")
        self.default_PiezoR2V = self.get_dataset("355_Raman2.V2")

    # 26/01/12 gt: shortened prepare() to accomodate the unit assignment in build
    def prepare(self):
        # ---------------- Basic Init ----------------
        self.num_repeat = self.get_dataset("Repetitions")
        self.histpoints = np.zeros(self.num_repeat, dtype=int)
        self.points = [[0.0] * self.num_repeat, [0.0] * self.num_repeat]
        self.PMTThreshold = self.get_dataset("PMTThreshold")
        self.scanHistogramList = []
        # self.scanHistogramList = np.array([np.zeros(self.num_repeat, dtype=int)])


        self.iter = 0
        self.modSBCtime = 0.0
        self.modpreptime = 0.0
        self.PiBy2Time435_1mod = 0.0
        self.PiBy2Time435_2mod = 0.0

        # ---------------- Helper ----------------
        # Helper to safely extract numeric value from Datasets or Scannables
        def numeric(x):
            if hasattr(x, "get"): return x.get()
            if hasattr(x, "value"): return x.value
            return float(x)

        # ---------------- Static Datasets ----------------
        self.doppler_freq = numeric(self.get_dataset("Doppler.Frequency"))
        self.doppler_amp = numeric(self.get_dataset("Doppler.Amp"))
        self.doppler_time = numeric(self.get_dataset("Doppler.Time(ms)")) * ms

        self.det_freq = numeric(self.get_dataset("Detection.Frequency"))
        self.det_amp = numeric(self.get_dataset("Detection.Amp"))
        self.det_time = numeric(self.get_dataset("Detection.Time(ms)")) * ms

        self.freq_935 = numeric(self.get_dataset("935.Frequency"))
        self.amp_935 = numeric(self.get_dataset("935.Amp"))

        self.attenuation_435_1 = numeric(self.get_dataset("435_1.Attenuation"))

        self.frequency355switch = numeric(self.get_dataset("355_switch.Frequency"))
        self.amplitude355switch = numeric(self.get_dataset("355_switch.Amp"))
        self.attenuation355switch = numeric(self.get_dataset("355_switch.Attenuation"))

        self.RamseyFrequency435mod = numeric(self.get_dataset("Ramsey.Frequency435")) + numeric(
            self.get_dataset("Ramsey.Detuning435"))
        self.RamseyAmplitude435 = numeric(self.get_dataset("Ramsey.Amplitude435"))
        self.PiBy2Time435_1 = numeric(self.get_dataset("Ramsey.PiBy2Time435_1(ms)")) * ms
        self.PiBy2Time435_2 = numeric(self.get_dataset("Ramsey.PiBy2Time435_2(ms)")) * ms

        self.RR_lock_Amp = numeric(self.get_dataset("355_RR_lock.Amp"))
        self.RR_lock_Frequency = numeric(self.get_dataset("355_RR_lock.Frequency"))
        self.RR_lock_Att = numeric(self.get_dataset("355_RR_lock.Attenuation"))

        self.ULE_369_Amp = numeric(self.get_dataset("369_ULE.Amp"))
        self.ULE_369_Frequency = numeric(self.get_dataset("369_ULE.Frequency"))
        self.ULE_369_Att = numeric(self.get_dataset("369_ULE.Attenuation"))

        self.cameraCoolingShotTime = numeric(self.get_dataset('Camera.GlobalCoolingShotTime(ms)')) * ms

        # ---------------- Scan / Argument Unwrapping ----------------
        # Default initialization
        self.scan_param_name = "step"
        self.scan_arr = np.array([0.0])
        self.scan_unit = ""
        self.awg_enabled = getattr(self, "EnableAWG", False)

        # We store these for run() to use later
        self.awg_scan_info = None
        self.awg_globals = None

        # 1. Check for AWG Scan
        if self.awg_enabled:
            self.scan_param_name = self.get_dataset('AWG.Scan_Parameter.name')
            self.scan_arr = self.get_dataset('AWG.Scan_Parameter.array')
            awg_scan_unit = self.get_dataset('AWG.Scan_Parameter.units')

            if awg_scan_unit == 's':
                self.scan_unit = 'ms'
            elif awg_scan_unit == 'Hz':
                self.scan_unit = 'MHz'
            else:
                self.scan_unit = awg_scan_unit

            # C. Prepare AWG Payload (Moved here from Block 2)
            try:
                self.awg_scan_info = {
                    "scan_variables": [str(self.scan_param_name)],
                    # NOTE: We add scan_array here to be safe, though Precomputer handles it
                    "scan_array": self.scan_arr.tolist(),
                    "start": self.scan_arr[0],
                    "stop": self.scan_arr[-1],
                    "num_pts": len(self.scan_arr),
                    "num_reps": self.num_repeat
                }
                self.awg_globals = self.get_awg_globals()
            except Exception as e:
                print(f"AWG Setup Error in Prepare: {e}")

        # 2. Check for Standard Argument Scans
        else:
            # We iterate over the list we created in build()
            for name in self.scannable_names:
                arg = getattr(self, name)

                if hasattr(arg, "value"):# Case A: Fixed Value (NoScan)
                    # Unwrap the value so self.Param becomes a float
                    setattr(self, name, arg.value)

                else: # Case B: Scanning Value
                    # It is an iterable scan object. Convert to array for metadata.
                    # We catch TypeError just in case a non-iterable slipped in
                    try:
                        scan_values = np.array(list(arg))
                    except TypeError:
                        continue

                    if len(scan_values) > 1:
                        # Found the active scan!
                        self.scan_param_name = name
                        self.scan_arr = scan_values
                        # Retrieve the unit we stored in build()
                        self.scan_unit = self.scannable_units.get(name, "")

                    # Note: We do NOT unwrap 'arg' here. The Scan object (iterator)
                    # remains in self.Param so run() can iterate over it.

        print(f"\nScan parameter: {self.scan_param_name} [{self.scan_unit}]")
        print(f"\nScan array: {self.scan_arr}")

        # ---------------- Plotting & Datasets ----------------

        self.set_dataset("ScanDataPlot.x_label", str(f"{self.scan_param_name} [{self.scan_unit}]"), broadcast=True, archive=True, persist=True)
        self.set_dataset("ScanDataPlot.y_vals", [float(np.nan)], broadcast=True, archive=True, persist=True)
        self.set_dataset("ScanDataPlot.x_vals", [float(np.nan)], broadcast=True, archive=True, persist=True)
        self.set_dataset("ScanDataPlot.yerr_vals", [float(np.nan)], broadcast=True, archive=True, persist=True)

        # self.set_dataset("Calibrations.AllZ_calib_max", float(0.07), broadcast=True, archive=True, persist=True)
        # self.set_dataset("Calibrations.AllZ_calib_n", int(1), broadcast=True, archive=True, persist=True)
        # self.set_dataset("Calibrations.AllZ_calib_num_pts", int(9), broadcast=True, archive=True, persist=True)
        # self.set_dataset("Calibrations.AllZ_calib_width", float(0.07), broadcast=True, archive=True, persist=True)
        # self.set_dataset("Calibrations.AllZ_calib_Raman_t", float(1e-6), broadcast=True, archive=True, persist=True)

        # save scan array for allZ_calib
        width = self.get_dataset('Calibrations.AllZ_calib_width')
        self.AllZ_calib_num_pts = self.get_dataset('Calibrations.AllZ_calib_num_pts')
        self.AllZ_calib_n_skip = self.get_dataset('Calibrations.AllZ_calib_n')
        self.AllZ_calib_max = self.get_dataset('Calibrations.AllZ_calib_max')
        self.AllZ_calib_Raman_t = self.get_dataset('Calibrations.AllZ_calib_Raman_t')
        self.allZ_calib_array = np.linspace(self.AllZ_calib_max - width / 2, self.AllZ_calib_max + width / 2, self.AllZ_calib_num_pts)
        self.AllZ_calib_histpoints = np.zeros(self.num_repeat, dtype=int)
        self.set_dataset("Calibrations.AllZ_calib_x", self.allZ_calib_array, broadcast=True, archive=True, persist=True)
        self.set_dataset("Calibrations.AllZ_calib_y", [float(np.nan)], broadcast=True, archive=True, persist=True)
        self.set_dataset("Calibrations.AllZ_calib_y_err", [float(np.nan)], broadcast=True, archive=True, persist=True)

# 26/01/15 gt: generate lists for kernel in prepare; run takes care of preloading AWG and feeding these to kernel
        self.t_0_def = time.time()  # Start timing definitions
        # ---------------- 1. Kernel Argument Definition ----------------
        # Order must match 'krun' signature exactly
        self.on_params = [
            "Frequency435", "Amplitude435", "Time435", "attenuation_435_1", "choice435channel_1_2",
            "doppler_freq", "doppler_amp", "doppler_time",
            "det_freq", "det_amp", "DetTime369", "checkCameraDetection",
            "checkGlobalCoolingShot", "cameraCoolingShotTime",
            "freq_935", "amp_935",
            "prepfreqOP", "prepampOP", "preptimeOP",
            "FrequencyMW", "AmplitudeMW", "TimeMW",
            "SBCFrequency355_1", "SBCAmplitude355_1",
            "SBCFrequency355_2", "SBCAmplitude355_2",
            "SBCTime", "SBCAmplitude935",
            "ClearoutPower935", "ClearoutTime935",
            "prepfreq435", "preptime",
            "WaitTime", "Ramseycheck", "Phase1", "Phase2",
            "frequency355switch", "amplitude355switch", "attenuation355switch",
            "EnableAWG",
            "Frequency355_Raman1", "Amplitude355_Raman1",
            "Frequency355_Raman2", "Amplitude355_Raman2",
            "RamanTime", "LighShiftFactor_BSB", "GlobalSidebandAmpScale", "Bz",
            "RamseyFrequency435mod", "RamseyAmplitude435",
            "PiBy2Time435_1", "PiBy2Time435_2",
            "endcapX", "allY", "allZ",
            "piezoR1H", "piezoR1V", "piezoR2H", "piezoR2V",
            "num_repeat", "iter", "checkLineTrigger", "checkAllZ_calib", 'AllZ_calib_flag'
        ]

        self.bool_params = {
            "checkCameraDetection", "checkGlobalCoolingShot", "Ramseycheck",
            "EnableAWG", "checkLineTrigger"
        }

        # ---------------- 3. Prepare Plotting Data ----------------
        self.plot_scan_arr = list(self.scan_arr)
        scan_name_lower = str(getattr(self, "scan_param_name", "")).lower()

        if ".t" in scan_name_lower or 'time' in scan_name_lower:
            self.plot_scan_arr = [x * 1e3 for x in self.scan_arr]  # s -> ms
        elif ".f" in scan_name_lower or "frequency" in scan_name_lower:
            self.plot_scan_arr = [x * 1e-6 for x in self.scan_arr]  # Hz -> MHz
        elif '.ph' in scan_name_lower or 'phase' in scan_name_lower:
            self.plot_scan_arr = self.scan_arr

        print("\nThe plot scan array for ", scan_name_lower, " is:", self.plot_scan_arr, '\n')

        # ---------------- 4. Logic & Overrides ----------------
        self.num_points = len(self.scan_arr)

        # Map AWG.ch1.T0 -> RamanTime, AWG.ch1.T1 -> WaitTime
        kernel_scan_target = getattr(self, "scan_param_name", "")
        if self.awg_enabled:
            awg_map = {"AWG.ch1.T0": "RamanTime", "AWG.ch1.T1": "WaitTime"}
            if kernel_scan_target in awg_map:
                kernel_scan_target = awg_map[kernel_scan_target]

        # Define Overrides
        overrides = {}
        if not getattr(self, "SBCcheck", False):
            overrides["SBCTime"] = 0.0
        if not getattr(self, "StatePrep", False):
            overrides["preptime"] = 0.0
        if not getattr(self, "Ramseycheck", False):
            overrides["PiBy2Time435_1"] = 0.0
            overrides["PiBy2Time435_2"] = 0.0


        # 26/01/19 gt: for faster data comm
        # ---------------- 5. Build Kernel Arguments (VECTOR OPTIMIZED) ----------------
        # Instead of list-of-lists, we create:
        # 1. default_values: List of floats (current static values)
        # 2. scan_values: List of floats (the changing values)
        # 3. scan_index: The index in default_values to update

        self.default_values = []
        self.scan_values = []
        self.scan_index = -1
        self.iter_index = -1  # To track where 'iter' lives in the list

        for idx, name in enumerate(self.on_params):
            val = 0.0

            # --- A. Determine Value ---
            if name in overrides:
                val = overrides[name]
            elif name == "iter":
                val = 0.0  # Placeholder
                self.iter_index = idx
            elif name == "num_repeat":
                val = float(self.num_repeat)
            elif name == "RamanTime" and self.awg_enabled:
                # If AWG controls this but NOT scanning, get static
                val = self.get_dataset("AWG.ch1.T0")
            elif name == "WaitTime" and self.awg_enabled:
                val = self.get_dataset("AWG.ch1.T1")
            elif name == 'allZ' and self.checkAllZ_calib: # if checked checkAllZ_calib, get allZ from the Calibrations dataset
                val = self.get_dataset('Calibrations.AllZ_calib_max')
            else:
                # Get from self
                raw = getattr(self, name, 0.0)
                # Unwrap if Scannable (taking current value)
                if hasattr(raw, "__iter__") and not isinstance(raw, (str, bytes)):
                    val = raw.value if hasattr(raw, "value") else list(raw)[0]
                else:
                    val = raw

            # --- B. Convert to Float (Homogeneous List) ---
            if isinstance(val, (bool, np.bool_)):
                val = 1.0 if val else 0.0

            self.default_values.append(float(val))

            # --- C. Check Scan Target ---
            if name == kernel_scan_target:
                self.scan_index = idx
                self.scan_values = [float(x) for x in self.scan_arr]

        # Safety: If we are scanning an AWG param that isn't in Kernel (e.g. AWG Amp),
        # scan_values is empty. Fill it so loop runs.
        if len(self.scan_values) == 0:
            self.scan_values = [0.0] * self.num_points

        self.t_f_def = time.time()


        # ---------------- Camera Config ----------------
        self.cameraHOST = '127.0.0.6'
        self.cameraPORT = 65438
        self.set_dataset('Camera.Check', self.checkCameraDetection, broadcast=True, persist=True, archive=True)

        if self.checkCameraDetection:
            # --- FIX: Scale values to match the Unit Label ---

            # 1. Create a copy of the array for manipulation
            camera_vals = np.array(self.scan_arr)
            unit_str = getattr(self, "scan_unit", "arb")

            # 2. Apply scaling based on the unit string
            # ARTIQ data is always in Seconds or Hz. We convert to ms/MHz for display.
            if unit_str == "ms":
                camera_vals = camera_vals * 1e3  # Seconds -> ms
            elif unit_str == "us":
                camera_vals = camera_vals * 1e6  # Seconds -> us
            elif unit_str == "MHz":
                camera_vals = camera_vals * 1e-6  # Hz -> MHz

            # 3. Convert to Python list for JSON
            scan_list = camera_vals.tolist()

            # 4. Build the packet
            self.send_datapacket = {
                'x': {
                    'name': f"{getattr(self, 'scan_param_name', 'Scan')} [{unit_str}]",
                    'value': scan_list
                },
                'rid': getattr(self.scheduler, "rid", -1),
                'repetitions': self.num_repeat,
                'Experiment exposure time': {
                    "value": self.det_time / ms,
                    "unit": "ms"
                }
            }

            self.set_dataset('Camera.x', json.dumps(scan_list), persist=True)
            self.cameraCOMM_prescan()

    @kernel
    def EndcapX(self, V):
        """
        pushes towards +ve X with endcaps
        """
        self.electrodeUpdate(V, [1, 5, 6, 10], [1, -1, -1, 1])

    @kernel
    def AllY(self, V):
        """
        pushes towards +ve Y with all electrodes
        """
        self.electrodeUpdate(V,[0,1,2,3,4,5,6,7,8,9,10,11],[-1]+[-1]*5+[1]*5+[1])
    @kernel
    def AllZ(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V,[0,1,2,3,4,5,6,7,8,9,10,11],[1]+[-1]*5+[1]*5+[-1])

    @kernel
    def electrodeUpdate(self,V,electrodeList,signList):
        for i in range(len(electrodeList)):
            self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] = self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] + V*(signList[i])

    @rpc
    def AllZ_calib_get(self) -> TFloat:
        return float(self.get_dataset('Calibrations.AllZ_calib_max'))

    @kernel
    def ON(self, Frequency435, Amplitude435, Time435, Attenuation_435, choice435, doppler_freq, doppler_amp, doppler_time,
           det_freq, det_amp, det_time, checkCameraDetection, checkGlobalCoolingShot, cameraCoolingShotTime,
           freq_935, amp_935,
           OP_freq, OP_amp, OP_time, MW_freq, MW_amp, MW_time,
           SBCFrequency355_1, SBCAmplitude355_1, SBCFrequency355_2, SBCAmplitude355_2, SBCTime, SBCAmplitude935,
           ClearoutPower935, ClearoutTime935,
           prepfreq435, preptime,
           wait_time, RamseyCheck, phase1, phase2,
           Frequency355switch, Amplitude355switch, Attenuation355switch,
           EnableAWG, FrequencyRaman1, AmplitudeRaman1,
           FrequencyRaman2, AmplitudeRaman2,
           Raman_time, LighShiftFactor, GlobalSidebandAmpScale, Bz,
           RamseyFrequency435, RamseyAmplitude435, PiBy2Time435_1, PiBy2Time435_2,
           newEndcapX, newAllY, newAllZ, piezoR1H, piezoR1V, piezoR2H, piezoR2V,
           num_repeat, iterScan, checkLineTrigger, checkAllZ_calib = False, AllZ_calib_flag = False):

        self.zotino0.init()
        delay(2 * ms)
        # updating zotino with all voltage combinations on electrodes.

        for i in range(12):
            self.modDCElectrodeValues[i] = self.originalDCElectrodeValues[i]
        # adding up combinations
        newX = newEndcapX - self.originalEndcapX
        newY = newAllY - self.originalAllY

        if checkAllZ_calib and AllZ_calib_flag:
            newZ = newAllZ - self.originalAllZ
        elif checkAllZ_calib and not AllZ_calib_flag:
            newZ = self.AllZ_calib_get() - self.originalAllZ
        else:
            newZ = newAllZ - self.originalAllZ

        # if AllZ_calib_flag:
        print("Core sees AllZ Voltage:", newAllZ)

        self.EndcapX(newX)
        self.AllY(newY)
        self.AllZ(newZ)

        self.core.break_realtime()

        # initialize DACS
        for i in range(12):
            ind = self.DCElectrodeMapping[i]
            self.zotino0.write_dac(self.DCElectrodeMapping[i], self.modDCElectrodeValues[ind])
        # self.zotino0.load()

        # piezo voltage  update
        self.zotino0.write_dac(24, piezoR1H)  # new DAC value for 435, need more for 355 beams
        self.zotino0.write_dac(25, piezoR1V)  # new DAC value for 435, need more for 355 beams
        self.zotino0.write_dac(26, piezoR2H)  # new DAC value for 435, need more for 355 beams
        self.zotino0.write_dac(27, piezoR2V)  # new DAC value for 435, need more for 355 beams
        self.zotino0.load()
        delay(2 * ms)

        if iterScan==0:

            self.urukul0_cpld.init()
            self.urukul1_cpld.init()
            self.urukul2_cpld.init()

            delay(10 * ms)
            attenuation=3.0 # use as required

            # Doppler+935

            # Doppler
            self.urukul0_ch1.init()
            self.urukul0_ch1.set_att(0*dB)
            self.urukul0_ch1.set( frequency= doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch1.sw.off()

            # 935
            self.urukul0_ch2.init()
            self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
            self.urukul0_ch2.sw.off()

            # 435
            self.urukul0_ch0.init()
            self.urukul0_ch0.set_att(Attenuation_435 * dB)
            self.urukul0_ch0.sw.off()
            self.urukul1_ch0.init()
            self.urukul1_ch0.set_att(Attenuation_435 * dB)
            self.urukul1_ch0.sw.off()

            # Detection
            self.urukul0_ch3.init()
            self.urukul0_ch3.set_att(0 * dB)
            self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
            self.urukul0_ch3.sw.off()

            # OP
            self.urukul1_ch1.init()
            self.urukul1_ch1.set_att(0 * dB)
            self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
            self.urukul1_ch1.sw.off()

            # MW
            self.urukul1_ch2.init()
            self.urukul1_ch2.set_att(0 * dB)
            self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
            self.urukul1_ch2.sw.off()

            # 369 protection
            self.urukul1_ch3.init()
            self.urukul1_ch3.set_att(0* dB)
            self.urukul1_ch3.set(frequency=200*MHz, amplitude=0.8, phase_mode=2)
            self.urukul1_ch3.sw.off()

            # 355 Raman 1
            self.urukul2_ch0.init()
            self.urukul2_ch0.set_att(0 * dB)
            self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
            self.urukul2_ch0.sw.off()

            # 355 Raman 2
            self.ttl6.output()

            # AWG trigger
            self.ttl5.output()

            # Camera shutter
            self.ttl4.output()

            # 355 Raman 1 channel2 dual tone application
            self.urukul2_ch1.init()
            self.urukul2_ch1.set_att(0 * dB)
            self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
            self.urukul2_ch1.sw.off()

            self.sum_rising_edges = 0.0

            # self.sum_rising_edges_cooling = 0.0

            # warming up detection and Doppler AOM
            self.urukul0_ch1.sw.on()
            self.urukul0_ch3.sw.on()
            self.urukul1_ch3.sw.on()
            self.urukul1_ch1.sw.on()
            delay(5*ms)
            self.urukul0_ch1.sw.off()
            self.urukul0_ch3.sw.off()
            self.urukul1_ch3.sw.off()
            self.urukul1_ch1.sw.off()

            # Cooling shot: 1 extra ttl trigger from the camera just before the entire exp sequence
            if checkGlobalCoolingShot and checkCameraDetection:
                self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
                self.urukul0_ch1.sw.on()
                self.urukul0_ch2.sw.on()
                self.urukul1_ch3.sw.on()  # protection on

                self.ttl4.on()  # camera trigger
                delay(cameraCoolingShotTime)
                self.ttl4.off()

                delay(11 * ms)  # Need this delay for camera acquisition.
                self.urukul0_ch1.sw.off()
                self.urukul0_ch2.sw.off()
                self.urukul1_ch3.sw.off()  # protection off

        i=0

        with self.core_dma.record("seq"):
            #delay(30 * us)  # This delay will exist between repetitions

            # self.ttl5.on()

            self.urukul0_ch1.set_att(0 * dB) # Doppler
            self.urukul0_ch2.set_att(0 * dB) # 935
            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            self.urukul0_ch2.sw.on()
            self.urukul1_ch3.sw.on()  # protection on

            if checkCameraDetection:
                delay(6*ms)
            else:
                delay(doppler_time)

            self.urukul0_ch1.sw.off()
            self.urukul0_ch2.sw.off()

            self.urukul1_ch3.sw.off() # protection off

            self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
            self.urukul1_ch1.set_att(0 * dB)
            self.urukul2_ch0.set_att(0 * dB)

            if SBCTime>0.1*us:

                # for 171, uncomment
                # self.urukul1_ch1.sw.on()
                # delay(0.05 * ms)
                # self.urukul1_ch1.sw.off()
                # self.urukul0_ch2.sw.on()

                # for 172 uncomment
                # 411 State prep
                # if preptime > 0.0001 * ms:
                #     self.urukul0_ch0.set(frequency=prepfreq435, amplitude=0.8, phase_mode=2)
                #     self.urukul1_ch0.set(frequency=80 * MHz, amplitude=0.8, phase_mode=2)
                #     self.urukul0_ch0.sw.on()
                #     self.urukul1_ch0.sw.on()
                #     # self.urukul0_ch2.sw.on()
                #     delay(preptime)
                #     self.urukul0_ch0.sw.off()
                #     self.urukul1_ch0.sw.off()
                    # self.urukul0_ch2.sw.off()


                # # # # # Outer Tilt
                # self.urukul2_ch0.set(frequency= 189.797657*MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(50):
                #     #self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(SBCTime)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     #self.ttl5.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.05 * ms)
                #     self.urukul1_ch1.sw.off()

                # 2nd order SB
                # self.urukul2_ch0.set(frequency= 189.797657 * MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(15):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.05*ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     # self.ttl5.off()
                #     self.urukul1_ch1.sw.on() # OP
                #     delay(0.03 * ms)
                #     self.urukul1_ch1.sw.off()


                # # # # inner tilt
                # self.urukul2_ch0.set(frequency=190.106798* MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(50):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(SBCTime)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     # self.ttl5.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.03 * ms)
                #     self.urukul1_ch1.sw.off()


                # # # # 2nd round IT1
                # self.urukul2_ch0.set(frequency=190.08812 * MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(15):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.028*ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     # self.ttl5.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.03 * ms)
                #     self.urukul1_ch1.sw.off()

                # # # # # Outer 1
                self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                for cyc in range(50):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    delay(SBCTime)
                    # delay(0.012*ms)
                    #delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    self.urukul1_ch1.sw.on()
                    delay(0.05 * ms) # prev 0.03ms need strong OP power
                    self.urukul1_ch1.sw.off()

                # # # # # Inner 1
                # # # #
                self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                for cyc in range(60):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    # self.ttl5.on()
                    delay(SBCTime)
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    self.urukul1_ch1.sw.on()
                    delay(0.05 * ms)
                    self.urukul1_ch1.sw.off()
                # # # # #
                # #  # # # Outer1 2nd stage
                self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                for cyc in range(25):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    delay(0.03 * ms)
                    # delay(SBCTime)
                    # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    self.urukul1_ch1.sw.on()
                    delay(0.05 * ms)  # prev 0.03ms need strong OP power
                    self.urukul1_ch1.sw.off()
                # # # # # # #
                # # # # # # # # #
                # # # # # # # Inner1 2nd stage
                self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                for cyc in range(15):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    # self.ttl5.on()
                    delay(0.02 * ms)
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    self.urukul1_ch1.sw.on()
                    delay(0.05 * ms)
                    self.urukul1_ch1.sw.off()
                # self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                # for cyc in range(25):
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.035*ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.01 * ms)
                #     self.urukul1_ch1.sw.off()
                #
                # # # # 2nd round OT1
                # self.urukul2_ch0.set(frequency= 189.797657 * MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(15):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.035*ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     # self.ttl5.off()
                #     self.urukul1_ch1.sw.on() # OP
                #     delay(0.03 * ms)
                #     self.urukul1_ch1.sw.off()
                #
                #
                # # # # # 2nd round IT1
                # self.urukul2_ch0.set(frequency=190.106798 * MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(15):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.027*ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     # self.ttl5.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.03 * ms)
                #     self.urukul1_ch1.sw.off()
                #
                # # # #  # # # Outer1 2nd stage
                # self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                # for cyc in range(30):
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.038 * ms)
                #     # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.05 * ms)  # prev 0.03ms need strong OP power
                #     self.urukul1_ch1.sw.off()

                # Axial CSBC 411+976

                #2nd
                # self.urukul0_ch0.set(frequency= 231.519781*MHz, amplitude=SBCAmplitude355_1, phase_mode=2)
                # self.urukul1_ch0.set(frequency=80 * MHz, amplitude=SBCAmplitude935, phase_mode=2)
                # self.urukul0_ch0.sw.on()
                # self.urukul1_ch0.sw.on()
                # self.urukul0_ch2.sw.on()
                # delay(3*ms)
                # self.urukul0_ch0.sw.off()
                # self.urukul1_ch0.sw.off()
                # self.urukul0_ch2.sw.off()
                # self.urukul0_ch2.sw.off()

                ########################################
                # in-phase mode (IP1) CSBC #

                # self.urukul0_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                # self.urukul1_ch0.set(frequency=80 * MHz, amplitude=SBCAmplitude935, phase_mode=2)
                # self.urukul0_ch2.set(frequency=113 * MHz, amplitude=0.8, phase_mode=2)
                #
                # self.urukul0_ch0.sw.on()
                # self.urukul1_ch0.sw.on()
                # self.urukul0_ch2.sw.on()
                # delay(SBCTime)
                # self.urukul0_ch0.sw.off()
                # self.urukul1_ch0.sw.off()
                # self.urukul0_ch2.sw.off()
                # self.urukul0_ch2.sw.off()
                ##########################################

                # # 1st

                ##########################################
                # Out-of-phase mode (OP1) CSB #

                # self.urukul0_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                # self.urukul1_ch0.set(frequency=80 * MHz, amplitude=SBCAmplitude935, phase_mode=2)
                # self.urukul0_ch2.set(frequency=113 * MHz, amplitude=0.8, phase_mode=2)
                #
                # self.urukul0_ch0.sw.on()
                # self.urukul1_ch0.sw.on()
                # self.urukul0_ch2.sw.on()
                # # delay(3*ms)
                # delay(SBCTime)
                # self.urukul0_ch0.sw.off()
                # self.urukul1_ch0.sw.off()
                # self.urukul0_ch2.sw.off()
                # self.urukul0_ch2.sw.off()
                ############################################

                # Axial PSBC

                # 2nd sideband
                # self.urukul0_ch0.set(frequency=234.527 * MHz, amplitude=0.8, phase_mode=2)
                # self.urukul1_ch0.set(frequency=80 * MHz, amplitude=0.8, phase_mode=2)
                # for cyc in range(180):
                #     self.urukul0_ch0.sw.on()
                #     delay(0.01*ms)
                #     self.urukul0_ch0.sw.off()
                #
                #     self.urukul1_ch0.sw.on()
                #     delay(0.03 * ms)
                #     self.urukul1_ch0.sw.off()
                #     self.urukul0_ch2.sw.on()
                #     delay(0.03 * ms)
                #     self.urukul0_ch2.sw.off()

                #1st sideband
                # self.urukul0_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                # self.urukul1_ch0.set(frequency=80 * MHz, amplitude=0.5, phase_mode=2)
                #
                # for cyc in range(300):
                #     self.urukul0_ch0.sw.on()
                #     delay(SBCTime)
                #     self.urukul0_ch0.sw.off()
                #
                #     self.urukul1_ch0.sw.on()
                #     delay(0.005 * ms)
                #     self.urukul1_ch0.sw.off()
                #     self.urukul0_ch2.sw.on()
                #     delay(0.01*ms)
                #     self.urukul0_ch2.sw.off()
                #
                # for cyc in range(40):
                #     self.urukul0_ch0.sw.on()
                #     delay(SBCTime*5)
                #     self.urukul0_ch0.sw.off()
                #     self.urukul1_ch0.sw.on()
                #     delay(0.005 * ms)
                #     self.urukul1_ch0.sw.off()
                #     self.urukul0_ch2.sw.on()
                #     delay(0.01*ms)
                #     self.urukul0_ch2.sw.off()

                # for cyc in range(60):
                #     self.urukul0_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                #     self.urukul0_ch0.sw.on()
                #     delay(SBCTime*10)
                #     self.urukul0_ch0.sw.off()
                #
                #     # self.urukul0_ch0.set(frequency=209.318*MHz, amplitude=SBCAmplitude355_1, phase_mode=2)
                #     # self.urukul0_ch0.sw.on()
                #     # delay(SBCTime)
                #     # self.urukul0_ch0.sw.off()
                #
                #     self.urukul1_ch0.sw.on()
                #     delay(0.03 * ms)
                #     self.urukul1_ch0.sw.off()
                #     self.urukul0_ch2.sw.on()
                #     delay(0.03*ms)
                #     self.urukul0_ch2.sw.off()

                #clearout 976
                # self.urukul1_ch0.set(frequency=80 * MHz, amplitude=0.8, phase_mode=2)
                # self.urukul1_ch0.sw.on()
                # # delay(0.05* ms)
                # delay(0.03*ms)
                # self.urukul1_ch0.sw.off()


                #CSBC
                # self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=0.7, phase_mode=2)
                # self.urukul1_ch1.set(frequency=OP_freq, amplitude=SBCAmplitude355_2, phase_mode=2)
                # self.urukul2_ch0.sw.on()
                # self.ttl6.on()
                # self.urukul1_ch1.sw.on()
                # delay(SBCTime)
                # # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                # self.urukul2_ch0.sw.off()
                # self.ttl6.off()
                # self.urukul1_ch1.sw.off()

                # Axial
                # self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                # for cyc in range(100):
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     # self.ttl5.on()
                #     delay(SBCTime)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.1 * ms)
                #     self.urukul1_ch1.sw.off()

                # CSBC Raman
                # self.urukul1_ch1.set(frequency=OP_freq, amplitude=SBCAmplitude935, phase_mode=2)
                # self.urukul2_ch0.sw.on()
                # self.ttl6.on()
                # self.urukul1_ch1.sw.on()
                # delay(SBCTime)
                # self.urukul2_ch0.sw.off()
                # self.ttl6.off()
                # self.urukul1_ch1.sw.off()

                #self.urukul0_ch2.sw.off()

            # self.ttl5.on()
            # OP state prep with 935
            if OP_time>0.01*us:
                self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
                self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
                self.urukul1_ch1.set_att(0 * dB)
                self.urukul0_ch2.set_att(0 * dB)
                self.urukul1_ch1.sw.on()

                delay(OP_time)
                # delay(0.05* ms)
                delay_mu(1)

                self.urukul1_ch1.sw.off()

            # self.ttl5.off()
            #delay(-1*us) # important for syncing. Must be before setting up the DDS config or else there is some gradual ampltiude ramp of 435 DDS

            if RamseyCheck==True and not EnableAWG:

                #delay(1*ms)
                # # MW ramsey
                # #First pi/2 pulse
                # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
                # #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.sw.on()
                # delay(PiBy2Time435_1)
                # delay_mu(1)
                # # self.urukul1_ch2.set_att(30 * dB)
                # self.urukul1_ch2.sw.off()
                # #delay(0.05*ms)
                #
                # # # # Raman 1 ch 1-RSB
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on()  # Raman 1
                # # self.ttl6.on()  # Raman 2
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()  # Raman 1
                # # self.ttl6.off()  # Raman 2
                #
                # # Raman pulse with MW
                # # # # Raman 1 ch 1
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on()
                # # self.ttl6.on()
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()
                # # self.ttl6.off()
                #
                # # # wait time
                # # delay(wait_time)
                # # delay_mu(1)
                #
                #
                # # wait time with 1 echo pi
                #
                # # for n in range(4):
                # #     delay(wait_time/(2*4))
                # #     delay_mu(1)
                # #     self.urukul1_ch2.sw.on()
                # #     delay(PiBy2Time435_1*2)
                # #     delay_mu(1)
                # #     # self.urukul1_ch2.set_att(30 * dB)
                # #     self.urukul1_ch2.sw.off()
                # #     delay(wait_time/(2*4))
                # #     delay_mu(1)
                #
                #
                #
                # # wait time with 355 on
                # #
                #
                # # self.urukul2_ch0.sw.on() # Raman 1
                # # self.ttl6.on() # Raman 2
                # delay(wait_time)
                # delay_mu(1)
                # # self.urukul2_ch0.sw.off() # Raman 1
                # # self.ttl6.off() # Raman 2
                # #
                # #
                # #
                # #
                #
                # # Raman pulse with MW
                # # # Raman 1 ch 1
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on()
                # # self.ttl6.on()
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()
                # # self.ttl6.off()
                #
                # # # # Raman 1 ch 1-RSB
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on()  # Raman 1
                # # self.ttl6.on()  # Raman 2
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()  # Raman 1
                # # self.ttl6.off()  # Raman 2
                #
                # # Ramsey second pi/2 435/MW pulse
                #
                # self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
                # #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                # # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.sw.on()
                # self.urukul1_ch2.set_att(0 * dB)
                # delay(PiBy2Time435_2)
                # delay_mu(1)
                # # self.urukul1_ch2.set_att(30 * dB)
                # self.urukul1_ch2.sw.off()

                #delay(0.05*ms)

                # Raman Ramsey

                # # Ramsey first pi/2
                self.urukul1_ch2.set_att(0 * dB)
                self.urukul2_ch0.set(frequency=RamseyFrequency435 ,phase=0.0, amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()
                self.ttl6.on()
                delay(0.3 * us)  # AOM delay
                delay(PiBy2Time435_1)
                # delay(Raman_time)
                #delay_mu(1)
                # self.urukul1_ch2.set_att(30 * dB)

                self.urukul2_ch0.sw.off()
                self.ttl6.off()

                #self.urukul2_ch0.set(frequency=202*MHz,phase=0.0, amplitude=RamseyAmplitude435, phase_mode=2)

                # delay(0.05*ms)

                # # delay(10*us)
                # # # # # Raman 1 ch 1 -RSB
                # self.urukul2_ch0.set(frequency=FrequencyRaman1,phase=0.0, amplitude=AmplitudeRaman1, phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # ### extra
                # self.urukul2_ch1.set(frequency=FrequencyRaman2 , phase=phase2,
                #                      amplitude=AmplitudeRaman2 , phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()  # Raman 1,ch2
                # ### extra -end
                # self.urukul2_ch0.sw.on()  # Raman 1
                # self.ttl6.on()  # Raman 2
                # delay(0.3 * us)  # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch0.sw.off()  # Raman 1 ch1
                # self.ttl6.off()  # Raman 2
                #
                # ### extra
                # self.urukul2_ch1.sw.off() # Raman 1 ch2
                # ### extra -end

                # # Raman 1 ch 2-RSB
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, phase= 0.0, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()  # Raman 1
                # self.ttl6.on()  # Raman 2
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch1.sw.off()  # Raman 1
                # self.ttl6.off()  # Raman 2

                #wait time
                # delay(wait_time)
                # delay_mu(1)

                # #Changing DACs during Ramsey
                # self.endcapX(newX)
                # self.allY(0.0)
                # self.allZ(0.0)
                # for i in range(12):
                #     ind = self.DCElectrodeMapping[i]
                #     self.zotino0.write_dac(self.DCElectrodeMapping[i], self.modDCElectrodeValues[ind])
                # self.zotino0.load()



                # Dynamical decoupling
                # for n in range(2):
                #
                #     # wait fraction
                #     delay(wait_time/(2.0*(2)))
                #     delay_mu(1)

                    # pure RSB decoupling
                    # self.urukul1_ch2.set_att(0 * dB)
                    # # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1,
                    # #                      phase_mode=2)
                    # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=(0.0 + np.pi / 2.0 * (n % 2)), amplitude=AmplitudeRaman1,phase_mode=2)
                    # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                    # self.urukul2_ch0.set_att(0 * dB)
                    # self.urukul2_ch0.sw.on()
                    # self.ttl6.on()
                    # delay(0.3 * us)  # AOM delay
                    # delay(Raman_time*2.0)
                    # # delay_mu(1)
                    # # self.urukul1_ch2.set_att(30 * dB)
                    # self.urukul2_ch0.sw.off()
                    # self.ttl6.off()

                    # carrier and rsb decoupling

                    # #RSB pi
                    # self.urukul1_ch2.set_att(0 * dB)
                    # self.urukul2_ch0.set(frequency=SBCFrequency355_1, phase=0.0,
                    #                      amplitude=0.7, phase_mode=2)
                    # self.urukul2_ch0.set_att(0 * dB)
                    # self.urukul2_ch0.sw.on()
                    # self.ttl6.on()
                    # delay(0.3 * us)  # AOM delay
                    # delay(0.035*ms)
                    # self.urukul2_ch0.sw.off()
                    # self.ttl6.off()
                    #
                    # # carrier pi
                    # self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=(0.0 + np.pi / 2.0 * (n % 2)),
                    #                      amplitude=RamseyAmplitude435, phase_mode=2)
                    # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                    # self.urukul2_ch0.set_att(0 * dB)
                    # self.urukul2_ch0.sw.on()
                    # self.ttl6.on()
                    # delay(0.3 * us)  # AOM delay
                    # delay(PiBy2Time435_1*2.0)
                    # # delay_mu(1)
                    # # self.urukul1_ch2.set_att(30 * dB)
                    # self.urukul2_ch0.sw.off()
                    # self.ttl6.off()
                    #
                    # # RSB pi
                    # self.urukul1_ch2.set_att(0 * dB)
                    # self.urukul2_ch0.set(frequency=SBCFrequency355_1, phase=np.pi,
                    #                      amplitude=0.7, phase_mode=2)
                    # self.urukul2_ch0.set_att(0 * dB)
                    # self.urukul2_ch0.sw.on()
                    # self.ttl6.on()
                    # delay(0.3 * us)  # AOM delay
                    # delay(0.035*ms)
                    # self.urukul2_ch0.sw.off()
                    # self.ttl6.off()

                    # carrier and rsb with bsb decoupling

                    # # carrier pi
                    # self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=(0.0 + np.pi / 2.0 * (n % 2)),
                    #                      amplitude=RamseyAmplitude435, phase_mode=2)
                    # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                    # self.urukul2_ch0.set_att(0 * dB)
                    # self.urukul2_ch0.sw.on()
                    # self.ttl6.on()
                    # delay(0.3 * us)  # AOM delay
                    # delay(PiBy2Time435_1 * 2.0)
                    # # delay_mu(1)
                    # # self.urukul1_ch2.set_att(30 * dB)
                    # self.urukul2_ch0.sw.off()
                    # self.ttl6.off()
                    #
                    # # BSB pi- ch2
                    # self.urukul2_ch1.set(frequency=195.43771*MHz, phase=0.0,
                    #                      amplitude=0.4017, phase_mode=2)
                    # self.urukul2_ch1.set_att(0 * dB)
                    # self.urukul2_ch1.sw.on()
                    # self.ttl6.on()
                    # delay(0.3 * us)  # AOM delay
                    # delay(0.059755 * ms)
                    # self.urukul2_ch1.sw.off()
                    # self.ttl6.off()
                    #
                    #
                    # # RSB pi -ch1
                    # self.urukul2_ch0.set(frequency=189.626452*MHz, phase=0.0,
                    #                      amplitude=0.35, phase_mode=2)
                    # self.urukul2_ch0.set_att(0 * dB)
                    # self.urukul2_ch0.sw.on()
                    # self.ttl6.on()
                    # delay(0.3 * us)  # AOM delay
                    # delay(0.064 * ms)
                    # self.urukul2_ch0.sw.off()
                    # self.ttl6.off()
                    #
                    #
                    # # wait fraction
                    # delay(wait_time/(2.0*(2)))
                    # delay_mu(1)

                # wait time with 355 on
                #
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase= 0.0,  amplitude=AmplitudeRaman1*GlobalSidebandAmpScale, phase_mode=2) #RSB
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, phase=phase2, amplitude=AmplitudeRaman2*LighShiftFactor*GlobalSidebandAmpScale, phase_mode=2) #BSB
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch0.sw.on() # Raman 1 ch1
                # self.urukul2_ch1.sw.on()  # Raman 1 ch2
                # self.ttl6.on() # Raman 2
                delay(wait_time)
                delay_mu(1)
                # self.ttl6.off() # Raman 2
                # self.urukul2_ch0.sw.off() # Raman 1 ch1
                # self.urukul2_ch1.sw.off() # Raman 1 ch2

                #
                # # # # # # Raman 1 ch 1-RSB
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=phase1, amplitude=AmplitudeRaman1, phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # ### extra
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, phase=phase2,
                #                      amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()  # Raman 1,ch2
                # ### extra -end
                #
                # self.urukul2_ch0.sw.on()  # Raman 1
                # self.ttl6.on()  # Raman 2
                # delay(0.3 * us)  # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch0.sw.off()  # Raman 1
                # self.ttl6.off()  # Raman 2
                # ### extra
                # self.urukul2_ch1.sw.off()  # Raman 1 ch2
                # ### extra -end

                # # Raman 1 ch 2-RSB
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, phase=np.pi-(SBCAmplitude935-0.4)*np.pi/0.8, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()  # Raman 1
                # self.ttl6.on()  # Raman 2
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch1.sw.off()  # Raman 1
                # self.ttl6.off()  # Raman 2


                # # # Ramsey second pi/2
                # # # delay(10 * us)
                self.urukul2_ch0.set(frequency=RamseyFrequency435, phase= phase1,  amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul1_ch2.set_att(0 * dB)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()
                self.ttl6.on()
                delay(0.6 * us)  # AOM delay
                delay(PiBy2Time435_2)
                # delay(Raman_time)
                #delay_mu(1)
                self.urukul2_ch0.sw.off()
                self.ttl6.off()


            # 435 interaction
            self.urukul0_ch2.sw.off() # 935/760 repumper
            self.urukul1_ch0.sw.off()  # 976 repumper
            #if choice435==1:
            # self.urukul0_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
            # self.urukul0_ch0.sw.on()
            # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2) # Raman 1
            # self.urukul2_ch0.set_att(0 * dB) # Raman 1
            # self.urukul2_ch0.sw.on()  # Raman 1
            # self.ttl6.on()  # Raman 2
            # delay(Time435)
            # self.urukul0_ch0.sw.off()
            # self.urukul2_ch0.sw.off()  # Raman 1
            # self.ttl6.off()  # Raman 2

            #elif choice435==2:
            #delay(10*us) # a delay because suspectected pulse sequence was not running properly. Have to revisit it.

            # 976
            # self.urukul1_ch0.set(frequency=80*MHz, amplitude=0.8, phase_mode=2)
            # self.urukul1_ch0.sw.on()
            # delay(1*ms)
            # self.urukul1_ch0.sw.off()

            #self.urukul0_ch2.sw.off() # 935 repumper

            # For dual drive

            # self.urukul0_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
            # self.urukul1_ch0.set(frequency=prepfreq435, amplitude=Amplitude435, phase_mode=2)
            # self.urukul0_ch0.sw.on()
            # self.urukul1_ch0.sw.on()
            # delay(Time435)
            # self.urukul0_ch0.sw.off()
            # self.urukul1_ch0.sw.off()

            #delay(30 * ms)

            # # 760/935 PUMPING INTERACTION
            # delay(10 * us)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=ClearoutPower935, phase_mode=2)
            # self.urukul0_ch2.sw.on()
            # delay(ClearoutTime935)
            # self.urukul0_ch2.sw.off()
            # delay(10 * us)

            # 976 PUMPING INTERACTION
            # delay(10 * us)
            # self.urukul1_ch0.set(frequency=80*MHz, amplitude=ClearoutPower935, phase_mode=2)
            # self.urukul1_ch0.sw.on()
            # delay(ClearoutTime935)
            # self.urukul1_ch0.sw.off()
            # delay(10 * us)


            # self.ttl5.on()
            #delay(wait_time)
            # self.ttl5.off()

            if RamseyCheck and EnableAWG:
                self.zotino0.write_dac(31, 0.0)  # set and turn z0ch31 to 0 V (switch to AWG)
                self.zotino0.load()
                delay(0.5 * ms)

                self.ttl5.on()  # trigger to AWG/ Raman 1
                self.ttl6.on()  # Raman 2 on
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                self.ttl6.off()  # Raman 2 off

                # self.ttl5.on()
                # delay(wait_time*1e-3)

                delay(wait_time)

                # delay(Raman_time) # diagnostic
                # self.ttl5.off()

                self.ttl6.on()  # Raman 2 on
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                self.ttl6.off()  # Raman 2 off

                self.ttl5.off()

                # delay(0.5 * ms)
                self.zotino0.write_dac(31, 5.0)  # set back to DDS
                self.zotino0.load()
                delay(0.5 * ms)

            # MW interaction
            if MW_time>0.01*us:
                self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
                #self.urukul1_ch2.set_att(0 * dB)
                self.urukul1_ch2.set_att(0 * dB)
                self.urukul1_ch2.sw.on()
                delay(MW_time)
                delay_mu(1)
                self.urukul1_ch2.sw.off()


            if checkAllZ_calib and AllZ_calib_flag:
                # Raman 1 ch 1
                self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()  # Raman 1
                self.ttl6.on()  # Raman 2
                delay(0.3 * us)  # AOM delay

                delay(self.AllZ_calib_Raman_t)

                self.urukul2_ch0.sw.off()  # Raman 1
                self.ttl6.off()  # Raman 25*us


            # Raman
            if Raman_time > 0.01 * us and not EnableAWG and not RamseyCheck and not AllZ_calib_flag:
                delay(0.001*ms)

                # Raman 1 ch 1
                self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()# Raman 1

                self.ttl6.on() # Raman 2
                # self.ttl5.on() # AWG trigger
                delay(0.3*us) # AOM delay
                delay(Raman_time)
                self.urukul2_ch0.sw.off() # Raman 1
                self.ttl6.off() # Raman 25*us
                # self.ttl5.off() # AWG trigger

                # # # # Raman 1: ch1 and ch2 on
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase= 0.0, amplitude=AmplitudeRaman1*0.50978*1.0/0.8, phase_mode=2)
                # self.urukul2_ch0.set(frequency=FrequencyRaman1 - Frequency435 + Bz, phase= 0.0, amplitude=AmplitudeRaman1*GlobalSidebandAmpScale, phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # ## self.urukul2_ch1.set(frequency=FrequencyRaman2, phase= 0.0, amplitude=AmplitudeRaman1*0.7/0.6, phase_mode=2)
                # self.urukul2_ch1.set(frequency=FrequencyRaman2 + Frequency435 + Bz, phase= phase2, amplitude=AmplitudeRaman2*LighShiftFactor*GlobalSidebandAmpScale, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()# Raman 1
                # self.urukul2_ch1.sw.on()# Raman 1,ch2
                # self.ttl6.on() # Raman 2
                # delay(0.3*us) # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch0.sw.off() # Raman 1 ch1
                # self.urukul2_ch1.sw.off()  # Raman 1ch2
                # self.ttl6.off() # Raman 25*us

                # # #  Parity analysis pulse # Raman 1 ch 1
                # self.urukul2_ch0.set(frequency=192.546039253*MHz, phase=phase1, amplitude= 0.5,  phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()# Raman 1
                # self.ttl6.on() # Raman 2
                # delay(0.25*us) # AOM delay
                # delay(0.0010957*ms)
                # #delay(Raman_time)
                # self.urukul2_ch0.sw.off() # Raman 1
                # self.ttl6.off() # Raman 25*us

                # # # # Raman 1 ch2
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()
                # self.ttl6.on()
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.ttl6.off()
                # self.urukul2_ch1.sw.off()

            # AWG Raman
            if EnableAWG and not RamseyCheck:
                self.zotino0.write_dac(31, 0.0) # set and turn z0ch31 to 0 V (switch to AWG)
                self.zotino0.load()
                delay(0.5*ms)

                self.ttl5.on() # trigger to AWG/ Raman 1
                self.ttl6.on()  # Raman 2 on
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                self.ttl6.off() # Raman 2 off
                self.ttl5.off()

                delay(0.5 *ms)
                self.zotino0.write_dac(31, 5.0)  # set back to DDS
                self.zotino0.load()
                delay(0.5 * ms)

            # Detection w. 935
            if det_time>0.01*us:
                self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
                self.urukul0_ch3.sw.on()
                if checkCameraDetection:
                    self.ttl4.on()# camera
                self.ttl.gate_rising(det_time)
                if checkCameraDetection:
                    self.ttl4.off() # camera
                self.urukul0_ch3.sw.off()

            # self.ttl5.off()

            # Doppler + 760/935
            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
            self.urukul0_ch1.set_att(0 * dB)
            self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch1.sw.on()
            self.urukul0_ch2.sw.on()
            self.urukul1_ch3.sw.on()

            # delay(20 * ms) # for 976 and 760

            if checkCameraDetection and SBCTime<=0.1*us:
                delay(5*ms) # important for 411 and camera based detection
            elif checkCameraDetection and SBCTime>0.1*us:
                delay(2*ms)

            # exp loop with dma

        # for DMA (agrees with barebones)
        seq_handle = self.core_dma.get_handle("seq")
        # repetition loop for DMA
        if checkAllZ_calib and AllZ_calib_flag:
            num_repeat_mod=50
        else:
            num_repeat_mod=num_repeat

        for i in range(num_repeat_mod):
            # Line trigger sync
            if checkLineTrigger:
                '''
                loops until 1 count from the trigger line is detected
                '''
                fc = 0
                while fc == 0:
                    self.ttl0_counter.gate_rising(0.05 * ms) # lower detection time helps to finely resolve ext trigger timing
                    delay(10 * us)
                    fc = self.ttl0_counter.fetch_count()
            # DMA's single execution run
            self.core_dma.playback_handle(seq_handle)
            if checkAllZ_calib and AllZ_calib_flag:
                self.AllZ_calib_histpoints[i] = self.ttl.fetch_count()
                # self.calib_counts_print(self.ttl.fetch_count())
            else:
                self.histpoints[i] = self.ttl.fetch_count() # I think can only be called once per gate event or blocks function until counts is available

    @rpc
    def calib_counts_print(self, counts):
        print('The unthresholded counts from the AllZ scan are ', counts)

# 26/02/02 gt: for non-DMA scan
#     @kernel
#     def ON(self, Frequency435, Amplitude435, Time435, Attenuation_435, choice435, doppler_freq, doppler_amp,
#            doppler_time,
#            det_freq, det_amp, det_time, checkCameraDetection, checkGlobalCoolingShot, cameraCoolingShotTime,
#            freq_935, amp_935,
#            OP_freq, OP_amp, OP_time, MW_freq, MW_amp, MW_time,
#            SBCFrequency355_1, SBCAmplitude355_1, SBCFrequency355_2, SBCAmplitude355_2, SBCTime, SBCAmplitude935,
#            ClearoutPower935, ClearoutTime935,
#            prepfreq435, preptime,
#            wait_time, RamseyCheck, phase1, phase2,
#            Frequency355switch, Amplitude355switch, Attenuation355switch,
#            EnableAWG, FrequencyRaman1, AmplitudeRaman1,
#            FrequencyRaman2, AmplitudeRaman2,
#            Raman_time, LighShiftFactor, GlobalSidebandAmpScale, Bz,
#            RamseyFrequency435, RamseyAmplitude435, PiBy2Time435_1, PiBy2Time435_2,
#            newEndcapX, newAllY, newAllZ, piezoR1H, piezoR1V, piezoR2H, piezoR2V,
#            num_repeat, iterScan, checkLineTrigger, checkAllZ_calib=False, AllZ_calib_flag=False):
#
#         self.core.break_realtime()
#
#         self.zotino0.init()
#         delay(2 * ms)
#         # updating zotino with all voltage combinations on electrodes.
#
#         for i in range(12):
#             self.modDCElectrodeValues[i] = self.originalDCElectrodeValues[i]
#         # adding up combinations
#         newX = newEndcapX - self.originalEndcapX
#         newY = newAllY - self.originalAllY
#
#         if checkAllZ_calib and AllZ_calib_flag:
#             newZ = newAllZ - self.originalAllZ
#         elif checkAllZ_calib and not AllZ_calib_flag:
#             newZ = self.AllZ_calib_get() - self.originalAllZ
#         else:
#             newZ = newAllZ - self.originalAllZ
#
#         # if AllZ_calib_flag:
#         print("Core sees AllZ Voltage:", newAllZ)
#
#         self.EndcapX(newX)
#         self.AllY(newY)
#         self.AllZ(newZ)
#
#         self.core.break_realtime()
#
#         # initialize DACS
#         for i in range(12):
#             ind = self.DCElectrodeMapping[i]
#             self.zotino0.write_dac(self.DCElectrodeMapping[i], self.modDCElectrodeValues[ind])
#         # self.zotino0.load()
#
#         # piezo voltage  update
#         self.zotino0.write_dac(24, piezoR1H)  # new DAC value for 435, need more for 355 beams
#         self.zotino0.write_dac(25, piezoR1V)  # new DAC value for 435, need more for 355 beams
#         self.zotino0.write_dac(26, piezoR2H)  # new DAC value for 435, need more for 355 beams
#         self.zotino0.write_dac(27, piezoR2V)  # new DAC value for 435, need more for 355 beams
#         self.zotino0.load()
#         delay(2 * ms)
#
#         if iterScan == 0:
#
#             self.urukul0_cpld.init()
#             self.urukul1_cpld.init()
#             self.urukul2_cpld.init()
#
#             delay(10 * ms)
#             attenuation = 3.0  # use as required
#
#             # Doppler+935
#
#             # Doppler
#             self.urukul0_ch1.init()
#             self.urukul0_ch1.set_att(0 * dB)
#             self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
#             self.urukul0_ch1.sw.off()
#
#             # 935
#             self.urukul0_ch2.init()
#             self.urukul0_ch2.set_att(0 * dB)
#             self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
#             self.urukul0_ch2.sw.off()
#
#             # 435
#             self.urukul0_ch0.init()
#             self.urukul0_ch0.set_att(Attenuation_435 * dB)
#             self.urukul0_ch0.sw.off()
#             self.urukul1_ch0.init()
#             self.urukul1_ch0.set_att(Attenuation_435 * dB)
#             self.urukul1_ch0.sw.off()
#
#             # Detection
#             self.urukul0_ch3.init()
#             self.urukul0_ch3.set_att(0 * dB)
#             self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
#             self.urukul0_ch3.sw.off()
#
#             # OP
#             self.urukul1_ch1.init()
#             self.urukul1_ch1.set_att(0 * dB)
#             self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
#             self.urukul1_ch1.sw.off()
#
#             # MW
#             self.urukul1_ch2.init()
#             self.urukul1_ch2.set_att(0 * dB)
#             self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
#             self.urukul1_ch2.sw.off()
#
#             # 369 protection
#             self.urukul1_ch3.init()
#             self.urukul1_ch3.set_att(0 * dB)
#             self.urukul1_ch3.set(frequency=200 * MHz, amplitude=0.8, phase_mode=2)
#             self.urukul1_ch3.sw.off()
#
#             # 355 Raman 1
#             self.urukul2_ch0.init()
#             self.urukul2_ch0.set_att(0 * dB)
#             self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
#             self.urukul2_ch0.sw.off()
#
#             # 355 Raman 2
#             self.ttl6.output()
#
#             # AWG trigger
#             self.ttl5.output()
#
#             # Camera shutter
#             self.ttl4.output()
#
#             # 355 Raman 1 channel2 dual tone application
#             self.urukul2_ch1.init()
#             self.urukul2_ch1.set_att(0 * dB)
#             self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
#             self.urukul2_ch1.sw.off()
#
#             self.sum_rising_edges = 0.0
#
#             # self.sum_rising_edges_cooling = 0.0
#
#             # warming up detection and Doppler AOM
#             self.urukul0_ch1.sw.on()
#             self.urukul0_ch3.sw.on()
#             self.urukul1_ch3.sw.on()
#             self.urukul1_ch1.sw.on()
#             delay(5 * ms)
#             self.urukul0_ch1.sw.off()
#             self.urukul0_ch3.sw.off()
#             self.urukul1_ch3.sw.off()
#             self.urukul1_ch1.sw.off()
#
#             # Cooling shot: 1 extra ttl trigger from the camera just before the entire exp sequence
#             if checkGlobalCoolingShot and checkCameraDetection:
#                 self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
#                 self.urukul0_ch1.sw.on()
#                 self.urukul0_ch2.sw.on()
#                 self.urukul1_ch3.sw.on()  # protection on
#
#                 self.ttl4.on()  # camera trigger
#                 delay(cameraCoolingShotTime)
#                 self.ttl4.off()
#
#                 delay(11 * ms)  # Need this delay for camera acquisition.
#                 self.urukul0_ch1.sw.off()
#                 self.urukul0_ch2.sw.off()
#                 self.urukul1_ch3.sw.off()  # protection off
#
#         for i in range(num_repeat):
#             # delay(30 * us)  # This delay will exist between repetitions
#             self.core.break_realtime()
#             # self.ttl5.on()
#
#             self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
#             self.urukul0_ch2.sw.on()
#             self.urukul1_ch3.sw.on()  # protection on
#
#             if checkCameraDetection:
#                 delay(6 * ms)
#             else:
#                 delay(doppler_time)
#
#             self.urukul0_ch1.sw.off()
#             self.urukul0_ch2.sw.off()
#
#             self.urukul1_ch3.sw.off()  # protection off
#
#             if SBCTime > 0.1 * us:
#
#                 # # # # # Outer 1
#                 self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
#                 for cyc in range(50):
#                     self.urukul2_ch0.sw.on()
#                     self.ttl6.on()
#                     delay(SBCTime)
#                     # delay(0.012*ms)
#                     # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
#                     self.urukul2_ch0.sw.off()
#                     self.ttl6.off()
#                     self.urukul1_ch1.sw.on()
#                     delay(0.05 * ms)  # prev 0.03ms need strong OP power
#                     self.urukul1_ch1.sw.off()
#
#                 # # # # # Inner 1
#                 # # # #
#                 self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
#                 for cyc in range(60):
#                     self.urukul2_ch0.sw.on()
#                     self.ttl6.on()
#                     # self.ttl5.on()
#                     delay(SBCTime)
#                     self.urukul2_ch0.sw.off()
#                     self.ttl6.off()
#                     self.urukul1_ch1.sw.on()
#                     delay(0.05 * ms)
#                     self.urukul1_ch1.sw.off()
#                 # # # # #
#                 # #  # # # Outer1 2nd stage
#                 self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
#                 for cyc in range(25):
#                     self.urukul2_ch0.sw.on()
#                     self.ttl6.on()
#                     delay(0.03 * ms)
#                     # delay(SBCTime)
#                     # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
#                     self.urukul2_ch0.sw.off()
#                     self.ttl6.off()
#                     self.urukul1_ch1.sw.on()
#                     delay(0.05 * ms)  # prev 0.03ms need strong OP power
#                     self.urukul1_ch1.sw.off()
#                 # # # # # # #
#                 # # # # # # # # #
#                 # # # # # # # Inner1 2nd stage
#                 self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
#                 for cyc in range(15):
#                     self.urukul2_ch0.sw.on()
#                     self.ttl6.on()
#                     # self.ttl5.on()
#                     delay(0.02 * ms)
#                     self.urukul2_ch0.sw.off()
#                     self.ttl6.off()
#                     self.urukul1_ch1.sw.on()
#                     delay(0.05 * ms)
#                     self.urukul1_ch1.sw.off()
#
#             # self.ttl5.on()
#             # OP state prep with 935
#             if OP_time > 0.01 * us:
#                 # self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
#                 # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
#                 # self.urukul1_ch1.set_att(0 * dB)
#                 # self.urukul0_ch2.set_att(0 * dB)
#                 self.urukul1_ch1.sw.on()
#
#                 delay(OP_time)
#                 # delay(0.05* ms)
#                 delay_mu(1)
#
#                 self.urukul1_ch1.sw.off()
#
#             # self.ttl5.off()
#             # delay(-1*us) # important for syncing. Must be before setting up the DDS config or else there is some gradual ampltiude ramp of 435 DDS
#
#             if RamseyCheck == True and not EnableAWG:
#
#
#                 # Raman Ramsey
#
#                 # # Ramsey first pi/2
#                 self.urukul1_ch2.set_att(0 * dB)
#                 self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=0.0, amplitude=RamseyAmplitude435,
#                                      phase_mode=2)
#                 # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
#                 self.urukul2_ch0.set_att(0 * dB)
#                 self.urukul2_ch0.sw.on()
#                 self.ttl6.on()
#                 delay(0.3 * us)  # AOM delay
#                 delay(PiBy2Time435_1)
#                 # delay(Raman_time)
#                 # delay_mu(1)
#                 # self.urukul1_ch2.set_att(30 * dB)
#
#                 self.urukul2_ch0.sw.off()
#                 self.ttl6.off()
#
#
#                 delay(wait_time)
#                 delay_mu(1)
#
#
#                 # # # Ramsey second pi/2
#                 # # # delay(10 * us)
#                 self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=phase1, amplitude=RamseyAmplitude435,
#                                      phase_mode=2)
#                 # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
#                 # self.urukul1_ch2.set_att(0 * dB)
#                 self.urukul2_ch0.set_att(0 * dB)
#                 self.urukul2_ch0.sw.on()
#                 self.ttl6.on()
#                 delay(0.6 * us)  # AOM delay
#                 delay(PiBy2Time435_2)
#                 # delay(Raman_time)
#                 # delay_mu(1)
#                 self.urukul2_ch0.sw.off()
#                 self.ttl6.off()
#
#             # 435 interaction
#             self.urukul0_ch2.sw.off()  # 935/760 repumper
#             self.urukul1_ch0.sw.off()  # 976 repumper
#
#
#             if RamseyCheck and EnableAWG:
#                 self.zotino0.write_dac(31, 0.0)  # set and turn z0ch31 to 0 V (switch to AWG)
#                 self.zotino0.load()
#                 delay(0.5 * ms)
#
#                 self.ttl5.on()  # trigger to AWG/ Raman 1
#                 self.ttl6.on()  # Raman 2 on
#                 delay(0.3 * us)  # AOM delay
#                 delay(Raman_time)
#                 self.ttl6.off()  # Raman 2 off
#
#                 # self.ttl5.on()
#                 # delay(wait_time*1e-3)
#
#                 delay(wait_time)
#
#                 # delay(Raman_time) # diagnostic
#                 # self.ttl5.off()
#
#                 self.ttl6.on()  # Raman 2 on
#                 delay(0.3 * us)  # AOM delay
#                 delay(Raman_time)
#                 self.ttl6.off()  # Raman 2 off
#
#                 self.ttl5.off()
#
#                 # delay(0.5 * ms)
#                 self.zotino0.write_dac(31, 5.0)  # set back to DDS
#                 self.zotino0.load()
#                 delay(0.5 * ms)
#
#             # MW interaction
#             if MW_time > 0.01 * us:
#                 self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
#                 # self.urukul1_ch2.set_att(0 * dB)
#                 self.urukul1_ch2.set_att(0 * dB)
#                 self.urukul1_ch2.sw.on()
#                 delay(MW_time)
#                 delay_mu(1)
#                 self.urukul1_ch2.sw.off()
#
#             if checkAllZ_calib and AllZ_calib_flag:
#                 # Raman 1 ch 1
#                 self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
#                 self.urukul2_ch0.set_att(0 * dB)
#                 self.urukul2_ch0.sw.on()  # Raman 1
#                 self.ttl6.on()  # Raman 2
#                 delay(0.3 * us)  # AOM delay
#
#                 delay(self.AllZ_calib_Raman_t)
#
#                 self.urukul2_ch0.sw.off()  # Raman 1
#                 self.ttl6.off()  # Raman 25*us
#
#             # Raman
#             if Raman_time > 0.01 * us and not EnableAWG and not RamseyCheck and not AllZ_calib_flag:
#                 delay(0.001 * ms)
#
#                 # Raman 1 ch 1
#                 self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
#                 self.urukul2_ch0.set_att(0 * dB)
#                 self.urukul2_ch0.sw.on()  # Raman 1
#                 self.ttl6.on()  # Raman 2
#                 # self.ttl5.on() # AWG trigger
#                 delay(0.3 * us)  # AOM delay
#
#                 delay(Raman_time)
#
#                 self.urukul2_ch0.sw.off()  # Raman 1
#                 self.ttl6.off()  # Raman 25*us
#                 # self.ttl5.off() # AWG trigger
#
#             # AWG Raman
#             if EnableAWG and not RamseyCheck:
#                 self.zotino0.write_dac(31, 0.0)  # set and turn z0ch31 to 0 V (switch to AWG)
#                 self.zotino0.load()
#                 delay(0.5 * ms)
#
#                 self.ttl5.on()  # trigger to AWG/ Raman 1
#                 self.ttl6.on()  # Raman 2 on
#                 delay(0.3 * us)  # AOM delay
#                 delay(Raman_time)
#                 self.ttl6.off()  # Raman 2 off
#                 self.ttl5.off()
#
#                 delay(0.5 * ms)
#                 self.zotino0.write_dac(31, 5.0)  # set back to DDS
#                 self.zotino0.load()
#                 delay(0.5 * ms)
#
#             # Detection w. 935
#             if det_time > 0.01 * us:
#                 # self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
#                 self.urukul0_ch3.sw.on()
#                 if checkCameraDetection:
#                     self.ttl4.on()  # camera
#                 self.ttl.gate_rising(det_time)
#                 if checkCameraDetection:
#                     self.ttl4.off()  # camera
#                 self.urukul0_ch3.sw.off()
#
#             # self.ttl5.off()
#
#             # Doppler + 760/935
#             # self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
#             # self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
#             # self.urukul0_ch1.set_att(0 * dB)
#             # self.urukul0_ch2.set_att(0 * dB)
#             self.urukul0_ch1.sw.on()
#             self.urukul0_ch2.sw.on()
#             self.urukul1_ch3.sw.on()
#
#             # delay(20 * ms) # for 976 and 760
#
#             if checkCameraDetection and SBCTime <= 0.1 * us:
#                 delay(5 * ms)  # important for 411 and camera based detection
#             elif checkCameraDetection and SBCTime > 0.1 * us:
#                 delay(2 * ms)
#
#             if checkAllZ_calib and AllZ_calib_flag:
#                 self.AllZ_calib_histpoints[i] = self.ttl.fetch_count()
#             else:
#                 self.histpoints[i] = self.ttl.fetch_count()  # I think can only be called once per gate event or blocks function until counts is available

    @rpc # Checked; it is implemented in prepare()
    def cameraCOMM_prescan(self):
        # -----------------------------------------------------------------
        # PHASE 1: Send Scan Data (x_data)
        # -----------------------------------------------------------------
        print("--- PHASE 1: Sending Scan Data ---")
        try:
            # Create a socket and connect to the server
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                print(f"Connecting to {self.cameraHOST}:{self.cameraPORT}...")
                s.connect((self.cameraHOST, self.cameraPORT))

                # 1. Prepare and send the x_data list as JSON
                data_payload = json.dumps(self.send_datapacket).encode('utf-8')
                print(f"Sending data packet with x_data with {len(self.send_datapacket['x']['value'])} points.")
                s.sendall(data_payload)

                # 2. Wait for the "received" confirmation
                confirmation = s.recv(1024)
                if confirmation == b"received":
                    print("Server confirmed receipt.")

                else:
                    print(f"Warning: Expected 'received', got: {confirmation}")

        except Exception as e:
            print(f"!!! ERROR in Phase 1: {e}")
            print("Could not send scan data. Is the camera GUI running and 'Acquire' clicked?")
            exit()  # Exit the script if Phase 1 fails
            
    @rpc
    def cameraCOMM_postscan(self):
        # -----------------------------------------------------------------
        # PHASE 2: Receive ROI Data
        # -----------------------------------------------------------------
        print("\n--- PHASE 2: Receiving ROI Data ---")
        self.received_data_dict = {}
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                print(f"Connecting to {self.cameraHOST}:{self.cameraPORT}...")
                s.connect((self.cameraHOST, self.cameraPORT))
                s.settimeout(10.0)  # Set a timeout

                # 1. Send the "ready" ping
                print("Sending 'ready' ping to server.")
                s.sendall(b"ready")

                # 2. Receive the length first (read until newline)
                data_len_str = b""
                while True:
                    char = s.recv(1)
                    if char == b'\n':
                        break
                    if not char:
                        raise ConnectionAbortedError("Connection closed while reading length")
                    data_len_str += char

                data_len = int(data_len_str.decode('utf-8'))
                print(f"Server is sending {data_len} bytes...")

                # 3. Receive exactly that many bytes
                data_buffer = b""
                bytes_received = 0
                while bytes_received < data_len:
                    remaining = data_len - bytes_received
                    chunk = s.recv(4096 if remaining > 4096 else remaining)
                    if not chunk:
                        raise ConnectionAbortedError("Connection closed - data incomplete")
                    data_buffer += chunk
                    bytes_received += len(chunk)

                print(f"Received {bytes_received} bytes.")

                # 4. Decode the JSON data (now a dictionary)
                self.received_data_dict = json.loads(data_buffer.decode('utf-8'))

                # 5. Send "received" confirmation back
                print("Sending 'received' confirmation.")
                s.sendall(b"received")

        except socket.timeout:
            print("!!! Socket timed out during Phase 2.")
            exit()
        except Exception as e:
            print(f"!!! ERROR in Phase 2: {e}")
            exit()

        # --- NEW DATA PROCESSING ---
        print("\n--- Process Complete ---")
        if self.received_data_dict:
            print("Successfully received data dictionary. Loading to dataset.pyon")
            self.set_dataset('Camera.y', json.dumps(self.received_data_dict), persist=True)

            # Loop through ROI keys
            for key, roi_data in self.received_data_dict.items():

                print(f"\n--- Data for {key} ---")
                print(f"  ROI Position (x,y,w,h): {roi_data.get('roi pos')}")
                print(f"  Threshold: {roi_data.get('threshold')}")

                y_values = roi_data.get('value', [[]])
                print(y_values)
                # print(f"  Y Mean: {y_values[:5][0]}... ({len(y_values[:][0])} points total)")
                # print(f"  Y Stderr: {y_values[:5][1]}... ({len(y_values[:][0])} points total)")

        else:
            print("No data was received.")
    @rpc
    def extractScanSequence(self):
        currentExpid=self.scheduler.expid

        currentExpidScan=(currentExpid['arguments'])['ndscan_params']
        currentExpidScanDict=json.loads(self.find_and_extract_object(currentExpidScan, "scan"))
        # note: a custom function is needed for dict extraction due to
        # flawed ndscan format for simple json.loads() to work

        if currentExpidScanDict["axes"]:
            scanAxes=(currentExpidScanDict["axes"][0]) # scan sequence in ndscan
            scanParamStr=scanAxes["fqn"].split(".")[-1] # str, parameter
            scanUnit=self._free_params[scanParamStr].unit # str, unit from FloatParam, not FloatParamHandle
            scanUnitScale=self._free_params[scanParamStr].scale # float, scaling
            scanParamSequence=np.linspace(scanAxes["range"]["start"],scanAxes["range"]["stop"],scanAxes["range"]["num_points"])
            scanParamSequenceRescaled=scanParamSequence/scanUnitScale
            scanText=scanParamStr+"|"+scanUnit
            return {"x":{"name":scanText,"value":scanParamSequenceRescaled.tolist()}}
        else:
            return {"x": {"name": "Step in place", "value": [0.0]}}

        #print(type(currentExpidScanDict))

    @rpc
    def find_and_extract_object(self,text_data, key):
        """
        Finds the first occurrence of a whole word 'key' (e.g., "scan"),
        finds the next '{', and extracts the full object string
        (including braces) until its matching '}'.
        """

        # 1. Find the whole word 'key'
        # We use \b for word boundaries so "scan" doesn't match "scanning"
        match = re.search(r'\b' + re.escape(key) + r'\b', text_data)

        if not match:
            print(f"Error: Key '{key}' not found.")
            return None

        # 2. Find the first '{' *after* the key
        try:
            start_brace_index = text_data.index('{', match.end())
        except ValueError:
            print(f"Error: No '{{' found after key '{key}'.")
            return None

        # 3. Track brace levels to find the matching '}'
        level = 1
        # Start scanning *after* the opening brace
        for i in range(start_brace_index + 1, len(text_data)):
            char = text_data[i]

            if char == '{':
                level += 1
            elif char == '}':
                level -= 1

            if level == 0:
                # We found the matching closing brace
                end_brace_index = i

                # Extract the full object string (including braces)
                object_string = text_data[start_brace_index: end_brace_index + 1]
                return object_string

        # If we reach here, the string was incomplete (no matching '}')
        print("Error: No matching '}' found.")
        return None

    def get_awg_globals(self) -> dict:
        """
        Scrapes all relevant AWG global variables from the datasets
        to send to the AWG server for cache verification.
        """
        # Define the standard keys for a Keysight M3202A (4 channels)
        # Adjust 'range(1, 5)' if you have more/fewer channels.
        channels = range(1, 5)
        params = ["T", "V", "ph"]
        # Add frequency params which might be f00, f01, etc.
        freq_params = [f"f{i}{j}" for i in range(4) for j in range(2)]

        # Build the list of expected keys
        keys_to_fetch = []
        for ch in channels:
            # Add basic params: AWG.ch1.T0, AWG.ch1.V0, etc.
            for p in params:
                for i in range(4):  # Assuming 4 segments/tones per channel
                    keys_to_fetch.append(f"AWG.ch{ch}.{p}{i}")
            # Add frequency params
            for fp in freq_params:
                keys_to_fetch.append(f"AWG.ch{ch}.{fp}")

        # Fetch values from Datasets
        current_globals = {}
        for key in keys_to_fetch:
            try:
                # We default to 0.0 if a dataset is missing to prevent crash
                val = self.get_dataset(key, default=0.0)
                current_globals[key] = float(val)
            except Exception:
                pass

        return current_globals

    @rpc
    def init_awg_connection(self, scan_info, global_vars):
        """
        Measures time from command leaving ARTIQ to response arriving.
        """
        HOST = "127.0.0.1"
        PORT = 5000

        if self.AWG_Mode == "preload":
            command = "PRELOAD_ALL_SCAN"
            print(f"[ARTIQ] Mode: PRELOAD. Sending load command...")
        else:
            command = "INIT_LIVE_SCAN"
            print(f"[ARTIQ] Mode: LIVE. Sending init command...")

        payload = {
            "command": command,
            "scan_info": scan_info,
            "globals": global_vars
        }

        try:
            # --- TIMER START: Command leaving ARTIQ ---
            t_start = time.time()

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(30.0)
                s.connect((HOST, PORT))
                s.recv(4096)  # Handshake
                s.sendall(pyon.encode(payload).encode('utf-8'))  # Send

                # Block until response arrives
                resp = pyon.decode(s.recv(4096).decode('utf-8'))

            # --- TIMER END: Response arrived ---
            self.t_init_roundtrip = time.time() - t_start

            if resp.get("status") in ["WAVEFORMS_LOADED", "READY_FOR_LIVE_SCAN"]:
                print(f"[ARTIQ] Init Success. Round-trip time: {self.t_init_roundtrip:.4f} s")
            else:
                raise RuntimeError(f"AWG Error: {resp.get('message')}")

        except Exception as e:
            print(f"[ARTIQ] CRITICAL: AWG Init failed: {e}")
            raise

    @rpc
    def load_awg_step_rpc(self, step_index, num_pts, num_reps):
        """
        Measures duration from leaving kernel until returning (RPC execution time).
        """
        HOST = "127.0.0.1"
        PORT = 5000
        payload = {
            "command": "LOAD_STEP",
            "step_index": step_index, # only this matters to the awg for loading scan point
            "num_pts": num_pts, # not needed on awg side for loading scan point
            "num_reps": num_reps # not needed on awg side for loading scan point
        }

        # --- TIMER START: Leaving Kernel (approx) ---
        t_start = time.time()

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))
                s.recv(4096)
                s.sendall(pyon.encode(payload).encode())

                # Block until AWG confirms load
                resp = pyon.decode(s.recv(4096).decode())

                if resp.get("status") != "STEP_LOADED":
                    raise RuntimeError(f"AWG Load Step Failed: {resp}")
        except Exception as e:
            print(f"[ARTIQ] Error loading step {step_index}: {e}")
            raise

        # --- TIMER END: Returning to Kernel ---
        duration = time.time() - t_start

        # Safety check: Initialize if missing (e.g., if build() didn't run recently)
        if not hasattr(self, "t_step_durations"):
            self.t_step_durations = []

        self.t_step_durations.append(duration)

    @rpc
    def cleanup_awg(self):
        """
        Tells the AWG the scan is over (or aborted).
        Essential for 'live' mode to restore original values.
        If you terminate early, it restores the AWG
        """
        HOST = "127.0.0.1"
        PORT = 5000
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))
                s.recv(4096)
                s.sendall(pyon.encode({"command": "END_SCAN"}).encode())
                # Fire and forget - we don't strictly need to wait for reply on cleanup
        except Exception as e:
            print(f"[ARTIQ] Warning: AWG cleanup failed: {e}")

    @rpc
    def AllZcalibFitter(self): # -> TFloat:
        """
        Algebraic Parabolic Peak Finder.
        Fastest method for small scans (5-10 points). Works perfectly for low counts (0.0 to 0.5).
        """
        try:
            # 1. Convert to numpy for easier handling
            x = np.array(self.get_dataset('Calibrations.AllZ_calib_x'))
            y = np.array(self.get_dataset('Calibrations.AllZ_calib_y'))

            # 2. Find the index of the maximum value
            # This is our "coarse" guess
            i = np.argmax(y)
            center_val = x[i]

            # 3. Refine: Use neighbors to calculate exact peak (Parabolic Vertex)
            # We need at least one neighbor on each side (cannot be index 0 or last)
            if 0 < i < len(y) - 1:
                y_L = y[i - 1]  # Left neighbor
                y_C = y[i]  # Center (max)
                y_R = y[i + 1]  # Right neighbor

                # Denominator corresponds to the curvature (2nd derivative)
                # For a peak, (y_L - 2*y_C + y_R) should be negative.
                denom = y_L - 2 * y_C + y_R

                # Only fit if it looks like a peak (concave down), not a valley or flat line
                if denom < 0:
                    # The Magic Formula for the vertex of a parabola through 3 equidistant points
                    # offset = 0.5 * (y_L - y_R) / (y_L - 2*y_C + y_R)
                    offset_fraction = (y_L - y_R) / (2.0 * denom)

                    # Calculate step size (assuming uniform scan)
                    dx = x[i] - x[i - 1]

                    # Apply correction
                    refined_center = x[i] + (offset_fraction * dx)

                    # Safety Clamp: Don't let the fit wander more than 1 step away
                    # (This handles noise spikes preventing wild jumps)
                    if abs(refined_center - x[i]) <= dx:
                        center_val = refined_center

            # 4. Update the Dataset
            # The kernel will pick this up on the next iteration

            self.set_dataset("Calibrations.AllZ_calib_n", int(1), broadcast=True, archive=True, persist=True)
            self.set_dataset('Calibrations.AllZ_calib_max', center_val, broadcast=True, archive=True, persist = True)
            # self.mutate_dataset('Calibrations.AllZ_calib_max',center_val)
            # return center_val

        except Exception as e:
            # If something goes wrong, just keep the old value or print error
            print(f"AllZ Fitter Error: {e}")

    @kernel
    def uninterrupted_processes(self):
        # RR lock
        self.urukul2_ch2.set(frequency=self.RR_lock_Frequency, amplitude=self.RR_lock_Amp)
        self.urukul2_ch2.set_att(self.RR_lock_Att * dB)
        self.urukul2_ch2.sw.on()

        # 369 ULE
        self.urukul2_ch3.set(frequency=self.ULE_369_Frequency, amplitude=self.ULE_369_Amp)
        self.urukul2_ch3.set_att(self.ULE_369_Att * dB)
        self.urukul2_ch3.sw.on()

    # 26/01/15 gt: merely preloading AWG and feeding list into kernel; lists are populated in prepare()
    def run(self):

        # 1. Hardware Initialization (AWG)
        # We do this here so the connection is fresh when execution starts
        if self.awg_enabled and self.awg_scan_info:
            try:
                # self.trigger_awg_preload(...)
                self.init_awg_connection(self.awg_scan_info, self.awg_globals)
            except Exception as e:
                print(f"AWG Connection Failed: {e}")

        # 26/01/19 gt: for faster data transfer
        self.krun(self.scan_values, self.default_values, self.scan_index, self.iter_index)

    # 26/01/19 gt: for fast data transfer
    @kernel
    def krun(self, scan_vals, defaults, scan_idx, iter_idx):

        print("[DIAGNOSTIC] 1. Kernel Started (Entry)")

        # Track if we need to clean up (True = we are running, False = we finished safely)
        cleanup_needed = True

        # Assuming it's safe or pre-computed. If this fails, pass is_live_mode as an argument too.
        is_live_mode = (self.AWG_Mode == "live")
        awg_enabled = self.awg_enabled

        try:
            self.core.reset()
            # print("[DIAGNOSTIC] 2. Core Reset Complete")

            # Loop over the scan steps
            for i in range(len(scan_vals)):

                AllZ_calib_flag = False

                # AllZ autocalibration
                if self.checkAllZ_calib:
                    n = self.AllZ_calib_n_skip
                    AllZ_calib_flag = True
                    if i % n == 0:  # do calibration every nth scan point

                        # AllZ calibration scan
                        for j in range(self.AllZ_calib_num_pts):
                            self.core.break_realtime()
                            self.rid_termination()
                            self.uninterrupted_processes()

                            defaults[63] = 1.0  # AllZ_calib_flag (TRUE)
                            defaults[54] = self.allZ_calib_array[j]

                            # --- 4. Call ON (Physics) ---
                            # "defaults" is now a list of floats. Your ON() function must handle
                            # float-booleans (1.0 vs 0.0) or cast them at the start of ON().
                            # We cast booleans using (> 0.5) so ON receives strict bools
                            self.ON(
                                defaults[0], defaults[1], defaults[2], defaults[3], int(defaults[4]),
                                # Freq435... choice435(int)
                                defaults[5], defaults[6], defaults[7],  # Doppler
                                defaults[8], defaults[9], defaults[10],  # Det

                                defaults[11] > 0.5,  # checkCameraDetection
                                defaults[12] > 0.5,  # checkGlobalCoolingShot

                                defaults[13],
                                defaults[14], defaults[15],  # 935
                                defaults[16], defaults[17], defaults[18],  # prepOP
                                defaults[19], defaults[20], defaults[21],  # MW
                                defaults[22], defaults[23], defaults[24], defaults[25],  # SBC 355
                                defaults[26], defaults[27],  # SBCTime, Amp935
                                defaults[28], defaults[29],  # Clearout
                                defaults[30], defaults[31],  # Prep435
                                defaults[32],  # WaitTime

                                defaults[33] > 0.5,  # Ramseycheck

                                defaults[34], defaults[35],  # Phases
                                defaults[36], defaults[37], defaults[38],  # 355 switch

                                defaults[39] > 0.5,  # EnableAWG

                                defaults[40], defaults[41], defaults[42], defaults[43],  # Raman Freqs/Amps
                                defaults[44], defaults[45], defaults[46], defaults[47],  # RamanTime... Bz
                                defaults[48], defaults[49], defaults[50], defaults[51],  # Ramsey435
                                defaults[52], defaults[53], defaults[54],  # Endcap/Y/Z
                                defaults[55], defaults[56], defaults[57], defaults[58],  # Piezos
                                int(defaults[59]), int(defaults[60]),  # num_repeat, iter

                                defaults[61] > 0.5,  # checkLineTrigger

                                defaults[62] > 0.5,  # checkAllZ_calib
                                defaults[63] > 0.5 # Allz_calib_flag
                            )

                            # --- 5. Push Results ---
                            self.host_push_results(self.AllZ_calib_histpoints, j, AllZ_calib_flag)

                    AllZ_calib_flag = False
                    defaults[63] = 0.0

                    self.AllZcalibFitter()  # calls the fitter based on the values stored in the Calibrations dataset

                # --- 1. Update the Vector (The "Fast Swap") ---
                # Update 'iter' placeholder
                if iter_idx >= 0:
                    defaults[iter_idx] = float(i)

                # Update the 'scanned' parameter
                if scan_idx >= 0:
                    defaults[scan_idx] = scan_vals[i]

                # --- 2. Live Mode Hook ---
                # If we are in 'live' mode, we must load the waveform NOW.
                if awg_enabled and is_live_mode:
                    # Note: We use defaults[iter_idx] or simple calculation for num_reps if needed.
                    # Assuming defaults stores num_repeat somewhere (e.g., at index 60),
                    # but typically load_awg_step_rpc just needs 'i' and maybe 'total_steps'.
                    self.load_awg_step_rpc(i, len(scan_vals), 0)  # 0 is dummy for num_reps if rpc handles it

                # --- 3. Timing & Safety ---
                self.core.break_realtime()
                self.rid_termination()
                self.uninterrupted_processes()

                # --- 4. Call ON (Physics) ---
                # "defaults" is now a list of floats. Your ON() function must handle
                # float-booleans (1.0 vs 0.0) or cast them at the start of ON().
                # We cast booleans using (> 0.5) so ON receives strict bools
                self.ON(
                    defaults[0], defaults[1], defaults[2], defaults[3], int(defaults[4]),  # Freq435... choice435(int)
                    defaults[5], defaults[6], defaults[7],  # Doppler
                    defaults[8], defaults[9], defaults[10],  # Det

                    defaults[11] > 0.5,  # checkCameraDetection
                    defaults[12] > 0.5,  # checkGlobalCoolingShot

                    defaults[13],
                    defaults[14], defaults[15],  # 935
                    defaults[16], defaults[17], defaults[18],  # prepOP
                    defaults[19], defaults[20], defaults[21],  # MW
                    defaults[22], defaults[23], defaults[24], defaults[25],  # SBC 355
                    defaults[26], defaults[27],  # SBCTime, Amp935
                    defaults[28], defaults[29],  # Clearout
                    defaults[30], defaults[31],  # Prep435
                    defaults[32],  # WaitTime

                    defaults[33] > 0.5,  # Ramseycheck

                    defaults[34], defaults[35],  # Phases
                    defaults[36], defaults[37], defaults[38],  # 355 switch

                    defaults[39] > 0.5,  # EnableAWG

                    defaults[40], defaults[41], defaults[42], defaults[43],  # Raman Freqs/Amps
                    defaults[44], defaults[45], defaults[46], defaults[47],  # RamanTime... Bz
                    defaults[48], defaults[49], defaults[50], defaults[51],  # Ramsey435
                    defaults[52], defaults[53], defaults[54],  # Endcap/Y/Z
                    defaults[55], defaults[56], defaults[57], defaults[58],  # Piezos
                    int(defaults[59]), int(defaults[60]),  # num_repeat, iter

                    defaults[61] > 0.5,  # checkLineTrigger

                    defaults[62] > 0.5,  # checkAllZ_calib
                    defaults[63] > 0.5  # Allz_calib_flag
                )

                # --- 5. Push Results ---
                # We can't use self.histpoints here easily if it's not passed to kernel.
                # Usually host_push_results is an RPC.
                # Pass the CURRENT scan value (scan_vals[i]) and iteration (i).

                self.host_push_results(self.histpoints, i, AllZ_calib_flag)

            # If we get here, the loop finished naturally
            cleanup_needed = False

        finally:
            # This runs if the loop finishes OR if you click "Terminate"
            if awg_enabled and is_live_mode:
                if cleanup_needed:
                    print("ARTIQ: Scan Aborted. Cleaning up AWG...")
                else:
                    print("ARTIQ: Scan Finished. Cleaning up AWG...")

                # Always restore AWG to original state after a live scan
                self.cleanup_awg()


    @rpc(flags={"async"})
    def rid_termination(self):  # required to teriminate any barebones scan script mid scan upon clicking terminate instances
        rid = self.scheduler.rid
        if self.scheduler.check_termination(rid):
            self.scheduler.delete(rid)

    # 26/01/19 gt: for proper plotting
    # @rpc(flags={"async"})
    # def host_push_results(self, histpoints, i, AllZ_calib_flag = False):
    #     """
    #     Push data to the datasets and update the plot.
    #     'i' is the current iteration index (0, 1, 2...).
    #     """
    #
    #     if self.checkAllZ_calib and AllZ_calib_flag:
    #         x_val = self.allZ_calib_array[int(i)]
    #     else:
    #         x_val = self.plot_scan_arr[int(i)] # obtain the scan value with appropriate plotting units (see prepare())
    #                                        # time in ms, frequency in MHz, phase in multiples of 2*pi
    #
    #     # 1. Manage Raw Data History
    #     # If this is the first point, reset the history.
    #     if i == 0:
    #         self.scanHistogramList = [histpoints]  # Start a fresh list
    #     else:
    #         # Standard list append is much faster than np.vstack for growing data
    #         self.scanHistogramList.append(histpoints)
    #
    #     # 2. Calculate Plot Values (y_val and y_err)
    #     if self.CheckThresholding:
    #         # Binomial Statistics
    #         y_val, y_err = binom_onesided(np.sum(histpoints >= self.PMTThreshold), self.num_repeat)
    #     else:
    #         # Simple Mean Statistics
    #         y_val = np.mean(histpoints)
    #         y_err = y_val / np.sqrt(self.num_repeat)
    #
    #     # 3. Update Datasets (Handle Plotting)
    #     if i == 0:
    #         # --- First Point: Reset Datasets & Spawn Applet ---
    #         rid = getattr(self.scheduler, "rid", "Local")
    #         xlabel = f"{self.scan_param_name} [{self.scan_unit}]"
    #
    #         # Overwrite datasets to ensure we don't see data from the previous run
    #         self.set_dataset("ScanDataPlot.x_label", str(xlabel), broadcast=True, archive=True, persist=True)
    #
    #         if self.checkAllZ_calib and AllZ_calib_flag: # 26/01/30 gt: for AllZ calibration scan
    #             self.set_dataset("Calibrations.AllZ_calib_x", [x_val], broadcast=True, archive=True, persist=True)
    #             self.set_dataset("Calibrations.AllZ_calib_y", [y_val], broadcast=True, archive=True, persist=True)
    #             print(f"[DEBUG] Mean = {np.mean(histpoints)}")
    #             self.set_dataset("Calibrations.AllZ_calib_y_err", [y_err], broadcast=True, archive=True, persist=True)
    #         else:
    #             self.set_dataset("ScanDataPlot.x_vals", [x_val], broadcast=True, archive=True, persist=True)
    #             self.set_dataset("ScanDataPlot.y_vals", [y_val], broadcast=True, archive=True, persist=True)
    #             self.set_dataset("ScanDataPlot.yerr_vals", [y_err], broadcast=True, archive=True, persist=True)
    #
    #         # Create the Applet with the dynamic title
    #         command1 = (
    #             "${artiq_applet}plot_xy ScanDataPlot.y_vals "
    #             "--x ScanDataPlot.x_vals "
    #             "--error ScanDataPlot.yerr_vals "
    #             f"--title 'RID {rid}: Counts vs {xlabel}' "
    #         )
    #         self.ccb.issue("create_applet", "Barebones Scan Plot", command1)
    #
    #         # monitor peak of AllZ
    #         command2 = (
    #             "${artiq_applet}plot_xy Calibrations.AllZ_calib_y "
    #             "--x Calibrations.AllZ_calib_x "
    #             "--error Calibrations.AllZ_calib_y_err "
    #             f"--title 'RID {rid}: Counts vs AllZ [V]' "
    #         )
    #         self.ccb.issue("create_applet", "Barebones AllZ Monitor", command2)
    #     else:
    #         # --- Subsequent Points: Append Data ---
    #         if self.checkAllZ_calib and AllZ_calib_flag: # 26/01/30 gt: for AllZ calibration scan
    #             self.append_to_dataset("Calibrations.AllZ_calib_x", x_val)
    #             self.append_to_dataset("Calibrations.AllZ_calib_y", y_val)
    #             self.append_to_dataset("Calibrations.AllZ_calib_y_err", y_err)
    #         else:
    #             self.append_to_dataset("ScanDataPlot.x_vals", x_val)
    #             self.append_to_dataset("ScanDataPlot.y_vals", y_val)
    #             self.append_to_dataset("ScanDataPlot.yerr_vals", y_err)

    # 26/02/02 gt: plot handling based on original barebones
    @rpc(flags={"async"})
    def host_push_results(self, histpoints, i, AllZ_calib_flag=False):
        # 1. Determine if we are initializing a fresh dataset
        is_init_point = (int(i) == 0)

        if self.checkAllZ_calib and AllZ_calib_flag:
            x_val = self.allZ_calib_array[int(i)]
            # x_val = self.plot_scan_arr[int(i)]
            target_x = "Calibrations.AllZ_calib_x"
            target_y = "Calibrations.AllZ_calib_y"
            target_err = "Calibrations.AllZ_calib_y_err"
        else:
            x_val = self.plot_scan_arr[int(i)]
            target_x = "ScanDataPlot.x_vals"
            target_y = "ScanDataPlot.y_vals"
            target_err = "ScanDataPlot.yerr_vals"

        # 2. Statistics calculation
        if self.CheckThresholding:
            y_val, y_err = binom_onesided(np.sum(histpoints >= self.PMTThreshold), self.num_repeat)
            # if self.checkAllZ_calib and AllZ_calib_flag:
            #     y_val = self.get_dataset('Calibrations.AllZ_calib_max')
        else:
            y_val = np.mean(histpoints)
            y_err = y_val / np.sqrt(self.num_repeat)

        # 3. SMART DATASET HANDLING
        # Only reset the SPECIFIC dataset being used
        if is_init_point:
            self.set_dataset(target_x, [x_val], broadcast=True)
            self.set_dataset(target_y, [y_val], broadcast=True)
            self.set_dataset(target_err, [y_err], broadcast=True)

            rid = getattr(self.scheduler, "rid", "Local")
            xlabel = f"{self.scan_param_name} [{self.scan_unit}]"

            # Create the Applet with the dynamic title
            command1 = (
                "${artiq_applet}plot_xy ScanDataPlot.y_vals "
                "--x ScanDataPlot.x_vals "
                "--error ScanDataPlot.yerr_vals "
                f"--title 'RID {rid}: Counts vs {xlabel}' "
            )
            self.ccb.issue("create_applet", "Barebones Scan Plot", command1)

            # monitor peak of AllZ
            command2 = (
                "${artiq_applet}plot_xy Calibrations.AllZ_calib_y "
                "--x Calibrations.AllZ_calib_x "
                "--error Calibrations.AllZ_calib_y_err "
                f"--title 'RID {rid}: Counts vs AllZ [V]' "
            )
            # command2 = (
            #     "${artiq_applet}plot_xy Calibrations.AllZ_calib_y "
            #     "--x ScanDataPlot.x_vals "
            #     f"--title 'RID {rid}: Counts vs AllZ [V]' "
            # )
            self.ccb.issue("create_applet", "Barebones AllZ Monitor", command2)

        else:
            self.append_to_dataset(target_x, x_val)
            self.append_to_dataset(target_y, y_val)
            self.append_to_dataset(target_err, y_err)
    # def host_push_results(self, histpoints, i, AllZ_calib_flag=False):
    #     """
    #     Push data to the datasets and update the plot.
    #     'i' is the current iteration index (0, 1, 2...).
    #     """
    #
    #     # calibration vs scan
    #     if self.checkAllZ_calib and AllZ_calib_flag:
    #         x_val = self.allZ_calib_array[int(i)]
    #     else:
    #         x_val = self.plot_scan_arr[int(i)]  # obtain the scan value with appropriate plotting units (see prepare())
    #         # time in ms, frequency in MHz, phase in multiples of 2*pi
    #
    #     # 1. Manage Raw Data History
    #     # If this is the first point, reset the history.
    #     if i == 0:
    #         self.scanHistogramList = [histpoints]  # Start a fresh list
    #     else:
    #         # Standard list append is much faster than np.vstack for growing data
    #         self.scanHistogramList.append(histpoints)
    #
    #     # 2. Calculate Plot Values (y_val and y_err)
    #     if self.CheckThresholding:
    #         # Binomial Statistics
    #         y_val, y_err = binom_onesided(np.sum(histpoints >= self.PMTThreshold), self.num_repeat)
    #     else:
    #         # Simple Mean Statistics
    #         y_val = np.mean(histpoints)
    #         y_err = y_val / np.sqrt(self.num_repeat)
    #
    #     # 3. Update Datasets (Handle Plotting)
    #     if i == 0:
    #         # --- First Point: Reset Datasets & Spawn Applet ---
    #         rid = getattr(self.scheduler, "rid", "Local")
    #         xlabel = f"{self.scan_param_name} [{self.scan_unit}]"
    #
    #         # Overwrite datasets to ensure we don't see data from the previous run
    #         self.set_dataset("ScanDataPlot.x_label", str(xlabel), broadcast=True, archive=True, persist=True)
    #
    #         if self.checkAllZ_calib and AllZ_calib_flag:  # 26/01/30 gt: for AllZ calibration scan
    #             self.set_dataset("Calibrations.AllZ_calib_x", [x_val], broadcast=True, archive=True, persist=True)
    #             self.set_dataset("Calibrations.AllZ_calib_y", [y_val], broadcast=True, archive=True, persist=True)
    #             print(f"[DEBUG] Mean = {np.mean(histpoints)}")
    #             self.set_dataset("Calibrations.AllZ_calib_y_err", [y_err], broadcast=True, archive=True, persist=True)
    #         else:
    #             self.set_dataset("ScanDataPlot.x_vals", [x_val], broadcast=True, archive=True, persist=True)
    #             self.set_dataset("ScanDataPlot.y_vals", [y_val], broadcast=True, archive=True, persist=True)
    #             self.set_dataset("ScanDataPlot.yerr_vals", [y_err], broadcast=True, archive=True, persist=True)
    #
    #     else:
    #         # --- Subsequent Points: Append Data ---
    #         if self.checkAllZ_calib and AllZ_calib_flag:  # 26/01/30 gt: for AllZ calibration scan
    #             self.append_to_dataset("Calibrations.AllZ_calib_x", x_val)
    #             self.append_to_dataset("Calibrations.AllZ_calib_y", y_val)
    #             self.append_to_dataset("Calibrations.AllZ_calib_y_err", y_err)
    #         else:
    #             self.append_to_dataset("ScanDataPlot.x_vals", x_val)
    #             self.append_to_dataset("ScanDataPlot.y_vals", y_val)
    #             self.append_to_dataset("ScanDataPlot.yerr_vals", y_err)

        # if i == 0:
        #     # Create the Applet with the dynamic title
        #     command1 = (
        #         "${artiq_applet}plot_xy ScanDataPlot.y_vals "
        #         "--x ScanDataPlot.x_vals "
        #         "--error ScanDataPlot.yerr_vals "
        #         f"--title 'RID {rid}: Counts vs {xlabel}' "
        #     )
        #     self.ccb.issue("create_applet", "Barebones Scan Plot", command1)
        #
        #     # monitor peak of AllZ
        #     command2 = (
        #         "${artiq_applet}plot_xy Calibrations.AllZ_calib_y "
        #         "--x Calibrations.AllZ_calib_x "
        #         "--error Calibrations.AllZ_calib_y_err "
        #         f"--title 'RID {rid}: Counts vs AllZ [V]' "
        #     )
        #     self.ccb.issue("create_applet", "Barebones AllZ Monitor", command2)

    #-----Analyze-----#
    def save_global_dataset(self):
        '''
         Save all global dataset parameters in a dictionary here.
        '''

        parentdir = r"C:\Users\TrappedIonRice4\Documents\Artiq-Rice" # system dependent
        datasetdir = parentdir + "\dataset_db.pyon"
        self.globaldataset = {}
        f=open(datasetdir, 'r')
        txt=f.readlines()
        f.close() # must close the dataset file soon enough to reflect the updates.
        for ele in txt[1:-1]: #ignoring curly braces
            ele2 = ele.split(":") # some regex
            ele3 = (ele2[0].split('    '))[-1]
            ele4=''.join(list(ele3)[1:-1])
            self.globaldataset[ele4]=self.get_dataset(ele4)

    def analyze(self): # artiq barebone's postscan function, similar to host_cleaup() in ndscan

        # reinstantisate global dataset DC values
        DCcontrolId = {
            "file": "RFandDC/DCelectrodes.py",
            "class_name": "DC_Control",
            "arguments": {},
            "log_level": self.scheduler.expid["log_level"],
            "repo_rev": self.scheduler.expid["repo_rev"],
        }
        self.scheduler.submit("main", DCcontrolId)
        self.set_dataset('Histogram',self.scanHistogramList,broadcast=True, archive=True, persist=True)
        self.save_global_dataset()

        # camera roi data
        if self.checkCameraDetection:
            self.cameraCOMM_postscan()
    #--------------#
