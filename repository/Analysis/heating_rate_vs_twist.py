from matplotlib import pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from scipy.optimize import curve_fit
m=170.936*1.660539*10**-27
Q=1.602*10**-19
h=6.626*10**-34

'''
# 2025/07/04 data
# innerfreq=192.487473-np.array([189.328168,189.721056,190.169147,190.633567 ])
# outerfreq=192.487473-np.array([189.088465,189.45906,189.865999, 190.270807 ])
# SEscalingfactor=4*m*h/(Q**2)
#
# inner_heatingrate=np.array([123.75, 28.2, 112.715, 1389.5])*SEscalingfactor*innerfreq*10**6
# inner_heatingrate_err=np.array([14.7, 3.18, 20.357, 119.3])*SEscalingfactor*innerfreq*10**6
# outer_heatingrate=np.array([25.1, 14.6, 12.03, 31.9])*SEscalingfactor*outerfreq*10**6
# outer_heatingrate_err=np.array([2.9,3.85, 3.08, 4.6])*SEscalingfactor*outerfreq*10**6

# 2025/07/21-22 data
# twist=np.array([-2,-4,-1,1,2,4])
# innerfreq=192.498275-np.array([189.842143, 189.985821, 189.771117,189.775570, 189.846065,189.992903 ])
# outerfreq=192.498275-np.array([189.570232, 189.442429, 189.636238,189.630094, 189.565595,189.438575 ])
# SEscalingfactor=4*m*h/(Q**2)
# 
# inner_heatingrate=np.array([12.7*0+14.702, 20.789, 12.965, 5.143, 3.832, 3.804])#*SEscalingfactor*innerfreq*10**6
# inner_heatingrate_err=np.array([1.802*0+1.470, 1.364, 1.24, 0.416, 0.244, 0.481])#*SEscalingfactor*innerfreq*10**6
# outer_heatingrate=np.array([3.67*0+1.076, 1.474, 1.193, 8.037, 14.316, 7.674])#*SEscalingfactor*outerfreq*10**6
# outer_heatingrate_err=np.array([0.27*0 + 0.434, 0.353, 0.263, 1.4101, 0.693, 1.647])#*SEscalingfactor*outerfreq*10**6

# CarrierRabi= 222.81#kHz
# IC_SBCRabi=1/(2*np.array([])) #kHz
# OC_SBCRabi=1/(2*np.array([30])) #kHz

# IC_SBCeta=np.array([0.085, 0.0873,0.109, 0.11])
# OC_SBCeta=np.array([0.073, 0.079,0.0858,0.0936])
# RFamp=[0.685,0.6,0.5,0.4]
#
# IC_theta=np.arcsin(np.sqrt(innerfreq)*IC_SBCeta)*180/np.pi
# OC_theta=np.arccos(np.sqrt(outerfreq)*OC_SBCeta)*180/np.pi
# net_theta=IC_theta+OC_theta




fig,ax=plt.subplots(figsize=(8,6))
ax.errorbar(innerfreq,inner_heatingrate,inner_heatingrate_err ,color='red', label="Inner",marker='o',markersize=10, linestyle="None")
ax.set_xlabel("Radial frequency (MHz)",fontsize=14)
#ax.set_yaxis(color='red')
ax.set_ylabel(r"$\dot{\overline{n}}_{inner}$ (q/s)",fontsize=14,color='red')

ax2=ax.twinx()
ax2.errorbar(outerfreq, outer_heatingrate, outer_heatingrate_err,color='blue',label="Outer",marker='x', markersize=10, linestyle="None")
ax2.set_ylabel(r"$\dot{\overline{n}}_{outer}$ (q/s)",fontsize=14,color='blue')
#ax2.set_yaxis(color='blue')

# ax.legend(fontsize=12)
# ax2.legend(fontsize=12)
ax.set_title("Heating rate vs Twist",fontsize=16)
ax.set_yscale('linear')
ax2.set_yscale('linear')
plt.tight_layout()
#ax2.tight_layout()
plt.show()

# fig3,ax3=plt.subplots(figsize=(8,6))
# ax3.plot(RFamp,IC_theta ,color='red', label="IC angle")
# ax3.plot(RFamp,OC_theta ,color='blue', label="OC angle")
# ax3.plot(RFamp,net_theta ,color='black', label="Total angle")
# ax3.set_ylabel(r"$\theta (deg)$", fontsize=14)
# ax3.set_xlabel(r"RFamp", fontsize=14)
# ax3.set_yticks(range(0,95,10))
# ax3.legend(fontsize=10)
# ax3.grid(visible=True)
#plt.show()
'''


# heating rate vs twist DC
# 2025/07/21-22 data
# twist=np.array([-4,-2,-1,1,2,4])
# innerfreq=192.498275-np.array([ 189.985821,189.842143, 189.771117,189.775570, 189.846065,189.992903 ])
# outerfreq=192.498275-np.array([ 189.442429,189.570232, 189.636238,189.630094, 189.565595,189.438575 ])
# SEscalingfactor=4*m*h/(Q**2)
#
# inner_heatingrate=np.array([ 20.789,12.7*1+14.702*0, 12.965, 5.143, 3.832, 3.804])*SEscalingfactor*innerfreq*10**6
# inner_heatingrate_err=np.array([ 1.364,1.802*1+1.470*0, 1.24, 0.416, 0.244, 0.481])*SEscalingfactor*innerfreq*10**6
# outer_heatingrate=np.array([ 1.474, 3.67*1+1.076*0,1.193, 8.037, 14.316, 7.674])*SEscalingfactor*outerfreq*10**6
# outer_heatingrate_err=np.array([ 0.353,0.27*1 + 0.434*0, 0.263, 1.4101, 0.693, 1.647])*SEscalingfactor*outerfreq*10**6


# 2025/07/29 -31 data
twist=np.array([-8,-6, -4,-2,-1,1,2,4, 6.5, 8,-4.11]) # last two are from 31st
innerfreq=192.50308135-np.array([190.334120,190.164059 , 190.003177,189.854686, 189.786378,189.792551,
                                 189.8617,190.010753,# last 2 are from 31st
                                 190.213143,190.334053,#last 2 are from 1stAug, rfamp=9.8
                                 190.990621])# last is from Rfamp=7
outerfreq=192.50308135-np.array([189.222882,189.341214, 189.463897,189.594899, 189.6552,189.653726,
                                 189.590783,189.460221,# last 2 are from 31st
                                 189.308691,189.217439,#last 2 are from 1stAug, rfamp=9.8
                                 190.226148  ]) # last is from Rfamp=7
SEscalingfactor=4*m*h/(Q**2)

inner_heatingrate=np.array([34.745, 17.32, 14.895,6.656, 10.618, 2.090, 1.959, 2.107,1.585, 2.556,108.206 ])#*SEscalingfactor*innerfreq*10**6 # last 2 are from 31st
inner_heatingrate_err=np.array([4.022, 1.295 ,1.48,1.325, 0.813, 0.143, 0.246, 0.175, 0.173, 0.283,27.932])#*SEscalingfactor*innerfreq*10**6
outer_heatingrate=np.array([ 1.023, 1.410, 1.138,1.057 ,0.969, 8.431, 7.743, 6.095, 14.076, 8.940,4.219])#*SEscalingfactor*outerfreq*10**6
outer_heatingrate_err=np.array([0.091, 0.219 ,0.184,0.099, 1.4101, 0.917, 0.808, 0.597, 0.885, 0.847,1.201])#*SEscalingfactor*outerfreq*10**6


# CarrierRabi= 222.81#kHz
# IC_SBCRabi=1/(2*np.array([])) #kHz
# OC_SBCRabi=1/(2*np.array([30])) #kHz

# IC_SBCeta=np.array([0.085, 0.0873,0.109, 0.11])
# OC_SBCeta=np.array([0.073, 0.079,0.0858,0.0936])
# RFamp=[0.685,0.6,0.5,0.4]
#
# IC_theta=np.arcsin(np.sqrt(innerfreq)*IC_SBCeta)*180/np.pi
# OC_theta=np.arccos(np.sqrt(outerfreq)*OC_SBCeta)*180/np.pi
# net_theta=IC_theta+OC_theta




fig,ax=plt.subplots(figsize=(8,6))

cmap_palette='gist_rainbow'

cmap = plt.get_cmap(cmap_palette)
n_colors=len(twist)
color_arr=[cmap(i / (n_colors - 1)) for i in range(n_colors)]

# ax.errorbar(twist,inner_heatingrate,inner_heatingrate_err ,color='red', label="Inner",marker='o',markersize=10, linestyle="None")
# ax.errorbar(twist, outer_heatingrate, outer_heatingrate_err,color='blue',label="Outer",marker='x', markersize=10, linestyle="None")

for pt in range(len(twist)-1):

    if pt==0:
        ax.errorbar(innerfreq[pt], inner_heatingrate[pt], inner_heatingrate_err[pt], c=color_arr[pt], label="Inner",
                    marker='o', markersize=10,
                    linestyle="None")
        ax.errorbar(outerfreq[pt], outer_heatingrate[pt], outer_heatingrate_err[pt], c=color_arr[pt], label="Outer",
                    marker='x', markersize=10,
                    linestyle="None")
    else:
        ax.errorbar(innerfreq[pt], inner_heatingrate[pt], inner_heatingrate_err[pt], c=color_arr[pt], marker='o',
                    markersize=10,
                    linestyle="None")
        ax.errorbar(outerfreq[pt], outer_heatingrate[pt], outer_heatingrate_err[pt], c=color_arr[pt], marker='x',
                    markersize=10,
                    linestyle="None")

#exception to plot data of RFamp=7V, twist= -4V

ax.errorbar(innerfreq[-1], inner_heatingrate[-1], inner_heatingrate_err[-1], c=color_arr[2], marker='o', alpha=0.3,
                    markersize=10,
                    linestyle="None")
ax.errorbar(outerfreq[-1], outer_heatingrate[-1], outer_heatingrate_err[-1], c=color_arr[2], marker='x',alpha=0.3,
            markersize=10,
            linestyle="None")


ax.set_xlabel("Radial Frequency (MHz)",fontsize=14)
ax.set_ylabel(r"$\dot{\overline{n}}$ (q/s)",fontsize=14,color='black')
#ax.set_ylabel(r"$S_{E}(\omega_t)$",fontsize=14,color='black')


ax.set_title("Heating rate vs Twist",fontsize=16)
ax.set_yscale('log')
ax.set_xscale('log')

#ax.set_yscale('linear')

norm = Normalize(vmin=twist.min(), vmax=twist.max())
sm = ScalarMappable(norm=norm, cmap=cmap)
sm.set_array([])  # Dummy data for colorbar

# Add colorbar
cbar = plt.colorbar(sm, ax=ax)
#cbar= plt.colorbar(twist, ax=ax)
cbar.set_label('Twist (V)', fontsize=12)
#ax2.set_yscale('linear')
plt.tight_layout()


# power law fit to heating rate data to check scaling with frequency

def power_law(x,a,b):
    return a*(x)**b

indC=[0,5,5,10]
newdatasetCooler=np.array([np.concatenate((outerfreq[indC[0]:indC[1]],innerfreq[indC[2]:indC[3]])),
                           np.concatenate((outer_heatingrate[indC[0]:indC[1]],inner_heatingrate[indC[2]:indC[3]])),
                           np.concatenate((outer_heatingrate_err[indC[0]:indC[1]],inner_heatingrate_err[indC[2]:indC[3]]))]).T
print(newdatasetCooler)
print(newdatasetCooler.shape)
paramsCooler, covarianceCooler = curve_fit(power_law, newdatasetCooler[:,0], newdatasetCooler[:,1],p0=[1, -3])  # Initial guess [a, b]
a_fitCooler, b_fitCooler = paramsCooler
print(f"Fitted Parameters: a = {a_fitCooler:.3f}, b = {b_fitCooler:.3f}")
print(np.sqrt(covarianceCooler[0,0]), np.sqrt(covarianceCooler[1,1]))


indH=[0,5,5,10]
newdatasetHotter=np.array([np.concatenate((innerfreq[indH[0]:indH[1]],outerfreq[indH[2]:indH[3]])),
                           np.concatenate((inner_heatingrate[indH[0]:indH[1]],outer_heatingrate[indH[2]:indH[3]])),
                           np.concatenate((inner_heatingrate_err[indH[0]:indH[1]],outer_heatingrate_err[indH[2]:indH[3]]))]).T
# print(newdatasetCooler)
# print(newdatasetCooler.shape)
paramsHotter, covarianceHotter = curve_fit(power_law, newdatasetHotter[:,0], newdatasetHotter[:,1],p0=[10, -4])  # Initial guess [a, b]
a_fitHotter, b_fitHotter = paramsHotter
print(f"Fitted Parameters: a = {a_fitHotter:.3f}, b = {b_fitHotter:.3f}")
print(np.sqrt(covarianceHotter[0,0]), np.sqrt(covarianceHotter[1,1]))




# Generate Fitted Curve
x_fitCooler = np.linspace(3.5,1,10)
x_fitHotter = np.linspace(3.5,1,10)
#x_fit=np.linspace(t2[0],t2[-1],50)
y_fitCooler = power_law(x_fitCooler, a_fitCooler, b_fitCooler)
y_fitHotter = power_law(x_fitHotter, a_fitHotter, b_fitHotter)
# fig1=plt.figure(1, figsize=(8,6))
# ax1=plt.gca()
#ax.plot(t2, ad, label='data')
ax.errorbar(x_fitCooler, y_fitCooler, yerr=None, xerr=None,
              label=r"Fit to Cold mode: $\dot{{\overline{{n}}}} $ = $\frac{{{0:.3f}}}{{f^{{{1:.3f}}}}}$".format(a_fitCooler,b_fitCooler),color="b", linestyle='dashed')
ax.errorbar(x_fitHotter, y_fitHotter, yerr=None, xerr=None,
              label=r"Fit to Hot mode: $\dot{{\overline{{n}}}} $ = $\frac{{{0:.3f}}}{{f^{{{1:.3f}}}}}$".format(a_fitHotter,b_fitHotter),color="r", linestyle='dashed')

ax.legend(fontsize=12)
plt.tight_layout()
plt.show()


# Sample data
'''
np.random.seed(0)
x = np.random.rand(50)
y = np.random.rand(50)
c = np.random.rand(50) * 100  # Values for color
groups = np.random.choice(['Group A', 'Group B'], size=50)

# Create figure
fig, ax = plt.subplots()

# Scatter plot for each group with different markers
for group, marker in zip(['Group A', 'Group B'], ['o', 's']):
    mask = groups == group
    sc = ax.scatter(x[mask], y[mask], c=c[mask], cmap='viridis', marker=marker, label=group)

# Add colorbar
cbar = plt.colorbar(sc, ax=ax)
cbar.set_label('Color Scale')

# Add marker legend
legend = ax.legend(title='Groups', loc='upper left')

plt.xlabel("X")
plt.ylabel("Y")
plt.title("Scatter with Colorbar and Marker Legend")
plt.show()
'''