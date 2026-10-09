"""
Ion tracking inside the main scan experiment (N ions, EndcapX, NO calibration needed): a "cooling shot" between scan points
measures where the ions sit on Grabber ROI pairs, and the EndcapX value of the NEXT scan point is corrected so the ions stay
where they were at the start of the run.

Usage (see the hooks listed in the delivery message):  class BarebonesArtiqScan2DGrabberV2(IonTrackingMixin, EnvExperiment)

What happens when `trackIon` is on:
  * Camera GUI: ONE ROI centred on EACH ion. The number of ions N is the number of ROIs the camera sends (N <= 8). ARTIQ makes
    one pair per ion: that ROI is shifted by half its size (slot i, "first") and a same-size partner ROI is put directly next to
    it in an EXTRA Grabber slot (slot N + i, "second", not on the GUI). The Grabber therefore reads 2N ROI sums per frame.
  * BEFORE scan point 0, N, 2N, ... (`track_every_n`) a tracking EVENT runs: Doppler cooling for `track_cool_time`, then
    `track_frames` camera frames read on all pairs (averaged): per ion the brightness imbalance
    dP_i = (first_i - second_i)/(first_i + second_i).
  * FIRST EVENT (set-up, once per run), all before scan point 0:
      1. the scan's own DC values are written (ON() has not done it yet), so what follows is measured in the real configuration;
      2. the first LATCH_DET detections (no correction) fix the SETPOINT of every ion: the ions are held where they start
         (dP_set_i = median of its first detections);
      3. a PROBE step of EndcapX (about PROBE_PX camera pixels) is applied and the response of the average imbalance gives the
         slope s0 = d e / d V (sign and size) of THIS ion set in THIS configuration; the step is undone at once;
      4. s0 gives the direction of the correction, the band (track_band_px converted to dP) and, with track_Ki_mV = 0, the gain.
    If the probe produces no clear response the run stops with an error (the ions are not on the sensitive part of their pairs,
    the camera does not see them, or EndcapX does not move them).
  * Every event: the tracker error is the AVERAGE over the ions, e = mean_i (dP_i - dP_set_i) (error bar sqrt(sum err_i^2)/N).
    The controller NULLS e (PID on dP itself, no curve inversion). Then
        latest detection in band (|e| <= band, and every ion within IND_BAND_FACTOR x band) -> the scan point(s) run (the GATE);
        after leaving the band, CHECK_TIMES more in-band detections must follow before the point may run;
        out, but the median of the last 3 is in band      -> look again, nothing moves (jitter / spike);
        out and the median is out                         -> PID step of EndcapX (<= track_max_step_mV), wait, detect again;
        ... up to `track_max_iter` detections; if the ions are still out of band the points run anyway (Tracking.point_ok = 0).
    band = min(max(track_band_px in dP, BAND_SIGMA standard errors of e), BAND_MAX_DP). The decision code is track_decide().
    With track_correct off one detection per event is made and nothing is changed (A/B comparison with the same frame timing; the
    only disturbance is the short probe in the first event, undone at once); the in-band flag and Tracking.point_ok then show what
    the gate would have rejected.
  * Gains are in mV of EndcapX per unit dP (track_Kp_mV, track_Ki_mV); Ki = 0 means automatic (half of 1/|s0|).
  * The DC change inside an event uses the same DC lines as ON() with the scan point's own values (only EndcapX shifted by the
    correction), so ON() of the next point writes the same value: no extra jump. Steps are <= track_max_step_mV and the total
    <= track_max_excursion_mV.
  * Every event starts with `track_dark_frames` Doppler-off frame(s) (bias of that event).
  * If one ion is lost (signal below MIN_SIGNAL) nothing is changed for that detection (status 3).
  * With a single ROI everything reduces to the single-ion tracker.

Camera: the extra frames are announced to the camera in the 'start' packet ('extra_frames'), as the stand-alone scripts do.
Datasets (archived with the run): Tracking.EndcapX_{t, ev, it, pt, dP, dP_err, S, e_dP, resid_mV, resid_err_mV, V_mV, drift_mV, band_mV,
inband, status, flag, spread_mV, dP<i>, e<i>_dP, resid<i>_mV [, *_px]} (one row per DETECTION; dP, S, resid are the averages over the ions;
resid* = e / s0 are NaN until the probe has measured s0), Tracking.setpoint_dP (per ion),
Tracking.event_{pt, ok, dv_mV, detections}, Tracking.point_dv_mV, Tracking.point_ok (per scan point), Tracking.summary.
26/10/01 gt
"""
from artiq.experiment import *
import numpy as np
import json
import time


# ----------------------------------------------------------------------------------------------
# pure helpers
# ----------------------------------------------------------------------------------------------
def pair_rois(axis, nth, frame=None):
    """axis 'Y': side by side, first = nth moved left by w//2, second directly right. axis 'X': stacked, first = nth moved up by
    h//2, second directly below. Both have the size of nth. Returns (first, second); dP = (first - second)/(first + second)."""
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
            raise RuntimeError(f"ROI {r} for the pair falls outside the camera frame {frame}; move the ion ROI away from the frame edge")
    return first, second


def pair_stats_mean(raw, npix, dark_pp):
    """raw (frames, 2) ROI sums -> (first, second, sum, dP, err_dP): mean counts/px, bias subtracted, propagated SEM."""
    per_px = np.asarray(raw, dtype=float) / np.asarray(npix, dtype=float)
    n_f = per_px.shape[0]
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


def ions_stats(raw, npix, dark_pp, n):
    """raw (frames, 2n): columns 0..n-1 are the 'first' ROIs of ions 0..n-1 (Grabber slots 0..n-1), columns n..2n-1 the 'second' ROIs
    (slots n..2n-1). Returns one pair_stats_mean tuple (first, second, sum, dP, err) per ion."""
    raw = np.asarray(raw, dtype=float)
    npix = np.asarray(npix, dtype=float)
    out = []
    for i in range(int(n)):
        cols = [i, int(n) + i]
        out.append(pair_stats_mean(raw[:, cols], npix[cols], dark_pp))
    return out


MIN_SIGNAL = 5.0       # (first + second) counts/px below which an ion is considered lost (nothing changes)
MIN_COUNTS_NODARK = 600.0  # track_dark_frames = 0: the bias is NOT subtracted, so this is a RAW level, (first + second) counts/px of an ion pair; below it = lost
LOST_STOP_N = 2             # this many consecutive lost detections stop the experiment (0 = only flag them, never stop)
RECOVERY_ON_LOST = True                                   # ions lost -> submit the recovery script after the run
RECOVERY_PRIORITY = 10                                    # runs before anything else waiting in the pipeline
LATCH_SKIP = 0         # first detections thrown away (start-up transient) before the latch collects
LATCH_DET = 3          # detections (first event, no correction in between) whose median fixes the setpoints
PROBE_PX = 1.0         # size of the probe step of EndcapX, in camera pixels (needs track_volts_per_pixel; limited by track_max_step_mV)
PROBE_V = 5e-3         # probe step (V) if track_volts_per_pixel is not set
PROBE_SNR = 4.0        # the probe response must exceed this many standard errors ...
PROBE_MIN_DP = 0.02    # ... and this change of the average dP, otherwise the run stops with an error
KICK_PULSES = 300      # trigger pulses (15 ms apart) sent while the end-of-scan fetch is running (releases the blocked Andor stop)
ROI_FOLLOW_SIGN = 1      # +1: ROI rows go DOWN in number (ion moves up in the image) when EndcapX increases; set -1 if the Grabber axis is flipped
PID_MEDIAN = 3         # the controller acts on the median of the last PID_MEDIAN detections (kills isolated spikes); 1 = raw detection
BAND_SIGMA = 0.0       # the in-band test is never tighter than this many standard errors of the detection
BAND_MAX_DP = 0.3      # ... and never wider than this (dP)
IND_BAND_FACTOR = 2.0  # several ions: EVERY ion must also be within this many bands of its own setpoint (the average alone would hide
                       # ions that move in opposite directions, e.g. a rotating crystal)
AUTO_LOOP_GAIN = 0.5   # track_Ki_mV = 0: Ki is set to this fraction of 1/|s0| (s0 = dP per V measured by the probe)
CUSTOM_APPLET = True   # True: launch `${artiq_applet}ion_tracking_applet` (status colours + deadband lines; the file must be copied into
                       # artiq/applets/ of the ARTIQ environment, see the top of ion_tracking_applet.py) instead of the stock plot_xy
SETTLE = 50e-3         # s of Doppler cooling after a DC change before the next detection

CHECK_TIMES = 2        # after an out-of-band detection, this many further in-band detections must follow before the point may run
VOTE_N = 5             # out-of-band detection: up to this many detections in total are taken before a correction is decided
VOTE_MAJ = 3           # ... and this many that agree (out on the same side, or in band) decide it


def track_pid(st, e, kp, ki):
    """One step of the incremental (velocity-form) PI controller. e = offset of the ions from their setpoints (dP) as measured with the
    correction in force. st = {"e1"} (previous error; None at the start), modified in place.
    Returns (dv, (p, i)): the change of the correction, dv = -(p + i), with
        p = kp * (e - e_prev)                    proportional (on the change of the error)
        i = ki * e                               integral    (the sum of all dv's IS the integral: no windup state)
    Gains are per detection. The plant is static (the offset is drift + correction), so the loop is
    z^2 + (kp + ki - 1) z - kp = 0: stable for 0 <= kp < 1 and ki < 2 (1 - kp); kp > 0 only slows it down and rings."""
    e1 = e if st["e1"] is None else st["e1"]
    p, i = kp * (e - e1), ki * e
    st["e1"] = e
    return -(p + i), (p, i)


class IonTrackingMixin:
    # ------------------------------------------------------------------------------------------
    # arguments (call self.track_build() at the end of build())
    # ------------------------------------------------------------------------------------------
    def track_build(self):
        g = "Ion tracking"
        self.setattr_argument("trackIon", BooleanValue(default=True), group=g,
                              tooltip="Cooling shot with Grabber ion-position measurement between scan points, and EndcapX "
                                      "correction of the following points. One camera-GUI ROI per ion (the number of ROIs = the number "
                                      "of ions, at most 8). Needs checkCameraDetection and use_grabber. No calibration needed: the "
                                      "first event measures the response of the ions to a small EndcapX step.")
        self.setattr_argument("track_every_n", NumberValue(default=1, step=1, ndecimals=0, min=1), group=g,
                              tooltip="Tracking event BEFORE scan point 0, N, 2N, ... (counted in scan points)")
        self.setattr_argument("track_correct", BooleanValue(default=False), group=g,
                              tooltip="True: track, correct and GATE: a scan point only runs when the latest detection is inside the band (see track_max_iter for the cap). "
                                      "False: measure only, nothing is changed and one detection per event (free drift for the A/B comparison; the in-band flag and "
                                      "Tracking.point_ok then show what the gate would have rejected).")
        self.setattr_argument("track_along", EnumerationValue(["image_horizontal", "image_vertical"],
                                                              default="image_horizontal"), group=g,
                              tooltip="Direction in the camera image in which EndcapX moves the ions")
        self.setattr_argument("track_frames", NumberValue(default=1, step=1, ndecimals=0, min=1), group=g)
        self.setattr_argument("track_dark_frames", NumberValue(default=0, step=1, ndecimals=0, min=0), group=g,
                              tooltip="Doppler-off frames at the start of EVERY tracking event (EMCCD bias for that event)")
        self.setattr_argument("track_cool_time", NumberValue(default=2 * ms, unit="ms", min=0, step=1 * ms, ndecimals=1),
                              group=g, tooltip="Doppler cooling before the first tracking frame of each event")
        self.setattr_argument("track_exposure", NumberValue(default=10 * ms, unit="ms", min=0.05 * ms, step=0.1 * ms, ndecimals=3),
                              group=g, tooltip="Camera exposure of the tracking frames")
        self.setattr_argument("track_frame_period", NumberValue(default=20 * ms, unit="ms", min=9 * ms, step=1 * ms, ndecimals=1),
                              group=g)
        g = "Ion tracking controller"
        self.setattr_argument("track_band_px", NumberValue(default=0.5, min=0.0, step=0.05, ndecimals=3), group=g,
                              tooltip="Deadband in camera pixels (needs track_volts_per_pixel): the ions count as on their setpoints when the "
                                      "average imbalance is within this many pixels of the setpoint (converted to dP with the slope measured by the "
                                      "probe). Automatically widened to BAND_SIGMA standard errors of the detection. With several ions every "
                                      "single ion must also be within IND_BAND_FACTOR x this band.")
        self.setattr_argument("track_max_iter", NumberValue(default=20, min=1, step=1, ndecimals=0), group=g,
                              tooltip="Cap on the detections per tracking event (track_correct on): detect -> look again / correct -> detect until the latest detection "
                                      "is inside the band. If the cap is reached the scan point(s) run anyway (flagged in Tracking.point_ok = 0). "
                                      "The first event also needs the set-up detections (latch + probe), so at least 6.")
        self.setattr_argument("track_Kp_mV", NumberValue(default=0.0, min=0.0, step=0.1, ndecimals=2), group=g,
                              tooltip="PID proportional gain, mV of EndcapX per unit dP (on the change of the imbalance). The imbalance is "
                                      "drift + correction (static plant), so Kp > 0 only slows the loop and makes it ring.")
        self.setattr_argument("track_Ki_mV", NumberValue(default=5.0, min=-1.0, step=0.1, ndecimals=2), group=g,
                              tooltip="PID integral gain, mV of EndcapX per unit dP removed per detection. 0 = automatic: half of 1/|slope| measured "
                                      "by the probe, i.e. half of the measured offset per correction. The log prints the resulting dimensionless "
                                      "loop gain (stable below 2).")
        self.setattr_argument("track_max_step_mV", NumberValue(default=10.0, min=0.1, step=0.5, ndecimals=2), group=g,
                              tooltip="Largest EndcapX change per single correction (the DC never jumps by more); also limits the probe step")
        self.setattr_argument("track_max_excursion_mV", NumberValue(default=50.0, min=0.1, step=1.0, ndecimals=1), group=g,
                              tooltip="The total correction never exceeds this (mV)")
        self.setattr_argument("track_plot_px", BooleanValue(default=True), group=g,
                              tooltip="Plot the tracker in camera pixels (needs track_volts_per_pixel)")
        self.setattr_argument("track_volts_per_pixel", NumberValue(default=0.006, min=0.0, step=0.001, ndecimals=5), group=g,
                              tooltip="V of EndcapX per camera pixel (0 = not set): size of the probe step, band and the px display")

        g = "Ion images"
        self.setattr_argument("track_save_images", BooleanValue(default=False), group=g,
                              tooltip="Save every camera image of the scan (tracking events and experimental shots) to one .npz together with the frame flags "
                                      "(1 = experimental scan-point shot, 2 = tracking detection in band directly before a scan point, 0 = other tracking / cooling frames")
        self.setattr_argument("track_image_name", StringValue(default="ion_images"), group=g,
                              tooltip="File name WITHOUT extension. Saved as <name>.npz in the camera's usual date folder; if it exists, _2, _3, ... is appended")

    # ------------------------------------------------------------------------------------------
    # prepare-time (host)
    # ------------------------------------------------------------------------------------------
    def track_prepare(self):
        """First line of prepare(): attribute defaults so the kernels always compile, and validation.
        The variables that mirror a GUI argument keep the GUI name (the argument is re-assigned with a clean type: bool / int / float / str);
        the others are the internal state of the tracker."""
        # ---- GUI arguments, re-assigned with a fixed type (same names as on the GUI; the fallback is the GUI default) ----
        self.trackIon = bool(getattr(self, "trackIon", True))                   # tracking on / off
        self.track_correct = bool(getattr(self, "track_correct", False))        # True: track + correct + gate; False: measure only
        self.track_every_n = max(1, int(getattr(self, "track_every_n", 1)))     # a tracking event before scan point 0, N, 2N, ...
        self.track_frames = int(getattr(self, "track_frames", 50))              # camera frames averaged in one bright detection
        self.track_dark_frames = int(getattr(self, "track_dark_frames", 5))     # Doppler-off frames at the start of every event (bias)
        self.track_cool_time = float(getattr(self, "track_cool_time", 2e-3))    # s of Doppler cooling before the first bright frame
        self.track_exposure = float(getattr(self, "track_exposure", 1e-3))      # s, camera exposure (= camera trigger pulse width)
        self.track_frame_period = float(getattr(self, "track_frame_period", 10e-3))   # s between two camera frames
        self.track_max_iter = max(1, int(getattr(self, "track_max_iter", 10)))  # cap on the detections per event
        self.track_band_px = float(getattr(self, "track_band_px", 0.1))         # deadband floor (camera px)
        self.track_volts_per_pixel = float(getattr(self, "track_volts_per_pixel", 0.013))   # V of EndcapX per camera pixel (0 = unknown)
        self.track_plot_px = bool(getattr(self, "track_plot_px", True))         # plot / report in px (needs track_volts_per_pixel > 0)
        # ---- aliases the main experiment's krun hook still uses (do not rename without changing the main file) ----
        self.track_on = self.trackIon                    # krun: `if self.track_on:`
        self.track_every = self.track_every_n            # krun: `flat_iter % self.track_every == 0`
        # ---- Grabber geometry (filled in track_after_prescan, once the number of ions = the number of GUI ROIs is known) ----
        self.track_kick = int(KICK_PULSES)
        self._tr_fetch_thread = None
        self.t_n_ion = 1                                 # number of ions (= number of ROIs the camera sends)
        self.t_nb = 2                                    # Grabber values per frame = 2 x ions (N 'first' ROIs, then N 'second' ROIs)
        self.tr_mask = 3                                 # gate mask of the tracking ROIs: slots 0 .. 2N - 1
        # 'first' ROI of every ion (slot i) and 'second' ROI of every ion (slot N + i), [x0, y0, x1, y1] as separate kernel lists
        self.tr_a_x0, self.tr_a_y0, self.tr_a_x1, self.tr_a_y1 = [0], [0], [1], [1]
        self.tr_b_x0, self.tr_b_y0, self.tr_b_x1, self.tr_b_y1 = [0], [0], [1], [1]
        self.t_npix = np.array([1.0, 1.0])               # pixels of the 2N tracking ROIs (sums -> counts/px)
        # ---- buffers and counters of the kernels ----
        self.tbuf = [0, 0]                                           # one Grabber read: the 2N ROI sums of a frame
        self.tbuf_all = [0] * (2 * max(self.track_frames, self.track_dark_frames, 1))   # all frames of one detection, 2N values per frame
        self.tr_frame_counter = 0                        # frames read so far (tag of the Grabber timeout guard)
        self.tr_aborted = False                          # set when a termination was requested: the main krun checks it and returns
        self.tr_settle = SETTLE                          # s of Doppler cooling after a DC change, before the next detection
        self.track_extra_frames = 0                      # upper bound of camera frames announced to the camera (set in track_plan)
        self.t_frames_taken = 0                          # camera frames actually used so far
        self.track_frames_taken = 0                      # same, read by the main experiment's cameraCOMM_postscan
        # ---- controller state ----
        self.t_dv = 0.0                    # correction in force (V), host copy of what track_event returns
        self.t_status = 0                  # decision of the last detection, read by the kernel: 0 done, 1 look again, 2 corrected, 3 give up
        self.t_pid = {"e1": None}   # PID memory: previous error
        self.t_pidc = (float('nan'),) * 2  # P, I contributions of the last step (V)
        self.t_ehist = []                  # last PID_MEDIAN average imbalances (after the probe) for the median filter
        self.t_ev_out = False              # an out-of-band detection happened in the current event
        self.t_confirm = 0                 # consecutive in-band confirmations since then
        self.t_votes = []
        self.t_lost_n = 0
        self.t_lost_stop = False
        self.t_band_dP = 0.0               # floor of the band in dP, set when the probe has measured the slope
        self.t_gains = (0.0, 0.0)     # (Kp, Ki) in V per unit dP, set when the probe has measured the slope
        self.t_s0 = None                   # dP per V of the average imbalance (signed), measured by the probe in the first event
        # ---- set-up of the first event: setpoints (latch) and probe ----
        self.t_sp_dP = np.full(1, float('nan'))   # setpoint of every ion (dP): where it was at the start
        self.t_sp_set = False              # the setpoints have been latched
        self.t_latch = [[]]                # per ion: dP of the first detections (the setpoint decision)
        self.t_probe_pending = False       # the probe step is applied, its response is the next detection
        self.t_probe_fail = False          # the probe found no response: the next detection raises the error
        self.t_probe_v0 = 0.0              # correction before the probe step (V)
        self.t_probe_dv = 0.0              # probe step (V)
        # ---- bookkeeping of the detections and events ----
        self.t_t0 = None                   # wall-clock time of the first detection (t = 0 of the tracker plot)
        self.t_n = 0                       # detections so far
        self.t_rec = []                    # one dict per detection (also the datasets Tracking.EndcapX_*)
        self.t_cols = {}                   # the same, per quantity, kept as lists and published as numpy arrays
        self.t_ev_info = {}                # per event: [scan point, final correction (V), in band at the end, detections]
        self.t_ev_cur = -1                 # index of the current event
        self.t_ev_n = 0                    # detections so far in the current event
        self.t_ev_pt = None                # scan point the current event belongs to (to catch a double call in krun)
        # ---- reference values ----
        self.t_dark = 0.0                  # dark (bias) level of the current event, counts/px
        self.t_dark_ref = None             # dark level of the first event of this run, counts/px
        self.t_Scal = float('nan')         # (first + second) counts/px of the ions at the start of the run (reference for the log)
        if self.trackIon and self.track_plot_px and self.track_volts_per_pixel <= 0:
            print("[TRACK WARNING] track_plot_px is on but track_volts_per_pixel = 0: plotting in mV instead")
            self.track_plot_px = False
        if self.trackIon and self.track_exposure >= self.track_frame_period:
            raise ValueError("track_exposure must be shorter than track_frame_period")
        if self.trackIon and self.track_max_iter < LATCH_SKIP + LATCH_DET + 3:
            raise ValueError(f"track_max_iter = {self.track_max_iter}: the first event needs {LATCH_SKIP + LATCH_DET} detections for the setpoints, "
                             f"one for the probe, one to step back and one to verify: at least {LATCH_SKIP + LATCH_DET + 3}")

        self.track_save_images = bool(getattr(self, "track_save_images", False))
        self.track_image_name = str(getattr(self, "track_image_name", "ion_images")).strip()
        self.fr_flag = []     # one entry per camera frame, in acquisition order: 1 = experimental shot, 2 = tracking detection in band right before a scan point, 0 = other tracking / cooling frames
        self.fr_idx = []      # scan point (flag 1) or tracking event (flag 0); -1 = the global cooling shot
        if self.track_save_images and not (getattr(self, "checkCameraDetection", False) and getattr(self, "use_grabber", False)):
            print("[FRAMES WARNING] track_save_images needs checkCameraDetection and use_grabber: no images will be saved")

    def track_plan(self, n_points):
        """Called from _setup_camera (before the 'start' packet is built). Returns the number of extra camera frames."""
        self.track_extra_frames = 0
        if not self.trackIon:
            return 0
        if not (getattr(self, "checkCameraDetection", False) and getattr(self, "use_grabber", False)):
            raise ValueError("trackIon needs checkCameraDetection and use_grabber")
        if getattr(self, "checkAllZ_calib", False):
            raise ValueError("trackIon cannot be combined with the AllZ calibration")
        idx_x = getattr(self, "idx_endcapX", None)
        if idx_x is not None and idx_x in (getattr(self, "scan_index", -1), getattr(self, "scan_index_y", -1)):
            raise ValueError("trackIon corrects EndcapX, so EndcapX itself cannot be scanned")
        n_events = len(range(0, int(n_points), self.track_every_n))
        self.t_n_events = n_events
        self.track_extra_frames = n_events * (self.track_dark_frames + self.track_max_iter * self.track_frames)   # upper bound
        print(f"[TRACK] {n_events} tracking events (before scan point 0, {self.track_every_n}, ... of {int(n_points)} points), each up to "
              f"{self.track_max_iter} detections; at most {self.track_extra_frames} extra camera frames (usually far fewer; the camera "
              f"must accept fewer frames, see Camera.py patch); correction {'ON' if self.track_correct else 'OFF (track only)'}")
        return self.track_extra_frames

    def roi_follow_plan(self, frame):
        """Host: per scan point (flat index j * nx + i) the row shift of the main ROIs that keeps them on the ions when EndcapX is scanned."""
        self.rf_on = False
        self.rf_dy = [0]
        self.rf_now = 0
        names = (self.scan_param_name, self.scan_param_y if self.is_2d_scan else None)
        if "endcapX" not in names or not (self.use_grabber and self.checkCameraDetection) or self.trackIon:
            return
        vpp = float(self.track_volts_per_pixel)
        if vpp <= 0:
            raise ValueError("track_volts_per_pixel must be > 0 to let the ROIs follow an EndcapX scan")
        ref = float(self.originalEndcapX)
        dy = []
        for j in range(len(self.scan_arr_y)):
            for i in range(len(self.scan_arr)):
                v = float(self.scan_arr[i]) if self.scan_param_name == "endcapX" else float(self.scan_arr_y[j])
                dy.append(int(round(-ROI_FOLLOW_SIGN * (v - ref) / vpp)))
        lo, hi = min(dy), max(dy)
        if frame:
            for k in range(self.n_roi):
                if self.roi_x0[k] + lo < 0 or self.roi_x1[k] + hi > frame["w"]:
                    raise RuntimeError(
                        f"EndcapX scan moves ROI {k} {[self.roi_x0[k], self.roi_y0[k], self.roi_x1[k], self.roi_y1[k]]} "
                        f"by {lo:+d}..{hi:+d} px along x, outside the camera frame {frame}; reduce the scan range or move the ROI")
        self.rf_dy = dy
        self.rf_on = True
        print(f"[ROI-FOLLOW] EndcapX scan: ROIs follow the ions, shift {lo:+d} .. {hi:+d} rows "
              f"(ref EndcapX = {ref:.4f} V, {vpp * 1e3:.1f} mV/px, sign {ROI_FOLLOW_SIGN:+d})")

    def frame_log(self, n, flag, idx):
        n = int(n)
        if n > 0:
            self.fr_flag.extend([int(flag)] * n)
            self.fr_idx.extend([int(idx)] * n)

    def frame_log_publish(self):
        if not (getattr(self, "checkCameraDetection", False) and getattr(self, "use_grabber", False)):
            return
        self.set_dataset("Camera.frame_flag", np.array(self.fr_flag, dtype=np.int8), broadcast=True, archive=True)
        self.set_dataset("Camera.frame_idx", np.array(self.fr_idx, dtype=np.int32), broadcast=True, archive=True)
        fl = np.array(self.fr_flag)
        n1, n2 = int(np.sum(fl == 1)), int(np.sum(fl == 2))
        print(
            f"[FRAMES] {len(fl)} camera frames logged: {n1} experimental (flag 1), {n2} tracking frames in band before a scan point (flag 2), "
            f"{len(fl) - n1 - n2} other tracking / cooling frames (flag 0)")

    def _jsonable(self, o):
        if isinstance(o, dict):
            return {str(k): self._jsonable(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [self._jsonable(v) for v in o]
        if isinstance(o, np.ndarray):
            return self._jsonable(o.tolist())
        if isinstance(o, np.generic):
            return o.item()
        return o

    def fetch_payload(self):
        """ARTIQ-side data of this run, saved with the images for comparison (called at the end of the scan: all RPCs of the points are done)."""
        d = {"rid": getattr(self.scheduler, "rid", -1), "num_repeat": int(self.num_repeat)}
        d["scan"] = {"x_name": str(self.scan_param_name), "x": np.asarray(self.scan_arr, dtype=float),
                     "x_unit": str(self.scan_unit),
                     "y_name": str(self.scan_param_y), "y": np.asarray(self.scan_arr_y, dtype=float),
                     "y_unit": str(self.scan_unit_y)}
        d["start_values"] = {n: float(v) for n, v in zip(self.on_params, self.default_values)}
        if getattr(self, "grabberHistogramList", None) is not None:
            d["grab_hist"] = np.asarray(self.grabberHistogramList,
                                        dtype=float)  # (scan points, ROIs, shots): raw ROI sums
            d["roi_npix"] = np.asarray(self.roi_npix, dtype=float)
            d["roi_box"] = [[self.roi_x0[k], self.roi_y0[k], self.roi_x1[k], self.roi_y1[k]] for k in range(self.n_roi)]
        if np.ndim(self.scanHistogramList) == 2:
            d["pmt_hist"] = np.asarray(self.scanHistogramList, dtype=float)  # (scan points, shots)
        if self.trackIon and self.t_rec:
            t = {k: list(v) for k, v in self.t_cols.items()}  # one entry per detection (= Tracking.EndcapX_*)
            evs = sorted(self.t_ev_info)
            n_pts = int(getattr(self, "n_points_expected", 0))
            dv_pt, ok_pt = np.zeros(n_pts), np.zeros(n_pts)
            for p in range(n_pts):
                cur = [e for e in evs if self.t_ev_info[e][0] <= p]
                if cur:
                    dv_pt[p], ok_pt[p] = self.t_ev_info[cur[-1]][1] * 1e3, float(self.t_ev_info[cur[-1]][2])
            t["event_pt"] = [self.t_ev_info[e][0] for e in evs]
            t["event_dv_mV"] = [self.t_ev_info[e][1] * 1e3 for e in evs]
            t["event_ok"] = [float(self.t_ev_info[e][2]) for e in evs]
            t["event_detections"] = [self.t_ev_info[e][3] for e in evs]
            t["point_dv_mV"], t["point_ok"] = dv_pt, ok_pt
            t["point_after_ok"], t["point_after_offset_mV"] = self.track_point_after()
            t["setpoint_dP"] = self.t_sp_dP
            t["slope_dP_per_V"] = float('nan') if self.t_s0 is None else self.t_s0
            t["band_dP"] = self.t_band_dP
            t["volts_per_pixel"] = self.track_volts_per_pixel
            t["correct"] = float(self.track_correct)
            t["track_frames"] = float(self.track_frames)
            t["dark_frames"] = float(self.track_dark_frames)
            d["track"] = t
        return d

    def fetch_msg(self, completed):
        """The fetch request: carries the frame flags, the image-saving choice and, if saving, the ARTIQ data of the run."""
        msg = {"cmd": "fetch", "completed": completed,
               "frame_flag": [int(x) for x in self.fr_flag], "frame_idx": [int(x) for x in self.fr_idx],
               "save_images": bool(self.track_save_images), "save_name": str(self.track_image_name)}
        if self.track_save_images:
            try:
                msg["artiq"] = self._jsonable(self.fetch_payload())
            except Exception as e:
                print(
                    f"[FRAMES] could not collect the ARTIQ data for the image file ({e!r}): images are saved without it")
        return msg

    @kernel
    def roi_follow_apply(self):
        """Kernel: main ROIs to their GUI boxes shifted by self.rf_now rows (between frames, nothing in flight)."""
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        for k in range(self.n_roi):
            self.grabber0.setup_roi(k, self.roi_x0[k] + self.rf_now, self.roi_y0[k],
                                    self.roi_x1[k] + self.rf_now, self.roi_y1[k])
        self.core.break_realtime()
        self.grabber0.gate_roi(self.roi_mask)
        self.core.break_realtime()

    def track_after_prescan(self, frame):
        """Called at the end of cameraCOMM_prescan (ROIs known, camera armed): one pair per ROI (= per ion)."""
        if not self.trackIon:
            return
        try:
            n = int(self.n_roi)                      # ions = ROIs the camera sent
            if n < 1:
                raise RuntimeError("the camera sent no ROI: nothing to track")
            if 2 * n > 16:
                raise RuntimeError(f"{n} ions (= ROIs on the camera GUI) need {2 * n} Grabber slots for the tracking pairs, "
                                   f"the gateware has 16: at most 8 ions can be tracked")
            horiz = (str(self.track_along) == "image_horizontal")
            kind = "Y" if horiz else "X"            # EndcapX pair: side by side if the ions move horizontally
            firsts, seconds, boxes = [], [], []
            for k in range(n):
                box = (self.roi_x0[k], self.roi_y0[k], self.roi_x1[k], self.roi_y1[k])
                try:
                    f1, s1 = pair_rois(kind, box, frame)
                except RuntimeError as e:
                    raise RuntimeError(f"ion {k}: {e}")
                firsts.append(f1)
                seconds.append(s1)
                boxes.append(box)
            self.t_n_ion, self.t_nb = n, 2 * n
            self.tr_mask = (1 << (2 * n)) - 1
            self.tr_a_x0, self.tr_a_y0 = [int(r[0]) for r in firsts], [int(r[1]) for r in firsts]
            self.tr_a_x1, self.tr_a_y1 = [int(r[2]) for r in firsts], [int(r[3]) for r in firsts]
            self.tr_b_x0, self.tr_b_y0 = [int(r[0]) for r in seconds], [int(r[1]) for r in seconds]
            self.tr_b_x1, self.tr_b_y1 = [int(r[2]) for r in seconds], [int(r[3]) for r in seconds]
            npx = lambda r: float((r[2] - r[0]) * (r[3] - r[1]))
            self.t_npix = np.array([npx(r) for r in firsts] + [npx(r) for r in seconds])
            self.tbuf = [0] * (2 * n)
            self.tbuf_all = [0] * (2 * n * max(self.track_frames, self.track_dark_frames, 1))
            self.t_sp_dP = np.full(n, float('nan'))
            self.t_latch = [[] for _ in range(n)]
            print(f"[TRACK] {n} ion{'s' if n > 1 else ''} (= ROIs on the camera GUI): {'left / right' if kind == 'Y' else 'upper / lower'} pairs, "
                  f"{2 * n} Grabber slots")
            for k in range(n):
                print(f"[TRACK]   ion {k}: ROI {list(boxes[k])} (GUI) -> first {list(firsts[k])} (slot {k}), "
                      f"second {list(seconds[k])} (extra slot {n + k})")
            for i in range(n):                      # the pair windows of neighbouring ions may overlap: information only
                wi = (min(firsts[i][0], seconds[i][0]), min(firsts[i][1], seconds[i][1]),
                      max(firsts[i][2], seconds[i][2]), max(firsts[i][3], seconds[i][3]))
                for j in range(i + 1, n):
                    wj = (min(firsts[j][0], seconds[j][0]), min(firsts[j][1], seconds[j][1]),
                          max(firsts[j][2], seconds[j][2]), max(firsts[j][3], seconds[j][3]))
                    if min(wi[2], wj[2]) > max(wi[0], wj[0]) and min(wi[3], wj[3]) > max(wi[1], wj[1]):
                        print(f"[TRACK] the pair windows of ions {i} and {j} overlap: each ion's pair sees part of its neighbour's light "
                              f"(the probe measures the response with the neighbours present, as it is during the run)")
            self.t_ctl = (float(self.track_max_step_mV) * 1e-3, float(self.track_max_excursion_mV) * 1e-3)
            if self.track_volts_per_pixel <= 0:
                print("[TRACK WARNING] track_volts_per_pixel = 0: the probe step is %.1f mV, track_band_px cannot be converted "
                      "(the band is BAND_SIGMA standard errors of a detection only)" % (PROBE_V * 1e3))
            print(f"[TRACK] no calibration: the first event latches the setpoints (ions held where they start) and measures the response "
                  f"to a probe step of about {PROBE_PX:g} px (<= {self.t_ctl[0] * 1e3:.1f} mV) of EndcapX")
        except Exception:
            print("[TRACK] setup failed after the camera was armed: releasing the camera")
            self._track_release_camera()
            raise

    # ------------------------------------------------------------------------------------------
    # camera release (same logic as the stand-alone scripts)
    # ------------------------------------------------------------------------------------------
    @kernel
    def track_camera_pulses(self, n):
        self.core.reset()
        self.ttl4.output()
        delay(1 * ms)
        self.ttl4.off()
        self.ttl6.off()
        delay(5 * ms)
        for _ in range(n):
            self.ttl4.on()
            self.ttl6.on()
            delay(2 * ms)
            self.ttl4.off()
            # self.ttl6.off()
            delay(13 * ms)

    def track_release_camera(self):
        """Stop an armed acquisition: the abort request goes out in a background thread; while the camera does not answer
        (its acquisition thread is blocked waiting for a trigger), bursts of trigger pulses are sent. Returns when it answered."""
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
            print("[TRACK] camera did not answer the abort: sending trigger pulses (round %d)" % rounds)
            try:
                self.track_camera_pulses(20)
            except Exception as e:
                print("[TRACK] track_camera_pulses failed:", repr(e))
                break
            th.join(0.6)
        if th.is_alive():
            print("[TRACK] WARNING: camera still not released; pulse ttl4 by hand / restart the camera GUI")
        elif res.get("err"):
            print("[camera] abort failed:", res["err"])
        else:
            print("[TRACK] camera released" + (" after %d pulse round(s)" % rounds if rounds else ""))
        self._camera_closed = True

    _track_release_camera = track_release_camera

    def _track_fetch_worker(self, res, completed):
        for attempt in range(2):
            try:
                res["reply"] = self._camera_request(self.fetch_msg(completed), timeout=180)
                res.pop("err", None)
                return
            except ConnectionError as e:
                res["err"] = e
                print(f"[TRACK] camera connection dropped during the fetch ({e!r}); asking again" if attempt == 0 else
                      f"[TRACK] camera connection dropped again ({e!r})")
                time.sleep(1.0)
            except Exception as e:
                res["err"] = e
                return

    @rpc
    def track_end_scan(self):
        """Called from the END of krun: starts the camera fetch in a background thread and returns at once."""
        import threading
        self._tr_fetch_res = {}
        self._tr_fetch_thread = threading.Thread(target=self._track_fetch_worker, args=(self._tr_fetch_res, True),
                                                 daemon=True)
        self._tr_fetch_thread.start()
        print(
            f"[TRACK] end of scan: camera fetch started, {KICK_PULSES} trigger pulses follow to release the camera (about {KICK_PULSES * 15e-3:.1f} s)")

    def track_fetch_with_kick(self, completed):
        """Use in cameraCOMM_postscan instead of the plain fetch request."""
        import threading
        th = getattr(self, "_tr_fetch_thread", None)
        if th is None:
            res = {}
            th = threading.Thread(target=self._track_fetch_worker, args=(res, completed), daemon=True)
            th.start()
            print(
                f"[TRACK] ending the scan: {KICK_PULSES} trigger pulses to release the camera (about {KICK_PULSES * 15e-3:.1f} s)")
            self.track_camera_pulses(KICK_PULSES)
        else:
            res = self._tr_fetch_res
        rounds = 0
        while th.is_alive() and rounds < 10:
            rounds += 1
            print(f"[TRACK] camera still not answering: more trigger pulses (round {rounds})")
            self.track_camera_pulses(20)
            th.join(0.5)
        th.join(0.5)
        self._tr_fetch_thread = None
        if "err" in res:
            raise res["err"]
        return res.get("reply")

    # ------------------------------------------------------------------------------------------
    # kernels
    # ------------------------------------------------------------------------------------------
    @kernel
    def track_measure(self, n_frames, bright):
        """Put the N ion ROIs on their 'first' positions (slots 0..N-1) and the N extra slots on the 'second' positions (slots N..2N-1),
        read n_frames, put the ROIs back and re-open the gate for the main experiment. Frames go to self.tbuf_all (2N values per frame:
        the N 'first' sums, then the N 'second' sums)."""
        nb = self.t_nb
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        for j in range(self.n_roi):
            self.grabber0.setup_roi(j, self.tr_a_x0[j], self.tr_a_y0[j], self.tr_a_x1[j], self.tr_a_y1[j])
            self.grabber0.setup_roi(self.n_roi + j, self.tr_b_x0[j], self.tr_b_y0[j], self.tr_b_x1[j], self.tr_b_y1[j])
        self.grabber0.gate_roi(self.tr_mask)
        self.core.break_realtime()                           # as take_frames of the stand-alone scripts: ROI/gate writes settle first
        if bright:
            self.urukul0_ch1.sw.on()
            self.ttl6.on()
            delay(self.track_cool_time)
        else:
            self.urukul0_ch1.sw.off()
            self.ttl6.on()
            delay(2 * ms)
        for f in range(n_frames):
            self.ttl4.on()
            self.ttl6.on()                                   # camera trigger; exposure = pulse width (trigger mode 7)
            delay(self.track_exposure)
            self.ttl4.off()
            delay((self.track_frame_period - self.track_exposure) / 2.0)
            # self.ttl6.off()
            delay((self.track_frame_period - self.track_exposure) / 2.0)
            self.grabber_read_guarded(self.tbuf, self.grabber_timeout, 1000000 + self.tr_frame_counter + f)
            self.core.break_realtime()
            for j in range(nb):
                self.tbuf_all[nb * f + j] = self.tbuf[j]
            if f % 5 == 4 and f < n_frames - 1:              # termination check every 5 frames (an event lasts ~0.4 s)
                if self.track_should_stop():
                    self.tr_aborted = True
                    break
                self.core.break_realtime()
        self.tr_frame_counter += n_frames

    @kernel
    def track_restore(self):
        """The N ion ROIs back on their GUI boxes, gate as the main experiment needs it, Doppler on (also after an error)."""
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        for k in range(self.n_roi):
            self.grabber0.setup_roi(k, self.roi_x0[k], self.roi_y0[k], self.roi_x1[k], self.roi_y1[k])
        self.grabber0.gate_roi(self.roi_mask)
        self.urukul0_ch1.sw.on()

    @kernel
    def track_hw_init(self, dfreq, damp):
        """Only before scan point 0 (ON() initialises the Doppler DDS and the TTL directions only when it runs point 0):
        the same lines as ON(), so the very first tracking event can use the Doppler beam and the camera trigger."""
        self.core.break_realtime()
        self.urukul0_cpld.init()
        delay(10 * ms)
        self.urukul0_ch1.init()
        self.urukul0_ch1.set_att(0 * dB)
        self.urukul0_ch1.set(frequency=dfreq, amplitude=damp, phase_mode=2)
        self.urukul0_ch1.sw.on()
        self.ttl4.output()
        self.ttl4.off()
        self.ttl6.output()
        # self.ttl6.off()
        self.zotino0.init()               # ON() does this at every point; here only for the very first event
        delay(2 * ms)

    @kernel
    def track_apply_dc(self, newEndcapX, newAllY):
        """The electrode part of ON()'s DC block (same lines, same order; the piezo channels are NOT written), then a settling
        time with the Doppler beam on. ONLY EndcapX and AllY are moved.
        Called with the scan point's own EndcapX (+ the correction) and AllY."""
        self.core.break_realtime()
        self.urukul0_ch1.sw.on()
        for i in range(12):
            self.modDCElectrodeValues[i] = self.originalDCElectrodeValues[i]
        newX = newEndcapX - self.originalEndcapX
        newY = newAllY - self.originalAllY
        self.EndcapX(newX)
        self.AllY(newY)
        self.core.break_realtime()
        for i in range(12):
            ind = self.DCElectrodeMapping[i]
            self.zotino0.write_dac(self.DCElectrodeMapping[i], self.modDCElectrodeValues[ind])
        self.zotino0.load()
        delay(10 * ms)
        delay(self.tr_settle)

    @kernel
    def track_event(self, ev, pt, dv, first, xb, yb, dfreq, damp):
        """Tracking event BEFORE scan point pt: detect -> correct -> detect ... until the ions are inside the band
        or track_max_iter detections were made. xb... = the scan point's own DC values (EndcapX WITHOUT the correction).
        Returns the EndcapX correction (V) to use from this point on. Whatever happens inside (e.g. a Grabber timeout),
        the Doppler beam is switched back on and the ROIs restored."""
        newdv = dv
        st = 0
        it = 0
        done = False
        self.tr_aborted = False
        if self.track_should_stop():      # termination requested: skip the whole event, the scan loop exits at its next check
            self.tr_aborted = True
            return dv
        self.core.break_realtime()
        if first:
            self.track_hw_init(dfreq, damp)
            # the scan's own DC state (ON() has not written it yet): the first detections and the probe must see the real configuration
            self.track_apply_dc(xb + dv, yb)
        delay(self.track_frame_period)             # the camera is done with the last frame of the previous point before the first trigger
        try:
            while (not done) and it < self.track_max_iter:
                if it > 0 and self.track_should_stop():
                    self.tr_aborted = True
                    done = True
                else:
                    if it == 0 and self.track_dark_frames > 0:
                        self.track_measure(self.track_dark_frames, False)
                        if not self.tr_aborted:
                            self.host_track_dark(self.tbuf_all, self.track_dark_frames)
                        self.core.break_realtime()
                    if not self.tr_aborted:
                        self.track_measure(self.track_frames, True)
                    if self.tr_aborted:
                        done = True
                    else:
                        newdv = self.host_track(ev, pt, it, self.tbuf_all, self.track_frames)
                        st = self.host_track_status()
                        if st == 4:  # ions lost: leave the event and let the scan loop exit
                            self.tr_aborted = True
                            done = True
                        elif st == 2 and it + 1 < self.track_max_iter:  # correct: the DC change goes out now, then the next detection
                            self.track_apply_dc(xb + newdv, yb)
                        elif st != 1:  # 0 = in band, 3 = give up
                            done = True
                        it += 1
        finally:
            self.track_restore()
        self.core.break_realtime()
        return newdv

    @kernel
    def track_end_pulses(self):
        self.core.break_realtime()
        self.grabber0.gate_roi(0)
        self.ttl4.off()
        # self.ttl6.off()
        delay(5 * ms)
        for _ in range(self.track_kick):
            self.ttl4.on()
            delay(2 * ms)
            self.ttl4.off()
            delay(13 * ms)
        self.core.break_realtime()

    @kernel
    def track_pad_camera(self, n):
        """Fallback if Camera.py insists on its exact frame count: n unused triggers, Grabber gate closed (nothing is read)."""
        self.core.reset()
        self.grabber0.gate_roi(0)
        self.track_camera_pulses(n)
        self.core.break_realtime()
        self.grabber0.gate_roi(self.roi_mask)

    def track_pad_camera_frames(self):
        """Call after the scan, before cameraCOMM_postscan, ONLY if Camera.py was not patched to accept fewer frames."""
        missing = int(self.track_extra_frames - self.t_frames_taken)
        if self.trackIon and missing > 0:
            print(f"[TRACK] padding the camera with {missing} unused triggers")
            self.track_pad_camera(missing)

    # ------------------------------------------------------------------------------------------
    # host side
    # ------------------------------------------------------------------------------------------
    @rpc
    def track_should_stop(self) -> TBool:
        """True if a termination was requested (same test as the other scripts: check_termination, else check_pause)."""
        stop = False
        if hasattr(self, "should_stop"):                      # the main experiment's own check, if it has one (same behaviour)
            try:
                stop = bool(self.should_stop())
            except Exception:
                stop = False
        else:
            try:
                stop = bool(self.scheduler.check_termination(self.scheduler.rid))
            except Exception:
                try:
                    stop = bool(self.scheduler.check_pause())
                except Exception:
                    stop = False
        if stop and not getattr(self, "_track_stop_said", False):
            self._track_stop_said = True
            print("[TRACK] termination requested: leaving the tracking event")
        return stop

    @rpc(flags={"async"})
    def host_track_dark(self, buf, n):
        self.frame_log(n, 0, self.t_ev_cur + 1)
        self.t_frames_taken += int(n)
        self.track_frames_taken = self.t_frames_taken
        a = np.array(buf, dtype=float).reshape(-1, self.t_nb)[: int(n)]
        self.t_dark = float((a / self.t_npix).mean())
        msg = f"[TRACK] dark level: {self.t_dark:.1f} counts/px"
        if self.t_dark_ref is None:
            self.t_dark_ref = self.t_dark
            msg += " (reference for this run)"
        else:
            msg += f" (first event {self.t_dark_ref:.1f}, difference {self.t_dark - self.t_dark_ref:+.1f})"
        print(msg)
        if abs(self.t_dark - self.t_dark_ref) > 5:
            print("[TRACK WARNING] bias level changed during the run: camera temperature, EM gain or ambient light")

    @rpc
    def host_track_status(self) -> TInt32:
        """0 = event finished (in band, or measure-only), 1 = detect again without changing anything, 2 = the correction
        returned by host_track was applied: detect again, 3 = give up (lost / cannot move / out of band at the last detection)."""
        return 4 if self.t_lost_stop else int(self.t_status)

    def _track_probe_step(self, v_cur):
        """Size of the probe step (V): PROBE_PX camera pixels, within track_max_step_mV and the excursion limit."""
        step, dev = self.t_ctl
        vpp = self.track_volts_per_pixel
        dv = PROBE_PX * vpp if vpp > 0 else PROBE_V
        return float(max(1e-4, min(dv, step, dev - abs(v_cur))))

    def _track_learn(self, s0):
        """The probe has measured s0 (dP per V of the average imbalance): band, gains, fresh controller memory."""
        self.t_s0 = float(s0)
        vpp = self.track_volts_per_pixel
        self.t_band_dP = self.track_band_px * vpp * abs(self.t_s0) if vpp > 0 else 0.0
        kp, ki = (float(getattr(self, k, 0.0)) * 1e-3 for k in ("track_Kp_mV", "track_Ki_mV"))
        auto = ki <= 0
        if auto:
            ki = AUTO_LOOP_GAIN / abs(self.t_s0)
        self.t_gains = (kp, ki)
        self.t_pid = {"e1": None}
        self.t_ehist = []
        print(f"[TRACK] slope of the average imbalance: {self.t_s0 * 1e-3:+.4f} dP per mV; deadband {self.track_band_px:.3f} px = {self.t_band_dP:.4f} in dP"
              f"{'; every ion also within %g bands of its own setpoint' % IND_BAND_FACTOR if self.t_n_ion > 1 else ''}")
        print(f"[TRACK] gains Kp = {kp * 1e3:.2f}, Ki = {ki * 1e3:.2f}{' (auto)' if auto else ''}, mV per unit dP "
              f"-> dimensionless loop gains Kp = {kp * abs(self.t_s0):.2f}, Ki = {ki * abs(self.t_s0):.2f}")

    # ------------------------------------------------------------------------------------------
    # THE CORRECTION MECHANISM (edit here): band, gate, median filter, PID step
    # ------------------------------------------------------------------------------------------
    def track_decide(self, e, e_err, v_cur, s0, last, e_all=None):
        step, dev = self.t_ctl
        sgn = 1.0 if s0 >= 0 else -1.0
        band_dP = min(max(self.t_band_dP, BAND_SIGMA * (e_err if np.isfinite(e_err) else 0.0)), BAND_MAX_DP)
        in_mean = abs(e) <= band_dP
        spread_ok = True if e_all is None else bool(
            np.all(np.abs(np.asarray(e_all, dtype=float)) <= IND_BAND_FACTOR * band_dP))
        in_band = in_mean and spread_ok
        v_new = v_cur

        if not self.track_correct:
            what = "in band" if in_band else (
                "OUT of band (measure only)" if spread_ok else "OUT of band: the ions disagree (measure only)")
            return 0, v_new, in_band, band_dP, e, what

        # class of this detection: 0 in band, +1 / -1 out of band (high / low), 9 average fine but the ions disagree
        cls = 0 if in_band else (9 if in_mean else (1 if e > 0 else -1))

        if not self.t_votes:  # no vote running
            if cls == 0:
                if self.t_ev_out and self.t_confirm < CHECK_TIMES and not last:
                    self.t_confirm += 1
                    return 1, v_new, in_band, band_dP, e, f"in band after a correction: confirming ({self.t_confirm}/{CHECK_TIMES})"
                return 0, v_new, in_band, band_dP, e, "in band" + (
                    f" (confirmed {CHECK_TIMES}x)" if self.t_ev_out else "")
            if cls == 9:
                self.t_ev_out, self.t_confirm = True, 0
                return 1, v_new, in_band, band_dP, e, (
                            "the ions disagree (one is beyond %g x band, the average is fine): looking again" % IND_BAND_FACTOR)
            self.t_ev_out, self.t_confirm = True, 0  # first out-of-band detection: the vote starts with it

        self.t_votes.append((cls, float(e)))
        n = len(self.t_votes)
        n_in = sum(1 for c, _ in self.t_votes if c == 0)
        n_hi = sum(1 for c, _ in self.t_votes if c == 1)
        n_lo = sum(1 for c, _ in self.t_votes if c == -1)

        if n_in >= VOTE_MAJ:  # majority in band: the out-of-band detection was a fluke
            self.t_votes = []
            return 0, v_new, in_band, band_dP, e, f"vote: {n_in} of {n} in band, no correction"
        side = 1 if n_hi >= VOTE_MAJ else (-1 if n_lo >= VOTE_MAJ else 0)
        if side == 0:
            if n >= VOTE_N or last:  # split vote (or no detections left): leave the DC alone
                self.t_votes = []
                return 0, v_new, in_band, band_dP, e, f"vote: no majority in {n} detections (high {n_hi}, low {n_lo}, in {n_in}), no correction"
            return 1, v_new, in_band, band_dP, e, f"out of band: vote {n}/{VOTE_N} (high {n_hi}, low {n_lo}, in {n_in})"

        e_corr = float(np.mean([v for c, v in self.t_votes if c == side]))  # mean of the majority only
        dvp, pidc = track_pid(self.t_pid, e_corr, *self.t_gains)
        dv_pid = sgn * dvp
        self.t_pidc = tuple(sgn * c for c in pidc)
        v_try = max(-dev, min(dev, v_cur + max(-step, min(step, dv_pid))))
        n_maj = n_hi if side == 1 else n_lo
        self.t_votes = []
        if abs(v_try - v_cur) < 1e-7:
            return 3, v_new, in_band, band_dP, e_corr, "OUT of band, correction at its limit: giving up"
        v_new = v_try
        self.t_confirm = 0
        what = f"vote: {n_maj} of {n} out of band on the same side: correcting by the mean of those" + (
            " (last detection, not verified)" if last else "")
        return 2, v_new, in_band, band_dP, e_corr, what

    @rpc
    def host_track(self, ev, pt, it, buf, n) -> TFloat:
        """Evaluate one detection of tracking event ev. The controller works on the brightness imbalance dP itself:
        e = mean over the ions of (dP_i - dP_set_i) is nulled, so there is no curve inversion and no clipping, and the sign of e
        gives the direction. The very first detections of the run set up the tracker: setpoints (the ions' positions at the start),
        then a probe step of EndcapX whose response gives the slope s0 (sign and size), then the step is undone. Returns the EndcapX
        correction (V, relative to the GUI value); the decision for the kernel is in host_track_status()."""

        if self.t_probe_fail:             # the previous detection found no probe response and stepped back: now stop the run
            self.frame_log(n, 0, int(ev))
            raise RuntimeError("[TRACK] the EndcapX probe produced no clear response of the ion imbalance. The ions are not on the "
                               "sensitive part of their ROI pairs (centre the ROIs on the ions), the camera does not see them, "
                               "track_along is wrong, or EndcapX does not move them. Check the camera image and the Tracking.EndcapX_* "
                               "datasets of this run.")
        if self.t_t0 is None:
            self.t_t0 = time.time()
        t = time.time() - self.t_t0
        ev, pt, it = int(ev), int(pt), int(it)
        if ev != self.t_ev_cur:                                   # new event
            if self.t_ev_pt is not None and pt == self.t_ev_pt:
                print(f"[TRACK WARNING] event {ev + 1} starts before the SAME scan point {pt} as the previous event: "
                      f"track_event is called twice per point in krun")
            self.t_ev_cur, self.t_ev_n, self.t_ev_pt = ev, 0, pt
            self.t_ev_out, self.t_confirm, self.t_votes = False, 0, []
        self.t_ev_n += 1
        self.t_frames_taken += int(n)
        self.track_frames_taken = self.t_frames_taken
        last = (it >= self.track_max_iter - 1)
        nI = self.t_n_ion
        raw = np.array(buf, dtype=float).reshape(-1, self.t_nb)[: int(n)]
        stats = ions_stats(raw, self.t_npix, self.t_dark, nI)
        S_i = np.array([q[2] for q in stats])                     # (first + second) counts/px of every ion
        dP_i = np.array([q[3] for q in stats])                    # imbalance of every ion
        err_i = np.array([q[4] for q in stats])
        S = float(np.mean(S_i))
        dP = float(np.mean(dP_i))
        err = float(np.sqrt(np.sum(err_i ** 2)) / nI) if np.all(np.isfinite(err_i)) else float('nan')
        v_cur = self.t_dv
        min_sig = MIN_SIGNAL if self.track_dark_frames > 0 else MIN_COUNTS_NODARK
        lost = not (np.all(np.isfinite(dP_i)) and np.all(np.isfinite(S_i)) and np.all(S_i >= min_sig))
        self.t_lost_n = self.t_lost_n + 1 if lost else 0
        if lost and LOST_STOP_N > 0 and self.t_lost_n >= LOST_STOP_N:
            self.t_lost_stop = True
            print(f"[TRACK ERROR] ion signal [" + ", ".join(
                f"{x:.0f}" for x in S_i) + f"] counts/px is below {min_sig:g} "
                                           f"({'bias subtracted' if self.track_dark_frames > 0 else 'raw, no dark frames'}) in {self.t_lost_n} consecutive detections: "
                                           f"the ions are lost, stopping the experiment")
        nan = float('nan')
        # ---- set-up: latch the setpoints from the first detections (no correction in between) ----
        latching = start_probe = False
        if not lost and not self.t_sp_set:
            for i in range(nI):
                self.t_latch[i].append(float(dP_i[i]))
            n_lat = len(self.t_latch[0])
            if n_lat < LATCH_SKIP + LATCH_DET:
                latching = True
                print(f"[TRACK] setpoints: collecting the first {LATCH_DET} detections ({max(0, n_lat - LATCH_SKIP)}/{LATCH_DET}; first {LATCH_SKIP} are skipped as start-up transient), no correction yet")
            else:
                self.t_sp_dP = np.array([float(np.median(self.t_latch[i][LATCH_SKIP:])) for i in range(nI)])
                self.t_sp_set = True
                self.t_Scal = S
                start_probe = True
                print(f"[TRACK] setpoints: the ions are held where they start, dP = [" + ", ".join(f"{x:+.3f}" for x in self.t_sp_dP) +
                      f"] (median of the first {LATCH_DET} detections), sum = {S:.3g} counts/px")
                self.set_dataset("Tracking.setpoint_dP", self.t_sp_dP, broadcast=True, archive=True, persist=True)
        have_sp = self.t_sp_set and not lost
        e_i = (dP_i - self.t_sp_dP) if have_sp else np.full(nI, nan)     # the imbalance of every ion relative to its setpoint
        e = float(np.mean(e_i)) if have_sp else nan                      # the average: the imbalance to null
        # error bar for the plot: from the frames (k >= 2), else from the scatter of the ions around their setpoints (one frame, N >= 2)
        err_plot = err
        err_kind = 1 if np.isfinite(err) else 0               # 1 = frame statistics, 2 = scatter of the ions, 0 = none
        if have_sp and not np.isfinite(err_plot) and nI >= 2:
            err_plot = float(np.std(e_i, ddof=1) / np.sqrt(nI))
            err_kind = 2
        if err_kind == 0 and have_sp and not getattr(self, "_t_noerr_said", False):
            self._t_noerr_said = True
            print("[TRACK] no error bar: one frame and one ion give no statistics. Use track_frames >= 2 (or more than one ion).")
        e_err = err if np.isfinite(err) else nan
        band_dP = band = nan
        in_band = False
        e_med = nan
        self.t_pidc = (nan,) * 2
        v_new = v_cur
        status = 0
        what = ""
        if lost:
            status, what = 3, "LOST: no signal on at least one ion, unchanged"
            if self.t_probe_pending:      # the probe response was lost: undo the step and start the set-up again at the next event
                v_new = self.t_probe_v0
                self.t_probe_pending = False
                self.t_sp_set = False
                self.t_latch = [[] for _ in range(nI)]
                what += "; probe abandoned, step undone, set-up restarts"
        elif latching:
            status, what = 1, "setpoint collection"
        elif start_probe:                 # setpoints fixed: step EndcapX and look at the response
            dvp = self._track_probe_step(v_cur)
            self.t_probe_v0, self.t_probe_dv, self.t_probe_pending = v_cur, dvp, True
            v_new, status = v_cur + dvp, 2
            what = f"probe: EndcapX {dvp * 1e3:+.1f} mV to measure the response (stepped back right after)"
        elif self.t_probe_pending:        # e is now the response to the probe step
            dvp = self.t_probe_dv
            self.t_probe_pending = False
            v_new, status = self.t_probe_v0, 2           # undo the step in any case (the verification follows at the next detection)
            thr = max(PROBE_SNR * (e_err if np.isfinite(e_err) else 0.0), PROBE_MIN_DP)
            if abs(e) >= thr:
                self._track_learn(e / dvp)
                what = f"probe response: dP moved {e:+.3f} for {dvp * 1e3:+.1f} mV; stepping back"
            else:
                self.t_probe_fail = True
                what = (f"PROBE FAILED: dP moved only {e:+.4f} for {dvp * 1e3:+.1f} mV (needs {thr:.3f}); stepping back, "
                        f"the run stops at the next detection")
                print(f"[TRACK ERROR] {what}")
        else:
            status, v_new, in_band, band_dP, e_med, what = self.track_decide(e, e_err, v_cur, self.t_s0, last, e_i)   # <- the correction mechanism
            band = band_dP / abs(self.t_s0)
        known = self.t_s0 is not None
        s0 = self.t_s0 if known else nan
        resid = e / s0 if (known and np.isfinite(e)) else nan      # display: linearised offset from the setpoint (V)
        resid_err = err_plot / abs(s0) if known else nan
        drift = resid - v_cur                                       # offset the ions would have without any correction
        spread = (float(np.max(e_i) - np.min(e_i)) / abs(s0)) if (known and have_sp) else nan   # V: how far the ions disagree
        self.frame_log(n, 2 if (status == 0 and in_band) else 0, ev)
        flag = 2 if lost else 0
        self.t_dv = v_new
        self.t_status = status
        ok_end = bool(in_band) if status in (0, 3) else False
        self.t_ev_info[ev] = [pt, float(v_new), ok_end, self.t_ev_n]
        vals = {"t": t, "ev": float(ev), "it": float(it), "pt": float(pt), "dP": dP, "dP_err": err_plot, "err_kind": float(err_kind), "S": S, "e_dP": e,
                "band_dP": band_dP, "resid_mV": resid * 1e3,
                "resid_err_mV": resid_err * 1e3, "V_mV": v_cur * 1e3, "drift_mV": drift * 1e3, "flag": float(flag),
                "band_mV": band * 1e3, "inband": float(in_band), "status": float(status), "spread_mV": spread * 1e3,
                "pid_p_mV": -self.t_pidc[0] * 1e3, "pid_i_mV": -self.t_pidc[1] * 1e3}
        if nI > 1:                                                  # per-ion columns (with one ion they would repeat the averages)
            for i in range(nI):
                vals[f"dP{i}"] = float(dP_i[i])
                vals[f"e{i}_dP"] = float(e_i[i])
                vals[f"resid{i}_mV"] = float(e_i[i]) / s0 * 1e3 if known else nan
        if self.track_volts_per_pixel > 0:
            vals.update({"resid_px": resid / self.track_volts_per_pixel, "resid_err_px": resid_err / self.track_volts_per_pixel,
                         "V_px": v_cur / self.track_volts_per_pixel, "drift_px": drift / self.track_volts_per_pixel, "band_px": band / self.track_volts_per_pixel,
                         "spread_px": spread / self.track_volts_per_pixel})
            for i in range(nI):
                vals[f"drift_px{i}"] = (float(e_i[i]) / s0 - v_cur) / self.track_volts_per_pixel
        self.t_rec.append(vals)
        first = (self.t_n == 0)
        self.t_n += 1
        for key, v in vals.items():       # whole numpy arrays, not lists: the applets (pyqtgraph ErrorBarItem: height / 2.) need arrays
            col = self.t_cols.setdefault(key, [])
            col.append(float(v))
            self.set_dataset(f"Tracking.EndcapX_{key}", np.array(col), broadcast=True, archive=True)
        if first:
            rid = getattr(self.scheduler, "rid", "Local")
            u = "px" if self.track_plot_px else "mV"
            ylab = (f"EndcapX offset [camera px] (1 px = {self.track_volts_per_pixel * 1e3:.3g} mV)" if self.track_plot_px else "EndcapX [mV]")
            if nI > 1:
                ylab = "mean " + ylab
            what_t = ("every detection; red line = correction in force" if self.track_correct
                      else "NO correction (track only): points = ion offset, red line = 0")
            P = "Tracking.EndcapX_"
            if CUSTOM_APPLET:      # ion_tracking_applet.py installed in the artiq/applets: launched like the stock applets
                cmd = (f"${{artiq_applet}}ion_tracking_applet {P}resid_{u} --x {P}t --error {P}resid_err_{u} --fit {P}V_{u} "
                       f"--band {P}band_{u} --status {P}status --inband {P}inband --x-label 'time [s]' "
                       f"--y-label '{ylab}' --title 'RID {rid} ion tracking ({nI} ion{'s' if nI > 1 else ''}), {what_t}'")
            else:
                cmd = (f"${{artiq_applet}}plot_xy {P}resid_{u} --x {P}t --error {P}resid_err_{u} --fit {P}V_{u} --x-label 'time [s]' "
                       f"--y-label '{ylab}' --title 'RID {rid} ion tracking ({nI} ion{'s' if nI > 1 else ''}), {what_t}'")
            print(f"[TRACK] applet command: {cmd}")
            self.ccb.issue("create_applet", "Ion tracking", cmd)
        ion_txt = (" [ions e: " + " ".join(f"{x:+.3f}" for x in e_i) + "]") if nI > 1 else ""
        print(f"[TRACK] event {ev + 1} (before point {pt}) detection {it + 1}/{self.track_max_iter}: sum = {S:.3g} (start {self.t_Scal:.3g}), "
              f"dP = {dP:+.3f} +- {err_plot:.3f}, imbalance e = {e:+.3f} (median {e_med:+.3f}, band +-{band_dP:.3f}){ion_txt} = offset {resid * 1e3:+.2f} +- {resid_err * 1e3:.2f} mV, "
              f"correction {v_cur * 1e3:+.2f} -> {v_new * 1e3:+.2f} mV: {what}")
        return float(v_new)

    def track_analyze(self):
        """Call from analyze(): summary + per-point record."""
        if not getattr(self, "trackIon", False) or not self.t_rec:
            return
        evs = sorted(self.t_ev_info)
        n_pts = int(getattr(self, "n_points_expected", 0))
        dv_pt = np.zeros(n_pts)
        ok_pt = np.zeros(n_pts)
        for p in range(n_pts):
            cur = [e for e in evs if self.t_ev_info[e][0] <= p]
            if cur:
                info = self.t_ev_info[cur[-1]]
                dv_pt[p], ok_pt[p] = info[1] * 1e3, float(info[2])
        self.set_dataset("Tracking.event_pt", np.array([self.t_ev_info[e][0] for e in evs], dtype=float), broadcast=True, archive=True)
        self.set_dataset("Tracking.event_ok", np.array([float(self.t_ev_info[e][2]) for e in evs]), broadcast=True, archive=True)
        self.set_dataset("Tracking.event_dv_mV", np.array([self.t_ev_info[e][1] * 1e3 for e in evs]), broadcast=True, archive=True)
        self.set_dataset("Tracking.event_detections", np.array([float(self.t_ev_info[e][3]) for e in evs]), broadcast=True, archive=True)
        self.set_dataset("Tracking.point_dv_mV", dv_pt, broadcast=True, archive=True, persist=True)
        self.set_dataset("Tracking.point_ok", ok_pt, broadcast=True, archive=True, persist=True)
        ok_after, off_after = self.track_point_after()
        self.set_dataset("Tracking.point_after_ok", ok_after, broadcast=True, archive=True, persist=True)
        self.set_dataset("Tracking.point_after_offset_mV", off_after, broadcast=True, archive=True, persist=True)
        good = [q for q in self.t_rec if q["flag"] != 2 and np.isfinite(q["resid_mV"])]
        first_det = np.array([q["resid_mV"] for q in good if q["it"] == 0])
        last_det = np.array([[q for q in good if q["ev"] == e][-1]["resid_mV"] for e in evs if any(q["ev"] == e for q in good)])
        s = {"ions": int(self.t_n_ion), "correct": bool(self.track_correct), "every_n": int(self.track_every_n), "events": len(evs),
             "detections": len(self.t_rec), "detections_per_event": float(len(self.t_rec)) / max(len(evs), 1),
             "events_not_in_band": int(sum(1 for e in evs if not self.t_ev_info[e][2])),
             "slope_dP_per_mV": float(self.t_s0 * 1e-3) if self.t_s0 is not None else float('nan'),
             "lost": int(sum(q["flag"] == 2 for q in self.t_rec)),
             "points_out_after": int(np.sum(ok_after == 0)), "points_in_after": int(np.sum(ok_after == 1))}
        if len(first_det) > 1:
            s["offset_first_rms_mV"] = float(np.sqrt(np.mean(first_det ** 2)))
        if len(last_det) > 1:
            s["offset_final_rms_mV"] = float(np.sqrt(np.mean(last_det ** 2)))
        if self.t_n_ion > 1:
            sp = np.array([q["spread_mV"] for q in good], dtype=float)
            if sp.size:
                s["ion_spread_mean_mV"] = float(np.nanmean(sp))
        self.set_dataset("Tracking.summary", json.dumps(s), archive=True, persist=True)
        print("\n" + "=" * 64)
        print("[TRACK] summary: " + ", ".join(f"{k} = {v:.4g}" if isinstance(v, float) else f"{k} = {v}" for k, v in s.items()))
        print("[TRACK]   offset_first_rms = offset at the first detection of each event (what the point would have seen without the loop),")
        print("[TRACK]   offset_final_rms = offset at the last detection (what the scan points saw); Tracking.point_ok = 1 where the ions were in band")
        print("=" * 64 + "\n")

        self.track_recover_if_lost()

    def track_recover_if_lost(self):
        """After an experiment stopped because the ions were lost: record it and submit the recovery script."""
        if not getattr(self, "t_lost_stop", False):
            return
        self.set_dataset("Tracking.ions_lost", True, broadcast=True, archive=True)
        if not RECOVERY_ON_LOST:
            print("[TRACK] ions lost: automatic recovery is disabled (RECOVERY_ON_LOST = False)")
            return
        if getattr(self, "_recovery_submitted", False):
            return
        self._recovery_submitted = True
        expid = {"file": "Experiments/ion_chain_recovery.py",
                 "class_name": "RecoverySchedule",
                 "arguments": {},
                 "log_level": 0,
                 "repo_rev": self.scheduler.expid["repo_rev"]}
        rid = self.scheduler.submit("main", expid, RECOVERY_PRIORITY)
        print(f"[TRACK] ions lost: recovery script submitted (RID {rid})")

    def track_point_after(self):
        """Per scan point: was the first detection AFTER the point (first detection of the next tracking event) in band?
        1 = in band, 0 = out of band, nan = unknown (no event after the point, e.g. the last point, or the signal was lost).
        Also returns the offset (mV) of that detection."""
        n_pts = int(getattr(self, "n_points_expected", 0))
        first_det = {}
        for q in self.t_rec:
            if int(q["it"]) == 0 and int(q["ev"]) not in first_det:
                first_det[int(q["ev"])] = q
        evs = sorted((int(q["pt"]), e) for e, q in first_det.items())     # (scan point the event precedes, event)
        ok, off = np.full(n_pts, np.nan), np.full(n_pts, np.nan)
        for p in range(n_pts):
            nxt = [e for (pt, e) in evs if pt > p]
            if nxt:
                q = first_det[nxt[0]]
                if q["flag"] != 2 and np.isfinite(q["e_dP"]):
                    ok[p], off[p] = float(q["inband"]), q["resid_mV"]
        return ok, off