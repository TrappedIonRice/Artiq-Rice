from ndscan.experiment import *
from oitg.results import *
import numpy as np
from oitg.errorbars import binom_onesided, binom_twosided
from matplotlib import pyplot as plt
from ndscan.results.arguments import *
from statistics import stdev
from math import *
import time as tm
import oitg.fitting


class runScan(Fragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_device("core_dma")
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
        self.setattr_result("counts")
        # self.setattr_result("cooling_counts")
        self.setattr_result("res_err", display_hints={"error_bar_for": self.counts.path})
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
        self.electrodeUpdate(V, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], [-1] + [-1] * 5 + [1] * 5 + [1])

    @kernel
    def allZ(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], [1] + [-1] * 5 + [1] * 5 + [-1])

    @kernel
    def electrodeUpdate(self, V, electrodeList, signList):
        for i in range(len(electrodeList)):
            self.modDCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] = self.modDCElectrodeValues[
                                                                                       self.DCElectrodeMapping[
                                                                                           electrodeList[i]]] + V * (
                                                                                   signList[i])

    # @kernel
    # def pulseDetection(self, det_time):
    #     self.urukul0_ch2.sw.on()  # 935 on
    #     self.urukul0_ch3.sw.on()
    #     delay(det_time)
    #     self.urukul0_ch2.sw.off()  # 935 on
    #     self.urukul0_ch3.sw.off()

    @kernel
    def ON(self, Frequency435, Amplitude435, Time435, Attenuation_435, choice435, doppler_freq, doppler_amp,
           doppler_time,
           det_freq, det_amp, det_time,
           freq_935, amp_935,
           OP_freq, OP_amp, OP_time, MW_freq, MW_amp, MW_time,
           SBCFrequency355_1, SBCAmplitude355_1, SBCFrequency355_2, SBCAmplitude355_2, SBCTime, SBCAmplitude935,
           ClearoutPower935, ClearoutTime935,
           prepfreq435, preptime,
           wait_time, RamseyCheck, phase1, phase2,
           Frequency355switch, Amplitude355switch, Attenuation355switch,
           FrequencyRaman1, AmplitudeRaman1,
           FrequencyRaman2, AmplitudeRaman2,
           Raman_time,
           RamseyFrequency435, RamseyAmplitude435, PiBy2Time435_1, PiBy2Time435_2,
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
        self.endcapX(newX)
        self.allY(newY)
        self.allZ(newZ)
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

            if SBCTime > 0.1 * us:
                self.urukul1_ch1.sw.on()
                delay(0.05 * ms)
                #        self.urukul0_ch2.sw.off()
                self.urukul1_ch1.sw.off()

                # Outer Tilt
                # self.urukul2_ch0.set(frequency=189.697712*MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(30):
                #     #self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(SBCTime)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     #self.ttl5.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.015 * ms)
                #     self.urukul1_ch1.sw.off()
                # self.urukul2_ch0.set(frequency=189.697712 * MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(5):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.053*ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     # self.ttl5.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.015 * ms)
                #     self.urukul1_ch1.sw.off()
                # # #
                # # # # inner tilt
                # self.urukul2_ch0.set(frequency=189.9969  * MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(30):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(SBCTime)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     # self.ttl5.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.015 * ms)
                #     self.urukul1_ch1.sw.off()
                #
                # self.urukul2_ch0.set(frequency=189.9969 * MHz, amplitude=0.7, phase_mode=2)
                # for cyc in range(5):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.028*ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     # self.ttl5.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.015 * ms)
                #     self.urukul1_ch1.sw.off()

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

                # for cyc in range(10):
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     # delay(SBCTime)
                #     delay(0.008*ms)
                #     #delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #
                #     self.urukul1_ch1.sw.on()
                #     delay(0.05 * ms) # prev 0.03ms need strong OP power
                #     self.urukul1_ch1.sw.off()

                # Continuous SBC

                # self.urukul2_ch0.set(frequency=SBCFrequency355_1, amplitude=0.9, phase_mode=2)
                # self.urukul1_ch1.set(frequency=OP_freq, amplitude=SBCAmplitude355_1, phase_mode=2)
                # self.urukul2_ch0.sw.on()
                # self.ttl6.on()
                # self.urukul1_ch1.sw.on()
                # delay(SBCTime)
                # # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                # self.urukul2_ch0.sw.off()
                # self.ttl6.off()
                # self.urukul1_ch1.sw.off()

                # Inner 2
                # self.urukul2_ch0.set(frequency=189.3368901*MHz, amplitude=SBCAmplitude355_2, phase_mode=2)
                # for cyc in range(30):
                #     # self.ttl5.on()
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.2* ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.04 * ms)
                #     self.urukul1_ch1.sw.off()
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

                # CSBC
                # self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=0.7, phase_mode=2)
                # self.urukul1_ch1.set(frequency=OP_freq, amplitude=SBCAmplitude355_2, phase_mode=2)
                # self.urukul2_ch0.sw.on()
                # self.ttl6.on()
                # self.urukul1_ch1.sw.on()
                # delay(SBCTime)
                # # delay(0.003*ms*np.sqrt(80/(80-cyc*1.0)))
                # self.urukul2_ch0.sw.off()
                # self.ttl6.off()
                # self.urukul1_ch1.sw.off()

                # Axial
                # self.urukul2_ch0.set(frequency=SBCFrequency355_2, amplitude=SBCAmplitude355_2, phase_mode=2)
                # for cyc in range(100):
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     # self.ttl5.on()
                #     delay(SBCTime)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #     self.urukul1_ch1.sw.on()
                #     delay(0.1 * ms)
                #     self.urukul1_ch1.sw.off()

                # CSBC Raman
                # self.urukul1_ch1.set(frequency=OP_freq, amplitude=SBCAmplitude935, phase_mode=2)
                # self.urukul2_ch0.sw.on()
                # self.ttl6.on()
                # self.urukul1_ch1.sw.on()
                # delay(SBCTime)
                # self.urukul2_ch0.sw.off()
                # self.ttl6.off()
                # self.urukul1_ch1.sw.off()

            # OP state prep with 935

            # self.urukul0_ch2.set_att(0 * dB)
            if OP_time > 0.01 * us:
                self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
                self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
                self.urukul1_ch1.set_att(0 * dB)
                self.urukul0_ch2.set_att(0 * dB)
                # self.ttl5.on()
                self.urukul1_ch1.sw.on()
                # self.urukul1_ch3.sw.on()
                # self.urukul0_c.sw.on()
                delay(OP_time)
                delay_mu(1)
                self.urukul1_ch1.sw.off()

                # delay(50 * us)  # for debugging

                # self.urukul1_ch3.sw.off()
                # self.urukul0_ch2.sw.off()
                # self.ttl5.off()
                # self.urukul0_ch2.set_att(30 * dB)
                # delay(5 * us)
                # delay(100*us) # DO Not remove or else OP scan will not execute properly.
                # self.urukul1_ch1.sw.on()
                # self.urukul0_ch2.sw.on()

            # self.urukul1_ch1.sw.off()

            # Using channel 0 of urukul 0
            # Ramsey first pi 435 pulse

            # delay(-1*us) # important for syncing. Must be before setting up the DDS config or else there is some gradual ampltiude ramp of 435 DDS

            if RamseyCheck == True:
                # delay(1*ms)
                # # MW ramsey
                # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
                # #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.sw.on()
                # delay(PiBy2Time435_1)
                # delay_mu(1)
                # # self.urukul1_ch2.set_att(30 * dB)
                # self.urukul1_ch2.sw.off()
                # #delay(0.05*ms)
                #
                # # # # Raman 1 ch 1-RSB
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on()  # Raman 1
                # # self.ttl6.on()  # Raman 2
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()  # Raman 1
                # # self.ttl6.off()  # Raman 2
                #
                # # Raman pulse with MW
                # # # # Raman 1 ch 1
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on()
                # # self.ttl6.on()
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()
                # # self.ttl6.off()
                #
                # # # wait time
                # # delay(wait_time)
                # # delay_mu(1)
                #
                #
                # # wait time with 1 echo pi
                #
                # # for n in range(4):
                # #     delay(wait_time/(2*4))
                # #     delay_mu(1)
                # #     self.urukul1_ch2.sw.on()
                # #     delay(PiBy2Time435_1*2)
                # #     delay_mu(1)
                # #     # self.urukul1_ch2.set_att(30 * dB)
                # #     self.urukul1_ch2.sw.off()
                # #     delay(wait_time/(2*4))
                # #     delay_mu(1)
                #
                #
                #
                # # wait time with 355 on
                # #
                #
                # #self.urukul2_ch0.sw.on() # Raman 1
                # #self.ttl6.on() # Raman 2
                # delay(wait_time)
                # delay_mu(1)
                # #self.urukul2_ch0.sw.off() # Raman 1
                # #self.ttl6.off() # Raman 2
                # #
                # #
                # #
                # #
                #
                # # Raman pulse with MW
                # # # Raman 1 ch 1
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on()
                # # self.ttl6.on()
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()
                # # self.ttl6.off()
                #
                # # # # Raman 1 ch 1-RSB
                # # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # # self.urukul2_ch0.set_att(0 * dB)
                # # self.urukul2_ch0.sw.on()  # Raman 1
                # # self.ttl6.on()  # Raman 2
                # # delay(0.25 * us)  # AOM delay
                # # delay(Raman_time)
                # # self.urukul2_ch0.sw.off()  # Raman 1
                # # self.ttl6.off()  # Raman 2
                #
                # # Ramsey second pi 435 pulse
                #
                # self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
                # #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                # # self.urukul1_ch2.set_att(0 * dB)
                # self.urukul1_ch2.sw.on()
                # self.urukul1_ch2.set_att(0 * dB)
                # delay(PiBy2Time435_2)
                # delay_mu(1)
                # # self.urukul1_ch2.set_att(30 * dB)
                # self.urukul1_ch2.sw.off()

                # delay(0.05*ms)

                # Raman Ramsey

                # # Ramsey first pi/2
                self.urukul1_ch2.set_att(0 * dB)
                self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=0.0, amplitude=RamseyAmplitude435,
                                     phase_mode=2)
                # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()
                self.ttl6.on()
                delay(0.3 * us)  # AOM delay
                delay(PiBy2Time435_1)
                # delay_mu(1)
                # self.urukul1_ch2.set_att(30 * dB)
                self.urukul2_ch0.sw.off()
                self.ttl6.off()
                # delay(0.05*ms)

                # # delay(10*us)
                # # # Raman 1 ch 1 -RSB
                self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1, phase_mode=2)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()  # Raman 1
                self.ttl6.on()  # Raman 2
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                self.urukul2_ch0.sw.off()  # Raman 1
                self.ttl6.off()  # Raman 2

                # # Raman 1 ch 2-RSB
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, phase= 0.0, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()  # Raman 1
                # self.ttl6.on()  # Raman 2
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch1.sw.off()  # Raman 1
                # self.ttl6.off()  # Raman 2

                # wait time
                delay(wait_time)
                delay_mu(1)

                # Dynamical decoupling
                # for n in range(2):
                #
                #     # wait fraction
                #     delay(wait_time/(2.0*(2)))
                #     delay_mu(1)
                #
                #
                #     # pure RSB decoupling
                #     # self.urukul1_ch2.set_att(0 * dB)
                #     # # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=0.0, amplitude=AmplitudeRaman1,
                #     # #                      phase_mode=2)
                #     # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=(0.0 + np.pi / 2.0 * (n % 2)), amplitude=AmplitudeRaman1,phase_mode=2)
                #     # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(Raman_time*2.0)
                #     # # delay_mu(1)
                #     # # self.urukul1_ch2.set_att(30 * dB)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #
                #     # carrier and rsb decoupling
                #
                #     # #RSB pi
                #     # self.urukul1_ch2.set_att(0 * dB)
                #     # self.urukul2_ch0.set(frequency=SBCFrequency355_1, phase=0.0,
                #     #                      amplitude=0.7, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(0.035*ms)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #     #
                #     # # carrier pi
                #     # self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=(0.0 + np.pi / 2.0 * (n % 2)),
                #     #                      amplitude=RamseyAmplitude435, phase_mode=2)
                #     # # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(PiBy2Time435_1*2.0)
                #     # # delay_mu(1)
                #     # # self.urukul1_ch2.set_att(30 * dB)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #     #
                #     # # RSB pi
                #     # self.urukul1_ch2.set_att(0 * dB)
                #     # self.urukul2_ch0.set(frequency=SBCFrequency355_1, phase=np.pi,
                #     #                      amplitude=0.7, phase_mode=2)
                #     # self.urukul2_ch0.set_att(0 * dB)
                #     # self.urukul2_ch0.sw.on()
                #     # self.ttl6.on()
                #     # delay(0.3 * us)  # AOM delay
                #     # delay(0.035*ms)
                #     # self.urukul2_ch0.sw.off()
                #     # self.ttl6.off()
                #
                #     # carrier and rsb with bsb decoupling
                #
                #     # carrier pi
                #     self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=(0.0 + np.pi / 2.0 * (n % 2)),
                #                          amplitude=RamseyAmplitude435, phase_mode=2)
                #     # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                #     self.urukul2_ch0.set_att(0 * dB)
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.3 * us)  # AOM delay
                #     delay(PiBy2Time435_1 * 2.0)
                #     # delay_mu(1)
                #     # self.urukul1_ch2.set_att(30 * dB)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #
                #     # BSB pi- ch2
                #     self.urukul2_ch1.set(frequency=195.43771*MHz, phase=0.0,
                #                          amplitude=0.4017, phase_mode=2)
                #     self.urukul2_ch1.set_att(0 * dB)
                #     self.urukul2_ch1.sw.on()
                #     self.ttl6.on()
                #     delay(0.3 * us)  # AOM delay
                #     delay(0.059755 * ms)
                #     self.urukul2_ch1.sw.off()
                #     self.ttl6.off()
                #
                #
                #     # RSB pi -ch1
                #     self.urukul2_ch0.set(frequency=189.626452*MHz, phase=0.0,
                #                          amplitude=0.35, phase_mode=2)
                #     self.urukul2_ch0.set_att(0 * dB)
                #     self.urukul2_ch0.sw.on()
                #     self.ttl6.on()
                #     delay(0.3 * us)  # AOM delay
                #     delay(0.064 * ms)
                #     self.urukul2_ch0.sw.off()
                #     self.ttl6.off()
                #
                #
                #     # wait fraction
                #     delay(wait_time/(2.0*(2)))
                #     delay_mu(1)

                # # wait time with 355 on
                # #
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, phase= 0.0,  amplitude=AmplitudeRaman1, phase_mode=2) #RSB
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, phase= 0.0, amplitude=AmplitudeRaman2, phase_mode=2) #BSB
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch0.sw.on() # Raman 1 ch1
                # self.urukul2_ch1.sw.on()  # Raman 1 ch2
                # self.ttl6.on() # Raman 2
                # delay(wait_time)
                # delay_mu(1)
                # self.ttl6.off() # Raman 2
                # self.urukul2_ch0.sw.off() # Raman 1 ch1
                # self.urukul2_ch1.sw.off() # Raman 1 ch2

                # # # # # Raman 1 ch 1-RSB
                self.urukul2_ch0.set(frequency=FrequencyRaman1, phase=(SBCAmplitude935 - 0.4) * np.pi / 0.8 * 0.0,
                                     amplitude=AmplitudeRaman1, phase_mode=2)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()  # Raman 1
                self.ttl6.on()  # Raman 2
                delay(0.3 * us)  # AOM delay
                delay(Raman_time)
                self.urukul2_ch0.sw.off()  # Raman 1
                self.ttl6.off()  # Raman 2

                # # Raman 1 ch 2-RSB
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, phase=np.pi-(SBCAmplitude935-0.4)*np.pi/0.8, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()  # Raman 1
                # self.ttl6.on()  # Raman 2
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch1.sw.off()  # Raman 1
                # self.ttl6.off()  # Raman 2

                # # # Ramsey second pi/2
                # # # delay(10 * us)
                self.urukul2_ch0.set(frequency=RamseyFrequency435, phase=(SBCAmplitude935 - 0.4) * np.pi / 0.8,
                                     amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
                # self.urukul1_ch2.set_att(0 * dB)
                self.urukul2_ch0.set_att(0 * dB)
                self.urukul2_ch0.sw.on()
                self.ttl6.on()
                delay(0.3 * us)  # AOM delay
                delay(PiBy2Time435_2)
                # delay_mu(1)
                self.urukul2_ch0.sw.off()
                self.ttl6.off()

            # 435 interaction

            # self.urukul0_ch2.sw.on() # 935 repumper
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
            # self.urukul0_ch2.sw.off() # 935 repumper

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

            # self.ttl5.on()
            # delay(wait_time)
            # self.ttl5.off()

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

                # delay(50 * us)  # for debugging

                # self.ttl5.off()
            # 355 Turning on global switch
            # self.urukul1_ch3.set_att(0 * dB)
            # self.urukul1_ch3.sw.on()
            # delay_mu(1)
            # delay(10*us) # essential or else underflow
            # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
            # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
            # delay(0.1 * ms)
            # self.ttl5.on()

            # Raman 1 + 2
            # delay(1*ms)

            # self.urukul2_ch0.set(frequency=192.534*MHz, amplitude=AmplitudeRaman1, phase_mode=2)
            # # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
            # self.urukul2_ch0.set_att(0 * dB)
            # self.ttl5.on()
            # self.urukul1_ch3.sw.on()
            # self.urukul2_ch0.sw.on()
            # self.ttl6.on()
            # # self.urukul2_ch1.sw.on()
            # delay(0.25 * us)  # AOM delay
            # delay(0.9*us)#pi time
            # # delay_mu(1)
            # # self.urukul2_ch0.set_att(30 * dB)
            # self.urukul2_ch0.sw.off()
            # self.ttl6.off()
            # self.ttl5.off()
            # self.urukul1_ch3.sw.off()
            # delay(4*ms)

            # delay(5*ms)

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

                # # Raman 1 ch 1
                # self.urukul2_ch0.set(frequency=192.50309385*MHz, phase=(SBCAmplitude935-0.4)*np.pi/0.8, amplitude= 0.7,  phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul2_ch0.sw.on()# Raman 1
                # self.ttl6.on() # Raman 2
                # delay(0.25*us) # AOM delay
                # delay(0.00134*ms)
                # self.urukul2_ch0.sw.off() # Raman 1
                # self.ttl6.off() # Raman 25*us

                # # # # Raman 1 ch2
                # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch1.set_att(0 * dB)
                # self.urukul2_ch1.sw.on()
                # self.ttl6.on()
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.ttl6.off()
                # self.urukul2_ch1.sw.off()

                # Co-Propagating raman case from Raman1's side
                #
                # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
                # self.urukul1_ch3.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
                # self.urukul2_ch0.set_att(0 * dB)
                # self.urukul1_ch3.set_att(0 * dB)
                # self.urukul1_ch3.sw.on()
                # self.urukul2_ch0.sw.on()
                # delay(0.25 * us)  # AOM delay
                # delay(Raman_time)
                # self.urukul2_ch0.sw.off()
                # self.urukul1_ch3.sw.off()
                #

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

            if det_time > 0.01 * us:
                self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
                # delay(AOMdelay)
                self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
                # delay(AOMdelay)

                # self.urukul1_ch1.set_att(30 * dB)
                # self.urukul1_ch1.set(frequency=OP_freq, amplitude=det_amp, phase_mode=2)
                #
                # self.urukul1_ch1.sw.off()

                # a little bit of Doppler for pumping out dark state
                # self.urukul0_ch1.set(frequency=doppler_freq, amplitude=0.8, phase_mode=2)
                # self.urukul0_ch1.sw.on()

                # self.urukul0_ch3.set_att(0 * dB)

                #
                # self.urukul1_ch3.sw.on()
                self.urukul0_ch2.sw.on()  # 935 on
                self.urukul0_ch3.sw.on()
                self.ttl5.on()
                self.ttl4.on()  # camera

                # for simple detection using edge counter
                # delay(50*us)
                # with parallel:
                # delay(-5*us)
                self.ttl.gate_rising(det_time)
                # self.pulseDetection(det_time)
                # delay_mu(1)

                # without edge counter
                # detcounts_time = self.ttl.gate_rising(detTime)

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

                self.ttl4.off()  # camera
                self.ttl5.off()
                self.urukul0_ch3.sw.off()
                self.urukul0_ch2.sw.off()  # 935 on
                # self.urukul0_ch1.sw.off()
                # self.urukul1_ch3.sw.off()

                # delay(50 * us)  # for debugging

            # delay(50 * us)

            # continue Doppler+935

            self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
            self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
            self.urukul0_ch1.set_att(0 * dB)
            self.urukul0_ch2.set_att(0 * dB)
            self.urukul0_ch1.sw.on()
            self.urukul0_ch2.sw.on()
            self.urukul1_ch3.sw.on()
            # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)

            # delay(30 * us)
            # self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
            #  self.ttl5.off()
            # extra computations always left at the end of the scan, or else RTIO underflow occurs for Kasli. Problem doesn't persist with Kasli SOC.

            # self.sum_rising_edges = self.sum_rising_edges + x
            # delay(3*ms)
            # delay_mu(1)

            # x = self.ttl.fetch_count()
            # self.ttl.set_config(count_rising=True, count_falling=False, send_count_event=False, reset_to_zero=True)
            # self.histpoints[i]=x
            delay(10 * us)
            delay(0.5 * ms)

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
            self.histpoints[
                i] = self.ttl.fetch_count()  # I think can only be called once per gate event or blocks function until counts is available
            # tempval=self.histpoints[i]
            # sum_rising_edges= sum_rising_edges + tempval

    # self.mean_rising_edges = (self.sum_rising_edges)/(num_repeat)
    # self.mean_rising_edges_cooling=(self.sum_rising_edges_cooling)/(num_repeat)


class executeScan(ExpFragment):
    """Optimizer for Scan AOM355 DC,DMA"""

    def build_fragment(self):
        # self.setattr_param("channel", IntParam, "CHOOSE URUKUL CHANNEL (0-3)", default=0)
        self.setattr_device("core")
        self.setattr_device("core_dma")
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
        self.setattr_device("urukul1_ch3")  # 355 switch

        self.setattr_device("urukul2_cpld")  # Necessary for clock sync
        self.setattr_device("urukul2_ch0")  # Raman 1
        self.setattr_device("urukul2_ch1")  # Raman 2
        self.setattr_device("ttl5")
        self.setattr_device("ttl6")


        # setting defaults

        self.default_SBCcheck=bool(self.get_dataset("SBC.Check"))
        self.default_SBCFrequency355_1=self.get_dataset("SBC.tone1.Frequency")
        self.default_SBCAmplitude355_1 = self.get_dataset("SBC.tone1.Amplitude")
        self.default_SBCFrequency355_2 = self.get_dataset("SBC.tone2.Frequency")
        self.default_SBCAmplitude355_2 = self.get_dataset("SBC.tone2.Amplitude")
        self.default_SBCtime=self.get_dataset("SBC.tone1.Time(ms)")*ms
        self.default_prepfreqOP= self.get_dataset("OP.Frequency")
        self.default_prepampOP = self.get_dataset("OP.Amp")
        self.default_preptimeOP= self.get_dataset("OP.Time(ms)")*ms
        self.default_MWFrequency = self.get_dataset("MW.Frequency")
        self.default_MWAmp= self.get_dataset("MW.Amp")
        self.default_MWTime = self.get_dataset("MW.Time(ms)")*ms
        self.default_Raman1_freq=self.get_dataset("355_Raman1.Frequency")
        self.default_Raman1_amp = self.get_dataset("355_Raman1.Amp")
        self.default_Raman_time = self.get_dataset("355_Raman1.Time(ms)")*ms
        self.default_Raman1_ch2_freq = self.get_dataset("355_Raman1_ch2.Frequency")
        self.default_Raman1_ch2_amp = self.get_dataset("355_Raman1_ch2.Amp")
        self.default_ThresholdCheck=bool(self.get_dataset("PMTCheckThreshold"))
        self.default_detectionTime=self.get_dataset("Detection.Time(ms)")*ms
        self.default_endcapX=self.get_dataset("Experiment_config.endcapX")
        self.default_allY=self.get_dataset("Experiment_config.all_y")
        self.default_allZ=self.get_dataset("Experiment_config.all_z")
        self.default_PiezoR1H=self.get_dataset("355_Raman1.H1")
        self.default_PiezoR1V =self.get_dataset("355_Raman1.V1")
        self.default_PiezoR2H =self.get_dataset("355_Raman2.H2")
        self.default_PiezoR2V =self.get_dataset("355_Raman2.V2")




        # setting up parameters.
        self.setattr_param("SBCcheck", BoolParam, "SBC : ", default=self.default_SBCcheck)
        self.setattr_param("SBCFrequency355_1", FloatParam, "SBC Frequency 355_1", unit="MHz", default=self.default_SBCFrequency355_1)
        self.setattr_param("SBCAmplitude355_1", FloatParam, "SBC Amplitude 355_1", unit="", default=self.default_SBCAmplitude355_1,
                           min=0.00,
                           max=0.8)

        self.setattr_param("SBCFrequency355_2", FloatParam, "SBC Frequency 355_2", unit="MHz", default=self.default_SBCFrequency355_2)
        self.setattr_param("SBCAmplitude355_2", FloatParam, "SBC Amplitude 355_2 ", unit="", default=self.default_SBCAmplitude355_2, min=0.00,
                           max=0.8)

        self.setattr_param("SBCTime", FloatParam, "SBC Time ", unit="ms", default=self.default_SBCtime, min=0.00001 * ms)
        self.setattr_param("SBCAmplitude935", FloatParam, "SBC Amplitude 935 ", unit="", default=0.00500, min=0.0,
                           max=0.8)

        self.setattr_param("ClearoutPower935", FloatParam, "Clearout Power 935", unit="", default=0.01, max=0.8)
        self.setattr_param("ClearoutTime935", FloatParam, "Clearout Time 935", unit="ms", min=0.00001 * ms,
                           default=0.05 * ms)

        self.setattr_param("StatePrepOP", BoolParam, "State Preparation with OP: ", default=True)
        self.setattr_param("prepfreqOP", FloatParam, "Prep OP frequency", unit="MHz", default=self.default_prepfreqOP)
        self.setattr_param("prepampOP", FloatParam, "Prep OP amplitude", unit="", default=self.default_prepampOP, max=0.8)
        self.setattr_param("preptimeOP", FloatParam, "Prep OP time", unit="ms", min=0.00001 * ms, default=self.default_preptimeOP)

        self.setattr_param("StatePrep", BoolParam, "State Preparation: ", default=False)
        self.setattr_param("prepfreq435", FloatParam, "Prep 435 frequency", unit="MHz", default=234.1743 * MHz)
        self.setattr_param("preptime", FloatParam, "Prep time", unit="ms", default=2 * ms, min=0.00001 * ms)

        self.setattr_param("choice435", IntParam, "Choose 435 channel (1,2): ", default=1, min=1, max=2)
        self.setattr_param("Ramseycheck", BoolParam, "Ramsey on/off: ", default=False)
        self.setattr_param("WaitTime", FloatParam, "Wait Time ", unit="ms", default=0.00001 * ms, min=0.00001 * ms)

        self.setattr_param("Phase1", FloatParam, "Phase 1:", default=0.0, min=-2 * np.pi, max=2 * np.pi)
        self.setattr_param("Phase2", FloatParam, "Phase 2:", default=0.0, min=-2 * np.pi, max=2 * np.pi)

        self.setattr_param("FrequencyMW", FloatParam, "Frequency MW", unit="MHz", default=self.default_MWFrequency)
        self.setattr_param("AmplitudeMW", FloatParam, "Amplitude MW ", unit="", default=self.default_MWAmp, min=0.00, max=0.8)
        self.setattr_param("TimeMW", FloatParam, "Time MW ", unit="ms", default=self.default_MWTime, min=0.00001 * ms)

        self.setattr_param("Frequency435", FloatParam, "Frequency 435", unit="MHz",
                           default=243.2854 * MHz)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Amplitude435", FloatParam, "Amplitude 435 ", unit="", default=0.000, min=0.00,
                           max=0.8)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Time435", FloatParam, "Time 435 ", unit="ms", default=0.01 * ms, min=0.00001 * ms)

        self.setattr_param("Frequency355_Raman1", FloatParam, "Frequency 355_Raman1", unit="MHz",
                           default=self.default_Raman1_freq)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Amplitude355_Raman1", FloatParam, "Amplitude 355_Raman1 ", unit="", default=self.default_Raman1_amp, min=0.00,
                           max=0.8)

        self.setattr_param("Frequency355_Raman2", FloatParam, "Frequency 355_Raman2", unit="MHz",
                           default=self.default_Raman1_ch2_freq)  # changed min to 1 to avoid fit issue when 0
        self.setattr_param("Amplitude355_Raman2", FloatParam, "Amplitude 355_Raman2 ", unit="", default=self.default_Raman1_ch2_amp, min=0.00,
                           max=0.8)

        self.setattr_param("RamanTime", FloatParam, "Raman time 355", unit="ms", default=self.default_Raman_time, min=0.00001 * ms)

        self.setattr_param("CheckThresholding", BoolParam, "Thresholding On/Off ", default=self.default_ThresholdCheck)
        self.setattr_param("DetTime369", FloatParam, "Detection Time ", unit="ms", default=self.default_detectionTime, min=0.00001 * ms)

        self.setattr_param("endcapX", FloatParam, "EndcapX ", unit="", default=self.default_endcapX)
        self.setattr_param("allY", FloatParam, "AllY ", unit="", default=self.default_allY)
        self.setattr_param("allZ", FloatParam, "AllZ ", unit="", default=self.default_allZ)

        self.setattr_param("piezoR1H", FloatParam, "Raman 1 Piezo Horizontal ", unit="", default=self.default_PiezoR1H, min=0.0,
                           max=10.0)  # from attocube
        self.setattr_param("piezoR1V", FloatParam, "Raman 1 Piezo Vertical ", unit="", default=self.default_PiezoR1V, min=0.0,
                           max=10.0)  # from thorlabs
        self.setattr_param("piezoR2H", FloatParam, "Raman 2 Piezo Horizontal ", unit="", default=self.default_PiezoR2H, min=0.0,
                           max=10.0)  # from thorlabs
        self.setattr_param("piezoR2V", FloatParam, "Raman 2 Piezo Vertical ", unit="", default=self.default_PiezoR2V, min=0.0,
                           max=10.0)  # from thorlabs

        self.setattr_fragment("runObj",
                              runScan)  # Assigns runScan fragment and its attributes/functions to this fragment

        self.setattr_device("scheduler")

        # self.setattr_fragment("histplot",histPlot,len(self.run.points)) # creates histogram plot, maybe called too early
        # fit_params = ["TIME", "FREQUENCY", "AMPLITUDE"]
        # self.setattr_argument("histogram",BooleanValue(default=False) ,tooltip="Save histogram data also")
        # self.setattr_argument("threshold_enable", BooleanValue(default=False),group="THRESHOLD", tooltip="Single ion threshhold")
        # self.setattr_argument("threshold_value",NumberValue(min=0.0, max=100, ndecimals=3, default=0), group="THRESHOLD", tooltip="Single ion threshhold")
        # self.setattr_argument("SET_FIT_PARAM", EnumerationValue(fit_params, default="TIME"), group = "SET FIT")
        # fits = ["cos", "decaying_sinusoid", "detuned_square_pulse", "exponential_decay",
        #        "gaussian", "line", "lorentzian", "rabi_flop", "sinusoid", "v_function", "None"]
        # self.setattr_argument("CHOOSE_FIT", EnumerationValue(fits, default="None"), group = "SET FIT")

        # self.setattr_argument("x0", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("y0", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("y_inf", NumberValue(default=0, ndecimals=6), group = "SET FIT")
        # self.setattr_argument("tau", NumberValue(default=0*us, unit = "us", ndecimals=6), group = "SET FIT")

        # self.dict_obj = {"TIME" : self.waittime, "AMPLITUDE" : self.recoolamp, "FREQUENCY" : self.recoolfreq}

    #       self.analyses = AnnotationContext()
    # self.setattr_result("test")

    def host_setup(self):  # reserved key word
        self.doppler_freq = self.get_dataset("Doppler.Frequency")
        self.doppler_amp = self.get_dataset("Doppler.Amp")
        self.num_repeat = self.get_dataset("Repetitions")
        self.doppler_time = self.get_dataset("Doppler.Time(ms)") * ms

        self.scanHistogramList = np.array([np.zeros(self.get_dataset('Repetitions'), dtype=int)])
        self.PMTThreshold = self.get_dataset("PMTThreshold")

        self.det_freq = self.get_dataset("Detection.Frequency")
        self.det_amp = self.get_dataset("Detection.Amp")
        self.det_time = self.get_dataset("Detection.Time(ms)") * ms

        self.freq_935 = self.get_dataset("935.Frequency")
        self.amp_935 = self.get_dataset("935.Amp")

        self.attenuation_435_1 = self.get_dataset("435_1.Attenuation")

        self.frequency355switch = self.get_dataset("355_switch.Frequency")
        self.amplitude355switch = self.get_dataset("355_switch.Amp")
        self.attenuation355switch = self.get_dataset("355_switch.Attenuation")

        self.RamseyFrequency435mod = self.get_dataset("Ramsey.Frequency435") + self.get_dataset("Ramsey.Detuning435")
        self.RamseyAmplitude435 = self.get_dataset("Ramsey.Amplitude435")
        self.PiBy2Time435_1 = self.get_dataset("Ramsey.PiBy2Time435_1(ms)") * ms
        self.PiBy2Time435_2 = self.get_dataset("Ramsey.PiBy2Time435_2(ms)") * ms

        self.modSBCtime = 0.00001 * ms * 0
        self.modpreptime = 0.00001 * ms * 0
        #     self.modpreptimeOP=0.00001*ms*0
        self.PiBy2Time435_1mod = 0.00001 * ms * 0
        self.PiBy2Time435_2mod = 0.00001 * ms * 0
        self.iter = 0  # keeps track of iteration number so that peripheral initialization only happens once.

        plt.figure()
        # print(self.scheduler.expid['arguments']['ndscan_params'])

        # self.parameters

    # print(self.Time435.get())
    # print(self.DetTime369.get())

    # self.cooling_time = self.get_dataset("935.Time(ms)") * ms
    # if (self.SBCcheck.get() == True):
    #     self.modSBCtime = self.SBCTime.get()
    #
    # if (self.StatePrep.get() == True):
    #     self.modpreptime = self.preptime.get()
    #
    # if (self.StatePrepOP.get() == True):
    #     self.modpreptimeOP = self.preptimeOP.get()
    #
    # if (self.Ramseycheck.get() == True):
    #     self.PiBy2Time435_1mod = self.PiBy2Time435_1
    #     self.PiBy2Time435_2mod = self.PiBy2Time435_2

    # @kernel
    # def run(self) -> None:
    #     self.core.break_realtime()
    #     #delay(-1*ms)
    # self.core.break_realtime()
    # delay(10*ms)

    @kernel
    def run_once(self):

        """Retrieves constant values from dataset, then runs experiment"""
        # self.runObj.core_init()
        # self.run_cone
        # if self.iter<10:
        #     self.core.break_realtime()
        # self.iter+=1
        self.core.reset()
        if (self.SBCcheck.get() == True):
            self.modSBCtime = self.SBCTime.get()

        if (self.StatePrep.get() == True):
            self.modpreptime = self.preptime.get()

        # if (self.StatePrepOP.get() == True):
        #     self.modpreptimeOP = self.preptimeOP.get()

        if (self.Ramseycheck.get() == True):
            self.PiBy2Time435_1mod = self.PiBy2Time435_1
            self.PiBy2Time435_2mod = self.PiBy2Time435_2

        self.runObj.ON(self.Frequency435.get(), self.Amplitude435.get(), self.Time435.get(), self.attenuation_435_1,
                       self.choice435.get(), \
                       self.doppler_freq, self.doppler_amp, self.doppler_time, \
                       self.det_freq, self.det_amp, self.DetTime369.get(), \
                       self.freq_935, self.amp_935, \
                       self.prepfreqOP.get(), self.prepampOP.get(), self.preptimeOP.get(), self.FrequencyMW.get(),
                       self.AmplitudeMW.get(), self.TimeMW.get(), \
                       self.SBCFrequency355_1.get(), self.SBCAmplitude355_1.get(), self.SBCFrequency355_2.get(),
                       self.SBCAmplitude355_2.get(), self.modSBCtime, self.SBCAmplitude935.get(), \
                       self.ClearoutPower935.get(), self.ClearoutTime935.get(), \
                       self.prepfreq435.get(), self.modpreptime, \
                       self.WaitTime.get(), self.Ramseycheck.get(), self.Phase1.get(), self.Phase2.get(), \
                       self.frequency355switch, self.amplitude355switch, self.attenuation355switch, \
                       self.Frequency355_Raman1.get(), self.Amplitude355_Raman1.get(), self.Frequency355_Raman2.get(),
                       self.Amplitude355_Raman2.get(), \
                       self.RamanTime.get(), \
                       self.RamseyFrequency435mod, self.RamseyAmplitude435, self.PiBy2Time435_1mod,
                       self.PiBy2Time435_2mod, \
                       self.endcapX.get(), self.allY.get(), self.allZ.get(), self.piezoR1H.get(), self.piezoR1V.get(),
                       self.piezoR2H.get(), self.piezoR2V.get(), \
                       self.num_repeat, self.iter)  # calls ON function in runScan fragment

        self.iter = self.iter + 1
        # self.runObj.counts.push(np.log(self.run.mean_rising_edges))

        self.host_push_results(self.runObj.points, self.runObj.histpoints)

        # print(self.runObj.histpoints)
        # print(self.analyses.describe_online_analyses())
        # self.test.push(np.sin(9586958.6))

    @rpc(flags={"async"})
    def host_push_results(self, points, histpoints):

        # self.run.counts.push(mean_rising_edges/self.det_time)
        # self.run.res_err.push(mean_rising_edges/(self.det_time*sqrt(self.num_repeat)))
        # T=self.DetTime369.get()
        # storing histograms
        if np.sum(self.scanHistogramList) == 0:  # trivial condition to get rid of 0 array that was intialized
            self.scanHistogramList = np.array([histpoints])
        else:
            self.scanHistogramList = np.vstack((self.scanHistogramList, [histpoints]))

        # Thresholding
        if self.CheckThresholding.get():

            p, p_err = binom_onesided(np.sum(histpoints >= self.PMTThreshold), self.num_repeat)
            self.runObj.counts.push(p)
            self.runObj.res_err.push(p_err)
        else:
            self.runObj.counts.push(np.mean(histpoints))
            self.runObj.res_err.push(np.std(histpoints) / np.sqrt(self.num_repeat))

        # plot histogram in realtime
        # plt.hist(histpoints, bins=10)
        # ax=plt.gca()
        # # ax.set_ylim([0,200])
        # ax.set_xlim([0, 100])
        # plt.pause(0.5)
        # plt.clf()

        # else:
        #     self.scanHistogramList=[histpoints]
        # print(self.scanHistogramList)
        # self.run.counts.push(mean_rising_edges /1)
        # self.run.res_err.push(mean_rising_edges/(1*sqrt(self.num_repeat)))
        # self.scanHistogramList.append(self.run.histpoints)

        # self.runObj.cooling_counts.push(mean_rising_edges_cooling / 1)

    # print('Mean:'+str(mean_rising_edges)+'\n'+'Stddev:'+str(mean_rising_edges/ sqrt(self.num_repeat)))

    # print("{0:.7f}".format(mean_rising_edges/ sqrt(self.num_repeat)))
    # print(oitg.fitting.exponential_decay.fit(self.time, self.run.counts, self.run.res_err, evaluate_function=True,
    #                                          evaluate_n=100))

    def save_global_dataset(self):
        '''
         Save all global dataset parameters in a dictionary here.
        '''

        parentdir = r"C:\Users\TrappedIonRice4\Documents\Artiq-Rice"  # system dependent
        datasetdir = parentdir + "\dataset_db.pyon"
        self.globaldataset = {}
        f = open(datasetdir, 'r')
        txt = f.readlines()
        f.close()  # must close the dataset file soon enough to reflect the updates.
        for ele in txt[1:-1]:  # ignoring curly braces
            ele2 = ele.split(":")  # some regex
            ele3 = (ele2[0].split('    '))[-1]
            ele4 = ''.join(list(ele3)[1:-1])
            self.globaldataset[ele4] = self.get_dataset(ele4)

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
        self.set_dataset('Histogram', self.scanHistogramList, broadcast=True, archive=True, persist=True)
        self.save_global_dataset()

        # print(self.runObj.counts)

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




