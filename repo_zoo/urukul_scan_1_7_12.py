from ndscan.experiment import *
from oitg.results import *
import numpy as np
from statistics import stdev
from math import *

class runScan(Fragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        for i in range(3):
            self.setattr_device("urukul0_ch" + str(i))
        self.urukul_list = [self.urukul0_ch0, self.urukul0_ch1, self.urukul0_ch2]
        ttl_params = ["ttl0", "ttl1", "ttl2", "ttl3"]
        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl0"))
        self.setattr_device(str(self.INPUT_TTL)) #must typecast or NoneType error when recomputing args
        self.ttl = self.get_device(self.INPUT_TTL)
        self.setattr_device("ttl4")
        self.setattr_result("result")
        self.setattr_result("res_err", display_hints={"error_bar_for": self.result.path})
        self.points = [0.0] * self.get_dataset("repetitions")
        self.gate_end_mu = np.int64(0) # necessary or type error when assigning new val
        self.num_edges = 0
        self.mean_rising_edges = 0.0
        self.channel_num = [0, 1, 2]

    @kernel
    def ON(self, pulse_time, freq, channel, const_time, num_repeat, detection_time, inpFreq, inpAmp):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Calculates mean
        rising edges for a given num_repeat to push to result channel"""

        self.initializeUrukul()
        sum_rising_edges = 0

        for i in range(num_repeat):
            for channel_num in range(3):
                if channel == channel_num:
                    self.pulseScanVal(channel, pulse_time, inpFreq, inpAmp)
                else:
                    self.pulseUrukul(channel_num, const_time, freq)
            with parallel:
                self.gate_end_mu = self.ttl.gate_rising(detection_time)
                with sequential:# Q: How to access number of scan points?
                    #add if statement checking if pulse time is zero if min changes, or else will get zero division error
                    maxttl=int(detection_time/pulse_time) # detection has to be greater than pulse time
                    for i in range(maxttl):
                        self.ttl4.pulse(detection_time/(maxttl*2.0))
                        delay(detection_time/(maxttl*2.0))
            delay(500*us)
            self.num_edges = self.ttl.count(self.gate_end_mu)#self.ttl0.count(self.gate_end_mu)
            sum_rising_edges += self.num_edges
            self.points[i] = float(self.num_edges) # need to convert to float or else returns type error
        self.mean_rising_edges = sum_rising_edges/(num_repeat)
        #self.core.wait_until_mu(now_mu()) <-- could this solve timing issue?

    @kernel
    def initializeUrukul(self): # Question: Do we need to run this experiment segment repeatedly?
        self.core.reset()
        #delay(1 * ms)
        self.urukul0_cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.ttl.input()
        self.ttl4.output()
        #delay(1 * ms)

    @kernel
    def pulseUrukul(self, numChan, const_time, freq):

        """Pulses either urukul ch0, 1, or 2 based on a dataset-stored channel number, time, and frequency"""

        self.urukul_list[numChan].sw.on() #can't use dictionary under kernel
        self.urukul_list[numChan].set(freq)
        delay(const_time[numChan])
        self.urukul_list[numChan].sw.off()

    @kernel
    def pulseScanVal(self, numChan, time, freq, amp):

        """Pulses urukul ch0, 1, or 2 based on user defined scannable channel number, time and frequency"""

        self.urukul_list[numChan].sw.on()
        self.urukul_list[numChan].set(freq, amp)
        delay(time)
        self.urukul_list[numChan].sw.off()

class executeScan(ExpFragment):

    """ScanExperiment1"""

    def build_fragment(self):
        self.setattr_param("channel", IntParam, "CHOOSE URUKUL CHANNEL (0, 1, OR 2)", 0)
        self.setattr_param("time", FloatParam, "SET PULSE TIME (us)",unit="us", default= 1.0*us, min = 1.0*us) #changed min to 1 to avoid fit issue when 0
        self.setattr_param("inputFreq", FloatParam, "SET CHANNEL FREQUENCY (MHz)",unit="MHz", default= 0.0*MHz)
        self.setattr_param("inputAmp", FloatParam, "SET CHANNEL AMPLITUDE (FROM 0-1)", 0.0)
        self.setattr_fragment("run", runScan) #Assigns runScan fragment and its attributes/functions to this fragment
        fit_params = ["TIME", "FREQUENCY", "AMPLITUDE"]
        self.setattr_argument("SET_FIT_PARAM", EnumerationValue(fit_params, default="TIME"), group = "SET FIT")
        fits = ["cos", "decaying_sinusoid", "detuned_square_pulse", "exponential_decay",
        "gaussian", "line", "lorentzian", "rabi_flop", "sinusoid", "v_function", "None"]
        self.setattr_argument("CHOOSE_FIT", EnumerationValue(fits, default="None"), group = "SET FIT")
        self.dict_obj = {"TIME" : self.time, "AMPLITUDE" : self.inputAmp, "FREQUENCY" : self.inputFreq}



    def run_once(self):

        """Retrieves constant values from dataset, then runs experiment"""

        freq = self.get_dataset("freq1") * MHz
        scanFreq = self.inputFreq.get()
        t1 = self.get_dataset("time1") * us
        t2 = self.get_dataset("time2") * us
        t3 = self.get_dataset("time3") * us
        num_repeat = self.get_dataset("repetitions")
        detection_time = self.get_dataset("detection_time") * us
        const_time = [t1, t2, t3]
        pulse_time = self.time.get()

        self.run.ON(pulse_time, freq, self.channel.get(), const_time, num_repeat, detection_time, scanFreq,
                    self.inputAmp.get()) #calls ON function in runScan fragment

        self.run.result.push(self.run.mean_rising_edges)
        self.run.res_err.push(np.std(self.run.points)/sqrt(num_repeat))

        print("SCAN COMPLETE")

    def get_default_analyses(self):
        if self.CHOOSE_FIT != "None":
            return [
                OnlineFit(self.CHOOSE_FIT,
                          data={
                              "x": self.dict_obj[self.SET_FIT_PARAM],
                              "y": self.run.result,
                              "y_err": self.run.res_err,
                          }
                          )
            ]
        else:
            return []

ScanForTime = make_fragment_scan_exp(executeScan)