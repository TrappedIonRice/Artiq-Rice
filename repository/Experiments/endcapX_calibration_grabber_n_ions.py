"""
Calibration for the two EDGE ions of a chain (double differential): Delta P vs EndcapX (axial, "X") or vs AllY (radial, "Y").

Camera GUI: ONE ROI per ion, centred on the ion (N ions -> N ROIs; e.g. 6 ions -> 6 ROIs). Nothing else is drawn. The two edge
ions are `ion_a_roi` (default 0, the first) and `ion_b_roi` (default -1, the last); the same ROI for both (or a single ROI on the
GUI) calibrates one ion. ARTIQ creates the pairs itself, in Grabber slots that are not on the GUI: the ion's ROI is shifted by
half its size (first = left / upper) and a ROI of the same size is put directly next to it (second = right / lower, in an extra
slot), so the common boundary runs through the ion. Which image direction EndcapX moves the ion in is set by `endcapX_along`
(the AllY pair is the other way round). Same ROI size for all ions, e.g. 6x6 px.

At each voltage of the scanned knob, `frames_per_point` frames are taken while the chain is Doppler cooled
(cooling shot, no experiment) and BOTH pairs are read in the same frames:

        Delta P_i = (first_i - second_i) / (first_i + second_i)      (bias-subtracted counts per pixel), i = first, last

Three curves are produced, each fitted with   Delta P = B + A * erf((V - V0) / w):
  * first : the first ion,
  * last  : the last ion,
  * avg   : (Delta P_first + Delta P_last) / 2, the average position of the chain (insensitive to a symmetric
            stretch / compression of the chain), with its own S-curve fit.
Three applets show them (points with error bars + fit).

Results are stored under  Calibrations.Two_ions.<knob>_<first|last|avg>_<key>  (knob = EndcapX or AllY), keys V, dP, dP_err,
fit, sigmoid_A/B/w/V0_err/chi2_red, V0, slope, slope_err, gain (+ L, R for first / last), and the common keys
Calibrations.Two_ions.<knob>_{roi_pairs, n_ions, axis, exposure_ms, frame_period_ms, dark_pp_first, dark_pp_last, time}.
The chain stabilizer (grabber_chain_stabilizer.py) reads these.

Requirements (camera GUI / Camera.py): the cooling-shot combo box = "None"; Camera.py with the `extra_frames` field.
Hardware set-up lines are copied from BarebonesArtiqScan2DGrabberV2.ON() wherever possible.
26/10/01 gt
"""
from artiq.experiment import *
from artiq.coredevice.rtio import rtio_input_timestamped_data
from artiq.coredevice.grabber import OutOfSyncException
import numpy as np
import json
import socket
import struct
import time
import math



# ----------------------------------------------------------------------------------------------
# Pure helpers (no ARTIQ): grabber statistics with binomial / beta-distribution error bars
# ----------------------------------------------------------------------------------------------
try:
    from oitg.errorbars import binom_onesided
except Exception:                                   # oitg not importable: fall back below
    binom_onesided = None


def binom_p_err(k, n):
    """Success probability k/n of n shots and its 1-sigma error from the beta posterior (same as the main
    experiment: oitg.errorbars.binom_onesided; fallback = Jeffreys interval Beta(k+1/2, n-k+1/2))."""
    k = int(k); n = int(n)
    if n <= 0:
        return float('nan'), float('nan')
    if binom_onesided is not None:
        try:
            p, e = binom_onesided(k, n)
            return float(p), float(np.mean(np.atleast_1d(e)))
        except Exception:
            pass
    try:
        from scipy.stats import beta
        lo = beta.ppf(0.15865, k + 0.5, n - k + 0.5)
        hi = beta.ppf(0.84135, k + 0.5, n - k + 0.5)
        return k / n, float(0.5 * (hi - lo))
    except Exception:
        p = k / n
        return p, float(np.sqrt(max(p * (1 - p), 1.0 / (4 * n)) / n))


def pair_rois(axis, nth, frame=None):
    """ROI pair used for the differential signal, built from the N-th ROI (marginal ion), integer pixels.
    nth = (x0, y0, x1, y1); frame = {"w":..., "h":...} (optional bounds check). Image y grows downwards.
      axis "X": stacked vertically.  first = nth moved up by h//2, second directly below it (same x range).
      axis "Y": side by side.        first = nth moved left by w//2, second directly right of it (same rows).
    Both ROIs have the size of nth. Returns (first, second); dP = (first - second) / (first + second)."""
    x0, y0, x1, y1 = (int(v) for v in nth)
    w, h = x1 - x0, y1 - y0
    if axis == "X":
        s = h // 2
        first, second = (x0, y0 - s, x1, y1 - s), (x0, y1 - s, x1, y1 - s + h)
    elif axis == "Y":
        s = w // 2
        first, second = (x0 - s, y0, x1 - s, y1), (x1 - s, y0, x1 - s + w, y1)
    else:
        raise ValueError(f"axis must be 'X' or 'Y', got {axis!r}")
    for r in (first, second):
        if r[0] < 0 or r[1] < 0 or (frame and (r[2] > frame["w"] or r[3] > frame["h"])):
            raise RuntimeError(f"ROI {r} for the {axis} pair falls outside the camera frame {frame}; "
                               f"move the ion ROIs away from the frame edge")
    return first, second


def pair_stats(raw, npix, dark_pp, use_thr, thr):
    """raw: (frames, 2) ROI sums; npix: (2,) pixels per ROI; dark_pp: bias per pixel (scalar or (2,)).
    use_thr False: mean counts/px (bias subtracted), error = propagated standard error of the means.
    use_thr True : probability that counts/px >= thr (per ROI), error from the beta distribution
                   (binom_onesided), as the main experiment's CheckThresholding. Raw (not bias-subtracted) counts/px
                   are compared with thr, exactly as the main experiment does.
    Returns (first, second, sum, dP, err_dP) with dP = (first - second) / (first + second)."""
    per_px = np.asarray(raw, dtype=float) / np.asarray(npix, dtype=float)
    n_f = per_px.shape[0]
    if use_thr:
        thr = np.asarray(thr, dtype=float)
        k = (per_px >= thr).sum(axis=0)
        p1, e1 = binom_p_err(k[0], n_f)
        p2, e2 = binom_p_err(k[1], n_f)
        S = p1 + p2
        if S > 0:
            dP = (p1 - p2) / S
            err = 2.0 * math.sqrt((p2 * e1) ** 2 + (p1 * e2) ** 2) / S ** 2
        else:
            dP, err = float('nan'), float('nan')
        return p1, p2, S, dP, err
    a = per_px - dark_pp
    L, R = a[:, 0], a[:, 1]
    Lm, Rm = float(L.mean()), float(R.mean())
    S = Lm + Rm
    dP = (Lm - Rm) / S if S > 0 else float('nan')
    if n_f > 1 and S > 0:
        cov = np.cov(L, R, ddof=1) / n_f
        gL, gR = 2.0 * Rm / S ** 2, -2.0 * Lm / S ** 2
        err = float(np.sqrt(max(gL * gL * cov[0, 0] + gR * gR * cov[1, 1] + 2 * gL * gR * cov[0, 1], 0.0)))
    else:
        err = float('nan')
    return Lm, Rm, S, dP, err


def fit_sigmoid(V, y, yerr, err_floor=0.02):
    """Weighted fit of  y = B + A * erf((V - V0) / w)  (w > 0) to all points.
    Returns a dict (A, B, V0, w, slope = 2A/(sqrt(pi) w) at V0, gain = 1/slope, their 1-sigma errors,
    chi2_red, yfit at the data points) or None if scipy is missing / the fit fails."""
    try:
        from scipy.optimize import curve_fit
        from scipy.special import erf
    except Exception:
        return None
    V = np.asarray(V, dtype=float)
    y = np.asarray(y, dtype=float)
    e = np.asarray(yerr, dtype=float)
    ok = np.isfinite(V) & np.isfinite(y)
    if ok.sum() < 5:
        return None
    V, y, e = V[ok], y[ok], e[ok]
    sig = np.where(np.isfinite(e), np.maximum(e, err_floor), 0.05)   # floor: keeps lucky tiny error bars from dominating

    def model(v, A, B, V0, w):
        return B + A * erf((v - V0) / w)

    # starting values: half range, mid level, zero crossing, a third of the scan for the width
    A0 = 0.5 * (y.max() - y.min())
    B0 = 0.5 * (y.max() + y.min())
    sign = 1.0 if np.polyfit(V, y, 1)[0] >= 0 else -1.0
    order = np.argsort(V)
    Vs, ys = V[order], y[order] - B0
    cross = np.where(np.sign(ys[:-1]) != np.sign(ys[1:]))[0]
    V00 = float(Vs[cross[len(cross) // 2]]) if len(cross) else float(V.mean())
    w0 = max((V.max() - V.min()) / 6.0, 1e-4)
    try:
        popt, pcov = curve_fit(model, V, y, p0=[sign * abs(A0), B0, V00, w0], sigma=sig, absolute_sigma=True,
                               bounds=([-2.0, -1.0, V.min(), 1e-5], [2.0, 1.0, V.max(), V.max() - V.min() + 1e-5]),
                               maxfev=20000)
    except Exception:
        return None
    A, B, V0, w = (float(v) for v in popt)
    perr = np.sqrt(np.clip(np.diag(pcov), 0, None))
    resid = (y - model(V, *popt)) / sig
    dof = max(len(V) - 4, 1)
    chi2_red = float((resid ** 2).sum() / dof)
    infl = math.sqrt(chi2_red) if chi2_red > 1 else 1.0          # inflate if the scatter exceeds the error bars
    slope = 2.0 * A / (math.sqrt(math.pi) * w)
    # error of slope = 2A/(sqrt(pi) w) from the covariance of (A, w)
    rel2 = (perr[0] / A) ** 2 + (perr[3] / w) ** 2 - 2.0 * pcov[0, 3] / (A * w) if A != 0 else float('nan')
    slope_err = abs(slope) * math.sqrt(max(rel2, 0.0)) * infl
    return {"A": A, "B": B, "V0": V0, "w": w, "V0_err": float(perr[2]) * infl,
            "slope": slope, "slope_err": slope_err, "gain": 1.0 / slope if slope != 0 else float('nan'),
            "chi2_red": chi2_red, "yfit": model(V, *popt), "order_V": V}


class ChainCalibrationGrabber(EnvExperiment):
    """EndcapX calibration (2 edge ions)"""

    def build(self):
        # ---- devices (same names as the main experiment) ----
        self.setattr_device("core")
        self.setattr_device("ccb")
        self.setattr_device("scheduler")
        self.setattr_device("grabber0")
        self.setattr_device("zotino0")
        self.setattr_device("urukul0_cpld")  # clock sync
        self.setattr_device("urukul0_ch1")   # Doppler
        self.setattr_device("urukul1_cpld")
        self.setattr_device("urukul1_ch3")   # 'protection' switch of the global cooling shot (optional)
        self.setattr_device("urukul2_cpld")
        self.setattr_device("urukul2_ch3")   # ULE 369
        self.setattr_device("ttl4")          # camera trigger
        self.setattr_device("ttl6")

        # ---- arguments ----
        def add_scannable(name, argument, group=None, tooltip=None):
            """Wrapper for setattr_argument: records the name and unit of every scannable."""
            if not hasattr(self, "scannable_names"):
                self.scannable_names = []
            if not hasattr(self, "scannable_units"):
                self.scannable_units = {}
            self.scannable_units[name] = getattr(argument, "unit", "")
            if name not in self.scannable_names:
                self.scannable_names.append(name)
            self.setattr_argument(name, argument, group=group, tooltip=tooltip)

        g = "Scan"
        self.setattr_argument("scan_axis", EnumerationValue(["X (EndcapX)", "Y (AllY)"], default="X (EndcapX)"),
                              group=g, tooltip="Which DC knob is scanned. Only the matching scannable below is used.")
        self.setattr_argument("max_excursion", NumberValue(default=0.5, unit="V", min=0.0, step=0.05, ndecimals=3),
                              group=g,
                              tooltip="Safety: refuse to run if any scan voltage differs from the current "
                                      "dataset value of that knob by more than this")
        self.setattr_argument("scan_order", EnumerationValue(["as_entered", "up_and_down", "random"],
                                                             default="as_entered"), group=g)
        self.setattr_argument("settle_time", NumberValue(default=100 * ms, unit="ms", min=0, step=10 * ms,
                                                         ndecimals=1), group=g,
                              tooltip="Wait after each DC change (Doppler cooling on)")

        d0 = float(self.get_dataset("Experiment_config.endcapX"))
        add_scannable("EndcapX_scan",
                      Scannable(RangeScan(d0 - 0.1, d0 + 0.1, 21),
                                global_min=-9.0, global_max=9.0, global_step=1.0e-3,
                                unit="V", ndecimals=4),
                      group="EndcapX scan (X)",
                      tooltip="ABSOLUTE EndcapX voltage (V), like the endcapX scannable of the main experiment. "
                              "Default: current Experiment_config.endcapX +- 0.1 V")
        y0 = float(self.get_dataset("Experiment_config.all_y"))
        add_scannable("AllY_scan",
                      Scannable(RangeScan(y0 - 0.1, y0 + 0.1, 21),
                                global_min=-9.0, global_max=9.0, global_step=1.0e-3,
                                unit="V", ndecimals=4),
                      group="AllY scan (Y)",
                      tooltip="ABSOLUTE AllY voltage (V), like the allY scannable of the main experiment. "
                              "Default: current Experiment_config.all_y +- 0.1 V")

        g = "Cooling shot"
        self.setattr_argument("frames_per_point", NumberValue(default=100, step=1, ndecimals=0, min=1), group=g)
        self.setattr_argument("dark_frames", NumberValue(default=100, step=1, ndecimals=0, min=0), group=g,
                              tooltip="Frames with the Doppler light off, taken once at the start (EMCCD bias)")
        self.setattr_argument("exposure", NumberValue(default=1 * ms, unit="ms", min=0.05 * ms, step=0.1 * ms,
                                                      ndecimals=3), group=g,
                              tooltip="Camera trigger pulse width = exposure (trigger mode 7)")
        self.setattr_argument("frame_period", NumberValue(default=15 * ms, unit="ms", min=9 * ms, step=1 * ms,
                                                          ndecimals=1), group=g,
                              tooltip="Fixed spacing between camera triggers. 15 ms is what the burst test proved. "
                                      "Each frame is read one period after its trigger (data arrive ~9 ms after it).")
        self.setattr_argument("grabber_timeout", NumberValue(default=100 * ms, unit="ms", min=1 * ms, step=10 * ms,
                                                             ndecimals=1), group=g)
        self.setattr_argument("protection_switch", BooleanValue(default=False), group=g,
                              tooltip="Switch urukul1_ch3 on during the shot, as in the global cooling shot")

        g = "Chain"
        self.setattr_argument("ion_a_roi", NumberValue(default=0, step=1, ndecimals=0), group=g,
                              tooltip="Index of the camera-GUI ROI centred on the first edge ion (0 = first ROI)")
        self.setattr_argument("ion_b_roi", NumberValue(default=-1, step=1, ndecimals=0), group=g,
                              tooltip="Index of the camera-GUI ROI centred on the last edge ion (negative = counted from the end). "
                                      "Same as ion_a_roi (or one ROI on the GUI): a single ion is calibrated")
        self.setattr_argument("endcapX_along", EnumerationValue(["image_horizontal", "image_vertical"],
                                                                default="image_horizontal"), group=g,
                              tooltip="Direction in the camera image in which EndcapX moves the ion. "
                                      "image_horizontal: X pair side by side, Y pair stacked; image_vertical: the other way round.")

        g = "Housekeeping"
        self.setattr_argument("restore_idle", BooleanValue(default=True), group=g,
                              tooltip="At the end: restore the DC electrodes and restart the idler, like the main experiment")

    # ------------------------------------------------------------------------------------------
    # prepare
    # ------------------------------------------------------------------------------------------

    def prepare(self):
        # kill the idler, as the main experiment does
        for rid, job in self.scheduler.get_status().items():
            if job["expid"]["class_name"] == "Idle369On355Pulsed":
                print(f"[CAL] Found active idler (RID {rid}). Requesting termination...")
                self.scheduler.request_termination(rid)
                while rid in self.scheduler.get_status():
                    time.sleep(0.05)

        def numeric(x):
            if hasattr(x, "get"): return x.get()
            if hasattr(x, "value"): return x.value
            return float(x)

        # electrodes (separate copies; the kernel modifies modDCElectrodeValues)
        self.originalDCElectrodeValues = [float(v) for v in self.get_dataset("DC.ElectrodeValues")]
        self.modDCElectrodeValues = [float(v) for v in self.get_dataset("DC.ElectrodeValues")]
        self.DCElectrodeMapping = [int(v) for v in self.get_dataset("DC.ElectrodeMapping")]
        self.originalEndcapX = float(self.get_dataset("Experiment_config.endcapX"))
        self.originalAllY = float(self.get_dataset("Experiment_config.all_y"))
        self.originalAllZ = float(self.get_dataset("Experiment_config.all_z"))
        self.originalEndcapAvg = float(self.get_dataset("Experiment_config.endcap_avg"))
        # piezo voltages, written with every DC update exactly as in the main experiment's ON()
        self.piezo_R1H = float(self.get_dataset("355_RamanB1.H1"))
        self.piezo_R1V = float(self.get_dataset("355_RamanB1.V1"))
        self.piezo_R2V = float(self.get_dataset("355_Raman2.V2"))

        # lasers
        self.doppler_freq = numeric(self.get_dataset("Doppler.Frequency"))
        self.doppler_amp = numeric(self.get_dataset("Experiment_config.DopplerAmp"))
        self.ULE_369_Amp = numeric(self.get_dataset("369_ULE.Amp"))
        self.ULE_369_Frequency_exp = numeric(self.get_dataset("Experiment_config.ULE369_freq"))
        self.ULE_369_Att = numeric(self.get_dataset("369_ULE.Attenuation"))
        self.ULE_ramp_rate = numeric(self.get_dataset("369_ULE.ramp_rate"))
        self.ULE_time_step = numeric(self.get_dataset("369_ULE.time_step"))
        self.default_Raman_time = self.get_dataset("355_RamanB1.Time(ms)") * ms
        self.default_SBCTime = self.get_dataset("SBC.tone1.Time(ms)") * ms

        # ints / flags for the kernel
        self.frames = int(self.frames_per_point)
        self.n_dark = int(self.dark_frames)
        self.use_protection = bool(self.protection_switch)
        self.settle = float(self.settle_time)
        self.frame_counter = 0
        self.n_points_pushed = 0
        self._camera_closed = False

        # scan voltages (absolute) of the chosen knob
        self.axis_key = "X" if str(self.scan_axis).startswith("X") else "Y"
        if self.axis_key == "X":
            self.cal_name, self.knob_label, v_orig = "EndcapX", "EndcapX", self.originalEndcapX
            asc = np.array([float(v) for v in self.EndcapX_scan], dtype=float)
        else:
            self.cal_name, self.knob_label, v_orig = "AllY", "AllY", self.originalAllY
            asc = np.array([float(v) for v in self.AllY_scan], dtype=float)
        worst = float(np.max(np.abs(asc - v_orig)))
        if worst > float(self.max_excursion):
            raise ValueError(f"{self.knob_label} scan reaches {worst:.3f} V away from the current {v_orig:.4f} V, "
                             f"more than max_excursion = {float(self.max_excursion):.3f} V. Check the scan range.")
        if self.scan_order == "up_and_down":
            order = np.concatenate([asc, asc[-2::-1]])
        elif self.scan_order == "random":
            order = np.random.default_rng(1).permutation(asc)
        else:
            order = asc
        self.scan_volts = [float(v) for v in order]
        self.n_run = len(self.scan_volts)
        # the kernel sets BOTH knobs at every point; the one that is not scanned stays at its dataset value
        if self.axis_key == "X":
            self.scan_x = list(self.scan_volts)
            self.scan_y = [float(self.originalAllY)] * self.n_run
        else:
            self.scan_x = [float(self.originalEndcapX)] * self.n_run
            self.scan_y = list(self.scan_volts)
        print(f"[CAL] {self.knob_label} scan: {self.n_run} points from {min(self.scan_volts):.4f} to "
              f"{max(self.scan_volts):.4f} V (current {v_orig:.4f} V), order = {self.scan_order}")

        # kernel defaults (overwritten by the prescan)
        self.roi_x0, self.roi_y0, self.roi_x1, self.roi_y1 = [0], [0], [0], [0]
        self.n_roi = 1
        self.roi_mask = 1
        self.gbuf = [0]
        self.i0, self.i1, self.i2, self.i3 = 0, 0, 0, 0      # word indices of first_a, second_a, first_b, second_b
        self.tr_npix = np.ones(4)
        self.buf = [0] * (4 * max(self.frames, self.n_dark, 1))
        self.dark = np.zeros(4)

        # host-side results
        self.TAGS = ("first", "last", "avg")      # reduced to ("first",) in the prescan for a single ion (one ion)
        self.single = False
        self.res_V = []
        self.res = {t: {"dP": [], "err": [], "L": [], "R": []} for t in self.TAGS}
        self.base = f"Calibrations.Two_ions.{self.cal_name}_"
        self.n_ions_found = 0

        # camera: tell it how many frames to expect, receive the ROIs
        self.cameraHOST = '127.0.0.6'
        self.cameraPORT = 65438
        self.send_datapacket = {
            'x': {'name': f'{self.cal_name} [V]', 'value': self.scan_volts},
            'rid': getattr(self.scheduler, "rid", -1),
            'repetitions': self.frames,
            'Experiment exposure time': {"value": float(self.exposure) / ms, "unit": "ms"},
            'mode': 'grabber',
            'extra_frames': self.n_dark,
        }
        self.cameraCOMM_prescan()

    # ------------------------------------------------------------------------------------------
    # camera communication (same protocol as the main experiment)
    # ------------------------------------------------------------------------------------------

    def _camera_request(self, msg, timeout):
        def recv_exact(c, n):
            buf = bytearray()
            while len(buf) < n:
                chunk = c.recv(n - len(buf))
                if not chunk:
                    raise ConnectionError("socket closed mid-message")
                buf += chunk
            return bytes(buf)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((self.cameraHOST, self.cameraPORT))
            payload = json.dumps(msg).encode('utf-8')
            s.sendall(struct.pack(">I", len(payload)) + payload)
            (n,) = struct.unpack(">I", recv_exact(s, 4))
            return json.loads(recv_exact(s, n).decode('utf-8'))

    def cameraCOMM_prescan(self):
        print("--- sending scan info to the camera / receiving ROIs ---")
        try:
            reply = self._camera_request(dict(self.send_datapacket, cmd="start"), timeout=60)
        except Exception as e:
            raise RuntimeError(f"Camera prescan failed: {e}. Is the camera GUI running (live mode)?")
        if reply.get("status") == "error":
            raise RuntimeError(f"Camera refused to start: {reply.get('error')}")
        try:
            rois = sorted(reply.get("rois") or [], key=lambda r: r["id"])
            frame = reply.get("frame")
            if len(rois) < 1:
                raise RuntimeError(f"Need at least 1 ROI (one per ion) on the camera GUI, got {len(rois)}")
            if len(rois) > 16:
                raise RuntimeError(f"{len(rois)} ROIs defined, gateware supports 16")

            self.roi_x0, self.roi_y0, self.roi_x1, self.roi_y1, npix = [], [], [], [], []
            for k, r in enumerate(rois):
                x0, y0, x1, y1 = (int(r[key]) for key in ("x0", "y0", "x1", "y1"))
                if not (0 <= x0 < x1 and 0 <= y0 < y1):
                    raise RuntimeError(f"ROI {k} degenerate/negative: {(x0, y0, x1, y1)}")
                if frame and not (x1 <= frame["w"] and y1 <= frame["h"]):
                    raise RuntimeError(f"ROI {k} {(x0, y0, x1, y1)} outside frame {frame}")
                self.roi_x0.append(x0); self.roi_y0.append(y0)
                self.roi_x1.append(x1); self.roi_y1.append(y1)
                npix.append((x1 - x0) * (y1 - y0))
            n_cam = len(rois)
            n_ions = n_cam
            self.n_ions_found = n_ions

            def idx(v):
                v = int(v)
                return v + n_cam if v < 0 else v
            ia, ib = idx(self.ion_a_roi), idx(self.ion_b_roi)
            if not (0 <= ia < n_cam and 0 <= ib < n_cam):
                raise RuntimeError(f"Bad ion ROI indices {self.ion_a_roi}, {self.ion_b_roi} for {n_cam} ROIs")
            self.single = (ia == ib)
            if n_cam + (1 if self.single else 2) > 16:
                raise RuntimeError(f"{n_cam} ROIs + partner ROIs exceed the 16 Grabber slots")
            if self.single:
                self.TAGS = ("first",)
                self.res = {t: {"dP": [], "err": [], "L": [], "R": []} for t in self.TAGS}
            box = lambda k: (self.roi_x0[k], self.roi_y0[k], self.roi_x1[k], self.roi_y1[k])
            horiz = (str(self.endcapX_along) == "image_horizontal")
            if self.axis_key == "X":
                kind = "Y" if horiz else "X"          # pair_rois("Y") = side by side, ("X") = stacked
            else:
                kind = "X" if horiz else "Y"
            gui_a, gui_b = list(box(ia)), list(box(ib))      # GUI boxes, before the slots are overwritten below
            f1, s1 = pair_rois(kind, box(ia), frame)
            f2, s2 = (f1, s1) if self.single else pair_rois(kind, box(ib), frame)
            # slots: the ion's own slot takes 'first', an extra slot (n_cam, n_cam + 1) takes 'second'
            sl_a1, sl_b1 = ia, n_cam
            sl_a2, sl_b2 = (sl_a1, sl_b1) if self.single else (ib, n_cam + 1)
            n_slots = n_cam + (1 if self.single else 2)
            for lst in (self.roi_x0, self.roi_y0, self.roi_x1, self.roi_y1):
                lst.extend([0] * (n_slots - len(lst)))
            for sl, r in ((sl_a1, f1), (sl_b1, s1), (sl_a2, f2), (sl_b2, s2)):
                self.roi_x0[sl], self.roi_y0[sl], self.roi_x1[sl], self.roi_y1[sl] = r
            used = sorted({sl_a1, sl_b1, sl_a2, sl_b2})       # the Grabber returns the gated ROIs in ascending slot order
            self.n_roi = n_slots
            self.roi_mask = sum(1 << k for k in used)
            self.gbuf = [0] * len(used)
            self.i0, self.i1 = used.index(sl_a1), used.index(sl_b1)
            self.i2, self.i3 = used.index(sl_a2), used.index(sl_b2)
            area = lambda r: float((r[2] - r[0]) * (r[3] - r[1]))
            self.tr_npix = np.array([area(f1), area(s1), area(f2), area(s2)])
            self.roi_pairs = [[list(f1), list(s1)]] if self.single else [[list(f1), list(s1)], [list(f2), list(s2)]]
            print(f"[CAL] {n_cam} ROIs on the GUI (N = {n_ions} ions, one per ion), {'left / right' if kind == 'Y' else 'upper / lower'} "
                  f"pairs built in ARTIQ. First ion: ROI {ia} {gui_a} -> first {list(f1)} (slot {sl_a1}), second {list(s1)} (extra slot {sl_b1})")
            if self.single:
                print("[CAL] single ion: one pair only (dataset tag 'first')")
            else:
                print(f"[CAL] Last ion: ROI {ib} {gui_b} -> first {list(f2)} (slot {sl_a2}), second {list(s2)} (extra slot {sl_b2})")
            sizes = {tuple(np.array(box(k))[2:] - np.array(box(k))[:2]) for k in {ia, ib}}
            if len(sizes) > 1:
                print(f"[CAL WARNING] the two ion ROIs have different sizes {sizes}")
            self.set_dataset("Camera.rois", json.dumps(reply), persist=True, archive=True)
        except Exception:
            # the camera has already been armed by "start": release it, otherwise it freezes waiting for triggers
            self._recover_camera()
            raise

    def _recover_camera(self):
        print("[CAL] setup failed after the camera was armed: recovery pulse + abort, restoring the machine")
        self._release_camera()
        if self.restore_idle:
            self.scheduler.submit("main", {
                "file": "RFandDC/DCelectrodes.py", "class_name": "DC_Control", "arguments": {},
                "log_level": self.scheduler.expid["log_level"], "repo_rev": self.scheduler.expid["repo_rev"]})
            self.scheduler.submit("main", {
                "file": "Experiments/idle_369_on_355_pulsed.py", "class_name": "Idle369On355Pulsed",
                "arguments": {"timeRaman": self.default_Raman_time, "timeSBC": self.default_SBCTime},
                "log_level": 0, "repo_rev": self.scheduler.expid["repo_rev"]})

    @rpc
    def cameraCOMM_postscan(self):
        if self._camera_closed:
            # run() already aborted the acquisition (early stop / error): a "fetch" on an aborted acquisition
            # can block the camera, so do not send it
            print("[camera] acquisition was aborted earlier, not fetching")
            return
        completed = bool(self.n_points_pushed >= self.n_run)
        try:
            reply = self._camera_request({"cmd": "fetch", "completed": completed}, timeout=180)
            self._camera_closed = True
        except Exception as e:
            print(f"!!! camera fetch failed: {e}")
            return
        expected = self.n_dark + self.n_run * self.frames
        frames = reply.get("frames")
        print(f"[CAL] camera acquired {frames} frames, expected {expected}")
        if completed and frames is not None and frames != expected:
            print("[CAL WARNING] frame count mismatch: triggers were missed (trigger spacing too short?) or the camera GUI's "
                  "cooling-shot combo box is not 'None'")

    @rpc
    def cameraCOMM_abort(self):
        try:
            self._camera_request({"cmd": "abort"}, timeout=15)
        except Exception as e:
            print(f"[camera] abort failed: {e}")
        self._camera_closed = True

    def _release_camera(self):
        """Stop an armed acquisition. The abort request is sent in a background thread; if the camera does not answer
        within 0.5 s (its acquisition thread is blocked waiting for a trigger), trigger pulses are sent until it does."""
        import threading
        res = {}

        def worker():
            try:
                self._camera_request({"cmd": "abort"}, timeout=60)
                res["ok"] = True
            except Exception as e:
                res["err"] = repr(e)

        th = threading.Thread(target=worker, daemon=True)
        th.start()
        th.join(0.5)
        rounds = 0
        while th.is_alive() and rounds < 10:
            rounds += 1
            print("[CAL] camera did not answer the abort: sending trigger pulses (round %d)" % rounds)
            try:
                self.camera_pulses(20)
            except Exception as e:
                print("[CAL] camera_pulses failed:", repr(e))
                break
            th.join(0.6)
        if th.is_alive():
            print("[CAL] WARNING: camera still not released; toggle the trigger line by hand / restart the camera GUI")
        elif res.get("err"):
            print("[camera] abort failed:", res["err"])
        else:
            print("[CAL] camera released" + (" after %d pulse round(s)" % rounds if rounds else ""))
        self._camera_closed = True

    # ------------------------------------------------------------------------------------------
    # kernels
    # ------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------
    @kernel
    def EndcapX(self, V):
        """pushes towards +ve X with endcaps (same as the main experiment)"""
        self.electrodeUpdate(V, [1, 5, 6, 10], [1, -1, -1, 1])

    @kernel
    def electrodeUpdate(self, V, electrodeList, signList):
        for i in range(len(electrodeList)):
            self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] = \
                self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] + V * (signList[i])

    @kernel
    def AllY(self, V):
        """pushes towards +ve Y with all electrodes (same as the main experiment)"""
        self.electrodeUpdate(V, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], [-1] + [-1] * 5 + [1] * 5 + [1])

    @kernel
    def AllZ(self, V):
        """pushes towards +ve Z with all electrodes (same as the main experiment)"""
        self.electrodeUpdate(V, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], [1] + [-1] * 5 + [1] * 5 + [-1])

    @kernel
    def endcapAvg(self, V):
        """changes axial confinement (same as the main experiment)"""
        self.electrodeUpdate(V, [1, 5, 6, 10], [1, 1, 1, 1])

    @kernel
    def set_dc(self, newEndcapX, newAllY):
        """
        DC update copied from the start of the main experiment's ON(), step for step:
        zotino init, reset to the dataset electrode values, add the EndcapX/AllY/AllZ/endcapAvg
        offsets (AllZ and endcapAvg are zero: they equal their datasets), write the 12 electrode
        channels and the piezo channels 24/25/27, then ONE load(). No ramp, no extra writes.
        """
        self.zotino0.init()
        delay(2 * ms)

        for i in range(12):
            self.modDCElectrodeValues[i] = self.originalDCElectrodeValues[i]
        newX = newEndcapX - self.originalEndcapX
        newY = newAllY - self.originalAllY
        newZ = self.originalAllZ - self.originalAllZ
        newendcapAvg = self.originalEndcapAvg - self.originalEndcapAvg

        self.EndcapX(newX)
        self.AllY(newY)
        self.AllZ(newZ)
        self.endcapAvg(newendcapAvg)

        self.core.break_realtime()

        for i in range(12):
            ind = self.DCElectrodeMapping[i]
            self.zotino0.write_dac(self.DCElectrodeMapping[i], self.modDCElectrodeValues[ind])

        self.zotino0.write_dac(24, self.piezo_R1H)   # PZ H indiv
        self.zotino0.write_dac(25, self.piezo_R1V)   # PZ V indiv
        self.zotino0.write_dac(27, self.piezo_R2V)   # PZ V glo
        self.zotino0.load()
        delay(2 * ms)

    @kernel
    def uninterrupted_processes(self):
        # 369 ULE (as in the main experiment)
        self.urukul2_ch3.set(frequency=self.ULE_369_Frequency_exp, amplitude=self.ULE_369_Amp)
        self.urukul2_ch3.set_att(self.ULE_369_Att * dB)
        self.urukul2_ch3.sw.on()

    @kernel
    def setup_hardware(self):
        self.core.break_realtime()
        self.urukul0_cpld.init()
        self.urukul1_cpld.init()
        self.urukul2_cpld.init()
        delay(10 * ms)

        # Doppler
        self.urukul0_ch1.init()
        self.urukul0_ch1.set_att(0 * dB)
        self.urukul0_ch1.set(frequency=self.doppler_freq, amplitude=self.doppler_amp, phase_mode=2)
        self.urukul0_ch1.sw.off()
        self.uninterrupted_processes()

        self.ttl4.output()
        self.ttl4.off()
        self.ttl6.output()
        self.ttl6.off()
        delay(1 * ms)

        # Grabber ROIs: all camera ROIs are gated, L and R are picked out of the frame words
        self.core.break_realtime()
        for k in range(self.n_roi):
            self.grabber0.setup_roi(k, self.roi_x0[k], self.roi_y0[k], self.roi_x1[k], self.roi_y1[k])
        self.core.break_realtime()
        self.grabber0.gate_roi(self.roi_mask)
        self.core.break_realtime()

        # warm up the Doppler AOM
        self.urukul0_ch1.sw.on()
        delay(500 * ms)

    @kernel
    def grabber_read_guarded(self, data, timeout_s, idx):
        # Grabber.input_mu with a timeout (the stock one blocks forever)
        timeout_mu = now_mu() + self.core.seconds_to_mu(timeout_s)
        channel = self.grabber0.channel_base + 1
        timestamp, sentinel = rtio_input_timestamped_data(timeout_mu, channel)
        if timestamp < 0:
            raise RuntimeError("Grabber frame timeout at frame {0}", np.int64(idx))
        if sentinel != self.grabber0.sentinel:
            raise OutOfSyncException
        for j in range(len(data)):
            timestamp, value = rtio_input_timestamped_data(timeout_mu, channel)
            if timestamp < 0:
                raise RuntimeError("Grabber timeout while reading ROI values at frame {0}", np.int64(idx))
            if value == self.grabber0.sentinel:
                raise OutOfSyncException
            data[j] = value

    @kernel
    def take_frames(self, n_frames, bright):
        """n_frames camera frames; Doppler on (bright) or off (dark). the four words (first_a, second_a, first_b, second_b) go to self.buf."""
        self.core.break_realtime()
        if bright:
            self.urukul0_ch1.sw.on()
            if self.use_protection:
                self.urukul1_ch3.sw.on()
        else:
            self.urukul0_ch1.sw.off()
        delay(2 * ms)                         # settle, same spacing as the Doppler phase of the main sequence
        for f in range(n_frames):
            self.ttl4.on()
            self.ttl6.on()# camera trigger; exposure = pulse width (trigger mode 7)
            delay(self.exposure)
            self.ttl4.off()
            delay((self.frame_period - self.exposure)/2.0)      # fixed trigger spacing, NOT tied to the frame arrival
            self.ttl6.off()
            delay((self.frame_period - self.exposure) / 2.0)
            self.grabber_read_guarded(self.gbuf, self.grabber_timeout, self.frame_counter + f)
            self.core.break_realtime()                     # no-op while the cursor is ahead of the RTIO counter
            self.buf[4 * f] = self.gbuf[self.i0]
            self.buf[4 * f + 1] = self.gbuf[self.i1]
            self.buf[4 * f + 2] = self.gbuf[self.i2]
            self.buf[4 * f + 3] = self.gbuf[self.i3]
        self.frame_counter += n_frames
        if self.use_protection:
            self.urukul1_ch3.sw.off()

    @kernel
    def camera_unstick(self):
        # Recovery on the camera trigger line: forces a falling edge, then pulses twice, so that a camera left
        # waiting for a trigger edge releases the SDK and the abort command can complete.
        self.core.reset()
        self.ttl4.output()
        delay(1 * ms)
        self.ttl4.off()
        delay(5 * ms)
        for _ in range(2):
            self.ttl4.on()
            delay(5 * ms)
            self.ttl4.off()
            delay(5 * ms)

    @kernel
    def camera_pulses(self, n):
        # n short trigger pulses, 15 ms apart (2 ms high): lets a camera thread that is blocked waiting for a frame move on
        self.core.reset()
        self.ttl4.output()
        delay(1 * ms)
        self.ttl4.off()
        delay(5 * ms)
        for _ in range(n):
            self.ttl4.on()
            delay(2 * ms)
            self.ttl4.off()
            delay(13 * ms)

    @rpc
    def should_stop(self) -> TBool:
        try:
            return bool(self.scheduler.check_termination(self.scheduler.rid))
        except Exception:
            return bool(self.scheduler.check_pause())

    @kernel
    def krun(self):
        try:
            self.core.reset()
            self.setup_hardware()

            if self.n_dark > 0:                       # dark frames once, at the initial voltage
                self.take_frames(self.n_dark, False)
                self.host_push_dark(self.buf, self.n_dark)

            for p in range(self.n_run):
                self.core.break_realtime()
                if self.should_stop():
                    print("[TERMINATION] Exiting krun cleanly between voltage points.")
                    return
                self.core.break_realtime()
                self.urukul0_ch1.sw.on()              # keep cooling while the voltage moves
                self.uninterrupted_processes()
                self.set_dc(self.scan_x[p], self.scan_y[p])
                delay(self.settle)
                self.take_frames(self.frames, True)
                self.host_push_point(p, self.scan_volts[p], self.buf, self.frames)
        finally:
            self.core.break_realtime()
            self.grabber0.gate_roi(0)
            self.set_dc(self.originalEndcapX, self.originalAllY)     # back to the initial voltages
            self.urukul0_ch1.sw.on()

    # ------------------------------------------------------------------------------------------
    # host side
    # ------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------
    # host side
    # ------------------------------------------------------------------------------------------
    @rpc(flags={"async"})
    def host_push_dark(self, buf, n):
        a = np.array(buf, dtype=float).reshape(-1, 4)[: int(n)]
        self.dark = a.mean(axis=0)
        dpp = self.dark / self.tr_npix
        print(f"[CAL] dark level per pixel: first ion {dpp[0]:.1f}, {dpp[1]:.1f}; last ion {dpp[2]:.1f}, {dpp[3]:.1f}")
        self.set_dataset(self.base + "dark_raw", self.dark, broadcast=True, archive=True)

    @rpc(flags={"async"})
    def host_push_point(self, p, V, buf, n):
        raw = np.array(buf, dtype=float).reshape(-1, 4)[: int(n)]
        dpp = self.dark / self.tr_npix
        s1 = pair_stats(raw[:, 0:2], self.tr_npix[0:2], dpp[0:2], False, 0.0)
        if self.single:
            s2 = s1
            dP = {"first": s1[3]}
            er = {"first": s1[4]}
            LR = {"first": (s1[0], s1[1])}
        else:
            s2 = pair_stats(raw[:, 2:4], self.tr_npix[2:4], dpp[2:4], False, 0.0)
            # (L, R, sum, dP, err) of each pair; the average position: mean of the two dP, independent errors
            dP = {"first": s1[3], "last": s2[3], "avg": 0.5 * (s1[3] + s2[3])}
            er = {"first": s1[4], "last": s2[4], "avg": 0.5 * math.sqrt(s1[4] ** 2 + s2[4] ** 2)}
            LR = {"first": (s1[0], s1[1]), "last": (s2[0], s2[1])}

        self.n_points_pushed += 1
        first = (len(self.res_V) == 0)
        self.res_V.append(float(V))
        for t in self.TAGS:
            self.res[t]["dP"].append(dP[t]); self.res[t]["err"].append(er[t])
            if t in LR:
                self.res[t]["L"].append(LR[t][0]); self.res[t]["R"].append(LR[t][1])
            vals = {"V": float(V), "dP": dP[t], "dP_err": er[t]}
            if t in LR:
                vals.update({"L": LR[t][0], "R": LR[t][1]})
            for key, v in vals.items():
                name = f"{self.base}{t}_{key}"
                if first:
                    self.set_dataset(name, [v], broadcast=True, archive=True)
                else:
                    self.append_to_dataset(name, v)
        if first:
            self._applets(with_fit=False, labels={t: "" for t in self.TAGS})
        if self.single:
            print(f"[CAL] point {int(p) + 1}/{self.n_run}: {self.knob_label} = {V:.4f} V, dP = {dP['first']:+.4f} +- {er['first']:.4f}   (sum {s1[2]:.1f} counts/px)")
        else:
            print(f"[CAL] point {int(p) + 1}/{self.n_run}: {self.knob_label} = {V:.4f} V, "
                  f"dP first = {dP['first']:+.4f} +- {er['first']:.4f}, last = {dP['last']:+.4f} +- {er['last']:.4f}, "
                  f"avg = {dP['avg']:+.4f} +- {er['avg']:.4f}   (sums {s1[2]:.1f}, {s2[2]:.1f} counts/px)")

    def _applets(self, with_fit, labels):
        rid = getattr(self.scheduler, "rid", "Local")
        cn = self.cal_name
        names = {"first": "1st ion", "last": "last ion", "avg": "average of the two edge ions"}
        for t in self.TAGS:
            pre = f"{self.base}{t}_"
            cmd = (f"${{artiq_applet}}plot_xy {pre}dP --x {pre}V --error {pre}dP_err "
                   + (f"--fit {pre}fit " if with_fit else "")
                   + f"--x-label '{cn} [V]' --y-label 'Delta P = (first-second)/(sum)' "
                   + f"--title 'RID {rid} {cn} calibration, {names[t]} {labels[t]}'")
            self.ccb.issue("create_applet", f"{cn} calibration {t}", cmd)

    def analyze(self):
        V = np.array(self.res_V)
        if len(V) > 0:
            idx = np.argsort(V, kind="stable")
            self.set_dataset(self.base + "run_order", idx, archive=True)
            Vs = V[idx]
            labels = {}
            ok_all = True
            print("\n" + "=" * 64)
            for t in self.TAGS:
                d = self.res[t]
                dP = np.array(d["dP"])[idx]; err = np.array(d["err"])[idx]
                pre = f"{self.base}{t}_"
                ds = lambda k, v, persist=False: self.set_dataset(pre + k, v, broadcast=True, archive=True, persist=persist)
                ds("V", Vs); ds("dP", dP); ds("dP_err", err)
                if d["L"]:
                    ds("L", np.array(d["L"])[idx]); ds("R", np.array(d["R"])[idx])
                sg = fit_sigmoid(Vs, dP, err)
                if sg is None:
                    print(f"[CAL] {t}: S-curve fit impossible (too few valid points, or scipy missing)")
                    labels[t] = "(no fit)"
                    ok_all = False
                    continue
                for k in ("A", "B", "w", "V0_err", "chi2_red"):
                    ds(f"sigmoid_{k}", sg[k], True)
                ds("fit", sg["yfit"])
                ds("V0", sg["V0"], True); ds("slope", sg["slope"], True)
                ds("slope_err", sg["slope_err"], True); ds("gain", sg["gain"], True)
                labels[t] = f": w = {sg['w'] * 1e3:.2f} mV, V0 = {sg['V0']:.4f} V"
                print(f"[CAL] {t:5s}: Delta P = B + A erf((V - V0)/w): A = {sg['A']:+.3f}, B = {sg['B']:+.3f}, "
                      f"w = {sg['w'] * 1e3:.2f} mV, V0 = {sg['V0']:.5f} +- {sg['V0_err']:.5f} V, "
                      f"slope = {sg['slope']:+.2f} /V, chi2_red = {sg['chi2_red']:.2f}")
            cds = lambda k, v, persist=True: self.set_dataset(self.base + k, v, broadcast=True, archive=True, persist=persist)
            cds("roi_pairs", json.dumps(self.roi_pairs)); cds("n_ions", int(self.n_ions_found))
            cds("axis", self.axis_key); cds("observable", "mean")
            cds("exposure_ms", float(self.exposure) / ms); cds("frame_period_ms", float(self.frame_period) / ms)
            dpp = self.dark / self.tr_npix
            cds("dark_pp_first", float(np.mean(dpp[0:2]))); cds("dark_pp_last", float(np.mean(dpp[2:4])))      # equal to the first for a single ion
            cds("time", time.time())
            self._applets(with_fit=True, labels=labels)
            print("=" * 64 + "\n")

        # close the camera side (back to live; frame-count check)
        self.cameraCOMM_postscan()

        # restore the machine like the main experiment does
        if self.restore_idle:
            self.scheduler.submit("main", {
                "file": "RFandDC/DCelectrodes.py", "class_name": "DC_Control", "arguments": {},
                "log_level": self.scheduler.expid["log_level"], "repo_rev": self.scheduler.expid["repo_rev"]})
            self.scheduler.submit("main", {
                "file": "Experiments/idle_369_on_355_pulsed.py", "class_name": "Idle369On355Pulsed",
                "arguments": {"timeRaman": self.default_Raman_time, "timeSBC": self.default_SBCTime},
                "log_level": 0, "repo_rev": self.scheduler.expid["repo_rev"]})

    def run(self):
        try:
            # ramp the ULE AOM to the experiment frequency (copied from the main experiment)
            current_freq = float(self.get_dataset("369_ULE.Frequency"))
            target_freq = float(self.ULE_369_Frequency_exp)
            ramp_rate = float(self.ULE_ramp_rate)
            time_step = float(self.ULE_time_step)
            freq_diff = abs(target_freq - current_freq)
            num_steps = math.ceil(freq_diff / ramp_rate) if (freq_diff > 0 and ramp_rate > 0) else 0
            ramp_duration = num_steps * (time_step + 0.003) + 0.5
            self.scheduler.submit("ule_ramp", {
                "file": "Manual Control/ULE369_Ramp.py", "class_name": "ULE369_control",
                "arguments": {"ramp_rate": self.ULE_ramp_rate, "target_frequency": self.ULE_369_Frequency_exp,
                              "time_step": self.ULE_time_step},
                "log_level": 0, "repo_rev": self.scheduler.expid["repo_rev"]})
            time.sleep(ramp_duration)

            print("[CAL] starting kernel...")
            self.krun()
        finally:
            if not self._camera_closed and self.n_points_pushed < self.n_run:
                print("[CAL] scan incomplete: sending recovery pulse to the camera trigger line, then abort")
                self._release_camera()