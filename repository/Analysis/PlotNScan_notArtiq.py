from ndscan.experiment import *
from oitg.results import *
from oitg.fitting import *
import numpy as np
import matplotlib
# %matplotlib tk
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import scipy.optimize
import pylab as plt
import pickle
import json
#from mpl_interactions import ioff, panhandler, zoom_factory
import oitg
import matplotlib.ticker as mticker



fits = {"exponential_decay":exponential_decay,
        "sinusoid":sinusoid,
        "gaussian": gaussian,
        "rabi_flop":rabi_flop,
        "lorentzian":lorentzian,
        "decaying_sinusoid":decaying_sinusoid,
        "cos_2":cos_2,
        "line":line,
        "parabola":parabola,
        "None": ''}

rids=input("Enter list of rid's:")
CHOOSE_FIT=input("Enter fit type:\n "+str(fits.keys())+"\n")

lst_rids = list(map(int,rids.split()))
print(lst_rids)
# extract data from hdf5 for exp 1
#lst_rids = list(rids.get().split(","))
with plt.ioff():  # for scrollwheel zoom functionality
    figure, axis = plt.subplots()

# exponential decay function
# def exp_decay(x, a, b, c):
#     return a * np.exp(-b * x) + c

# clear previous plot

plt.clf()
colorlist=plt.cm.viridis(np.linspace(0.0,1.0,len(lst_rids)))


for ii, rid in enumerate(lst_rids):
    dict_test = find_results("", rid=int(rid),
                             root_path="C:/Users/TrappedIonRice4/Documents/Artiq-Rice/results")  # returns dict of results, used to find file path
    dict_hdf5 = load_hdf5_file(dict_test[int(rid)][0])  # returns file as dict
    dict_datasets = dict_hdf5["datasets"]  # dict key where all points are stored in a nested dict

    # extracting xlabel
    scanparam_axis0=json.loads(dict_datasets['ndscan.rid_'+str(rid)+'.axes'])[0]
    unit=""
    if 'unit' in scanparam_axis0['param']['spec'].keys():
        unit='('+scanparam_axis0['param']['spec']['unit']+')'
    xlabel_axis0=scanparam_axis0['param']['description']+unit
    # assign data for exp 1 and switch point
    key_name_x = "ndscan.rid_" + str(rid) + ".points.axis_0"  # key name for duration parameter points
    key_name_y = "ndscan.rid_" + str(rid) + ".points.channel_counts"  # key name for result parameter points
    key_name_err = "ndscan.rid_" + str(rid) + ".points.channel_res_err"  # key name for error parameter points
    #print(dict_datasets)
    x_vals_1 = list(dict_datasets[key_name_x])
    # for i in range(len(x_vals_1)):
    #     x_vals_1[i]=x_vals_1[i]*10**6
    y_vals_1 = list(dict_datasets[key_name_y])
    err_vals_1 = list(dict_datasets[key_name_err])
    # x_vals_1 = np.array(x_vals_1) * 1e-3
    plt.errorbar(x_vals_1, y_vals_1,color=colorlist[ii], yerr=err_vals_1, fmt="o")
    plt.plot(x_vals_1, y_vals_1, 'X',color=colorlist[ii], label="{0:d}".format(rid))
    # plt.plot(x_vals_1, y_vals_1, 'X',color=colorlist[ii], label="Data")


    if not (CHOOSE_FIT=="None"):
        for f in fits.keys():

            if CHOOSE_FIT == f: #"exponential_decay":
                '''
                template from test_sinusoid.py of oitg/test, sinusoid here is the final object of the fitting function
                that returns popt, pcov for a set of input parameters.
                p, p_err = sinusoid.fit(t,
                                        y,
                                        y_err=np.ones(y.shape) * amp * rel_noise,
                                        evaluate_function=False,# chooses to return fitted values also or not
                                        evaluate_x_limit=[0, t_max],
                                        constants=const_dict) # to set some parameters to be constant
                
                '''
                popt, pcov, x_fit, y_fit = fits[f].fit( x_vals_1,
                                        y_vals_1,
                                         y_err=err_vals_1,
                                        evaluate_function=True
                                        #,evaluate_x_limit=[x_vals_1[0],x_vals_1[-1]],
                                        #,constants=const_dict

                                        )

                # Kabir's fit
                # popt, pcov = curve_fit(exp_decay, x_vals_1, y_vals_1, p0=(1.0, 0.1, 1.0))
                #
                # a_opt, b_opt, c_opt = popt
                #
                # # Compute tau
                # tau = 1 / b_opt
                # print(f'Tau value (Exp 1) : {tau}')
                #x_fit = np.linspace(min(x_vals_1), max(x_vals_1), 100)
                #y_fit = exp_decay(x_fit, a_opt, b_opt, c_opt)

                print(popt)
                plt.plot(x_fit, y_fit , label='Fit: ' + str(popt), color=colorlist[ii])
                # plt.plot(x_fit, y_fit, label='Fit', color=colorlist[ii])
                plt.xlabel(xlabel_axis0)
                plt.ylabel('Counts')

#disconnect_zoom = zoom_factory(axis)
#pan_handler = panhandler(figure)
#plt.xlabel('Time (μs)')  # Indicate that the x axis is in microseconds
# plt.xlabel(xlabel_axis0)
# plt.ylabel('counts')
plt.ticklabel_format(style='sci', axis='x', scilimits=(-6, -6))
plt.legend()
plt.grid(visible=True)
data = np.array([[x_vals_1, y_vals_1, err_vals_1], [x_fit, y_fit]])
np.save(r'Z:\Lab Rice\Experimental Projects\Monolithic Trap\435 measurements\Spectroscopy\radial_rsb_flopping_separatedataset', data)
plt.show()



