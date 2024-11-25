from ndscan.experiment import *
from oitg.results import *
import numpy as np
from oitg.errorbars import binom_onesided,binom_twosided
from matplotlib import pyplot as plt
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
        self.setattr_device("urukul1_cpld")  # Necessary for clock sync
        self.setattr_device("urukul1_ch0")
        self.setattr_device("urukul1_ch1") # OP
        self.setattr_device("urukul1_ch2") # MW
        self.setattr_device("urukul1_ch3")  # 355 switch

        self.setattr_device("urukul2_cpld")  # Necessary for clock sync
        self.setattr_device("urukul2_ch0") # Raman 1
        self.setattr_device("urukul2_ch1") # Raman 2

        self.setattr_device("ttl5")
        self.setattr_device("ttl6")
        self.histpoints = np.zeros(self.get_dataset("Repetitions"), dtype=int)

        ttl_params = ["ttl1_counter"]
        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl1_counter"))
        self.setattr_device(str(self.INPUT_TTL)) #must typecast or NoneType error when recomputing args
        self.ttl = self.get_device(self.INPUT_TTL)

        self.sum_rising_edges=0.0
        self.sum_rising_edges_cooling=0.0
        self.setattr_result("counts")
        #self.setattr_result("cooling_counts")
        self.setattr_result("res_err", display_hints={"error_bar_for": self.counts.path})
        self.points = [[0.0] * self.get_dataset("Repetitions"), [0.0] * self.get_dataset("Repetitions")]

        self.gate_end_mu = np.int64(0) # necessary or type error when assigning new val
        self.mean_rising_edges = 0.0
        #self.mean_rising_edges_cooling=0.0
        self.channel_num = [1] # Doppler, Det, OP

        self.originalDCElectrodeValues= self.get_dataset("DC.ElectrodeValues")
        self.modDCElectrodeValues= self.get_dataset("DC.ElectrodeValues") # to be modified
        self.DCElectrodeMapping= self.get_dataset("DC.ElectrodeMapping")
        self.originalEndcapX=self.get_dataset("DC.EndcapX")
        self.originalAllY=self.get_dataset("DC.AllY")
        self.originalAllZ=self.get_dataset("DC.AllZ")

    @kernel
    def endcapX(self, V):
        """
        pushes towards +ve X with endcaps
        """
        self.electrodeUpdate(V, [1, 5, 6, 10], [1, -1, -1, 1])

    @kernel
    def allY(self, V):
        """
        pushes towards +ve Y with all electrodes
        """
        self.electrodeUpdate(V,[0,1,2,3,4,5,6,7,8,9,10,11],[-1]+[-1]*5+[1]*5+[1])
    @kernel
    def allZ(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V,[0,1,2,3,4,5,6,7,8,9,10,11],[1]+[-1]*5+[1]*5+[-1])

    @kernel
    def electrodeUpdate(self,V,electrodeList,signList):
        for i in range(len(electrodeList)):
            self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] = self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] + V*(signList[i])
    # @kernel
    # def pulseDetection(self, det_time):
    #     self.urukul0_ch2.sw.on()  # 935 on
    #     self.urukul0_ch3.sw.on()
    #     delay(det_time)
    #     self.urukul0_ch2.sw.off()  # 935 on
    #     self.urukul0_ch3.sw.off()


    @kernel
    def ON(self,Frequency435,Amplitude435,Time435,Attenuation_435,choice435, doppler_freq,doppler_amp,doppler_time,
           det_freq,det_amp,det_time,
           freq_935,amp_935,
           OP_freq,OP_amp, OP_time, MW_freq, MW_amp, MW_time,
           SBCFrequency435_1, SBCAmplitude435_1, SBCFrequency435_2, SBCAmplitude435_2, SBCTime, SBCAmplitude935,
           ClearoutPower935, ClearoutTime935,
           prepfreq435, preptime, wait_time,
           Frequency355switch, Amplitude355switch, Attenuation355switch,
           FrequencyRaman1, AmplitudeRaman1,
           FrequencyRaman2, AmplitudeRaman2,
           Raman_time,
           RamseyFrequency435, RamseyAmplitude435, PiBy2Time435_1,PiBy2Time435_2,
           newEndcapX, newAllY, newAllZ, piezoR1H, piezoR1V ,piezoR2H ,piezoR2V ,  num_repeat):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Calculates mean
        rising edges for a given num_repeat to push to counts channel"""

        self.core.reset()
        #self.core.break_realtime()
        #zotino
        self.zotino0.init()
        delay(2 * ms)
        # updating zotino with all voltage combinations on electrodes.

        for i in range(12):
            self.modDCElectrodeValues[i]=self.originalDCElectrodeValues[i]
        #adding up combinations
        newX=newEndcapX-self.originalEndcapX
        newY=newAllY - self.originalAllY
        newZ=newAllZ - self.originalAllZ
        self.endcapX(newX)
        self.allY(newY)
        self.allZ(newZ)
        #print(self.modDCElectrodeValues)
        #print(newX)
        #print(newEndcapX)
        #z=self.originalDCElectrodeValues-self.modDCElectrodeValues
        #print(self.modDCElectrodeValues)

        AOMdelay=-2.4*us


        for i in range(12):
            ind=self.DCElectrodeMapping[i]
            self.zotino0.write_dac(self.DCElectrodeMapping[i],self.modDCElectrodeValues[ind])
            self.zotino0.load()
            delay(2 * ms)

        # piezo voltage  update
        self.zotino0.write_dac(24, piezoR1H) # new DAC value for 435, need more for 355 beams
        self.zotino0.load()
        delay(2 * ms)
        self.zotino0.write_dac(25, piezoR1V)  # new DAC value for 435, need more for 355 beams
        self.zotino0.load()
        delay(2 * ms)
        self.zotino0.write_dac(26, piezoR2H)  # new DAC value for 435, need more for 355 beams
        self.zotino0.load()
        delay(2 * ms)
        self.zotino0.write_dac(27, piezoR2V)  # new DAC value for 435, need more for 355 beams
        self.zotino0.load()
        delay(2 * ms)

        self.urukul0_cpld.init()
        # self.urukul1_cpld.init()
        # self.urukul2_cpld.init()
        delay(1 * ms)
        attenuation=3.0 # use as required

        # self.urukul0_cpld.init() # for now this isn't doing anything
        # self.urukul0_ch0.init()
        # Doppler+935
        self.urukul0_ch1.init()
        self.urukul0_ch1.set_att(0*dB)
        self.urukul0_ch1.set( frequency= doppler_freq, amplitude=doppler_amp, phase_mode=2)
        self.urukul0_ch1.sw.off()

        self.urukul0_ch2.init()
        self.urukul0_ch2.set_att(0 * dB)
        self.urukul0_ch2.set(frequency=freq_935, amplitude=amp_935, phase_mode=2)
        self.urukul0_ch2.sw.off()

        # 435
        self.urukul0_ch0.init()
        self.urukul0_ch0.set_att(Attenuation_435 * dB)
        self.urukul0_ch0.sw.off()
        self.urukul1_ch0.init()
        self.urukul1_ch0.set_att(Attenuation_435 * dB)
        self.urukul1_ch0.sw.off()

        # Detection
        self.urukul0_ch3.init()
        self.urukul0_ch3.set_att(0 * dB)
        self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
        self.urukul0_ch3.sw.off()

        # OP
        self.urukul1_ch1.init()
        self.urukul1_ch1.set_att(0 * dB)
        self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
        self.urukul1_ch1.sw.off()

        # MW
        self.urukul1_ch2.init()
        self.urukul1_ch2.set_att(0 * dB)
        self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
        self.urukul1_ch2.sw.off()





        # 355 global switch
        self.urukul1_ch3.init()
        self.urukul1_ch3.set_att(Attenuation355switch* dB)
        self.urukul1_ch3.set(frequency=Frequency355switch, amplitude=Amplitude355switch, phase_mode=2)
        self.urukul1_ch3.sw.off()

        # 355 Raman 1
        self.urukul2_ch0.init()
        self.urukul2_ch0.set_att(0 * dB)
        self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
        self.urukul2_ch0.sw.off()

        # 355 Raman 2
        self.ttl6.output()

        # Experiment sync trigger
        self.ttl5.output()

        # self.urukul2_ch1.init()
        # self.urukul2_ch1.set_att(0 * dB)
        # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
        # self.urukul2_ch1.sw.off()

        self.sum_rising_edges = 0.0
        #self.sum_rising_edges_cooling = 0.0

        # exp loop without dma




        i=0
        while(i<num_repeat):
            #delay(30 * us)  # This delay will exist between repetitions

            self.ttl5.on()
            #if doppler_time> 0.0:

            # self.urukul0_ch1.set_att(0 * dB)
            # self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            self.urukul0_ch2.sw.on()
            delay(doppler_time)
            #self.ttl.gate_rising(doppler_time)

            #self.urukul0_ch2.set_att(30 * dB)
            self.urukul0_ch1.sw.off()
            self.urukul0_ch2.sw.off()
            self.ttl5.off()
            #self.urukul0_ch1.set_att(30 * dB)
            #delay(0.05*ms)
            #y = self.ttl.fetch_count()
            #self.sum_rising_edges_cooling = self.sum_rising_edges_cooling + y
            #delay(0.05*ms)
            #435 SBC

            #CSBC

            #if SBCTime>0:
            #delay(-7 * us)  # important for syncing. Must be before setting up the DDS config or else there is some gradual ampltiude ramp of 435 DDS

            # 2nd order Yb172
            # self.urukul0_ch0.set(frequency=247.825*MHz, amplitude=SBCAmplitude435_1, phase_mode=2)
            # self.urukul1_ch0.set(frequency=238.73833*MHz, amplitude=SBCAmplitude435_2, phase_mode=2)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=SBCAmplitude935, phase_mode=2)
            # self.urukul0_ch0.sw.on()
            # self.urukul1_ch0.sw.on()
            # self.urukul0_ch2.sw.on()
            # delay(0*ms)
            # self.urukul0_ch0.sw.off()
            # self.urukul1_ch0.sw.off()
            # self.urukul0_ch2.sw.off()

            # 1st order Yb172
            # self.urukul0_ch0.set(frequency=SBCFrequency435_1, amplitude=SBCAmplitude435_1, phase_mode=2)
            # self.urukul1_ch0.set(frequency=SBCFrequency435_2, amplitude=SBCAmplitude435_2, phase_mode=2)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=SBCAmplitude935, phase_mode=2)
            # self.urukul0_ch0.sw.on()
            # self.urukul1_ch0.sw.on()
            # self.urukul0_ch2.sw.on()
            # delay(SBCTime)
            # self.urukul0_ch0.sw.off()
            # self.urukul1_ch0.sw.off()
            # self.urukul0_ch2.sw.off()

            # 2nd order Yb171, uses ch2 435
            # # self.urukul0_ch0.set(frequency=SBCFrequency435_1, amplitude=SBCAmplitude435_1, phase_mode=2)
            # self.urukul1_ch0.set(frequency=SBCFrequency435_2, amplitude=SBCAmplitude435_2, phase_mode=2)
            # self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=SBCAmplitude935, phase_mode=2)
            # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
            # # self.urukul1_ch2.sw.on()
            # #self.urukul0_ch0.sw.on()
            # self.urukul1_ch0.sw.on()
            # self.urukul0_ch2.sw.on()
            # self.urukul1_ch1.sw.on()
            # delay(SBCTime*0)
            # #self.urukul0_ch0.sw.off()
            # self.urukul1_ch0.sw.off()
            # self.urukul0_ch2.sw.off()
            # self.urukul1_ch1.sw.off()
            # #  self.urukul1_ch2.sw.off()



          #   # 1st order Yb171, uses ch1 435
          #   self.urukul0_ch0.set(frequency=SBCFrequency435_1, amplitude=SBCAmplitude435_1, phase_mode=2)
          #  # self.urukul1_ch0.set(frequency=SBCFrequency435_2, amplitude=SBCAmplitude435_2, phase_mode=2)
          #   self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
          #   self.urukul0_ch2.set(frequency=freq_935, amplitude=SBCAmplitude935, phase_mode=2)
          #  # self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
          #  # self.urukul1_ch2.sw.on()
          #   self.urukul0_ch0.sw.on()
          # #  self.urukul1_ch0.sw.on()
          #   self.urukul0_ch2.sw.on()
          #   self.urukul1_ch1.sw.on()
          #   delay(SBCTime*0)
          #   self.urukul0_ch0.sw.off()
          # #  self.urukul1_ch0.sw.off()
          #   self.urukul0_ch2.sw.off()
          #   self.urukul1_ch1.sw.off()
          # #  self.urukul1_ch2.sw.off()



            #delay(5.5*ms)
            #Pulsed SBC

            self.urukul2_ch0.set(frequency=SBCFrequency435_1, amplitude=SBCAmplitude435_1, phase_mode=2)
            #self.urukul2_ch0.set(frequency=SBCFrequency435_2, amplitude=SBCAmplitude435_2, phase_mode=2)

            #self.urukul0_ch1.set(frequency=freq_935, amplitude=SBCAmplitude935, phase_mode=2)
            self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)

            # Outer
            if SBCTime>0:
                for cyc in range(10):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    delay(0.1*ms)
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
            #        self.urukul1_ch0.sw.on()
            #        delay(SBCTime)
            #        self.urukul1_ch0.sw.off()
            #       self.urukul0_ch2.sw.on()
                    self.urukul1_ch1.sw.on()
                    delay(0.03*ms)
            #        self.urukul0_ch2.sw.off()
                    self.urukul1_ch1.sw.off()

                for cyc in range(20):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    delay(0.21 * ms)
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    #        self.urukul1_ch0.sw.on()
                    #        delay(SBCTime)
                    #        self.urukul1_ch0.sw.off()
                    #       self.urukul0_ch2.sw.on()
                    self.urukul1_ch1.sw.on()
                    delay(0.03 * ms)
                    #        self.urukul0_ch2.sw.off()
                    self.urukul1_ch1.sw.off()

            # # Inner
            # self.urukul2_ch0.set(frequency=SBCFrequency435_2, amplitude=SBCAmplitude435_2, phase_mode=2)
            #
            # #if SBCTime > 0:
            # for cyc in range(40):
            #     self.urukul2_ch0.sw.on()
            #     self.ttl6.on()
            #     delay(SBCTime)
            #     self.urukul2_ch0.sw.off()
            #     self.ttl6.off()
            #     #        self.urukul1_ch0.sw.on()
            #     #        delay(SBCTime)
            #     #        self.urukul1_ch0.sw.off()
            #     #       self.urukul0_ch2.sw.on()
            #     self.urukul1_ch1.sw.on()
            #     delay(0.05 * ms)
            #     #        self.urukul0_ch2.sw.off()
            #     self.urukul1_ch1.sw.off()


            # D state prep with detection
            # self.urukul0_ch3.sw.on()
            # delay(DstateprepTimemod)
            # self.urukul0_ch3.sw.off()

            # 935 clearout
            # delay(10 * us)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=ClearoutPower935, phase_mode=2)
            # self.urukul0_ch2.sw.on()
            # delay(0* ms) # ClearoutTime935
            # self.urukul0_ch2.sw.off()
            # delay(10 * us)

            # delay(50 * us)


            # OP state prep with 935

            self.ttl5.on()
            self.urukul1_ch1.set_att(0 * dB)
            #self.urukul0_ch2.set_att(0 * dB)
            self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
            self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
            self.urukul1_ch1.sw.on()
            self.urukul0_ch2.sw.on()
            delay(OP_time)
            delay_mu(1)

            self.urukul1_ch1.sw.off()
            self.urukul0_ch2.sw.off()
            self.ttl5.off()
            #self.urukul0_ch2.set_att(30 * dB)
            #delay(5 * us)


            #delay(0.05*ms)




            #Using channel 0 of urukul 0
            #Ramsey first pi 435 pulse

            #delay(-1*us) # important for syncing. Must be before setting up the DDS config or else there is some gradual ampltiude ramp of 435 DDS



            # MW ramsey

            # self.urukul1_ch2.set_att(0 * dB)
            self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
            #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
            self.urukul1_ch2.sw.on()
            delay(PiBy2Time435_1)
            delay_mu(1)
            # self.urukul1_ch2.set_att(30 * dB)
            self.urukul1_ch2.sw.off()
            #delay(0.05*ms)

            # # wait time
            delay(wait_time)
            delay_mu(1)

            # wait time with 355 on
            #
            # self.urukul1_ch3.sw.on()
            # self.urukul2_ch0.sw.on() # Raman 1
            # #self.ttl6.on() # Raman 2
            # delay(wait_time)
            # delay_mu(1)
            # self.urukul2_ch0.sw.off() # Raman 1
            # #self.ttl6.off() # Raman 2
            # self.urukul1_ch3.sw.off()



            # Ramsey second pi 435 pulse

            self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
            #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
            # self.urukul1_ch2.set_att(0 * dB)
            self.urukul1_ch2.sw.on()
            delay(PiBy2Time435_2)
            delay_mu(1)
            # self.urukul1_ch2.set_att(30 * dB)
            self.urukul1_ch2.sw.off()

            #delay(0.05*ms)





            # 435 interaction

            #self.urukul0_ch2.sw.on() # 935 repumper
            # if choice435==1:
            #     self.urukul0_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
            #     self.urukul0_ch0.sw.on()
            #     delay(Time435)
            #     self.urukul0_ch0.sw.off()
            # elif choice435==2:
            #     #delay(10*us) # a delay because suspectected pulse sequence was not running properly. Have to revisit it.
            #     self.urukul1_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
            #     self.urukul1_ch0.sw.on()
            #     delay(Time435)
            #     self.urukul1_ch0.sw.off()
            #self.urukul0_ch2.sw.off() # 935 repumper

            # For dual drive

            # self.urukul0_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
            # self.urukul1_ch0.set(frequency=prepfreq435, amplitude=Amplitude435, phase_mode=2)
            # self.urukul0_ch0.sw.on()
            # self.urukul1_ch0.sw.on()
            # delay(Time435)
            # self.urukul0_ch0.sw.off()
            # self.urukul1_ch0.sw.off()

            # delay(50 * us)

            # # 935 PUMPING INTERACTION
            # delay(10 * us)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
            # self.urukul0_ch2.sw.on()
            # delay(ClearoutTime935)
            # self.urukul0_ch2.sw.off()
            # delay(10 * us)


            # MW interaction
            self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
            #self.urukul1_ch2.set_att(0 * dB)
            self.urukul1_ch2.sw.on()
            delay(MW_time)
            delay_mu(1)
            #self.urukul1_ch2.set_att(30 * dB)
            self.urukul1_ch2.sw.off()

            # 355 Turning on global switch
            #self.urukul1_ch3.set_att(0 * dB)
            #self.urukul1_ch3.sw.on()
            #delay_mu(1)
            #delay(10*us) # essential or else underflow
            # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
            # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
            # delay(0.1 * ms)
            #self.ttl5.on()



            # Raman 1 + 2
            self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
            #self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
            #self.urukul2_ch0.set_att(0 * dB)

            self.urukul2_ch0.sw.on()
            self.ttl6.on()
            #self.urukul2_ch1.sw.on()
            delay(Raman_time)
            delay_mu(1)
            #self.urukul2_ch0.set_att(30 * dB)
            self.urukul2_ch0.sw.off()
            self.ttl6.off()
            #self.urukul2_ch1.sw.off()
            #self.urukul2_ch0.set_att(30 * dB)
            #self.urukul1_ch3.sw.off()
           # self.ttl5.off()
           # delay(0.05*ms)




            # 935 clearout
            # # delay(10 * us)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=ClearoutPower935, phase_mode=2)
            # self.urukul0_ch2.sw.on()
            # delay(ClearoutTime935)
            # self.urukul0_ch2.sw.off()
            # delay(10 * us)

            # self.urukul0_ch3.sw.on()
            # #delay(200*us)
            # delay(wait_time)
            # self.urukul0_ch3.sw.off()
           # # # self.urukul0_ch2.sw.off()
           # delay(wait_time)

            # delay(500*ms)
            


            # Detection w. 935

            self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
           # delay(AOMdelay)
            self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
           # delay(AOMdelay)

            #self.urukul1_ch1.set_att(30 * dB)
            # self.urukul1_ch1.set(frequency=OP_freq, amplitude=det_amp, phase_mode=2)
            #
            # self.urukul1_ch1.sw.off()

            # a little bit of Doppler for pumping out dark state
            # self.urukul0_ch1.set(frequency=doppler_freq, amplitude=0.8, phase_mode=2)
            # self.urukul0_ch1.sw.on()

            #self.urukul0_ch3.set_att(0 * dB)


            #
            self.urukul1_ch3.sw.on()
            self.urukul0_ch2.sw.on() #935 on
            self.urukul0_ch3.sw.on()
            self.ttl5.on()



            # for simple detection using edge counter
            # delay(50*us)
            #with parallel:
            #delay(-5*us)
            self.ttl.gate_rising(det_time)
                #self.pulseDetection(det_time)
            delay_mu(1)


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
            # delay(50*us)
            # self.urukul0_ch2.set_att(30 * dB)
            # self.urukul0_ch3.set_att(30 * dB)

            self.urukul0_ch3.sw.off()
            self.urukul0_ch2.sw.off() #935 on
            #self.urukul0_ch1.sw.off()
            self.urukul1_ch3.sw.off()
            self.ttl5.off()

            delay(10 * us)


            # continue Doppler+935

            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
            self.urukul0_ch1.set_att(0 * dB)
            self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch1.sw.on()
            self.urukul0_ch2.sw.on()
           # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)

            #delay(30 * us)
            # self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
          #  self.ttl5.off()
            # extra computations always left at the end of the scan, or else RTIO underflow occurs for Kasli. Problem doesn't persist with Kasli SOC.

            #self.sum_rising_edges = self.sum_rising_edges + x
            #delay(3*ms)
            #delay_mu(1)

            x = self.ttl.fetch_count()
            #self.ttl.set_config(count_rising=True, count_falling=False, send_count_event=False, reset_to_zero=True)
            self.histpoints[i]=x
            delay(10*us)

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

       # self.mean_rising_edges = (self.sum_rising_edges)/(num_repeat)
       # self.mean_rising_edges_cooling=(self.sum_rising_edges_cooling)/(num_repeat)


class executeScan(ExpFragment):

    """Scan AOM355 DC control"""

    def build_fragment(self):
        # self.setattr_param("channel", IntParam, "CHOOSE URUKUL CHANNEL (0-3)", default=0)

        self.setattr_param("SBCcheck", BoolParam, "SBC 435: ", default=False)
        self.setattr_param("SBCFrequency435_1", FloatParam, "Set SBC Frequency 435_1", unit="MHz", default=190.50233 * MHz)
        self.setattr_param("SBCAmplitude435_1", FloatParam, "Set SBC Amplitude 435_1 ", unit="", default=0.80, min=0.00, max=0.8)

        self.setattr_param("SBCFrequency435_2", FloatParam, "Set SBC Frequency 435_2", unit="MHz", default=190.7228 * MHz)
        self.setattr_param("SBCAmplitude435_2", FloatParam, "Set SBC Amplitude 435_2 ", unit="", default=0.80, min=0.00, max=0.8)

        self.setattr_param("SBCTime", FloatParam, "Set SBC Time ", unit="ms", default=0.03 * ms, min=0.00001*ms)
        self.setattr_param("SBCAmplitude935", FloatParam, "Set SBC Amplitude 935 ", unit="", default=0.00500, min=0.00, max=0.8)

        self.setattr_param("ClearoutPower935", FloatParam, "Set 935 Clearout Power ", unit="", default=0.01, max= 0.8)
        self.setattr_param("ClearoutTime935", FloatParam, "Set 935 Clearout Time ", unit="ms", min=0.00001*ms, default=0.05 * ms)

        self.setattr_param("StatePrepOP", BoolParam, "State Preparation with OP: ", default=True)
        self.setattr_param("prepfreqOP", FloatParam, "Set Prep OP frequency", unit="MHz", default=215 * MHz)
        self.setattr_param("prepampOP", FloatParam, "Set Prep OP amplitude", unit="", default=0.8, max= 0.8)
        self.setattr_param("preptimeOP", FloatParam, "Set Prep OP time", unit="ms", default=0.05 * ms)

        self.setattr_param("StatePrep", BoolParam, "State Preparation: ", default=False)
        self.setattr_param("prepfreq435", FloatParam, "Set Prep 435 frequency", unit="MHz", default=234.1743* MHz)
        self.setattr_param("preptime", FloatParam, "Set Prep time", unit="ms", default=2 * ms,  min=0.00001*ms)

        self.setattr_param("choice435", IntParam, "Choose 435 channel (1,2): ", default=1, min=1, max=2)
        self.setattr_param("Ramsey435check", BoolParam, "Ramsey on/off: ", default=False)
        self.setattr_param("WaitTime", FloatParam, "Set Wait Time ", unit="ms", default=0.00 * ms, min=0.00001*ms)

        self.setattr_param("FrequencyMW", FloatParam, "Set Frequency MW", unit="MHz", default=142.83959* MHz)
        self.setattr_param("AmplitudeMW", FloatParam, "Set Amplitude MW ", unit="", default=0.80, min=0.00, max=0.8)
        self.setattr_param("TimeMW", FloatParam, "Set Time MW ", unit="ms", default=0.0088 * ms, min=0.00001*ms)

        self.setattr_param("Frequency435", FloatParam, "Set Frequency 435",unit="MHz", default= 243.2854*MHz) #changed min to 1 to avoid fit issue when 0
        self.setattr_param("Amplitude435", FloatParam, "Set Amplitude 435 ", unit="", default=0.000 , min=0.00, max=0.8)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Time435", FloatParam, "Set Time 435 ",unit="ms", default= 0.01*ms, min=0.00001*ms)

        self.setattr_param("Frequency355_Raman1", FloatParam, "Set Frequency 355_Raman1", unit="MHz", default=190.50233 * MHz)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Amplitude355_Raman1", FloatParam, "Set Amplitude 355_Raman1 ", unit="", default=0.800, min=0.00, max=0.8)

        self.setattr_param("Frequency355_Raman2", FloatParam, "Set Frequency 355_Raman2", unit="MHz", default=222.848159 * MHz)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Amplitude355_Raman2", FloatParam, "Set Amplitude 355_Raman2 ", unit="", default=0.800, min=0.00, max=0.8)

        self.setattr_param("RamanTime", FloatParam, "Set 355 Raman time ", unit="ms", default=0.0 * ms, min=0.00001*ms)

        self.setattr_param("CheckThresholding", BoolParam, "Thresholding On/Off ", default= False)
        self.setattr_param("DetTime369", FloatParam, "Set Detection Time ", unit="ms", default=0.3 * ms, min=0.00001*ms)

        self.setattr_param("endcapX", FloatParam, "Set EndcapX ", unit="", default=0.0 )
        self.setattr_param("allY", FloatParam, "Set AllY ", unit="", default=0.027 )
        self.setattr_param("allZ", FloatParam, "Set AllZ ", unit="", default=0.012 )

        self.setattr_param("piezoR1H", FloatParam, "Set Raman 1 Piezo Horizontal ", unit="", default=6.3, min= 0.0, max= 10.0)
        self.setattr_param("piezoR1V", FloatParam, "Set Raman 1 Piezo Vertical ", unit="", default=3.2, min=0.0, max=10.0)
        self.setattr_param("piezoR2H", FloatParam, "Set Raman 2 Piezo Horizontal ", unit="", default=4.6, min=0.0, max=10.0)
        self.setattr_param("piezoR2V", FloatParam, "Set Raman 2 Piezo Vertical ", unit="", default=3.8, min=0.0, max=10.0)

        self.setattr_fragment("run", runScan) #Assigns runScan fragment and its attributes/functions to this fragment

        self.setattr_device("scheduler")


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

        self.scanHistogramList=np.array([np.zeros(self.get_dataset('Repetitions'), dtype=int)])
        self.PMTThreshold=self.get_dataset("PMTThreshold")

        self.det_freq = self.get_dataset("Detection.Frequency")
        self.det_amp = self.get_dataset("Detection.Amp")
        self.det_time = self.get_dataset("Detection.Time(ms)") * ms

        self.freq_935 = self.get_dataset("935.Frequency")
        self.amp_935 = self.get_dataset("935.Amp")


        self.attenuation_435_1=self.get_dataset("435_1.Attenuation")

        self.frequency355switch= self.get_dataset("355_switch.Frequency")
        self.amplitude355switch=self.get_dataset("355_switch.Amp")
        self.attenuation355switch= self.get_dataset("355_switch.Attenuation")



        self.RamseyFrequency435mod=self.get_dataset("Ramsey.Frequency435")+self.get_dataset("Ramsey.Detuning435")
        self.RamseyAmplitude435= self.get_dataset("Ramsey.Amplitude435")
        self.PiBy2Time435_1 = self.get_dataset("Ramsey.PiBy2Time435_1(ms)")*ms
        self.PiBy2Time435_2 = self.get_dataset("Ramsey.PiBy2Time435_2(ms)")*ms




        self.modSBCtime=0.0
        self.modpreptime = 0.0
        self.modpreptimeOP=0.0
        self.PiBy2Time435_1mod = 0.0
        self.PiBy2Time435_2mod = 0.0


        plt.figure()

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

        if (self.StatePrepOP.get()==True):
            self.modpreptimeOP=self.preptimeOP.get()

        if (self.Ramsey435check.get()==True):
            self.PiBy2Time435_1mod= self.PiBy2Time435_1
            self.PiBy2Time435_2mod= self.PiBy2Time435_2


        self.run.ON(self.Frequency435.get(),self.Amplitude435.get(),self.Time435.get(),self.attenuation_435_1, self.choice435.get(),\
                    self.doppler_freq,self.doppler_amp,self.doppler_time,\
                    self.det_freq,self.det_amp,self.DetTime369.get(), \
                    self.freq_935,self.amp_935, \
                    self.prepfreqOP.get(), self.prepampOP.get(), self.modpreptimeOP, self.FrequencyMW.get(), self.AmplitudeMW.get(), self.TimeMW.get(), \
                    self.SBCFrequency435_1.get(),self.SBCAmplitude435_1.get(),self.SBCFrequency435_2.get(),self.SBCAmplitude435_2.get(), self.modSBCtime, self.SBCAmplitude935.get(),\
                    self.ClearoutPower935.get(),self.ClearoutTime935.get(),\
                    self.prepfreq435.get(),self.modpreptime, \
                    self.WaitTime.get(), \
                    self.frequency355switch, self.amplitude355switch, self.attenuation355switch,\
                    self.Frequency355_Raman1.get(),self.Amplitude355_Raman1.get() , self.Frequency355_Raman2.get(), self.Amplitude355_Raman2.get(),\
                    self.RamanTime.get(),\
                    self.RamseyFrequency435mod, self.RamseyAmplitude435, self.PiBy2Time435_1mod, self.PiBy2Time435_2mod,\
                    self.endcapX.get(),self.allY.get(), self.allZ.get(), self.piezoR1H.get(), self.piezoR1V.get(), self.piezoR2H.get(), self.piezoR2V.get(),\
                    self.num_repeat) #calls ON function in runScan fragment

        # self.run.counts.push(np.log(self.run.mean_rising_edges))

        self.host_push_results(self.run.points,self.run.histpoints)
        #print(self.run.histpoints)
        #print(self.analyses.describe_online_analyses())
        #self.test.push(np.sin(9586958.6))


    @rpc(flags={"async"})
    def host_push_results(self,points, histpoints):

        # self.run.counts.push(mean_rising_edges/self.det_time)
        # self.run.res_err.push(mean_rising_edges/(self.det_time*sqrt(self.num_repeat)))
        #T=self.DetTime369.get()

        # storing histograms
        if np.sum(self.scanHistogramList)==0: # trivial condition to get rid of 0 array that was intialized
            self.scanHistogramList = np.array([histpoints])
        else:
            self.scanHistogramList=np.vstack((self.scanHistogramList, [histpoints]))

        # Thresholding
        if self.CheckThresholding.get():

            p,p_err=binom_onesided(np.sum(histpoints>=self.PMTThreshold), self.num_repeat)
            self.run.counts.push(p)
            self.run.res_err.push(p_err)
        else:
            self.run.counts.push(np.mean(histpoints))
            self.run.res_err.push(np.std(histpoints)/np.sqrt(self.num_repeat))
        #
        # plt.hist(histpoints, bins=30)
        # ax=plt.gca()
        # # ax.set_ylim([0,200])
        # # ax.set_xlim([0, 150])
        # plt.pause(0.5)
        # plt.clf()

        # else:
        #     self.scanHistogramList=[histpoints]
        #print(self.scanHistogramList)
        # self.run.counts.push(mean_rising_edges /1)
        # self.run.res_err.push(mean_rising_edges/(1*sqrt(self.num_repeat)))
        #self.scanHistogramList.append(self.run.histpoints)

        #self.run.cooling_counts.push(mean_rising_edges_cooling / 1)

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

        # reinstantisate global dataset DC values
        DCcontrolId = {
            "file": "RFandDC/DCelectrodes.py",
            "class_name": "DC_Control",
            "arguments": {},
            "log_level": self.scheduler.expid["log_level"],
            "repo_rev": self.scheduler.expid["repo_rev"],
        }
        self.scheduler.submit("main", DCcontrolId)
        self.set_dataset('Histogram',self.scanHistogramList,broadcast=True, archive=True, persist=True)
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




