
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
import math  # Make sure to add this at the top of your file


class BarebonesArtiqScan2DV1(EnvExperiment):
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
        self.setattr_device("urukul1_ch1")  # LOP
        self.setattr_device("urukul1_ch2")  # MW
        self.setattr_device("urukul1_ch3")  # Raman B2

        self.setattr_device("urukul2_cpld")  # Necessary for clock sync
        self.setattr_device("urukul2_ch0")  # Raman B1
        self.setattr_device("urukul2_ch1")  # Raman A16
        self.setattr_device("urukul2_ch2")  # OP
        self.setattr_device("urukul2_ch3")  # A15; was ULE369

        self.setattr_device("ttl4")  # Camera Trigger
        self.setattr_device("ttl5")  # AWG trigger
        self.setattr_device("ttl6")  # Raman 2 shutter
        self.setattr_device("ttl7") # DET switch

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
        self.originalEndcapAvg = self.get_dataset("Experiment_config.endcap_avg")
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


        # -----Detection-------#
        self.setattr_argument("checkCameraDetection", BooleanValue(default=False), group='Detection')
        self.setattr_argument("checkGlobalCoolingShot", BooleanValue(default=False), group='Detection')
        self.setattr_argument("CheckThresholding", BooleanValue(default=self.default_ThresholdCheck), group='Detection')
        self.setattr_argument("CenterScanMode", EnumerationValue(["linear", "center_out"], default="linear"),
                              group="Detection")
        self.setattr_argument("checkLineTrigger", BooleanValue(default=False), group='Detection')
        add_scannable("DetTime369", Scannable(NoScan(value=self.default_detectionTime), global_min=0.00001 * ms,
                                              global_step=1.0e-9 * ms, unit="ms", ndecimals=4), group='Detection')
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
                                unit="ms", ndecimals=4) ,group='MW')
        add_scannable("AmplitudeMW",
                      Scannable(NoScan(value=self.default_MWAmp),
                                global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                unit="", ndecimals=3), group='MW')
        # --------------------#


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


        # ------Raman---------#
        self.setattr_argument('EnableAWG', BooleanValue(default=False), group='Raman')
        self.setattr_argument("AWG_Mode", EnumerationValue(["preload", "live"], default="preload"),
                              group="Raman")
        self.setattr_argument('MScheck', BooleanValue(default=False), group='Raman')
        self.setattr_argument("B1check", BooleanValue(default=True), group='Raman')
        add_scannable("Frequency355_Raman1",
                      Scannable(NoScan(value=self.default_Raman1_freq),
                                global_min=100.0 * MHz, global_max=250.0 * MHz,
                                global_step=1.0e-9 * MHz, unit="MHz", ndecimals=7), group='Raman')
        add_scannable("Amplitude355_Raman1",
                      Scannable(NoScan(value=self.default_Raman1_amp),
                                global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                unit="", ndecimals=5), group='Raman')
        self.setattr_argument("A16check", BooleanValue(default=False), group='Raman')
        add_scannable("Frequency355_RamanA16",
                      Scannable(NoScan(value=self.default_RamanA16_freq),
                                global_min=100.0 * MHz, global_max=250.0 * MHz,
                                global_step=1.0e-9 * MHz, unit="MHz", ndecimals=7), group='Raman')
        add_scannable("Amplitude355_RamanA16",
                      Scannable(NoScan(value=self.default_RamanA16_amp),
                                global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                unit="", ndecimals=5), group='Raman')
        self.setattr_argument("B2check", BooleanValue(default=False), group='Raman')
        add_scannable("Frequency355_RamanB2",
                      Scannable(NoScan(value=self.default_RamanB2_freq),
                                global_min=100.0 * MHz, global_max=250.0 * MHz,
                                global_step=1.0e-9 * MHz, unit="MHz", ndecimals=7), group='Raman')
        add_scannable("Amplitude355_RamanB2",
                      Scannable(NoScan(value=self.default_RamanB2_amp),
                                global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                unit="", ndecimals=5), group='Raman')
        self.setattr_argument("A15check", BooleanValue(default=False), group='Raman')
        add_scannable("Frequency355_RamanA15",
                      Scannable(NoScan(value=self.default_RamanA15_freq),
                                global_min=100.0 * MHz, global_max=250.0 * MHz,
                                global_step=1.0e-9 * MHz, unit="MHz", ndecimals=7), group='Raman')
        add_scannable("Amplitude355_RamanA15",
                      Scannable(NoScan(value=self.default_RamanA15_amp),
                                global_min=0.0, global_max=0.8, global_step=1.0e-9,
                                unit="", ndecimals=5), group='Raman')
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
        add_scannable("endcap_avg",
                      Scannable(NoScan(value=self.default_endcap_avg), global_min=-9.0, global_max=9.0,
                                global_step=1.0e-9, unit="", ndecimals=3), group='Electrodes')
        add_scannable("allY",
                      Scannable(NoScan(value=self.default_allY), global_min=-9.0, global_max=9.0,
                                global_step=1.0e-9, unit="", ndecimals=3), group='Electrodes')
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
        self.default_RamanA16_freq = self.get_dataset("355_RamanA16.Frequency")
        self.default_RamanA16_amp = self.get_dataset("355_RamanA16.Amp")
        self.default_RamanB2_freq = self.get_dataset("355_RamanB2.Frequency")
        self.default_RamanB2_amp = self.get_dataset("355_RamanB2.Amp")
        self.default_RamanA15_freq = self.get_dataset("355_RamanA15.Frequency")
        self.default_RamanA15_amp = self.get_dataset("355_RamanA15.Amp")
        self.default_ThresholdCheck = bool(self.get_dataset("PMTCheckThreshold"))
        self.default_detectionTime = self.get_dataset("Detection.Time(ms)") * ms
        self.default_endcapX = self.get_dataset("Experiment_config.endcapX")
        self.default_endcap_avg = self.get_dataset("Experiment_config.endcap_avg")
        self.default_allY = self.get_dataset("Experiment_config.all_y")
        self.default_allZ = self.get_dataset("Experiment_config.all_z")
        self.default_PiezoR1H = self.get_dataset("355_Raman1.H1")
        self.default_PiezoR1V = self.get_dataset("355_Raman1.V1")
        self.default_PiezoR2H = self.get_dataset("355_Raman2.H2")
        self.default_PiezoR2V = self.get_dataset("355_Raman2.V2")


    # more elegant; works (26/07/17)
    def prepare(self):
        import time
        print("\n" + "=" * 40)
        print("STARTING TIMING PROFILE")
        print("=" * 40)

        t_start_all = time.time()

        # 1. Initialize core variables
        t0 = time.time()
        self._init_basics()
        print(f"1. Init Basics:          {time.time() - t0:.4f} seconds")

        # 2. Bulk fetch all static datasets
        t0 = time.time()
        self._fetch_static_datasets()
        print(f"2. Fetch Datasets:       {time.time() - t0:.4f} seconds")

        # 3. Determine what is being scanned
        t0 = time.time()
        self._setup_scan_parameters()
        print(f"3. Setup Scan Params:    {time.time() - t0:.4f} seconds")

        # 4. Initialize datasets for the GUI plots
        t0 = time.time()
        self._setup_plotting()
        print(f"4. Setup Plotting:       {time.time() - t0:.4f} seconds")

        # 5. Build the array of values passed to krun()
        t0 = time.time()
        self._build_kernel_arguments()
        print(f"5. Build Kernel Args:    {time.time() - t0:.4f} seconds")

        # 6. Configure camera TCP connection
        t0 = time.time()
        self._setup_camera()
        print(f"6. Setup Camera:         {time.time() - t0:.4f} seconds")

        self.t_f_def = time.time()
        print("-" * 40)
        print(f"TOTAL PREPARE TIME:      {self.t_f_def - t_start_all:.4f} seconds")
        print("=" * 40 + "\n")

    def _init_basics(self):
        self.num_repeat = self.get_dataset("Repetitions")
        self.histpoints = np.zeros(self.num_repeat, dtype=int)
        self.points = [[0.0] * self.num_repeat, [0.0] * self.num_repeat]
        self.PMTThreshold = self.get_dataset("PMTThreshold")
        self.scanHistogramList = []

        self.iter = 0
        self.modSBCtime = 0.0
        self.modpreptime = 0.0
        self.PiBy2Time435_1mod = 0.0
        self.PiBy2Time435_2mod = 0.0

    def _fetch_static_datasets(self):
        def numeric(x):
            if hasattr(x, "get"): return x.get()
            if hasattr(x, "value"): return x.value
            return float(x)

        # Format: (attribute_name, dataset_key, multiplier)
        datasets = [
            ("doppler_freq", "Doppler.Frequency", 1.0),
            # ("doppler_amp", "Doppler.Amp", 1.0),
            ("doppler_amp", "Experiment_config.DopplerAmp", 1.0),
            ("doppler_time", "Doppler.Time(ms)", ms),
            ("det_freq", "Detection.Frequency", 1.0),
            ("det_amp", "Detection.Amp", 1.0),
            ("det_time", "Detection.Time(ms)", ms),
            ("freq_935", "935.Frequency", 1.0),
            ("amp_935", "935.Amp", 1.0),
            ("attenuation_435_1", "435_1.Attenuation", 1.0),
            ("RamseyAmplitude435", "Ramsey.Amplitude435", 1.0),
            ("PiBy2Time435_1", "Ramsey.PiBy2Time435_1(ms)", ms),
            ("PiBy2Time435_2", "Ramsey.PiBy2Time435_2(ms)", ms),
            ("ULE_369_Amp", "369_ULE.Amp", 1.0),
            ("ULE_369_Frequency", "369_ULE.Frequency", 1.0),
            ("ULE_369_Att", "369_ULE.Attenuation", 1.0),
            ("cameraCoolingShotTime", "Camera.GlobalCoolingShotTime(ms)", ms),
        ]

        for attr, key, mult in datasets:
            setattr(self, attr, numeric(self.get_dataset(key)) * mult)

        # Handle composite datasets explicitly
        self.RamseyFrequency435mod = (numeric(self.get_dataset("Ramsey.Frequency435")) +
                                      numeric(self.get_dataset("Ramsey.Detuning435")))


    # restore AWG functionality
    def _setup_scan_parameters(self):
        import numpy as np

        def to_center_out(arr):
            sorted_arr = np.sort(arr)
            n = len(sorted_arr)
            mid = n // 2
            res = [sorted_arr[mid]]
            left, right = mid - 1, mid + 1
            while left >= 0 or right < n:
                if right < n:
                    res.append(sorted_arr[right])
                    right += 1
                if left >= 0:
                    res.append(sorted_arr[left])
                    left -= 1
            return np.array(res)

        self.scan_param_name = "step"
        self.scan_arr = np.array([0.0])
        self.scan_unit = ""

        self.is_2d_scan = False
        self.scan_param_y = None
        self.scan_arr_y = np.array([0.0])
        self.scan_unit_y = ""

        self.awg_enabled = getattr(self, "EnableAWG", False)
        self.awg_scan_info = None
        self.awg_globals = None

        scan_mode = getattr(self, "CenterScanMode", "linear")

        # --- RESTORED AWG LOGIC ---
        if self.awg_enabled:
            self.scan_param_name = self.get_dataset('AWG.Scan_Parameter.name')
            self.scan_arr = np.array(self.get_dataset('AWG.Scan_Parameter.array'))
            awg_scan_unit = self.get_dataset('AWG.Scan_Parameter.units')
            self.scan_unit = 'ms' if awg_scan_unit == 's' else ('MHz' if awg_scan_unit == 'Hz' else awg_scan_unit)

            # Catch 2D Variables
            self.is_2d_scan = self.get_dataset('AWG.Scan_Parameter.is_2D', default=False)
            if self.is_2d_scan:
                self.scan_param_y = self.get_dataset('AWG.Scan_Parameter.name_y')
                self.scan_arr_y = np.array(self.get_dataset('AWG.Scan_Parameter.array_y'))
                awg_scan_unit_y = self.get_dataset('AWG.Scan_Parameter.units_y')
                self.scan_unit_y = 'ms' if awg_scan_unit_y == 's' else (
                    'MHz' if awg_scan_unit_y == 'Hz' else awg_scan_unit_y)

                master_scan_vars = [str(self.scan_param_name), str(self.scan_param_y)]
            else:
                master_scan_vars = [str(self.scan_param_name)]

            # Fetch the unrolled grid for the AWG payload
            awg_unrolled_array = self.get_dataset('AWG.Scan_Parameter.unrolled_grid')

            try:
                num_repeat = getattr(self, "num_repeat", 100)
                self.awg_scan_info = {
                    "scan_variables": master_scan_vars,
                    "scan_array": awg_unrolled_array,  # Re-send the unrolled grid to hit the cache
                    "num_reps": num_repeat,
                    "is_2d": self.is_2d_scan
                }
                self.awg_globals = self.get_awg_globals()
            except Exception as e:
                print(f"AWG Setup Error in Prepare: {e}")

        # --- STANDARD ARTIQ ARGUMENT SCANS ---
        else:
            scanned_vars = []
            for name in getattr(self, "scannable_names", []):
                arg = getattr(self, name)

                if hasattr(arg, "value"):
                    setattr(self, name, arg.value)
                else:
                    try:
                        # Capture if the GUI 'Randomize' checkbox was ticked
                        is_random = getattr(arg, "randomize", False)
                        scan_values = np.array(list(arg))
                        if len(scan_values) > 1:
                            unit = getattr(self, "scannable_units", {}).get(name, "")
                            scanned_vars.append((name, scan_values, unit, is_random))
                    except TypeError:
                        continue

            # --- 1D SCAN HANDLING ---
            if len(scanned_vars) == 1:
                self.scan_param_name, self.scan_arr, self.scan_unit, is_random = scanned_vars[0]

                # Only sort/reorder if GUI randomization is disabled
                if not is_random:
                    if scan_mode == "linear":
                        self.scan_arr = np.sort(self.scan_arr)
                    elif scan_mode == "center_out":
                        is_monotonic = np.all(np.diff(self.scan_arr) >= 0) or np.all(np.diff(self.scan_arr) <= 0)
                        if is_monotonic:
                            self.scan_arr = to_center_out(self.scan_arr)

            # --- 2D SCAN HANDLING ---
            elif len(scanned_vars) >= 2:
                self.is_2d_scan = True
                self.scan_param_name, self.scan_arr, self.scan_unit, is_random_x = scanned_vars[0]
                self.scan_param_y, self.scan_arr_y, self.scan_unit_y, is_random_y = scanned_vars[1]

                if not is_random_x:
                    if scan_mode == "linear":
                        self.scan_arr = np.sort(self.scan_arr)
                    elif scan_mode == "center_out":
                        self.scan_arr = to_center_out(self.scan_arr)

                if not is_random_y:
                    if scan_mode == "linear":
                        self.scan_arr_y = np.sort(self.scan_arr_y)
                    elif scan_mode == "center_out":
                        self.scan_arr_y = to_center_out(self.scan_arr_y)

    def _setup_plotting(self):
        import numpy as np

        def format_plot_arr(scan_name, arr):
            name_lower = str(scan_name).lower()
            if ".t" in name_lower or 'time' in name_lower:
                return [float(x * 1e3) for x in arr]
            elif ".f" in name_lower or "frequency" in name_lower:
                return [float(x * 1e-6) for x in arr]
            return [float(x) for x in arr]

        # --- Step 1: Format Plot Arrays ---

        # A. Execution Order Array (Needed for 1D point-by-point appending)
        self.plot_scan_arr = format_plot_arr(self.scan_param_name, self.scan_arr)
        print("\nThe execution plot scan array (X) is:", self.plot_scan_arr, '\n')

        # B. Monotonic Sorted Arrays & Maps (Needed for 2D Heatmap Grid Bounds)
        sorted_x = np.sort(self.scan_arr)
        self.plot_scan_arr_sorted = format_plot_arr(self.scan_param_name, sorted_x)
        self.x_index_map = [int(np.where(sorted_x == val)[0][0]) for val in self.scan_arr]

        if getattr(self, "is_2d_scan", False):
            sorted_y = np.sort(self.scan_arr_y)
            self.plot_scan_arr_y_sorted = format_plot_arr(getattr(self, "scan_param_y", ""), sorted_y)
            self.y_index_map = [int(np.where(sorted_y == val)[0][0]) for val in self.scan_arr_y]

        # --- Step 2: Initialize Datasets ---
        self.set_dataset("ScanDataPlot.x_label", str(f"{self.scan_param_name} [{self.scan_unit}]"), broadcast=True,
                         archive=True, persist=True)
        self.set_dataset("ScanDataPlot.y_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ScanDataPlot.x_vals", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("ScanDataPlot.yerr_vals", [], broadcast=True, archive=True, persist=True)

        if getattr(self, "is_2d_scan", False):
            # 2D Heatmap MUST use the _sorted arrays to prevent axis warping
            self.set_dataset("ScanDataPlot.x_vals", self.plot_scan_arr_sorted, broadcast=True)
            self.set_dataset("ScanDataPlot.y_vals", self.plot_scan_arr_y_sorted, broadcast=True)

            num_x = len(self.scan_arr)
            num_y = len(self.scan_arr_y)

            # Initialize matrix with NaNs for center-out expansion
            self.z_mat = np.full((num_y, num_x), np.nan)

            self.set_dataset("ScanDataPlot.z_vals", self.z_mat, broadcast=True)
            self.set_dataset("ScanDataPlot.x_label", f"{self.scan_param_name} [{self.scan_unit}]", broadcast=True)
            self.set_dataset("ScanDataPlot.y_label",
                             f"{getattr(self, 'scan_param_y', 'Y')} [{getattr(self, 'scan_unit_y', '')}]",
                             broadcast=True)

        # --- Step 3: AllZ Calibration Datasets ---
        width = self.get_dataset('Calibrations.AllZ_calib_width')
        self.AllZ_calib_num_pts = int(self.get_dataset('Calibrations.AllZ_calib_num_pts'))
        self.AllZ_calib_n_skip = int(self.get_dataset('Calibrations.AllZ_calib_n'))
        self.AllZ_calib_max = self.get_dataset('Calibrations.AllZ_calib_max')
        self.AllZ_calib_Raman_t = self.get_dataset('Calibrations.AllZ_calib_Raman_t')
        self.allZ_calib_array = np.linspace(self.AllZ_calib_max - width / 2, self.AllZ_calib_max + width / 2,
                                            self.AllZ_calib_num_pts)
        self.AllZ_calib_histpoints = np.zeros(self.num_repeat, dtype=int)

        self.set_dataset("Calibrations.AllZ_calib_x", self.allZ_calib_array, broadcast=True, archive=True, persist=True)
        self.set_dataset("Calibrations.AllZ_calib_y", [], broadcast=True, archive=True, persist=True)
        self.set_dataset("Calibrations.AllZ_calib_y_err", [], broadcast=True, archive=True, persist=True)

    def _build_kernel_arguments(self):
        # Order must match 'krun' signature exactly
        self.on_params = [
            "Frequency435", "Amplitude435", "Time435", "attenuation_435_1", "choice435channel_1_2",
            "doppler_freq", "doppler_amp", "doppler_time",
            "det_freq", "det_amp", "DetTime369", "checkCameraDetection",
            "checkGlobalCoolingShot", "cameraCoolingShotTime",
            "freq_935", "amp_935",
            "prepfreqOP", "prepampOP", "preptimeOP",
            "prepfreqLOP", "prepampLOP", "preptimeLOP",
            "FrequencyMW", "AmplitudeMW", "TimeMW",
            "SBCcheck", "SBCFrequency355_1", "SBCAmplitude355_1",
            "SBCFrequency355_2", "SBCAmplitude355_2",
            "SBCTime", "SBCAmplitude935",
            "ClearoutPower935", "ClearoutTime935",
            "prepfreq435", "preptime",
            "WaitTime", "Ramseycheck", "Phase1", "Phase2",
            "EnableAWG", "MScheck",
            "B1check", "Frequency355_Raman1", "Amplitude355_Raman1",
            "A16check", "Frequency355_RamanA16", "Amplitude355_RamanA16",
            "B2check", "Frequency355_RamanB2", "Amplitude355_RamanB2",
            "A15check", "Frequency355_RamanA15", "Amplitude355_RamanA15",
            "RamanTime", "LighShiftFactor_BSB", "GlobalSidebandAmpScale", "Bz",
            "RamseyFrequency435mod", "RamseyAmplitude435",
            "PiBy2Time435_1", "PiBy2Time435_2",
            "endcapX", "allY", "allZ", "endcap_avg",
            "piezoR1H", "piezoR1V", "piezoR2H", "piezoR2V",
            "num_repeat", "iter", "checkLineTrigger", "checkAllZ_calib", 'AllZ_calib_flag'
        ]

        param_to_attr = {
            "Attenuation_435": "attenuation_435_1",
            "choice435": "choice435channel_1_2",
            "OP_freq": "prepfreqOP",
            "OP_amp": "prepampOP",
            "OP_time": "preptimeOP",
            "LOP_freq": "prepfreqLOP",
            "LOP_amp": "prepampLOP",
            "LOP_time": "preptimeLOP",
            "MW_freq": "FrequencyMW",
            "MW_amp": "AmplitudeMW",
            "MW_time": "TimeMW",
            "wait_time": "WaitTime",
            "RamseyCheck": "Ramseycheck",
            "phase1": "Phase1",
            "phase2": "Phase2",
            "FrequencyRaman1": "Frequency355_Raman1",
            "AmplitudeRaman1": "Amplitude355_Raman1",
            "FrequencyRamanA16": "Frequency355_RamanA16",
            "AmplitudeRamanA16": "Amplitude355_RamanA16",
            "FrequencyRamanB2": "Frequency355_RamanB2",
            "AmplitudeRamanB2": "Amplitude355_RamanB2",
            "FrequencyRamanA15": "Frequency355_RamanA15",
            "AmplitudeRamanA15": "Amplitude355_RamanA15",
            "Raman_time": "RamanTime",
            "LighShiftFactor": "LighShiftFactor_BSB",
            "RamseyFrequency435": "RamseyFrequency435mod",
            "newEndcapX": "endcapX",
            "newAllY": "allY",
            "newAllZ": "allZ",
            "endcapAvg_V": "endcap_avg",
            "piezo_R1H": "piezoR1H",
            "piezo_R1V": "piezoR1V",
            "piezo_R2H": "piezoR2H",
            "piezo_R2V": "piezoR2V",
            "iterScan": "iter"
        }

        # Detect if target parameter is explicitly an AWG parameter
        raw_x = getattr(self, "scan_param_name", "")
        raw_y = getattr(self, "scan_param_y", "") if getattr(self, "is_2d_scan", False) else ""
        is_awg_scan = getattr(self, "awg_enabled", False) and ("AWG" in raw_x or "AWG" in raw_y)

        # 1. Enforce 2D Axis Priority Swap
        if getattr(self, "is_2d_scan", False):
            priority_order = [
                "AWG.ch1.T0", "AWG.ch2.T0", "AWG.ch3.T0", "AWG.ch4.T0",
                "AWG.ch1.T1", "AWG.ch2.T1", "AWG.ch3.T1", "AWG.ch4.T1",
                "Raman_time", "RamanTime", "wait_time", "WaitTime", "TimeMW", "preptime",
                "AWG.ch1.V0", "AWG.ch2.V0", "AWG.ch3.V0", "AWG.ch4.V0",
                "AWG.ch1.Amp", "AWG.ch2.Amp", "AWG.ch3.Amp", "AWG.ch4.Amp",
                "AmplitudeRaman1", "Amplitude355_Raman1",
                "FrequencyRaman1", "Frequency355_Raman1"
            ]

            def get_priority(param_str):
                for rank, key in enumerate(priority_order):
                    if key in param_str:
                        return rank
                return 999

            rank_x = get_priority(raw_x)
            rank_y = get_priority(raw_y)

            if rank_y < rank_x:
                print(f"[AXIS SWAPPER] Swapping Y ({raw_y}) to X-axis to enforce priority!")
                self.scan_param_name, self.scan_param_y = raw_y, raw_x
                self.scan_arr, self.scan_arr_y = self.scan_arr_y, self.scan_arr

                if hasattr(self, "plot_scan_arr") and hasattr(self, "plot_scan_arr_y"):
                    self.plot_scan_arr, self.plot_scan_arr_y = self.plot_scan_arr_y, self.plot_scan_arr
                if hasattr(self, "plot_scan_arr_sorted") and hasattr(self, "plot_scan_arr_y_sorted"):
                    self.plot_scan_arr_sorted, self.plot_scan_arr_y_sorted = (
                        self.plot_scan_arr_y_sorted,
                        self.plot_scan_arr_sorted,
                    )
                if hasattr(self, "x_index_map") and hasattr(self, "y_index_map"):
                    self.x_index_map, self.y_index_map = self.y_index_map, self.x_index_map

                self.z_mat = np.full((len(self.scan_arr_y), len(self.scan_arr)), np.nan)

        # Setup Targets
        self.num_points = len(self.scan_arr)
        kernel_scan_target = getattr(self, "scan_param_name", "")
        if kernel_scan_target in param_to_attr:
            kernel_scan_target = param_to_attr[kernel_scan_target]

        kernel_scan_target_y = getattr(self, "scan_param_y", "")
        if kernel_scan_target_y in param_to_attr:
            kernel_scan_target_y = param_to_attr[kernel_scan_target_y]

        # Remap AWG targets to native internal variables
        if is_awg_scan:
            awg_map = {
                "AWG.ch1.T0": "RamanTime", "AWG.ch2.T0": "RamanTime", "AWG.ch3.T0": "RamanTime",
                "AWG.ch4.T0": "RamanTime", "AWG.ch1.T1": "WaitTime",
                "AWG.ch1.V0": "Amplitude355_Raman1", "AWG.ch2.V0": "Amplitude355_RamanA16",
                "AWG.ch3.V0": "Amplitude355_RamanB2", "AWG.ch4.V0": "Amplitude355_RamanA15"
            }
            for awg_var, raman_var in awg_map.items():
                if awg_var in kernel_scan_target:
                    kernel_scan_target = raman_var
                    break
            if self.is_2d_scan:
                for awg_var, raman_var in awg_map.items():
                    if awg_var in kernel_scan_target_y:
                        kernel_scan_target_y = raman_var
                        break

        overrides = {}
        if not getattr(self, "SBCcheck", False): overrides["SBCTime"] = 0.0
        if not getattr(self, "StatePrep", False): overrides["preptime"] = 0.0
        if not getattr(self, "Ramseycheck", False): overrides["PiBy2Time435_1"] = 0.0; overrides["PiBy2Time435_2"] = 0.0

        self.default_values = []
        self.scan_values = []
        self.scan_values_y = [0.0]
        self.scan_index = -1
        self.scan_index_y = -1
        self.iter_index = -1

        internal_to_gui = {v: k for k, v in param_to_attr.items()}

        for idx, name in enumerate(self.on_params):
            val = 0.0
            if name in overrides:
                val = overrides[name]
            elif name == "iter":
                val = 0.0;
                self.iter_index = idx
            elif name == "num_repeat":
                val = float(self.num_repeat)
            elif name == "EnableAWG":
                # Enable AWG in kernel ONLY if this is an AWG scan
                val = 1.0 if is_awg_scan else 0.0
            elif name == "RamanTime" and is_awg_scan:
                val = self.get_dataset("AWG.ch1.T0")
            elif name == "WaitTime" and is_awg_scan:
                val = self.get_dataset("AWG.ch1.T1")
            elif name == 'allZ' and getattr(self, "checkAllZ_calib", False):
                val = self.get_dataset('Calibrations.AllZ_calib_max')
            else:
                gui_attr_name = internal_to_gui.get(name, name)
                if hasattr(self, gui_attr_name):
                    raw_val = getattr(self, gui_attr_name)
                elif hasattr(self, name):
                    raw_val = getattr(self, name)
                else:
                    raw_val = 0.0

                if hasattr(raw_val, "value"):
                    val = raw_val.value
                elif hasattr(raw_val, "__iter__") and not isinstance(raw_val, (str, bytes)):
                    val = list(raw_val)[0]
                else:
                    try:
                        val = float(raw_val)
                    except (TypeError, ValueError):
                        val = 0.0

            if isinstance(val, (bool, np.bool_)): val = 1.0 if val else 0.0
            self.default_values.append(float(val))

            # Check for X mapping
            if name == kernel_scan_target:
                self.scan_index = idx
                self.scan_values = [float(x) for x in self.scan_arr]

            # Check for Y mapping
            if getattr(self, "is_2d_scan", False) and name == kernel_scan_target_y:
                self.scan_index_y = idx
                self.scan_values_y = [float(y) for y in self.scan_arr_y]

        if len(self.scan_values) == 0:
            self.scan_values = [0.0] * self.num_points

        # Safety check to prevent -1 trap
        if self.scan_index == -1:
            print(f"[WARNING] Scan target '{kernel_scan_target}' was not matched to any kernel parameter!")

        for idx, name in enumerate(self.on_params):
            setattr(self, f"idx_{name}", idx)

    def _setup_camera(self):
        self.cameraHOST = '127.0.0.6'
        self.cameraPORT = 65438

        self.run_camera_detection = bool(getattr(self, 'checkCameraDetection', False))
        self.set_dataset('Camera.Check', self.run_camera_detection, broadcast=True, persist=True, archive=True)

        if self.run_camera_detection:
            camera_vals = np.array(self.scan_arr)
            unit_str = getattr(self, "scan_unit", "arb")

            if unit_str == "ms":
                camera_vals = camera_vals * 1e3
            elif unit_str == "us":
                camera_vals = camera_vals * 1e6
            elif unit_str == "MHz":
                camera_vals = camera_vals * 1e-6

            scan_list = camera_vals.tolist()

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
        self.electrodeUpdate(V ,[0 ,1 ,2 ,3 ,4 ,5 ,6 ,7 ,8 ,9 ,10 ,11] ,[-1 ] +[-1 ] * 5 +[1 ] * 5 +[1])
    @kernel
    def AllZ(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V ,[0 ,1 ,2 ,3 ,4 ,5 ,6 ,7 ,8 ,9 ,10 ,11] ,[1 ] +[-1 ] * 5 +[1 ] * 5 +[-1])

    @kernel
    def endcapAvg(self, V):
        """
        changes axial confinement
        """
        self.electrodeUpdate(V, [1, 5, 6, 10], [1, 1, 1, 1])

    @kernel
    def electrodeUpdate(self ,V ,electrodeList ,signList):
        for i in range(len(electrodeList)):
            self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] = \
                self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] + V* (signList[i])

    @rpc
    def AllZ_calib_get(self) -> TFloat:
        return float(self.get_dataset('Calibrations.AllZ_calib_max'))

    @kernel
    def ON(self, Frequency435, Amplitude435, Time435, Attenuation_435, choice435, doppler_freq, doppler_amp,
           doppler_time,
           det_freq, det_amp, det_time, checkCameraDetection, checkGlobalCoolingShot, cameraCoolingShotTime,
           freq_935, amp_935,
           OP_freq, OP_amp, OP_time, LOP_freq, LOP_amp, LOP_time,
           MW_freq, MW_amp, MW_time,
           SBCcheck, SBCFrequency355_1, SBCAmplitude355_1, SBCFrequency355_2, SBCAmplitude355_2, SBCTime,
           SBCAmplitude935,
           ClearoutPower935, ClearoutTime935,
           prepfreq435, preptime,
           wait_time, RamseyCheck, phase1, phase2,
           EnableAWG, MScheck,
           B1check, FrequencyRaman1, AmplitudeRaman1,
           A16check, FrequencyRamanA16, AmplitudeRamanA16,
           B2check, FrequencyRamanB2, AmplitudeRamanB2,
           A15check, FrequencyRamanA15, AmplitudeRamanA15,
           Raman_time, LighShiftFactor, GlobalSidebandAmpScale, Bz,
           RamseyFrequency435, RamseyAmplitude435, PiBy2Time435_1, PiBy2Time435_2,
           newEndcapX, newAllY, newAllZ, endcapAvg_V, piezo_R1H, piezo_R1V, piezo_R2H, piezo_R2V,
           num_repeat, iterScan, checkLineTrigger, checkAllZ_calib=False, AllZ_calib_flag=False):

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

        newendcapAvg = endcapAvg_V - self.originalEndcapAvg

        # if AllZ_calib_flag:
        # print("Core sees AllZ Voltage:", newAllZ)

        self.EndcapX(newX)
        self.AllY(newY)
        self.AllZ(newZ)
        self.endcapAvg(newendcapAvg)

        self.core.break_realtime()

        # initialize DACS
        for i in range(12):
            ind = self.DCElectrodeMapping[i]
            self.zotino0.write_dac(self.DCElectrodeMapping[i], self.modDCElectrodeValues[ind])
        # self.zotino0.load()

        # piezo voltage  update
        self.zotino0.write_dac(24, piezo_R1H)  # PZ H indiv
        self.zotino0.write_dac(25, piezo_R1V)  # PZ V indiv
        # self.zotino0.write_dac(26, piezo_R2H)  # now used for OP switch
        self.zotino0.write_dac(27, piezo_R2V)  # PZ V glo
        self.zotino0.load()
        delay(2 * ms)

        if iterScan == 0:

            self.urukul0_cpld.init()
            self.urukul1_cpld.init()
            self.urukul2_cpld.init()

            delay(10 * ms)
            attenuation = 3.0  # use as required

            # Doppler+935

            # Doppler
            self.urukul0_ch1.init()
            self.urukul0_ch1.set_att(0 * dB)
            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch1.sw.off()

            # 935 # leaving it on for TAMOS system , 2026-7-31
            self.urukul0_ch2.init()
            self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
            self.urukul0_ch2.sw.on()

            # 435
            self.urukul0_ch0.init()
            self.urukul0_ch0.set_att(Attenuation_435 * dB)
            self.urukul0_ch0.sw.off()
            self.urukul1_ch0.init()
            self.urukul1_ch0.set_att(Attenuation_435 * dB)
            self.urukul1_ch0.sw.off()

            # Detection
            self.urukul0_ch3.init()
            self.ttl7.output()  # 26/07/13 gt; DET switch
            self.urukul0_ch3.set_att(0 * dB)
            self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
            self.urukul0_ch3.sw.off()
            self.ttl7.off()

            # OP
            self.urukul2_ch2.init()
            self.urukul2_ch2.set_att(0 * dB)
            self.urukul2_ch2.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
            self.urukul2_ch2.sw.off()
            self.zotino0.write_dac(26, 0.0)  # 26/07/13 gt: turning off GOP switch
            self.zotino0.load()

            # LOP
            self.urukul1_ch1.init()
            self.urukul1_ch1.set_att(0 * dB)
            self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
            self.urukul1_ch1.sw.off()

            # MW
            self.urukul1_ch2.init()
            self.urukul1_ch2.set_att(0 * dB)
            self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
            self.urukul1_ch2.sw.off()

            # 355 Raman 1; B1
            self.urukul2_ch0.init()
            self.urukul2_ch0.set_att(0 * dB)
            self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
            self.urukul2_ch0.sw.off()
            # self.urukul2_ch0.sw.on()
            self.zotino0.write_dac(31, 5.0)  # set RF switch to B1 DDS
            # self.zotino0.write_dac(31, 0.0)  # set RF switch to B1 AWG
            self.zotino0.load()

            # 355 Raman 1; A16
            self.urukul2_ch1.init()
            self.urukul2_ch1.set_att(0 * dB)
            self.urukul2_ch1.set(frequency=FrequencyRamanA16, amplitude=AmplitudeRamanA16, phase_mode=2)
            self.urukul2_ch1.sw.off()
            self.zotino0.write_dac(30, 5.0)  # set RF switch to A16 DDS
            # self.zotino0.write_dac(30, 0.0)  # set RF switch to A16 AWG
            self.zotino0.load()

            # Raman 1; B2
            self.urukul1_ch3.init()
            self.urukul1_ch3.set_att(0 * dB)
            self.urukul1_ch3.set(frequency=FrequencyRamanB2, amplitude=AmplitudeRamanB2, phase_mode=2)
            self.urukul1_ch3.sw.off()
            self.zotino0.write_dac(29, 5.0)  # set RF switch to B2 DDS
            # self.zotino0.write_dac(29, 0.0)  # set RF switch to B2 AWG
            self.zotino0.load()

            # 355 Raman 1; A15
            self.urukul2_ch3.init()
            self.urukul2_ch3.set_att(0 * dB)
            self.urukul2_ch3.set(frequency=FrequencyRamanA15, amplitude=AmplitudeRamanA15, phase_mode=2)
            self.urukul2_ch3.sw.off()
            self.zotino0.write_dac(28, 5.0)  # set RF switch to A15 DDS
            # self.zotino0.write_dac(28, 0.0)  # set RF switch to A15 AWG
            self.zotino0.load()

            # 355 Raman 2
            self.ttl6.output()

            # AWG trigger
            self.ttl5.output()

            # Camera shutter
            self.ttl4.output()

            # DET switch
            self.ttl7.output()

            self.sum_rising_edges = 0.0

            # self.sum_rising_edges_cooling = 0.0

            # warming up detection, OP, and Doppler AOMs
            self.urukul0_ch1.sw.on()
            self.ttl7.on()
            self.urukul0_ch3.sw.on()
            self.ttl6.on()
            # self.urukul2_ch2.sw.on()
            # self.zotino0.write_dac(26, 5.0)  # 26/07/13 gt: turning on GOP switch
            # self.zotino0.load()
            delay(1000 * ms)
            self.urukul0_ch1.sw.off()
            self.urukul0_ch3.sw.off()
            self.ttl7.off()
            self.ttl6.off()
            # self.urukul2_ch2.sw.off()
            # self.zotino0.write_dac(26, 0.0)  # 26/07/13 gt: turning off GOP switch
            # self.zotino0.load()

            # Cooling shot: 1 extra ttl trigger from the camera just before the entire exp sequence
            if checkGlobalCoolingShot and checkCameraDetection:
                self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
                self.urukul0_ch1.sw.on()
                # self.urukul0_ch2.sw.on() # 935
                self.urukul1_ch3.sw.on()  # protection on

                self.ttl4.on()  # camera trigger
                delay(cameraCoolingShotTime)
                self.ttl4.off()

                delay(11 * ms)  # Need this delay for camera acquisition.
                self.urukul0_ch1.sw.off()
                # self.urukul0_ch2.sw.off() # 935

        with self.core_dma.record("seq"):
            delay(30 * us)  # This delay will exist between repetitions
            self.urukul0_ch1.set_att(0 * dB)  # Doppler
            # self.urukul0_ch2.set_att(0 * dB) # 935
            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            # self.urukul0_ch2.sw.on()

            if checkCameraDetection:
                # delay(6 * ms)
                delay(2*ms)
            else:
                delay(doppler_time)

            self.urukul0_ch1.sw.off()
            # self.urukul0_ch2.sw.off()

            self.urukul2_ch2.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
            self.urukul2_ch2.set_att(0 * dB)
            self.zotino0.write_dac(26, 5.0)  # 26/07/13 gt: turning on GOP switch
            self.zotino0.load()
            self.urukul2_ch0.set_att(0 * dB)

            if SBCcheck:  # SBCTime>0.1*us:

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
                    # delay(SBCTime)
                    delay(0.01*ms)
                    # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    # GOP
                    self.urukul2_ch2.sw.on()
                    delay(0.05 * ms)  # prev 0.03ms need strong OP power
                    self.urukul2_ch2.sw.off()

                # # # # # Inner 1
                # # # #
                self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                for cyc in range(50):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    # self.ttl5.on()
                    # delay(SBCTime)
                    delay(0.005 * ms)
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()

                    self.urukul2_ch2.sw.on()  # GOP
                    delay(0.05 * ms)
                    self.urukul2_ch2.sw.off()
                # # # # #
                # #  # # # Outer1 2nd stage
                self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                for cyc in range(25):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    delay(0.025* ms)
                    # delay(SBCTime)
                    # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    # GOP
                    self.urukul2_ch2.sw.on()
                    delay(0.05 * ms)  # prev 0.03ms need strong OP power
                    self.urukul2_ch2.sw.off()
                # # # # # # #
                # # # # # # # # #
                # # # Inner1 2nd stage
                self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                for cyc in range(15):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    # self.ttl5.on()
                    delay(0.02 * ms)
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()

                    # GOP
                    self.urukul2_ch2.sw.on()
                    delay(0.05 * ms)
                    self.urukul2_ch2.sw.off()


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

                # 2nd
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

                # 1st sideband
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

                # clearout 976
                # self.urukul1_ch0.set(frequency=80 * MHz, amplitude=0.8, phase_mode=2)
                # self.urukul1_ch0.sw.on()
                # # delay(0.05* ms)
                # delay(0.03*ms)
                # self.urukul1_ch0.sw.off()

                ####CSBC with LOP
                # # self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2) # B1
                # self.urukul1_ch3.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2) # B2
                # self.urukul1_ch1.set(frequency=LOP_freq, amplitude=LOP_amp, phase_mode=2)
                # # self.urukul2_ch0.sw.on()
                # self.urukul1_ch3.sw.on()
                #
                # self.ttl6.on()
                # self.urukul1_ch1.sw.on()
                # delay(SBCTime)
                # # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                # # self.urukul2_ch0.sw.off()
                # self.urukul1_ch3.sw.off()
                #
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
                # self.urukul0_ch2.sw.off()

            # OP state prep with 935
            if OP_time > 0.01 * us:
                self.urukul2_ch2.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
                # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
                self.urukul2_ch2.set_att(0 * dB)
                # self.urukul0_ch2.set_att(0 * dB)

                self.zotino0.write_dac(26, 5.0)  # 26/07/13 gt: turning on GOP switch
                self.zotino0.load()
                delay(OP_time)
                self.urukul2_ch2.sw.on()
                delay(OP_time)
                # delay(0.05*ms)
                delay_mu(1)
                self.urukul2_ch2.set(frequency=OP_freq, amplitude=0.0001, phase_mode=2)
                self.urukul2_ch2.set_att(30 * dB)
                self.urukul2_ch2.sw.off()
                self.zotino0.write_dac(26, 0.0)  # 26/07/13 gt: turning off GOP switch
                self.zotino0.load()
                delay(0.5 * ms)

            ####LOP; can pump globally by sequentially pumping each ion; locations determined by the frequency array
            # if OP_time > 0.01 * us:
            #     for f in [203.92-0.4-0.55, 200.25-0.55, 197.5-0.4-0.55] :
            #         self.urukul1_ch1.set(frequency=f * MHz, amplitude=0.8, phase_mode=2)
            #         self.urukul1_ch1.set_att(0 * dB)
            #         # self.ttl5.on()
            #         # delay(0.1 * ms)
            #         self.urukul1_ch1.sw.on()
            #         # self.urukul1_ch3.sw.on()
            #         # self.urukul0_c.sw.on()
            #         delay(OP_time)
            #         # delay(0.0001 * ms)
            #         #
            #         delay_mu(1)
            #         self.urukul1_ch1.set(frequency=f * MHz, amplitude=0.0001, phase_mode=2)
            #         self.urukul1_ch1.set_att(30 * dB)
            #         self.urukul1_ch1.sw.off()
            #
            #         delay(0.1 * ms)
            #
            #     delay(0.5 * ms)

            # delay(-1*us) # important for syncing. Must be before setting up the DDS config or else there is some gradual ampltiude ramp of 435 DDS

            if RamseyCheck == True and not EnableAWG:

                # # # MW ramsey: First pi/2 pulse
                # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
                # #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.sw.on()
                # delay(PiBy2Time435_1)
                # delay_mu(1)
                # self.urukul1_ch2.sw.off()
                # delay(0.05*ms)


                # delay(wait_time)


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





                # ###### wait time with 355 on ##########

                # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch0.sw.on() # Raman 1
                # self.ttl6.on() # Raman 2
                # delay(wait_time)
                # delay_mu(1)
                # # self.urukul2_ch0.sw.off() # Raman 1
                # self.ttl6.off() # Raman 2
                ########################################



                # # Raman pulse with MW
                # # # Raman 1 ch 1
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()
                # self.ttl6.on()
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch0.sw.off()
                # self.ttl6.off()
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


                # #CSBC LOP
                # # self.urukul2_ch0.set(frequency= AmplitudeRaman1, amplitude=SBCAmplitude355_2, phase_mode=2)
                # self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)  # B1
                #
                # # self.urukul2_ch1.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2) # A16
                # # self.urukul1_ch3.set(frequency= SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2) # B2
                #
                # self.urukul1_ch1.set(frequency=LOP_freq, amplitude=LOP_amp, phase_mode=2)
                # self.urukul2_ch0.sw.on()
                # # self.urukul2_ch1.sw.on()
                # # self.urukul1_ch3.sw.on()
                # self.ttl6.on()
                # self.urukul1_ch1.sw.on()
                # delay(wait_time)
                # # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                # self.urukul2_ch0.sw.off()
                # # self.urukul2_ch1.sw.off()
                # # self.urukul1_ch3.sw.off()
                # self.ttl6.off()
                # self.urukul1_ch1.sw.off()
                # delay(0.05 * ms)



                # # # MW Ramsey: Second pi/2  pulse
                # self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
                # #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                # # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.sw.on()
                # self.urukul1_ch2.set_att(0 * dB)
                # delay(PiBy2Time435_2)
                # delay_mu(1)
                # # self.urukul1_ch2.set_att(30 * dB)
                # self.urukul1_ch2.sw.off()
                # delay(0.05*ms)




                # # # # Raman Ramsey # # # # # #
                # # #
                ########## Ramsey first pi/2 ##############
                self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch0.set(frequency=RamseyFrequency435 ,phase=0.0, amplitude=RamseyAmplitude435, phase_mode=2)
                self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1, phase_mode=2)
                # self.urukul2_ch1.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1, phase_mode=2)

                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()
                # self.urukul2_ch1.sw.on() # A16

                self.ttl6.on()
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                # delay(Raman_time)
                self.urukul2_ch0.sw.off()
                # self.urukul2_ch1.sw.off()

                self.ttl6.off()





                # amplitude ramped pi/2
                # delay(0.001 * ms)
                #
                # # --- 1. RAMP UP ---
                # for n in range(10):
                #     # Calculate amplitude scaling factor (0.0 up to ~0.975)
                #     amp_scale_up = np.sin(math.pi / 2.0 * n / 10.0) ** 2
                #     self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0,
                #                                      amplitude=AmplitudeRaman1 * amp_scale_up, phase_mode=2)
                #     # At first step, set attenuation and turn on switches
                #     if n == 0:
                #         self.urukul2_ch0.set_att(0 * dB)
                #         self.urukul2_ch0.sw.on()
                #         self.ttl6.on()  # Raman 2
                #
                #     delay(0.3 * us)  # AOM delay
                #     delay(1 * us * (n + 1) / 10.0)
                # # --- 2. FLAT TOP ---
                # # Ensure full amplitude
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1,
                #                                  phase_mode=2)
                # # Ensure att and switches are on (matching old logic)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()
                # delay(0.3 * us)  # AOM delay
                #
                # delay(Raman_time)
                #
                # # --- 3. RAMP DOWN ---
                # for n in range(10):
                #     # Calculate amplitude scaling factor (~0.975 down to 0.0)
                #     amp_scale_down = 1.0 - np.cos(math.pi / 2.0 * (1.0 - (n + 1) / 10.0)) ** 2
                #     self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0,
                #                                      amplitude=AmplitudeRaman1 * amp_scale_down, phase_mode=2)
                #
                #     delay(0.3 * us)  # AOM delay
                #     delay(1 * us * (n + 1) / 10.0)
                # # --- 4. TURN OFF ---
                # self.urukul2_ch0.sw.off()  # Raman 1
                # self.ttl6.off()  # Raman 2 off


                #
                # self.urukul2_ch1.set_att(0 * dB)
                # # self.urukul2_ch0.set(frequency=RamseyFrequency435 ,phase=0.0, amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase=0.0, amplitude=AmplitudeRamanA16, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()
                # self.ttl6.on()
                # delay(0.3 * us)  # AOM delay
                # delay(Raman_time)
                # # delay(Raman_time)
                # self.urukul2_ch1.sw.off()
                # self.ttl6.off()
                # #
                # n = 4
                # for i in range(n):
                #     delay(wait_time / 2 / n)
                #
                #     self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.5*(i%2), amplitude=AmplitudeRaman1, phase_mode=2)
                #     # self.urukul1_ch2.set(frequency=MW_freq, phase = 0.0, amplitude=RamseyAmplitude435, phase_mode=2)
                #     self.urukul2_ch0.set_att(0 * dB)
                #     self.ttl6.on()
                #     self.urukul2_ch0.sw.on()
                #     delay(2 * Raman_time)
                #     # delay(2 * MW_time)
                #     delay_mu(1)
                #     # self.urukul1_ch2.set_att(30 * dB)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #
                #     delay(wait_time / 2 / n)

                delay(wait_time)

                #########  Ramsey second pi/2 #######
                # self.urukul2_ch0.set(frequency=RamseyFrequency435, phase= phase1,  amplitude=RamseyAmplitude435, phase_mode=2)
                self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=phase2, amplitude=AmplitudeRaman1, phase_mode=2)
                # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul2_ch1.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1, phase_mode=2)

                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()
                # self.urukul2_ch1.sw.on()

                self.ttl6.on()
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                # delay_mu(1)
                self.urukul2_ch0.sw.off()
                # self.urukul2_ch1.sw.off()

                self.ttl6.off()


                # --- frequency modulation Parameters ---
                # mod_freq = 0.0* Hz # Hz
                # mod_amp = 0.5
                # # Modulation depth in turns
                # mod_phase_offset = 0.0 # Scan phase offset (radians)
                # # Timestamps for each pulse start relative to sequence trigger (t = 0)
                # t1 = 0.0 * ms
                # t2 = t1 + Raman_time + 0.3 * us + wait_time

                # phase1_compensated = mod_amp * np.sin(2.0 * np.pi * mod_freq * t1 + phase2)
                phase1_compensated = 0.0
                # phase2_compensated = mod_amp * np.sin(2.0 * np.pi * mod_freq * t2 + phase2)
                phase2_compensated = phase2


                ########## First pi/2 Pulse ##########
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=phase1_compensated, amplitude=AmplitudeRaman1,
                #                      phase_mode=2)
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1,
                #                      phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # # self.ttl5.on()
                # self.ttl6.on()
                # delay(0.025 * us)
                # self.urukul2_ch0.sw.on()
                #
                # delay(0.3 * us)  # AOM delay
                # delay(Raman_time)

                # self.ttl6.off()
                # delay(0.1 * us)
                # self.urukul2_ch0.sw.off()
                #
                ########## Ramsey Wait Time ##########
                # delay(wait_time)
                #
                # ########## Second pi/2 Pulse ##########
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=phase2_compensated, amplitude=AmplitudeRaman1,
                # #                      phase_mode=2)
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=phase2, amplitude=AmplitudeRaman1,
                #                      phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.ttl6.on()  # Raman 2
                # delay(0.025 * us)
                # self.urukul2_ch0.sw.on()
                #
                # delay(0.3 * us)  # AOM delay
                # delay(Raman_time)
                #
                # self.ttl6.off()
                # delay(0.1 * us)
                # self.urukul2_ch0.sw.off()
                # # self.ttl5.off()



                # delay(0.001 * ms)
                #
                # # --- 1. RAMP UP ---
                # for n in range(10):
                #     # Calculate amplitude scaling factor (0.0 up to ~0.975)
                #     amp_scale_up = np.sin(math.pi / 2.0 * n / 10.0) ** 2
                #     self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0,
                #                          amplitude=AmplitudeRaman1 * amp_scale_up, phase_mode=2)
                #     # At first step, set attenuation and turn on switches
                #     if n == 0:
                #         self.urukul2_ch0.set_att(0 * dB)
                #         self.urukul2_ch0.sw.on()
                #         self.ttl6.on()  # Raman 2
                #
                #     delay(0.3 * us)  # AOM delay
                #     delay(1 * us * (n + 1) / 10.0)
                # # --- 2. FLAT TOP ---
                # # Ensure full amplitude
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1,
                #                      phase_mode=2)
                # # Ensure att and switches are on (matching old logic)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()
                # delay(0.3 * us)  # AOM delay
                #
                # delay(Raman_time)
                #
                # # --- 3. RAMP DOWN ---
                # for n in range(10):
                #     # Calculate amplitude scaling factor (~0.975 down to 0.0)
                #     amp_scale_down = 1.0 - np.cos(math.pi / 2.0 * (1.0 - (n + 1) / 10.0)) ** 2
                #     self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0,
                #                          amplitude=AmplitudeRaman1 * amp_scale_down, phase_mode=2)
                #
                #     delay(0.3 * us)  # AOM delay
                #     delay(1 * us * (n + 1) / 10.0)
                # # --- 4. TURN OFF ---
                # self.urukul2_ch0.sw.off()  # Raman 1
                # self.ttl6.off()  # Raman 2 off



                # # self.urukul2_ch0.set(frequency=RamseyFrequency435 ,phase=0.0, amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase=0.0, amplitude=AmplitudeRamanA16, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()
                # self.ttl6.on()
                # delay(0.6 * us)  # AOM delay
                # delay(Raman_time)
                # # delay(Raman_time)
                # self.urukul2_ch1.sw.off()
                # self.ttl6.off()

                # #self.urukul2_ch0.set(frequency=202*MHz,phase=0.0, amplitude=RamseyAmplitude435, phase_mode=2)
                #
                # # delay(0.05*ms)
                #
                # # # delay(10*us)
                # # # # # # Raman 1 ch 1 -RSB
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1,phase=0.0, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # ### extra
                # # self.urukul2_ch1.set(frequency=FrequencyRamanA16 , phase=phase2,
                # #                      amplitude=AmplitudeRamanA16 , phase_mode=2)
                # # self.urukul2_ch1.set_att(0 * dB)
                # # self.urukul2_ch1.sw.on()  # Raman 1,ch2
                # # ### extra -end
                # # self.urukul2_ch0.sw.on()  # Raman 1
                # # self.ttl6.on()  # Raman 2
                # # delay(0.3 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()  # Raman 1 ch1
                # # self.ttl6.off()  # Raman 2
                # #
                # # ### extra
                # # self.urukul2_ch1.sw.off() # Raman 1 ch2
                # # ### extra -end
                #
                # # # Raman 1 ch 2-RSB
                # # self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase= 0.0, amplitude=AmplitudeRamanA16, phase_mode=2)
                # # self.urukul2_ch1.set_att(0 * dB)
                # # self.urukul2_ch1.sw.on()  # Raman 1
                # # self.ttl6.on()  # Raman 2
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch1.sw.off()  # Raman 1
                # # self.ttl6.off()  # Raman 2
                #
                # #wait time
                # # delay(wait_time)
                # # delay_mu(1)
                #
                # # #Changing DACs during Ramsey
                # # self.endcapX(newX)
                # # self.allY(0.0)
                # # self.allZ(0.0)
                # # for i in range(12):
                # #     ind = self.DCElectrodeMapping[i]
                # #     self.zotino0.write_dac(self.DCElectrodeMapping[i], self.modDCElectrodeValues[ind])
                # # self.zotino0.load()
                #
                #
                #
                # # Dynamical decoupling
                # # for n in range(2):
                # #
                # #     # wait fraction
                # #     delay(wait_time/(2.0*(2)))
                # #     delay_mu(1)
                #
                #     # pure RSB decoupling
                #     # self.urukul1_ch2.set_att(0 * dB)
                #     # # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1,
                #     # #                      phase_mode=2)
                #     # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=(0.0 + np.pi / 2.0 * (n % 2)), amplitude=AmplitudeRaman1,phase_mode=2)
                #     # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(Raman_time*2.0)
                #     # # delay_mu(1)
                #     # # self.urukul1_ch2.set_att(30 * dB)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #
                #     # carrier and rsb decoupling
                #
                #     # #RSB pi
                #     # self.urukul1_ch2.set_att(0 * dB)
                #     # self.urukul2_ch0.set(frequency=SBCFrequency355_1, phase=0.0,
                #     #                      amplitude=0.7, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(0.035*ms)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #     #
                #     # # carrier pi
                #     # self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=(0.0 + np.pi / 2.0 * (n % 2)),
                #     #                      amplitude=RamseyAmplitude435, phase_mode=2)
                #     # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(PiBy2Time435_1*2.0)
                #     # # delay_mu(1)
                #     # # self.urukul1_ch2.set_att(30 * dB)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #     #
                #     # # RSB pi
                #     # self.urukul1_ch2.set_att(0 * dB)
                #     # self.urukul2_ch0.set(frequency=SBCFrequency355_1, phase=np.pi,
                #     #                      amplitude=0.7, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(0.035*ms)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #
                #     # carrier and rsb with bsb decoupling
                #
                #     # # carrier pi
                #     # self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=(0.0 + np.pi / 2.0 * (n % 2)),
                #     #                      amplitude=RamseyAmplitude435, phase_mode=2)
                #     # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(PiBy2Time435_1 * 2.0)
                #     # # delay_mu(1)
                #     # # self.urukul1_ch2.set_att(30 * dB)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #     #
                #     # # BSB pi- ch2
                #     # self.urukul2_ch1.set(frequency=195.43771*MHz, phase=0.0,
                #     #                      amplitude=0.4017, phase_mode=2)
                #     # self.urukul2_ch1.set_att(0 * dB)
                #     # self.urukul2_ch1.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(0.059755 * ms)
                #     # self.urukul2_ch1.sw.off()
                #     # self.ttl6.off()
                #     #
                #     #
                #     # # RSB pi -ch1
                #     # self.urukul2_ch0.set(frequency=189.626452*MHz, phase=0.0,
                #     #                      amplitude=0.35, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(0.064 * ms)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #     #
                #     #
                #     # # wait fraction
                #     # delay(wait_time/(2.0*(2)))
                #     # delay_mu(1)
                #
                # # wait time with 355 on
                # #
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase= 0.0,  amplitude=AmplitudeRaman1*GlobalSidebandAmpScale, phase_mode=2) #RSB
                # # self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase=phase2, amplitude=AmplitudeRamanA16*LighShiftFactor*GlobalSidebandAmpScale, phase_mode=2) #BSB
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch1.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on() # Raman 1 ch1
                # # self.urukul2_ch1.sw.on()  # Raman 1 ch2
                # # self.ttl6.on() # Raman 2
                # # delay(wait_time)
                # # delay_mu(1)
                # # self.ttl6.off() # Raman 2
                # # self.urukul2_ch0.sw.off() # Raman 1 ch1
                # # self.urukul2_ch1.sw.off() # Raman 1 ch2
                #
                # #
                # # # # # # # Raman 1 ch 1-RSB
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=phase1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # ### extra
                # # self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase=phase2,
                # #                      amplitude=AmplitudeRamanA16, phase_mode=2)
                # # self.urukul2_ch1.set_att(0 * dB)
                # # self.urukul2_ch1.sw.on()  # Raman 1,ch2
                # # ### extra -end
                # #
                # # self.urukul2_ch0.sw.on()  # Raman 1
                # # self.ttl6.on()  # Raman 2
                # # delay(0.3 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()  # Raman 1
                # # self.ttl6.off()  # Raman 2
                # # ### extra
                # # self.urukul2_ch1.sw.off()  # Raman 1 ch2
                # # ### extra -end
                #
                # # # Raman 1 ch 2-RSB
                # # self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase=np.pi-(SBCAmplitude935-0.4)*np.pi/0.8, amplitude=AmplitudeRamanA16, phase_mode=2)
                # # self.urukul2_ch1.set_att(0 * dB)
                # # self.urukul2_ch1.sw.on()  # Raman 1
                # # self.ttl6.on()  # Raman 2
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch1.sw.off()  # Raman 1
                # # self.ttl6.off()  # Raman 2
                #
                #
                # # # # Ramsey second pi/2
                # # # # delay(10 * us)
                # delay(wait_time)
                # # self.urukul2_ch0.set(frequency=RamseyFrequency435, phase= phase1,  amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()
                # self.ttl6.on()
                # delay(0.6 * us)  # AOM delay
                # delay(Raman_time)
                # # delay(Raman_time)
                # #delay_mu(1)
                # self.urukul2_ch0.sw.off()
                # self.ttl6.off()

            # 435 interaction
            # self.urukul0_ch2.sw.off() # 935/760 repumper
            # self.urukul1_ch0.sw.off()  # 976 repumper
            # if choice435==1:
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

            # elif choice435==2:
            # delay(10*us) # a delay because suspectected pulse sequence was not running properly. Have to revisit it.

            # 976
            # self.urukul1_ch0.set(frequency=80*MHz, amplitude=0.8, phase_mode=2)
            # self.urukul1_ch0.sw.on()
            # delay(1*ms)
            # self.urukul1_ch0.sw.off()

            # self.urukul0_ch2.sw.off() # 935 repumper

            # For dual drive

            # self.urukul0_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
            # self.urukul1_ch0.set(frequency=prepfreq435, amplitude=Amplitude435, phase_mode=2)
            # self.urukul0_ch0.sw.on()
            # self.urukul1_ch0.sw.on()
            # delay(Time435)
            # self.urukul0_ch0.sw.off()
            # self.urukul1_ch0.sw.off()

            # delay(30 * ms)

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
            # delay(wait_time)
            # self.ttl5.off()

            if RamseyCheck and EnableAWG:  # for now only on B1
                self.zotino0.write_dac(31, 0.0)  # switch to AWG
                self.zotino0.load()
                delay(0.5 * ms)

                self.ttl5.on()  # trigger to AWG/ Raman 1

                delay(0.175 * us)  # needed b/c the indiv turns on slightly delayed from the global
                # delay(2*us) # for pulse shaping
                self.ttl6.on()  # Raman 2 on
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                delay(-0.3 * us)
                # delay(6*us)# for pulse shaping
                self.ttl6.off()  # Raman 2 off

                delay(wait_time)

                # delay(4*us) # for pulse shaping
                self.ttl6.on()  # Raman 2 on
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                delay(-0.3 * us)
                # delay(6*us) # for pulse shaping
                self.ttl6.off()  # Raman 2 off

                self.ttl5.off()

                # delay(0.5 * ms)
                self.zotino0.write_dac(31, 5.0)  # set back to DDS
                self.zotino0.load()
                delay(0.5 * ms)

            # MW interaction
            if MW_time > 0.01 * us:
                self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
                # self.urukul1_ch2.set_att(0 * dB)
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

            # Raman original
            if (B1check or A16check or B2check or A15check) \
                    and Raman_time > 0.01 * us and not EnableAWG and not RamseyCheck and not AllZ_calib_flag:

                delay(0.001 * ms)

                if not MScheck: # Regular Raman interaction
                    # Raman 1; B1
                    self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                    self.urukul2_ch0.set_att(0* dB)
                    # A16
                    self.urukul2_ch1.set(frequency=FrequencyRamanA16, amplitude=AmplitudeRamanA16, phase_mode=2)
                    self.urukul2_ch1.set_att(0 * dB)
                    # B2
                    self.urukul1_ch3.set(frequency=FrequencyRamanB2, amplitude=AmplitudeRamanB2, phase_mode=2)
                    self.urukul1_ch3.set_att(0 * dB)
                    # A15
                    self.urukul2_ch3.set(frequency=FrequencyRamanA15, amplitude=AmplitudeRamanA15, phase_mode=2)
                    self.urukul2_ch3.set_att(0 * dB)

                    # self.ttl5.on() # diagnostic/awg trigger (remember to reconnect to AWG)

                    self.ttl6.on()  # Raman 2
                    delay(0.025 * us)

                    if B1check: self.urukul2_ch0.sw.on()  # B1
                    if A16check: self.urukul2_ch1.sw.on()  # A16
                    if B2check: self.urukul1_ch3.sw.on()  # B2
                    if A15check: self.urukul2_ch3.sw.on()  # A15

                    delay(0.3 * us)  # AOM delay

                    delay(Raman_time)

                    self.ttl6.off()  # Raman 2 off
                    delay(0.1 * us) # noticed on PD that AOMs had a relative shift of ~100 ns in the end
                    self.urukul2_ch0.sw.off()  # Raman 1
                    self.urukul2_ch1.sw.off()  # A16
                    self.urukul1_ch3.sw.off()  # B2
                    self.urukul2_ch3.sw.off()  # A15
                    # delay(0.3 * ms) # noticed on PD that AOMs turn off ~300 ns after ttl5 is off
                    # self.ttl5.off()

                if MScheck:
                    # # # # Raman 1: ch1 and ch2 on, on DDS; it was done by combining r and b on a PS
                    # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase= 0.0, amplitude=AmplitudeRaman1*0.50978*1.0/0.8, phase_mode=2)
                    # self.urukul2_ch0.set(frequency=FrequencyRaman1 - Frequency435 + Bz, phase= 0.0, amplitude=AmplitudeRaman1*GlobalSidebandAmpScale, phase_mode=2)
                    # self.urukul2_ch0.set_att(0 * dB)
                    # ## self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase= 0.0, amplitude=AmplitudeRaman1*0.7/0.6, phase_mode=2)
                    # self.urukul2_ch1.set(frequency=FrequencyRamanA16 + Frequency435 + Bz, phase= phase2, amplitude=AmplitudeRamanA16*LighShiftFactor*GlobalSidebandAmpScale, phase_mode=2)
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


                    #### MS with AWG
                    if EnableAWG:
                        self.zotino0.write_dac(31, 0.0)  # switch to B1 AWG
                        self.zotino0.write_dac(30, 0.0)  # A16 AWG
                        self.zotino0.write_dac(29, 0.0)  # B2 AWG
                        self.zotino0.write_dac(28, 0.0)  # A15 AWG
                        self.zotino0.load()
                        delay(0.5 * ms)

                        delay(0.001 * ms)

                        self.ttl5.on()  # trigger to AWG/ Raman 1
                        delay(0.175 * us)  # needed b/c the indiv turns on slightly delayed from the global
                        # delay(2*us) # adjust for pulse shaping
                        self.ttl6.on()  # Raman 2 on
                        delay(0.3 * us)  # AOM delay

                        delay(Raman_time)

                        delay(-0.3 * us)  # global was turning off after individual
                        # delay(6*us) # for pulse shaping
                        self.ttl6.off()  # Raman 2 off
                        self.ttl5.off()

                        # delay(0.5 *ms)
                        self.zotino0.write_dac(31, 5.0)  # set back to DDS
                        self.zotino0.write_dac(30, 5.0)
                        self.zotino0.write_dac(29, 5.0)
                        self.zotino0.write_dac(28, 5.0)
                        self.zotino0.load()
                        delay(0.5 * ms)




            #### Raman with Pulse shapingon DDS ###########
            # if Raman_time > 0.01 * us and not EnableAWG and not RamseyCheck and not AllZ_calib_flag:
            #     delay(0.001 * ms)
            #
            #     # --- 1. RAMP UP ---
            #     for n in range(10):
            #         # Calculate amplitude scaling factor (0.0 up to ~0.975)
            #         amp_scale_up = np.sin(math.pi / 2.0 * n / 10.0) ** 2
            #
            #         if B1check: self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0,
            #                                          amplitude=AmplitudeRaman1 * amp_scale_up, phase_mode=2)
            #         if A16check: self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase=0.0,
            #                                           amplitude=AmplitudeRamanA16 * amp_scale_up, phase_mode=2)
            #         if B2check: self.urukul1_ch3.set(frequency=FrequencyRamanB2, phase=0.0,
            #                                          amplitude=AmplitudeRamanB2 * amp_scale_up, phase_mode=2)
            #         if A15check: self.urukul2_ch3.set(frequency=FrequencyRamanA15, phase=0.0,
            #                                           amplitude=AmplitudeRamanA15 * amp_scale_up, phase_mode=2)
            #
            #         # At first step, set attenuation and turn on switches
            #         if n == 0:
            #             if B1check:
            #                 self.urukul2_ch0.set_att(0 * dB)
            #                 self.urukul2_ch0.sw.on()
            #             if A16check:
            #                 self.urukul2_ch1.set_att(0 * dB)
            #                 self.urukul2_ch1.sw.on()
            #             if B2check:
            #                 self.urukul1_ch3.set_att(0 * dB)
            #                 self.urukul1_ch3.sw.on()
            #             if A15check:
            #                 self.urukul2_ch3.set_att(0 * dB)
            #                 self.urukul2_ch3.sw.on()
            #             self.ttl6.on()  # Raman 2
            #
            #         delay(0.3 * us)  # AOM delay
            #         delay(1 * us * (n + 1) / 10.0)
            #
            #     # --- 2. FLAT TOP ---
            #     # Ensure full amplitude
            #     if B1check: self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1,
            #                                      phase_mode=2)
            #     if A16check: self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase=0.0, amplitude=AmplitudeRamanA16,
            #                                       phase_mode=2)
            #     if B2check: self.urukul1_ch3.set(frequency=FrequencyRamanB2, phase=0.0, amplitude=AmplitudeRamanB2,
            #                                      phase_mode=2)
            #     if A15check: self.urukul2_ch3.set(frequency=FrequencyRamanA15, phase=0.0, amplitude=AmplitudeRamanA15,
            #                                       phase_mode=2)
            #
            #     # Ensure att and switches are on (matching old logic)
            #     if B1check:
            #         self.urukul2_ch0.set_att(0 * dB)
            #         self.urukul2_ch0.sw.on()
            #     if A16check:
            #         self.urukul2_ch1.set_att(0 * dB)
            #         self.urukul2_ch1.sw.on()
            #     if B2check:
            #         self.urukul1_ch3.set_att(0 * dB)
            #         self.urukul1_ch3.sw.on()
            #     if A15check:
            #         self.urukul2_ch3.set_att(0 * dB)
            #         self.urukul2_ch3.sw.on()
            #
            #     delay(0.3 * us)  # AOM delay
            #     delay(Raman_time)
            #
            #     # --- 3. RAMP DOWN ---
            #     for n in range(10):
            #         # Calculate amplitude scaling factor (~0.975 down to 0.0)
            #         amp_scale_down = 1.0 - np.cos(math.pi / 2.0 * (1.0 - (n + 1) / 10.0)) ** 2
            #
            #         if B1check: self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0,
            #                                          amplitude=AmplitudeRaman1 * amp_scale_down, phase_mode=2)
            #         if A16check: self.urukul2_ch1.set(frequency=FrequencyRamanA16, phase=0.0,
            #                                           amplitude=AmplitudeRamanA16 * amp_scale_down, phase_mode=2)
            #         if B2check: self.urukul1_ch3.set(frequency=FrequencyRamanB2, phase=0.0,
            #                                          amplitude=AmplitudeRamanB2 * amp_scale_down, phase_mode=2)
            #         if A15check: self.urukul2_ch3.set(frequency=FrequencyRamanA15, phase=0.0,
            #                                           amplitude=AmplitudeRamanA15 * amp_scale_down, phase_mode=2)
            #
            #         delay(0.3 * us)  # AOM delay
            #         delay(1 * us * (n + 1) / 10.0)
            #
            #     # --- 4. TURN OFF ---
            #     self.urukul2_ch0.sw.off()  # Raman 1
            #     self.urukul2_ch1.sw.off()  # A16
            #     self.urukul1_ch3.sw.off()  # B2
            #     self.urukul2_ch3.sw.off()  # A15
            #     self.ttl6.off()  # Raman 2 off


            # AWG Raman
            if EnableAWG and not RamseyCheck:
                self.zotino0.write_dac(31, 0.0)  # switch to B1 AWG
                self.zotino0.write_dac(30, 0.0)  # A16 AWG
                self.zotino0.write_dac(29, 0.0)  # B2 AWG
                self.zotino0.write_dac(28, 0.0)  # A15 AWG
                self.zotino0.load()
                delay(0.5 * ms)

                delay(0.001 * ms)

                self.ttl5.on()  # trigger to AWG/ Raman 1
                delay(0.175 * us) # needed b/c the indiv turns on slightly delayed from the global
                # delay(2*us) # adjust for pulse shaping
                self.ttl6.on()  # Raman 2 on
                delay(0.3 * us)  # AOM delay

                delay(Raman_time)

                delay(-0.3 * us) # global was turning off after individual
                # delay(6*us) # for pulse shaping
                self.ttl6.off()  # Raman 2 off
                self.ttl5.off()

                # delay(0.5 *ms)
                self.zotino0.write_dac(31, 5.0)  # set back to DDS
                self.zotino0.write_dac(30, 5.0)
                self.zotino0.write_dac(29, 5.0)
                self.zotino0.write_dac(28, 5.0)
                self.zotino0.load()
                delay(0.5 * ms)

            # Detection w. 935
            if det_time > 0.01 * us:
                self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
                self.ttl7.on()
                self.urukul0_ch3.sw.on()
                if checkCameraDetection:
                    self.ttl4.on()  # camera
                self.ttl.gate_rising(det_time)
                if checkCameraDetection:
                    self.ttl4.off()  # camera
                self.urukul0_ch3.sw.off()
                self.ttl7.off()

            # Doppler + 760/935
            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
            self.urukul0_ch1.set_att(0 * dB)
            # self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch1.sw.on()
            # self.urukul0_ch2.sw.on()

            # delay(20 * ms) # for 976 and 760

            if checkCameraDetection and SBCTime <= 0.1 * us:
                delay(5 * ms)  # important for 411 and camera based detection
            elif checkCameraDetection and SBCTime > 0.1 * us:
                delay(2 * ms)

            # exp loop with dma


        # for DMA (agrees with barebones)
        seq_handle = self.core_dma.get_handle("seq")
        # repetition loop for DMA
        if checkAllZ_calib and AllZ_calib_flag:
            num_repeat_mod = 50
        else:
            num_repeat_mod = num_repeat

        for i in range(num_repeat_mod):
            # Line trigger sync
            if checkLineTrigger:
                '''
                loops until 1 count from the trigger line is detected
                '''
                fc = 0
                while fc == 0:
                    self.ttl0_counter.gate_rising(
                        0.05 * ms)  # lower detection time helps to finely resolve ext trigger timing
                    delay(10 * us)
                    fc = self.ttl0_counter.fetch_count()
            # DMA's single execution run
            delay(100 * us)
            self.core_dma.playback_handle(seq_handle)
            if checkAllZ_calib and AllZ_calib_flag:
                self.AllZ_calib_histpoints[i] = self.ttl.fetch_count()
                # self.calib_counts_print(self.ttl.fetch_count())
            else:
                self.histpoints[i] = self.ttl.fetch_count()  # I think can only be called once per gate event or blocks function until counts is available

    @rpc
    def calib_counts_print(self, counts):
        print('The unthresholded counts from the AllZ scan are ', counts)

    @rpc  # Checked; it is implemented in prepare()
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
        currentExpid = self.scheduler.expid

        currentExpidScan = (currentExpid['arguments'])['ndscan_params']
        currentExpidScanDict = json.loads(self.find_and_extract_object(currentExpidScan, "scan"))
        # note: a custom function is needed for dict extraction due to
        # flawed ndscan format for simple json.loads() to work

        if currentExpidScanDict["axes"]:
            scanAxes = (currentExpidScanDict["axes"][0])  # scan sequence in ndscan
            scanParamStr = scanAxes["fqn"].split(".")[-1]  # str, parameter
            scanUnit = self._free_params[scanParamStr].unit  # str, unit from FloatParam, not FloatParamHandle
            scanUnitScale = self._free_params[scanParamStr].scale  # float, scaling
            scanParamSequence = np.linspace(scanAxes["range"]["start"], scanAxes["range"]["stop"],
                                            scanAxes["range"]["num_points"])
            scanParamSequenceRescaled = scanParamSequence / scanUnitScale
            scanText = scanParamStr + "|" + scanUnit
            return {"x": {"name": scanText, "value": scanParamSequenceRescaled.tolist()}}
        else:
            return {"x": {"name": "Step in place", "value": [0.0]}}

        # print(type(currentExpidScanDict))

    @rpc
    def find_and_extract_object(self, text_data, key):
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
            "step_index": step_index,  # only this matters to the awg for loading scan point
            "num_pts": num_pts,  # not needed on awg side for loading scan point
            "num_reps": num_reps  # not needed on awg side for loading scan point
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
    def AllZcalibFitter(self):  # -> TFloat:
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
            self.set_dataset('Calibrations.AllZ_calib_max', center_val, broadcast=True, archive=True, persist=True)
            # self.mutate_dataset('Calibrations.AllZ_calib_max',center_val)
            # return center_val

        except Exception as e:
            # If something goes wrong, just keep the old value or print error
            print(f"AllZ Fitter Error: {e}")

    @kernel
    def uninterrupted_processes(self):

        # 369 ULE
        # self.urukul2_ch3.set(frequency=self.ULE_369_Frequency, amplitude=self.ULE_369_Amp)
        # self.urukul2_ch3.set_att(self.ULE_369_Att * dB)
        # self.urukul2_ch3.sw.on()

        pass

    # original
    def run(self):
        import time
        t_run_start = time.time()

        # Time gap between prepare() ending and run() starting
        wait_time = t_run_start - getattr(self, 't_f_def', t_run_start)
        print(f"Wait before run():       {wait_time:.4f} seconds")

        print("[DIAGNOSTIC] Entering run()...")
        x_len = len(self.scan_arr)
        y_len = len(self.scan_arr_y)
        print(f"[DIAGNOSTIC] Starting loops for {x_len} x {y_len} grid...")

        # 1. Hardware Initialization (AWG)
        t_awg_start = time.time()
        if self.awg_enabled and self.awg_scan_info:
            print("Initializing AWG connection...")
            try:
                # self.trigger_awg_preload(...)
                self.init_awg_connection(self.awg_scan_info, self.awg_globals)
            except Exception as e:
                print(f"AWG Connection Failed: {e}")

        print(f"AWG Init Time:           {time.time() - t_awg_start:.4f} seconds")

        # 26/01/19 gt: for faster data transfer
        print("Starting ARTIQ Compilation & Execution (krun)...")
        t_kernel_start = time.time()

        # [2D ADDITION] Pass the new Y-axis variables (scan_values_y, scan_index_y) to krun
        self.krun(
            self.scan_values,
            self.scan_values_y,
            self.default_values,
            self.scan_index,
            self.scan_index_y,
            self.iter_index
        )

        print(f"Kernel Compile + Exec:   {time.time() - t_kernel_start:.4f} seconds")
        print("=" * 40 + "\n")


    @kernel
    def krun(self, scan_vals, scan_vals_y, defaults, scan_idx, scan_idx_y, iter_idx):
        print("[DIAGNOSTIC] 1. Kernel Started (Entry)")

        cleanup_needed = True
        is_live_mode = (self.AWG_Mode == "live")
        awg_enabled = self.awg_enabled

        try:
            self.core.reset()

            # Outer loop over Y (Rows)
            for j in range(len(scan_vals_y)):
                if scan_idx_y != -1:
                    defaults[scan_idx_y] = float(scan_vals_y[j])

                # Inner loop over X (Columns: Left to Right)
                for i in range(len(scan_vals)): # also, 1D scan uses this loop
                    # print("[DIAGNOSTIC] Executing point (", i, ",", j, ")...")

                    if scan_idx != -1:
                        defaults[scan_idx] = float(scan_vals[i])

                    # Flat iteration counter for row-major order
                    flat_iter = (j * len(scan_vals)) + i
                    if iter_idx != -1:
                        defaults[iter_idx] = float(flat_iter)

                    AllZ_calib_flag = False

                    # AllZ autocalibration logic
                    if defaults[self.idx_checkAllZ_calib] > 0.5:
                        n = self.AllZ_calib_n_skip
                        AllZ_calib_flag = True
                        if flat_iter % n == 0:
                            for calib_j in range(self.AllZ_calib_num_pts):
                                self.core.break_realtime()
                                # self.rid_termination()
                                if self.check_termination_and_restore():
                                    print("[TERMINATION] Exiting krun cleanly between scan points.")
                                    return  # Safely returns from kernel without interrupting self.ON() mid-point
                                self.core.break_realtime()
                                # self.uninterrupted_processes()

                                defaults[self.idx_AllZ_calib_flag] = 1.0
                                defaults[self.idx_allZ] = self.allZ_calib_array[calib_j]

                                self.ON(
                                    defaults[self.idx_Frequency435], defaults[self.idx_Amplitude435],
                                    defaults[self.idx_Time435],
                                    defaults[self.idx_attenuation_435_1], int(defaults[self.idx_choice435channel_1_2]),
                                    defaults[self.idx_doppler_freq], defaults[self.idx_doppler_amp],
                                    defaults[self.idx_doppler_time],
                                    defaults[self.idx_det_freq], defaults[self.idx_det_amp],
                                    defaults[self.idx_DetTime369],
                                    defaults[self.idx_checkCameraDetection] > 0.5,
                                    defaults[self.idx_checkGlobalCoolingShot] > 0.5,
                                    defaults[self.idx_cameraCoolingShotTime],
                                    defaults[self.idx_freq_935], defaults[self.idx_amp_935],
                                    defaults[self.idx_prepfreqOP], defaults[self.idx_prepampOP],
                                    defaults[self.idx_preptimeOP],
                                    defaults[self.idx_prepfreqLOP], defaults[self.idx_prepampLOP],
                                    defaults[self.idx_preptimeLOP],
                                    defaults[self.idx_FrequencyMW], defaults[self.idx_AmplitudeMW],
                                    defaults[self.idx_TimeMW],
                                    defaults[self.idx_SBCcheck] > 0.5, defaults[self.idx_SBCFrequency355_1],
                                    defaults[self.idx_SBCAmplitude355_1],
                                    defaults[self.idx_SBCFrequency355_2], defaults[self.idx_SBCAmplitude355_2],
                                    defaults[self.idx_SBCTime], defaults[self.idx_SBCAmplitude935],
                                    defaults[self.idx_ClearoutPower935], defaults[self.idx_ClearoutTime935],
                                    defaults[self.idx_prepfreq435], defaults[self.idx_preptime],
                                    defaults[self.idx_WaitTime], defaults[self.idx_Ramseycheck] > 0.5,
                                    defaults[self.idx_Phase1],
                                    defaults[self.idx_Phase2],
                                    defaults[self.idx_EnableAWG] > 0.5, defaults[self.idx_MScheck] > 0.5,
                                    defaults[self.idx_B1check] > 0.5, defaults[self.idx_Frequency355_Raman1],
                                    defaults[self.idx_Amplitude355_Raman1],
                                    defaults[self.idx_A16check] > 0.5, defaults[self.idx_Frequency355_RamanA16],
                                    defaults[self.idx_Amplitude355_RamanA16],
                                    defaults[self.idx_B2check] > 0.5, defaults[self.idx_Frequency355_RamanB2],
                                    defaults[self.idx_Amplitude355_RamanB2],
                                    defaults[self.idx_A15check] > 0.5, defaults[self.idx_Frequency355_RamanA15],
                                    defaults[self.idx_Amplitude355_RamanA15],
                                    defaults[self.idx_RamanTime], defaults[self.idx_LighShiftFactor_BSB],
                                    defaults[self.idx_GlobalSidebandAmpScale], defaults[self.idx_Bz],
                                    defaults[self.idx_RamseyFrequency435mod], defaults[self.idx_RamseyAmplitude435],
                                    defaults[self.idx_PiBy2Time435_1], defaults[self.idx_PiBy2Time435_2],
                                    defaults[self.idx_endcapX], defaults[self.idx_allY], defaults[self.idx_allZ],
                                    defaults[self.idx_endcap_avg],
                                    defaults[self.idx_piezoR1H], defaults[self.idx_piezoR1V],
                                    defaults[self.idx_piezoR2H],
                                    defaults[self.idx_piezoR2V],
                                    int(defaults[self.idx_num_repeat]), int(defaults[self.idx_iter]),
                                    defaults[self.idx_checkLineTrigger] > 0.5,
                                    defaults[self.idx_checkAllZ_calib] > 0.5, defaults[self.idx_AllZ_calib_flag] > 0.5
                                )
                                self.host_push_results(self.AllZ_calib_histpoints, calib_j, 0, True)

                        AllZ_calib_flag = False
                        defaults[self.idx_AllZ_calib_flag] = 0.0
                        self.AllZcalibFitter()

                    # Live Mode Hook
                    if awg_enabled and is_live_mode:
                        self.load_awg_step_rpc(flat_iter, len(scan_vals) * len(scan_vals_y), 0)

                    # Timing & Safety
                    self.core.break_realtime()
                    # self.rid_termination()
                    if self.check_termination_and_restore():
                        print("[TERMINATION] Exiting krun cleanly between scan points.")
                        return  # Safely returns from kernel without interrupting self.ON() mid-point
                    self.core.break_realtime()
                    # self.uninterrupted_processes()

                    # Physics
                    self.ON(
                        defaults[self.idx_Frequency435], defaults[self.idx_Amplitude435],
                        defaults[self.idx_Time435],
                        defaults[self.idx_attenuation_435_1], int(defaults[self.idx_choice435channel_1_2]),
                        defaults[self.idx_doppler_freq], defaults[self.idx_doppler_amp],
                        defaults[self.idx_doppler_time],
                        defaults[self.idx_det_freq], defaults[self.idx_det_amp], defaults[self.idx_DetTime369],
                        defaults[self.idx_checkCameraDetection] > 0.5,
                        defaults[self.idx_checkGlobalCoolingShot] > 0.5,
                        defaults[self.idx_cameraCoolingShotTime],
                        defaults[self.idx_freq_935], defaults[self.idx_amp_935],
                        defaults[self.idx_prepfreqOP], defaults[self.idx_prepampOP],
                        defaults[self.idx_preptimeOP],
                        defaults[self.idx_prepfreqLOP], defaults[self.idx_prepampLOP],
                        defaults[self.idx_preptimeLOP],
                        defaults[self.idx_FrequencyMW], defaults[self.idx_AmplitudeMW],
                        defaults[self.idx_TimeMW],
                        defaults[self.idx_SBCcheck] > 0.5, defaults[self.idx_SBCFrequency355_1],
                        defaults[self.idx_SBCAmplitude355_1],
                        defaults[self.idx_SBCFrequency355_2], defaults[self.idx_SBCAmplitude355_2],
                        defaults[self.idx_SBCTime], defaults[self.idx_SBCAmplitude935],
                        defaults[self.idx_ClearoutPower935], defaults[self.idx_ClearoutTime935],
                        defaults[self.idx_prepfreq435], defaults[self.idx_preptime],
                        defaults[self.idx_WaitTime], defaults[self.idx_Ramseycheck] > 0.5,
                        defaults[self.idx_Phase1],
                        defaults[self.idx_Phase2],
                        defaults[self.idx_EnableAWG] > 0.5, defaults[self.idx_MScheck] > 0.5,
                        defaults[self.idx_B1check] > 0.5, defaults[self.idx_Frequency355_Raman1],
                        defaults[self.idx_Amplitude355_Raman1],
                        defaults[self.idx_A16check] > 0.5, defaults[self.idx_Frequency355_RamanA16],
                        defaults[self.idx_Amplitude355_RamanA16],
                        defaults[self.idx_B2check] > 0.5, defaults[self.idx_Frequency355_RamanB2],
                        defaults[self.idx_Amplitude355_RamanB2],
                        defaults[self.idx_A15check] > 0.5, defaults[self.idx_Frequency355_RamanA15],
                        defaults[self.idx_Amplitude355_RamanA15],
                        defaults[self.idx_RamanTime], defaults[self.idx_LighShiftFactor_BSB],
                        defaults[self.idx_GlobalSidebandAmpScale], defaults[self.idx_Bz],
                        defaults[self.idx_RamseyFrequency435mod], defaults[self.idx_RamseyAmplitude435],
                        defaults[self.idx_PiBy2Time435_1], defaults[self.idx_PiBy2Time435_2],
                        defaults[self.idx_endcapX], defaults[self.idx_allY], defaults[self.idx_allZ],
                        defaults[self.idx_endcap_avg],
                        defaults[self.idx_piezoR1H], defaults[self.idx_piezoR1V], defaults[self.idx_piezoR2H],
                        defaults[self.idx_piezoR2V],
                        int(defaults[self.idx_num_repeat]), int(defaults[self.idx_iter]),
                        defaults[self.idx_checkLineTrigger] > 0.5,
                        defaults[self.idx_checkAllZ_calib] > 0.5, defaults[self.idx_AllZ_calib_flag] > 0.5
                    )

                    # Push Results using column index (i) and row index (j)
                    self.host_push_results(self.histpoints, i, j, AllZ_calib_flag)

            cleanup_needed = False

        finally:
            if awg_enabled and is_live_mode:
                if cleanup_needed:
                    print("ARTIQ: Scan Aborted. Cleaning up AWG...")
                else:
                    print("ARTIQ: Scan Finished. Cleaning up AWG...")
                self.cleanup_awg()


    # original
    # @rpc(flags={"async"})
    # def rid_termination(
    #         self):  # required to teriminate any barebones scan script mid scan upon clicking terminate instances
    #     rid = self.scheduler.rid
    #     if self.scheduler.check_termination(rid):
    #         print("[TERMINATION] Abort requested. Submitting DC_Control to restore voltages...")
    #
    #         # 1. Submit DC_Control to reset DAC voltages BEFORE deleting this run
    #         DCcontrolId = {
    #             "file": "RFandDC/DCelectrodes.py",
    #             "class_name": "DC_Control",
    #             "arguments": {},
    #             "log_level": self.scheduler.expid["log_level"],
    #             "repo_rev": self.scheduler.expid["repo_rev"],
    #         }
    #         self.scheduler.submit("main", DCcontrolId)
    #
    #         self.scheduler.delete(rid)

    #test
    @rpc
    def check_termination_and_restore(self) -> TBool:
        """
        Checks if the GUI requested termination between scan points.
        If requested, queues laser/DC recovery and returns True to exit krun cleanly.
        """
        rid = self.scheduler.rid
        if self.scheduler.check_termination(rid):
            print("[TERMINATION] Abort detected between scan points. Restoring lasers...")

            # 1. Turn Doppler and 935 AOMs back ON
            expid_ExpConfigAOMsOn = {
                "file": "Manual Control/exp_config_idle_AOMs_on.py",
                "class_name": "ExpConfigAOMsOn",
                "arguments": {
                    "u0ch1_Doppler": True
                },
                "log_level": 0,
                "repo_rev": self.scheduler.expid["repo_rev"],
            }
            self.scheduler.submit("main", expid_ExpConfigAOMsOn)

            # 2. Reset DC electrodes
            expid_DC = {
                "file": "RFandDC/DCelectrodes.py",
                "class_name": "DC_Control",
                "arguments": {},
                "log_level": self.scheduler.expid["log_level"],
                "repo_rev": self.scheduler.expid["repo_rev"],
            }
            self.scheduler.submit("main", expid_DC)

            # DO NOT call self.scheduler.delete(rid) — let krun exit naturally!
            return True

        return False

    # test
    @rpc(flags={"async"})
    def host_push_results(self, histpoints, i, j=0, AllZ_calib_flag=False):
        is_init_point = (int(i) == 0 and int(j) == 0)

        # Process counts for current step
        if self.CheckThresholding:
            y_val, y_err = binom_onesided(np.sum(histpoints >= self.PMTThreshold), self.num_repeat)
        else:
            y_val = float(np.mean(histpoints))
            y_err = float(y_val / np.sqrt(self.num_repeat))

        # --- ALL-Z CALIBRATION HANDLING ---
        if self.checkAllZ_calib and AllZ_calib_flag:
            x_val = self.allZ_calib_array[int(i)]
            target_x = "Calibrations.AllZ_calib_x"
            target_y = "Calibrations.AllZ_calib_y"
            target_err = "Calibrations.AllZ_calib_y_err"

            if is_init_point:
                self.set_dataset(target_x, [x_val], broadcast=True)
                self.set_dataset(target_y, [y_val], broadcast=True)
                self.set_dataset(target_err, [y_err], broadcast=True)

                rid = getattr(self.scheduler, "rid", "Local")
                command2 = (
                    "${artiq_applet}plot_xy Calibrations.AllZ_calib_y "
                    "--x Calibrations.AllZ_calib_x "
                    "--error Calibrations.AllZ_calib_y_err "
                    f"--title 'RID {rid}: Counts vs AllZ [V]' "
                )
                self.ccb.issue("create_applet", "Barebones AllZ Monitor", command2)
            else:
                self.append_to_dataset(target_x, x_val)
                self.append_to_dataset(target_y, y_val)
                self.append_to_dataset(target_err, y_err)
            return

        # --- 2D SCAN HANDLING ---
        if getattr(self, "is_2d_scan", False):
            # Map execution loop indices (i, j) to spatial grid coordinates (grid_x, grid_y)
            grid_x = self.x_index_map[int(i)] if hasattr(self, "x_index_map") else int(i)
            grid_y = self.y_index_map[int(j)] if hasattr(self, "y_index_map") else int(j)

            self.z_mat[grid_y, grid_x] = y_val
            self.set_dataset("ScanDataPlot.z_vals", self.z_mat.copy(), broadcast=True)

            if is_init_point:
                self.ccb.issue("disable_applet", "Barebones Scan Plot")

                # Update initial bounds using the sorted arrays
                self.set_dataset("ScanDataPlot.x_vals", self.plot_scan_arr_sorted, broadcast=True)
                self.set_dataset("ScanDataPlot.y_vals", self.plot_scan_arr_y_sorted, broadcast=True)

                rid = getattr(self.scheduler, "rid", "Local")
                x_name = getattr(self, "scan_param_name_x", getattr(self, "scan_param_name", "X Axis"))
                x_unit = getattr(self, "scan_unit_x", getattr(self, "scan_unit", ""))
                x_label = f"{x_name} [{x_unit}]" if x_unit else str(x_name)

                y_name = getattr(self, "scan_param_name_y", getattr(self, "scan_param_y", "Y Axis"))
                y_unit = getattr(self, "scan_unit_y", "")
                y_label = f"{y_name} [{y_unit}]" if y_unit else str(y_name)

                command_2d = (
                    "${artiq_applet}plot_2d ScanDataPlot.z_vals "
                    "--x ScanDataPlot.x_vals --y ScanDataPlot.y_vals "
                    f"--x-label '{x_label}' --y-label '{y_label}' "
                    f"--title 'RID {rid}'"
                )
                self.ccb.issue("create_applet", "Barebones 2D Heatmap", command_2d)
            return

        # --- 1D SCAN HANDLING ---
        # Because plot_scan_arr wasn't sorted, it matches execution order exactly
        x_val = self.plot_scan_arr[int(i)]
        target_x = "ScanDataPlot.x_vals"
        target_y = "ScanDataPlot.y_vals"
        target_err = "ScanDataPlot.yerr_vals"

        if is_init_point:
            self.ccb.issue("disable_applet", "Barebones 2D Heatmap")

            self.set_dataset(target_x, [x_val], broadcast=True)
            self.set_dataset(target_y, [y_val], broadcast=True)
            self.set_dataset(target_err, [y_err], broadcast=True)

            rid = getattr(self.scheduler, "rid", "Local")
            xlabel = f"{self.scan_param_name} [{self.scan_unit}]" if self.scan_unit else str(self.scan_param_name)
            ylabel = "Counts"

            command1 = (
                "${artiq_applet}plot_xy ScanDataPlot.y_vals "
                "--x ScanDataPlot.x_vals "
                "--error ScanDataPlot.yerr_vals "
                f"--x-label '{xlabel}' "
                f"--y-label '{ylabel}' "
                f"--title 'RID {rid}' "
            )
            self.ccb.issue("create_applet", "Barebones Scan Plot", command1)
        else:
            self.append_to_dataset(target_x, x_val)
            self.append_to_dataset(target_y, y_val)
            self.append_to_dataset(target_err, y_err)

    # original
    # @rpc(flags={"async"})
    # def host_push_results(self, histpoints, i, j=0, AllZ_calib_flag=False):
    #     # print(f"[HOST LOG] Pushing point ({i}, {j}) - mean: {np.mean(histpoints):.2f}")
    #
    #     is_init_point = (int(i) == 0 and int(j) == 0)
    #
    #     # Process counts for current step
    #     if self.CheckThresholding:
    #         y_val, y_err = binom_onesided(np.sum(histpoints >= self.PMTThreshold), self.num_repeat)
    #     else:
    #         y_val = float(np.mean(histpoints))
    #         y_err = float(y_val / np.sqrt(self.num_repeat))
    #
    #     # --- ALL-Z CALIBRATION HANDLING ---
    #     if self.checkAllZ_calib and AllZ_calib_flag:
    #         x_val = self.allZ_calib_array[int(i)]
    #         target_x = "Calibrations.AllZ_calib_x"
    #         target_y = "Calibrations.AllZ_calib_y"
    #         target_err = "Calibrations.AllZ_calib_y_err"
    #
    #         if is_init_point:
    #             self.set_dataset(target_x, [x_val], broadcast=True)
    #             self.set_dataset(target_y, [y_val], broadcast=True)
    #             self.set_dataset(target_err, [y_err], broadcast=True)
    #
    #             rid = getattr(self.scheduler, "rid", "Local")
    #             command2 = (
    #                 "${artiq_applet}plot_xy Calibrations.AllZ_calib_y "
    #                 "--x Calibrations.AllZ_calib_x "
    #                 "--error Calibrations.AllZ_calib_y_err "
    #                 f"--title 'RID {rid}: Counts vs AllZ [V]' "
    #             )
    #             self.ccb.issue("create_applet", "Barebones AllZ Monitor", command2)
    #         else:
    #             self.append_to_dataset(target_x, x_val)
    #             self.append_to_dataset(target_y, y_val)
    #             self.append_to_dataset(target_err, y_err)
    #
    #         return
    #
    #     # --- 2D SCAN HANDLING ---
    #     if getattr(self, "is_2d_scan", False):
    #         # Insert current point into matrix
    #         self.z_mat[int(j)][int(i)] = y_val
    #
    #         # Broadcast updated matrix
    #         self.set_dataset("ScanDataPlot.z_vals", self.z_mat.copy(), broadcast=True)
    #
    #         if is_init_point:
    #             # Disable 1D plot if open
    #             self.ccb.issue("disable_applet", "Barebones Scan Plot")
    #
    #             # Broadcast formatted plot arrays
    #             self.set_dataset("ScanDataPlot.x_vals", self.plot_scan_arr, broadcast=True)
    #             self.set_dataset("ScanDataPlot.y_vals", self.plot_scan_arr_y, broadcast=True)
    #
    #             rid = getattr(self.scheduler, "rid", "Local")
    #
    #             # X Axis Label Construction
    #             x_name = getattr(self, "scan_param_name_x", getattr(self, "scan_param_name", "X Axis"))
    #             x_unit = getattr(self, "scan_unit_x", getattr(self, "scan_unit", ""))
    #             x_label = f"{x_name} [{x_unit}]" if x_unit else str(x_name)
    #
    #             # Y Axis Label Construction
    #             y_name = getattr(self, "scan_param_name_y", getattr(self, "scan_param_y", "Y Axis"))
    #             y_unit = getattr(self, "scan_unit_y", "")
    #             y_label = f"{y_name} [{y_unit}]" if y_unit else str(y_name)
    #
    #             command_2d = (
    #                 "${artiq_applet}plot_2d ScanDataPlot.z_vals "
    #                 "--x ScanDataPlot.x_vals --y ScanDataPlot.y_vals "
    #                 f"--x-label '{x_label}' --y-label '{y_label}' "
    #                 f"--title 'RID {rid}'"
    #             )
    #             self.ccb.issue("create_applet", "Barebones 2D Heatmap", command_2d)
    #
    #         return
    #
    #     # --- 1D SCAN HANDLING ---
    #     x_val = self.plot_scan_arr[int(i)]
    #     target_x = "ScanDataPlot.x_vals"
    #     target_y = "ScanDataPlot.y_vals"
    #     target_err = "ScanDataPlot.yerr_vals"
    #
    #     if is_init_point:
    #         # Disable 2D plot if open
    #         self.ccb.issue("disable_applet", "Barebones 2D Heatmap")
    #
    #         self.set_dataset(target_x, [x_val], broadcast=True)
    #         self.set_dataset(target_y, [y_val], broadcast=True)
    #         self.set_dataset(target_err, [y_err], broadcast=True)
    #
    #         rid = getattr(self.scheduler, "rid", "Local")
    #         xlabel = f"{self.scan_param_name} [{self.scan_unit}]" if self.scan_unit else str(self.scan_param_name)
    #         ylabel = "Counts"
    #
    #         command1 = (
    #             "${artiq_applet}plot_xy ScanDataPlot.y_vals "
    #             "--x ScanDataPlot.x_vals "
    #             "--error ScanDataPlot.yerr_vals "
    #             f"--x-label '{xlabel}' "
    #             f"--y-label '{ylabel}' "
    #             f"--title 'RID {rid}' "
    #         )
    #         self.ccb.issue("create_applet", "Barebones Scan Plot", command1)
    #     else:
    #         self.append_to_dataset(target_x, x_val)
    #         self.append_to_dataset(target_y, y_val)
    #         self.append_to_dataset(target_err, y_err)


    # -----Analyze-----#
    def save_global_dataset(self):
        '''
         Save all global dataset parameters in a dictionary here.
        '''

        parentdir = r"C:\Users\TrappedIonRice4\Documents\Artiq-Rice"  # system dependent
        datasetdir = parentdir + "\dataset_db.pyon"
        self.globaldataset = {}
        f = open(datasetdir, 'r')
        txt = f.readlines()
        f.close()  # must close the dataset file soon enough to reflect the updates.
        for ele in txt[1:-1]:  # ignoring curly braces
            ele2 = ele.split(":")  # some regex
            ele3 = (ele2[0].split('    '))[-1]
            ele4 = ''.join(list(ele3)[1:-1])
            self.globaldataset[ele4] = self.get_dataset(ele4)

    def analyze(self):  # artiq barebone's postscan function, similar to host_cleaup() in ndscan

        ## reinstantisate global dataset DC values
        DCcontrolId = {
            "file": "RFandDC/DCelectrodes.py",
            "class_name": "DC_Control",
            "arguments": {},
            "log_level": self.scheduler.expid["log_level"],
            "repo_rev": self.scheduler.expid["repo_rev"],
        }
        self.scheduler.submit("main", DCcontrolId)
        self.set_dataset('Histogram', self.scanHistogramList, broadcast=True, archive=True, persist=True)
        self.save_global_dataset()

        # camera roi data
        if self.checkCameraDetection:
            self.cameraCOMM_postscan()
    # --------------#


