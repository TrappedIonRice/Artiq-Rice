from ndscan.experiment import *
from oitg.results import *
import numpy as np
from statistics import stdev
from math import *
import time as tm
import oitg.fitting

class runScan(Fragment):

    def build_fragment(self):
        self.setattr_device("core")
        #self.setattr_device("core_dma")
        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("urukul0_ch3")

        ttl_params = ["ttl0_counter"]
        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl0_counter"))
        self.setattr_device(str(self.INPUT_TTL)) #must typecast or NoneType error when recomputing args

        self.sum_rising_edges=0.0
        self.setattr_result("counts")
   #    self.setattr_result("result2")
       # self.setattr_param("urukulchan2freq",FloatParam,"Urukul channel 2 freq", unit="MHz",default=1.0*MHz)
        self.setattr_result("res_err", display_hints={"error_bar_for": self.counts.path})
        self.points = [[0.0] * self.get_dataset("Repetitions"), [0.0] * self.get_dataset("Repetitions")]
        self.gate_end_mu = np.int64(0) # necessary or type error when assigning new val
        self.mean_rising_edges = 0.0
        self.channel_num = [1] # Doppler, Det, OP


    @kernel
    def ON(self, wait_time, coolingfreq,coolingamp, coolingtime, detFreq,detAmp, detTime, num_repeat):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Calculates mean
        rising edges for a given num_repeat to push to counts channel"""

        self.core.reset()
       #self.core.break_realtime()
        self.urukul0_cpld.init()
        self.urukul0_ch0.init() # leave RF as is
        self.urukul0_ch0.set_att(0*dB)
        self.urukul0_ch0.set( frequency= 25.671*MHz, amplitude=self.RFamp)
        #delay(1*us)
        self.urukul0_ch0.sw.on() # turns it on as in the last config
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.urukul0_ch2.set_att(0 * dB)
        self.urukul0_ch2.sw.on()

        # self.ttl.input()
        self.ttl4.output()

        self.sum_rising_edges = 0.0

        self.urukul0_ch1.set_att(0*dB)

        #exp loop without dma
        i=0
        while(i<num_repeat):
            delay(30 * us)  # This delay will exist between scan points
            # Doppler cool initially using Global freq and amplitude
            self.urukul0_ch1.set(frequency=coolingfreq, amplitude=coolingamp, phase_mode=2)
            #delay(30*us)
            self.urukul0_ch1.set_att(0 * dB)
            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            delay(coolingtime)
            self.urukul0_ch1.sw.off()
            #wait
            delay(wait_time)

            # Reset Detection DC freq, amp
            self.urukul0_ch1.set(frequency=detFreq, amplitude=detAmp)
            self.urukul0_ch1.set_att(0 * dB)

            # rising trigger to timeharp
            self.ttl4.on()
            #Detection DC on
            delay(-100*ns) # to sync TTL4 and Doppler DDS
            self.urukul0_ch1.sw.on()
            #Detection with Doppler using script specific freq and amplitude

            # for simple detection using edge counter
            self.ttl.gate_rising(detTime)
            # without edge counter
            #detcounts_time = self.ttl.gate_rising(detTime)

            # with parallel:
            #     with sequential:# Q: How to access number of scan points?
            #         maxttl2=(detTime/pulse_time) # detection has to be greater than pulse time
            #         maxttl=int(maxttl2)
            #         for i in range(maxttl):
            #             self.ttl4.pulse(detTime*i/(maxttl2*2.0))
            #             delay(detTime/(maxttl2*2.0))

            # Detection DC off
            self.urukul0_ch1.sw.off()
            # falling trigger to timeharp
            self.ttl4.off()
            delay(-2*us) # to match TTL4 falling edge and Doppler on edges
            #continue Doppler
            self.urukul0_ch1.set(frequency=coolingfreq, amplitude=coolingamp, phase_mode=2)
            #delay(5 * us)
            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel

            #extra computations always left at the end of the scan, or else RTIO underflow occurs
            x=self.ttl.fetch_count()
            self.sum_rising_edges = self.sum_rising_edges + x
            delay(1*ms)

            i=i+1


        # exp loop with dma
        # with self.core_dma.record("seq"):
        #     delay(30 * us) # This delay will exist between scan points
        #     self.pulseUrukul(1, const_time[1], freq)
        #
        #     delay(scan_time)
        #     self.ttl4.on()
        #     # for simple detection using edge counter
        #     #self.ttl.gate_rising(detection_time)
        #     # without edge counter
        #     detcounts_time=self.ttl.gate_rising(detection_time)
        #     self.ttl4.off()
        #     # for debugging detection with pmt ttl
        #     # with parallel:
        #     #     self.ttl.gate_rising(detection_time)
        #     #     with sequential:# Q: How to access number of scan points?
        #     #         maxttl2=(detection_time/pulse_time) # detection has to be greater than pulse time
        #     #         maxttl=int(maxttl2)
        #     #         for i in range(maxttl):
        #     #             self.ttl4.pulse(detection_time*i/(maxttl2*2.0))
        #     #             delay(detection_time/(maxttl2*2.0))

        # for DMA
        #seq_handle = self.core_dma.get_handle("seq")


        # repetition loop for DMA
        # self.core.break_realtime()
        # for i in range(num_repeat):
        #     tempval = 0.0
        #     self.core_dma.playback_handle(seq_handle)
        #     self.points[0][i] = float(self.ttl.fetch_count()) #I think can only be called once per gate event or blocks function until counts is available
        #     tempval=self.points[0][i]
        #     sum_rising_edges= sum_rising_edges + tempval

        # options for thresholding and/or histogram

        self.mean_rising_edges = (self.sum_rising_edges)/(num_repeat)



class executeScan(ExpFragment):

    """Scan AOM435"""

    def build_fragment(self):
       # self.setattr_param("channel", IntParam, "CHOOSE URUKUL CHANNEL (0-3)", default=0)
        self.setattr_param("Frequency", FloatParam, "Set Frequency ",unit="MHz", default= 250.000*MHz, min = 230.00*MHz, max=270*MHz) #changed min to 1 to avoid fit issue when 0
        self.setattr_param("Amplitude", FloatParam, "Set Amplitude ", unit="", default=0.000 , min=0.00, max=0.8)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Time", FloatParam, "Set Time ",unit="ms", default= 1.00*ms)
        self.setattr_fragment("run", runScan) #Assigns runScan fragment and its attributes/functions to this fragment

        #self.setattr_fragment("histplot",histPlot,len(self.run.points)) # creates histogram plot, maybe called too early
        #fit_params = ["TIME", "FREQUENCY", "AMPLITUDE"]
        # self.setattr_argument("histogram",BooleanValue(default=False) ,tooltip="Save histogram data also")
        # self.setattr_argument("threshold_enable", BooleanValue(default=False),group="THRESHOLD", tooltip="Single ion threshhold")
        # self.setattr_argument("threshold_value",NumberValue(min=0.0, max=100, ndecimals=3, default=0), group="THRESHOLD", tooltip="Single ion threshhold")
        #self.setattr_argument("SET_FIT_PARAM", EnumerationValue(fit_params, default="TIME"), group = "SET FIT")
        #fits = ["cos", "decaying_sinusoid", "detuned_square_pulse", "exponential_decay",
        #        "gaussian", "line", "lorentzian", "rabi_flop", "sinusoid", "v_function", "None"]
        #self.setattr_argument("CHOOSE_FIT", EnumerationValue(fits, default="None"), group = "SET FIT")

        # self.setattr_argument("x0", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("y0", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("y_inf", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("tau", NumberValue(default=0*us, unit = "us", ndecimals=6), group = "SET FIT")

        #self.dict_obj = {"TIME" : self.waittime, "AMPLITUDE" : self.recoolamp, "FREQUENCY" : self.recoolfreq}
 #       self.analyses = AnnotationContext()
        #self.setattr_result("test")

    def host_setup(self):           #reserved key word
        self.cooling_freq = self.get_dataset("Doppler.Frequency")
        self.cooling_amp = self.get_dataset("Doppler.Amp")
        self.num_repeat = self.get_dataset("Repetitions")
        self.cooling_time = self.get_dataset("Doppler.Time(ms)") * ms

        self.cooling_freq = self.get_dataset("Doppler.Frequency")
        self.cooling_amp = self.get_dataset("Doppler.Amp")
        self.num_repeat = self.get_dataset("Repetitions")
        self.cooling_time = self.get_dataset("Doppler.Time(ms)") * ms




    @kernel
    def run_once(self):

        """Retrieves constant values from dataset, then runs experiment"""

        # detFreq = self.recoolfreq.get()
        # detAmp = self.recoolamp.get()
        # detTime=self.recooltime.get()
        # waitTime=self.waittime.get()
        self.run.ON(self.waittime.get(), self.cooling_freq,self.cooling_amp,self.cooling_time, self.recoolfreq.get(), self.recoolamp.get(), self.recooltime.get(), self.num_repeat) #calls ON function in runScan fragment

        # self.run.counts.push(np.log(self.run.mean_rising_edges))
        self.host_push_results(self.run.mean_rising_edges, self.run.points)

        #print(self.analyses.describe_online_analyses())
        #self.test.push(np.sin(9586958.6))


    @rpc(flags={"async"})
    def host_push_results(self, mean_rising_edges, points):

        self.run.counts.push(mean_rising_edges)
        self.run.res_err.push(mean_rising_edges/ sqrt(self.num_repeat))
        print('Mean:'+str(10**-3*mean_rising_edges/self.recooltime.get())+'\n'+'Stddev:'+str(10**-3*mean_rising_edges/ sqrt(self.num_repeat)/self.recooltime.get()))

        #print("{0:.7f}".format(mean_rising_edges/ sqrt(self.num_repeat)))
        # print(oitg.fitting.exponential_decay.fit(self.time, self.run.counts, self.run.res_err, evaluate_function=True,
        #                                          evaluate_n=100))

    def save_global_dataset(self):
        '''
         Save all global dataset parameters in a dictionary here.
        '''

        parentdir = r"C:\Users\TrappedIonRice4\Documents\Artiq-Rice" # system dependent
        datasetdir = parentdir + "\dataset_db.pyon"
        self.globaldataset = {}
        f=open(datasetdir, 'r')
        txt=f.readlines()
        f.close() # must close the dataset file soon enough to reflect the updates.
        for ele in txt[1:-1]: #ignoring curly braces
            ele2 = ele.split(":") # some regex
            ele3 = (ele2[0].split('    '))[-1]
            ele4=''.join(list(ele3)[1:-1])
            self.globaldataset[ele4]=self.get_dataset(ele4)

    def host_cleanup(self):
        self.save_global_dataset()
        #print(self.run.counts)


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
                              "y": self.run.counts,
                              "y_err": self.run.res_err,
                          },
                   #       constants= dict_constants
                          )
            ]
        else:
            return []

ScanForTime = make_fragment_scan_exp(executeScan)




