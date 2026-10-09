"""
Ion-chain position tracker (double differential, standalone, no experiment): track the drift of a chain of N ions with
"cooling shots" using its two EDGE ions, and optionally correct the average position with EndcapX (axial, X) or AllY (radial, Y).

Camera GUI: ONE ROI per ion, centred on the ion (N ions -> N ROIs; N = 1 uses one pair and one plot). Nothing else is drawn.
`first_ion_roi` / `last_ion_roi` (default 0 and -1) select the two edge ions. The partner ROIs are created here, in extra Grabber
slots (n_roi, n_roi + 1), and never appear on the GUI. Every cycle (hold_time of Doppler cooling stands in for the experiment):

  * the ion's ROI is shifted by half its size (slot of the ion = 'first') and a ROI of the same size is put directly next to it
    ('second', extra slot), so that their common boundary runs through the ion; same for the last ion;
  * frames_per_axis frames are taken (both pairs in the same frames), Delta P_i = (first_i - second_i)/(sum_i);
  * each edge ion's offset from its boundary is obtained by inverting its calibration S-curve (Delta P = B + A erf((V-V0)/w), shape
    only); the average position of the chain = mean of the two offsets;
  * correct_and_track: the knob is moved to bring the AVERAGE offset to zero (gain inside the inverse model, clamped at the
    linear cutoff, deadband, step and excursion limits); track_only: nothing is changed (free drift);
  * the ion ROIs return to their GUI positions.
Three applets: 1st ion, last ion, average (one for a single ion). mode = response_test steps the knob in a fixed pattern and prints the measured/applied slope (expected +1) to check sign and size of the calibration in situ; with `guard` the correction switches itself off if it does not act as calibrated. Points = offset of the ion(s) from the boundary after correction (error bars from the
statistics of the frames), red line = correction applied to the knob. Y axis in camera pixels if plot_in_pixels (needs volts_per_pixel),
else in mV of the knob. The datasets are Stabilizer.Two_ions.<X|Y>_<first|last|avg>_<t, dP, dP_err, S, resid_mV, resid_err_mV, V_mV, flag [, *_px]>.

Needs the calibration from grabber_chain_calibration.py (Calibrations.Two_ions.<EndcapX|AllY>_<first|last>_sigmoid_A/B/w).
Camera requirements: the GUI's cooling-shot combo box = "None"; Camera.py with `extra_frames`.
DC updates are copied step for step from BarebonesArtiqScan2DGrabberV2.ON() (no ramp): keep steps small.
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


def orientation_sign(pair_cal, kind):
    """Compare the arrangement of the CALIBRATION's (first, second) ROIs with this run's pair.
    pair_cal = [first_box, second_box] saved by the calibration; kind 'Y' = side by side with first LEFT, 'X' = stacked with
    first UPPER (what pair_rois builds). Returns (sign, text): +1 if first/second are arranged the same way, -1 if the
    calibration's first ROI was the right / lower one (then dP of this run must be multiplied by -1 before the S-curve is used,
    otherwise the correction has the wrong sign and runs away). Raises if the calibration pair lies along the other image axis."""
    f, s = pair_cal
    dx = 0.5 * (s[0] + s[2]) - 0.5 * (f[0] + f[2])
    dy = 0.5 * (s[1] + s[3]) - 0.5 * (f[1] + f[3])
    horiz_cal = abs(dx) >= abs(dy)
    if horiz_cal != (kind == "Y"):
        raise RuntimeError(f"The calibration pair lies {'side by side' if horiz_cal else 'stacked'} (first {f}, second {s}) but this "
                           f"run's pair is {'side by side' if kind == 'Y' else 'stacked'}: the calibration measured motion along the "
                           f"other image axis. Change endcapX_along (or recalibrate with the ROIs arranged like this run).")
    d = dx if horiz_cal else dy
    if d > 0:
        return 1.0, f"calibration first ROI is the {'left' if horiz_cal else 'upper'} one, like this run: dP sign unchanged"
    return -1.0, (f"calibration first ROI was the {'right' if horiz_cal else 'lower'} one, opposite to this run "
                  f"(first = {'left' if horiz_cal else 'upper'}): dP sign FLIPPED to match the calibration")


RESID_CLIP = 0.9      # |u| above this: the offset ESTIMATE (for display) is clipped at w*erfinv(0.9) ~ 1.16 w


def chain_correction(dPs, Ss, cals, v_cur, v_ref, gain, deadband_v, max_step, max_dev, min_sum, cutoff):
    """One correction step for the AVERAGE position of the chain from its two edge ions.
    dPs, Ss: Delta P and signal sum of each edge ion; cals: (A, B, w, V0) of each ion's S-curve.
    Per ion, u = (dP - B)/A:
      resid_i = w erfinv(clip(|u|, RESID_CLIP))            estimated offset of this ion (display value)
      off_i   = w erfinv(clip(u, +-erf(cutoff)))            offset with the error clamped at the linear cutoff
      corr_i  = w erfinv(gain * clip(u, +-erf(cutoff)))     gain INSIDE the inverse model
    average position = mean(resid_i); no change if |mean(off_i)| < deadband; else dv = -mean(corr_i); then max_step and max_dev.
    If either ion has no usable signal (dP not finite or S < min_sum) nothing is changed (lost).
    Returns dict(resid=[..], resid_avg, sat=[..], lost, v_new)."""
    n = len(dPs)
    for d, s in zip(dPs, Ss):
        if (not math.isfinite(d)) or (not math.isfinite(s)) or s < min_sum:
            return {"resid": [float('nan')] * n, "resid_avg": float('nan'), "sat": [False] * n, "lost": True, "v_new": v_cur}
    u_c = math.erf(cutoff)
    resid, sats, offs, corr = [], [], [], []
    for d, (A, Bc, w, V0) in zip(dPs, cals):
        u = (d - Bc) / A
        resid.append(w * erfinv_safe(math.copysign(min(abs(u), RESID_CLIP), u)))
        sat = abs(u) > u_c
        sats.append(sat)
        ucl = math.copysign(u_c, u) if sat else u
        offs.append(w * erfinv_safe(ucl))
        corr.append(w * erfinv_safe(gain * ucl))
    off_avg = sum(offs) / n
    dv = 0.0 if abs(off_avg) < deadband_v else -sum(corr) / n
    dv = max(-max_step, min(max_step, dv))
    v_new = max(v_ref - max_dev, min(v_ref + max_dev, v_cur + dv))
    return {"resid": resid, "resid_avg": sum(resid) / n, "sat": sats, "lost": False, "v_new": v_new}


class GrabberChainStabilizer(EnvExperiment):
    """Grabber chain tracker"""

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

        g = "Chain tracker"
        self.setattr_argument("mode", EnumerationValue(["correct_and_track", "track_only", "response_test"],
                                                       default="track_only"), group=g,
                              tooltip="track_only: measure only, DC never changed after the start (free drift). "
                                      "correct_and_track: apply the corrections (average position -> 0). "
                                      "response_test: step the knob by +-test_step_mV in a fixed pattern (no controller) and compare the "
                                      "measured offset change with the applied one (expected slope +1): checks sign and size of the calibration in situ.")
        self.setattr_argument("track_axis", EnumerationValue(["X (EndcapX)", "Y (AllY)"], default="X (EndcapX)"), group=g,
                              tooltip="Which axis is tracked / corrected (one at a time)")
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
        self.setattr_argument("test_step_mV", NumberValue(default=4.0, min=0.5, step=0.5, ndecimals=1), group=g,
                              tooltip="response_test only: the knob is stepped through 0, +step, 0, -step, ... (mV); must not exceed max_step_mV")
        self.setattr_argument("guard", BooleanValue(default=True), group=g,
                              tooltip="correct_and_track: if 3 corrections of >= 2 mV in a row change the measured offset by less than 25% of "
                                      "what was applied (or the wrong way), the correction is switched off and the knob returns to its starting "
                                      "value in max_step steps")
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

        g = "Chain"
        self.setattr_argument("first_ion_roi", NumberValue(default=0, step=1, ndecimals=0), group=g,
                              tooltip="Index of the camera-GUI ROI centred on the first ion of the chain (0 = first ROI)")
        self.setattr_argument("last_ion_roi", NumberValue(default=-1, step=1, ndecimals=0), group=g,
                              tooltip="Index of the camera-GUI ROI centred on the last ion (negative = counted from the end). "
                                      "Same as first_ion_roi (or only one ROI on the GUI): a single ion is tracked")

        g = "Plot"
        self.setattr_argument("plot_in_pixels", BooleanValue(default=True), group=g,
                              tooltip="True: the Y axis of the plots is in camera pixels (offset and applied correction divided by "
                                      "volts_per_pixel; falls back to mV with a warning if volts_per_pixel is 0). False: mV of the knob.")
        self.setattr_argument("volts_per_pixel", NumberValue(default=0.0, min=0.0, step=0.001, ndecimals=5), group=g,
                              tooltip="Conversion factor: volts of the knob (EndcapX or AllY) that move the ions by one camera pixel (V/px). 0 = not set.")

    def prepare(self):
        for rid, job in self.scheduler.get_status().items():
            if job["expid"]["class_name"] == "Idle369On355Pulsed":
                print(f"[CHAIN] Found active idler (RID {rid}). Requesting termination...")
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
        self.ax_name = "X" if str(self.track_axis).startswith("X") else "Y"
        self.ak = 0 if self.ax_name == "X" else 1
        self.cn = "EndcapX" if self.ak == 0 else "AllY"
        self.nI = 0          # number of ions: set from the number of ROIs on the camera GUI (= n_roi) in the prescan
        self.mode_s = str(self.mode)
        self.do_correct = (self.mode_s in ("correct_and_track", "response_test"))     # the kernel applies the returned voltage
        self.test_step = float(self.test_step_mV) * 1e-3
        if self.mode_s == "response_test" and (float(self.test_step_mV) > float(self.max_step_mV) or float(self.test_step_mV) > float(self.max_excursion_mV)):
            raise ValueError("test_step_mV must not exceed max_step_mV and max_excursion_mV")
        pat = [0.0, 1.0, 0.0, -1.0]
        self.test_pat = [pat[i % 4] * self.test_step for i in range(int(self.n_cycles) + 2)]   # knob offset (V) during measurement i
        self.guard_on = bool(self.guard)
        self.guard_bad = 0
        self.guard_tripped = False
        self.prev_move = None          # (offset measured, correction commanded) of the previous cycle
        self.nf = int(self.frames_per_axis)
        self.n_dark = int(self.dark_frames)
        self.n_cyc = int(self.n_cycles)
        self.settle = float(self.settle_time)
        self.hold = float(self.hold_time)
        self.use_protection = False
        self.frame_counter = 0
        self.n_pushed = 0
        self.n_expected_pushes = self.n_cyc
        self._camera_closed = False
        self.buf = [0] * (4 * max(self.nf, self.n_dark, 1))
        self.gbuf = [0, 0, 0, 0]
        self.w0, self.w1, self.w2, self.w3 = 1, 0, 2, 3      # word index of first_1, second_1, first_N, second_N (ascending slot order 0, 1, N, N+1)
        self.dark_pp = 0.0
        self.TAGS = ("first", "last", "avg")      # reduced to ("first",) for a single ion
        self.two_pairs = True
        self.pre = f"Stabilizer.Two_ions.{self.ax_name}_"

        # controller limits in volts
        self.c_gain = float(self.loop_gain)
        self.c_dead = float(self.deadband_mV) * 1e-3
        self.c_step = float(self.max_step_mV) * 1e-3
        self.c_dev = float(self.max_excursion_mV) * 1e-3
        self.c_min = float(self.min_signal)
        self.c_sat = float(self.linear_cutoff)

        # plot units
        self.v_per_px = float(self.volts_per_pixel)
        self.px_plot = bool(self.plot_in_pixels)
        if self.px_plot and self.v_per_px <= 0:
            print("[CHAIN WARNING] plot_in_pixels is on but volts_per_pixel = 0: plotting in mV of the knob instead")
            self.px_plot = False
        self.u = "px" if self.px_plot else "mV"

        self.base_cal = f"Calibrations.Two_ions.{self.cn}_"
        self.cal = {}
        self.S_cal = {"first": float('nan'), "last": float('nan')}
        self.h_v = [self.originalEndcapX, self.originalAllY]     # voltages applied now (host copy)
        self.v_ref = [self.originalEndcapX, self.originalAllY]
        self.t0 = None
        self.log_n = 0
        self.rec = {t: [] for t in self.TAGS}

        self.cameraHOST = '127.0.0.6'
        self.cameraPORT = 65438
        self.expected_frames = self.n_dark + self.n_cyc * self.nf
        self.send_datapacket = {
            'x': {'name': 'cycle', 'value': list(range(self.n_cyc))},
            'rid': getattr(self.scheduler, "rid", -1),
            'repetitions': self.nf,
            'Experiment exposure time': {"value": float(self.exposure) / ms, "unit": "ms"},
            'mode': 'grabber',
            'extra_frames': self.n_dark,
        }
        self.cameraCOMM_prescan()

    # ------------------------------------------------------------------------------------------
    # camera communication
    # ------------------------------------------------------------------------------------------

    def load_calibration(self):
        """S-curve shape(s) from the calibration datasets: 'first' (and 'last' for N >= 2 ions)."""
        base = self.base_cal
        tags = ("first", "last") if self.two_pairs else ("first",)
        for t in tags:
            try:
                self.cal[t] = tuple(float(self.get_dataset(f"{base}{t}_{k}")) for k in ("sigmoid_A", "sigmoid_B", "sigmoid_w", "V0"))
            except KeyError as e:
                raise RuntimeError(f"Calibration {base}{t}_* not found ({e}). Run grabber_chain_calibration.py with the "
                                   f"{self.cn} scan first.")
            A, Bc, w, V0 = self.cal[t]
            print(f"[CHAIN] {self.cn} calibration, {t} ion (shape only): A = {A:+.3f}, B = {Bc:+.3f}, w = {w * 1e3:.2f} mV")
        for t in tags:
            try:
                Vc = np.array(self.get_dataset(f"{base}{t}_V"), dtype=float)
                Sc = np.array(self.get_dataset(f"{base}{t}_L"), dtype=float) + np.array(self.get_dataset(f"{base}{t}_R"), dtype=float)
                self.S_cal[t] = float(Sc[int(np.argmin(np.abs(Vc - self.cal[t][3])))])
                print(f"[CHAIN] {t} ion: undisturbed dP = {self.cal[t][1]:+.3f}, sum = {self.S_cal[t]:.1f} counts/px at the calibration centre")
            except Exception as e:
                print(f"[CHAIN] no reference data for the {t} ion: {e!r}")
        try:
            age_h = (time.time() - float(self.get_dataset(f"{base}time"))) / 3600.0
            exp_c = float(self.get_dataset(f"{base}exposure_ms"))
            print(f"[CHAIN] calibration is {age_h:.1f} h old, exposure {exp_c:.3f} ms (now {float(self.exposure) / ms:.3f} ms)")
            if abs(exp_c - float(self.exposure) / ms) > 0.01 * exp_c:
                print("[CHAIN WARNING] exposure differs from the calibration: sums and dP are not comparable")
            if age_h > 4:
                print("[CHAIN WARNING] the calibration is more than 4 h old: recalibrate if the first cycles are far from the expected values")
        except Exception:
            print("[CHAIN] no calibration conditions saved")

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
            nI = self.n_roi      # ONE ROI per ion on the GUI, centred on the ion; the partner ROIs are made here
            def idx(v):
                v = int(v)
                return v + self.n_roi if v < 0 else v
            ia, ib = idx(self.first_ion_roi), idx(self.last_ion_roi)
            if not (0 <= ia < self.n_roi and 0 <= ib < self.n_roi):
                raise RuntimeError(f"Bad ion ROI indices {self.first_ion_roi}, {self.last_ion_roi} for {self.n_roi} ROIs")
            self.nI = nI
            self.two_pairs = (ia != ib)
            if not self.two_pairs:
                self.TAGS = ("first",)
                self.rec = {t: [] for t in self.TAGS}
            if self.n_roi + (2 if self.two_pairs else 1) > 16:
                raise RuntimeError(f"{self.n_roi} ROIs + {2 if self.two_pairs else 1} partner ROIs exceed the 16 Grabber slots")
            self.load_calibration()
            try:
                n_cal = int(self.get_dataset(f"Calibrations.Two_ions.{self.cn}_n_ions"))
                if n_cal != nI:
                    print(f"[CHAIN WARNING] the {self.cn} calibration was taken with {n_cal} ions, now {nI}: the S-curve width of the "
                          f"edge ions depends on the chain length; recalibrate if the offsets look wrong")
            except Exception:
                pass
            # slots: the ion's own ROI slot takes the 'first' ROI of its pair, an extra slot (n_roi, n_roi + 1) the 'second'
            self.sl_a1, self.sl_b1 = ia, self.n_roi
            if self.two_pairs:
                self.sl_a2, self.sl_b2 = ib, self.n_roi + 1
            else:
                self.sl_a2, self.sl_b2 = self.sl_a1, self.sl_b1
            box = lambda k: [ox0[k], oy0[k], ox1[k], oy1[k]]
            self.o_a1, self.o_a2 = box(ia), box(ib)
            self.o_b1 = list(self.o_a1); self.o_b2 = list(self.o_a2)       # extra slots have no GUI position (restore_rois skips them)
            horiz = (str(self.endcapX_along) == "image_horizontal")
            # pair_rois("Y") = side by side, pair_rois("X") = stacked
            if self.ak == 0:
                kind = "Y" if horiz else "X"
            else:
                kind = "X" if horiz else "Y"
            f1, s1 = pair_rois(kind, tuple(self.o_a1), frame)
            if self.two_pairs:
                f2, s2 = pair_rois(kind, tuple(self.o_a2), frame)
            else:
                f2, s2 = f1, s1                                    # single ion: no second pair (columns repeat the first)
            self.g_a1, self.g_b1, self.g_a2, self.g_b2 = list(f1), list(s1), list(f2), list(s2)
            used = [self.sl_a1, self.sl_b1] + ([self.sl_a2, self.sl_b2] if self.two_pairs else [])
            self.mask_pair = sum(1 << k for k in used)
            order = sorted(used)                                   # the Grabber returns the gated ROIs in ascending slot order
            self.gbuf = [0] * len(order)
            self.w0, self.w1 = order.index(self.sl_a1), order.index(self.sl_b1)
            self.w2, self.w3 = order.index(self.sl_a2), order.index(self.sl_b2)
            npx = lambda r: float((r[2] - r[0]) * (r[3] - r[1]))
            self.pair_npix = [np.array([npx(f1), npx(s1)]), np.array([npx(f2), npx(s2)])]
            print(f"[CHAIN] {self.n_roi} ROIs on the GUI (N = {nI} ions, one ROI per ion). Axis {self.ax_name} ({self.cn}), "
                  f"{'left / right' if kind == 'Y' else 'upper / lower'} pairs built in ARTIQ. For each shot:")
            print(f"[CHAIN]   1st ion : ROI {ia} {self.o_a1} -> first {f1} (slot {self.sl_a1}), second {s1} (extra slot {self.sl_b1})")
            if self.two_pairs:
                print(f"[CHAIN]   last ion: ROI {ib} {self.o_a2} -> first {f2} (slot {self.sl_a2}), second {s2} (extra slot {self.sl_b2})")
            else:
                print("[CHAIN]   single ion: one pair only")
            rects = [f1, s1, f2, s2] if self.two_pairs else [f1, s1]
            for a_ in range(len(rects)):
                for b_ in range(a_ + 1, len(rects)):
                    r, q = rects[a_], rects[b_]
                    if min(r[2], q[2]) > max(r[0], q[0]) and min(r[3], q[3]) > max(r[1], q[1]) and {a_, b_} not in ({0, 1}, {2, 3}):
                        print(f"[CHAIN WARNING] sensing ROIs {r} and {q} of different ions overlap")
            # sign convention: is the calibration's (first, second) arranged like this run's (first = left / upper)?
            self.dsign = [1.0] * (2 if self.two_pairs else 1)
            try:
                prs = json.loads(str(self.get_dataset(f"Calibrations.Two_ions.{self.cn}_roi_pairs")))
            except Exception:
                prs = None
                print("[CHAIN WARNING] no calibration ROI geometry saved, assuming first = left / upper as in this run")
            if prs is not None:
                for q, tg in enumerate(("first", "last")[:len(self.dsign)]):
                    self.dsign[q], msg = orientation_sign(prs[q], kind)
                    print(f"[CHAIN] {tg} ion: {msg}")
            # the S-curves were measured with ROIs of some size; a different size changes w
            try:
                pr = json.loads(str(self.get_dataset(f"Calibrations.Two_ions.{self.cn}_roi_pairs")))
                chk = ((pr[0][0], self.o_a1), (pr[1][0], self.o_a2)) if self.two_pairs else ((pr[0][0], self.o_a1),)
                for t, (cp, ns) in zip(("first", "last"), chk):
                    csz = (cp[2] - cp[0], cp[3] - cp[1]); nsz = (ns[2] - ns[0], ns[3] - ns[1])
                    if tuple(csz) != tuple(nsz):
                        print(f"[CHAIN WARNING] the calibration used {csz[0]}x{csz[1]} px ROIs for the {t} ion but its ROI is "
                              f"{nsz[0]}x{nsz[1]} px: w (and so the offsets) will not match")
            except Exception:
                pass
            self.set_dataset("Camera.rois", json.dumps(reply), persist=True, archive=True)
        except Exception:
            # the camera has already been armed by "start": release it, otherwise it freezes waiting for triggers
            self._recover_camera()
            raise

    def _recover_camera(self):
        print("[CHAIN] setup failed after the camera was armed: recovery pulse + abort, restoring the machine")
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
        """n_frames camera frames; Doppler on (bright) or off (dark). the 4 words (first_1, second_1, first_N, second_N) go to self.buf."""
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
            self.buf[4 * f] = self.gbuf[self.w0]
            self.buf[4 * f + 1] = self.gbuf[self.w1]
            self.buf[4 * f + 2] = self.gbuf[self.w2]
            self.buf[4 * f + 3] = self.gbuf[self.w3]
        self.frame_counter += n_frames
        if self.use_protection:
            self.urukul1_ch3.sw.off()

    @kernel
    def measure_chain(self, n_frames, bright):
        """Move the ROIs of the 1st ion (slots 1, 0) and of the last ion (slots N, N+1) into their differential pairs,
        read n_frames, close the gate."""
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        self.grabber0.setup_roi(self.sl_a1, self.g_a1[0], self.g_a1[1], self.g_a1[2], self.g_a1[3])
        self.grabber0.setup_roi(self.sl_b1, self.g_b1[0], self.g_b1[1], self.g_b1[2], self.g_b1[3])
        if self.two_pairs:
            self.grabber0.setup_roi(self.sl_a2, self.g_a2[0], self.g_a2[1], self.g_a2[2], self.g_a2[3])
            self.grabber0.setup_roi(self.sl_b2, self.g_b2[0], self.g_b2[1], self.g_b2[2], self.g_b2[3])
        self.grabber0.gate_roi(self.mask_pair)
        self.take_frames(n_frames, bright)
        self.core.break_realtime()
        self.grabber0.gate_roi(0)

    @kernel
    def restore_rois(self):
        """The ion ROIs back to where the camera GUI has them (experiment position); the extra partner slots stay unused."""
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        self.grabber0.setup_roi(self.sl_a1, self.o_a1[0], self.o_a1[1], self.o_a1[2], self.o_a1[3])
        if self.two_pairs:
            self.grabber0.setup_roi(self.sl_a2, self.o_a2[0], self.o_a2[1], self.o_a2[2], self.o_a2[3])

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
                self.measure_chain(self.n_dark, False)
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

                self.measure_chain(self.nf, True)
                newv = self.host_chain(c, self.buf, self.nf)
                self.core.break_realtime()
                if self.do_correct:
                    if self.ak == 0:
                        d = newv - vx
                        if d > 1e-7 or d < -1e-7:
                            vx = newv
                            self.set_dc(vx, vy)
                            delay(self.settle)
                    else:
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
        a = np.array(buf, dtype=float).reshape(-1, 4)[: int(n)]
        npix = np.concatenate([self.pair_npix[0], self.pair_npix[1]])      # single ion: the second pair repeats the first
        self.dark_pp = float((a / npix).mean())
        print(f"[CHAIN] dark level: {self.dark_pp:.1f} counts/px (raw sums {a.mean(axis=0)})")
        try:
            d_cal = 0.5 * (float(self.get_dataset(f"Calibrations.Two_ions.{self.cn}_dark_pp_first")) +
                           float(self.get_dataset(f"Calibrations.Two_ions.{self.cn}_dark_pp_last")))
            print(f"[CHAIN] calibration dark level was {d_cal:.1f} counts/px (difference {self.dark_pp - d_cal:+.1f})")
            if abs(self.dark_pp - d_cal) > 5:
                print("[CHAIN WARNING] bias/dark level differs from the calibration: camera temperature, EM gain or ambient light changed")
        except Exception:
            pass
        self.set_dataset("Stabilizer.Two_ions.dark_pp", self.dark_pp, broadcast=True, archive=True)

    @rpc
    def host_chain(self, c, buf, n) -> TFloat:
        """One measurement of the chain. Returns the voltage the knob should have now."""
        ax, k, cn = self.ax_name, self.ak, self.cn
        if self.t0 is None:
            self.t0 = time.time()
        t = time.time() - self.t0
        raw = np.array(buf, dtype=float).reshape(-1, 4)[: int(n)]
        np_ = 2 if self.two_pairs else 1
        st = [pair_stats(raw[:, 2 * q:2 * q + 2], self.pair_npix[q], self.dark_pp, False, 0.0) for q in range(np_)]
        dPs = [self.dsign[q] * st[q][3] for q in range(np_)]; Ss = [x[2] for x in st]; errs = [x[4] for x in st]
        v_cur = self.h_v[k]
        cals = [self.cal["first"]] + ([self.cal["last"]] if np_ == 2 else [])
        res = chain_correction(dPs, Ss, cals, v_cur, self.v_ref[k], self.c_gain, self.c_dead, self.c_step, self.c_dev,
                               self.c_min, self.c_sat)
        lost = res["lost"]
        r_err = []
        for q in range(np_):
            A_c, B_c, w_c, _ = cals[q]
            if lost or not np.isfinite(errs[q]):
                r_err.append(float('nan'))
            else:
                slope_loc = 2.0 * abs(A_c) / (math.sqrt(math.pi) * w_c) * math.exp(-(res["resid"][q] / w_c) ** 2)   # per volt
                r_err.append(errs[q] / slope_loc if slope_loc > 0 else float('nan'))
        avg_err = (0.5 * math.sqrt(r_err[0] ** 2 + r_err[1] ** 2) if (np_ == 2 and not lost) else r_err[0])
        resid_now = res["resid_avg"]
        guard_msg = ""
        if self.mode_s == "track_only":
            v_new = v_cur
        elif self.mode_s == "response_test":
            v_new = self.v_ref[k] + self.test_pat[int(c) + 1]
        else:
            v_new = res["v_new"]
            # guard: did the previous correction change the measured offset by (about) what was commanded?
            if self.guard_on and not lost and self.prev_move is not None and not self.guard_tripped:
                r_prev, dv_prev = self.prev_move
                if abs(dv_prev) >= 2e-3:
                    ratio = (resid_now - r_prev) / dv_prev
                    if ratio < 0.25:
                        self.guard_bad += 1
                        guard_msg = f"  [GUARD: last correction {dv_prev * 1e3:+.1f} mV changed the offset by {(resid_now - r_prev) * 1e3:+.1f} mV, {self.guard_bad}/3]"
                    else:
                        self.guard_bad = 0
                if self.guard_bad >= 3:
                    self.guard_tripped = True
                    print("[CHAIN GUARD] CORRECTION SWITCHED OFF: three corrections in a row did not move the measured offset as the "
                          "calibration predicts (wrong sign / size, or the offset is not along this knob). Returning the knob to its "
                          "starting value. Run mode = response_test to check sign and slope.")
            if self.guard_tripped:
                v_new = v_cur + max(-self.c_step, min(self.c_step, self.v_ref[k] - v_cur))
                guard_msg = "  [GUARD TRIPPED: correction off, returning to the start value]"
            self.prev_move = (resid_now, v_new - v_cur) if not lost else None
        self.h_v[k] = v_new
        applied = v_cur - self.v_ref[k]

        self.n_pushed += 1
        flag_i = [2 if lost else (1 if sx else 0) for sx in res["sat"]]
        flags = {"first": flag_i[0]}
        data = {"first": (dPs[0], errs[0], Ss[0], res["resid"][0], r_err[0])}
        if np_ == 2:
            flags.update({"last": flag_i[1], "avg": 2 if lost else (1 if any(res["sat"]) else 0)})
            data["last"] = (dPs[1], errs[1], Ss[1], res["resid"][1], r_err[1])
            data["avg"] = (0.5 * (dPs[0] + dPs[1]),
                           0.5 * math.sqrt(errs[0] ** 2 + errs[1] ** 2) if np.isfinite(errs[0]) and np.isfinite(errs[1]) else float('nan'),
                           0.5 * (Ss[0] + Ss[1]), res["resid_avg"], avg_err)
        first_call = (self.log_n == 0)
        self.log_n += 1
        for tg in self.TAGS:
            dP_, e_, S_, r_, re_ = data[tg]
            vals = {"t": t, "dP": dP_, "dP_err": e_, "S": S_, "resid_mV": r_ * 1e3, "resid_err_mV": re_ * 1e3,
                    "V_mV": applied * 1e3, "flag": float(flags[tg])}
            if self.v_per_px > 0:
                vals.update({"resid_px": r_ / self.v_per_px, "resid_err_px": re_ / self.v_per_px, "V_px": applied / self.v_per_px})
            self.rec[tg].append(vals)
            for key, v in vals.items():
                name = f"{self.pre}{tg}_{key}"
                if first_call:
                    self.set_dataset(name, [v], broadcast=True, archive=True)
                else:
                    self.append_to_dataset(name, v)
        if first_call:
            rid = getattr(self.scheduler, "rid", "Local")
            lab = {"correct_and_track": "WITH correction", "track_only": "NO correction (track only)",
                   "response_test": "RESPONSE TEST (knob stepped by hand pattern)"}[self.mode_s]
            names = {"first": "1st ion" if self.two_pairs else "the ion", "last": f"last ion (#{self.nI})",
                     "avg": "AVERAGE of the two edge ions"}
            ylab = (f"offset [camera px] (1 px = {self.v_per_px * 1e3:.3g} mV of {cn})" if self.px_plot else f"offset [mV of {cn}]")
            for tg in self.TAGS:
                p_ = f"{self.pre}{tg}_"
                self.ccb.issue("create_applet", f"Chain {ax} {tg}" if self.two_pairs else f"Ion {ax}",
                               f"${{artiq_applet}}plot_xy {p_}resid_{self.u} --x {p_}t --error {p_}resid_err_{self.u} "
                               f"--fit {p_}V_{self.u} --x-label 'time [s]' --y-label '{ylab}' "
                               f"--title 'RID {rid} {ax} ({cn}) {lab}: {names[tg]}; points = offset from the boundary"
                               f"{' after correction' if self.mode_s == 'correct_and_track' else ''}, red line = correction applied'")
        tag = ""
        if lost:
            tag = "  [LOST: no signal, unchanged]"
        elif any(res["sat"]):
            tag = "  [CLAMPED: beyond the linear cutoff]"
        px = (lambda x: f" ({x / self.v_per_px:+.2f} px)") if self.v_per_px > 0 else (lambda x: "")
        parts = []
        for q, nm in enumerate(("1st" if self.two_pairs else "ion", "last")[:np_]):
            sc = self.S_cal["first" if q == 0 else "last"]
            parts.append(f"{nm}: sum {Ss[q]:.1f} (cal {sc:.1f}), dP {dPs[q]:+.3f}+-{errs[q]:.3f}, "
                         f"offset {res['resid'][q] * 1e3:+.2f}+-{r_err[q] * 1e3:.2f} mV{px(res['resid'][q])}")
        avg_txt = (f" | AVG offset {res['resid_avg'] * 1e3:+.2f}+-{avg_err * 1e3:.2f} mV{px(res['resid_avg']) if not lost else ''}"
                   if np_ == 2 else "")
        print(f"[CHAIN] cycle {int(c) + 1}/{self.n_cyc} {ax}: " + " | ".join(parts) + avg_txt +
              f"; applied {applied * 1e3:+.2f} -> {(v_new - self.v_ref[k]) * 1e3:+.2f} mV{tag}{guard_msg}")
        return float(v_new)

    def analyze(self):
        self.cameraCOMM_postscan()          # first: close the camera side whatever happens below
        summary = {"mode": str(self.mode), "axis": self.ax_name, "n_cycles": int(self.n_cyc)}
        for tg in self.TAGS:
            r = self.rec[tg]
            if not r:
                continue
            ok = [q for q in r if q["flag"] != 2]
            s = {"n": len(r), "lost": int(sum(q["flag"] == 2 for q in r)), "clamped": int(sum(q["flag"] == 1 for q in r))}
            if len(ok) > 1:
                off = np.array([q["resid_mV"] for q in ok])
                s.update({"offset_rms_mV": float(np.sqrt(np.mean(off ** 2))), "offset_mean_mV": float(off.mean()),
                          "offset_std_mV": float(off.std(ddof=1))})
                if self.v_per_px > 0:
                    s.update({"offset_rms_px": s["offset_rms_mV"] * 1e-3 / self.v_per_px,
                              "offset_std_px": s["offset_std_mV"] * 1e-3 / self.v_per_px})
            summary[tg] = s
        if self.mode_s == "response_test":
            print("\n" + "=" * 64)
            print(f"[CHAIN] RESPONSE TEST: measured offset vs knob offset applied during the measurement (expected slope +1.00)")
            for tg in self.TAGS:
                ok = [q for q in self.rec[tg] if q["flag"] == 0]          # linear part of the S-curve only
                note = ""
                if len(ok) < 5:
                    ok = [q for q in self.rec[tg] if q["flag"] != 2]
                    note = " (offset mostly beyond the linear part of the S-curve: the slope is underestimated; centre the ion first)"
                if len(ok) < 5:
                    print(f"[CHAIN]   {tg}: too few valid cycles ({len(ok)})")
                    continue
                x = np.array([q["V_mV"] for q in ok]); y = np.array([q["resid_mV"] for q in ok])
                if np.ptp(x) < 1e-6:
                    print(f"[CHAIN]   {tg}: the knob never moved")
                    continue
                (m, b), cov = np.polyfit(x, y, 1, cov=True) if len(x) > 3 else (np.polyfit(x, y, 1), np.zeros((2, 2)))
                me = float(np.sqrt(abs(cov[0, 0])))
                if m > 0.7 and m < 1.4:
                    verdict = "OK: the ion moves as the calibration says"
                elif m < -0.3:
                    verdict = "WRONG SIGN: a correction would run away. Check which ROI is first/second and the calibration"
                elif abs(m) < 0.3:
                    verdict = "NO RESPONSE: the measured pair does not see the knob (wrong axis / ROIs / ion not on the boundary)"
                else:
                    verdict = f"the response is {m:.2f}x the calibrated one: recalibrate under the current conditions"
                print(f"[CHAIN]   {tg}: slope = {m:+.2f} +- {me:.2f}, offset at 0 applied = {b:+.2f} mV  -> {verdict}{note}")
                summary.setdefault(tg, {})["response_slope"] = float(m)
            print("=" * 64 + "\n")
        self.set_dataset("Stabilizer.Two_ions.summary", json.dumps(summary, default=lambda o: o.item() if hasattr(o, "item") else str(o)), persist=True, archive=True)
        self.set_dataset("Stabilizer.Two_ions.mode", str(self.mode), archive=True)
        print("\n" + "=" * 64)
        print(f"[CHAIN] summary, mode = {self.mode}, axis = {self.ax_name}")
        for tg in self.TAGS:
            if tg in summary:
                print(f"[CHAIN]   {tg:5s}: " + ", ".join(f"{k} = {v:.2f}" if isinstance(v, float) else f"{k} = {v}"
                                                         for k, v in summary[tg].items()))
        print("[CHAIN]   offset_rms = how far the ion sat from its boundary when measured (smaller = better centred)")
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
        print(f"[CHAIN] camera acquired {frames} frames, expected {self.expected_frames}")
        if completed and frames is not None and frames != self.expected_frames:
            print("[CHAIN WARNING] frame count mismatch (missed triggers, or the cooling-shot combo box is not 'None')")

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
            print("[CHAIN] camera did not answer the abort: sending trigger pulses (round %d)" % rounds)
            try:
                self.camera_pulses(20)
            except Exception as e:
                print("[CHAIN] camera_pulses failed:", repr(e))
                break
            th.join(0.6)
        if th.is_alive():
            print("[CHAIN] WARNING: camera still not released; toggle the trigger line by hand / restart the camera GUI")
        elif res.get("err"):
            print("[camera] abort failed:", res["err"])
        else:
            print("[CHAIN] camera released" + (" after %d pulse round(s)" % rounds if rounds else ""))
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

            print("[CHAIN] starting kernel...")
            self.krun()
        finally:
            if not self._camera_closed and self.n_pushed < self.n_expected_pushes:
                print("[CHAIN] scan incomplete: sending recovery pulse to the camera trigger line, then abort")
                self._release_camera()