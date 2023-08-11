from ndscan.experiment import *
from oitg.results import *
import oitg.fitting
import numpy as np
import matplotlib
#%matplotlib tk
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import scipy.optimize
import pylab as plt
from mpl_interactions import ioff, panhandler, zoom_factory
import matplotlib.ticker as mticker
from scipy.stats import norm

class plotScan(ExpFragment):
    def build_fragment(self):
        """exp 1"""
        self.setattr_param("date", StringParam, "EXPERIMENT DATE (YYYY-MM-DD)", default = None)
        self.setattr_param("rid", IntParam, "RUN ID (RID) NUMBER", default = None)

        """exp 2"""

        self.setattr_param("exp2", BoolParam, "INCLUDE 2ND EXPERIMENT", default=False)
        self.setattr_param("date_2", StringParam, "EXPERIMENT 2 DATE (YYYY-MM-DD)", default=None)
        self.setattr_param("rid_2", IntParam, "EXPERIMENT 2 RUN ID (RID) NUMBER", default=None)


        fits = ["exponential_decay", "sinusoid", "gaussian", "None"]

        self.setattr_argument("CHOOSE_FIT_1", EnumerationValue(fits, default="None"))

        self.setattr_argument("CHOOSE_FIT_2", EnumerationValue(fits, default="None"))



    def run_once(self):
        #extract data from hdf5 for exp 1
        dict_test = find_results(self.date.get(), rid=self.rid.get(),
                root_path="C:/Artiq/artiq_new_installation/results")  #returns dict of results, used to find file path
        dict_hdf5 = load_hdf5_file(dict_test[self.rid.get()][0]) #returns file as dict
        dict_datasets = dict_hdf5["datasets"] #dict key where all points are stored in a nested dict

        # extract data from hdf5 for exp 2
        dict_test_2 = find_results(self.date_2.get(), rid=self.rid_2.get(),
                                 root_path="C:/Artiq/artiq_new_installation/results")  # returns dict of results, used to find file path
        dict_hdf5_2 = load_hdf5_file(dict_test_2[self.rid_2.get()][0])  # returns file as dict
        dict_datasets_2 = dict_hdf5_2["datasets"]  # dict key where all points are stored in a nested dict

        #assign data for exp 1 and switch point
        key_name_x = "ndscan.rid_" + str(self.rid.get()) + ".points.axis_0" #key name for duration parameter points
        key_name_y = "ndscan.rid_" + str(self.rid.get()) + ".points.channel_result" #key name for result parameter points
        key_name_err = "ndscan.rid_" + str(self.rid.get()) + ".points.channel_res_err" #key name for error parameter points
        x_vals_1 = list(dict_datasets[key_name_x])
        y_vals_1 = list(dict_datasets[key_name_y])
        err_vals_1 = list(dict_datasets[key_name_err])

        # plt.plot(x_vals_1, y_vals_1)
        # plt.show()

        with plt.ioff(): #for scrollwheel zoom functionality
            figure, axis = plt.subplots()
        plt.scatter(x_vals_1, y_vals_1)
        plt.errorbar(x_vals_1, y_vals_1, yerr = err_vals_1, fmt = "o")



        #exponential decay function
        def exp_decay(x, a, b, c):
            return a * np.exp(-b * x) + c

        # sin function
        def fit_sin(tt, yy):
            '''Fit sin to the input time sequence, and return fitting parameters "amp", "omega", "phase", "offset", "freq", "period" and "fitfunc"'''
            tt = np.array(tt)
            yy = np.array(yy)
            ff = np.fft.fftfreq(len(tt), (tt[1] - tt[0]))  # assume uniform spacing
            Fyy = abs(np.fft.fft(yy))
            guess_freq = abs(
                ff[np.argmax(Fyy[1:]) + 1])  # excluding the zero frequency "peak", which is related to offset
            guess_amp = np.std(yy) * 2. ** 0.5
            guess_offset = np.mean(yy)
            guess = np.array([guess_amp, 2. * np.pi * guess_freq, 0., guess_offset])

            def sinfunc(t, A, w, p, c):  return A * np.sin(w * t + p) + c

            popt, pcov = scipy.optimize.curve_fit(sinfunc, tt, yy, p0=guess)
            A, w, p, c = popt
            f = w / (2. * np.pi)
            fitfunc = lambda t: A * np.sin(w * t + p) + c
            return {"amp": A, "omega": w, "phase": p, "offset": c, "freq": f, "period": 1. / f, "fitfunc": fitfunc,
                    "maxcov": np.max(pcov), "rawres": (guess, popt, pcov)}

        #gaussian function
        def gaussian(x, amplitude, mean, stddev):
            return amplitude * np.exp(-((x - mean) / 4 / stddev) ** 2)

        if self.CHOOSE_FIT_1 == "exponential_decay":
            popt, pcov = curve_fit(exp_decay, x_vals_1, y_vals_1, p0=(1.0, 0.1, 1.0))

            a_opt, b_opt, c_opt = popt

            # Compute tau
            tau = 1 / b_opt
            print(f'Tau value (Exp 1) : {tau}')

            x_fit = np.linspace(min(x_vals_1), max(x_vals_1), 100)
            y_fit = exp_decay(x_fit, a_opt, b_opt, c_opt)
            plt.plot(x_fit, y_fit, 'r-', label='fit: a=%5.3f, b=%5.3f, c=%5.3f' % tuple(popt))

        elif self.CHOOSE_FIT_1 == "sinusoid":
            res = fit_sin(x_vals_1, y_vals_1)
            x_fit = np.linspace(min(x_vals_1), max(x_vals_1), 100)
            plt.plot(x_fit, res["fitfunc"](x_fit), "r-", label="y fit curve", linewidth=2)

        elif self.CHOOSE_FIT_1 == "gaussian":
            x_vals_1 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
            y_vals_1 = [0, 2, 4, 8, 13, 38, 15, 8, 5, 2]
            popt, pcov = curve_fit(gaussian, x_vals_1, y_vals_1)#, p0=(36, 0.000001, 0))
            amp_opt, avg_opt, std_opt = popt

            x_fit = np.linspace(min(x_vals_1), max(x_vals_1), 100)
            y_fit = gaussian(x_fit, amp_opt, avg_opt, std_opt)
            for i in range(len(x_vals_1)):
                x_vals_1[i] = x_vals_1[i] * 10 **-6
            plt.scatter(x_vals_1, y_vals_1)
            plt.plot(x_fit/10**6, y_fit, 'r-', label='fit: Amplitude =%5.3f, Mean =%5.3f, Stddev =%5.3f' % tuple(popt))
            # plt.plot(x_fit, gaussian(x_fit, *popt))

        if self.exp2.get() == True:
            key_name_x2 = "ndscan.rid_" + str(
                self.rid_2.get()) + ".points.axis_0"  # key name for duration parameter points
            key_name_y2 = "ndscan.rid_" + str(
                self.rid_2.get()) + ".points.channel_result"  # key name for result parameter points
            key_name_err2 = "ndscan.rid_" + str(
                self.rid_2.get()) + ".points.channel_res_err"  # key name for error parameter points
            x_vals_2 = list(dict_datasets_2[key_name_x2])
            y_vals_2 = list(dict_datasets_2[key_name_y2])
            err_vals_2 = list(dict_datasets_2[key_name_err2])
            plt.scatter(x_vals_2, y_vals_2)

            if self.CHOOSE_FIT_2 == "exponential_decay":
                popt, pcov = curve_fit(exp_decay, x_vals_2, y_vals_2, p0=(1.0, 0.1, 1.0))

                a_opt, b_opt, c_opt = popt

                # Compute tau
                tau = 1 / b_opt
                print(f'Tau value (Exp 2) : {tau}')

                x_fit = np.linspace(min(x_vals_2), max(x_vals_2), 100)
                y_fit = exp_decay(x_fit, a_opt, b_opt, c_opt)
                plt.plot(x_fit, y_fit, 'b-', label='fit: a=%5.3f, b=%5.3f, c=%5.3f' % tuple(popt))

            elif self.CHOOSE_FIT_2 == "sinusoid":
                res = fit_sin(x_vals_2, y_vals_2)
                x_fit = np.linspace(min(x_vals_2), max(x_vals_2), 100)
                plt.plot(x_fit, res["fitfunc"](x_fit), "r-", label="y fit curve", linewidth=2)

        #enable scoll wheel zoom

        disconnect_zoom = zoom_factory(axis)
        pan_handler = panhandler(figure)

        plt.xlabel('Time (μs)')  # Indicate that the x axis is in microseconds
        plt.ticklabel_format(style='sci', axis='x', scilimits=(-6, -6))
        plt.legend()
        plt.show()


PlotScan = make_fragment_scan_exp(plotScan)






"""
import numpy, scipy.optimize

def fit_sin(tt, yy):
    '''Fit sin to the input time sequence, and return fitting parameters "amp", "omega", "phase", "offset", "freq", "period" and "fitfunc"'''
    tt = numpy.array(tt)
    yy = numpy.array(yy)
    ff = numpy.fft.fftfreq(len(tt), (tt[1]-tt[0]))   # assume uniform spacing
    Fyy = abs(numpy.fft.fft(yy))
    guess_freq = abs(ff[numpy.argmax(Fyy[1:])+1])   # excluding the zero frequency "peak", which is related to offset
    guess_amp = numpy.std(yy) * 2.**0.5
    guess_offset = numpy.mean(yy)
    guess = numpy.array([guess_amp, 2.*numpy.pi*guess_freq, 0., guess_offset])

    def sinfunc(t, A, w, p, c):  return A * numpy.sin(w*t + p) + c
    popt, pcov = scipy.optimize.curve_fit(sinfunc, tt, yy, p0=guess)
    A, w, p, c = popt
    f = w/(2.*numpy.pi)
    fitfunc = lambda t: A * numpy.sin(w*t + p) + c
    return {"amp": A, "omega": w, "phase": p, "offset": c, "freq": f, "period": 1./f, "fitfunc": fitfunc, "maxcov": numpy.max(pcov), "rawres": (guess,popt,pcov)}
"""

"""
import pylab as plt

N, amp, omega, phase, offset, noise = 500, 1., 2., .5, 4., 3
#N, amp, omega, phase, offset, noise = 50, 1., .4, .5, 4., .2
#N, amp, omega, phase, offset, noise = 200, 1., 20, .5, 4., 1
tt = numpy.linspace(0, 10, N)
tt2 = numpy.linspace(0, 10, 10*N)
yy = amp*numpy.sin(omega*tt + phase) + offset
yynoise = yy + noise*(numpy.random.random(len(tt))-0.5)

res = fit_sin(tt, yynoise)
print( "Amplitude=%(amp)s, Angular freq.=%(omega)s, phase=%(phase)s, offset=%(offset)s, Max. Cov.=%(maxcov)s" % res )

plt.plot(tt, yy, "-k", label="y", linewidth=2)
plt.plot(tt, yynoise, "ok", label="y with noise")
plt.plot(tt2, res["fitfunc"](tt2), "r-", label="y fit curve", linewidth=2)
plt.legend(loc="best")
plt.show()
"""