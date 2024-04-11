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
        self.setattr_device("zotino0")

        ttl_params = ["ttl0_counter"]
        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl0_counter"))
        self.setattr_device(str(self.INPUT_TTL)) #must typecast or NoneType error when recomputing args
        self.ttl = self.get_device(self.INPUT_TTL)

        self.sum_rising_edges=0.0
        self.setattr_result("counts")
        self.setattr_result("res_err", display_hints={"error_bar_for": self.counts.path})
        self.points = [[0.0] * self.get_dataset("Repetitions"), [0.0] * self.get_dataset("Repetitions")]
        self.gate_end_mu = np.int64(0) # necessary or type error when assigning new val
        self.mean_rising_edges = 0.0
        self.channel_num = [1] # Doppler, Det, OP

    @kernel
    def allY(self, V):
        """
        pushes towards +ve Y with all electrodes
        """
        self.electrodeUpdate(V,range(12),[-1]+[-1]*5+[1]*5+[1])
    @kernel
    def allZ(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V,range(12),[1]+[-1]*5+[1]*5+[-1])

    @kernel()

    @kernel
    def ON(self,Frequency435,Amplitude435,Time435,Attenuation_435, doppler_freq,doppler_amp,doppler_time,
           det_freq,det_amp,det_time,freq_935,amp_935,
           SBCFrequency435,SBCAmplitude435,SBCTime, SBCAmplitude935,
           prepfreq435,preptime, wait_time, endcapX,allY,allZ, num_repeat):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Calculates mean
        rising edges for a given num_repeat to push to counts channel"""

        self.core.reset()
        #self.core.break_realtime()

        #zotino
        self.zotino0.init()
        delay(10 * ms)
        # updating zotino with all voltage combinations on electrodes.
        for i in range(12):
            self.zotino0.write_dac(self.DCElectrodeMapping[i],
                                   self.DCElectrodeValues[self.DCElectrodeMapping[i]])
            self.zotino0.load()
            delay(0.1 * ms)

        self.urukul0_cpld.init()
        delay(10 * ms)
        attenuation=3.0 # use as required

        # self.urukul0_cpld.init() # for now this isn't doing anything
        # self.urukul0_ch0.init()
        # Doppler+935
        self.urukul0_ch1.init()
        self.urukul0_ch1.set_att(0*dB)
        self.urukul0_ch1.set( frequency= doppler_freq, amplitude=doppler_amp, phase_mode=2)
        self.urukul0_ch1.sw.on()
        self.urukul0_ch2.init()
        self.urukul0_ch2.set_att(0 * dB)
        self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
        self.urukul0_ch2.sw.on()

        # 435
        self.urukul0_ch0.init()
        self.urukul0_ch0.set_att(Attenuation_435 * dB)
        self.urukul0_ch0.sw.off()

        # Detection
        self.urukul0_ch3.init()
        self.urukul0_ch3.set_att(3 * dB)
        self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
        self.urukul0_ch3.sw.off()

        self.sum_rising_edges = 0.0

        # exp loop without dma
        i=0
        while(i<num_repeat):
            delay(30 * us)  # This delay will exist between repetitions

            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            self.urukul0_ch2.sw.on()
            delay(doppler_time)
            self.urukul0_ch1.sw.off()
            self.urukul0_ch2.sw.off()

            #435 SBC
            self.urukul0_ch0.set(frequency=SBCFrequency435, amplitude=SBCAmplitude435, phase_mode=2)
            self.urukul0_ch2.set(amplitude=SBCAmplitude935, phase_mode=2)
            self.urukul0_ch0.sw.on()
            self.urukul0_ch2.sw.on()
            delay(SBCTime)
            self.urukul0_ch0.sw.off()
            self.urukul0_ch2.sw.off()

          #  delay(50 * us)
            # 435 state prep

            self.urukul0_ch0.set(frequency=prepfreq435, amplitude=0.8, phase_mode=2)
            self.urukul0_ch2.set(amplitude=0.8, phase_mode=2)
            self.urukul0_ch0.sw.on()
            self.urukul0_ch2.sw.on()
            delay(preptime)
            self.urukul0_ch0.sw.off()
            self.urukul0_ch2.sw.off()

           # delay(50 * us)
            # 435 interaction
            self.urukul0_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
            self.urukul0_ch0.sw.on()
            delay(Time435)
            self.urukul0_ch0.sw.off()

           # delay(50 * us)
            # delay

            delay(wait_time)

            # detection
            self.urukul0_ch3.sw.on()
            #self.urukul0_ch2.sw.on() #935 on
            # for simple detection using edge counter
            self.ttl.gate_rising(det_time)

            # without edge counter
            #detcounts_time = self.ttl.gate_rising(detTime)

            # with parallel:
            #     with sequential:# Q: How to access number of scan points?
            #         maxttl2=(detTime/pulse_time) # detection has to be greater than pulse time
            #         maxttl=int(maxttl2)
            #         for i in range(maxttl):
            #             self.ttl4.pulse(detTime*i/(maxttl2*2.0))
            #             delay(detTime/(maxttl2*2.0))

            # Detection off
            #delay(-100*us)
            self.urukul0_ch3.sw.off()
            #self.urukul0_ch2.sw.off() #935 on

           # delay(50 * us)

            # continue Doppler+935
            self.urukul0_ch1.sw.on()
            self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
            self.urukul0_ch2.sw.on()

            # delay(5 * us)
            # self.urukul0_ch1.sw.on()  # can't use dictionary under kernel

            # extra computations always left at the end of the scan, or else RTIO underflow occurs
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

        self.setattr_param("SBCcheck", BoolParam, "SBC 435: ", default=False)
        self.setattr_param("SBCFrequency435", FloatParam, "Set SBC Frequency 435", unit="MHz", default=250.000 * MHz)
        self.setattr_param("SBCAmplitude435", FloatParam, "Set SBC Amplitude 435 ", unit="", default=0.00, min=0.00, max=0.8)
        self.setattr_param("SBCTime", FloatParam, "Set SBC Time ", unit="ms", default=1.00 * ms)
        self.setattr_param("SBCAmplitude935", FloatParam, "Set SBC Amplitude 935 ", unit="", default=0.0500, min=0.00, max=0.8)

        self.setattr_param("StatePrep", BoolParam, "State Preparation: ", default=False)
        self.setattr_param("prepfreq435", FloatParam, "Set Prep 435 frequency", unit="MHz", default=244.335 * MHz)
        self.setattr_param("preptime", FloatParam, "Set Prep time", unit="ms", default=2 * ms)

        self.setattr_param("Frequency435", FloatParam, "Set Frequency ",unit="MHz", default= 250.000*MHz) #changed min to 1 to avoid fit issue when 0
        self.setattr_param("Amplitude435", FloatParam, "Set Amplitude ", unit="", default=0.000 , min=0.00, max=0.8)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Time435", FloatParam, "Set Time ",unit="ms", default= 1.00*ms)
        self.setattr_param("WaitTime", FloatParam, "Set Wait Time ", unit="ms", default=1.00 * ms)
        self.setattr_param("DetTime369", FloatParam, "Set Detection Time ", unit="ms", default=1.00 * ms)

        self.setattr_param("endcapX", FloatParam, "Set EndcapX ", unit="", default=0.0 )
        self.setattr_param("allY", FloatParam, "Set AllY ", unit="", default=0.0 )
        self.setattr_param("allZ", FloatParam, "Set AllZ ", unit="", default=0.0 )

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
        self.doppler_freq = self.get_dataset("Doppler.Frequency")
        self.doppler_amp = self.get_dataset("Doppler.Amp")
        self.num_repeat = self.get_dataset("Repetitions")
        self.doppler_time = self.get_dataset("Doppler.Time(ms)") * ms


        self.det_freq = self.get_dataset("Detection.Frequency")
        self.det_amp = self.get_dataset("Detection.Amp")
        self.det_time = self.get_dataset("Detection.Time(ms)") * ms

        self.freq_935 = self.get_dataset("935.Frequency")
        self.amp_935 = self.get_dataset("935.Amp")

        self.attenuation_435=self.get_dataset("435.Attenuation")

        self.modSBCtime=0.0
        self.modpreptime = 0.0



       # print(self.Time435.get())
       # print(self.DetTime369.get())

        #self.cooling_time = self.get_dataset("935.Time(ms)") * ms

    @kernel
    def run_once(self):

        """Retrieves constant values from dataset, then runs experiment"""

        if (self.SBCcheck.get()==True):
            self.modSBCtime=self.SBCTime.get()

        if (self.StatePrep.get()==True):
            self.modpreptime=self.preptime.get()

        self.run.ON(self.Frequency435.get(),self.Amplitude435.get(),self.Time435.get(),self.attenuation_435,\
                    self.doppler_freq,self.doppler_amp,self.doppler_time,\
                    self.det_freq,self.det_amp,self.DetTime369.get(),\
                    self.freq_935,self.amp_935 ,\
                    self.SBCFrequency435.get(),self.SBCAmplitude435.get(),self.modSBCtime, self.SBCAmplitude935.get(),\
                    self.prepfreq435.get(),self.modpreptime, \
                    self.WaitTime.get(),\
                    self.endcapX.get(),self.allY.get(), self.allZ.get(),\
                    self.num_repeat) #calls ON function in runScan fragment

        # self.run.counts.push(np.log(self.run.mean_rising_edges))
        self.host_push_results(self.run.mean_rising_edges, self.run.points)

        #print(self.analyses.describe_online_analyses())
        #self.test.push(np.sin(9586958.6))


    @rpc(flags={"async"})
    def host_push_results(self, mean_rising_edges, points):

        # self.run.counts.push(mean_rising_edges/self.det_time)
        # self.run.res_err.push(mean_rising_edges/(self.det_time*sqrt(self.num_repeat)))
        T=self.DetTime369.get()
        self.run.counts.push(mean_rising_edges /1)
        self.run.res_err.push(mean_rising_edges/(1*sqrt(self.num_repeat)))

       # print('Mean:'+str(mean_rising_edges)+'\n'+'Stddev:'+str(mean_rising_edges/ sqrt(self.num_repeat)))

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


    # def get_default_analyses(self):
    #  #   lst_param = [self.x0, self.y0, self.y_inf, self.tau]
    #  #   param_names = ['x0', 'y0', 'y_inf', 'tau']
    #     dict_constants = {}
    #  #   for i in range(len(lst_param)):
    #  #       if lst_param[i] != 0:
    #  #           dict_constants[param_names[i]] = lst_param[i]
    #  #   print(dict_constants)
    #     if self.CHOOSE_FIT != "None":
    #         return [
    #             OnlineFit(self.CHOOSE_FIT,
    #                       data={
    #                           "x": self.dict_obj[self.SET_FIT_PARAM],
    #                           "y": self.run.counts,
    #                           "y_err": self.run.res_err,
    #                       },
    #                #       constants= dict_constants
    #                       )
    #         ]
    #     else:
    #         return []

ScanForTime = make_fragment_scan_exp(executeScan)




