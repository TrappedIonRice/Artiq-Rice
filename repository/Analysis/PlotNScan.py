from ndscan.experiment import *
from oitg.results import *
import oitg.fitting
import numpy as np
import matplotlib
# %matplotlib tk
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import scipy.optimize
import pylab as plt
from mpl_interactions import ioff, panhandler, zoom_factory
import matplotlib.ticker as mticker


class plotNScan(ExpFragment):
    def build_fragment(self):

        self.setattr_param("rids", StringParam, "INPUT LIST OF RIDs", default = None)
        fits = ["exponential_decay", "sinusoid", "gaussian", "None"]
        self.setattr_argument("CHOOSE_FIT", EnumerationValue(fits, default="None"))

    def run_once(self):
        # extract data from hdf5 for exp 1
        lst_rids = list(self.rids.get().split(", "))
        with plt.ioff():  # for scrollwheel zoom functionality
            figure, axis = plt.subplots()

        # exponential decay function
        def exp_decay(x, a, b, c):
            return a * np.exp(-b * x) + c

        for rid in lst_rids:
            dict_test = find_results("", rid=int(rid),
                                     root_path="C:/Artiq/artiq_new_installation/results")  # returns dict of results, used to find file path
            dict_hdf5 = load_hdf5_file(dict_test[int(rid)][0])  # returns file as dict
            dict_datasets = dict_hdf5["datasets"]  # dict key where all points are stored in a nested dict

            # assign data for exp 1 and switch point
            key_name_x = "ndscan.rid_" + rid + ".points.axis_0"  # key name for duration parameter points
            key_name_y = "ndscan.rid_" + rid + ".points.channel_result"  # key name for result parameter points
            key_name_err = "ndscan.rid_" + rid + ".points.channel_res_err"  # key name for error parameter points
            x_vals_1 = list(dict_datasets[key_name_x])
            y_vals_1 = list(dict_datasets[key_name_y])
            err_vals_1 = list(dict_datasets[key_name_err])
            plt.errorbar(x_vals_1, y_vals_1, yerr=err_vals_1, fmt="o")
            plt.scatter(x_vals_1, y_vals_1)

            if self.CHOOSE_FIT == "exponential_decay":
                popt, pcov = curve_fit(exp_decay, x_vals_1, y_vals_1, p0=(1.0, 0.1, 1.0))

                a_opt, b_opt, c_opt = popt

                # Compute tau
                tau = 1 / b_opt
                print(f'Tau value (Exp 1) : {tau}')

                x_fit = np.linspace(min(x_vals_1), max(x_vals_1), 100)
                y_fit = exp_decay(x_fit, a_opt, b_opt, c_opt)
                plt.plot(x_fit, y_fit, label='fit: a=%5.3f, b=%5.3f, c=%5.3f' % tuple(popt))

        disconnect_zoom = zoom_factory(axis)
        pan_handler = panhandler(figure)
        plt.xlabel('Time (μs)')  # Indicate that the x axis is in microseconds
        plt.ticklabel_format(style='sci', axis='x', scilimits=(-6, -6))
        plt.legend()
        plt.show()



PlotNScan = make_fragment_scan_exp(plotNScan)
