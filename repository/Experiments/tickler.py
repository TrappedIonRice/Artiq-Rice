from artiq.experiment import *
import numpy as np
import matplotlib.pyplot as plt
from ndscan import *
import time
from scipy.optimize import curve_fit
from scipy.stats import chisquare

class Tickle(EnvExperiment):

    def build(self):
        # Devices
        self.setattr_device("core")
        # user arguments
        urukuls = ["0"]  # the list of the urukuls availible
        channels = ["1", '3']  # list of channel on a given urukul; only use channel 0

        # To set all channels of the urukul (device drivers) as attributes
        for i in channels:
            self.setattr_device("urukul0" + "_ch" + i)
        self.setattr_device("urukul0_ch0") # RF channel is very imp
        self.RFamp=self.get_dataset("UrukulCh0_RFamp")


        self.setattr_device("ttl0") # PMT counter received signal to DIO
        self.setattr_device("ttl4") # output trigger to sync with tickle time
        self.setattr_device("urukul0_cpld") # What for?


        # EnumerationValue specifies an argument that can take a string value among a set of string values

        self.setattr_argument("frequency", NumberValue(default=195 * MHz, unit="MHz", ndecimals=6), group='channel1')
        #self.frequencuy
        #self.setattr_argument("amplitude", NumberValue(default=0.8, min=0, max=1, ndecimals=6), group='channel1')
        self.amplitude=self.get_dataset("Doppler.Amp")
        self.setattr_argument("attenuation", NumberValue(default=0, unit="dB", min=0, max=10), group='channel1')

        self.setattr_argument("tickler_amp", NumberValue(default=0.8, min=0, max=1, ndecimals=6), group='channel3')

        self.setattr_argument("cooling_time", NumberValue(default=20*ms, ndecimals=4, unit="ms"), group='channel3')
        self.setattr_argument("tickle_time", NumberValue(default=50*ms, ndecimals=4, unit="ms"), group='channel3')
        self.setattr_argument("num_exp", NumberValue(default=50, ndecimals=0, step=1), group='channel3')

        # atributes for frequency scanning
        self.setattr_argument("min_freq", NumberValue(default=0.264*MHz, unit="MHz", step=0.1, ndecimals=3), group='channel3')
        self.setattr_argument("max_freq", NumberValue(default=0.270*MHz, unit="MHz", step=0.1, ndecimals=3), group='channel3')
        self.setattr_argument("num_freq_pts", NumberValue(default=61, unit=None, scale=1, step=1, ndecimals=0, type='int'), group='channel3')

        # for the creation of applets (plotting of results)
        self.setattr_device("ccb")

    def prepare(self):

        # broadcast: the data is sent in real-time to the master, which dispatches it.
        # archive: the data is saved into the local storage of the current run (archived as a HDF5 file).
        # Creates frequency range
        self.freq_range=np.linspace(self.min_freq, self.max_freq, self.num_freq_pts)
        self.freq_exp_matrix = np.empty((self.num_freq_pts, self.num_exp))
        self.freq_exp_rel_matrix = np.empty((self.num_freq_pts, self.num_exp))

        self.avg_rel_counts = np.zeros(self.num_freq_pts)

        self.set_dataset("freq_range",  self.freq_range, broadcast=True, archive=True)
        # setts datasets for plotting
        self.set_dataset("Tickler_counts_freq", np.full(self.num_freq_pts, float(np.nan)), broadcast=True, archive=True)
        self.set_dataset("Tickler_counts_y", np.full(self.num_freq_pts, float(np.nan)), broadcast=True, archive=True)

        # creates applet to plot the results
        command = "${artiq_applet}plot_xy Tickler_counts_y --x Tickler_counts_freq --fit Tickler_counts_y"
        self.ccb.issue("create_applet", "Tickler", command)


    @kernel # following method is run in kernel
    def krun(self):
        delay(1 * ms)
        self.core.reset()
        delay(50 * us)
        #self.urukul0_ch1.cpld.init()
        self.urukul0_cpld.init() # what is the purpose of this?
        delay(50 * us)
        self.urukul0_ch0.init()  # leave RF as is
        self.urukul0_ch0.set_att(0 * dB)
        self.urukul0_ch0.set(frequency=25.701 * MHz, amplitude=self.RFamp)
        # delay(1*us)
        self.urukul0_ch0.sw.on()  # turns it on as in the last config

        # DDS0 Doppler cooler "on"; we want it to run continuously through the run
        self.urukul0_ch1.init()

        self.urukul0_ch1.set(frequency=self.frequency, amplitude=self.amplitude, phase_mode=2)
        self.urukul0_ch1.set_att(0*dB)
        self.urukul0_ch1.sw.on()

        self.urukul0_ch3.set_att(0*dB)

        ###################################### Relative ratio ###########################################################
        exp_num = 0
        baseline = 0.0
        while (exp_num < self.num_exp): # repeat for num_exp
            scan_direction = exp_num % 2 == 0
            if scan_direction:
                freq_num = 0
            else:
                freq_num = len(self.freq_range) - 1

            exp_avg = 0.0
            # print(len(self.freq_range))
            while (scan_direction and freq_num < len(self.freq_range)) or ((not scan_direction) and freq_num >= 0): # scan through frequencies

                #if False:
                delay(1 * ms)
                self.urukul0_ch3.set(frequency=self.freq_range[freq_num], amplitude=self.tickler_amp, phase_mode=2)
                delay(1 * ms)
                counts_no = self.ttl0.gate_rising(self.cooling_time)  # incorporates cooling time
                self.urukul0_ch3.sw.on()
                self.ttl4.on()
                counts_yes = self.ttl0.gate_rising(self.tickle_time)
                self.urukul0_ch3.sw.off()
                self.ttl4.off()
                delay(50 * us)  # final delay to prevent underflow during experiment.
                                # Delay between shots should not cause problems esp since dds is in phase tracking mode.

                counts_no_tickle = self.ttl0.count(counts_no) * self.tickle_time / self.cooling_time
                delay(150*us)
                counts_tickle = self.ttl0.count(counts_yes)
                delay(150 * us)

                if exp_num == 0:
                    baseline += counts_no_tickle / self.cooling_time
                exp_avg += counts_no_tickle / self.cooling_time

                delta = counts_tickle - counts_no_tickle
                if counts_no_tickle > 0:
                    rel_counts = delta / counts_no_tickle / self.tickle_time
                else:
                    rel_counts = delta / self.tickle_time
                self.freq_exp_rel_matrix[freq_num, exp_num] = rel_counts
                if rel_counts < 0:
                    rel_counts *= -1
                self.avg_rel_counts[freq_num] = (self.avg_rel_counts[freq_num] * exp_num + rel_counts) / (exp_num + 1)
                self.mutate_dataset("Tickler_counts_freq", freq_num, self.freq_range[freq_num])
                self.mutate_dataset("Tickler_counts_y", freq_num, self.avg_rel_counts[freq_num])

                if scan_direction:
                    freq_num += 1
                else:
                    freq_num -= 1
                # else:
                #     self.ttl4.on()
                #     delay(1*us)
                #     self.ttl4.off()
                #     delay(332.3368*us)

            if exp_num == 0:
                baseline = baseline / freq_num
            #exp_avg = exp_avg / freq_num

            # print(baseline)
            # print(exp_avg)

            exp_num += 1

            # if exp_avg < baseline * 0.2:
            #     exp_num = self.num_exp
        #################################################################################################################
        delay(50*us)
        self.urukul0_ch1.set(frequency=self.frequency, amplitude=self.amplitude, phase_mode=2)
        delay(1*ms)
        self.urukul0_ch1.set_att(0 * dB)
        delay(1*ms)
        self.urukul0_ch1.sw.on()

    def run(self):
        self.krun()
        self.plot_rel_count_avg()

    def plot_rel_count_avg(self):
        data = np.zeros(len(self.freq_range))
        err = np.zeros(len(self.freq_range))

        for freq in range(len(self.freq_range)):
            dat = self.freq_exp_rel_matrix[freq]**2

            # dat = drop_outliers(dat, 0.05)
            data[freq] = np.mean(dat)
            err[freq] = np.std(dat) / np.sqrt(len(dat))

        # print(data)
        # print(self.freq_range)
        # print(data[np.where(data >= np.max(data))])
        # print(np.max(data))
        p0 = (data[np.where(data >= np.max(data))], self.freq_range[np.where(data >= np.max(data))], 1, np.min(data))
        print(p0)
        gdata, gfit, gpopt, perr, chisq, dof, p = fit_data(np.array([self.freq_range, data]), gaussian, -1, 3, p0=p0, bounds=(0, np.inf))
        # p0 = (1, 1)
        p0 = (np.max(data) - np.min(data), 1, data[np.where(data == np.max(data))])
        # ldata, lfit, lpopt, perr, chisq, dof, p = fit_data(np.array([self.freq_range, np.sqrt(np.log(data - np.min(data)))]), lambda x, a, sigma, x0: (x - x0) / np.sqrt(2) / sigma + a, -1, 2, p0=p0, bounds=(-np.inf, np.inf))

        plt.errorbar(self.freq_range / 1000, gdata[1], yerr=err, capsize=4, ecolor='cyan')
        plt.plot(self.freq_range / 1000, gfit, label='gfit: ' + str(gpopt))
        # plt.plot(self.freq_range / 1000, np.exp(lfit**2) + np.min(data), label='lfit: ' + str(lpopt))
        plt.xlabel('Tickling frequency (kHz)')
        plt.ylabel('Mean square relative signal')
        plt.legend()
        plt.show()

        np.savetxt('Z:/Lab Rice/Experimental Projects/Monolithic Trap/Trap frequency measurements/tickledata_freq' \
                   + str(int(self.freq_range[0] / 1000)) + '-' + str(int(self.freq_range[-1] / 1000)) + '_rf' + str(self.get_dataset('RFamp_Arduino')).replace('.', ',') \
                   + '_twist' + str(self.get_dataset('DC.Twist')).replace('.', ',') + '_endcapavg' + str(self.get_dataset('DC.EndcapAvg')).replace('.', ',') + '_endcapx' \
                   + str(self.get_dataset('DC.EndcapX')).replace('.', ',') + '.txt', self.freq_exp_rel_matrix)


def drop_outliers(data, cutoff):
    sorted_data = np.sort(data, axis=-1)
    sorted_data = sorted_data[int(np.ceil(len(sorted_data)*cutoff)):int(np.floor(len(sorted_data)*(1 - cutoff)))]
    return sorted_data


def fit_data(data, func, bins, ddof, p0=None, bounds=None):
        if bins > 0:
            data = np.array([[np.sum(var[int(len(var) / bins * bin):int(len(var) / bins * (bin + 1))]) / (len(var) / 15)
                              for bin in range(bins)] for var in data])

        if bounds is None:
            bounds = (-1 * np.inf, np.inf)
        popt, pcov = curve_fit(func, data[0], data[1], p0=p0, bounds=bounds)

        fit = func(data[0], *popt)
        perr = np.sqrt(np.diag(pcov))
        dof = len(data[1]) - 3
        try:
            chisq, p = chisquare(data[1], fit, ddof=ddof)
        except Exception:
            chisq, p = (0, 0)

        print('chi^2 =', chisq)
        print('dof = ', dof)
        print('reduced chi^2 =', chisq / dof)
        print('pval =', p)

        return data, fit, popt, perr, chisq, dof, p


def linear(x, a, b):
    return a * x + b


def gaussian(x, a, x0, sigma, b):
    return a * np.exp(-(x - x0)**2 / (2 * sigma)) + b


def double_gaussian(x, a1, a2, x1, x2, sigma1, sigma2):
    return gaussian(x, a1, x1, sigma1, 0) + gaussian(x, a2, x2, sigma2, 0)


def lorenztian(x, A, x0, Gamma, b):
    return A / (1 + ((x - x0) / Gamma)**2) + b
