
from artiq.experiment import *
import numpy as np
from collections import OrderedDict
from copy import copy

class ExpConfig(EnvExperiment):

    def build(self):
        # Devices
        # self.setattr_device("core")
        # self.setattr_device("ccb")
        # self.setattr_device("urukul0_ch0")
        # self.setattr_device("urukul0_ch1")
        # self.setattr_device("urukul0_cpld")
        # self.setattr_device("zotino0")
        # self.setattr_device("scheduler")

        # self.setattr_device("core")
        # # self.setattr_device("urukul0_cpld")# Doppler
        # # self.setattr_device("urukul0_ch0")  # Doppler
        # self.setattr_device("zotino0")
        # self.DCbounds = [-9.99, 9.99]

        # self.DCbounds = [-9.99, 9.99]
        # self.lowerlim = 0.0001
        # self.upperlim = 0.14
        # self.dataReprate = 100
        #
        # self.amplitude = self.get_dataset("Loading.rf_ramp")
        # self.rf_frequency = self.get_dataset("Loading.rf_frequency")
        # self.all_y = self.get_dataset("Loading.all_y")
        # self.all_z = self.get_dataset("Loading.all_z")
        # self.attenuation = self.get_dataset("Loading.attenuation")
        # self.endcap_avg = self.get_dataset("Loading.endcap_avg")
        # self.target_amp = self.get_dataset("Loading.target_amplitude")
        # self.num_points = self.get_dataset("Loading.num_points")
        # self.ramp_rate = self.get_dataset("Loading.ramp_rate")
        # self.time_step = self.get_dataset("Loading.time_step")
        # self.twist = self.get_dataset("Loading.twist")
        # self.wait_time = self.get_dataset("Loading.wait_time")
        # self.doppler_freq = self.get_dataset("Loading.doppler_frequency")
        # self.doppler_amp = self.get_dataset("Loading.doppler_amplitude")

        self.endcap_avg = self.get_dataset("Experiment_config.endcap_avg")
        self.centercap_avg=self.get_dataset("Experiment_config.centercap_avg")
        self.midcap_avg=self.get_dataset("Experiment_config.midcap_avg")
        self.endcapX=self.get_dataset("Experiment_config.endcapX")
        self.all_y = self.get_dataset("Experiment_config.all_y")
        self.all_z = self.get_dataset("Experiment_config.all_z")
        self.twist = self.get_dataset("Experiment_config.Twist")

    def run(self):
        self.set_dataset("DC.EndcapAvg", self.endcap_avg, broadcast=True, archive=True, persist=True)
        self.set_dataset("DC.CenterAvg", self.centercap_avg, broadcast=True, archive=True, persist=True)
        self.set_dataset("DC.MidcapAvg", self.midcap_avg, broadcast=True, archive=True, persist=True)
        self.set_dataset("DC.EndcapX", self.endcapX, broadcast=True, archive=True, persist=True)
        self.set_dataset("DC.AllY", self.all_y, broadcast=True, archive=True, persist=True)
        self.set_dataset("DC.AllZ", self.all_z, broadcast=True, archive=True, persist=True)
        self.set_dataset("DC.Twist", self.twist, broadcast=True, archive=True, persist=True)


        # # DC bias electrode values
        # self.DCElectrodeValuesOriginal = self.get_dataset("DC.ElectrodeValues",archive=True)
        # #votlage addition must start from 0
        # self.DCElectrodeValues = [0.0]*12
        #
        # # DC mapping
        # # index=abstract DAC channel/ Trap electrode no., value= real Zotino DAC channel/DC, eg. pos 0 val 2 means DC0 (RF electrode) of trap will map with value of DACpin 2
        # self.DCElectrodeMapping = [0,1,2,3,5,7,4,6,8,9,10,11] # 2023/11/1  # change config here
        # # self.DCElectrodeMapping = [0,1,2,3,4,5,6,7,8,9,10,11]   #2023/10/20
        # self.set_dataset("DC.ElectrodeMapping", self.DCElectrodeMapping, broadcast=True, archive=True, persist=True)
        # #[0, 2, 1, 3, 4, 6, 5, 8, 7, 10, 9, 11]#self.get_dataset("DC.ElectrodeMapping", archive=True)
        # # eg. [0, 2, 1, 3, 4, 5, 6, 8, 7, 9, 10, 11]
        #
        # # first reading values off of dataset
        # self.VComboList=OrderedDict()
        # self.VComboList={
        #     "DC.EndcapX": [self.get_dataset("DC.EndcapX"), self.endcapX],
        #     "DC.EndcapAvg": [self.get_dataset("DC.EndcapAvg"),self.endcapAvg],
        #     "DC.EndcapYZ": [self.get_dataset("DC.EndcapYZ"),self.endcapYZ],
        #     "DC.EndcapTiltYZ": [self.get_dataset("DC.EndcapTiltYZ"),self.endcapTiltYZ],
        #     "DC.MidcapX": [self.get_dataset("DC.MidcapX"),self.midcapX],
        #     "DC.MidcapAvg": [self.get_dataset("DC.MidcapAvg"), self.midcapAvg],
        #     "DC.CenterY": [self.get_dataset("DC.CenterY"),self.centerY],
        #     "DC.CenterZ": [self.get_dataset("DC.CenterZ"),self.centerZ],
        #     "DC.CenterAvg": [self.get_dataset("DC.CenterAvg"),self.centerAvg],
        #    "DC.AllY": [self.get_dataset("DC.AllY"),self.allY],
        #    "DC.AllZ": [self.get_dataset("DC.AllZ"),self.allZ],
        #    "DC.Twist": [self.get_dataset("DC.Twist"),self.twist],
        #     "DC.RFBottom":[self.get_dataset("DC.RFBottom"),self.RFBottom],
        #     "DC.DC01": [self.get_dataset("DC.DC01"), self.DC1],
        #     "DC.DC02": [self.get_dataset("DC.DC02"), self.DC2],
        #     "DC.DC03": [self.get_dataset("DC.DC03"), self.DC3],
        #     "DC.DC04": [self.get_dataset("DC.DC04"), self.DC4],
        #     "DC.DC05": [self.get_dataset("DC.DC05"), self.DC5],
        #     "DC.DC06": [self.get_dataset("DC.DC06"), self.DC6],
        #     "DC.DC07": [self.get_dataset("DC.DC07"), self.DC7],
        #     "DC.DC08": [self.get_dataset("DC.DC08"), self.DC8],
        #     "DC.DC09": [self.get_dataset("DC.DC09"), self.DC9],
        #     "DC.DC10": [self.get_dataset("DC.DC10"), self.DC10],
        #     "DC.RFTop": [self.get_dataset("DC.RFTop"), self.RFTop],
        #     "DC.AllDC": [self.get_dataset("DC.AllDC"), self.allDC],
        #
        #     # trapping at 2,3,8,9 electrodes
        #     "DC.TrapMidCent_EndcapX": [self.get_dataset("DC.TrapMidCent_EndcapX"), self.TrapMidCent_endcapX],
        #     "DC.TrapMidCent_EndcapAvg": [self.get_dataset("DC.TrapMidCent_EndcapAvg"), self.TrapMidCent_endcapAvg],
        #     "DC.TrapMidCent_EndcapYZ": [self.get_dataset("DC.TrapMidCent_EndcapYZ"), self.TrapMidCent_endcapYZ],
        #     "DC.TrapMidCent_EndcapTiltYZ": [self.get_dataset("DC.TrapMidCent_EndcapTiltYZ"), self.TrapMidCent_endcapTiltYZ],
        #     "DC.TrapMidCent_CenterY": [self.get_dataset("DC.TrapMidCent_CenterY"), self.TrapMidCent_centerY],
        #     "DC.TrapMidCent_CenterZ": [self.get_dataset("DC.TrapMidCent_CenterZ"), self.TrapMidCent_centerZ],
        #     "DC.TrapMidCent_CenterAvg": [self.get_dataset("DC.TrapMidCent_CenterAvg"), self.TrapMidCent_centerAvg],
        #     "DC.TrapMidCent_AllY": [self.get_dataset("DC.TrapMidCent_AllY"), self.TrapMidCent_allY],
        #     "DC.TrapMidCent_AllZ": [self.get_dataset("DC.TrapMidCent_AllZ"), self.TrapMidCent_allZ],
        #     "DC.TrapMidCent_Twist": [self.get_dataset("DC.TrapMidCent_Twist"), self.TrapMidCent_twist],
        #
        # }
        # self.VComboListOriginal=copy(self.VComboList)
        #
        # # adding all voltage from each config
        # # self.endcapX(self.get_dataset("DC.EndcapX"))
        #
        # # executing all voltage combinations
        # for Vcombo in self.VComboList.keys():
        #     self.VComboList[Vcombo][1](self.VComboList[Vcombo][0])
        #     if self.valueBoundsCheck(Vcombo):
        #         break
        # self.set_dataset("DC.ElectrodeValues", self.DCElectrodeValues, broadcast=True, archive=True, persist=True)
        # print("Real Electrode Values: "+str(self.DCElectrodeValues))
        # abstractval=[self.DCElectrodeValues[self.DCElectrodeMapping.index(i)] for i in range(12)]
        # print("Abstract Electrode Values: "+str(abstractval))

    # def prepare(self):
    #     self.set_dataset("Amplitude", np.full(int(self.num_points), float(np.nan)), broadcast=True, archive=False)
    #     self.set_dataset("Time", np.full(int(self.num_points), float(np.nan)), broadcast=True, archive=False)
    #     self.int_points = int(self.num_points)
    #     command = "${artiq_applet}plot_xy Amplitude --x Time --fit Amplitude"
    #     self.ccb.issue("create_applet", "Amplitude Ramp", command)
    #
    #     self.DCElectrodeValuesOriginal = self.get_dataset("DC.ElectrodeValues", archive=True) # DC bias electrode values
    #     self.DCElectrodeValues = [0.0] * 12 # votlage addition must start from 0
    #
    #     # DC mapping
    #     self.DCElectrodeMapping = [0, 1, 2, 3, 5, 7, 4, 6, 8, 9, 10, 11]  # 2023/11/1
    #     self.set_dataset("Loading.ElectrodeMapping", self.DCElectrodeMapping, broadcast=True, archive=True, persist=True)
    #
    #     # first reading values off of dataset
    #     self.VComboList = OrderedDict()
    #     self.VComboList = {
    #         "Loading.endcap_avg": [self.get_dataset("Loading.endcap_avg"), self.endcap_avg],
    #         "Loading.all_y": [self.get_dataset("Loading.all_y"), self.all_y],
    #         "Loading.all_z": [self.get_dataset("Loading.all_z"), self.all_z],
    #         "Loading.twist": [self.get_dataset("Loading.twist"), self.twist]
    #     }
    #     self.VComboListOriginal = copy(self.VComboList)
    #
    #     # executing all voltage combinations
    #     for Vcombo in self.VComboList.keys():
    #         #self.VComboList[Vcombo][1](self.VComboList[Vcombo][0])
    #         if self.valueBoundsCheck(Vcombo):
    #             break
    #
    #     self.set_dataset("Loading.ElectrodeValues", self.DCElectrodeValues, broadcast=True, archive=True, persist=True)
    #     print("Real Electrode Values: " + str(self.DCElectrodeValues))
    #     abstractval = [self.DCElectrodeValues[self.DCElectrodeMapping.index(i)] for i in range(12)]
    #     print("Abstract Electrode Values: " + str(abstractval))

    # def valueBoundsCheck(self, VcomboName) -> TBool:
    #     """
    #     Checks if all the DC electrode biases are within the bounds of the DAC or not and accordingly update
    #     """
    #     flag=0
    #     for i in range(12):
    #         elecvValue=self.DCElectrodeValues[self.DCElectrodeMapping[i]]
    #         if elecvValue > self.DCbounds[1]:
    #             print("Abstract DC {0:d}: {1:f} > {2:f}V ".format(i,elecvValue,self.DCbounds[1])) # checks electrode number acc. to schematic
    #             flag=1
    #         elif elecvValue < self.DCbounds[0]:
    #             print("Abstract DC {0:d}: {1:f} < {2:f}V ".format(i,elecvValue,self.DCbounds[0]))
    #             flag=1
    #
    #     if flag==1:
    #         print("Update stopped at {0:s}. Reduce magnitude".format(VcomboName))
    #         print("Electrode values reset to previous config.")
    #         # resetting electrode config
    #         self.DCElectrodeValues = self.DCElectrodeValuesOriginal
    #         return 1
    #     return 0
    #
    # def electrodeUpdate(self,V,electrodeList,signList):
    #     for i in range(len(electrodeList)):
    #         self.DCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] = \
    #             self.DCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] + V*(signList[i])
    #
    # def endcap_avg(self, V):
    #     self.electrodeUpdate(V, [1, 5, 6, 10], [1, 1, 1, 1])
    # def all_y(self, V):
    #     """
    #     pushes towards +ve Y with all electrodes
    #     """
    #     self.electrodeUpdate(V,range(12),[-1]+[-1]*5+[1]*5+[1])
    # def all_z(self, V):
    #     """
    #     pushes towards +ve Z with all electrodes
    #     """
    #     self.electrodeUpdate(V,range(12),[1]+[-1]*5+[1]*5+[-1])
    # def twist(self, V):
    #     """
    #     :param V:  Positive V means DC's have +ve push and RF have -ve push
    #     """
    #     self.electrodeUpdate(V,range(12),[-1]+[1]*10+[-1])
    #
    # @kernel
    # def initialize_urukul_zotino(self):
    #     self.core.reset()
    #     self.zotino0.init()
    #     self.urukul0_ch0.cpld.init()
    #     self.urukul0_ch0.init()
    #     self.urukul0_ch1.init()
    #     delay(1 * ms)
    #
    #
    # @kernel
    # def turn_on_nonRFDDS(self):
    #     self.urukul0_ch1.set(frequency=self.doppler_freq, amplitude=self.doppler_amp)
    #     self.urukul0_ch1.set_att(self.attenuation)
    #     self.urukul0_ch1.sw.on()
    #
    #
    # @kernel
    # def turn_on(self):
    #     self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=self.amplitude)
    #     self.urukul0_ch0.set_att(self.attenuation)
    #     self.urukul0_ch0.sw.on()
    #     delay(1 * ms)
    #
    #
    # @kernel
    # def turn_off(self):
    #     self.urukul0_ch0.sw.off()
    #     delay(1 * ms)
    #
    # @kernel
    # def activateUrukul(self):
    #
    #     self.initialize_urukul_zotino()
    #
    #     self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=self.amplitude)
    #     self.urukul0_ch0.set_att(0 * dB)
    #     self.urukul0_ch0.sw.on()
    #     print("Urukul0 ch0 on")
    #     print(self.amplitude)
    #     delay(10 * ms)
    #
    #     self.turn_on_nonRFDDS()
    #     self.krun(self.target_amp)
    #
    # @kernel
    # def krun(self, target_amp):
    #
    #     # settinbg zotino tp trapping configuration
    #     #delay(10 * ms)
    #     # for i in range(12):
    #     #     self.zotino0.write_dac(self.DCElectrodeMapping[i],
    #     #                            self.DCElectrodeValues[self.DCElectrodeMapping[i]])
    #     #     self.zotino0.load()
    #     #     delay(0.1 * ms)
    #
    #     amp = self.amplitude
    #     delay(2 * ms)
    #     idx = 0
    #     time = 0.0
    #     # ramp down before loading to release any trapped ions
    #     while amp > 0.00012: # 0.00012 corresponds to a min amplitude of 0.0001
    #         ampminus = (amp - self.ramp_rate)
    #         self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=ampminus)
    #         delay(2 * ms)
    #         self.set_dataset("Loading.rf_ramp", ampminus, broadcast=True, persist=True)
    #         if (idx % self.dataReprate == 0):
    #             self.changeDataset(ampminus, time, self.dataReprate, idx)
    #         amp = ampminus
    #         delay(self.time_step)
    #         time += self.time_step  # * 1000
    #         idx += 1
    #         delay(2 * ms)
    #
    #     if target_amp > amp:
    #         while amp < target_amp:
    #             ampplus = (amp + self.ramp_rate)
    #             self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=ampplus)
    #             delay(2 * ms)
    #             self.set_dataset("Loading.rf_ramp", ampplus, broadcast=True, persist=True)
    #             # for multiple points
    #             if (idx % self.dataReprate == 0):
    #                 self.changeDataset(ampplus, time, self.dataReprate, idx)
    #             amp = ampplus
    #             delay(self.time_step)
    #             time += (self.time_step)  # * 1000
    #             idx += 1
    #             delay(2 * ms)
    #
    #     else:
    #         while amp > self.target_amp:
    #             ampminus = (amp - self.ramp_rate)
    #             self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=ampminus)
    #             delay(2 * ms)
    #             self.set_dataset("Loading.rf_ramp", ampminus, broadcast=True, persist=True)
    #             if (idx % self.dataReprate == 0):
    #                 self.changeDataset(ampminus, time, self.dataReprate, idx)
    #             amp = ampminus
    #             delay(self.time_step)
    #             time += self.time_step  # * 1000
    #             idx += 1
    #             delay(2 * ms)
    #
    #     print("Ramp complete")
    #     delay(4 * ms)
    #     self.urukul0_ch0.set(frequency=self.rf_frequency, amplitude=self.target_amp)
    #     delay(1 * ms)
    #     self.set_dataset("Loading.rf_ramp", self.target_amp, broadcast=True, persist=True)
    #     delay(1 * ms)
    #
    #
    # @kernel
    # def changeDataset(self, amp, tm, mod, idx):
    #     self.mutate_dataset("Amplitude", idx // mod, amp)
    #     self.mutate_dataset("Time", idx // mod, tm)
    #
    #
    # def run(self):
    #     self.activateUrukul()









