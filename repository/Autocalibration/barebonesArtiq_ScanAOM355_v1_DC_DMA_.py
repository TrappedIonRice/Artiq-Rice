from artiq.experiment import *
import numpy as np
from oitg.results import *
from oitg.errorbars import binom_onesided,binom_twosided
from matplotlib import pyplot as plt


# import include

class allZScan(EnvExperiment):

    # \/ \/ \/ \/ \/ \/ build \/ \/ \/ \/ \/ \/
    def build(self):
        self.setattr_device("core")
        self.setattr_device("core_dma")
        self.setattr_device("scheduler")
        self.setattr_device("ccb")  # needed to make plots displaying the counts
        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("urukul0_ch3")
        self.setattr_device("zotino0")
        self.setattr_device("urukul1_cpld")  # Necessary for clock sync
        self.setattr_device("urukul1_ch0")
        self.setattr_device("urukul1_ch1")  # OP
        self.setattr_device("urukul1_ch2")  # MW
        self.setattr_device("urukul1_ch3")  # 369 protection beam

        self.setattr_device("urukul2_cpld")  # Necessary for clock sync
        self.setattr_device("urukul2_ch0")  # Raman 1 ch1
        self.setattr_device("urukul2_ch1")  # Raman 1 ch2

        self.setattr_device("ttl4")  # Camera Trigger
        self.setattr_device("ttl5")  # exp sync trigger
        self.setattr_device("ttl6")  # Raman 2 shutter
        self.histpoints = np.zeros(self.get_dataset("Repetitions"), dtype=int)

        ttl_params = ["ttl1_counter"]
        self.setattr_argument("INPUT_TTL", EnumerationValue(ttl_params, default="ttl1_counter"))
        self.setattr_device(str(self.INPUT_TTL))  # must typecast or NoneType error when recomputing args
        self.ttl = self.get_device(self.INPUT_TTL)

        self.sum_rising_edges = 0.0
        self.sum_rising_edges_cooling = 0.0

        #self.setattr_result("counts")
        # self.setattr_result("cooling_counts")
        #self.setattr_result("res_err", display_hints={"error_bar_for": self.counts.path})
        self.points = [[0.0] * self.get_dataset("Repetitions"), [0.0] * self.get_dataset("Repetitions")]

        self.gate_end_mu = np.int64(0)  # necessary or type error when assigning new val
        self.mean_rising_edges = 0.0
        # self.mean_rising_edges_cooling=0.0
        self.channel_num = [1]  # Doppler, Det, OP

        self.originalDCElectrodeValues = self.get_dataset("DC.ElectrodeValues")
        self.modDCElectrodeValues = self.get_dataset("DC.ElectrodeValues")  # to be modified
        self.DCElectrodeMapping = self.get_dataset("DC.ElectrodeMapping")
        self.originalEndcapX = self.get_dataset("DC.EndcapX")
        self.originalAllY = self.get_dataset("DC.AllY")
        self.originalAllZ = self.get_dataset("DC.AllZ")

        # setting up other arguments for allZ scan
        #self.setattr_argument("allz_start", NumberValue(default=-0.1, ndecimals=3, min=-0.2, max= 0.1))
        self.setattr_argument("allz_scan",Scannable( default= RangeScan(-0.15,-0.1,5), global_min=-0.2, global_max= 0.2, global_step=0.001))
        self.setattr_argument("CheckThresholding",BooleanValue(default=False))
        #

        # /\ /\ /\ /\ /\ /\ build /\ /\ /\ /\ /\ /\


    @kernel
    def endcapX_func(self, V):
        """
        pushes towards +ve X with endcaps
        """
        self.electrodeUpdate(V, [1, 5, 6, 10], [1, -1, -1, 1])

    @kernel
    def allY_func(self, V):
        """
        pushes towards +ve Y with all electrodes
        """
        self.electrodeUpdate(V, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], [-1] + [-1] * 5 + [1] * 5 + [1])

    @kernel
    def allZ_func(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], [1] + [-1] * 5 + [1] * 5 + [-1])

    @kernel
    def electrodeUpdate(self, V, electrodeList, signList):
        for i in range(len(electrodeList)):
            self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] = self.modDCElectrodeValues[
                                                                                       self.DCElectrodeMapping[
                                                                                           electrodeList[
                                                                                               i]]] + V * (
                                                                                   signList[i])

    # @kernel
    # def pulseDetection(self, det_time):
    #     self.urukul0_ch2.sw.on()  # 935 on
    #     self.urukul0_ch3.sw.on()
    #     delay(det_time)
    #     self.urukul0_ch2.sw.off()  # 935 on
    #     self.urukul0_ch3.sw.off()

    @kernel
    def ON(self, doppler_freq, doppler_amp,doppler_time,
           det_freq, det_amp, det_time,
           OP_freq, OP_amp, OP_time, MW_freq, MW_amp, MW_time,
           # SBCFrequency355_1, SBCAmplitude355_1, SBCFrequency355_2, SBCAmplitude355_2, SBCTime, SBCAmplitude935,
           # wait_time, RamseyCheck, phase1, phase2,
           FrequencyRaman1, AmplitudeRaman1,
           FrequencyRaman2, AmplitudeRaman2,
           Raman_time,
           # RamseyFrequency435, RamseyAmplitude435, PiBy2Time435_1, PiBy2Time435_2,
           newEndcapX, newAllY, newAllZ, piezoR1H, piezoR1V, piezoR2H, piezoR2V, num_repeat, iterScan):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Calculates mean
        rising edges for a given num_repeat to push to counts channel"""
        # self.core.reset()
        # self.core.break_realtime()
        # zotino

        self.zotino0.init()
        delay(2 * ms)
        # updating zotino with all voltage combinations on electrodes.

        for i in range(12):
            self.modDCElectrodeValues[i] = self.originalDCElectrodeValues[i]
        # adding up combinations
        newX = newEndcapX - self.originalEndcapX
        newY = newAllY - self.originalAllY
        newZ = newAllZ - self.originalAllZ
        self.endcapX_func(newX)
        self.allY_func(newY)
        self.allZ_func(newZ)
        # print(self.modDCElectrodeValues)
        # print(newX)
        # print(newEndcapX)
        # z=self.originalDCElectrodeValues-self.modDCElectrodeValues
        # print(self.modDCElectrodeValues)

        AOMdelay = -2.4 * us

        for i in range(12):
            ind = self.DCElectrodeMapping[i]
            self.zotino0.write_dac(self.DCElectrodeMapping[i], self.modDCElectrodeValues[ind])
        # self.zotino0.load()
        # delay(2 * ms)

        # piezo voltage  update
        self.zotino0.write_dac(24, piezoR1H)  # new DAC value for 435, need more for 355 beams
        # self.zotino0.load()
        # delay(2 * ms)
        self.zotino0.write_dac(25, piezoR1V)  # new DAC value for 435, need more for 355 beams
        # self.zotino0.load()
        # delay(2 * ms)
        self.zotino0.write_dac(26, piezoR2H)  # new DAC value for 435, need more for 355 beams
        # self.zotino0.load()
        # delay(2 * ms)
        self.zotino0.write_dac(27, piezoR2V)  # new DAC value for 435, need more for 355 beams
        self.zotino0.load()
        delay(2 * ms)

        if iterScan == 0:
            self.urukul0_cpld.init()
            self.urukul1_cpld.init()
            self.urukul2_cpld.init()
            delay(10 * ms)
            attenuation = 3.0  # use as required

            # self.urukul0_cpld.init() # for now this isn't doing anything
            # self.urukul0_ch0.init()
            # Doppler+935

            self.urukul0_ch1.init()
            self.urukul0_ch1.set_att(0 * dB)
            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch1.sw.off()


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

            # 369 protection
            self.urukul1_ch3.init()
            self.urukul1_ch3.set_att(0 * dB)
            self.urukul1_ch3.set(frequency=200 * MHz, amplitude=0.8, phase_mode=2)
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

            # Camera shutter
            self.ttl4.output()

            # 355 Raman 1 channel2 dual tone application
            self.urukul2_ch1.init()
            self.urukul2_ch1.set_att(0 * dB)
            self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
            self.urukul2_ch1.sw.off()

            self.sum_rising_edges = 0.0
            # self.sum_rising_edges_cooling = 0.0

            # warming up detection and Doppler AOM
            self.urukul0_ch1.sw.on()
            self.urukul0_ch3.sw.on()
            self.urukul1_ch3.sw.on()
            self.urukul1_ch1.sw.on()

            delay(5 * ms)
            self.urukul0_ch1.sw.off()
            self.urukul0_ch3.sw.off()
            self.urukul1_ch3.sw.off()
            self.urukul1_ch1.sw.off()
            #
            #
            # delay(-0.025* ms)

        # exp loop without dma
        # self.urukul1_ch1.init()

        i = 0
        # while(i<num_repeat):
        with self.core_dma.record("seq"):
            # delay(30 * us)  # This delay will exist between repetitions

            # self.ttl4.on() # camera
            self.ttl5.on()
            # if doppler_time> 0.0:

            self.urukul0_ch1.set_att(0 * dB)
            self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            self.urukul0_ch2.sw.on()
            self.urukul1_ch3.sw.on()  # protection on
            delay(doppler_time)
            # self.ttl.gate_rising(doppler_time)
            # self.ttl4.off()
            # delay(wait_time) # solely for camera acquisition . comment otherwise
            # self.urukul0_ch2.set_att(30 * dB)
            self.urukul0_ch1.sw.off()
            self.urukul0_ch2.sw.off()

            # delay(50 * us)  # for debugging

            self.urukul1_ch3.sw.off()  # protection off

            self.ttl5.off()

            # Doppler cooling ramp down
            # self.urukul0_ch2.set_att(0 * dB)
            # self.urukul0_ch1.set_att(0 * dB)
            # self.urukul1_ch1.set_att(0 * dB)
            # STEPS=50
            # for step in range(STEPS):
            #     self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp*(STEPS-step*1.0)/STEPS, phase_mode=2)
            #     self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp*(step*1.0)/STEPS, phase_mode=2)
            #     self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            #     self.urukul0_ch2.sw.on()
            #     # self.urukul1_ch3.sw.on()
            #     delay(doppler_time/STEPS*1.0)
            #     # self.ttl.gate_rising(doppler_time)
            #     # self.urukul0_ch2.set_att(30 * dB)
            #     self.urukul0_ch1.sw.off()
            #     self.urukul0_ch2.sw.off()

            # 2nd doppler cooling stage
            # self.urukul0_ch1.set(frequency=doppler_freq+10*MHz, amplitude=0.8, phase_mode=2)
            # self.urukul0_ch1.sw.on()
            # self.urukul0_ch2.sw.on()
            # delay(0.5*ms)
            # # self.ttl.gate_rising(doppler_time)
            # # self.urukul0_ch2.set_att(30 * dB)
            # self.urukul0_ch1.sw.off()
            # self.urukul0_ch2.sw.off()

            # self.urukul0_ch1.set_att(30 * dB)
            # delay(0.05*ms)
            # y = self.ttl.fetch_count()
            # self.sum_rising_edges_cooling = self.sum_rising_edges_cooling + y
            # delay(0.05*ms)

            # delay(5.5*ms)
            # Pulsed SBC

            # self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
            # self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)

            # self.urukul0_ch1.set(frequency=freq_935, amplitude=SBCAmplitude935, phase_mode=2)
            self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
            self.urukul1_ch1.set_att(0 * dB)
            self.urukul2_ch0.set_att(0 * dB)
            # delay(2.35*ms)

            '''
            if SBCTime > 0.1 * us:
                self.urukul1_ch1.sw.on()
                delay(0.05 * ms)
                #        self.urukul0_ch2.sw.off()
                self.urukul1_ch1.sw.off()

                
                # # Outer 1
                self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                for cyc in range(50):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    delay(SBCTime)
                    # delay(0.006*ms)
                    # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    self.urukul1_ch1.sw.on()
                    delay(0.05 * ms)  # prev 0.03ms need strong OP power
                    self.urukul1_ch1.sw.off()


                # # # Inner 1
                # #
                self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                for cyc in range(50):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    # self.ttl5.on()
                    delay(SBCTime)
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    self.urukul1_ch1.sw.on()
                    delay(0.05 * ms)
                    self.urukul1_ch1.sw.off()
                # # #
                # # # # # Outer1 2nd stage
                self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=SBCAmplitude355_1, phase_mode=2)
                for cyc in range(15):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    delay(0.028 * ms)
                    # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    self.urukul1_ch1.sw.on()
                    delay(0.05 * ms)  # prev 0.03ms need strong OP power
                    self.urukul1_ch1.sw.off()
                # # # #
                # # # # # # #
                # # # # # Inner1 2nd stage
                self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                for cyc in range(5):
                    self.urukul2_ch0.sw.on()
                    self.ttl6.on()
                    # self.ttl5.on()
                    delay(0.025 * ms)
                    self.urukul2_ch0.sw.off()
                    self.ttl6.off()
                    self.urukul1_ch1.sw.on()
                    delay(0.05 * ms)
                    self.urukul1_ch1.sw.off()
            '''

            # OP state prep with 935

            # self.urukul0_ch2.set_att(0 * dB)
            if OP_time > 0.01 * us:
                self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
                #self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
                self.urukul1_ch1.set_att(0 * dB)
                #self.urukul0_ch2.set_att(0 * dB)
                # self.ttl5.on()
                self.urukul1_ch1.sw.on()
                # self.urukul1_ch3.sw.on()
                # self.urukul0_c.sw.on()
                delay(OP_time)
                delay_mu(1)
                self.urukul1_ch1.sw.off()


            # MW interaction

            if MW_time > 0.01 * us:
                self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
                # self.urukul1_ch2.set_att(0 * dB)
                self.urukul1_ch2.set_att(0 * dB)
                self.urukul1_ch2.sw.on()
                # self.ttl5.on()
                delay(MW_time)
                # delay(-0.01*us)
                delay_mu(1)
                # self.urukul1_ch2.set_att(30 * dB)
                self.urukul1_ch2.sw.off()


            # Raman

            if Raman_time > 0.01 * us:
                delay(0.001 * ms)
                # # #pass
                # # Raman 1 ch 1
                self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()  # Raman 1
                self.ttl6.on()  # Raman 2
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                self.urukul2_ch0.sw.off()  # Raman 1
                self.ttl6.off()  # Raman 25*us

                # # # Raman multiple pulses
                # for j in range(int(31.0/0.4*SBCAmplitude935)):
                #     # Raman 1 ch1
                #     # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()# Raman 1
                #     # self.ttl6.on() # Raman 2
                #     # delay(0.3*us) # AOM delay
                #     # delay(Raman_time)
                #     # self.urukul2_ch0.sw.off() # Raman 1
                #     # self.ttl6.off() # Raman 25*us
                #
                #     # # Raman 1 ch2
                #     self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
                #     self.urukul2_ch1.set_att(0 * dB)
                #     self.urukul2_ch1.sw.on()
                #     self.ttl6.on()
                #     delay(0.25 * us)  # AOM delay
                #     delay(Raman_time)
                #     self.ttl6.off()
                #     self.urukul2_ch1.sw.off()

                # # # # Raman 1 ch2
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()
                # self.ttl6.on()
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.ttl6.off()
                # self.urukul2_ch1.sw.off()

                # # Raman 1 ch 1- only for ramsey test pi/2
                # self.urukul2_ch0.set(frequency=192.50309385 * MHz, phase=0.0, amplitude=0.7, phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()  # Raman 1
                # self.ttl6.on()  # Raman 2
                # delay(0.25 * us)  # AOM delay
                # delay(0.00134 * ms)
                # self.urukul2_ch0.sw.off()  # Raman 1
                # self.ttl6.off()  # Raman 25*us

                # # Raman 1: ch1 and ch2 on
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase= 0.0, amplitude=AmplitudeRaman1, phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, phase= 0.0, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()# Raman 1
                # self.urukul2_ch1.sw.on()# Raman 1,ch2
                # self.ttl6.on() # Raman 2
                # delay(0.3*us) # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch0.sw.off() # Raman 1 ch1
                # self.urukul2_ch1.sw.off()  # Raman 1ch2
                # self.ttl6.off() # Raman 25*us


            # Detection w. 935

            if det_time > 0.01 * us:
                self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
                #self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
                #self.urukul0_ch2.sw.on()  # 935 on
                self.urukul0_ch3.sw.on()
                self.ttl5.on()
                self.ttl4.on()  # camera

                self.ttl.gate_rising(det_time)

                self.ttl4.off()  # camera
                self.ttl5.off()
                self.urukul0_ch3.sw.off()
                #self.urukul0_ch2.sw.off()  # 935 on
                # self.urukul0_ch1.sw.off()
                # self.urukul1_ch3.sw.off()

                # delay(50 * us)  # for debugging

            # delay(50 * us)

            # continue Doppler+935

            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
            self.urukul0_ch1.set_att(0 * dB)
            # self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch1.sw.on()
            # self.urukul0_ch2.sw.on()
            # self.urukul1_ch3.sw.on() # 369 protection beam
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
            # x = self.ttl.fetch_count()
            # self.ttl.set_config(count_rising=True, count_falling=False, send_count_event=False, reset_to_zero=True)
            # self.histpoints[i]=x
            delay(10 * us)
            delay(0.5 * ms)
            #delay(5 * ms)
            # delay(0.016*s)

            # i=i+1

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
        seq_handle = self.core_dma.get_handle("seq")
        # repetition loop for DMA
        # self.core.break_realtime()
        for i in range(num_repeat):
            # tempval = 0.0
            self.core_dma.playback_handle(seq_handle)
            self.histpoints[i] = self.ttl.fetch_count()
            # I think can only be called once per gate event or blocks function until counts is available
            # tempval=self.histpoints[i]
            # sum_rising_edges= sum_rising_edges + tempval

    # self.mean_rising_edges = (self.sum_rising_edges)/(num_repeat)
    # self.mean_rising_edges_cooling=(self.sum_rising_edges_cooling)/(num_repeat)


    # \/ \/ \/ \/ \/ \/ prepare \/ \/ \/ \/ \/ \/
    def prepare(self):

        # preparing all previous assignments from dataset

        self.num_repeat = self.get_dataset("Repetitions")
        self.scanHistogramList = np.array([np.zeros(self.get_dataset('Repetitions'), dtype=int)])
        self.PMTThreshold = self.get_dataset("PMTThreshold")
        self.PMTThreshold = self.get_dataset("PMTThreshold")

        self.doppler_freq = self.get_dataset("Doppler.Frequency")
        self.doppler_amp = self.get_dataset("Doppler.Amp")
        self.doppler_time = self.get_dataset("Doppler.Time(ms)") * ms

        self.det_freq = self.get_dataset("Detection.Frequency")
        self.det_amp = self.get_dataset("Detection.Amp")
        self.det_time = self.get_dataset("Detection.Time(ms)") * ms

        self.prepfreqOP = self.get_dataset("OP.Frequency")
        self.prepampOP = self.get_dataset("OP.Amp")
        self.preptimeOP = self.get_dataset("OP.Time(ms)") * ms

        self.FrequencyMW = self.get_dataset("MW.Frequency")
        self.AmplitudeMW = self.get_dataset("MW.Amp")
        self.TimeMW = self.get_dataset("MW.Time(ms)") * ms

        self.Frequency355_Raman1 = self.get_dataset("355_Raman1.Frequency")
        self.Amplitude355_Raman1 = self.get_dataset("355_Raman1.Amp")
        self.piezoR1H = self.get_dataset("355_Raman1.H1")
        self.piezoR1V = self.get_dataset("355_Raman1.V1")

        self.Frequency355_Raman2 = self.get_dataset("355_Raman2.Frequency")
        self.Amplitude355_Raman2 = self.get_dataset("355_Raman2.Amp")
        self.piezoR2H = self.get_dataset("355_Raman2.H2")
        self.piezoR2V = self.get_dataset("355_Raman2.V2")

        self.RamanTime = self.get_dataset("355_Raman1.Time(ms)") * ms

        self.allY = self.get_dataset("Experiment_config.all_y")
        self.allZ = self.get_dataset("Experiment_config.all_z")
        self.endcapX = self.get_dataset("Experiment_config.endcapX")


        self.iter = 0  # keeps track of iteration number so that peripheral initialization only happens once.

        # Plot preparation
        # np.full(self.num_repeat, float(np.nan))
        # avg data point value
        self.set_dataset("allZScan_Counts.Y_vals",[0.0], broadcast=True,
                         archive=True)
        # avg data point value's error
        self.set_dataset("allZScan_Counts.Yerr_vals",[0.0], broadcast=True,
                         archive=True)
        # scan point value
        self.set_dataset("allZScan_Counts.X_vals",[0.0], broadcast=True,
                         archive=True)

        command = "${artiq_applet}plot_xy allZScan_Counts.Y_vals --x allZScan_Counts.X_vals"
                  # --y_err allZScan_Counts.Yerr_vals"
                  # " --xlabel 'AllZ'" \
                  # " --ylabel 'Counts'"
        # " --fit allZScan_Counts.Y_vals"
        self.ccb.issue("create_applet", "allZScan Counts", command)

        #print(self.allz_scan.sequence)
        # scan_points = list(self.allz_scan.get_scan_points())
        # print("Scan points:", scan_points)



    # /\ /\ /\ /\ /\ /\ prepare /\ /\ /\ /\ /\ /\

    # \/ \/ \/ \/ \/ \/ run \/ \/ \/ \/ \/ \/

    def run(self):



        self.krun()
        # self.iter = 0
        # for scan_val in [-0.15,-0.1,-0.05,0.01]:
        #     self.krun(scan_val)   # runs iterations per scan point and collects counts per iteration
        #     # self.mutate_dataset("allZScan_Counts.X_vals", self.iter,scan_val)
        #     # self.mutate_dataset("allZScan_Counts.Y_vals", self.iter, np.mean(self.histpoints))
        #     #self.mutate_dataset("allZScan_Counts.Yerr_vals", self.iter, np.std(histpoints) / np.sqrt(self.num_repeat))
        #     self.host_push_results(scan_val,self.histpoints) # passes modified histogram counts to a function for thresholding and plotting
        #     self.iter=self.iter+1 # keeps track of iteration number so that all the dds are initialized only once
        #     #print(self.iter)
        #     # collect counts per iteration
        #     # mutate dataset.

    @kernel
    def krun(self):
        #if self.iter==0:
        self.core.reset()
        #self.run_scan_point(scan_val)

        self.iter = 0
        scan_arr=self.allz_scan.sequence # learned this from digging into source code in the documentation

        for scan_val in scan_arr:
            self.run_scan_point(scan_val)  # runs iterations per scan point and collects counts per iteration
            # self.mutate_dataset("allZScan_Counts.X_vals", self.iter,scan_val)
            # self.mutate_dataset("allZScan_Counts.Y_vals", self.iter, np.mean(self.histpoints))
            # self.mutate_dataset("allZScan_Counts.Yerr_vals", self.iter, np.std(histpoints) / np.sqrt(self.num_repeat))
            self.host_push_results(scan_val,self.histpoints, self.iter)  # passes modified histogram counts to a function for thresholding and plotting
            self.iter = self.iter + 1  # keeps track of iteration number so that all the dds are initialized only once
            # print(self.iter)
            # collect counts per iteration
            # mutate dataset.



    @kernel
    def run_scan_point(self, scan_val):
        self.ON(
               self.doppler_freq, self.doppler_amp, self.doppler_time, \
               self.det_freq, self.det_amp, self.det_time, \
               self.prepfreqOP, self.prepampOP, self.preptimeOP,
               self.FrequencyMW,self.AmplitudeMW, self.TimeMW, \
               # self.SBCFrequency355_1, self.SBCAmplitude355_1, self.SBCFrequency355_2,
               # self.SBCAmplitude355_2, self.modSBCtime, self.SBCAmplitude935, \
               # self.WaitTime.get(), self.Ramseycheck.get(), self.Phase1.get(), self.Phase2.get(), \
               self.Frequency355_Raman1, self.Amplitude355_Raman1,\
               self.Frequency355_Raman2, self.Amplitude355_Raman2, \
               self.RamanTime, \
               # self.RamseyFrequency435mod, self.RamseyAmplitude435, self.PiBy2Time435_1mod,self.PiBy2Time435_2mod,\
               self.endcapX, self.allY, scan_val, \
               self.piezoR1H,self.piezoR1V, self.piezoR2H, self.piezoR2V, \
               self.num_repeat, self.iter
        )  # calls ON function in krun

        # appending data
        # delay(10 * ms)
        # self.mutate_dataset("PMT_Counts.X_vals", self.num_points - i, time * self.Bin_Size)
        # self.mutate_dataset("PMT_Counts.Y_vals", self.num_points - i, self.count / self.Bin_Size)
        # delay(1 * ms)


    @rpc(flags={"async"})
    def host_push_results(self, scan_val, histpoints, iter):

        if np.sum(self.scanHistogramList) == 0:  # trivial condition to get rid of 0 array that was intialized
            self.scanHistogramList = np.array([histpoints])
        else:
            self.scanHistogramList = np.vstack((self.scanHistogramList, [histpoints]))
        #
        # # Thresholding
        if self.CheckThresholding:

            p, p_err = binom_onesided(np.sum(histpoints >= self.PMTThreshold), self.num_repeat)
            # self.runObj.counts.push(p)
            # self.runObj.res_err.push(p_err)
            # self.mutate_dataset("allZScan_Counts.X_vals", self.iter, scan_val)
            # self.mutate_dataset("allZScan_Counts.Y_vals", self.iter, p)
            #self.mutate_dataset("allZScan_Counts.Yerr_vals", self.iter, p_err)
            #print(scan_val,p)
            if iter == 0:
                self.mutate_dataset("allZScan_Counts.X_vals", 0, scan_val)
                self.mutate_dataset("allZScan_Counts.Y_vals", 0, p)
            else:
                self.append_to_dataset("allZScan_Counts.X_vals", scan_val)
                self.append_to_dataset("allZScan_Counts.Y_vals", p)

        else:

            # self.mutate_dataset("allZScan_Counts.X_vals", self.iter, scan_val)
            # self.mutate_dataset("allZScan_Counts.Y_vals", self.iter, np.mean(histpoints))
            # self.mutate_dataset("allZScan_Counts.Yerr_vals", self.iter, np.std(histpoints) / np.sqrt(self.num_repeat))
            if iter == 0:
                self.mutate_dataset("allZScan_Counts.X_vals", 0, scan_val)
                self.mutate_dataset("allZScan_Counts.Y_vals", 0,np.mean(histpoints))
            else:
                self.append_to_dataset("allZScan_Counts.X_vals", scan_val)
                self.append_to_dataset("allZScan_Counts.Y_vals", np.mean(histpoints))

        # mean_hist=0.0
        # for i in range(self.num_repeat):
        #     mean_hist=mean_hist + histpoints[i]
        # mean_hist=mean_hist/self.num_repeat
        #
        # if iter==0:
        #     self.mutate_dataset("allZScan_Counts.X_vals", 0, scan_val)
        #     self.mutate_dataset("allZScan_Counts.Y_vals", 0, mean_hist)
        # else:
        #     self.append_to_dataset("allZScan_Counts.X_vals", scan_val)
        #     self.append_to_dataset("allZScan_Counts.Y_vals", mean_hist)



    # /\ /\ /\ /\ /\ /\ run /\ /\ /\ /\ /\ /\

    # /\ /\ /\ /\ /\ /\ analyze /\ /\ /\ /\ /\ /\

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

    def analyze(self):

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