# *****************************************************************
# IonControl:  Copyright 2016 Sandia Corporation
# This Software is released under the GPL license detailed
# in the file "license.txt" in the top-level IonControl directory
# *****************************************************************
# import functools
from functools import partial

from PyQt5 import QtCore, QtWidgets
import PyQt5.uic

# from modules import CountrateConversion
# from trace.pens import penicons
# from uiModules.ComboBoxDelegate import ComboBoxDelegate
# from uiModules.MultiSelectDelegate import MultiSelectDelegate
# from uiModules.MagnitudeSpinBoxDelegate import MagnitudeSpinBoxDelegate
# from modules.PyqtUtility import updateComboBoxItems

# from modules.Utility import unique

from datetime import datetime, timedelta
# import copy

import os

from uiModules.ParameterTable import ParameterTable, Parameter, ParameterTableModel
# from pulseProgram import VariableTableModel, VariableDictionary
from modules.SequenceDict import SequenceDict
from pint import UnitRegistry
from modules.GuiAppearance import restoreGuiState, saveGuiState

# from modules.AttributeComparisonEquality import AttributeComparisonEquality

uipath = os.path.join(os.path.dirname(__file__), '..', 'ui/CameraSettings.ui')
UiForm, UiBase = PyQt5.uic.loadUiType(uipath)

Q = UnitRegistry.Quantity

import pytz


def now():
    return datetime.now(pytz.utc)


class Settings(object):
    def __init__(self):

        self.liveExposureTime = Parameter(name='Live exposure time', dataType='magnitude', value=Q(50, 'ms'),
                                          tooltip="Livemode exposure time")
        self.liveCycleTime = Parameter(name='Live cycle time', dataType='magnitude', value=Q(50, 'ms'),
                                       tooltip="Livemode exposure time")
        self.EMCCDGain = Parameter(name='EMCCDGain', dataType='magnitude', value=0, tooltip="EM gain")
        self.H1 = Parameter(name='H1', dataType='magnitude', value=1,
                                             tooltip="Horizontal start point")
        self.H2 = Parameter(name='H2', dataType='magnitude', value=512,
                                             tooltip="Horizontal end point")
        self.V1 = Parameter(name='V1', dataType='magnitude', value=1,
                                             tooltip="Vertical start point")
        self.V2 = Parameter(name='V2', dataType='magnitude', value=512,
                                             tooltip="Vertical end point")
        self.repetition = Parameter(name='Repetition', dataType='magnitude', value=1, tooltip='Number of repetitions')
        self.NumberOfIons = Parameter(name='ionNumber', dataType='magnitude', value=1, tooltip="Number of Ions")
        self.parameterDict = SequenceDict([(self.liveExposureTime.name, self.liveExposureTime),
                                           (self.liveCycleTime.name, self.liveCycleTime),
                                           (self.EMCCDGain.name, self.EMCCDGain),
                                           (self.NumberOfIons.name, self.NumberOfIons),
                                           (self.repetition.name, self.repetition),
                                           (self.H1.name, self.H1),
                                           (self.H2.name, self.H2),
                                           (self.V1.name, self.V1),
                                           (self.V2.name, self.V2)])
        self.name = "CameraSettings"

    def check_settings(self):
        if self.EMCCDGain.value > 200:
            self.EMCCDGain.value = 200
            print("EMGain Set Too High")
        print(self.liveExposureTime.value)
        upperET = Q(500, 'ms')
        if upperET < self.liveExposureTime.value:
            self.liveExposureTime.value = Q(500, 'ms')
            print("liveExposureTime Set Too High")
        if self.liveCycleTime.value < self.liveExposureTime.value:
            self.liveCycleTime.value = self.liveExposureTime.value * 1.3
            print("Live cycle time is lower than live exposure time")

    def __setstate__(self, state):
        """this function ensures that the given fields are present in the class object
        after unpickling. Only new class attributes need to be added here.
        """
        self.__dict__ = state
        # self.__dict__.setdefault( 'exposureTime', Q(20, 'ms') )
        # self.__dict__.setdefault( 'EMGain', 0)
        # self.__dict__.setdefault('NumberOfExperiments', 200)

        # self.__dict__.setdefault(self.exposureTime.name, self.exposureTime.value)
        # self.__dict__.setdefault(self.EMGain.name, self.EMGain.value)
        # self.__dict__.setdefault(self.NumberOfExperiments.name, self.NumberOfExperiments.value)
        self.__dict__.setdefault('param'
                                 'eterDict', SequenceDict(
            [(self.exposureTime.name, self.exposureTime), (self.EMGain.name, self.EMGain),
             (self.NumberOfExperiments.name, self.NumberOfExperiments)]))
        self.__dict__.setdefault('name', 'CameraSettings')


class CameraSettings(UiForm, UiBase):
    valueChanged = QtCore.pyqtSignal(object)

    def __init__(self, config, globalVariablesUi, cam =None, parent=None):
        UiForm.__init__(self)
        UiBase.__init__(self, parent)
        self.config = config
        self.settings = self.config.get('CameraSettings.Settingis', Settings())
        self.settingsDict = self.config.get('CameraSettings.Settings.dict', dict())
        self.currentSettingsName = self.config.get('CameraSettings.SettingsName', '')
        self.cam = cam
        self.globalVariables = globalVariablesUi.globalDict
        self.globalVariablesChanged = globalVariablesUi.valueChanged
        self.globalVariablesUi = globalVariablesUi

        self.parameterDict = self.settings.parameterDict
        self.ParameterTableModel = ParameterTableModel(parameterDict=self.parameterDict)

    def setupUi(self, parent):
        UiForm.setupUi(self, parent)

        # self.integrationTimeBox.setValue( self.settings.integrationTime )
        # self.integrationTimeBox.valueChanged.connect( functools.partial(self.onValueChanged, 'integrationTime') )
        # self.exposureTimeBox.setValue( self.settings.exposureTime1 )
        # self.exposureTimeBox.valueChanged.connect( functools.partial(self.onValueChanged,'exposureTime') )
        # self.EMGainBox.setValue(self.settings.EMGain1)
        # self.EMGainBox.valueChanged.connect(functools.partial(self.onValueChanged, 'EMGain'))

        self.ParameterTable = ParameterTable()
        self.ParameterTable.setupUi(parameterDict=self.parameterDict, globalDict=self.globalVariables)
        self.parameterView.setModel(self.ParameterTableModel)
        self.parameterView.resizeColumnToContents(0)

        # self.delegate = MagnitudeSpinBoxDelegate(self.globalVariables)
        # self.parameterView.setItemDelegateForColumn(1, self.delegate)
        if self.globalVariablesChanged:
            self.globalVariablesChanged.connect(
                partial(self.ParameterTableModel.evaluate, self.globalVariables))

        self.ParameterTableModel.valueChanged.connect(
            partial(self.onDataChanged, self.ParameterTableModel.parameterDict))

        restoreGuiState(self, self.config.get('CameraSettings.guiState'))

    def onDataChanged(self, parameterDict):
        for key, param in self.parameterDict.items():
            # print('{0}: {1}'.format(key, param.value))
            if type(param.value) == str:
                param.value = Q(param.value)
        self.settings.check_settings()
        self.cam.onSettingsChanged()
        # print('Changed Camera Parameters')

    def onValueChanged(self, name, value):
        setattr(self.settings, name, Q(value))
        self.valueChanged.emit(self.settings)

    def changeSettings(self, config):
        print(config)
        self.settings.liveExposureTime.value = Q(config['ExposureTime'], 'ms')
        self.settings.liveCycleTime.value = Q(config['CycleTime'], 'ms')
        self.settings.EMCCDGain.value = config['EMCCDGain']
        self.settings.repetition.value = config['Repetition']

        self.settings.NumberOfIons.value = config['IonNumber']
        if config['UseROI']:
            ROI = config['ROI']
            self.settings.H1.value = ROI['H1']
            self.settings.H2.value = ROI['H2']
            self.settings.V1.value = ROI['V1']
            self.settings.V2.value = ROI['V2']


    def saveConfig(self):
        self.config['CameraSettings.Settings'] = self.settings
        self.config['CameraSettings.guiState'] = saveGuiState(self)
        self.config['CameraSettings.Settings.dict'] = self.settingsDict
        self.config['CameraSettings.SettingsName'] = self.currentSettingsName
