"""
Ion-position stabilizer test with the Grabber (standalone, no experiment): track the drift of the ion chain with
"cooling shots" and optionally correct it with the EndcapX (axial, X) and AllY (radial, Y) calibrations.

N ions -> N+1 ROIs on the camera GUI: one ROI centred on each ion, the (N+1)-th spare ROI just below the last one.
Every cycle (hold_time of Doppler cooling stands in for the experiment, then a cooling shot):

  X measurement: the N-th ROI (where YOU put it on the ion before the run) is shifted by half its size and the spare
                 ROI is put directly next to it, so that their common boundary runs through the ion (side by side for
                 EndcapX, stacked for AllY with the default endcapX_along). frames_per_axis frames are
                 taken, Delta P = (first - second)/(sum), the S-curve shape from the calibration
                 Delta P = B + A erf((V - V0)/w) is inverted, and (correct_and_track) EndcapX is moved to cancel it.
  Y measurement: the same with the AllY calibration's pair and AllY.
  Then both ROIs return to their original positions (where the real experiment would run), and the next cycle starts.

mode = "track_only" measures exactly the same but never changes the DC voltages (the free drift);
mode = "correct_and_track" closes the loop (proportional with gain, deadband, step and excursion limits).
Run both and compare the logged `Stabilizer.*_resid_mV` (offset of the chain from the centre, measured BEFORE each
correction) and `*_drift_mV` (the drift in EndcapX/AllY-equivalent mV, = offset minus what has been applied).

Needs the calibrations from EndcapX_calibration_grabber.py (scan_axis = X and/or Y):
Calibrations.EndcapX_* and Calibrations.AllY_* (only the S-curve shape sigmoid_A, sigmoid_B, sigmoid_w is used; no
position). The zero point of the offsets is the boundary of the ROI pair built from the N-th ROI as placed on the GUI,
so before every run put the N-th ROI on the ion and leave the spare ROI anywhere below it.

Camera requirements: the GUI's cooling-shot combo box = "None"; Camera.py with `extra_frames`.
DC updates are copied step for step from BarebonesArtiqScan2DGrabberV2.ON() (no ramp): keep steps small.
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


def erfinv_safe(u):
    """Inverse error function for |u| < 1 (Winitzki start + Newton steps with math.erf)."""
    u = float(u)
    if u == 0.0:
        return 0.0
    a = 0.147
    ln = math.log(1.0 - u * u)
    t = 2.0 / (math.pi * a) + ln / 2.0
    x = math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), u)
    for _ in range(4):
        err = math.erf(x) - u
        x -= err / (2.0 / math.sqrt(math.pi) * math.exp(-x * x))
    return x


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


RESID_CLIP = 0.9      # |u| above this: the offset ESTIMATE (for display) is clipped at w*erfinv(0.9) ~ 1.16 w


def axis_correction(dP, S, cal, v_cur, v_ref, gain, deadband_v, max_step, max_dev, min_sum, cutoff):
    """One correction step for one axis, gain INSIDE the inverse model with a cutoff on the error.
    cal = (A, B, w, V0) of the S-curve dP = B + A erf((V - V0)/w); v_cur = voltage now applied; v_ref = the
    voltage at start (excursion reference); cutoff = end of the linear part of the S-curve in units of w.
    With u = (dP - B)/A:  correction = -w * erfinv(gain * clip(u, +-erf(cutoff))).
    The step is monotonic toward the centre, never exceeds w*erfinv(gain*erf(cutoff)), is the same as
    gain*offset near the centre and slightly smaller further out. max_step and max_dev stay as hard limits.
    Returns (resid, sat, lost, dv_raw, v_new):
      resid  = estimated offset of the chain from the centre in volts of this knob (display value)
      sat    = |u| > erf(cutoff): the error was clamped (chain on the flat part, only a bounded step is made)
      lost   = no usable signal (dP not finite or S < min_sum): nothing is changed
    """
    A, Bc, w, V0 = cal
    if (not math.isfinite(dP)) or (not math.isfinite(S)) or S < min_sum:
        return float('nan'), False, True, 0.0, v_cur
    u = (dP - Bc) / A
    resid = w * erfinv_safe(math.copysign(min(abs(u), RESID_CLIP), u))
    u_c = math.erf(cutoff)
    sat = abs(u) > u_c
    u_cl = math.copysign(u_c, u) if sat else u
    if abs(w * erfinv_safe(u_cl)) < deadband_v:
        dv = 0.0
    else:
        dv = -w * erfinv_safe(gain * u_cl)
    dv = max(-max_step, min(max_step, dv))
    v_new = max(v_ref - max_dev, min(v_ref + max_dev, v_cur + dv))
    return resid, sat, False, -resid, v_new


class GrabberIonStabilizer(EnvExperiment):
    """Grabber ion stabilizer (X, Y): correct_and_track / track_only"""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("ccb")
        self.setattr_device("scheduler")
        self.setattr_device("grabber0")
        self.setattr_device("zotino0")
        self.setattr_device("urukul0_cpld")
        self.setattr_device("urukul0_ch1")   # Doppler
        self.setattr_device("urukul1_cpld")
        self.setattr_device("urukul1_ch3")
        self.setattr_device("urukul2_cpld")
        self.setattr_device("urukul2_ch3")   # ULE 369
        self.setattr_device("ttl4")          # camera trigger
        self.setattr_device("ttl6")

        g = "Stabilizer"
        self.setattr_argument("mode", EnumerationValue(["correct_and_track", "track_only"],
                                                       default="track_only"), group=g,
                              tooltip="track_only: measure only, DC never changed after the start (free drift). "
                                      "correct_and_track: apply the corrections.")
        self.setattr_argument("track_x", BooleanValue(default=True), group=g)
        self.setattr_argument("track_y", BooleanValue(default=True), group=g)
        self.setattr_argument("n_cycles", NumberValue(default=50, step=1, ndecimals=0, min=1), group=g,
                              tooltip="Number of cooling shots (each with an X and/or a Y measurement)")
        self.setattr_argument("hold_time", NumberValue(default=1.0, unit="s", min=0.0, step=0.1, ndecimals=2),
                              group=g, tooltip="Doppler cooling between two cooling shots (stands in for the experiment)")
        self.setattr_argument("settle_time", NumberValue(default=100 * ms, unit="ms", min=0, step=10 * ms,
                                                         ndecimals=1), group=g,
                              tooltip="Wait after each DC correction (Doppler on)")

        g = "Controller"
        self.setattr_argument("loop_gain", NumberValue(default=0.7, min=0.0, max=1.0, step=0.1, ndecimals=2),
                              group=g, tooltip="Fraction of the measured offset corrected per cycle")
        self.setattr_argument("deadband_mV", NumberValue(default=1.0, min=0.0, step=0.5, ndecimals=2), group=g,
                              tooltip="No correction if the measured offset is smaller than this (mV of the knob)")
        self.setattr_argument("max_step_mV", NumberValue(default=5.0, min=0.1, step=0.5, ndecimals=2), group=g,
                              tooltip="Largest change of the knob per cycle (mV)")
        self.setattr_argument("max_excursion_mV", NumberValue(default=30.0, min=0.1, step=1.0, ndecimals=1),
                              group=g, tooltip="The knob is never moved further than this from its starting value (mV)")
        self.setattr_argument("min_signal", NumberValue(default=5.0, min=0.0, step=1.0, ndecimals=1), group=g,
                              tooltip="Minimum (first+second) bias-subtracted counts/pixel; below this the chain "
                                      "is considered lost and nothing is changed")
        self.setattr_argument("linear_cutoff", NumberValue(default=0.5, min=0.1, max=1.5, step=0.1, ndecimals=2),
                              group=g, tooltip="End of the linear part of the S-curve in units of its width w. Beyond this "
                                               "offset the error is clamped: correction = w*erfinv(gain*erf(cutoff)) at most")

        g = "Cooling shot"
        self.setattr_argument("frames_per_axis", NumberValue(default=20, step=1, ndecimals=0, min=1), group=g)
        self.setattr_argument("dark_frames", NumberValue(default=5, step=1, ndecimals=0, min=0), group=g,
                              tooltip="Doppler-off frames once at the start (EMCCD bias)")
        self.setattr_argument("exposure", NumberValue(default=1 * ms, unit="ms", min=0.05 * ms, step=0.1 * ms,
                                                      ndecimals=3), group=g)
        self.setattr_argument("frame_period", NumberValue(default=15 * ms, unit="ms", min=9 * ms, step=1 * ms,
                                                          ndecimals=1), group=g)
        self.setattr_argument("grabber_timeout", NumberValue(default=100 * ms, unit="ms", min=1 * ms, step=10 * ms,
                                                             ndecimals=1), group=g)
        self.setattr_argument("endcapX_along", EnumerationValue(["image_horizontal", "image_vertical"],
                                                                default="image_horizontal"), group=g,
                              tooltip="Direction in the camera image in which EndcapX moves the ion. "
                                      "image_horizontal: X pair side by side, Y pair stacked (your EndcapX calibration). "
                                      "image_vertical: the other way round.")
        self.setattr_argument("restore_idle", BooleanValue(default=True), group=g)

        g = "Observable"
        self.setattr_argument("use_threshold", BooleanValue(default=False), group=g,
                              tooltip="False: mean counts/px (error = standard error of the mean). True: probability that "
                                      "counts/px >= the threshold of the N-th ROI on the camera GUI, with beta-distribution "
                                      "(binom_onesided) error bars. Must match the calibration's observable.")
        self.setattr_argument("threshold_per_px", NumberValue(default=0.0, min=0.0, step=1.0, ndecimals=2), group=g,
                              tooltip="0 = use threshold_per_px of the N-th ROI from the camera GUI")

        g = "Plot"
        self.setattr_argument("plot_in_pixels", BooleanValue(default=False), group=g,
                              tooltip="False: the tracker plot's Y axis is in mV of the knob. True: in camera pixels "
                                      "(offset and applied correction divided by volts_per_pixel).")
        self.setattr_argument("volts_per_pixel", NumberValue(default=0.0, min=0.0, step=0.001, ndecimals=5), group=g,
                              tooltip="Conversion factor: volts of the knob (EndcapX or AllY) that move the ion by one camera "
                                      "pixel (V/px). Required for plot_in_pixels; 0 = not set. Also printed in the log if set.")

        g = "Debug"
        self.setattr_argument("debug_static_pair", BooleanValue(default=False), group=g,
                              tooltip="Diagnostic: the N-th and spare ROI are moved to the X calibration pair ONCE at the start "
                                      "and the Grabber gate stays open; no ROI/gate changes between cycles. Use it to test whether "
                                      "the ROI motion causes an offset. X only (track_y must be off).")

    # ------------------------------------------------------------------------------------------
    def prepare(self):
        for rid, job in self.scheduler.get_status().items():
            if job["expid"]["class_name"] == "Idle369On355Pulsed":
                print(f"[STAB] Found active idler (RID {rid}). Requesting termination...")
                self.scheduler.request_termination(rid)
                while rid in self.scheduler.get_status():
                    time.sleep(0.05)

        def numeric(x):
            if hasattr(x, "get"): return x.get()
            if hasattr(x, "value"): return x.value
            return float(x)

        self.originalDCElectrodeValues = [float(v) for v in self.get_dataset("DC.ElectrodeValues")]
        self.modDCElectrodeValues = [float(v) for v in self.get_dataset("DC.ElectrodeValues")]
        self.DCElectrodeMapping = [int(v) for v in self.get_dataset("DC.ElectrodeMapping")]
        self.originalEndcapX = float(self.get_dataset("Experiment_config.endcapX"))
        self.originalAllY = float(self.get_dataset("Experiment_config.all_y"))
        self.originalAllZ = float(self.get_dataset("Experiment_config.all_z"))
        self.originalEndcapAvg = float(self.get_dataset("Experiment_config.endcap_avg"))
        self.piezo_R1H = float(self.get_dataset("355_RamanB1.H1"))
        self.piezo_R1V = float(self.get_dataset("355_RamanB1.V1"))
        self.piezo_R2V = float(self.get_dataset("355_Raman2.V2"))

        self.doppler_freq = numeric(self.get_dataset("Doppler.Frequency"))
        self.doppler_amp = numeric(self.get_dataset("Experiment_config.DopplerAmp"))
        self.ULE_369_Amp = numeric(self.get_dataset("369_ULE.Amp"))
        self.ULE_369_Frequency_exp = numeric(self.get_dataset("Experiment_config.ULE369_freq"))
        self.ULE_369_Att = numeric(self.get_dataset("369_ULE.Attenuation"))
        self.ULE_ramp_rate = numeric(self.get_dataset("369_ULE.ramp_rate"))
        self.ULE_time_step = numeric(self.get_dataset("369_ULE.time_step"))
        self.default_Raman_time = self.get_dataset("355_RamanB1.Time(ms)") * ms
        self.default_SBCTime = self.get_dataset("SBC.tone1.Time(ms)") * ms

        # flags / ints for the kernel
        self.tx, self.ty = bool(self.track_x), bool(self.track_y)
        if not (self.tx or self.ty):
            raise ValueError("Nothing to track: enable track_x and/or track_y")
        self.do_correct = (str(self.mode) == "correct_and_track")
        self.fx = int(self.frames_per_axis) if self.tx else 0
        self.fy = int(self.frames_per_axis) if self.ty else 0
        self.n_dark = int(self.dark_frames)
        self.n_cyc = int(self.n_cycles)
        self.settle = float(self.settle_time)
        self.hold = float(self.hold_time)
        self.dark_axis = 0 if self.tx else 1
        self.static = bool(self.debug_static_pair)
        if self.static and (self.ty or not self.tx):
            raise ValueError("debug_static_pair works with track_x only: enable track_x and disable track_y")
        self.use_protection = False
        self.frame_counter = 0
        self.n_pushed = 0
        self.n_expected_pushes = self.n_cyc * (int(self.tx) + int(self.ty))
        self._camera_closed = False
        self.buf = [0] * (2 * max(self.fx, self.fy, self.n_dark, 1))
        self.gbuf = [0, 0]
        self.iL, self.iR = 0, 1
        self.dark_pp = 0.0

        # controller limits in volts
        self.c_gain = float(self.loop_gain)
        self.c_dead = float(self.deadband_mV) * 1e-3
        self.c_step = float(self.max_step_mV) * 1e-3
        self.c_dev = float(self.max_excursion_mV) * 1e-3
        self.c_min = 0.05 if self.use_threshold else float(self.min_signal)    # threshold mode: S = p1 + p2
        self.thr = 0.0
        self.v_per_px = float(self.volts_per_pixel)
        self.px_plot = bool(self.plot_in_pixels)
        if self.px_plot and self.v_per_px <= 0:
            raise ValueError("plot_in_pixels needs volts_per_pixel > 0 (V of the knob per camera pixel)")
        self.c_sat = float(self.linear_cutoff)

        # calibrations
        self.cal = {}
        for ax, cn in (("X", "EndcapX"), ("Y", "AllY")):
            if (ax == "X" and not self.tx) or (ax == "Y" and not self.ty):
                continue
            try:
                self.cal[ax] = tuple(float(self.get_dataset(f"Calibrations.{cn}_{k}"))
                                     for k in ("sigmoid_A", "sigmoid_B", "sigmoid_w", "V0"))
            except KeyError as e:
                raise RuntimeError(f"Calibration for {cn} not found ({e}). Run EndcapX_calibration_grabber.py with "
                                   f"scan_axis = {ax} first (S-curve fit needs scipy).")
            A, Bc, w, V0 = self.cal[ax]
            print(f"[STAB] {cn} calibration (shape only): A = {A:+.3f}, B = {Bc:+.3f}, w = {w * 1e3:.2f} mV "
                  f"(its V0 = {V0:.5f} V is NOT used; the zero point is where you placed the N-th ROI)")
        # reference values from the calibration data, for the diagnostic print: S at the voltage nearest to the start
        self.S_cal = {"X": float('nan'), "Y": float('nan')}
        for ax, cn in (("X", "EndcapX"), ("Y", "AllY")):
            if ax not in self.cal:
                continue
            try:
                Vc = np.array(self.get_dataset(f"Calibrations.{cn}_V"), dtype=float)
                Sc = np.array(self.get_dataset(f"Calibrations.{cn}_L"), dtype=float) + \
                    np.array(self.get_dataset(f"Calibrations.{cn}_R"), dtype=float)
                self.S_cal[ax] = float(Sc[int(np.argmin(np.abs(Vc - self.cal[ax][3])))])     # sum at the calibration centre
                A, Bc, w, V0 = self.cal[ax]
                print(f"[STAB] {cn}: undisturbed (ion on the boundary) the calibration gives dP = {Bc:+.3f}, "
                      f"sum (L+R) = {self.S_cal[ax]:.1f} counts/px (plateau median {np.median(Sc):.1f})")
            except Exception as e:
                print(f"[STAB] no reference data for {cn}: {e!r}")
            # conditions the calibration was taken under (saved by the newer calibration script)
            try:
                age_h = (time.time() - float(self.get_dataset(f"Calibrations.{cn}_time"))) / 3600.0
                exp_c = float(self.get_dataset(f"Calibrations.{cn}_exposure_ms"))
                print(f"[STAB] {cn} calibration is {age_h:.1f} h old, exposure {exp_c:.3f} ms "
                      f"(now {float(self.exposure) / ms:.3f} ms), frame period "
                      f"{float(self.get_dataset(f'Calibrations.{cn}_frame_period_ms')):.1f} ms")
                if abs(exp_c - float(self.exposure) / ms) > 0.01 * exp_c:
                    print(f"[STAB WARNING] exposure differs from the {cn} calibration: sums and dP are not comparable")
                if age_h > 4:
                    print(f"[STAB WARNING] the {cn} calibration is more than 4 h old: the chain may have moved; "
                          f"recalibrate if the first cycles are far from the expected values")
            except Exception:
                print(f"[STAB] {cn}: no calibration conditions saved (re-run the newer calibration script to get them)")
        self.h_v = [self.originalEndcapX, self.originalAllY]     # voltages applied now (host copy)
        self.v_ref = [self.originalEndcapX, self.originalAllY]
        self.t0 = None
        self.log = {"X": {"n": 0}, "Y": {"n": 0}}
        self.rec = {"X": [], "Y": []}

        self.cameraHOST = '127.0.0.6'
        self.cameraPORT = 65438
        per_cycle = self.fx + self.fy
        self.expected_frames = self.n_dark + self.n_cyc * per_cycle
        self.send_datapacket = {
            'x': {'name': 'cycle', 'value': list(range(self.n_cyc))},
            'rid': getattr(self.scheduler, "rid", -1),
            'repetitions': per_cycle,
            'Experiment exposure time': {"value": float(self.exposure) / ms, "unit": "ms"},
            'mode': 'grabber',
            'extra_frames': self.n_dark,
        }
        self.cameraCOMM_prescan()

    # ------------------------------------------------------------------------------------------
    # camera communication
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
                raise RuntimeError(f"Need N ion ROIs + 1 spare ROI (at least 2) on the camera GUI, got {len(rois)}")
            if len(rois) > 16:
                raise RuntimeError(f"{len(rois)} ROIs defined, gateware supports 16")
            ox0, oy0, ox1, oy1 = [], [], [], []
            for k, r in enumerate(rois):
                x0, y0, x1, y1 = (int(r[key]) for key in ("x0", "y0", "x1", "y1"))
                if not (0 <= x0 < x1 and 0 <= y0 < y1):
                    raise RuntimeError(f"ROI {k} degenerate/negative: {(x0, y0, x1, y1)}")
                if frame and not (x1 <= frame["w"] and y1 <= frame["h"]):
                    raise RuntimeError(f"ROI {k} {(x0, y0, x1, y1)} outside frame {frame}")
                ox0.append(x0); oy0.append(y0); ox1.append(x1); oy1.append(y1)
            self.roi_x0, self.roi_y0, self.roi_x1, self.roi_y1 = ox0, oy0, ox1, oy1
            self.n_roi = len(rois)
            a, b = self.n_roi - 2, self.n_roi - 1
            self.slot_a, self.slot_b = a, b
            self.oa = [ox0[a], oy0[a], ox1[a], oy1[a]]
            self.ob = [ox0[b], oy0[b], ox1[b], oy1[b]]
            # Sensing ROIs are built from the N-th ROI EXACTLY WHERE IT IS ON THE GUI NOW (place it on the ion before the
            # run). The calibration only supplies the shape of the S-curve (A, B, w), never a position.
            #   side-by-side pair: N-th ROI shifted LEFT by w//2, spare ROI directly to its right (same rows)
            #   stacked pair:      N-th ROI shifted UP   by h//2, spare ROI directly below it (same columns)
            self.mask_pair = (1 << a) | (1 << b)
            nth = tuple(self.oa)
            horiz = (str(self.endcapX_along) == "image_horizontal")
            # pair_rois("Y") = side by side, pair_rois("X") = stacked (orientation names of the helper)
            fx1, fx2 = pair_rois("Y" if horiz else "X", nth, frame)      # pair that senses EndcapX
            fy1, fy2 = pair_rois("X" if horiz else "Y", nth, frame)      # pair that senses AllY
            self.gx1, self.gx2, self.gy1, self.gy2 = list(fx1), list(fx2), list(fy1), list(fy2)
            npx = lambda r: float((r[2] - r[0]) * (r[3] - r[1]))
            self.pair_npix = {0: np.array([npx(fx1), npx(fx2)]), 1: np.array([npx(fy1), npx(fy2)])}
            print(f"[STAB] {self.n_roi} ROIs on the GUI (N = {self.n_roi - 1} ions). N-th ROI (slot {a}) = {nth}, "
                  f"spare (slot {b}) = {self.ob}. For each shot they are moved to:")
            if self.tx:
                print(f"[STAB]   X (EndcapX), {'left / right' if horiz else 'upper / lower'}: first = {fx1}, second = {fx2}")
            if self.ty:
                print(f"[STAB]   Y (AllY), {'upper / lower' if horiz else 'left / right'}: first = {fy1}, second = {fy2}")
            # the S-curve was measured with ROIs of some size; a different size changes its width w
            for ax, cn in (("X", "EndcapX"), ("Y", "AllY")):
                if ax not in self.cal:
                    continue
                try:
                    pr = json.loads(str(self.get_dataset(f"Calibrations.{cn}_roi_pair")))
                    csz = (pr[0][2] - pr[0][0], pr[0][3] - pr[0][1])
                    nsz = (nth[2] - nth[0], nth[3] - nth[1])
                    if tuple(csz) != tuple(nsz):
                        print(f"[STAB WARNING] {cn} calibration used {csz[0]}x{csz[1]} px ROIs but the N-th ROI is "
                              f"{nsz[0]}x{nsz[1]} px: the S-curve width w (and so the offsets in mV) will not match")
                except Exception:
                    pass
            self.thr = float(rois[a].get("threshold_per_px", 0.0) or 0.0)
            if float(self.threshold_per_px) > 0:
                self.thr = float(self.threshold_per_px)
            if self.use_threshold:
                if self.thr <= 0:
                    raise RuntimeError("use_threshold needs threshold_per_px > 0 (not set on the N-th ROI of the camera GUI; "
                                       "set it there or in the threshold_per_px argument)")
                print(f"[STAB] observable = P(counts/px >= {self.thr:.1f}) per ROI, beta-distribution error bars")
            for ax, cn in (("X", "EndcapX"), ("Y", "AllY")):
                if ax not in self.cal:
                    continue
                try:
                    obs = str(self.get_dataset(f"Calibrations.{cn}_observable"))
                except Exception:
                    obs = "mean"
                if obs != ("threshold" if self.use_threshold else "mean"):
                    raise RuntimeError(f"{cn} calibration used observable '{obs}' but use_threshold = {bool(self.use_threshold)}: "
                                       f"the S-curve is not valid; recalibrate or change use_threshold")
                if self.use_threshold:
                    try:
                        tc = json.loads(str(self.get_dataset(f"Calibrations.{cn}_threshold_per_px")))
                        if abs(np.mean(tc) - self.thr) > 0.01 * max(self.thr, 1e-9):
                            print(f"[STAB WARNING] {cn} calibration threshold was {np.mean(tc):.1f} counts/px, now {self.thr:.1f}")
                    except Exception:
                        pass
            self.set_dataset("Camera.rois", json.dumps(reply), persist=True, archive=True)
        except Exception:
            # the camera has already been armed by "start": release it, otherwise it freezes waiting for triggers
            self._recover_camera()
            raise

    def _recover_camera(self):
        print("[STAB] setup failed after the camera was armed: recovery pulse + abort, restoring the machine")
        self._release_camera()
        if self.restore_idle:
            self.scheduler.submit("main", {
                "file": "RFandDC/DCelectrodes.py", "class_name": "DC_Control", "arguments": {},
                "log_level": self.scheduler.expid["log_level"], "repo_rev": self.scheduler.expid["repo_rev"]})
            self.scheduler.submit("main", {
                "file": "Experiments/idle_369_on_355_pulsed.py", "class_name": "Idle369On355Pulsed",
                "arguments": {"timeRaman": self.default_Raman_time, "timeSBC": self.default_SBCTime},
                "log_level": 0, "repo_rev": self.scheduler.expid["repo_rev"]})

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

        # Grabber ROIs at their camera-GUI positions; gate closed until a measurement starts
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        for k in range(self.n_roi):
            self.grabber0.setup_roi(k, self.roi_x0[k], self.roi_y0[k], self.roi_x1[k], self.roi_y1[k])
        self.core.break_realtime()
        if self.static:
            # debug: sensing pair set once, gate stays open, nothing moves later
            self.grabber0.setup_roi(self.slot_a, self.gx1[0], self.gx1[1], self.gx1[2], self.gx1[3])
            self.grabber0.setup_roi(self.slot_b, self.gx2[0], self.gx2[1], self.gx2[2], self.gx2[3])
            self.grabber0.gate_roi(self.mask_pair)
            self.core.break_realtime()

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
    def measure_pair(self, g1, g2, n_frames, bright):
        """Move the N-th ROI (slot a) to g1 and the spare ROI (slot b) to g2, read n_frames, close the gate."""
        self.core.break_realtime()
        if not self.static:
            self.grabber0.gate_roi(0)
            self.grabber0.setup_roi(self.slot_a, g1[0], g1[1], g1[2], g1[3])
            self.grabber0.setup_roi(self.slot_b, g2[0], g2[1], g2[2], g2[3])
            self.grabber0.gate_roi(self.mask_pair)
        self.take_frames(n_frames, bright)
        if not self.static:
            self.core.break_realtime()
            self.grabber0.gate_roi(0)

    @kernel
    def restore_rois(self):
        """Both ROIs back to where the camera GUI has them (experiment position)."""
        if not self.static:
            self.core.break_realtime()
            self.grabber0.gate_roi(0)
            self.grabber0.setup_roi(self.slot_a, self.oa[0], self.oa[1], self.oa[2], self.oa[3])
            self.grabber0.setup_roi(self.slot_b, self.ob[0], self.ob[1], self.ob[2], self.ob[3])

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
        vx = self.originalEndcapX
        vy = self.originalAllY
        try:
            self.core.reset()
            self.setup_hardware()
            self.core.break_realtime()
            self.set_dc(vx, vy)

            if self.n_dark > 0:
                if self.dark_axis == 0:
                    self.measure_pair(self.gx1, self.gx2, self.n_dark, False)
                else:
                    self.measure_pair(self.gy1, self.gy2, self.n_dark, False)
                self.host_push_dark(self.buf, self.n_dark)
                self.restore_rois()
                self.core.break_realtime()
                self.urukul0_ch1.sw.on()

            for c in range(self.n_cyc):
                self.core.break_realtime()
                if self.should_stop():
                    print("[TERMINATION] Exiting krun cleanly between cycles.")
                    return
                self.core.break_realtime()
                self.urukul0_ch1.sw.on()
                self.uninterrupted_processes()
                delay(self.hold)                          # the "experiment"
                self.core.wait_until_mu(now_mu())         # make it a real-time wait

                if self.tx:
                    self.measure_pair(self.gx1, self.gx2, self.fx, True)
                    newv = self.host_axis(0, c, self.buf, self.fx)
                    self.core.break_realtime()
                    if self.do_correct:
                        d = newv - vx
                        if d > 1e-7 or d < -1e-7:
                            vx = newv
                            self.set_dc(vx, vy)
                            delay(self.settle)
                if self.ty:
                    self.measure_pair(self.gy1, self.gy2, self.fy, True)
                    newv = self.host_axis(1, c, self.buf, self.fy)
                    self.core.break_realtime()
                    if self.do_correct:
                        d = newv - vy
                        if d > 1e-7 or d < -1e-7:
                            vy = newv
                            self.set_dc(vx, vy)
                            delay(self.settle)
                self.restore_rois()
        finally:
            self.core.break_realtime()
            self.grabber0.gate_roi(0)
            self.restore_rois()
            self.set_dc(self.originalEndcapX, self.originalAllY)
            self.urukul0_ch1.sw.on()

    # ------------------------------------------------------------------------------------------
    # host side
    # ------------------------------------------------------------------------------------------
    @rpc(flags={"async"})
    def host_push_dark(self, buf, n):
        a = np.array(buf, dtype=float).reshape(-1, 2)[: int(n)]
        self.dark_pp = float((a / self.pair_npix[self.dark_axis]).mean())
        print(f"[STAB] dark level: {self.dark_pp:.1f} counts/px (raw sums {a.mean(axis=0)})")
        try:
            cn = "EndcapX" if self.dark_axis == 0 else "AllY"
            d_cal = float(self.get_dataset(f"Calibrations.{cn}_dark_pp"))
            print(f"[STAB] calibration dark level was {d_cal:.1f} counts/px (difference {self.dark_pp - d_cal:+.1f})")
            if abs(self.dark_pp - d_cal) > 5:
                print("[STAB WARNING] bias/dark level differs from the calibration: camera temperature, EM gain or "
                      "ambient light changed")
        except Exception:
            pass
        self.set_dataset("Stabilizer.dark_pp", self.dark_pp, broadcast=True, archive=True)

    @rpc
    def host_axis(self, axis, c, buf, n) -> TFloat:
        """One measurement of one axis. Returns the voltage the knob should have now."""
        ax = "X" if int(axis) == 0 else "Y"
        k = int(axis)
        if self.t0 is None:
            self.t0 = time.time()
        t = time.time() - self.t0
        raw = np.array(buf, dtype=float).reshape(-1, 2)[: int(n)]
        Lm, Rm, S, dP, err = pair_stats(raw, self.pair_npix[k], self.dark_pp, bool(self.use_threshold), self.thr)
        v_cur = self.h_v[k]
        resid, sat, lost, dv_raw, v_new = axis_correction(
            dP, S, self.cal[ax], v_cur, self.v_ref[k], self.c_gain, self.c_dead, self.c_step, self.c_dev,
            self.c_min, self.c_sat)
        drift = resid - (v_cur - self.v_ref[k]) if not lost else float('nan')
        # error of the offset: dP error divided by the local slope of the S-curve (large on the flat parts)
        A_c, B_c, w_c, _ = self.cal[ax]
        if lost or not np.isfinite(err):
            resid_err = float('nan')
        else:
            slope_loc = 2.0 * abs(A_c) / (math.sqrt(math.pi) * w_c) * math.exp(-(resid / w_c) ** 2)   # per volt
            resid_err = err / slope_loc if slope_loc > 0 else float('nan')
        flag = 2 if lost else (1 if sat else 0)
        if not self.do_correct:
            v_new = v_cur
        self.h_v[k] = v_new

        self.n_pushed += 1
        vals = {"t": t, "dP": dP, "dP_err": err, "S": S, "resid_mV": resid * 1e3, "resid_err_mV": resid_err * 1e3, "V_mV": (v_cur - self.v_ref[k]) * 1e3,
                "drift_mV": drift * 1e3, "flag": float(flag)}
        if self.v_per_px > 0:      # same quantities in camera pixels (V / (V/px))
            vals.update({"resid_px": resid / self.v_per_px, "resid_err_px": resid_err / self.v_per_px,
                         "V_px": (v_cur - self.v_ref[k]) / self.v_per_px, "drift_px": drift / self.v_per_px})
        self.rec[ax].append(vals)
        first = (self.log[ax]["n"] == 0)
        self.log[ax]["n"] += 1
        for key, v in vals.items():
            name = f"Stabilizer.{ax}_{key}"
            if first:
                self.set_dataset(name, [v], broadcast=True, archive=True)
            else:
                self.append_to_dataset(name, v)
        if first:
            rid = getattr(self.scheduler, "rid", "Local")
            cn = "EndcapX" if ax == "X" else "AllY"
            both = bool(self.tx) and bool(self.ty)
            u = "px" if self.px_plot else "mV"
            ylab = (f"{ax} offset [camera px] (1 px = {self.v_per_px * 1e3:.3g} mV of {cn})" if self.px_plot
                    else f"{ax} [mV of {cn}]")
            name = f"{ax} stabilizer" if both else "Stabilizer"        # one tracked axis at a time -> a single applet
            what = ("WITH correction: points = ion offset from the boundary after correction, "
                    "red line = correction applied" if self.do_correct else
                    "NO correction (track only): points = ion offset from the boundary, red line = correction applied (0)")
            self.ccb.issue("create_applet", name,
                           f"${{artiq_applet}}plot_xy Stabilizer.{ax}_resid_{u} --x Stabilizer.{ax}_t "
                           f"--error Stabilizer.{ax}_resid_err_{u} "
                           f"--fit Stabilizer.{ax}_V_{u} --x-label 'time [s]' "
                           f"--y-label '{ylab}' "
                           f"--title 'RID {rid} {ax} ({cn}) {what}'")
        px_txt = (f" ({resid / self.v_per_px:+.2f} +- {resid_err / self.v_per_px:.2f} px)" if self.v_per_px > 0 else "")
        tag = {0: "", 1: "  [CLAMPED: beyond the linear cutoff, bounded step]", 2: "  [LOST: no signal, unchanged]"}[flag]
        A_, B_, w_, V0_ = self.cal[ax]
        exp_dP = B_ + A_ * math.erf((v_cur - self.v_ref[k]) / w_)    # ion boundary = N-th ROI placement at the start voltage
        print(f"[STAB] cycle {int(c) + 1}/{self.n_cyc} {ax}: sum = {S:.3g} {'(prob.)' if self.use_threshold else 'c/px'} (cal {self.S_cal[ax]:.3g}), "
              f"dP = {dP:+.3f} +- {err:.3f} (expected {exp_dP:+.3f} if the chain has not moved), "
              f"offset = {resid * 1e3:+.2f} +- {resid_err * 1e3:.2f} mV{px_txt}, applied = {(v_cur - self.v_ref[k]) * 1e3:+.2f} mV"
              f" -> {(v_new - self.v_ref[k]) * 1e3:+.2f} mV{tag}")
        return float(v_new)

    def analyze(self):
        self.cameraCOMM_postscan()          # first: close the camera side whatever happens below
        summary = {"mode": str(self.mode), "n_cycles": int(self.n_cyc)}
        for ax in ("X", "Y"):
            r = self.rec[ax]
            if not r:
                continue
            ok = [q for q in r if q["flag"] != 2]
            off = np.array([q["resid_mV"] for q in ok])
            dr = np.array([q["drift_mV"] for q in ok])
            t = np.array([q["t"] for q in ok])
            s = {"n": len(r), "lost": int(sum(q["flag"] == 2 for q in r)), "saturated": int(sum(q["flag"] == 1 for q in r))}
            if len(ok) > 1:
                s.update({"offset_rms_mV": float(np.sqrt(np.mean(off ** 2))), "offset_mean_mV": float(off.mean()),
                          "offset_std_mV": float(off.std(ddof=1)),
                          "drift_mean_mV": float(dr.mean()), "drift_std_mV": float(dr.std(ddof=1)),
                          "drift_trend_mV_per_min": float(np.polyfit(t, dr, 1)[0] * 60.0) if np.ptp(t) > 0 else 0.0})
            summary[ax] = s
        self.set_dataset("Stabilizer.summary", json.dumps(summary, default=lambda o: o.item() if hasattr(o, "item") else str(o)), persist=True, archive=True)
        self.set_dataset("Stabilizer.mode", str(self.mode), archive=True)
        print("\n" + "=" * 64)
        print(f"[STAB] summary, mode = {self.mode}")
        for ax in ("X", "Y"):
            if ax in summary:
                print(f"[STAB]   {ax}: " + ", ".join(f"{k} = {v:.2f}" if isinstance(v, float) else f"{k} = {v}"
                                                      for k, v in summary[ax].items()))
        print("[STAB]   offset_rms = how far the chain sat from the centre when measured (smaller = better centred)")
        print("=" * 64 + "\n")

        if self.restore_idle:
            self.scheduler.submit("main", {
                "file": "RFandDC/DCelectrodes.py", "class_name": "DC_Control", "arguments": {},
                "log_level": self.scheduler.expid["log_level"], "repo_rev": self.scheduler.expid["repo_rev"]})
            self.scheduler.submit("main", {
                "file": "Experiments/idle_369_on_355_pulsed.py", "class_name": "Idle369On355Pulsed",
                "arguments": {"timeRaman": self.default_Raman_time, "timeSBC": self.default_SBCTime},
                "log_level": 0, "repo_rev": self.scheduler.expid["repo_rev"]})

    def cameraCOMM_postscan(self):
        if self._camera_closed:
            # run() already aborted the acquisition (early stop / error): a "fetch" on an aborted acquisition
            # can block the camera, so do not send it
            print("[camera] acquisition was aborted earlier, not fetching")
            return
        completed = bool(self.n_pushed >= self.n_expected_pushes)
        try:
            reply = self._camera_request({"cmd": "fetch", "completed": completed}, timeout=180)
            self._camera_closed = True
        except Exception as e:
            print(f"!!! camera fetch failed: {e}")
            return
        frames = reply.get("frames")
        print(f"[STAB] camera acquired {frames} frames, expected {self.expected_frames}")
        if completed and frames is not None and frames != self.expected_frames:
            print("[STAB WARNING] frame count mismatch (missed triggers, or the cooling-shot combo box is not 'None')")

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
            print("[STAB] camera did not answer the abort: sending trigger pulses (round %d)" % rounds)
            try:
                self.camera_pulses(20)
            except Exception as e:
                print("[STAB] camera_pulses failed:", repr(e))
                break
            th.join(0.6)
        if th.is_alive():
            print("[STAB] WARNING: camera still not released; toggle the trigger line by hand / restart the camera GUI")
        elif res.get("err"):
            print("[camera] abort failed:", res["err"])
        else:
            print("[STAB] camera released" + (" after %d pulse round(s)" % rounds if rounds else ""))
        self._camera_closed = True


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

            print("[STAB] starting kernel...")
            self.krun()
        finally:
            if not self._camera_closed and self.n_pushed < self.n_expected_pushes:
                print("[STAB] scan incomplete: sending recovery pulse to the camera trigger line, then abort")
                self._release_camera()