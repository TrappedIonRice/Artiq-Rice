import time

from artiq.experiment import *
from collections import OrderedDict
from copy import copy
import numpy as np
import time

'''
Script handles DC bias electrode manipulation for different voltage combinations.
Two representations of DC electrodes: 1) abstract, 2) real

1) Abstract DC electrodes used for electrode manipulation: 
Assumes 0- RF bottom and 11 - RF top, 1-5 DC 1, 6-10 DC2 with 5 opposite 6

2) Real DC electrodes are the Zotino channel values from 0-11 channel. 
Zotino and DC.ElectrodeValues have the real electrode mapping

Mapping between the two representations is made through DC.ElectrodeMapping with elements as 
    index= abstract electrode position, value= real electrode position.

Log outputs the values of real and abstract DC electrodes V like zotino DAC channels

'''
class DC_Control(EnvExperiment):
    def build(self):
        self.setattr_device("core")
       # self.setattr_device("urukul0_cpld")# Doppler
       # self.setattr_device("urukul0_ch0")  # Doppler
        self.setattr_device("zotino0")
        self.DCbounds=[-9.99,9.99]

    def prepare(self):
        '''
        Data update operations must tale place here and not in build.

        '''
        # DC bias electrode values
        self.DCElectrodeValuesOriginal = self.get_dataset("DC.ElectrodeValues",archive=True)
        #votlage addition must start from 0
        self.DCElectrodeValues = [0.0]*12

        # DC mapping
        # index=abstract DAC channel/ Trap electrode no., value= real Zotino DAC channel/DC, eg. pos 0 val 2 means DC0 (RF electrode) of trap will map with value of DACpin 2
        self.DCElectrodeMapping = [0,1,2,3,5,7,4,6,8,9,10,11] # 2023/11/1  # change config here
        # self.DCElectrodeMapping = [0,1,2,3,4,5,6,7,8,9,10,11]   #2023/10/20
        self.set_dataset("DC.ElectrodeMapping", self.DCElectrodeMapping, broadcast=True, archive=True, persist=True)
        #[0, 2, 1, 3, 4, 6, 5, 8, 7, 10, 9, 11]#self.get_dataset("DC.ElectrodeMapping", archive=True)
        # eg. [0, 2, 1, 3, 4, 5, 6, 8, 7, 9, 10, 11]

        # first reading values off of dataset
        self.VComboList=OrderedDict()
        self.VComboList={
            "DC.EndcapX": [self.get_dataset("DC.EndcapX"), self.endcapX],
            "DC.EndcapAvg": [self.get_dataset("DC.EndcapAvg"),self.endcapAvg],
            "DC.EndcapYZ": [self.get_dataset("DC.EndcapYZ"),self.endcapYZ],
            "DC.EndcapTiltYZ": [self.get_dataset("DC.EndcapTiltYZ"),self.endcapTiltYZ],
            "DC.MidcapX": [self.get_dataset("DC.MidcapX"),self.midcapX],
            "DC.MidcapAvg": [self.get_dataset("DC.MidcapAvg"), self.midcapAvg],
            "DC.CenterY": [self.get_dataset("DC.CenterY"),self.centerY],
            "DC.CenterZ": [self.get_dataset("DC.CenterZ"),self.centerZ],
            "DC.CenterAvg": [self.get_dataset("DC.CenterAvg"),self.centerAvg],
           "DC.AllY": [self.get_dataset("DC.AllY"),self.allY],
           "DC.AllZ": [self.get_dataset("DC.AllZ"),self.allZ],
           "DC.Twist": [self.get_dataset("DC.Twist"),self.twist],
            "DC.RFBottom":[self.get_dataset("DC.RFBottom"),self.RFBottom],
            "DC.DC01": [self.get_dataset("DC.DC01"), self.DC1],
            "DC.DC02": [self.get_dataset("DC.DC02"), self.DC2],
            "DC.DC03": [self.get_dataset("DC.DC03"), self.DC3],
            "DC.DC04": [self.get_dataset("DC.DC04"), self.DC4],
            "DC.DC05": [self.get_dataset("DC.DC05"), self.DC5],
            "DC.DC06": [self.get_dataset("DC.DC06"), self.DC6],
            "DC.DC07": [self.get_dataset("DC.DC07"), self.DC7],
            "DC.DC08": [self.get_dataset("DC.DC08"), self.DC8],
            "DC.DC09": [self.get_dataset("DC.DC09"), self.DC9],
            "DC.DC10": [self.get_dataset("DC.DC10"), self.DC10],
            "DC.RFTop": [self.get_dataset("DC.RFTop"), self.RFTop],
            "DC.AllDC": [self.get_dataset("DC.AllDC"), self.allDC],

            # trapping at 2,3,8,9 electrodes
            "DC.TrapMidCent_EndcapX": [self.get_dataset("DC.TrapMidCent_EndcapX"), self.TrapMidCent_endcapX],
            "DC.TrapMidCent_EndcapAvg": [self.get_dataset("DC.TrapMidCent_EndcapAvg"), self.TrapMidCent_endcapAvg],
            "DC.TrapMidCent_EndcapYZ": [self.get_dataset("DC.TrapMidCent_EndcapYZ"), self.TrapMidCent_endcapYZ],
            "DC.TrapMidCent_EndcapTiltYZ": [self.get_dataset("DC.TrapMidCent_EndcapTiltYZ"), self.TrapMidCent_endcapTiltYZ],
            "DC.TrapMidCent_CenterY": [self.get_dataset("DC.TrapMidCent_CenterY"), self.TrapMidCent_centerY],
            "DC.TrapMidCent_CenterZ": [self.get_dataset("DC.TrapMidCent_CenterZ"), self.TrapMidCent_centerZ],
            "DC.TrapMidCent_CenterAvg": [self.get_dataset("DC.TrapMidCent_CenterAvg"), self.TrapMidCent_centerAvg],
            "DC.TrapMidCent_AllY": [self.get_dataset("DC.TrapMidCent_AllY"), self.TrapMidCent_allY],
            "DC.TrapMidCent_AllZ": [self.get_dataset("DC.TrapMidCent_AllZ"), self.TrapMidCent_allZ],
            "DC.TrapMidCent_Twist": [self.get_dataset("DC.TrapMidCent_Twist"), self.TrapMidCent_twist],

        }
        self.VComboListOriginal=copy(self.VComboList)

        # adding all voltage from each config
        # self.endcapX(self.get_dataset("DC.EndcapX"))

        # executing all voltage combinations
        for Vcombo in self.VComboList.keys():
            self.VComboList[Vcombo][1](self.VComboList[Vcombo][0])
            if self.valueBoundsCheck(Vcombo):
                break
        self.set_dataset("DC.ElectrodeValues", self.DCElectrodeValues, broadcast=True, archive=True, persist=True)
        print("Real Electrode Values: "+str(self.DCElectrodeValues))
        abstractval=[self.DCElectrodeValues[self.DCElectrodeMapping.index(i)] for i in range(12)]
        print("Abstract Electrode Values: "+str(abstractval))


    #@rpc(flags={"async"})
    def valueBoundsCheck(self, VcomboName) -> TBool:
        """
        Checks if all the DC electrode biases are within the bounds of the DAC or not and accordingly update
        """
        flag=0
        for i in range(12):
            elecvValue=self.DCElectrodeValues[self.DCElectrodeMapping[i]]
            if elecvValue > self.DCbounds[1]:
                print("Abstract DC {0:d}: {1:f} > {2:f}V ".format(i,elecvValue,self.DCbounds[1])) # checks electrode number acc. to schematic
                flag=1
            elif elecvValue < self.DCbounds[0]:
                print("Abstract DC {0:d}: {1:f} < {2:f}V ".format(i,elecvValue,self.DCbounds[0]))
                flag=1

        if flag==1:
            print("Update stopped at {0:s}. Reduce magnitude".format(VcomboName))
            print("Electrode values reset to previous config.")
            # resetting electrode config
            self.DCElectrodeValues = self.DCElectrodeValuesOriginal
            # resetting values in dataset is not possible now because currently cannot access values of dataset stored a few min ago.
            return 1
        return 0

    def electrodeUpdate(self,V,electrodeList,signList):
        for i in range(len(electrodeList)):
            self.DCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] = \
                self.DCElectrodeValues[self.DCElectrodeMapping[electrodeList[i]]] + V*(signList[i])

    def RFBottom(self,V):
        self.electrodeUpdate(V, [0], [1])
    def RFTop(self,V):
        self.electrodeUpdate(V, [11], [1])
    def DC1(self,V):
        self.electrodeUpdate(V, [1], [1])
    def DC2(self,V):
        self.electrodeUpdate(V, [2], [1])
    def DC3(self,V):
        self.electrodeUpdate(V, [3], [1])
    def DC4(self,V):
        self.electrodeUpdate(V, [4], [1])
    def DC5(self,V):
        self.electrodeUpdate(V, [5], [1])
    def DC6(self, V):
        self.electrodeUpdate(V, [6], [1])
    def DC7(self, V):
        self.electrodeUpdate(V, [7], [1])
    def DC8(self, V):
        self.electrodeUpdate(V, [8], [1])
    def DC9(self, V):
        self.electrodeUpdate(V, [9], [1])
    def DC10(self, V):
        self.electrodeUpdate(V, [10], [1])
    def endcapX(self, V):
        self.electrodeUpdate(V,[1,5,6,10],[1,-1,-1,1])
    def endcapAvg(self, V):
        self.electrodeUpdate(V, [1, 5, 6, 10], [1, 1, 1, 1])
    def endcapYZ(self, V): # +ve V in +YZ quadrant
        self.electrodeUpdate(V, [1, 5, 6, 10], [-1, -1, 1, 1])
    def endcapTiltYZ(self, V): # +ve V follows clockwise in DC blades plane
        self.electrodeUpdate(V, [1, 5, 6, 10], [-1, 1, -1, 1])
    def midcapX(self, V):
        self.electrodeUpdate(V, [2, 4, 7, 9], [1, -1, -1, 1])
    def midcapAvg(self, V):
        self.electrodeUpdate(V, [2, 4, 7, 9], [1, 1, 1, 1])
    def centerY(self, V):
        self.electrodeUpdate(V, [3, 8, 0, 11], [-1, 1, -1, 1])
    def centerZ(self, V):
        self.electrodeUpdate(V, [3, 8, 0, 11], [-1, 1, 1, -1])
    def centerAvg(self, V):
        self.electrodeUpdate(V, [3, 8, 0, 11], [1, 1, 1, 1])

    def allY(self, V):
        """
        pushes towards +ve Y with all electrodes
        """
        self.electrodeUpdate(V,range(12),[-1]+[-1]*5+[1]*5+[1])
    def allZ(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V,range(12),[1]+[-1]*5+[1]*5+[-1])
    def twist(self, V):
        """
        :param V:  Positive V means DC's have +ve push and RF have -ve push
        """
        self.electrodeUpdate(V,range(12),[-1]+[1]*10+[-1])

    def allDC(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V, range(12), [1]*12)

    ### Now the same for trapping at midcap and centercap, with  4&5 shorted, trapping at electrodes 2,3,8,9 #########

    def TrapMidCent_endcapX(self, V):
        self.electrodeUpdate(V,[1,4,5,6,7,10],[1,-1,-1,-1,-1, 1])
    def TrapMidCent_endcapAvg(self, V):
        self.electrodeUpdate(V, [1,4,5,6,7,10], [1, 1, 1, 1, 1, 1])
    def TrapMidCent_endcapYZ(self, V): # +ve V in +YZ quadrant
        self.electrodeUpdate(V, [1,4,5,6,7,10], [-1, -1, -1, 1,  1, 1])
    def TrapMidCent_endcapTiltYZ(self, V): # +ve V follows clockwise in DC blades plane
        self.electrodeUpdate(V, [1,4,5,6,7,10], [-1, 1, 1, -1, -1, 1])

    def TrapMidCent_centerY(self, V):
        self.electrodeUpdate(V, [2, 3, 8, 9, 0, 11], [-1, -1, 1, 1, -1, 1])
    def TrapMidCent_centerZ(self, V):
        self.electrodeUpdate(V, [2, 3, 8, 9, 0, 11], [-1, -1, 1, 1, 1, -1])
    def TrapMidCent_centerAvg(self, V):
        self.electrodeUpdate(V, [2, 3, 8, 9, 0, 11], [1, 1, 1, 1, 1, 1])

    def TrapMidCent_allY(self, V):
        """
        pushes towards +ve Y with all electrodes
        """
        self.electrodeUpdate(V,range(12),[-1]+[-1]*5+[1]*5+[1])
    def TrapMidCent_allZ(self, V):
        """
        pushes towards +ve Z with all electrodes
        """
        self.electrodeUpdate(V,range(12),[1]+[-1]*5+[1]*5+[-1])
    def TrapMidCent_twist(self, V):
        """
        :param V:  Positive V means DC's have +ve push and RF have -ve push
        """
        self.electrodeUpdate(V,range(12),[-1]+[1]*10+[-1])



    @kernel
    def krun(self):
        self.core.reset()
        self.zotino0.init()
        # self.urukul0_cpld.init() # for now this isn't doing anything
        # self.urukul0_ch0.init()
        delay(10 * ms)
        # updating zotino with all voltage combinations on electrodes.
        for i in range(12):

            self.zotino0.write_dac(self.DCElectrodeMapping[i],
                                   self.DCElectrodeValues[self.DCElectrodeMapping[i]])
            self.zotino0.load()
            delay(0.1*ms)

    def run(self):
        self.krun()










