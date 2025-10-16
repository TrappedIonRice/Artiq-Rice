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
from uiModules.MagnitudeSpinBoxDelegate import MagnitudeSpinBoxDelegate
# from modules.PyqtUtility import updateComboBoxItems

# from modules.Utility import unique

from datetime import datetime, timedelta
# import copy

import os

from uiModules.ParameterTable import ParameterTable, Parameter, ParameterTableModel
# from pulseProgram import VariableTableModel, VariableDictionary
from modules.SequenceDict import SequenceDict
from modules.quantity import Q
from modules.GuiAppearance import restoreGuiState, saveGuiState

# from modules.AttributeComparisonEquality import AttributeComparisonEquality

uipath = os.path.join(os.path.dirname(__file__), '..', 'ui\CameraSettings.ui')
UiForm, UiBase = PyQt5.uic.loadUiType(uipath)

import pytz
import os, sys
import PyQt5.uic

HERE = os.path.dirname(os.path.abspath(__file__))          # ...\Camera_2025_Mulin
UI_DIR = os.path.join(HERE, "ui")                           # ...\Camera_2025_Mulin\ui
UI_RC_DIR = UI_DIR


if UI_RC_DIR not in sys.path:
    sys.path.insert(0, UI_RC_DIR)

uipath = os.path.join(UI_DIR, "CameraSettings.ui")
UiForm, UiBase = PyQt5.uic.loadUiType(uipath)




def now():
    return datetime.now(pytz.utc)


class Settings(object):
    def __init__(self):
        self.exposureTime = Parameter(name = 'Exposure time', dataType = 'magnitude', value = Q(1, 'ms'),
                                      tooltip = "Exposure time")
        self.liveExposureTime = Parameter(name = 'Live exposure time', dataType = 'magnitude', value = Q(50, 'ms'),
                                        tooltip = "Livemode exposure time")
        self.EMGain = Parameter(name = 'EMGain', dataType = 'magnitude', value = 0, tooltip = "EM gain")
        self.EMAdvanced = Parameter(name = 'EMAdvanced', dataType = 'magnitude', value = 0, tooltip = "EM advanced")
        self.NumberOfExperiments = Parameter(name = 'experiments', dataType = 'magnitude', value = 50,
                                             tooltip = "Number of experiments")
        self.NumberOfIons = Parameter(name = 'ionNumber', dataType = 'magnitude', value = 1, tooltip = "Number of Ions")
        self.parameterDict = SequenceDict([(self.exposureTime.name, self.exposureTime),
                                           (self.liveExposureTime.name, self.liveExposureTime),
                                           (self.EMGain.name, self.EMGain),
                                           (self.EMAdvanced.name, self.EMAdvanced),
                                           (self.NumberOfExperiments.name, self.NumberOfExperiments),
                                           (self.NumberOfIons.name, self.NumberOfIons)])
        self.name = "CameraSettings"

    def check_settings(self):
        if self.EMGain.value > 1000:
            self.EMGain.value = 1000
            print("EMGain Set Too High")
        if  self.liveExposureTime.value > Q(100, 'ms'):
            self.liveExposureTime.value = Q(100, 'ms')
            print("liveExposureTime Set Too High")

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
        self.__dict__.setdefault('parameterDict', SequenceDict(
                [(self.exposureTime.name, self.exposureTime), (self.EMGain.name, self.EMGain),
                 (self.NumberOfExperiments.name, self.NumberOfExperiments)]))
        self.__dict__.setdefault('name', 'CameraSettings')


class CameraSettings(UiForm, UiBase):
    valueChanged = QtCore.pyqtSignal(object)

    def __init__(self, config, globalVariablesUi, parent = None):
        UiForm.__init__(self)
        UiBase.__init__(self, parent)
        self.config = config
        self.settings = self.config.get('CameraSettings.Settings', Settings())
        self.settingsDict = self.config.get('CameraSettings.Settings.dict', dict())
        self.currentSettingsName = self.config.get('CameraSettings.SettingsName', '')

        self.globalVariables = globalVariablesUi.globalDict
        self.globalVariablesChanged = globalVariablesUi.valueChanged
        self.globalVariablesUi = globalVariablesUi

        self.parameterDict = self.settings.parameterDict
        self.ParameterTableModel = ParameterTableModel(parameterDict = self.parameterDict)

    def setupUi(self, parent):
        UiForm.setupUi(self, parent)

        # self.integrationTimeBox.setValue( self.settings.integrationTime )
        # self.integrationTimeBox.valueChanged.connect( functools.partial(self.onValueChanged, 'integrationTime') )
        # self.exposureTimeBox.setValue( self.settings.exposureTime1 )
        # self.exposureTimeBox.valueChanged.connect( functools.partial(self.onValueChanged,'exposureTime') )
        # self.EMGainBox.setValue(self.settings.EMGain1)
        # self.EMGainBox.valueChanged.connect(functools.partial(self.onValueChanged, 'EMGain'))

        self.ParameterTable = ParameterTable()
        self.ParameterTable.setupUi(parameterDict = self.parameterDict, globalDict = self.globalVariables)
        self.parameterView.setModel(self.ParameterTableModel)
        self.parameterView.resizeColumnToContents(0)

        self.delegate = MagnitudeSpinBoxDelegate(self.globalVariables)
        self.parameterView.setItemDelegateForColumn(1, self.delegate)
        if self.globalVariablesChanged:
            self.globalVariablesChanged.connect(
                partial(self.ParameterTableModel.evaluate, self.globalVariables))

        self.ParameterTableModel.valueChanged.connect(
                partial(self.onDataChanged, self.ParameterTableModel.parameterDict))

        restoreGuiState(self, self.config.get('CameraSettings.guiState'))

    def onDataChanged(self, parameterDict):
        self.settings.check_settings()
        # print('Changed Camera Parameters')
        # for key, param in self.parameterDict.items():
        #     print('{0}: {1}'.format(key, param.value))

    def onValueChanged(self, name, value):
        setattr(self.settings, name, value)
        self.valueChanged.emit(self.settings)

    def saveConfig(self):
        self.config['CameraSettings.Settings'] = self.settings
        self.config['CameraSettings.guiState'] = saveGuiState(self)
        self.config['CameraSettings.Settings.dict'] = self.settingsDict
        self.config['CameraSettings.SettingsName'] = self.currentSettingsName
