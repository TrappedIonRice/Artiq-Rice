from ndscan.experiment import *
from oitg.results import *
import numpy as np
import time
from statistics import stdev
from math import *

"""CREATED AS A TEST FILE FOR URUKUL SCAN 1. PURPOSE IS TO LIMIT DELAY TIME WITHIN SCAN"""

class runScan2(Fragment):

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
        self.points = [0] * self.get_dataset("repetitions")
        self.gate_end_mu = np.int64(0) # necessary or type error when assigning new val
        self.num_edges = 0
        #self.mean_rising_edges = 0.0
        self.channel_num = [0, 1, 2]
        self.t1 = 0.0 * us
        self.t2 = 0.0 * us
        self.t3 = 0.0 * us
        self.numChan = 0
        self.scan_channel = 0
        self.inpFreq = 0.0 * MHz
        self.freq = 0.0 * MHz
        self.detection_time = 0.0 *MHz
        self.inpAmp = 0.0
        self.pulse_time = 0.0 * us
        self.num_repeat = 0
        self.core.reset()

    @kernel
    def ON(self):#, pulse_time, freq, channel, const_time, num_repeat, detection_time, inpFreq, inpAmp):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Calculates mean
        rising edges for a given num_repeat to push to result channel"""

        self.initialize_hardware()
        sum_rising_edges = 0
        const_time = [self.t1, self.t2, self.t3]
        #self.urukul0_ch0.set(freq=1*MHz)
        for channel_num in range(3):
            if self.scan_channel == channel_num:
                self.pulseScanVal()  # works with 100 us delay if if and for loop are removed and only this line of code is present in this section
            else:
                self.numChan = channel_num
                self.pulseUrukul()
        for i in range(self.num_repeat):
            # for channel_num in range(3):
            #     if channel == channel_num:
            #         self.pulseScanVal(channel, pulse_time, inpFreq, inpAmp) #works with 100 us delay if if and for loop are removed and only this line of code is present in this section
            #     else:
            #         self.pulseUrukul(channel, const_time[channel_num], freq)
            self.allurukul()
            # self.urukul_list[0].sw.pulse(pulse_time)
            # self.urukul_list[1].sw.pulse(t1)
            # self.urukul_list[2].sw.pulse(t2)
            # self.gate_end_mu = self.ttl.gate_rising(detection_time)

            self.detection_pulse()

            #self.ttl4.pulse(detection_time / (maxttl * 2.0))
            #             delay(detection_time/(maxttl*2.0))

            #self.urukul_list[3].sw.pulse(time)
            # with parallel:
            #     self.gate_end_mu = self.ttl.gate_rising(detection_time)
            #     with sequential:# Q: How to access number of scan points?
            #         #add if statement checking if pulse time is zero if min changes, or else will get zero division error
            #         maxttl=int(detection_time/pulse_time) # detection has to be greater than pulse time
            #         for i in range(maxttl):
            #             self.ttl4.pulse(detection_time/(maxttl*2.0))
            #             delay(detection_time/(maxttl*2.0))
       #     delay(10*us)
       #     delay_mu(8)
            #self.num_edges = self.ttl.count(self.gate_end_mu)#self.ttl0.count(self.gate_end_mu)
            #sum_rising_edges= sum_rising_edges+ self.num_edges
            #self.points[i] = self.num_edges # need to convert to float or else returns type error
        #self.mean_rising_edges = sum_rising_edges/(num_repeat)
        #self.core.wait_until_mu(now_mu())#<-- could this solve timing issue?

    @kernel
    def initialize_hardware(self): # Question: Do we need to run this experiment segment repeatedly?
        #self.core.reset()
        self.urukul0_cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.ttl.input()
        self.ttl4.output()

    @kernel
    def pulseUrukul(self):

        """Pulses either urukul ch0, 1, or 2 based on a dataset-stored channel number, time, and frequency"""


        self.urukul0_ch0.set(self.inpFreq)
        #self.urukul_list[numChan].sw.pulse(const_time)
        #delay()
        #self.urukul_list[numChan].sw.off()

    @kernel
    def pulseScanVal(self):

        """Pulses urukul ch0, 1, or 2 based on user defined scannable channel number, time and frequency"""


        self.urukul0_ch0.set(self.inpFreq, self.inpAmp)
        delay(1*us)
        #self.urukul_list[numChan].sw.pulse(time)
        #delay(time)
        #self.urukul_list[numChan].sw.off()

    @kernel
    def allurukul(self):
        self.urukul0_ch0.sw.pulse(self.pulse_time)
        # delay(10*us)
        # self.urukul0_ch1.sw.pulse(self.t1)
        # delay(1*us)
        # self.urukul0_ch2.sw.pulse(self.t2)
        # delay(1*us)


    @kernel
    def detection_pulse(self):
        "detection pulse"
        self.gate_end_mu = self.ttl.gate_rising(self.detection_time)
        delay(100 * us)
        self.num_edges = self.ttl.count(self.gate_end_mu)
class executeScan2(ExpFragment):

    """LimitDelayScan"""

    def build_fragment(self):
        self.setattr_param("channel", IntParam, "CHOOSE URUKUL CHANNEL (0, 1, OR 2)", 0)
        self.setattr_param("time", FloatParam, "SET PULSE TIME (us)",unit="us", default= 1.0*us, min = 1.0*us) #changed min to 1 to avoid fit issue when 0
        self.setattr_param("inputFreq", FloatParam, "SET CHANNEL FREQUENCY (MHz)",unit="MHz", default= 0.0*MHz)
        self.setattr_param("inputAmp", FloatParam, "SET CHANNEL AMPLITUDE (FROM 0-1)", 0.0)
        self.setattr_fragment("run", runScan2) #Assigns runScan2 fragment and its attributes/functions to this fragment
        fit_params = ["TIME", "FREQUENCY", "AMPLITUDE"]
        self.setattr_argument("SET_FIT_PARAM", EnumerationValue(fit_params, default="TIME"), group = "SET FIT")
        fits = ["cos", "decaying_sinusoid", "detuned_square_pulse", "exponential_decay",
        "gaussian", "line", "lorentzian", "rabi_flop", "sinusoid", "v_function", "None"]
        self.setattr_argument("CHOOSE_FIT", EnumerationValue(fits, default="None"), group = "SET FIT")
        self.dict_obj = {"TIME" : self.time, "AMPLITUDE" : self.inputAmp, "FREQUENCY" : self.inputFreq}



    def run_once(self):

        """Retrieves constant values from dataset, then runs experiment"""

        # freq = self.get_dataset("freq1") * MHz
        # scanFreq = self.inputFreq.get()
        self.run.t1 = self.get_dataset("time1") * us
        self.run.t2 = self.get_dataset("time2") * us
        self.run.t3 = self.get_dataset("time3") * us
        self.run.pulse_time = self.time.get()
        self.run.freq = self.get_dataset("freq1") * MHz
        self.run.scan_channel = self.channel.get()
        self.run.num_repeat = self.get_dataset("repetitions")
        self.run.detection_time = self.get_dataset("detection_time") * us
        self.run.inpFreq = self.inputFreq.get()
        self.run.inpAmp = self.inputAmp.get()
        # num_repeat = self.get_dataset("repetitions")
        # detection_time = self.get_dataset("detection_time") * us
        # const_time = [self.run.t1, self.run.t2, self.run.t3]
        # pulse_time = self.time.get()
        exec1=time.time()
        self.run.ON()
        print(time.time()-exec1)
        # self.run.ON(pulse_time, freq, self.channel.get(), const_time, num_repeat, detection_time, scanFreq,
        #             self.inputAmp.get()) #calls ON function in runScan2 fragment

        #self.run.result.push(np.sin(self.run.p))#np.mean(self.run.points))
        #self.run.res_err.push(0.5)#np.std(self.run.points)/sqrt(num_repeat))

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

LimitDelayScan = make_fragment_scan_exp(executeScan2)