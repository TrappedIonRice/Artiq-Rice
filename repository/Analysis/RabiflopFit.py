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

    evol=rescale*np.sum([((nbar**(n))/((nbar+1)**(n+1)))*np.cos(np.exp(-eta**2/2)*genlaguerre(n, 0)(eta**2)\
                                                        *Omega*t/2+phi0)**2 for n in range(0,ph_N)],0) + offset
    return evol



def RSBflop (t,Omega,eta,phi0,nbar,ph_N, rescale, offset):
    # assumes pi flip
    # evol=((nbar**0)/((nbar+1)**(0+1)))*np.cos(eta*Omega*t*np.sqrt(1)/2+phi0)**2
    evol=rescale*np.sum([((nbar**(n-1))/((nbar+1)**(n)))*np.cos(eta*Omega*t*np.sqrt(n)/2+phi0)**2 for n in range(1,ph_N)],0) + offset
    return evol

def BSBflop (t,Omega,eta,phi0,nbar,ph_N, rescale, offset):
    # assumes pi flip
    # evol=((nbar**0)/((nbar+1)**(0+1)))*np.cos(eta*Omega*t*np.sqrt(1)/2+phi0)**2
    evol=rescale*np.sum([((nbar**(n))/((nbar+1)**(n+1)))*np.cos(eta*Omega*t*np.sqrt(n+1)/2+phi0)**2 for n in range(0,ph_N)],0) + offset
    return evol

def linearfit(t,a,b):
    return a*t+b

plt.close('all')

#initial values for fit
Omega0=2*np.pi*0.0454*10**6; #MHz
eta=np.sqrt(3/2/2 *3/0.9)*0.1;
eta=0.074#/np.sqrt(2)
#eta= 0.039/np.sqrt(2)

tarr=np.linspace(0,20,200)*10**(-6); # mu*s

phi0RSB=np.pi/2*0;
phi0carrier=0;
phi0BSB=0;
nbar=15
ph_N=150;
rescale=0.7
offset=0.23


heatingrate, n_init= 1000, 1000


# RSBfloparr=np.zeros(len(tarr))
# Carrierfloparr=np.zeros(len(tarr))
# BSBfloparr=np.zeros(len(tarr))



# for i in range (len(tarr)):
#     #RSBfloparr[i]=RSBflop(tarr[i], Omega0, eta,phi0RSB,nbar,ph_N)*np.random.normal(1,0.2)
#     #BSBfloparr[i]=BSBflop(tarr[i], Omega0, eta,phi0BSB,nbar,ph_N)*np.random.normal(1,0.2)
#     Carrierfloparr[i]=Carrierflop( tarr[i], Omega0, eta,phi0carrier,nbar,ph_N)*np.random.normal(1,0.2)
# RSBfloparr=RSBflop(tarr, Omega0, eta,phi0RSB,nbar,ph_N)*np.random.normal(1,0.05,size=len(tarr))
# Carrierfloparr=Carrierflop( tarr, Omega0, eta,phi0carrier,nbar,ph_N, rescale, offset)*np.random.normal(1,0.05,size=len(tarr))
# BSBfloparr=BSBflop(tarr, Omega0, eta,phi0BSB,nbar,ph_N)*np.random.normal(1,0.05,size=len(tarr))

#extracting rid data

#rid=22757#22803
rid=int(input("Enter rid (enter 0 to bypass Rabi flop fit) : "))

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
    xdata_vals_1 = np.array(list(dict_datasets[key_name_x]))
    # for i in range(len(x_vals_1)):
    #     x_vals_1[i]=x_vals_1[i]*10**6
    ydata_vals_1 = np.array(list(dict_datasets[key_name_y]))
    errydata_vals_1 = np.array(list(dict_datasets[key_name_err]))
    # x_vals_1 = np.array(x_vals_1) * 1e-3
    # plt.figure(1)
    # plt.errorbar(xdata_vals_1, ydata_vals_1, yerr=errydata_vals_1, fmt="o")
    # plt.plot(xdata_vals_1, ydata_vals_1, 'X', label="{0:d}".format(rid))


#heating rate data
phonondata = np.array([27.248, 21.407, 16.387, 47.800, 25.529, 28.746, 59.377, 47.8, 69.434])
phononerr_data = np.array([3.704, 2.830, 2.519, 8.254, 2.772, 3.880, 9.402, 8.254, 14.201])
waittime = np.array([0, 0.25, 0.5,0.5, 1, 2, 3, 6, 8]) * 10 ** -3 + np.ones(9) * 0.2 * 10 ** -3


#fitting

def carrierfitmdl(Omega0,eta,phi0carrier, nbar,ph_N,rescale,offset):
    carriermdl = Model(Carrierflop)
    carrierparams = Parameters()
    carrierparams.add('Omega', value=Omega0, min=0.01 * 2 * np.pi * 10 ** 6, max=0.1 * 2 * np.pi * 10 ** 6, vary= True)
    carrierparams.add('eta', value=eta, min=0.01, max=0.2, vary=True)
    carrierparams.add('phi0', value=phi0carrier, min=0, max=2*np.pi)
    carrierparams.add('nbar', value=nbar, min=0, max=80)
    carrierparams.add('ph_N', value=ph_N,  vary=False)
    carrierparams.add('rescale', value=rescale, min=0.01, max=20,  vary=True)
    carrierparams.add('offset', value=offset, min=-0.0, max=0.5)
    return carriermdl,carrierparams
def RSBfitmdl(Omega0,eta,phi0, nbar,ph_N,rescale,offset):
    RSBmdl = Model(RSBflop)
    RSBparams = Parameters()
    RSBparams.add('Omega', value=Omega0, min=0.01 * 2 * np.pi * 10 ** 6, max=0.2 * 2 * np.pi * 10 ** 6, vary=True)
    RSBparams.add('eta', value=eta, min=0.01, max=0.2, vary=False)
    RSBparams.add('phi0', value=phi0, min=-0, max=2*np.pi)
    RSBparams.add('nbar', value=nbar, min=0, max=30)
    RSBparams.add('ph_N', value=ph_N,  vary=False)
    RSBparams.add('rescale', value=rescale, min=0.01, max=2)
    RSBparams.add('offset', value=offset, min=-0.0, max=0.5)
    return RSBmdl, RSBparams

def BSBfitmdl(Omega0,eta,phi0, nbar,ph_N,rescale,offset):
    BSBmdl = Model(BSBflop)
    BSBparams = Parameters()
    BSBparams.add('Omega', value=Omega0, min=0.25 * 2 * np.pi * 10 ** 6, max=0.55 * 2 * np.pi * 10 ** 6, vary=True)
    BSBparams.add('eta', value=eta, min=0.01, max=0.3, vary=False )
    BSBparams.add('phi0', value=phi0, min=0, max=2*np.pi)
    BSBparams.add('nbar', value=nbar, min=0, max=10)
    BSBparams.add('ph_N', value=ph_N, vary=False)
    BSBparams.add('rescale', value=rescale, min=0.1, max=20)
    BSBparams.add('offset', value=offset, min=-0.0, max=20)
    return BSBmdl, BSBparams

def heatingrateFitmdl(heatingrate,n_init):
    heatingratemdl = Model(linearfit)
    heatingratemdlparams = Parameters()
    heatingratemdlparams.add('a', value=heatingrate, min=0, max=100000)
    heatingratemdlparams.add('b', value=n_init, min=0, max=10000)
    return heatingratemdl, heatingratemdlparams

# carriermdl=Model(Carrierflop)
# carrierparams=Parameters()
# carrierparams.add('Omega', value=Omega0,min=0.01*2*np.pi*10**6, max=1*2*np.pi*10**6)
# carrierparams.add('eta', value=eta, min=0, max=0.2)
# carrierparams.add('phi0', value=phi0carrier, min=0, max=np.pi/2)
# carrierparams.add('nbar', value=nbar, min=0,max=10)
# carrierparams.add('ph_N', value=ph_N, min=9, max= 11, vary=False)
# carrierparams.add('rescale', value=rescale, min=0.5, max=2)
# carrierparams.add('offset', value=offset, min=-0.1, max=0.5)

fitchoice=int(input("Enter fit choice (0- carrier, 1 - RSB, 2- BSB, 3- heating rate) : "))

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

elif fitchoice==1:
    RSBmdl, RSBparams = RSBfitmdl(Omega0, eta, phi0RSB, nbar, ph_N, rescale, offset)
    RSBres = RSBmdl.fit(ydata_vals_1, RSBparams, t=xdata_vals_1)
    Omegafit, etafit, phi0fit, nbarfit, rescalefit, offsetfit = RSBres.params['Omega'].value, RSBres.params[
        'eta'].value, \
                                                                RSBres.params['phi0'].value, RSBres.params[
                                                                    'nbar'].value, \
                                                                RSBres.params['rescale'].value, RSBres.params[
                                                                    'offset'].value
    Omegafit_err, etafit_err, phi0fit_err, nbarfit_err, rescalefit_err, offsetfit_err = RSBres.params[
                                                                                            'Omega'].stderr, \
                                                                                        RSBres.params['eta'].stderr, \
                                                                                        RSBres.params[
                                                                                            'phi0'].stderr, \
                                                                                        RSBres.params[
                                                                                            'nbar'].stderr, \
                                                                                        RSBres.params[
                                                                                            'rescale'].stderr, \
                                                                                        RSBres.params[
                                                                                            'offset'].stderr
    # print(
    #     'RSB fit: Omegafit={Om:3f} MHz, etafit={e:.3f}, phifit={phi:.3f}, nbarfit={nb:.3f}, rescalefit={resc:.3f}, offsetfit={offs:.3f} '.format \
    #         (Om=Omegafit / (2 * np.pi), e=etafit, phi=phi0fit, nb=nbarfit, resc=rescalefit, offs=offsetfit))

    print(RSBres.fit_report())

    pass


elif fitchoice==2:
    BSBmdl, BSBparams = BSBfitmdl(Omega0, eta, phi0BSB, nbar, ph_N, rescale, offset)
    BSBres = BSBmdl.fit(ydata_vals_1, BSBparams, t=xdata_vals_1)
    Omegafit, etafit, phi0fit, nbarfit, rescalefit, offsetfit = BSBres.params['Omega'].value, BSBres.params[
        'eta'].value, \
                                                                BSBres.params['phi0'].value, BSBres.params[
                                                                    'nbar'].value, \
                                                                BSBres.params['rescale'].value, BSBres.params[
                                                                    'offset'].value

    Omegafit_err, etafit_err, phi0fit_err, nbarfit_err, rescalefit_err, offsetfit_err = BSBres.params[
                                                                                            'Omega'].stderr, \
                                                                                        BSBres.params['eta'].stderr, \
                                                                                        BSBres.params[
                                                                                            'phi0'].stderr, \
                                                                                        BSBres.params[
                                                                                            'nbar'].stderr, \
                                                                                        BSBres.params[
                                                                                            'rescale'].stderr, \
                                                                                        BSBres.params[
                                                                                            'offset'].stderr

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
else:
    print('Invalid choice')


#plotting


plt.figure(2, figsize=(10,8))
#plt.plot(tarr,RSBfloparr, 'r', marker='o', label='RSB')

# plt.plot(tarr,Carrierfloparr, 'black',marker='o', label='Carrier')
# plt.plot(tarr,carrierres.best_fit, 'grey', linestyle='--', label='Carrier fit')

if fitchoice==0:
    # plt.errorbar(xdata_vals_1*10**6, ydata_vals_1, yerr=errydata_vals_1, fmt="o", color='black', label=r'Carrier')
    # plt.plot(xdata_vals_1*10**6,carrierres.best_fit, 'grey', linestyle='--', label=r'Carrier fit, $\Omega$ = $2\pi*${0:.2f} kHz'.format(Omegafit/(2*np.pi*10**3)))
    cmap=mpl.colormaps['plasma']
    #for i in range(20):
   # plt.figure()
    i=0.25
    color_choice=cmap(i)
    plt.errorbar(xdata_vals_1 * 10 ** 6, ydata_vals_1, yerr=errydata_vals_1, fmt="o", color=color_choice, label=r'Carrier', markersize= 9)
    plt.plot(xdata_vals_1 * 10 ** 6, carrierres.best_fit, color=color_choice, linestyle='--',linewidth=3,
             label=r'Carrier fit, $\Omega$ = $2\pi*${0:.2f} kHz'.format(Omegafit / (2 * np.pi * 10 ** 3)))
elif fitchoice==1:
    plt.errorbar(xdata_vals_1*10**6, ydata_vals_1,yerr=errydata_vals_1, fmt="o", color='red',  label=r'RSB')
    plt.plot(xdata_vals_1*10**6,RSBres.best_fit, 'red', linestyle='--', label=r'RSB fit')
elif fitchoice==2:
    plt.errorbar(xdata_vals_1*10**6, ydata_vals_1, yerr=errydata_vals_1, fmt="o", color='blue',  label=r'BSB')
    plt.plot(xdata_vals_1*10**6,BSBres.best_fit, 'blue', linestyle='--', label=r'BSB fit')
elif fitchoice==3:
    plt.errorbar(waittime * 10 ** 3, phonondata, yerr=phononerr_data, fmt="o", color='C2', label='$\overline{{n}}$')
    plt.plot(waittime * 10 ** 3, heatingrate_res.best_fit, 'C2', linestyle='--',\
             label='$ d\overline{{n}}/dt= {heatingrate:0.3f} \pm {heatingrate_err:0.3f}$ quanta/s '.format(heatingrate=heatingrate, heatingrate_err= heatingrate_err)\
                   +'\n'\
                   + ' $ \overline{{n}}_0= {n_init:0.3f} \pm {niniterr:0.3f}$ quanta'.format( n_init=n_init, niniterr=n_init_err))

#plt.plot(tarr,BSBfloparr, 'b',marker='o', label='BSB')

plt.legend(fontsize=20)
plt.grid(visible=True)

if fitchoice != 3 :
    plt.xlabel(r'time($\mu s$)', fontsize=26)
    #plt.ylabel(r'Population $|\downarrow\downarrow \rangle$')
    plt.ylabel(r'Counts', fontsize=26)
    #plt.ylim([0, 1])
    # plt.title(r'Fitted values: $ \Omega= {Omega0:.3f}  \pm  {Omega0err:.3f} kHz, \overline{{n}}={nbar:.3f}  \pm  {nbarerr:.3f},  \eta={eta:.3f} \pm {etaerr:.3f} $'\
    #           .format(Omega0=Omegafit/(2*np.pi*10**3),nbar=nbarfit,eta=etafit, Omega0err=Omegafit_err/(2*np.pi*10**3),nbarerr=nbarfit_err, etaerr=etafit_err )\
    #           +'\n'+'RID: {rid:d}'.format(rid=rid))
    plt.xticks(fontsize=20)
    plt.yticks(fontsize=20)
else:
    plt.xlabel(r'time(ms)')
    plt.ylabel(r'$\overline{{n}}$')

plt.show()


