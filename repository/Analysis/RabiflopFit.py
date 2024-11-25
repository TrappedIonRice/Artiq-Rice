# -*- coding: utf-8 -*-
"""
Created on Sun Apr 21 20:37:10 2024

@author: abhim
"""
# RSB sideband temp calc

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
# %matplotlib notebook
import scipy.special as sp
from scipy.optimize import curve_fit
from scipy.signal import savgol_filter
from scipy.special import genlaguerre
import sympy
from sympy import cos, Eq, solve, nsolve, Symbol, symbols
sympy.init_printing()
import pandas as pd
from lmfit import Model, Parameters
import json
from ndscan.experiment import *
from oitg.results import *
from oitg.fitting import *

# complete fitting routine.

def Carrierflop (t,Omega,eta,phi0,nbar,ph_N,rescale,offset):

    evol=rescale*np.sum([((nbar**(n))/((nbar+1)**(n+1)))*np.cos(np.exp(-eta**2/2)*genlaguerre(n, 0)(eta**2)*Omega*t/2+phi0)**2 for n in range(0,ph_N)],0) + offset
    return evol



def RSBflop (t,Omega,eta,phi0,nbar,ph_N, rescale, offset, gamma):
    # assumes pi flip
    # evol=((nbar**0)/((nbar+1)**(0+1)))*np.cos(eta*Omega*t*np.sqrt(1)/2+phi0)**2
    evol=rescale*np.exp(-gamma*t)*np.sum([((nbar**(n-1))/((nbar+1)**(n)))*np.cos(np.exp(-eta**2/2)*np.sqrt(np.math.factorial(n-1)/np.math.factorial(n))*genlaguerre(n-1, 1)(eta**2)*eta*Omega*t/2+phi0)**2 for n in range(1,ph_N)],0) + offset
    return evol

def BSBflop (t,Omega,eta,phi0,nbar,ph_N, rescale, offset, gamma):
    # assumes pi flip
    # evol=((nbar**0)/((nbar+1)**(0+1)))*np.cos(eta*Omega*t*np.sqrt(1)/2+phi0)**2
    evol=rescale*np.exp(-gamma*t)*np.sum([((nbar**(n))/((nbar+1)**(n+1)))*np.cos(np.exp(-eta**2/2)*np.sqrt(np.math.factorial(n)/np.math.factorial(n+1))*genlaguerre(n, 1)(eta**2)*eta*Omega*t/2+phi0)**2 for n in range(0,ph_N)],0) + offset
    return evol

def linearfit(t,a,b):
    return a*t+b

def sinusoid_decay(t,a,omega,gamma,phi0,b):
    return a*np.exp(-gamma*t)*np.sin(omega*t+phi0) + b
    
plt.close('all')

#initial values for fit
Omega0=2*np.pi*0.13067*10**6; #MHz
eta=np.sqrt(3/2/2 *3/0.9)*0.1;
eta= np.sqrt(6.626*10**-34 *(2/355*10**9)**2 /(2* 171*1.6*10**-27 * 1.7*10**6))*np.abs(np.cos(0))
eta=0.13
print(eta)
#/np.sqrt(2)
#eta= 0.039/np.sqrt(2)

tarr=np.linspace(0,40,200)*10**(-6); # mu*s

phi0RSB=np.pi;
phi0carrier=np.pi/2;
phi0BSB=np.pi/2;
nbar=4
ph_N=100;
rescale=1
offset=0.00
gamma=1000*0

heatingrate, n_init= 1000, 1000


RSBfloparr=np.zeros(len(tarr))
Carrierfloparr=np.zeros(len(tarr))
BSBfloparr=np.zeros(len(tarr))



# for i in range (len(tarr)):
#     RSBfloparr[i]=RSBflop(tarr[i], Omega0, eta,phi0RSB,nbar,ph_N, rescale, offset)*np.random.normal(1,0.2)
#     BSBfloparr[i]=BSBflop(tarr[i], Omega0, eta,phi0BSB,nbar,ph_N, rescale, offset)*np.random.normal(1,0.2)
#     Carrierfloparr[i]=Carrierflop( tarr[i], Omega0, eta,phi0carrier,nbar,ph_N, rescale, offset)*np.random.normal(1,0.2)
RSBfloparr=RSBflop(tarr, Omega0, eta,phi0RSB,nbar,ph_N, rescale, offset, gamma)*np.random.normal(1,0.05,size=len(tarr))
Carrierfloparr=Carrierflop( tarr, Omega0, eta,phi0carrier,nbar,ph_N, rescale, offset)*np.random.normal(1,0.05,size=len(tarr))
BSBfloparr=BSBflop(tarr, Omega0, eta,phi0BSB,nbar,ph_N, rescale, offset, gamma)*np.random.normal(1,0.05,size=len(tarr))

def carrierfitmdl(Omega0,eta,phi0carrier, nbar,ph_N,rescale,offset):
    carriermdl = Model(Carrierflop)
    carrierparams = Parameters()
    carrierparams.add('Omega', value=Omega0, min=0.05 * 2 * np.pi * 10 ** 6, max=0.5 * 2 * np.pi * 10 ** 6, vary= False)
    carrierparams.add('eta', value=eta, min=0.01, max=0.2, vary=False)
    carrierparams.add('phi0', value=phi0carrier, min=0, max=2*np.pi, vary=True)
    carrierparams.add('nbar', value=nbar, min=0, max=60)
    carrierparams.add('ph_N', value=ph_N,  vary=False)
    carrierparams.add('rescale', value=rescale, min=0.00, max=2,  vary=False)
    carrierparams.add('offset', value=offset, min=-1, max=1, vary= False)
    return carriermdl,carrierparams
def RSBfitmdl(Omega0,eta,phi0, nbar,ph_N,rescale,offset, gamma):
    RSBmdl = Model(RSBflop)
    RSBparams = Parameters()
    RSBparams.add('Omega', value=Omega0, min=0.05 * 2 * np.pi * 10 ** 6, max=0.4* 2 * np.pi * 10 ** 6, vary=True)
    RSBparams.add('eta', value=eta, min=0.03, max=0.15, vary=False)
    RSBparams.add('phi0', value=phi0, min=0, max=2*np.pi)
    RSBparams.add('nbar', value=nbar, min=0, max=10)
    RSBparams.add('ph_N', value=ph_N,  vary=False)
    RSBparams.add('rescale', value=rescale, min=0.01, max=2, vary=False)
    RSBparams.add('offset', value=offset, min=-0.0, max=0.5, vary=False)
    RSBparams.add('gamma', value=gamma, min=0, max=500, vary=True)
    return RSBmdl, RSBparams

def BSBfitmdl(Omega0,eta,phi0, nbar,ph_N,rescale,offset, gamma):
    BSBmdl = Model(BSBflop)
    BSBparams = Parameters()
    BSBparams.add('Omega', value=Omega0, min=0.05 * 2 * np.pi * 10 ** 6, max=0.4 * 2 * np.pi * 10 ** 6, vary=True)
    BSBparams.add('eta', value=eta, min=0.03, max=0.15, vary=False )
    BSBparams.add('phi0', value=phi0, min=0, max=2*np.pi)
    BSBparams.add('nbar', value=nbar, min=0, max=10)
    BSBparams.add('ph_N', value=ph_N, vary=False)
    BSBparams.add('rescale', value=rescale, min=0., max=2, vary=True)
    BSBparams.add('offset', value=offset, min=0, max=1, vary=False)
    BSBparams.add('gamma', value=gamma, min=0, max=100000, vary=True)
    return BSBmdl, BSBparams

def heatingrateFitmdl(heatingrate,n_init):
    heatingratemdl = Model(linearfit)
    heatingratemdlparams = Parameters()
    heatingratemdlparams.add('a', value=heatingrate, min=0, max=100000)
    heatingratemdlparams.add('b', value=n_init, min=0, max=10000)
    return heatingratemdl, heatingratemdlparams

sa=0.5
somega=2*np.pi*10**4
sgamma=2*np.pi*1000
sphi0=np.pi/2
sb=0.5
def sinusoid_decayFitmdl(a,omega,gamma,phi0,b):
    sinusoid_decayFitmdl = Model(sinusoid_decay)
    sinusoid_decayFitmdlparams = Parameters()
    sinusoid_decayFitmdlparams.add('a', value=0.5, min=-1, max=1)
    sinusoid_decayFitmdlparams.add('omega', value=100, min=100, max=10**6)
    sinusoid_decayFitmdlparams.add('gamma', value=5000, min=0, max=60000)
    sinusoid_decayFitmdlparams.add('phi0', value=0.2, min=0, max=2*np.pi)
    sinusoid_decayFitmdlparams.add('b', value=0.5, min=-1, max=1)
    return sinusoid_decayFitmdl, sinusoid_decayFitmdlparams

#extracting rid data

#rid=64605#22757#22803
#rid=int(input("Enter rid (enter 0 to bypass Rabi flop fit) : "))
rids=input("Enter rids (enter 0 to bypass Rabi flop fit) : ")
lst_rids = list(map(int,rids.split()))

i=0
for i,rid in enumerate(lst_rids):

    if rid:
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
        cutoff=35
        xdata_vals_1 = np.array(list(dict_datasets[key_name_x]))[:cutoff]
        # for i in range(len(x_vals_1)):
        #     x_vals_1[i]=x_vals_1[i]*10**6
        ydata_vals_1 = np.array(list(dict_datasets[key_name_y]))[:cutoff]
        errydata_vals_1 = np.array(list(dict_datasets[key_name_err]))[:cutoff]
        # x_vals_1 = np.array(x_vals_1) * 1e-3
        # plt.figure(1)
        # plt.errorbar(xdata_vals_1, ydata_vals_1, yerr=errydata_vals_1, fmt="o")
        # plt.plot(xdata_vals_1, ydata_vals_1, 'X', label="{0:d}".format(rid))

    #fitting

    #heating rate data #may 2024
    # phonondata = np.array([27.248, 21.407, 16.387, 47.800, 25.529, 28.746, 59.377, 47.8, 69.434])
    # phononerr_data = np.array([3.704, 2.830, 2.519, 8.254, 2.772, 3.880, 9.402, 8.254, 14.201])
    # waittime = np.array([0, 0.25, 0.5,0.5, 1, 2, 3, 6, 8]) * 10 ** -3 + np.ones(9) * 0.2 * 10 ** -3

    # full data, 2024/10/15
    phonondata = np.array([37.91, 43.85, 46.63, 50.64])
    phononerr_data = np.array([ 2.35 , 2.54 , 2.60, 2.62])

    # truncated data to half,  2024/10/15
    phonondata = np.array([30.78, 38.12, 40.53, 44.41])
    phononerr_data = np.array([1.94 , 2.64 , 2.63, 3.01])

    # truncated data to half 2024/10/25
    phonondata = np.array([27.19, 30.22, 32.17, 34.70, 32.66, 28.60, 32.42, 35.79 ])
    phononerr_data = np.array([1.60 , 1.61 , 1.90, 2.23, 1.76, 1.60, 1.78, 2.16 ])
    waittime = np.array([0, 1, 2,3,1.5,0.5,1.5,3 ]) * 10 ** -3

    # truncated data to half 2024/10/24
    phonondata = np.array([24.13, 30.66,35.35, 39.79  ])
    phononerr_data = np.array([1.20, 1.91, 2.86, 2.92  ])
    waittime = np.array([0, 1, 2, 3 ]) * 10 ** -3


    # truncated data to half 2024/10/28
    phonondata = np.array([21.10, 28.81, 35.61,35.33, 36.24, 32.60, 29.08,25.20   ])
    phononerr_data = np.array([1.28, 1.74, 2.55, 3.18, 2.49, 2.31, 2.09, 1.57  ])
    waittime = np.array([0,1,3,5,4,2,1,0.5]) * 10 ** -3

    # truncated to 3ms, 2024/10/28
    phonondata = np.array([21.10, 28.81, 35.61,  32.60, 29.08,25.20   ])
    phononerr_data = np.array([1.28, 1.74, 2.55,  2.31, 2.09, 1.57  ])
    waittime = np.array([0,1,3,2,1,0.5]) * 10 ** -3

    # after stabilizing 369 laser, 2024/10/30
    phonondata = np.array([ 17.14,22.65 , 25.44 , 26.74])
    phononerr_data = np.array([0.91, 1.63 , 1.92, 2.37])
    waittime = np.array([0,1,2,3]) * 10 ** -3

    # 2024/11/8, OC1 2MHz
    phonondata = np.array([0.84,1.47,1.61,2.22,2.52, 3.06])
    phononerr_data = np.array([0.14,0.22,0.3,0.33,0.40, 0.49])
    waittime = np.array([0, 1, 1.5, 2, 2.5, 3]) * 10 ** -3

    # 2024/11/8, IC1 1.5MHz
    phonondata = np.array([1.71, 2.87, 3.11, 4.00, 5.50, 6.10])
    phononerr_data = np.array([0.27, 0.45, 0.60, 0.60, 1.11, 1.00])
    waittime = np.array([0, 0.25, 0.35,0.5,  0.75, 1]) * 10 ** -3

    #2024/11/9, OC1 3 MHz
    phonondata = np.array([0.43, 1.27, 1.36, 2.19, 1.76, 2.65])
    phononerr_data = np.array([0.06, 0.14,0.21, 0.31, 0.32, 0.49])
    waittime = np.array([0, 1, 1.5, 2, 2.5, 3]) * 10 ** -3

    # 2024/11/11, Carrier 3 MHz v1
    phonondata = np.array([19.07, 27.69, 38.98])# 41.10, 43.40])
    phononerr_data = np.array([1.61, 2.17, 2.7])#, 2.82, 3.59])
    waittime = np.array([0, 0.5, 1]) * 10 ** -3 # 2,3])*10**-3

    # 2024/11/11, Carrier 3 MHz v2
    phonondata = np.array([19.59, 22.69, 28.78, 27.05, 34.29, 42.72])  # 41.10, 43.40])
    phononerr_data = np.array([1.29, 1.85, 2.35, 2.18, 2.37, 2.91])  # , 2.82, 3.59])
    waittime = np.array([0, 0.25, 0.5, 0.75, 1,2]) * 10 ** -3  # 2,3])*10**-3
    ########################
    # 2024/11/12, Carrier, 2 MHz
    phonondata = np.array([15.05, 18.88, 20.58, 24.02, 28.65])
    phononerr_data = np.array([1.44, 1.36, 1.38, 1.93, 2.06])
    waittime = np.array([0, 1, 2, 3,4]) * 10 ** -3

    # 2024/11/12 IC1 Twist=-2.5
    phonondata = np.array([2.32, 5.02, 9.6, 3.08, 5.91])
    phononerr_data = np.array([0.33, 1.21, 1.6, 0.46, 1.01])
    waittime = np.array([0, 0.5, 1, 0.25, 0.75]) * 10 ** -3



    # 2024/11/12 IC1 Twist=-1.5
    # phonondata = np.array([2.17, 3.26, 3.91, 5.21, 3.01])
    # phononerr_data = np.array([0.31, 0.44, 0.7, 0.89, 0.54])
    # waittime = np.array([0, 0.5, 0.25, 1, 0.15]) * 10 ** -3

    # 2024/11/12 OC1 Twist=-1.5
    # phonondata = np.array([0.72, 1.01, 1.59, 1.68, 3.23])
    # phononerr_data = np.array([0.13, 0.18, 0.35, 0.28, 0.75])
    # waittime = np.array([0, 0.5, 1, 2, 3]) * 10 ** -3

    # 2024/11/12 Carrier Twist=-1.5
    # phonondata = np.array([13.11, 14.32, 13.91, 18.13, 21.65, 26.19])
    # phononerr_data = np.array([1.01, 1.39, 1.08, 1.86, 2.02, 1.92])
    # waittime = np.array([0, 0.25, 0.5, 1, 2, 3]) * 10 ** -3

    # 2024/11/12 Carrier Twist=-3.5
    # phonondata = np.array([20.59, 22.74, 26.36, 29.84, 31.00])
    # phononerr_data = np.array([2.10, 2.24, 2.11, 2.34, 2.23])
    # waittime = np.array([0, 0.5, 1, 2, 3]) * 10 ** -3

    # 2024/11/12 OC1 Twist=-3.5
    # phonondata = np.array([1.61, 2.01, 2.28, 2.02])
    # phononerr_data = np.array([0.25, 0.28, 0.37, 0.29])
    # waittime = np.array([0, 0.5, 1, 0.25]) * 10 ** -3

    # 2024/11/12 IC1 Twist=-3.5
    # phonondata = np.array([2.67, 4.36, 2.51, 3.00])
    # phononerr_data = np.array([0.41, 1.03, 0.52, 0.51])
    # waittime = np.array([0, 0.25, 0.10, 0.05]) * 10 ** -3

    # 2024/11/13 Carrier Twist=-1.5
    phonondata = np.array([19.63, 26.80, 33.84, 36.49, 43.25 ])
    phononerr_data = np.array([1.70, 2.20, 2.28, 2.37, 2.41 ])
    waittime = np.array([0, 1,2,3,4]) * 10 ** -3

    # 2024/11/13 Carrier EndcapX=0.6
    phonondata = np.array([16.75, 23.11, 28.76, 30.12])
    phononerr_data = np.array([1.6, 1.35, 3.29, 3.12])
    waittime = np.array([0, 1, 2, 3]) * 10 ** -3

    # 2024/11/13 Carrier EndcapX=2
    phonondata = np.array([18.35, 27, 31.10,38.77])
    phononerr_data = np.array([1.6, 3.17, 2.84, 2.93])
    waittime = np.array([0, 1, 2, 3]) * 10 ** -3

    # 2024/11/14 Carrier EndcapX=2
    phonondata = np.array([12.85, 17.17, 20.93 ,27.56])
    phononerr_data = np.array([1.2, 1.88, 1.95, 2.36])
    waittime = np.array([0, 1, 2, 3]) * 10 ** -3

    # 2024/11/19 Carrier
    phonondata = np.array([12.98, 18.48, 23.80,26.08 ,30.55])
    phononerr_data = np.array([0.86, 1.50, 1.44, 1.90,1.90])
    waittime = np.array([0, 1, 2, 3,4]) * 10 ** -3

    # 2024/11/19 Carrier
    phonondata = np.array([15.32, 21.65, 27.81, 30.20 ,32.75])
    phononerr_data = np.array([0.93, 2.33, 1.68, 2.28,2.34])
    waittime = np.array([0, 1, 2, 3,4]) * 10 ** -3

    # plt.figure(2, figsize=(10,8))
    # plt.plot(tarr,RSBfloparr, 'r', marker='o', label='RSB')
    # plt.plot(tarr,Carrierfloparr, 'black',marker='o', label='Carrier')
    # plt.plot(tarr,BSBfloparr, 'b',marker='o', label='BSB')



    # carriermdl=Model(Carrierflop)
    # carrierparams=Parameters()
    # carrierparams.add('Omega', value=Omega0,min=0.01*2*np.pi*10**6, max=1*2*np.pi*10**6)
    # carrierparams.add('eta', value=eta, min=0, max=0.2)
    # carrierparams.add('phi0', value=phi0carrier, min=0, max=np.pi/2)
    # carrierparams.add('nbar', value=nbar, min=0,max=10)
    # carrierparams.add('ph_N', value=ph_N, min=9, max= 11, vary=False)
    # carrierparams.add('rescale', value=rescale, min=0.5, max=2)
    # carrierparams.add('offset', value=offset, min=-0.1, max=0.5)

    fitchoice=3

    #fitchoice=int(input("Enter fit choice (0- carrier, 1 - RSB, 2- BSB, 3- heating rate) : "))

    if fitchoice==0:

        carriermdl,carrierparams=carrierfitmdl(Omega0,eta,phi0carrier, nbar,ph_N,rescale,offset)
        carrierres=carriermdl.fit(ydata_vals_1,carrierparams,t=xdata_vals_1)
        #carrierres=carriermdl.fit(Carrierfloparr,carrierparams,t=tarr)

        Omegafit,etafit, phi0fit, nbarfit, rescalefit, offsetfit=carrierres.params['Omega'].value, carrierres.params['eta'].value,\
                                                                 carrierres.params['phi0'].value, carrierres.params['nbar'].value,\
                                                                 carrierres.params['rescale'].value, carrierres.params['offset'].value

        Omegafit_err, etafit_err, phi0fit_err, nbarfit_err, rescalefit_err, offsetfit_err = carrierres.params['Omega'].stderr, carrierres.params['eta'].stderr, \
                                                                    carrierres.params['phi0'].stderr, carrierres.params['nbar'].stderr, \
                                                                    carrierres.params['rescale'].stderr, carrierres.params['offset'].stderr

        # print('Carrier fit: Omegafit={Om:3f} MHz, etafit={e:.3f}, phifit={phi:.3f}, nbarfit={nb:.3f}, rescalefit={resc:.3f}, offsetfit={offs:.3f} '.format\
        #           (Om=Omegafit/(2*np.pi),e=etafit, phi=phi0fit, nb=nbarfit, resc=rescalefit, offs=offsetfit))
        print(carrierres.fit_report())
        pass

    elif fitchoice==1:
        RSBmdl, RSBparams = RSBfitmdl(Omega0, eta, phi0RSB, nbar, ph_N, rescale, offset, gamma)
        RSBres = RSBmdl.fit(ydata_vals_1, RSBparams, t=xdata_vals_1)
        Omegafit, etafit, phi0fit, nbarfit, rescalefit, offsetfit, gammafit = RSBres.params['Omega'].value, RSBres.params[
            'eta'].value, \
                                                                    RSBres.params['phi0'].value, RSBres.params[
                                                                        'nbar'].value, \
                                                                    RSBres.params['rescale'].value, RSBres.params[
                                                                        'offset'].value, \
                                                                    RSBres.params['gamma'].value
        Omegafit_err, etafit_err, phi0fit_err, nbarfit_err, rescalefit_err, offsetfit_err, gammafit_err= RSBres.params[
                                                                                                'Omega'].stderr, \
                                                                                            RSBres.params['eta'].stderr, \
                                                                                            RSBres.params[
                                                                                                'phi0'].stderr, \
                                                                                            RSBres.params[
                                                                                                'nbar'].stderr, \
                                                                                            RSBres.params[
                                                                                                'rescale'].stderr, \
                                                                                            RSBres.params[
                                                                                                'offset'].stderr, \
                                                                                            RSBres.params['gamma'].stderr
        # print(
        #     'RSB fit: Omegafit={Om:3f} MHz, etafit={e:.3f}, phifit={phi:.3f}, nbarfit={nb:.3f}, rescalefit={resc:.3f}, offsetfit={offs:.3f} '.format \
        #         (Om=Omegafit / (2 * np.pi), e=etafit, phi=phi0fit, nb=nbarfit, resc=rescalefit, offs=offsetfit))

        print(RSBres.fit_report())

        pass


    elif fitchoice==2:
        BSBmdl, BSBparams = BSBfitmdl(Omega0, eta, phi0BSB, nbar, ph_N, rescale, offset, gamma)
        BSBres = BSBmdl.fit(ydata_vals_1, BSBparams, t=xdata_vals_1)
        Omegafit, etafit, phi0fit, nbarfit, rescalefit, offsetfit, gammafit = BSBres.params['Omega'].value, BSBres.params[
            'eta'].value, \
                                                                    BSBres.params['phi0'].value, BSBres.params[
                                                                        'nbar'].value, \
                                                                    BSBres.params['rescale'].value, BSBres.params[
                                                                        'offset'].value, \
                                                                    BSBres.params['gamma'].value

        Omegafit_err, etafit_err, phi0fit_err, nbarfit_err, rescalefit_err, offsetfit_err, gammafit_err = BSBres.params[
                                                                                                'Omega'].stderr, \
                                                                                            BSBres.params['eta'].stderr, \
                                                                                            BSBres.params[
                                                                                                'phi0'].stderr, \
                                                                                            BSBres.params[
                                                                                                'nbar'].stderr, \
                                                                                            BSBres.params[
                                                                                                'rescale'].stderr, \
                                                                                            BSBres.params[
                                                                                                'offset'].stderr, \
                                                                                            BSBres.params['gamma'].stderr


        # print(
        #     'BSB fit: Omegafit={Om:3f} MHz, etafit={e:.3f}, phifit={phi:.3f}, nbarfit={nb:.3f}, rescalefit={resc:.3f}, offsetfit={offs:.3f} '.format \
        #         (Om=Omegafit / (2 * np.pi), e=etafit, phi=phi0fit, nb=nbarfit, resc=rescalefit, offs=offsetfit))

        print(BSBres.fit_report())
        pass

    elif fitchoice ==3:

        heatingratemdl,heatingratemdlparams = heatingrateFitmdl(heatingrate, n_init)
        heatingrate_res=heatingratemdl.fit(phonondata,heatingratemdlparams,t=waittime)

        heatingrate, heatingrate_err, n_init, n_init_err= heatingrate_res.params['a'].value,\
                                                          heatingrate_res.params['a'].stderr, \
                                                          heatingrate_res.params['b'].value, \
                                                          heatingrate_res.params['b'].stderr
        print(heatingrate_res.fit_report())

    elif fitchoice ==4:

        sinusoid_decayFitmdl,sinusoid_decayFitmdlparams = sinusoid_decayFitmdl(sa,somega,sgamma,sphi0,sb)
        sinusoid_decayFit_res=sinusoid_decayFitmdl.fit(ydata_vals_1,sinusoid_decayFitmdlparams,t=xdata_vals_1)


        print(sinusoid_decayFit_res.fit_report())
    else:
        print('Invalid choice')


    #plotting




    #plt.plot(tarr,carrierres.best_fit, 'grey', linestyle='--', label='Carrier fit')
    plt.figure()
    if fitchoice==0 or fitchoice==4:
        # plt.errorbar(xdata_vals_1*10**6, ydata_vals_1, yerr=errydata_vals_1, fmt="o", color='black', label=r'Carrier')
        # plt.plot(xdata_vals_1*10**6,carrierres.best_fit, 'grey', linestyle='--', label=r'Carrier fit, $\Omega$ = $2\pi*${0:.2f} kHz'.format(Omegafit/(2*np.pi*10**3)))
        cmap=mpl.colormaps['plasma']
        #for i in range(20):
       # plt.figure()
        #i=0.25
        color_choice=cmap(i/4.0)
        plt.errorbar(xdata_vals_1 * 10 ** 6, ydata_vals_1, yerr=errydata_vals_1, fmt="o-", color=color_choice,markersize= 9, label='Carrier flop, rid: {0:d}'.format(rid))
       # plt.plot(xdata_vals_1 * 10 ** 3, sinusoid_decayFit_res.best_fit, color=color_choice, linestyle='--', linewidth=3) # only plotting fit, no label
        plt.plot(xdata_vals_1 * 10 ** 6, carrierres.best_fit, color=color_choice, linestyle='--',linewidth=3,
                label='Carrier fit, $\Omega$ = $2\pi*${0:.2f} kHz, $\overline{{n}}$= {1:.2f} $\pm$ {2:.2f}'.format(Omegafit / (2 * np.pi * 10 ** 3), nbarfit, nbarfit_err))
                # label='$\overline{{n}}$= {1:.2f} $\pm$ {2:.2f}'.format(Omegafit / (2 * np.pi * 10 ** 3), nbarfit, nbarfit_err))
    elif fitchoice==1:
        plt.errorbar(xdata_vals_1*10**6, ydata_vals_1,yerr=errydata_vals_1, fmt="o", color='red',  label='RSB, rid: {0:d}'.format(rid))
        plt.plot(xdata_vals_1*10**6,RSBres.best_fit, 'red', linestyle='--',
                 label='RSB fit, $\Omega$ = $2\pi*${0:.2f} kHz, \n $\overline{{n}}$= {1:.2f} $\pm$ {2:.2f}, \n $\gamma$= {3:.3f} kHz'.format(Omegafit / (2 * np.pi * 10 ** 3), nbarfit, nbarfit_err, gammafit/(2*np.pi * 10 ** 3)))
    elif fitchoice==2:
        plt.errorbar(xdata_vals_1*10**6, ydata_vals_1, yerr=errydata_vals_1, fmt="o", color='blue',  label='BSB fit, rid: {0:d}'.format(rid))
        plt.plot(xdata_vals_1*10**6,BSBres.best_fit, 'blue', linestyle='--',
            label = 'RSB fit, $\Omega$ = $2\pi*${0:.2f} kHz,\n $\overline{{n}}$= {1:.2f} $\pm$ {2:.2f}, \n $\gamma$= {3:.3f} kHz'.format(Omegafit / (2 * np.pi * 10 ** 3), nbarfit, nbarfit_err, gammafit/(2*np.pi * 10 ** 3)) )
    elif fitchoice==3:
        plt.errorbar(waittime * 10 ** 3, phonondata, yerr=phononerr_data, fmt="o", color='C2', label='$\overline{{n}}$')
        plt.plot(waittime * 10 ** 3, heatingrate_res.best_fit, 'C2', linestyle='-',\
                 label='$ d\overline{{n}}/dt= {heatingrate:0.3f} \pm {heatingrate_err:0.3f}$ quanta/s '.format(heatingrate=heatingrate, heatingrate_err= heatingrate_err)\
                       +'\n'\
                       + ' $ \overline{{n}}_0= {n_init:0.3f} \pm {niniterr:0.3f}$ quanta'.format( n_init=n_init, niniterr=n_init_err))





    if fitchoice != 3 :
        plt.xlabel(r'time($\mu$s)', fontsize=20)
        #plt.ylabel(r'Population $|\downarrow\downarrow \rangle$')
        plt.ylabel(r'Counts', fontsize=20)
        #plt.ylim([0, 1])
        # plt.title(r'Fitted values: $ \Omega= {Omega0:.3f}  \pm  {Omega0err:.3f} kHz, \overline{{n}}={nbar:.3f}  \pm  {nbarerr:.3f},  \eta={eta:.3f} \pm {etaerr:.3f} $'\
        #           .format(Omega0=Omegafit/(2*np.pi*10**3),nbar=nbarfit,eta=etafit, Omega0err=Omegafit_err/(2*np.pi*10**3),nbarerr=nbarfit_err, etaerr=etafit_err )\
        #           +'\n'+'RID: {rid:d}'.format(rid=rid))
        plt.xticks(fontsize=15)
        plt.yticks(fontsize=15)
    else:
        plt.xlabel(r'time(ms)', fontsize=20)
        plt.ylabel(r'$\overline{{n}}$', fontsize=20)
        plt.xticks(fontsize=15)
        plt.yticks(fontsize=15)

    plt.legend(fontsize=15, loc='upper right')
    plt.grid(visible=True)
    plt.show()


