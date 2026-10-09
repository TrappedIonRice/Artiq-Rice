"""
Ion-position calibration with the Grabber: Delta P vs EndcapX (axial, "X") or vs AllY (radial, "Y").

Choose the axis with `scan_axis`. At each voltage of the chosen knob, `frames_per_point` camera frames are taken while the ion chain is Doppler cooled
(a "cooling shot"; no experiment is run) and read by the Grabber in two side-by-side ROIs (L and R) that
sit on one marginal ion of the chain. The differential

        Delta P = (L - R) / (L + R)           (bias-subtracted, counts per pixel)

is zero when the chain is centred on the two ROIs. Delta P(V) is an S-curve (the ion image crossing the
ROI boundary), so it is fitted with

        Delta P = B + A * erf( (V - V0) / w )

which gives V0 (Delta P = B, the centring voltage), the slope at the centre  2A / (sqrt(pi) w)  and the
gain 1/slope for the drift correction. A local linear fit (|Delta P| <= fit_limit) is kept for comparison
and as a fallback. The model can also be inverted for large offsets:  V = V0 + w * erfinv((dP - B) / A).

ROI pair: place the two ROIs yourself on the camera GUI (roi_left = first ROI, roi_right = second; by default the
last two). Same size as an ion ROI, with their common boundary through the ion:
  Orientation depends on how the knob moves the ion in the image: if EndcapX moves it horizontally, the X pair is side by side
  (first = left) and the Y pair stacked (first = upper); the other way round if vertical.
The geometry is saved (Calibrations.*_roi_pair) and the stabilizer checks that its own pair matches it.

Requirements (camera GUI / Camera.py):
  * the camera GUI's cooling-shot combo box set to "None" (the frame count must match);
  * Camera.py with the `extra_frames` field in `start_acquisition_andor` (numExp += extra_frames).

Results are stored under Calibrations.EndcapX_* (X) or Calibrations.AllY_* (Y), incl. sigmoid_A/B/w, V0, roi_pair.
Hardware set-up lines are copied from BarebonesArtiqScan2DGrabberV2.ON() wherever possible.
26/09/30 gt
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
# Pure helper (no ARTIQ): weighted straight-line fit, restricted to the near-linear region
# ----------------------------------------------------------------------------------------------
def fit_linear_window(V, y, yerr, limit=0.7):
    """Weighted least-squares line y = a*V + b using only points with |y| <= limit (all points if fewer
    than 3 qualify). Returns a dict with slope, slope_err, intercept, V0 (zero crossing), gain (=1/slope),
    n_used and the mask of the points used; None if the fit is impossible."""
    V = np.asarray(V, dtype=float)
    y = np.asarray(y, dtype=float)
    e = np.asarray(yerr, dtype=float)
    ok = np.isfinite(V) & np.isfinite(y)
    if ok.sum() < 3:
        return None
    sel = ok & (np.abs(y) <= limit)
    if sel.sum() < 3:
        sel = ok
    good_err = np.isfinite(e) & (e > 0)
    if good_err[sel].all():
        w = 1.0 / e[sel] ** 2
    else:
        w = np.ones(sel.sum())
    x = V[sel]
    yy = y[sel]
    S, Sx, Sy = w.sum(), (w * x).sum(), (w * yy).sum()
    Sxx, Sxy = (w * x * x).sum(), (w * x * yy).sum()
    delta = S * Sxx - Sx ** 2
    if delta <= 0:
        return None
    slope = (S * Sxy - Sx * Sy) / delta
    intercept = (Sxx * Sy - Sx * Sxy) / delta
    slope_err = math.sqrt(S / delta)
    dof = sel.sum() - 2
    if dof > 0:  # inflate if the scatter is larger than the error bars say
        chi2 = float((w * (yy - (slope * x + intercept)) ** 2).sum())
        if good_err[sel].all() and chi2 / dof > 1:
            slope_err *= math.sqrt(chi2 / dof)
    V0 = -intercept / slope if slope != 0 else float('nan')
    gain = 1.0 / slope if slope != 0 else float('nan')
    return {"slope": slope, "slope_err": slope_err, "intercept": intercept, "V0": V0, "gain": gain,
            "n_used": int(sel.sum()), "mask": sel}


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


class EndcapXCalibrationGrabber(EnvExperiment):
    """EndcapX calibration (Grabber)"""

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
        self.setattr_argument("roi_left", NumberValue(default=-2, step=1, ndecimals=0), group=g,
                              tooltip="Index of the first ROI of the pair (upper ROI for X, left ROI for Y) in the camera's ROI list (negative = from the end)")
        self.setattr_argument("roi_right", NumberValue(default=-1, step=1, ndecimals=0), group=g)
        self.setattr_argument("protection_switch", BooleanValue(default=False), group=g,
                              tooltip="Switch urukul1_ch3 on during the shot, as in the global cooling shot")

        g = "Debug"
        self.setattr_argument("burst_test", BooleanValue(default=False), group=g,
                              tooltip="Diagnostic: fire all dark-frame triggers 15 ms apart WITHOUT reading in between, "
                                      "then read them all, print the result and stop.")

        g = "Fit / housekeeping"
        self.setattr_argument("fit_limit", NumberValue(default=0.7, min=0.05, max=1.0, step=0.05, ndecimals=2),
                              group=g, tooltip="Only points with |Delta P| below this enter the linear fit")
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
        self.burst = bool(self.burst_test)
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
        self.iL, self.iR = 0, 0
        self.tr_npix = np.ones(2)
        self.buf = [0] * (2 * max(self.frames, self.n_dark, 1))
        self.dark = np.zeros(2)

        # host-side results
        self.res_V, self.res_dP, self.res_err, self.res_L, self.res_R = [], [], [], [], []

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
            if len(rois) < 2:
                raise RuntimeError(f"Need at least 2 ROIs (L and R) on the camera GUI, got {len(rois)}")
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
            self.n_roi = len(rois)
            self.roi_mask = (1 << self.n_roi) - 1
            self.gbuf = [0] * self.n_roi

            iL, iR = int(self.roi_left), int(self.roi_right)
            iL = iL + self.n_roi if iL < 0 else iL
            iR = iR + self.n_roi if iR < 0 else iR
            if not (0 <= iL < self.n_roi and 0 <= iR < self.n_roi) or iL == iR:
                raise RuntimeError(f"Bad L/R ROI indices ({iL}, {iR}) for {self.n_roi} ROIs")
            self.iL, self.iR = iL, iR
            self.tr_npix = np.array([npix[iL], npix[iR]], dtype=float)
            self.roi_pair = [[self.roi_x0[iL], self.roi_y0[iL], self.roi_x1[iL], self.roi_y1[iL]],
                             [self.roi_x0[iR], self.roi_y0[iR], self.roi_x1[iR], self.roi_y1[iR]]]
            print(f"[CAL] Camera ROIs: {self.n_roi}; L = ROI {iL} ({npix[iL]} px), R = ROI {iR} ({npix[iR]} px)")
            self.set_dataset("Camera.rois", json.dumps(reply), persist=True, archive=True)
        except Exception:
            # the camera has already been armed by "start": release it, otherwise it freezes waiting for triggers
            self._recover_camera()
            raise

    def _recover_camera(self):
        print("[CAL] setup failed after the camera was armed: recovery pulse + abort, restoring the machine")
        try:
            self.camera_unstick()
        except Exception as e:
            print("[CAL] camera_unstick failed:", repr(e))
        self.cameraCOMM_abort()
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

    # ------------------------------------------------------------------------------------------
    # kernels
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
        """n_frames camera frames; Doppler on (bright) or off (dark). L and R words go to self.buf."""
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
            self.buf[2 * f] = self.gbuf[self.iL]
            self.buf[2 * f + 1] = self.gbuf[self.iR]
        self.frame_counter += n_frames
        if self.use_protection:
            self.urukul1_ch3.sw.off()

    @kernel
    def burst_frames(self, n_frames):
        """Diagnostic. Triggers first (15 ms apart, no reads in between), reads afterwards."""
        self.core.break_realtime()
        self.urukul0_ch1.sw.off()
        delay(2 * ms)
        for f in range(n_frames):
            self.ttl4.on()
            delay(self.exposure)
            self.ttl4.off()
            delay(15 * ms - self.exposure)
        delay(self.frame_period)
        for f in range(n_frames):
            self.grabber_read_guarded(self.gbuf, self.grabber_timeout, f)
            self.core.break_realtime()
            self.buf[2 * f] = self.gbuf[self.iL]
            self.buf[2 * f + 1] = self.gbuf[self.iR]
        self.frame_counter += n_frames

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

            if self.burst:
                self.burst_frames(self.n_dark)
                self.host_push_dark(self.buf, self.n_dark)
                print("[CAL] burst test finished: all frames received")
                return

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
    @rpc(flags={"async"})
    def host_push_dark(self, buf, n):
        a = np.array(buf, dtype=float).reshape(-1, 2)[: int(n)]
        self.dark = a.mean(axis=0)
        print(f"[CAL] dark level (raw sums): L = {self.dark[0]:.1f}, R = {self.dark[1]:.1f} "
              f"-> per pixel {self.dark[0] / self.tr_npix[0]:.1f}, {self.dark[1] / self.tr_npix[1]:.1f}")
        self.set_dataset(f"Calibrations.{self.cal_name}_dark_raw", self.dark, broadcast=True, archive=True)

    @rpc(flags={"async"})
    def host_push_point(self, p, V, buf, n):
        a = (np.array(buf, dtype=float).reshape(-1, 2)[: int(n)] - self.dark) / self.tr_npix   # counts / pixel
        L, R = a[:, 0], a[:, 1]
        Lm, Rm = float(L.mean()), float(R.mean())
        dP = (Lm - Rm) / (Lm + Rm) if (Lm + Rm) > 0 else float('nan')
        # error of dP = (L-R)/(L+R) by propagation from the means (per-frame dP blows up when L+R ~ 0)
        n_f = L.size
        S = Lm + Rm
        if n_f > 1 and S > 0:
            cov = np.cov(L, R, ddof=1) / n_f                     # covariance matrix of the two means
            gL, gR = 2.0 * Rm / S ** 2, -2.0 * Lm / S ** 2       # d dP / dL, d dP / dR
            var = gL * gL * cov[0, 0] + gR * gR * cov[1, 1] + 2.0 * gL * gR * cov[0, 1]
            err = float(np.sqrt(max(var, 0.0)))
        else:
            err = float('nan')

        self.n_points_pushed += 1
        first = (len(self.res_V) == 0)
        self.res_V.append(float(V)); self.res_dP.append(dP); self.res_err.append(err)
        self.res_L.append(Lm); self.res_R.append(Rm)
        names = {"V": float(V), "dP": dP, "dP_err": err, "L": Lm, "R": Rm}
        for key, v in names.items():
            name = f"Calibrations.{self.cal_name}_{key}"
            if first:
                self.set_dataset(name, [v], broadcast=True, archive=True)
            else:
                self.append_to_dataset(name, v)
        if first:
            rid = getattr(self.scheduler, "rid", "Local")
            cn = self.cal_name
            cmd = (f"${{artiq_applet}}plot_xy Calibrations.{cn}_dP --x Calibrations.{cn}_V "
                   f"--error Calibrations.{cn}_dP_err --x-label '{cn} [V]' "
                   f"--y-label 'Delta P = (first-second)/(sum)' --title 'RID {rid} {cn} calibration'")
            self.ccb.issue("create_applet", f"{cn} calibration", cmd)
        print(f"[CAL] point {int(p) + 1}/{self.n_run}: {self.knob_label} = {V:.4f} V, L = {Lm:.1f}, R = {Rm:.1f} counts/px, "
              f"(L+R) = {Lm + Rm:.1f}, Delta P = {dP:+.4f} +- {err:.4f}")

    def analyze(self):
        # 1. fit. Re-sort by voltage so that the applet draws a clean curve in any scan order.
        V = np.array(self.res_V); dP = np.array(self.res_dP); err = np.array(self.res_err)
        L = np.array(self.res_L); R = np.array(self.res_R)
        if len(V) > 0:
            idx = np.argsort(V, kind="stable")
            V, dP, err, L, R = V[idx], dP[idx], err[idx], L[idx], R[idx]
            self.set_dataset(f"Calibrations.{self.cal_name}_run_order", idx, archive=True)
            lin = fit_linear_window(V, dP, err, limit=float(self.fit_limit))
            sig = fit_sigmoid(V, dP, err)
            if lin is None and sig is None:
                print("[CAL] fit impossible (too few valid points)")
            else:
                ds = lambda k, v, persist=False: self.set_dataset(f"Calibrations.{self.cal_name}_{k}", v, broadcast=True,
                                                                  archive=True, persist=persist)
                for name, val in (("V", V), ("dP", dP), ("dP_err", err), ("L", L), ("R", R)):
                    ds(name, val)
                if lin is not None:
                    ds("lin_slope", lin["slope"], True); ds("lin_V0", lin["V0"], True)
                    ds("lin_slope_err", lin["slope_err"], True)
                # primary result = S-curve fit; linear window fit if the S-fit is unavailable
                if sig is not None:
                    res = {"slope": sig["slope"], "slope_err": sig["slope_err"], "V0": sig["V0"], "gain": sig["gain"]}
                    yfit = sig["yfit"]
                    for k in ("A", "B", "w", "V0_err", "chi2_red"):
                        ds(f"sigmoid_{k}", sig[k], True)
                    label = f"S-fit slope = {sig['slope']:.1f} /V, V0 = {sig['V0']:.4f} V"
                else:
                    res = {k: lin[k] for k in ("slope", "slope_err", "V0", "gain")}
                    yfit = lin["slope"] * V + lin["intercept"]
                    label = f"linear slope = {lin['slope']:.1f} /V, V0 = {lin['V0']:.4f} V"
                ds("fit", yfit)
                ds("roi_pair", json.dumps(self.roi_pair), True)       # the stabilizer checks that its ROI pair matches
                ds("axis", self.axis_key, True)
                ds("slope", res["slope"], True); ds("slope_err", res["slope_err"], True)
                ds("V0", res["V0"], True); ds("gain", res["gain"], True)
                rid = getattr(self.scheduler, "rid", "Local")
                cn = self.cal_name
                cmd = (f"${{artiq_applet}}plot_xy Calibrations.{cn}_dP --x Calibrations.{cn}_V "
                       f"--error Calibrations.{cn}_dP_err --fit Calibrations.{cn}_fit "
                       f"--x-label '{cn} [V]' --y-label 'Delta P = (first-second)/(sum)' "
                       f"--title 'RID {rid} {cn}: {label}'")
                self.ccb.issue("create_applet", f"{cn} calibration", cmd)
                print("\n" + "=" * 64)
                if sig is not None:
                    print(f"[CAL] S-curve fit: Delta P = B + A erf((V - V0)/w)   (chi2_red = {sig['chi2_red']:.2f})")
                    print(f"[CAL]   A = {sig['A']:+.3f}, B = {sig['B']:+.3f}, w = {sig['w'] * 1e3:.2f} mV")
                    print(f"[CAL]   V0    = {sig['V0']:.5f} +- {sig['V0_err']:.5f} V  (chain centred on the ROIs)")
                    print(f"[CAL]   slope = {sig['slope']:+.2f} +- {sig['slope_err']:.2f} per V at V0")
                    print(f"[CAL]   gain 1/slope = {sig['gain'] * 1e3:+.2f} mV per unit Delta P")
                    print(f"[CAL]   quasi-linear range (|Delta P - B| < |A|/2): about V0 +- "
                          f"{0.477 * sig['w'] * 1e3:.1f} mV")
                if lin is not None:
                    print(f"[CAL] linear window fit (|Delta P| <= {float(self.fit_limit):.2f}, {lin['n_used']} of "
                          f"{len(V)} points): slope = {lin['slope']:+.2f} +- {lin['slope_err']:.2f} per V, "
                          f"V0 = {lin['V0']:.5f} V")
                print("=" * 64 + "\n")

        # 2. close the camera side (back to live; frame-count check)
        self.cameraCOMM_postscan()

        # 3. restore the machine like the main experiment does
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
                try:
                    self.camera_unstick()
                    print("[CAL] recovery pulse sent")
                except Exception as e:
                    print("[CAL] camera_unstick failed:", repr(e))
                self.cameraCOMM_abort()