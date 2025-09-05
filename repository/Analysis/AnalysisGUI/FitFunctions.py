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

    def activateFit(self, xvals, yvals):

        #def RSBfitmdl(Omega0, eta, phi0, nbar, ph_N, rescale, offset, gamma):
        self.mdl = Model(self.fitFunction)
        self.fitparams = Parameters()
        for i in range(self.num_params):
            self.fitparams.add(self.params2Dlist[i][1],
                               value=self.params2Dlist[i][2],
                               min= self.params2Dlist[i][4],
                               max=self.params2Dlist[i][5],
                               vary=self.params2Dlist[i][0])
        self.fitres=self.mdl.fit(yvals, self.fitparams, x=xvals)
        for i in range(self.num_params):
            self.params2Dlist[i][3]=self.fitres.params[self.params2Dlist[i][1]].value # setting the fit value to the 4th column of the 2D param list
        #carrierres.params['Omega']
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
                            [True,"A",1,0.1, -10,10],
                            [True,"B",0,0.1, -10,10]
                            ]
        self.description="A*x+B"

    def fitFunction(self, x, A,B):
        return A*x+B
    def functionPlot(self, xvals):
        arglist_val=tuple([self.params2Dlist[i][2] for i in range(self.num_params)])
        return self.fitfunction(xvals, *arglist_val)

class parabolaFit(FitObject):
    def __init__(self):
        super(parabolaFit, self).__init__()
        self.num_params = 3
        self.params2Dlist= [
                            [True,"A",1,0.1, -10,10],
                            [True,"x0", 0, 0.1, -10, 10],
                            [True,"B",0,0.1, -10,10]
                            ]
        self.description="A*(x-x0)^2+B"

    def fitFunction(self, x, A,x0,B):
        return A*(x-x0)**2+B

class exponentialFit(FitObject):
    def __init__(self):
        super(exponentialFit, self).__init__()
        self.num_params = 4
        self.params2Dlist= [
                            [True,"A",-30,0.1, -100,100],
                            [True,"tau",0,0.1, -100,100],
                            [True, "x0", 0, 0.1, -100,100],
                            [True,"B",30,0.1, 0,40]
                            ]
        self.description="A*exp(-(x-x0)/tau)+B"

    def fitFunction(self, x, A,tau,x0,B):
        return A*np.exp(-(x-x0)/tau)+B

class cos2decayFit(FitObject):
    def __init__(self):
        super(cos2decayFit, self).__init__()
        self.num_params = 5
        self.params2Dlist= [
                            [True,"A",1,0.1, -100,100],
                            [True,"tau",1,0.1, -100,100],
                            [True,"k", 1, 0.1, -100, 100],
                            [True,"phi0", 1, 0.1, -100,100],
                            [True,"B",0,0.1, -100,100]
                            ]
        self.description ="A*exp(-x/tau)*cos(2*pi*k*x+phi0)^2+B"

    def fitFunction(self, x, A,tau,k,phi0,B):
        return A*np.exp(-x/tau)*np.cos(2*np.pi*k*x+phi0)**2+B

class sinusoidFit(FitObject):
    def __init__(self):
        super(sinusoidFit, self).__init__()
        self.num_params = 4
        self.params2Dlist= [
                            [True,"A",1,0.1, -100,100],
                            [True,"k", 1, 0.1, -100, 100],
                            [True,"phi0", 1, 0.1, -100,100],
                            [True,"B",0,0.1, -100,100]
                            ]
        self.description ="A*sin(2*pi*k*x+phi0)+B"

    def fitFunction(self, x, A,k,phi0,B):
        return A*np.sin(2*np.pi*k*x+phi0)+B

class gaussianFit(FitObject):
    def __init__(self):
        super(gaussianFit, self).__init__()
        self.num_params = 4
        self.params2Dlist= [
                            [True,"A",1,0.1, -100,100],
                            [True,"sigma",0.1,0.1, -100,100],
                            [True,"x0", 0, 0.1, -100,100],
                            [True,"B",0,0.1, -100,100]
                            ]
        self.description ="A*exp(-(x-x0)^2/(2*sigma^2))+B"

    def fitFunction(self, x, A,sigma,x0,B):
        return A*np.exp(-(x-x0)**2/(2*sigma**2))+B

class lorentzianFit(FitObject):
    def __init__(self):
        super(lorentzianFit, self).__init__()
        self.num_params = 4
        self.params2Dlist= [
                            [True,"A",1,0.1, -100,100],
                            [True,"C",0.1,0.1, -100,100],
                            [True,"x0", 0, 0.1, -100,100],
                            [True,"B",0,0.1, -100,100]
                            ]
        self.description ="A/(1+((x-x0)/C))^2)+B"

    def fitFunction(self, x, A,C,x0,B):
        return A/(1+((x-x0)/C)**2)+B

class carrierFlopFit(FitObject):
    def __init__(self):
        super(carrierFlopFit, self).__init__()
        self.num_params = 8
        self.params2Dlist= [
                            [True,"Omega",1,0.1, -100,100],
                            [True,"eta",0.1,0.1, 0,0.5],
                            [True,"phi0", 0, 0.1, -100,100],
                            [True,"nbar",1,0.1, 0,30],
                            [False, "ph_N", 20, 0, -100, 100],
                            [False, "rescale", 1, 0.1, -100, 100],
                            [False, "offset", 0, 0.1, -100, 100],
                            [False, "gamma", 10**6, 0.1, 0, 10**7]
                            ]
        self.description ="Carrier Rabi flop with Laguerre polynomials and dephasing"


    def fitFunction(self, x,Omega,eta,phi0,nbar,ph_N,rescale,offset,gamma):
        evol = rescale * np.exp(-gamma*x) * np.sum([((nbar ** (n)) / ((nbar + 1) ** (n + 1))) * np.cos(
            np.exp(-eta ** 2 / 2) * genlaguerre(n, 0)(eta ** 2) * 2 * np.pi * Omega * x / 2 + phi0) ** 2 for n in range(0, int(ph_N))],
                                0) + offset
        return evol


class RSBFlopFit(FitObject):
    def __init__(self):
        super(RSBFlopFit, self).__init__()
        self.num_params = 8
        self.params2Dlist = [
            [True, "Omega", 1, 0.1, -100, 100],
            [True, "eta", 0.1, 0.1, 0, 0.5],
            [True, "phi0", 0, 0.1, -100, 100],
            [True, "nbar", 1, 0.1, 0, 30],
            [False, "ph_N", 20, 0, -100, 100],
            [False, "rescale", 1, 0.1, -100, 100],
            [False, "offset", 0, 0.1, -100, 100],
            [False, "gamma", 10 ** 6, 0.1, 0, 10 ** 7]
        ]
        self.description = "RSB Rabi flop with Laguerre polynomials and dephasing"

    def fitFunction(self, x, Omega, eta, phi0, nbar, ph_N, rescale, offset, gamma):
        evol = rescale * np.exp(-gamma * x) * np.sum([((nbar ** (n - 1)) / ((nbar + 1) ** (n))) * np.cos(
            np.exp(-eta ** 2 / 2) * np.sqrt(np.math.factorial(n - 1) / np.math.factorial(n)) * genlaguerre(n - 1, 1)(
                eta ** 2) * 2 * np.pi * eta * Omega * x / 2 + phi0) ** 2 for n in range(1,int(ph_N))], 0) + offset
        return evol

class BSBFlopFit(FitObject):
    def __init__(self):
        super(BSBFlopFit, self).__init__()
        self.num_params = 8
        self.params2Dlist = [
            [True, "Omega", 1, 0.1, -100, 100],
            [True, "eta", 0.1, 0.1, 0, 0.5],
            [True, "phi0", 0, 0.1, -100, 100],
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
    'sinusoid': sinusoidFit(),
    'lorentzian': lorentzianFit(),
    'CarrierFlopfit':carrierFlopFit(),
    'RSBFlopfit':RSBFlopFit(),
    'BSBFlopfit':BSBFlopFit()
}

        #return RSBmdl, RSBparams

