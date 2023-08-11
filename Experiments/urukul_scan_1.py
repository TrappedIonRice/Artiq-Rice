from ndscan.experiment import *
from oitg.results import *
import numpy as np
from statistics import stdev
from math import *
import oitg.fitting


class runScan(Fragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_device("core_dma")
        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        for i in range(3):
            self.setattr_device("urukul0_ch" + str(i))
        self.urukul_list = [self.urukul0_ch0, self.urukul0_ch1, self.urukul0_ch2]
        ttl_params = ["ttl0_counter", "ttl1_counter", "ttl2_counter", "ttl3_counter"]
        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl0_counter"))
        self.setattr_device(str(self.INPUT_TTL)) #must typecast or NoneType error when recomputing args
        self.ttl = self.get_device(self.INPUT_TTL)
        self.setattr_device("ttl4")
        self.setattr_result("result")
   #     self.setattr_result("result2")
        self.setattr_param("urukulchan2freq",FloatParam,"Urukul channel 2 freq", unit="MHz",default=1.0*MHz)
        self.setattr_result("res_err", display_hints={"error_bar_for": self.result.path})
        self.points = [[0.0] * self.get_dataset("scan1.repetitions"), [0.0] * self.get_dataset("scan1.repetitions")]
        self.gate_end_mu = np.int64(0) # necessary or type error when assigning new val
        self.mean_rising_edges = 0.0
        self.channel_num = [0, 1, 2]

    @kernel
    def ON(self, pulse_time, freq, channel, const_time, num_repeat, detection_time, inpFreq, inpAmp):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Calculates mean
        rising edges for a given num_repeat to push to result channel"""

        self.initializeUrukul()
        sum_rising_edges = 0.0

        self.urukul_list[1].set(freq)

        with self.core_dma.record("seq"):
            delay(30 * us)
            for channel_num in range(3):
                if channel == channel_num:
                    self.pulseScanVal(channel, pulse_time, inpFreq, inpAmp)
                else:
                    self.pulseUrukul(channel_num, const_time[channel_num], freq)
            with parallel:
                self.ttl.gate_rising(detection_time)
                with sequential:# Q: How to access number of scan points?
                    maxttl=int(detection_time/pulse_time) # detection has to be greater than pulse time
                    for i in range(maxttl):
                        self.ttl4.pulse(detection_time/(maxttl*2.0))
                        delay(detection_time/(maxttl*2.0))

        # for DMA
        seq_handle = self.core_dma.get_handle("seq")

        self.core.break_realtime()
        for i in range(num_repeat):
            self.core_dma.playback_handle(seq_handle)
            self.points[0][i] = float(self.ttl.fetch_count()) #I think can only be called once per gate event or blocks function until result is available
       #     self.points[1][i] = self.points[0][i] * -1
     #       print(float(self.ttl.fetch_count()))
     #       self.points[1][i] = float(self.ttl.fetch_count()) * -1
            sum_rising_edges += self.points[0][i]

        self.mean_rising_edges = sum_rising_edges/(num_repeat)


    @kernel
    def initializeUrukul(self): # Question: Do we need to run this experiment segment repeatedly?
        self.core.reset()
        # self.core.break_realtime()
        self.urukul0_cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        #self.ttl.input()
        self.ttl4.output()


    @kernel
    def pulseUrukul(self, numChan, const_time, freq):

        """Pulses either urukul ch0, 1, or 2 based on a dataset-stored channel number, time, and frequency"""
        self.urukul_list[numChan].set(freq, phase_mode=2)
        self.urukul_list[numChan].sw.on() #can't use dictionary under kernel
        delay(const_time)
        self.urukul_list[numChan].sw.off()

    @kernel
    def pulseScanVal(self, numChan, time, freq, amp):

        """Pulses urukul ch0, 1, or 2 based on user defined scannable channel number, time and frequency"""

        self.urukul_list[numChan].set(freq, amplitude=amp, phase_mode=2)
        self.urukul_list[numChan].sw.on()
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
        # self.setattr_argument("x0", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("y0", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("y_inf", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("tau", NumberValue(default=0*us, unit = "us", ndecimals=6), group = "SET FIT")
        self.dict_obj = {"TIME" : self.time, "AMPLITUDE" : self.inputAmp, "FREQUENCY" : self.inputFreq}
 #       self.analyses = AnnotationContext()
        #self.setattr_result("test")

    def host_setup(self):           #reserved key word
        self.freq = self.get_dataset("scan1.freq1") * MHz
        self.t1 = self.get_dataset("scan1.time1") * us
        self.t2 = self.get_dataset("scan1.time2") * us
        self.t3 = self.get_dataset("scan1.time3") * us
        self.num_repeat = self.get_dataset("scan1.repetitions")
        self.detection_time = self.get_dataset("scan1.detection_time") * us

    @kernel
    def run_once(self):

        """Retrieves constant values from dataset, then runs experiment"""

        scanFreq = self.inputFreq.get()
        const_time = [self.t1, self.t2, self.t3]
        pulse_time = self.time.get()
        self.run.ON(pulse_time, self.freq, self.channel.get(), const_time, self.num_repeat, self.detection_time, scanFreq,
                    self.inputAmp.get()) #calls ON function in runScan fragment

        # self.run.result.push(np.log(self.run.mean_rising_edges))
        self.host_push_results(self.run.mean_rising_edges, self.run.points)
       # print(self.analyses.describe_online_analyses())
        #self.test.push(np.sin(9586958.6))


    @rpc(flags={"async"})
    def host_push_results(self, mean_rising_edges, points):
        self.run.result.push(mean_rising_edges)
     #   self.run.result2.push(np.mean(points[1]))
        self.run.res_err.push(5.0 / sqrt(self.num_repeat))
        # print(oitg.fitting.exponential_decay.fit(self.time, self.run.result, self.run.res_err, evaluate_function=True,
        #                                          evaluate_n=100))

    def get_default_analyses(self):
     #   lst_param = [self.x0, self.y0, self.y_inf, self.tau]
     #   param_names = ['x0', 'y0', 'y_inf', 'tau']
        dict_constants = {}
     #   for i in range(len(lst_param)):
     #       if lst_param[i] != 0:
     #           dict_constants[param_names[i]] = lst_param[i]
     #   print(dict_constants)
        if self.CHOOSE_FIT != "None":
            return [
                OnlineFit(self.CHOOSE_FIT,
                          data={
                              "x": self.dict_obj[self.SET_FIT_PARAM],
                              "y": self.run.result,
                              "y_err": self.run.res_err,
                          },
                   #       constants= dict_constants
                          )
            ]
        else:
            return []

ScanForTime = make_fragment_scan_exp(executeScan)

# class runSubscan1(ExpFragment):
#     def build_fragment(self):
#         self.setattr_param("max_time", FloatParam, "SET MAX PULSE TIME (us)",unit="us", default= 0.0*us, min = 1.0*us)
#         self.setattr_fragment("scan1", executeScan)
#         self.scan1.CHOOSE_FIT = "exponential_decay"
#         self.scan1.SET_FIT_PARAM = "TIME"
#         setattr_subscan(self, "scan", self.scan1, [(self.scan1, "time")], expose_analysis_results = True)
#     def run_once(self):
#         self.scan.run([(self.scan1.time, LinearGenerator(1, self.max_time.get(), 10, False))])
#
# Scan1Subscan = make_fragment_scan_exp(runSubscan1)
#



