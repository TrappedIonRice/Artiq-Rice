from ndscan.experiment import *
from oitg.results import *
import numpy as np
from statistics import stdev
from math import *


import h5py
filename = r"C:\Artiq\artiq_new_installation\results\2023-10-16\15\000006562-executeScan.h5"

with h5py.File(filename, "r") as f:
    # Print all root level object names (aka keys)
    # these can be group or dataset names
    print("Keys: %s" % f.keys())
    keylist= list(f.keys())
    # data=f[keylist]
    # print(data[()])
h5file=load_hdf5_file(filename)
print(h5file)
print(h5file['archive'])
print(h5file['datasets'])
#print(h5file['rid'])
print(h5file['expid'])
#     # data=list(f[keylist])
#     # print(f[keylist()])

parentdir=r"C:\Artiq\artiq_new_installation"
datasetdir=parentdir+"\dataset_db.pyon"
datasetkeylist=[]
with open(datasetdir,'r') as f:
    txt=f.readlines()
    #print(txt)
    for ele in txt[1:-1]:
        ele2=ele.split(":")
        ele3=(ele2[0].split('    '))[-1]
        # print(''.join(list(ele3)[1:-1]))
        # datasetkeylist.append(ele3)
        # print(ele3)