from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QTimer, Qt
from oitg.results import find_results
from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
from pyqtgraph.dockarea import *
import sys  # We need sys so that we can pass argv to QApplication
import numpy as np
import os
from ndscan.experiment import *
from oitg import *
import time
from oitg.results import *
from oitg.fitting import *
from lmfit import Model, Parameters
import numpy as np
from scipy.special import genlaguerre
import scipy.special as sp
import sympy
import matplotlib
# %matplotlib tk
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import scipy.optimize
import pylab as plt
import pickle
import json
# from mpl_interactions import ioff, panhandler, zoom_factory
import oitg
import matplotlib.ticker as mticker




class FitObject:

    def __init__(self):
        self.num_params=0
        self.cols=6
        # below parameter will be changed in the form of a table
        #Format: [ <bool for fit enabling>, <fitparam>, <initial value>, < fit value>, <min_fit value>, <max_fit value> ]
        self.params2Dlist=[[True,"A",0,0.1, -1,1]]*self.num_params

    def fitFunction(self, x,a,b):
        return a*x+b

    # 26/01/06 gt
    def guess_parameters(self, x, y, x_label=""):
        """
        Base method for parameter guessing.
        Overridden by child classes to provide intelligent guesses.
        """
        pass

    # 26/01/06 gt
    def _set_param(self, name, value):
        """Helper to safely set a parameter's initial value in the list."""
        for row in self.params2Dlist:
            if row[1] == name:
                row[2] = value
                break

    # 26/01/06 gt
    def activateFit(self, xvals, yvals):
        # 1. Setup Model
        self.mdl = Model(self.fitFunction)
        self.fitparams = Parameters()

        for i in range(self.num_params):
            # This strictly trusts the values currently in self.params2Dlist
            param_name = self.params2Dlist[i][1]
            initial_val = self.params2Dlist[i][2]
            min_val = self.params2Dlist[i][4]
            max_val = self.params2Dlist[i][5]
            vary_bool = self.params2Dlist[i][0]

            self.fitparams.add(param_name,
                               value=initial_val,
                               min=min_val,
                               max=max_val,
                               vary=vary_bool)

        # 2. Perform Fit
        # 'nan_policy' handles missing data points gracefully
        self.fitres = self.mdl.fit(yvals, self.fitparams, x=xvals, nan_policy='omit')

        # 3. Update the list with results
        for i in range(self.num_params):
            param_name = self.params2Dlist[i][1]
            self.params2Dlist[i][3] = self.fitres.params[param_name].value

        print(self.fitres.fit_report())
        return self.fitres.best_fit, self.params2Dlist

    def functionVal(self, xvals):
        arglist_val=tuple([self.params2Dlist[i][2] for i in range(self.num_params)])
        return self.fitFunction(xvals, *arglist_val)


class lineFit(FitObject):
    def __init__(self):
        super(lineFit, self).__init__()
        self.num_params = 2
        self.params2Dlist= [
                            [True,"A",1,0.1, -np.inf,np.inf],
                            [True,"B",0,0.1, -np.inf,np.inf]
                            ]
        self.description="A*x+B"

    def fitFunction(self, x, A,B):
        return A*x+B

    # 26/01/06 gt
    def guess_parameters(self, x, y, x_label=""):
        # Simple slope estimate
        if len(x) > 1:
            slope = (y[-1] - y[0]) / (x[-1] - x[0])
            intercept = y[0] - slope * x[0]
            self._set_param("A", slope)
            self._set_param("B", intercept)

    def functionPlot(self, xvals):
        arglist_val=tuple([self.params2Dlist[i][2] for i in range(self.num_params)])
        return self.fitfunction(xvals, *arglist_val)

class parabolaFit(FitObject):
    def __init__(self):
        super(parabolaFit, self).__init__()
        self.num_params = 3
        self.params2Dlist= [
                            [True,"A",1,0.1, -np.inf,np.inf],
                            [True,"x0", 0, 0.1, -np.inf,np.inf],
                            [True,"B",0,0.1, -np.inf,np.inf]
                            ]
        self.description="A*(x-x0)^2+B"

    # 26/01/06 gt: intelligent fitting
    # 26/07/30 gt: updated for concavity detection
    def guess_parameters(self, x, y, x_label=""):
        import numpy as np

        # Compare the center of the data to the average of the two edges
        mid_idx = len(y) // 2
        edge_mean = (y[0] + y[-1]) / 2.0

        if y[mid_idx] > edge_mean:
            # Concave down (n-shaped): Vertex is the maximum
            idx = np.argmax(y)
            B_guess = np.max(y)
        else:
            # Concave up (U-shaped): Vertex is the minimum
            idx = np.argmin(y)
            B_guess = np.min(y)

        x0_guess = x[idx]

        # Intelligently estimate 'A' using the first data point
        # Derived from: y = A(x - x0)^2 + B  ->  A = (y - B) / (x - x0)^2
        dx = x[0] - x0_guess
        if dx != 0:
            A_guess = (y[0] - B_guess) / (dx ** 2)
        else:
            A_guess = -1.0 if y[mid_idx] > edge_mean else 1.0

        self._set_param("x0", x0_guess)
        self._set_param("B", B_guess)
        self._set_param("A", A_guess)

    def fitFunction(self, x, A,x0,B):
        return A*(x-x0)**2+B

class exponentialFit(FitObject):
    def __init__(self):
        super(exponentialFit, self).__init__()
        self.num_params = 4
        # Initialize with infinite bounds so we don't accidentally clip valid data
        # before the guess function runs.
        self.params2Dlist = [
            [True, "A", 1.0, 0.1, -np.inf, np.inf],
            [True, "tau", 1.0, 0.1, 0.0, np.inf],
            [True, "x0", 0.0, 0.1, -np.inf, np.inf],
            [True, "B", 0.0, 0.1, -np.inf, np.inf]
        ]
        self.description = "A*exp(-(x-x0)/tau)+B"

    def fitFunction(self, x, A, tau, x0, B):
        # A is amplitude, tau is decay constant, x0 is time offset, B is background/asymptote
        return A * np.exp(-(x - x0) / tau) + B

    # 26/07/30 gt: updated to handle noisy spikes
    def guess_parameters(self, x, y, x_label=""):
        import numpy as np

        # --- 0. Noise-Immune Edge Detection ---
        # Take the average of the first and last 5% of the data (minimum 1 point)
        # This prevents a single noisy spike from ruining the amplitude sign guess.
        window = max(1, len(y) // 20)
        start_y = np.mean(y[:window])
        end_y = np.mean(y[-window:])

        # --- 1. Guess Asymptote (B) ---
        B_guess = end_y

        # --- 2. Guess Offset (x0) ---
        x0_guess = x[0]

        # --- 3. Guess Amplitude (A) ---
        # Positive A = Decay. Negative A = Saturating Rise.
        A_guess = start_y - B_guess

        # --- 4. Guess Tau (Time Constant) ---
        target_y_at_tau = B_guess + (A_guess * np.exp(-1))

        # Find the index in the data closest to this target value
        idx_closest = (np.abs(y - target_y_at_tau)).argmin()
        tau_guess = x[idx_closest] - x0_guess

        # Fallback: If noise makes tau_guess 0 or negative, default to 1/3 of range
        if tau_guess <= 0:
            tau_guess = (x[-1] - x[0]) / 3.0

        # --- 5. Update Parameter List ---
        self.params2Dlist[0][2] = A_guess
        self.params2Dlist[1][2] = tau_guess
        self.params2Dlist[2][2] = x0_guess
        self.params2Dlist[3][2] = B_guess

        # --- 6. Intelligent Bounds (Dynamic) ---
        x_range = x[-1] - x[0]

        self.params2Dlist[1][4] = x_range * 0.001  # Min Tau
        self.params2Dlist[1][5] = x_range * 100  # Max Tau

        self.params2Dlist[2][4] = x[0] - x_range  # Min x0
        self.params2Dlist[2][5] = x[-1] + x_range  # Max x0

# 26/01/19 gt: proper units, and phase are multiples of 2pi
class sinusoidFit(FitObject):
    def __init__(self):
        super(sinusoidFit, self).__init__()
        self.num_params = 4
        # 1. Parameter Name is permanently "freq_kHz"
        self.params2Dlist = [
            [True, "A", 0.5, 0.1, -np.inf, np.inf],
            [True, "freq_kHz", 1.0, 0.1, 0, np.inf],
            [True, "phi0_turns", 0.0, 0.1, 0, 1.0],
            [True, "B", 0.0, 0.1, -np.inf, np.inf]
        ]
        self.description = "A*sin(2*pi*(freq_kHz*t_ms+phi))+B"

    # 2. Argument must match the list name EXACTLY
    def fitFunction(self, x, A, freq_kHz, phi0_turns, B):
        # Assumes x is in ms. (kHz * ms = cycles)
        return A * np.sin(2 * np.pi * (freq_kHz * x + phi0_turns)) + B

    def guess_parameters(self, x, y, x_label=""):
        # --- 1. Basic Amplitude Guesses ---
        B_guess = np.mean(y)
        A_guess = (np.max(y) - np.min(y)) / 2.0

        # --- 2. Frequency Guess (Raw FFT) ---
        k_guess = 1.0
        try:
            dx = x[1] - x[0]
            fft_vals = np.fft.rfft(y - B_guess)
            fft_freq = np.fft.rfftfreq(len(y), d=dx)
            peak_idx = np.argmax(np.abs(fft_vals[1:])) + 1
            k_guess = fft_freq[peak_idx]
        except:
            if len(x) > 1: k_guess = 1.0 / (x[-1] - x[0])

        # --- 3. Unit Conversion for the Guess ---
        # The target parameter is kHz.
        # We adjust k_guess based on what the input units seem to be.

        if "(us)" in x_label or "[us]" in x_label:
            # Input: us -> FFT returns MHz
            # Target: kHz
            # Conversion: MHz * 1000 = kHz
            k_guess = k_guess * 1000.0

        elif "(s)" in x_label or "[s]" in x_label:
            # Input: s -> FFT returns Hz
            # Target: kHz
            # Conversion: Hz / 1000 = kHz
            k_guess = k_guess / 1000.0

        # If label is (ms), FFT returns kHz directly. No change needed.

        # --- 4. Phase Guess ---
        idx_max = np.argmax(y)
        x_at_max = x[idx_max]

        # We must use the same frequency unit logic for phase calculation
        # phi = 0.25 - (freq_kHz * x_ms)
        # (Assuming x and k are consistent now)
        phi_turns = 0.25 - (k_guess * x_at_max)
        phi_turns = phi_turns % 1.0

        # --- 5. Update Internal List ---
        self.params2Dlist[0][2] = A_guess
        self.params2Dlist[1][2] = k_guess  # Stores value as kHz
        self.params2Dlist[2][2] = phi_turns
        self.params2Dlist[3][2] = B_guess

# 26/01/23 gt: intelligent guess
class cos2decayFit(FitObject):
    def __init__(self):
        super(cos2decayFit, self).__init__()
        self.num_params = 5
        self.params2Dlist = [
            [True, "A", 1.0, 0.1, -np.inf, np.inf],
            [True, "tau", 10.0, 0.1, 0.0, np.inf],
            [True, "k_Hz", 1.0, 0.01, 0.0, np.inf],
            [True, "phi0_turns", 0.0, 0.1, 0, 1.0],  # Bounded 0 to 1
            [True, "B", 0.0, 0.1, -np.inf, np.inf]
        ]
        self.description = "A*exp(-x/tau)*cos(pi*(k * x +phi))^2+B"

    def fitFunction(self, x, A, tau, k_Hz, phi0_turns, B):
        # 1 turn = 2*pi radians.
        # We multiply the entire argument by 2*pi.
        # (k*x) is cycles. phi0_turns is cycles.
        return A * np.exp(-x / tau) * np.cos(np.pi * (k_Hz * x + phi0_turns)) ** 2 + B

    # def guess_parameters(self, x, y, x_label=""):
    #     # --- 1. Bounds and Basic Amplitude ---
    #     B_guess = np.min(y)
    #     A_guess = np.max(y) - B_guess
    #
    #     dx = x[1] - x[0]
    #     x_range = x[-1] - x[0]
    #
    #     # --- 2. Frequency Guess (FFT) ---
    #     y_centered = y - np.mean(y)
    #
    #     try:
    #         fft_vals = np.fft.rfft(y_centered)
    #         fft_freq = np.fft.rfftfreq(len(y), d=dx)
    #
    #         # Find strongest frequency
    #         peak_idx = np.argmax(np.abs(fft_vals[1:])) + 1
    #         f_dominant = fft_freq[peak_idx]
    #
    #         # Correction: cos^2(wt) oscillates at 2w. We want w.
    #         k_guess = f_dominant # / 2.0
    #     except:
    #         k_guess = 1.0 / x_range
    #
    #     # --- 3. Unit Adjustment ---
    #     if "(us)" in x_label or "[us]" in x_label:
    #         k_guess = k_guess * 1000.0
    #     elif "(s)" in x_label or "[s]" in x_label:
    #         k_guess = k_guess / 1000.0
    #
    #         # --- 4. Phase Guess (Turns) ---
    #     # Peak of cos(2*pi*u) occurs when u = Integer (0, 1, 2...)
    #     # u = k*x + phi
    #     # Therefore: phi = -k*x (modulo 1)
    #
    #     idx_max = np.argmax(y)
    #     x_at_max = x[idx_max]
    #
    #     phi_turns = -k_guess * x_at_max
    #     phi_turns = phi_turns % 1.0  # Normalize to 0..1
    #
    #     # --- 5. Tau Guess (Envelope Decay) ---
    #     target_y = B_guess + (A_guess * 0.368)  # 1/e point
    #
    #     # Only search among "peaks" to avoid picking a point in a trough
    #     mask_upper_half = y > (B_guess + A_guess / 3.0)
    #
    #     if np.any(mask_upper_half):
    #         y_candidates = y[mask_upper_half]
    #         x_candidates = x[mask_upper_half]
    #
    #         idx_tau = (np.abs(y_candidates - target_y)).argmin()
    #         tau_guess = x_candidates[idx_tau] - x[0]
    #     else:
    #         tau_guess = x_range
    #
    #     if tau_guess <= 0: tau_guess = x_range / 2.0
    #
    #     # --- 6. Set Parameters ---
    #     self.params2Dlist[0][2] = A_guess
    #     self.params2Dlist[1][2] = tau_guess
    #     self.params2Dlist[2][2] = k_guess
    #     self.params2Dlist[3][2] = phi_turns
    #     self.params2Dlist[4][2] = B_guess
    #
    #     # --- 7. Dynamic Bounds ---
    #     self.params2Dlist[1][4] = x_range * 0.001  # Min Tau
    #     self.params2Dlist[1][5] = x_range * 100  # Max Tau
    #     self.params2Dlist[2][4] = 0.0  # Min k

    # 26/07/30 gt:
    def guess_parameters(self, x, y, x_label=""):
        import numpy as np

        x_range = x[-1] - x[0]
        dx = x_range / (len(x) - 1) if len(x) > 1 else 1.0

        # --- 1. Noise-Immune Bounds and Amplitude ---
        # Use percentiles to ignore random single-point spikes
        top_y = np.percentile(y, 95)
        bottom_y = np.percentile(y, 5)

        B_guess = bottom_y
        A_guess = top_y - bottom_y

        # Prevent flatline data from causing division/zero errors later
        if A_guess <= 0:
            A_guess = 1e-3

            # --- 2. Frequency Guess (Zero-Padded FFT) ---
        y_centered = y - np.mean(y)

        try:
            # Pad the FFT to 10x the length for highly resolved frequency bins on short scans
            pad_len = len(y) * 10
            fft_vals = np.fft.rfft(y_centered, n=pad_len)
            fft_freq = np.fft.rfftfreq(pad_len, d=dx)

            # Find strongest frequency
            peak_idx = np.argmax(np.abs(fft_vals[1:])) + 1
            k_guess = fft_freq[peak_idx]
        except Exception:
            k_guess = 1.0 / x_range

        # --- 3. Unit Adjustment ---
        # Left intact from your original code
        if "(us)" in x_label or "[us]" in x_label:
            k_guess = k_guess * 1000.0
        elif "(s)" in x_label or "[s]" in x_label:
            k_guess = k_guess / 1000.0

        # --- 4. Phase Guess (Turns) ---
        # Smooth the data slightly to find the true physical peak, avoiding noise spikes
        window = max(1, len(y) // 20)
        y_smooth = np.convolve(y, np.ones(window) / window, mode='same')
        idx_max = np.argmax(y_smooth)
        x_at_max = x[idx_max]

        phi_turns = -k_guess * x_at_max
        phi_turns = phi_turns % 1.0  # Normalize to 0..1

        # --- 5. Tau Guess (Envelope Decay) ---
        target_y = B_guess + (A_guess * 0.368)  # 1/e point

        # Search among upper envelope values (top 40% of the signal)
        mask_upper = y > (B_guess + A_guess * 0.6)

        if np.any(mask_upper):
            y_candidates = y[mask_upper]
            x_candidates = x[mask_upper]

            idx_tau = (np.abs(y_candidates - target_y)).argmin()
            tau_guess = x_candidates[idx_tau] - x[0]
        else:
            tau_guess = x_range / 2.0

        # Safe fallback if the signal hasn't meaningfully decayed yet
        if tau_guess <= 0:
            tau_guess = x_range / 3.0

        # --- 6. Set Parameters ---
        self.params2Dlist[0][2] = A_guess
        self.params2Dlist[1][2] = tau_guess
        self.params2Dlist[2][2] = k_guess
        self.params2Dlist[3][2] = phi_turns
        self.params2Dlist[4][2] = B_guess

        # --- 7. Dynamic Bounds ---
        self.params2Dlist[1][4] = x_range * 0.001  # Min Tau
        self.params2Dlist[1][5] = x_range * 100  # Max Tau
        self.params2Dlist[2][4] = 0.0  # Min k

# 26/01/23 gt: intelligent guess
class sinDecayFit(FitObject):
    def __init__(self):
        super(sinDecayFit, self).__init__()
        self.num_params = 5
        self.params2Dlist = [
            [True, "A", 1.0, 0.1, -np.inf, np.inf],
            [True, "tau", 10.0, 0.1, -np.inf, np.inf],
            [True, "k_Hz", 1.0, 0.01, -np.inf, np.inf],
            [True, "phi0_turns", 0.0, 0.1, 0, 1.0],  # Bounded 0 to 1
            [True, "B", 0.0, 0.1, -np.inf, np.inf]
        ]
        self.description = "A*exp(-x/tau)*sin(2*pi*(k * x +phi))+B"

    def fitFunction(self, x, A, tau, k_Hz, phi0_turns, B):
        # 1 turn = 2*pi radians.
        # We multiply the entire argument by 2*pi.
        # (k*x) is cycles. phi0_turns is cycles.
        return A * np.exp(-x / tau) * np.sin(2*np.pi * (k_Hz * x + phi0_turns)) + B

    # def guess_parameters(self, x, y, x_label=""):
    #     # --- 1. Bounds and Basic Amplitude ---
    #     B_guess = np.min(y)
    #     A_guess = np.max(y) - B_guess
    #
    #     dx = x[1] - x[0]
    #     x_range = x[-1] - x[0]
    #
    #     # --- 2. Frequency Guess (FFT) ---
    #     y_centered = y - np.mean(y)
    #
    #     try:
    #         fft_vals = np.fft.rfft(y_centered)
    #         fft_freq = np.fft.rfftfreq(len(y), d=dx)
    #
    #         # Find strongest frequency
    #         peak_idx = np.argmax(np.abs(fft_vals[1:])) + 1
    #         f_dominant = fft_freq[peak_idx]
    #
    #         # Correction: cos^2(wt) oscillates at 2w. We want w.
    #         k_guess = f_dominant # / 2.0
    #     except:
    #         k_guess = 1.0 / x_range
    #
    #     # --- 3. Unit Adjustment ---
    #     if "(us)" in x_label or "[us]" in x_label:
    #         k_guess = k_guess * 1000.0
    #     elif "(s)" in x_label or "[s]" in x_label:
    #         k_guess = k_guess / 1000.0
    #
    #         # --- 4. Phase Guess (Turns) ---
    #     # Peak of cos(2*pi*u) occurs when u = Integer (0, 1, 2...)
    #     # u = k*x + phi
    #     # Therefore: phi = -k*x (modulo 1)
    #
    #     idx_max = np.argmax(y)
    #     x_at_max = x[idx_max]
    #
    #     phi_turns = -k_guess * x_at_max
    #     phi_turns = phi_turns % 1.0  # Normalize to 0..1
    #
    #     # --- 5. Tau Guess (Envelope Decay) ---
    #     target_y = B_guess + (A_guess * 0.368)  # 1/e point
    #
    #     # Only search among "peaks" to avoid picking a point in a trough
    #     mask_upper_half = y > (B_guess + A_guess / 3.0)
    #
    #     if np.any(mask_upper_half):
    #         y_candidates = y[mask_upper_half]
    #         x_candidates = x[mask_upper_half]
    #
    #         idx_tau = (np.abs(y_candidates - target_y)).argmin()
    #         tau_guess = x_candidates[idx_tau] - x[0]
    #     else:
    #         tau_guess = x_range
    #
    #     if tau_guess <= 0: tau_guess = x_range / 2.0
    #
    #     # --- 6. Set Parameters ---
    #     self.params2Dlist[0][2] = A_guess
    #     self.params2Dlist[1][2] = tau_guess
    #     self.params2Dlist[2][2] = k_guess
    #     self.params2Dlist[3][2] = phi_turns
    #     self.params2Dlist[4][2] = B_guess
    #
    #     # --- 7. Dynamic Bounds ---
    #     self.params2Dlist[1][4] = x_range * 0.001  # Min Tau
    #     self.params2Dlist[1][5] = x_range * 100  # Max Tau
    #     self.params2Dlist[2][4] = 0.0  # Min k

    # 26/07/30 gt: updated
    def guess_parameters(self, x, y, x_label=""):
        import numpy as np

        x_range = x[-1] - x[0]
        dx = x_range / (len(x) - 1) if len(x) > 1 else 1.0

        # --- 1. Noise-Immune Bounds and Amplitude ---
        # Standard sine waves oscillate around a central baseline.
        # We use percentiles to ignore random single-point spikes.
        top_y = np.percentile(y, 95)
        bottom_y = np.percentile(y, 5)

        B_guess = (top_y + bottom_y) / 2.0  # Baseline is the exact center
        A_guess = (top_y - bottom_y) / 2.0  # Amplitude is half the peak-to-peak range

        if A_guess <= 0:
            A_guess = 1e-3

            # --- 2. Frequency Guess (Zero-Padded FFT) ---
        y_centered = y - B_guess

        try:
            # Zero-pad the FFT to 10x the length for highly resolved frequency bins
            pad_len = len(y) * 10
            fft_vals = np.fft.rfft(y_centered, n=pad_len)
            fft_freq = np.fft.rfftfreq(pad_len, d=dx)

            # Find strongest frequency
            peak_idx = np.argmax(np.abs(fft_vals[1:])) + 1
            k_guess = fft_freq[peak_idx]
        except Exception:
            k_guess = 1.0 / x_range

        # --- 3. Unit Adjustment ---
        if "(us)" in x_label or "[us]" in x_label:
            k_guess = k_guess * 1000.0
        elif "(s)" in x_label or "[s]" in x_label:
            k_guess = k_guess / 1000.0

        # --- 4. Phase Guess (Turns) ---
        # Smooth data to find the true physical peak, avoiding noise spikes
        window = max(1, len(y) // 20)
        y_smooth = np.convolve(y, np.ones(window) / window, mode='same')
        idx_max = np.argmax(y_smooth)
        x_at_max = x[idx_max]

        # MATHEMATICAL NOTE ON PHASE:
        # If your fit function is A*cos(2*pi*k*x + 2*pi*phi):
        # phi_turns = (-k_guess * x_at_max) % 1.0

        # If your fit function is A*sin(2*pi*k*x + 2*pi*phi):
        # Sine peaks at a 1/4 phase shift compared to cosine
        phi_turns = (0.25 - k_guess * x_at_max) % 1.0

        # --- 5. Tau Guess (Envelope Decay) ---
        target_y = B_guess + (A_guess * 0.368)  # 1/e of the amplitude above baseline

        # Search only among upper envelope points (top half of the signal)
        mask_upper = y > (B_guess + A_guess * 0.5)

        if np.any(mask_upper):
            y_candidates = y[mask_upper]
            x_candidates = x[mask_upper]

            idx_tau = (np.abs(y_candidates - target_y)).argmin()
            tau_guess = x_candidates[idx_tau] - x[0]
        else:
            tau_guess = x_range / 2.0

        # Safe fallback
        if tau_guess <= 0:
            tau_guess = x_range / 3.0

        # --- 6. Set Parameters ---
        self.params2Dlist[0][2] = A_guess
        self.params2Dlist[1][2] = tau_guess
        self.params2Dlist[2][2] = k_guess
        self.params2Dlist[3][2] = phi_turns
        self.params2Dlist[4][2] = B_guess

        # --- 7. Dynamic Bounds ---
        self.params2Dlist[1][4] = x_range * 0.001  # Min Tau
        self.params2Dlist[1][5] = x_range * 100  # Max Tau
        self.params2Dlist[2][4] = 0.0  # Min k

class gaussianFit(FitObject):
    def __init__(self):
        super(gaussianFit, self).__init__()
        self.num_params = 4
        self.params2Dlist= [
                            [True,"A",1,0.1, 0.0, np.inf],
                            [True,"sigma",0.1,0.1, 0.0, np.inf],
                            [True,"x0", 0, 0.1, -np.inf,np.inf],
                            [True,"B",0,0.1, -np.inf,np.inf]
                            ]
        self.description ="A*exp(-(x-x0)^2/(2*sigma^2))+B"

    # 26/01/06 gt: intelligent guess
    # 26/07/30 gt: updated to take care of polarity
    def guess_parameters(self, x, y, x_label=""):
        import numpy as np

        # --- 0. Sort the Data ---
        # Fixes issues with zig-zag scanning patterns
        sort_idx = np.argsort(x)
        x = np.array(x)[sort_idx]
        y = np.array(y)[sort_idx]

        x_range = x[-1] - x[0]

        # --- 1. Noise-Immune Baseline and Amplitude ---
        top_y = np.percentile(y, 95)
        bottom_y = np.percentile(y, 5)

        # Calculate baseline using the physical edges of the scan, not global median.
        # We take the mean of the first 10% and last 10% of the sorted points.
        edge_pts = max(1, len(y) // 10)
        baseline_guess = np.median(np.concatenate((y[:edge_pts], y[-edge_pts:])))

        if (top_y - baseline_guess) > (baseline_guess - bottom_y):
            # Positive peak
            B_guess = baseline_guess
            A_guess = top_y - baseline_guess
            is_peak = True
        else:
            # Negative peak (absorption dip)
            B_guess = baseline_guess
            A_guess = bottom_y - baseline_guess
            is_peak = False

        if abs(A_guess) <= 0:
            A_guess = 1e-3 if is_peak else -1e-3

        # --- 2. Center (x0) ---
        window = max(1, len(y) // 20)
        y_smooth = np.convolve(y, np.ones(window) / window, mode='same')

        if is_peak:
            idx_center = np.argmax(y_smooth)
        else:
            idx_center = np.argmin(y_smooth)

        x0_guess = x[idx_center]

        # --- 3. Width (sigma) via Robust Half-Maximum ---
        half_height = B_guess + A_guess / 2.0

        if is_peak:
            mask = y > half_height
        else:
            mask = y < half_height

        if np.any(mask):
            x_masked = x[mask]
            # Safe to do now that x is sorted
            fwhm = x_masked[-1] - x_masked[0]
        else:
            fwhm = 0

        if fwhm <= 0:
            fwhm = x_range / 4.0

        sigma_guess = fwhm / 2.3548

        # --- 4. Set Parameters ---
        self._set_param("B", B_guess)
        self._set_param("A", A_guess)
        self._set_param("x0", x0_guess)
        self._set_param("sigma", sigma_guess)

    def fitFunction(self, x, A,sigma,x0,B):
        return A*np.exp(-(x-x0)**2/(2*sigma**2))+B

# 26/01/23 gt: intelligent guess; x_vals passed are in MHz or ms
class lorentzianFit(FitObject):
    def __init__(self):
        super(lorentzianFit, self).__init__()
        self.num_params = 4
        self.params2Dlist = [
            [True, "A", 1.0, 0.1, -np.inf, np.inf],
            [True, "w", 1.0, 0.1, 0, np.inf],  # Width must be positive
            [True, "x0", 0.0, 0.1, -np.inf, np.inf],
            [True, "B", 0.0, 0.1, -np.inf, np.inf]
        ]
        self.description = "A * (w/2)^2 / ((x-x0)^2 + (w/2)^2) + B"

    def fitFunction(self, x, A, w, x0, B):
        # A = Peak Height (above B)
        # w = Full Width at Half Max (FWHM)
        # x0 = Center
        hwhm = 0.5 * w
        return A * (hwhm ** 2) / ((x - x0) ** 2 + hwhm ** 2) + B

    # 26/07/30 gt: updated
    def guess_parameters(self, x, y, x_label=""):
        import numpy as np

        x_range = x[-1] - x[0]

        # --- 1. Noise-Immune Baseline and Amplitude (Polarity Aware) ---
        # We use percentiles and medians to ignore random single-point spikes.
        median_y = np.median(y)
        top_y = np.percentile(y, 95)
        bottom_y = np.percentile(y, 5)

        # Determine if it's a positive peak or an absorption dip
        if (top_y - median_y) > (median_y - bottom_y):
            # Positive peak
            B_guess = bottom_y
            A_guess = top_y - bottom_y
            is_peak = True
        else:
            # Negative peak (absorption dip)
            B_guess = top_y
            A_guess = bottom_y - top_y  # This will be a negative number
            is_peak = False

        if abs(A_guess) <= 0:
            A_guess = 1e-3 if is_peak else -1e-3

        # --- 2. Center Guess (x0) ---
        # Smooth the data slightly to find the true physical center,
        # preventing it from snapping to a random off-center noise spike.
        window = max(1, len(y) // 20)
        y_smooth = np.convolve(y, np.ones(window) / window, mode='same')

        if is_peak:
            idx_center = np.argmax(y_smooth)
        else:
            idx_center = np.argmin(y_smooth)

        x0_guess = x[idx_center]

        # --- 3. Width Guess (FWHM) ---
        half_height_val = B_guess + (0.5 * A_guess)

        # Boolean mask based on polarity
        if is_peak:
            mask_inside = y > half_height_val
        else:
            mask_inside = y < half_height_val

        if np.sum(mask_inside) >= 2:
            x_inside = x[mask_inside]
            # The difference between the last and first point crossing half-max
            w_guess = x_inside[-1] - x_inside[0]
        else:
            # Fallback: If peak is very narrow or cut off
            w_guess = x_range / 10.0

        # Safety: Width cannot be zero or negative
        if w_guess <= 0:
            w_guess = x_range / 10.0

        # --- 4. Set Parameters ---
        self.params2Dlist[0][2] = A_guess
        self.params2Dlist[1][2] = w_guess
        self.params2Dlist[2][2] = x0_guess
        self.params2Dlist[3][2] = B_guess

        # --- 5. Dynamic Bounds ---
        # Width must be positive and not larger than the scan itself (roughly)
        self.params2Dlist[1][4] = x_range * 0.0001  # Min Width
        self.params2Dlist[1][5] = x_range * 10.0  # Max Width

        # Center should be within the scan range (with some padding)
        # self.params2Dlist[2][4] = x[0] - x_range  # Min x0
        # self.params2Dlist[2][5] = x[-1] + x_range  # Max x0

# 26/06/17: gt added Ramsey dip model to extract waist of beam four_PSS_fit
class four_PSS_fit(FitObject):
    def __init__(self):
        super(four_PSS_fit, self).__init__()
        self.num_params = 6
        # Parameter bounds are now defined in Voltage units
        # conversion factor: 0.018 V / 2.37 um ≈ 0.0076 V/um
        # If w0 ~ 3 um, then w0_volts ~ 3 * 0.0076 ≈ 0.0228 V
        # Format: [ <bool>, <param>, <initial>, <fit_val>, <min>, <max> ]
        self.params2Dlist = [
            [True, "w0_V", 0.003, 0.003, 0.0005, 0.2],
            [True, "phi2", 3.0, 0.1, 0, np.pi * 1.5],
            [True, "phi4", 0.0, 0.1, 0, np.pi * 1.5],
            [True, "x0_V", -0.1, -0.1, -1.0, 1.0],
            [True, "y_off", 0.0, 0.1, 0, 100],
            [True, "amp", 1.0, 1.0, 0, 1.0]
        ]
        self.description = "y_off + amp * cos(phi2*exp(-2*(x-x0)^2/w0^2) + phi4*exp(-4*(x-x0)^2/w0^2))"

    def fitFunction(self, x, w0_V, phi2, phi4, x0_V, y_off, amp):
        # Fit performed strictly in Voltage units
        phase = phi2 * np.exp(-2 * (x - x0_V)**2 / w0_V**2) + \
                phi4 * np.exp(-4 * (x - x0_V)**2 / w0_V**2)
        return y_off + amp * np.cos(phase)

    def guess_parameters(self, x, y, x_label=""):
        # Initial guesses in Voltage
        y_off_guess = np.min(y)
        amp_guess = np.max(y) - y_off_guess
        x0_guess = x[np.argmin(y)] if (np.max(y) - np.min(y)) > 0 else 0
        w0_guess = 1 * 0.031 / 2.37 # 1 micron to V

        self._set_param("y_off", y_off_guess)
        self._set_param("amp", amp_guess)
        self._set_param("x0_V", x0_guess)
        self._set_param("w0_V", w0_guess)

# 26/06/23 gt: to extract waist in V from EndcapX scan
class ramanPiPulseWaistFit(FitObject):
    # def __init__(self):
    #     super(ramanPiPulseWaistFit, self).__init__()
    #     self.num_params = 4
    #
    #     # Format: [ <bool>, <param>, <initial>, <fit_val>, <min>, <max> ]
    #     # Voltages choices based on your scaling: ~0.019 V for a ~2.5 um beam
    #     self.params2Dlist = [
    #         [True, "w0_V", 0.02, 0.02, 0.0005, 0.2],
    #         [True, "x0_V", 0.0, 0.0, -1.0, 1.0],
    #         [True, "y_off", 0.02, 0.02, 0.0, 1.0],
    #         [True, "amp", 0.95, 0.95, 0.0, 1.0]
    #     ]
    #     self.description = "y_off + amp * sin(0.5 * pi * exp(-(x-x0_V)^2 / w0_V^2))^2"
    #
    # def fitFunction(self, x, w0_V, x0_V, y_off, amp):
    #     # Fit performed strictly in Voltage units
    #     exponent = -((x - x0_V) / w0_V) ** 2
    #     return y_off + amp * np.sin(0.5 * np.pi * np.exp(exponent)) ** 2
    #
    # def guess_parameters(self, x, y, x_label=""):
    #     # Initial guesses for populations
    #     y_off_guess = np.min(y)
    #     amp_guess = np.max(y) - y_off_guess
    #
    #     # Since it's a pi-pulse profile, the center is at the maximum excitation
    #     x0_guess = x[np.argmax(y)] if (np.max(y) - np.min(y)) > 0 else 0
    #
    #     # Dynamically guess the waist in Volts based on the Full Width at Half Max (FWHM)
    #     threshold = y_off_guess + 0.5 * amp_guess
    #     above_thresh = np.where(y > threshold)[0]
    #
    #     if len(above_thresh) > 1:
    #         # Distance from center-ish to edge of the peak in Volts
    #         w0_guess = (x[above_thresh[-1]] - x[above_thresh[0]]) / 2.0
    #     else:
    #         # Fallback if data is too noisy: assume the beam takes up ~1/4 of the scan range
    #         w0_guess = (np.max(x) - np.min(x)) / 4.0
    #
    #     # Enforce bounds sanity check for the guess
    #     w0_guess = np.clip(w0_guess, 0.0005, 0.2)
    #
    #     # Update GUI parameter state
    #     self._set_param("y_off", y_off_guess)
    #     self._set_param("amp", amp_guess)
    #     self._set_param("x0_V", x0_guess)
    #     self._set_param("w0_V", w0_guess)

    # 26/07/02 gt: this accounts for the dips when driving for different times
    def __init__(self):
        super(ramanPiPulseWaistFit, self).__init__()
        self.num_params = 5

        # Format: [ <bool>, <param>, <initial>, <fit_val>, <min>, <max> ]
        # pulse_area is the peak pulse area at the center of the beam (in radians)
        self.params2Dlist = [
            [True, "w0_V", 0.02, 0.02, 0.0005, 0.2],
            [True, "x0_V", 0.0, 0.0, -1.0, 1.0],
            [True, "y_off", 0.02, 0.02, 0.0, 1.0],
            [True, "amp", 0.95, 0.95, 0.0, 1.0],
            [True, "pulse_area", np.pi, np.pi, 0.0, 6.0 * np.pi]
        ]
        self.description = "y_off + amp * sin(0.5 * pulse_area * exp(-(x-x0_V)^2 / w0_V^2))^2"

    def fitFunction(self, x, w0_V, x0_V, y_off, amp, pulse_area):
        # Generalized fit function where pulse_area at x0 is a free parameter
        exponent = -((x - x0_V) / w0_V) ** 2
        return y_off + amp * np.sin(0.5 * pulse_area * np.exp(exponent)) ** 2

    def guess_parameters(self, x, y, x_label=""):
        # Baseline guess from the outer edges of the scan
        y_off_guess = (y[0] + y[-1]) / 2.0
        amp_guess = np.max(y) - y_off_guess

        # Find the global footprint of the feature
        threshold = y_off_guess + 0.3 * amp_guess
        above_thresh = np.where(y > threshold)[0]

        if len(above_thresh) > 1:
            # Center of the feature is the midpoint of its outer boundaries
            x0_guess = (x[above_thresh[-1]] + x[above_thresh[0]]) / 2.0
            total_width = x[above_thresh[-1]] - x[above_thresh[0]]

            # --- Auto-detect pulse area regime ---
            # Look at a small neighborhood around the calculated center to combat noise
            idx_center = np.argmin(np.abs(x - x0_guess))
            start_idx = max(0, idx_center - 1)
            end_idx = min(len(y), idx_center + 2)
            y_center_local = np.mean(y[start_idx:end_idx])

            if y_center_local < (y_off_guess + 0.4 * amp_guess):
                # The center is a local dip -> Guess a 2pi pulse profile
                pulse_area_guess = 2.0 * np.pi
                w0_guess = total_width / 2.35
            else:
                # The center is a local peak -> Guess a standard pi pulse profile
                pulse_area_guess = np.pi
                w0_guess = total_width / 2.0
        else:
            # Robust fallback if data is heavily attenuated or noisy
            x0_guess = x[np.argmax(y)]
            w0_guess = (np.max(x) - np.min(x)) / 4.0
            pulse_area_guess = np.pi

        # Clamp guesses within reasonable hardware/physical bounds
        w0_guess = np.clip(w0_guess, 0.0005, 0.2)

        # Update GUI parameter state
        self._set_param("y_off", y_off_guess)
        self._set_param("amp", amp_guess)
        self._set_param("x0_V", x0_guess)
        self._set_param("w0_V", w0_guess)
        self._set_param("pulse_area", pulse_area_guess)

# 26/07/02 gt: account for the Airy rings
class ramanAiryPulseWaistFit(FitObject):
    def __init__(self):
        super(ramanAiryPulseWaistFit, self).__init__()
        self.num_params = 5

        # Format: [ <bool>, <param>, <initial>, <fit_val>, <min>, <max> ]
        # w0_V now represents the true 1/e^2 intensity waist of the Airy beam
        self.params2Dlist = [
            [True, "w0_V", 0.02, 0.02, 0.0005, 0.3],
            [True, "x0_V", 0.0, 0.0, -1.0, 1.0],
            [True, "y_off", 0.02, 0.02, 0.0, 1.0],
            [True, "amp", 0.95, 0.95, 0.0, 1.0],
            [True, "pulse_area", np.pi, np.pi, 0.0, 6.0 * np.pi]
        ]
        self.description = "y_off + amp * sin(0.5 * pulse_area * [2*J1(z)/z])^2 where z = 2.5838*(x-x0)/w0_V"

    def fitFunction(self, x, w0_V, x0_V, y_off, amp, pulse_area):
        if w0_V == 0:
            w0_V = 1e-9

        # Scale factor 2.5838 maps w0_V directly to the 1/e^2 intensity point (1/e amplitude point)
        z = 2.5838 * (x - x0_V) / w0_V

        with np.errstate(divide='ignore', invalid='ignore'):
            # 2*J1(z)/z is the square root of the Airy intensity.
            # We do NOT square it here because Rabi frequency scales with the E-field amplitude.
            airy_amplitude = 2.0 * sp.j1(z) / z
            airy_amplitude = np.where(z == 0, 1.0, airy_amplitude)

        return y_off + amp * np.sin(0.5 * pulse_area * airy_amplitude) ** 2

    def guess_parameters(self, x, y, x_label=""):
        y_off_guess = (y[0] + y[-1]) / 2.0
        amp_guess = np.max(y) - y_off_guess

        threshold = y_off_guess + 0.3 * amp_guess
        above_thresh = np.where(y > threshold)[0]

        if len(above_thresh) > 1:
            x0_guess = (x[above_thresh[-1]] + x[above_thresh[0]]) / 2.0
            total_width = x[above_thresh[-1]] - x[above_thresh[0]]

            idx_center = np.argmin(np.abs(x - x0_guess))
            start_idx = max(0, idx_center - 1)
            end_idx = min(len(y), idx_center + 2)
            y_center_local = np.mean(y[start_idx:end_idx])

            if y_center_local < (y_off_guess + 0.4 * amp_guess):
                # 2pi pulse dip
                pulse_area_guess = 2.0 * np.pi
                w0_guess = total_width / 2.35
            else:
                # pi pulse peak
                pulse_area_guess = np.pi
                w0_guess = total_width / 1.6
        else:
            x0_guess = x[np.argmax(y)]
            w0_guess = (np.max(x) - np.min(x)) / 4.0
            pulse_area_guess = np.pi

        w0_guess = np.clip(w0_guess, 0.0005, 0.3)

        self._set_param("y_off", y_off_guess)
        self._set_param("amp", amp_guess)
        self._set_param("x0_V", x0_guess)
        self._set_param("w0_V", w0_guess)
        self._set_param("pulse_area", pulse_area_guess)

# 26/01/23 gt: intelligent guessing, and more robust computation by Gemini's suggestion
class carrierFlopFit(FitObject):
    def __init__(self):
        super(carrierFlopFit, self).__init__()
        # Increased ph_N default to 100 to prevent cutoff errors at higher temps
        self.num_params = 8
        self.params2Dlist = [
            [True, "Omega", 1.0, 0.1, 0, np.inf],  # Rabi Frequency
            [False, "eta", 0.1, 0.01, 0, 0.5],  # Lamb-Dicke (Usually fixed!)
            [True, "phi0_rad", 0.0, 0.1, -np.pi, np.pi],
            [True, "nbar", 5.0, 0.5, 0, 100],  # Temperature
            [False, "ph_N", 60, 0, 10, 200],  # Summation cut-off (Int)
            [True, "rescale", 1.0, 0.1, -np.inf, np.inf],
            [True, "offset", 0.0, 0.1, -np.inf, np.inf],
            [True, "gamma", 0.0, 0.01, 0, np.inf]  # Exponential decay rate
        ]
        self.description = "Carrier Rabi flop with Laguerre polynomials (thermal) and exp decay"

    def fitFunction(self, x, Omega, eta, phi0_rad, nbar, ph_N, rescale, offset, gamma):
        # 1. Thermal Distribution P(n)
        # We compute this vector once.
        n = np.arange(0, int(ph_N))

        # P_n = nbar^n / (nbar+1)^(n+1)
        # Computed in log space for numerical stability at high n, then exp
        log_Pn = n * np.log(nbar + 1e-9) - (n + 1) * np.log(nbar + 1 + 1e-9)
        P_n = np.exp(log_Pn)

        # Normalize P_n just in case of truncation
        P_n /= np.sum(P_n)

        # 2. Generalized Laguerre Polynomials L_n^0(eta^2)
        # Note: Omega_n = Omega_0 * exp(-eta^2/2) * L_n(eta^2)
        # We calculate the effective Rabi freq for each n
        eta_sq = eta ** 2

        # We need to broadcast x against n.
        # x shape: (T,), n shape: (N,) -> Result (N, T)
        t_grid = x[None, :]

        # Calculate contribution of each n
        # This loop is unavoidable unless we precompute Laguerre polys, but
        # scipy's genlaguerre returns a function, so we call it per n.
        # This is the performance bottleneck.
        summation = np.zeros_like(x, dtype=np.float64)

        prefactor = np.exp(-eta_sq / 2.0)

        for i in n:
            # L_i = genlaguerre(i, 0)(eta_sq) # Returns scalar value
            # SciPy optimization: pre-calculate the value since eta is scalar for the fit step
            # However, during fit, eta changes.
            L_val = genlaguerre(i, 0)(eta_sq)

            Omega_n = Omega * prefactor * L_val

            # Oscillating term: cos(2*pi * Omega_n * t + phi)^2
            osc = np.cos(2 * np.pi * Omega_n * t_grid + phi0_rad) ** 2

            summation += P_n[i] * osc[0, :]  # Add weighted contribution

        # 3. Apply Amplitude scaling and Exponential Decay
        return rescale * np.exp(-gamma * x) * summation + offset

    def guess_parameters(self, x, y, x_label=""):
        # --- 1. Basic Amplitude Limits ---
        B_guess = np.min(y)
        A_guess = np.max(y) - B_guess

        self._set_param("offset", B_guess)
        self._set_param("rescale", A_guess)

        # --- 2. Frequency Guess (FFT) ---
        dx = x[1] - x[0]
        x_range = x[-1] - x[0]

        try:
            fft_vals = np.fft.rfft(y - np.mean(y))
            fft_freq = np.fft.rfftfreq(len(y), d=dx)
            peak_idx = np.argmax(np.abs(fft_vals[1:])) + 1
            f_dominant = fft_freq[peak_idx]

            # Rabi flops in probability space oscillate at 2*Omega if using sin^2(Omega*t)
            # Or if using cos(2*pi*Omega*t)^2, the FFT sees 2*Omega.
            # We assume Omega represents the base Rabi frequency.
            omega_guess = f_dominant / 2.0
        except:
            omega_guess = 1.0 / x_range

        # Unit Correction
        if "(us)" in x_label or "[us]" in x_label:
            omega_guess *= 1000.0
        elif "(s)" in x_label or "[s]" in x_label:
            omega_guess /= 1000.0

        self._set_param("Omega", omega_guess)

        # --- 3. Phase Guess ---
        # Find peak location to align cosine
        idx_max = np.argmax(y)
        t_max = x[idx_max]
        # Peak of cos(wt + phi)^2 is when wt+phi = 0
        phi_guess = -2 * np.pi * omega_guess * t_max
        phi_guess = (phi_guess + np.pi) % (2 * np.pi) - np.pi
        self._set_param("phi0_rad", phi_guess)

        # --- 4. Gamma (Envelope Decay) ---
        # Rough estimate: How fast does the signal approach 0.5 (mixed state)?
        # We look for the point where the contrast drops.
        # This is hard to distinguish from nbar dephasing, so we start conservative.
        self._set_param("gamma", 0.0)  # Let the fitter find it, start at 0

        # --- 5. Nbar Guess ---
        # This is very difficult to guess without knowing Eta.
        # If the signal washes out quickly but Gamma is low, nbar is high.
        # We set a moderate starting point.
        self._set_param("nbar", 2.0)

        # --- 6. Bounds Updates ---
        # Set dynamic bounds for time-dependent variables
        self.params2Dlist[7][4] = 0.0  # Min Gamma
        self.params2Dlist[7][5] = 10.0 / x_range  # Max Gamma (decay shouldn't be instant)

# 26/01/23 gt: intelligent guess
class RSBFlopFit(FitObject):
    def __init__(self):
        super(RSBFlopFit, self).__init__()
        # Increased ph_N to ensure convergence at higher temps
        self.num_params = 8
        self.params2Dlist = [
            [True, "Omega", 1.0, 0.1, 0, np.inf],  # Base Rabi Frequency
            [False, "eta", 0.1, 0.01, 0, 0.5],  # Lamb-Dicke (Fix this if possible!)
            [True, "phi0_rad", 0.0, 0.1, -np.pi, np.pi],
            [True, "nbar", 1.0, 0.1, 0, 100],  # Temperature
            [False, "ph_N", 60, 0, 10, 200],  # Summation cut-off
            [True, "rescale", 1.0, 0.1, -np.inf, np.inf],
            [True, "offset", 0.0, 0.1, -np.inf, np.inf],
            [True, "gamma", 0.0, 0.01, 0, np.inf]  # Decay
        ]
        self.description = "RSB Rabi flop (n -> n-1) with thermal distribution"

    def fitFunction(self, x, Omega, eta, phi0_rad, nbar, ph_N, rescale, offset, gamma):
        # 1. Thermal Distribution P(n)
        # P_n = nbar^n / (nbar+1)^(n+1)
        # We compute for n = 0 to N, then select n=1..N for the loop
        n_indices = np.arange(0, int(ph_N))

        # Log-space calculation for numerical stability
        log_Pn = n_indices * np.log(nbar + 1e-9) - (n_indices + 1) * np.log(nbar + 1 + 1e-9)
        P_n = np.exp(log_Pn)

        # Normalize in case of truncation
        P_n /= np.sum(P_n)

        # 2. Summation over n = 1 to ph_N
        # RSB drives |n> -> |n-1>. Strength depends on n.
        # If n=0, no transition occurs (term is 0).

        summation = np.zeros_like(x, dtype=np.float64)
        t_grid = x[None, :]
        eta_sq = eta ** 2
        prefactor = np.exp(-eta_sq / 2.0)

        # Loop starts at 1
        for n in range(1, int(ph_N)):
            # Generalized Laguerre L_{n-1}^1(eta^2)
            # Scaling factor: sqrt(1/n) * eta * L...

            L_val = genlaguerre(n - 1, 1)(eta_sq)

            # Effective Rabi Frequency for this n-level
            # Note: The 'eta' in front comes from the RSB coupling strength
            Omega_n = Omega * eta * prefactor * (1.0 / np.sqrt(n)) * L_val

            # Oscillating term
            # Using the exact form from your snippet: 2 * pi * ... / 2
            osc = np.cos(2 * np.pi * Omega_n * t_grid + phi0_rad) ** 2

            # Weighted by population of the STARTING state |n>
            summation += P_n[n] * osc[0, :]

        return rescale * np.exp(-gamma * x) * summation + offset

    def guess_parameters(self, x, y, x_label=""):
        # --- 1. Basic Amplitude ---
        B_guess = np.min(y)
        A_guess = np.max(y) - B_guess

        self._set_param("offset", B_guess)
        self._set_param("rescale", A_guess)

        # --- 2. Check for "Flat" Signal (Ground State) ---
        # If the RSB is flat line 0, nbar is ~0.
        # If we try to fit a flat line with a cosine, the fitter will explode.
        if A_guess < 0.05:  # Arbitrary threshold for "no signal"
            self._set_param("nbar", 0.05)
            self._set_param("Omega", 1.0)  # Dummy value
            return  # Stop guessing, let fitter try small numbers

        # --- 3. Frequency Guess (FFT) ---
        dx = x[1] - x[0]
        x_range = x[-1] - x[0]

        try:
            fft_vals = np.fft.rfft(y - np.mean(y))
            fft_freq = np.fft.rfftfreq(len(y), d=dx)
            peak_idx = np.argmax(np.abs(fft_vals[1:])) + 1
            f_dominant = fft_freq[peak_idx]

            # RSB Physics Correction:
            # The oscillation frequency f_meas approx = Omega_carrier * eta
            # Therefore: Omega_carrier_guess = f_meas / eta

            # We use the current value of eta from the parameter list (default 0.1)
            eta_curr = self.params2Dlist[1][2]
            if eta_curr == 0: eta_curr = 0.1

            # Factor of 2 accounts for the cos^2 vs cos relation in FFT
            omega_guess = (f_dominant / 2.0) / eta_curr

        except:
            omega_guess = (1.0 / x_range) / 0.1

        # Unit Correction
        if "(us)" in x_label or "[us]" in x_label:
            omega_guess *= 1000.0
        elif "(s)" in x_label or "[s]" in x_label:
            omega_guess /= 1000.0

        self._set_param("Omega", omega_guess)

        # --- 4. Nbar Guess ---
        # For RSB: Higher Amplitude -> Higher nbar.
        # If A_guess is close to 1.0 (max contrast), nbar is large (>= 1).
        # If A_guess is small (< 0.3), nbar is small (< 0.5).
        if A_guess > 0.8:
            self._set_param("nbar", 2.0)
        elif A_guess > 0.3:
            self._set_param("nbar", 1.0)
        else:
            self._set_param("nbar", 0.2)

        # --- 5. Phase & Gamma ---
        idx_max = np.argmax(y)
        t_max = x[idx_max]

        # Re-calculate effective freq for phase alignment
        f_eff = omega_guess * self.params2Dlist[1][2]  # Omega * eta

        phi_guess = -2 * np.pi * f_eff * t_max
        phi_guess = (phi_guess + np.pi) % (2 * np.pi) - np.pi

        self._set_param("phi0_rad", phi_guess)
        self._set_param("gamma", 0.0)  # Start with no decay

        # --- 6. Bounds ---
        self.params2Dlist[7][4] = 0.0  # Min Gamma
        self.params2Dlist[7][5] = 10.0 / x_range

class BSBFlopFit(FitObject):
    def __init__(self):
        super(BSBFlopFit, self).__init__()
        self.num_params = 8
        self.params2Dlist = [
            [True, "Omega", 1, 0.1, -100, 100],
            [True, "eta", 0.1, 0.1, 0, 0.5],
            [True, "phi0_rad", 0, 0.1, -100, 100],
            [True, "nbar", 1, 0.1, 0, 30],
            [False, "ph_N", 20, 0, -100, 100],
            [False, "rescale", 1, 0.1, -100, 100],
            [False, "offset", 0, 0.1, -100, 100],
            [False, "gamma", 10 ** 6, 0.1, 0, 10 ** 7]
        ]
        self.description = "BSB Rabi flop with Laguerre polynomials and dephasing"

    def fitFunction(self, x, Omega, eta, phi0, nbar, ph_N, rescale, offset, gamma):
        evol = rescale * np.exp(-gamma * x) * np.sum([((nbar ** (n)) / ((nbar + 1) ** (n + 1))) * np.cos(
            np.exp(-eta ** 2 / 2) * np.sqrt(np.math.factorial(n) / np.math.factorial(n + 1)) * genlaguerre(n, 1)(
                eta ** 2) * 2 * np.pi * eta * Omega * x / 2 + phi0) ** 2 for n in range(0, int(ph_N))], 0) + offset
        return evol



FIT_DICTIONARY = {
    'line':lineFit(),
    'parabola': parabolaFit(),
    'exponential': exponentialFit(),
    'gaussian': gaussianFit(),
    'cos2_decay': cos2decayFit(),
    'sinDecay': sinDecayFit(),
    'sinusoid': sinusoidFit(),
    'lorentzian': lorentzianFit(),
    'fourPSSfit': four_PSS_fit(),
    'ramanWaist': ramanPiPulseWaistFit(),
    'ramanWaistAiry' : ramanAiryPulseWaistFit(),
    'CarrierFlopfit':carrierFlopFit(),
    'RSBFlopfit':RSBFlopFit(),
    'BSBFlopfit':BSBFlopFit()
}

        #return RSBmdl, RSBparams

