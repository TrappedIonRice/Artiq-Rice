from ndscan.experiment import *
from oitg.results import *
import numpy as np
from matplotlib import pyplot as plt
from statistics import stdev
from math import *
import time as tm
import datetime
import oitg.fitting

class runScan(Fragment):

    def build_fragment(self):
        self.setattr_device("core")
        #self.setattr_device("core_dma")
        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        self.setattr_device("urukul0_ch0") # RF channel is very imp
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")

        ttl_params = ["ttl0_counter"]
        self.RFamp=self.get_dataset("UrukulCh0_RFamp")

        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl0_counter"))
        self.setattr_device(str(self.INPUT_TTL)) #must typecast or NoneType error when recomputing args
        self.ttl = self.get_device(self.INPUT_TTL)
        self.setattr_device("ttl4") # triggering TimeHarp


       # self.setattr_result("counts_arr", result_channels="Opaq")
        self.setattr_result("counts")
       # self.setattr_result("result2")
       # self.setattr_param("urukulchan2freq",FloatParam,"Urukul channel 2 freq", unit="MHz",default=1.0*MHz)
        self.setattr_result("res_err", display_hints={"error_bar_for": self.counts.path})
        self.points = [[0.0] * self.get_dataset("Repetitions"), [0.0]*self.get_dataset("Repetitions")]
        self.gate_end_mu = np.int64(0) # necessary or type error when assigning new val
        self.mean_rising_edges = 0.0
        self.channel_num = [1]
        self.bins = self.get_dataset("NBins")
        self.bintime = self.get_dataset("BinWidth")
        self.counts_arr = np.zeros(self.bins, dtype= 'int32')
        self.counts_arr_temp = np.zeros(self.bins, dtype= 'int32')




    @kernel
    def ON(self, wait_time, coolingfreq, coolingamp, coolingtime, detFreq, detAmp, detTime, num_repeat):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Calculates mean
        rising edges for a given num_repeat to push to counts channel"""


        #self.core.reset()
        self.core.break_realtime()
        #self.urukul0_cpld.init()
        self.urukul0_ch0.init() # leave RF as is
        self.urukul0_ch0.set( frequency= 25.671*MHz, amplitude=self.RFamp)
        self.urukul0_ch0.set_att(0 * dB)
        self.urukul0_ch0.sw.on() # turns it on as in the last config
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.urukul0_ch2.set_att(0 * dB)
        self.urukul0_ch2.sw.on()

        # self.ttl.input()
        self.ttl4.output()
        #self.bintime=detTime/self.bins
        #sum_rising_edges = 0.0
        delay(5*us)
        #bintime=detTime/self.bins

        # for j in range(self.bins):
        #     self.counts_arr[j]=0.0

        #exp loop without dma
        i=0
        while(i<num_repeat):
            delay(30 * us)  # This delay will exist between scan points
            # Doppler cool initially using Global freq and amplitude
            self.urukul0_ch1.set(frequency=coolingfreq, amplitude=coolingamp, phase_mode=2)
            self.urukul0_ch1.set_att(0 * dB)
            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            # self.ttl.gate_rising(coolingtime)
            delay(coolingtime)
            self.urukul0_ch1.sw.off()
            # delay(1*ms)
            # sum_rising_edges=sum_rising_edges+self.ttl.fetch_count()
            # delay(1* ms)
            #wait
            delay(wait_time)

            # Reset Detection DC freq, amp
            self.urukul0_ch1.set(frequency=detFreq, amplitude=detAmp)
            self.urukul0_ch1.set_att(0 * dB)

            # rising trigger to timeharp
            self.ttl4.on() # temporarily commenting
            #Detection DC on
            delay(-100*ns) # to sync TTL4 and Doppler DDS
            self.urukul0_ch1.sw.on()
            #Detection with Doppler using script specific freq and amplitude
            # for simple detection using edge counter

            for k in range(0,self.bins,1):
            #    self.counts_arr[k]=k
                #detcounts_time=self.ttl.gate_rising(bin_time)
                #self.ttl4.on()
                self.ttl.gate_rising(self.bintime)
                delay(detTime/self.bins)        # have to correspond this t
                #delay(-1*self.bintime)
                delay(50*us)
                self.counts_arr_temp[k]=self.ttl.fetch_count()
                delay(-50 * us)
                delay(-1*self.bintime)
                #self.ttl4.off()
                #self.counts_arr[k] = self.counts_arr[k] + self.ttl.fetch_count() # To add up count rate
            # without edge counter

            # Detection DC off

            delay(50*us)
            self.urukul0_ch1.sw.off()
            # falling trigger to timeharp
            delay(2 * us)
            self.ttl4.off() # temporarily commenting
            delay(500*us) # to match TTL4 falling edge and Doppler on edges
            #continue Doppler
            self.urukul0_ch1.set(frequency=coolingfreq, amplitude=coolingamp, phase_mode=2)
            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel

            #generally extra computations always left at the end of the scan, or else RTIO underflow occurs

            # for i in range(self.bins):
            #     self.counts_arr[i]=self.counts_arr[i] + i+0*self.ttl.count(detcounts_time_list)
            self.urukul0_ch0.set(frequency=25.671 * MHz, amplitude=self.RFamp)
            self.urukul0_ch0.set_att(0 * dB)
            self.urukul0_ch0.sw.on()

            for k in range(0, self.bins, 1):
                self.counts_arr[k] = self.counts_arr[k] + self.counts_arr_temp[k]

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

       # self.mean_rising_edges = (sum_rising_edges)/(num_repeat)


class executeScan(ExpFragment):

    """Doppler Recooling V2"""

    def build_fragment(self):
       # self.setattr_param("channel", IntParam, "CHOOSE URUKUL CHANNEL (0-3)", default=0)
        self.setattr_param("waittime", FloatParam, "Set Wait Time ",unit="ms", default= 1.000*ms, min = 0.00*ms) #changed min to 1 to avoid fit issue when 0
        self.setattr_param("recooltime", FloatParam, "Set Recooling Time ", unit="ms", default=1.000 * ms, min=0.00 * ms)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("recoolfreq", FloatParam, "Set Recooling Frequency ",unit="MHz", default= 195.000*MHz)
        self.setattr_param("recoolamp", FloatParam, "Set Recooling Amplitude (FROM 0-0.8)", default=0.0, max = 0.800)
        self.setattr_fragment("run", runScan) #Assigns runScan fragment and its attributes/functions to this fragment
        fit_params = ["TIME", "FREQUENCY", "AMPLITUDE"]
        self.setattr_argument("SET_FIT_PARAM", EnumerationValue(fit_params, default="TIME"), group = "SET FIT")
        fits = ["cos", "decaying_sinusoid", "detuned_square_pulse", "exponential_decay",
                "gaussian", "line", "lorentzian", "rabi_flop", "sinusoid", "v_function", "None"]
        self.setattr_argument("CHOOSE_FIT", EnumerationValue(fits, default="None"), group = "SET FIT")


    def host_setup(self):           #reserved key word
        self.cooling_freq = self.get_dataset("Doppler.Frequency")
        self.cooling_amp = self.get_dataset("Doppler.Amp")
        self.num_repeat = self.get_dataset("Repetitions")
        self.cooling_time = self.get_dataset("Doppler.Time(ms)") * ms





    @kernel
    def run_once(self):

        """Retrieves constant values from dataset, then runs experiment"""
        self.run.ON(self.waittime.get(), self.cooling_freq,self.cooling_amp,self.cooling_time,\
                    self.recoolfreq.get(), self.recoolamp.get(), self.recooltime.get(), self.num_repeat) #calls ON function in runScan fragment
        #delay(1*ms)
        # self.run.counts.push(np.log(self.run.mean_rising_edges))
        #self.host_push_results(self.run.mean_rising_edges, self.run.points)



    @rpc(flags={"async"})
    def host_push_results(self, mean_rising_edges, points):

        #print(self.run.mean_rising_edges)
        self.run.counts.push(mean_rising_edges)
        self.run.res_err.push(mean_rising_edges/ sqrt(points))
        #print("{0:.7f}".format(mean_rising_edges/ sqrt(self.num_repeat)))
        # print(oitg.fitting.exponential_decay.fit(self.time, self.run.counts, self.run.res_err, evaluate_function=True,
        #                                          evaluate_n=100))

    def save_global_dataset(self):
        '''
         Save all global dataset parameters in a dictionary here.
        '''

        parentdir =  r"C:\Users\TrappedIonRice4\Documents\Artiq-Rice" # system dependent
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
        #tm.sleep(3)
        print(self.run.counts_arr)

        plt.figure(1)
        modcountsarr=self.run.counts_arr/(self.run.bintime*self.num_repeat)
        bin_arr=np.arange(self.run.bins)*self.recooltime.get()*10**3/self.run.bins
        plt.plot(bin_arr,modcountsarr,'-*')
        plt.grid(visible=True)
        plt.ylabel('Counts')
        plt.xlabel('Recooling Time (ms)')

        plt.show()
        self.save_global_dataset()

        dataarr=np.vstack((bin_arr,modcountsarr))
        dir=r'Z:\Lab Rice\Experimental Projects\Monolithic Trap\Heating Rate\Recooling data\2024-3-27\artiq_pmt'
        filename=r'\recooling_'+datetime.datetime.now().strftime("%b_%d_%Y_%H_%M_%S")+'.csv'
        np.savetxt(dir+filename,dataarr, delimiter=',')
        print('Saved data to :'+dir+filename)
        #print(self.run.counts)



ScanForTime = make_fragment_scan_exp(executeScan)




