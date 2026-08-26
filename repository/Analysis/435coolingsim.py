
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# %matplotlib notebook
import scipy.special as sp
from scipy.optimize import curve_fit
from scipy.signal import savgol_filter
from scipy.special import genlaguerre
import sympy
from sympy import cos, Eq, solve, nsolve, Symbol, symbols, Matrix, solve_linear_system
sympy.init_printing()
import cmath
import pandas as pd
from lmfit import Model, Parameters
import json
from ndscan.experiment import *
from oitg.results import *
from oitg.fitting import *

G935, G297, O21, O20, O10, D10 = symbols('G935 G297 O21 O20 O10 D10')
r22, r21, r20, r12, r11, r10, r02, r01, r00 = symbols('r22 r21 r20 r12 r11 r10 r02 r01 r00')

OBEmatrix = [[-0.5*(G935 + G297), 
   0+1j*O21/2, 0, 0-1j*O21/2, 0, 0, 0, 0, 0],
  [1j*O21/2, -0.5*(G935 + G297), 0,
   0, -1j*O21/2, 0, 1j*O10/2, 0, 0],
  [0, 1j*O10/
     2, -0.5*(G935 + G297), 0, 
   0, -1j*O21/2, 1j*D10, 0, 0 ],
  [-1j*O21/2, 
   0, -1j*O10/
     2, -0.5*(G935 + G297), 
   1j*O21/2, 0, 0, 0, 0 ],
  [G935, -1j*O21/2, 0, 
   1j*O21/2, 0, -1j*O10/2, 0, 
   1j*O10/2, 0],
  [0, 0, -1j*O21/2, 0, 1j*O10/2, 0, 0, 
   1j*D10, -1j*O10/2],
  [0, 0, -1j* D10/2, -1j* O10/2, 
   0, -0.5*(G935 + G297), 0, 
   1j*O21/2, 0],
  [0, 0, 0, 0, -1j*O10/2, -1j*D10, 
   1j*O21/2, 0, 1j*O10/2],
  [G297, 0, 0, 0, 0, 1j*O10/2, 
   0 , -1j*O10/2, 0]]

sympyOBE=Matrix(OBEmatrix)
print(OBEmatrix)
print(sympyOBE)
print(sympyOBE.solve(Matrix([0,0,0,0,0,0,0,0,0])))