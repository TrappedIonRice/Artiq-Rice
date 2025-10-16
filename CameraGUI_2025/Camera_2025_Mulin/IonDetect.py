"""
Author: Nate Dudley

Main class, IonDetection, used to identify Ion bright spots on a test image and create IonROI objects where ions
can be detected.
"""
from functools import partial

from PyQt5 import QtCore, QtWidgets
import PyQt5.uic

import numpy as np
import matplotlib.mlab as mlab
import matplotlib.pyplot as plt
from sklearn.cluster import AgglomerativeClustering
# from skimage.feature import blob_dog, blob_log
# from skimage.filters import gaussian
from modules.SequenceDict import SequenceDict
import time

import os
import sys

from uiModules.ParameterTable import ParameterTable, Parameter, ParameterTableModel
from pulseProgram import VariableTableModel, VariableDictionary
from modules.SequenceDict import SequenceDict
from modules.quantity import Q
from modules.GuiAppearance import restoreGuiState, saveGuiState

from pyqtgraph.graphicsItems import ROI

uipath = os.path.join(os.path.dirname(__file__), '..', 'ui/IonList.ui')
UiForm, UiBase = PyQt5.uic.loadUiType(uipath)

import pytz




class IonROI(ROI.RectROI):
    def __init__(self, center: np.ndarray, brightPoints: np.ndarray = None, radius = 1):
        self.center = center
        self.radius = radius
        super().__init__((round(center[0] - radius), round(center[1] - radius)), round(2 * radius))
        boundRadius = np.round(radius + 1)
        self.leftBound = int(np.round(self.center[0] - boundRadius))
        self.rightBound = int(np.round(self.center[0] + boundRadius))
        self.upBound = int(np.round(self.center[1] - boundRadius))
        self.lowBound = int(np.round(self.center[1] + boundRadius))
        self.brightPoints = brightPoints
        self.brightCalPoints = []
        self.darkCalPoints = []
        self._idCluster()

    def __str__(self) -> str:
        HSpan = (self.leftBound, self.rightBound)
        VSpan = (self.upBound, self.lowBound)
        Area = (self.rightBound - self.leftBound - 1) * (self.lowBound - self.upBound - 1)
        return 'R = {}, A = {}, C = {}'.format(self.radius, self.get_height()*self.get_width(), self.center)

    def __repr__(self):
        return 'IonROI({}, {}, {})'.format(self.center, self.brightPoints, self.radius)

    def is_inROI(self, x: int, y: int) -> bool:
        retval = False
        if self.leftBound < x < self.rightBound and self.upBound < y < self.lowBound:
            retval = True
        return retval

    def _idCluster(self):
        if self.brightPoints is not None:
            hMin = int(self.center[0])
            hMax = int(self.center[0])
            vMin = int(self.center[1])
            vMax = int(self.center[1])
            for i in self.brightPoints:
                if i[0] < hMin:
                    hMin = i[0]
                if i[0] > hMax:
                    hMax = i[0]
                if i[1] < vMin:
                    vMin = i[1]
                if i[1] > vMax:
                    vMax = i[1]
            self.leftBound = hMin - 1
            self.rightBound = hMax + 1
            self.upBound = vMin - 1
            self.lowBound = vMax + 1

    def get_height(self) -> int:
        return self.lowBound - self.upBound - 1

    def get_width(self) -> int:
        return self.rightBound - self.leftBound - 1

    def get_averageCounts(self, arr: np.array) -> float:
        count = 0
        numOfPoints = 0
        for i in range(self.leftBound + 1, self.rightBound):
            for j in range(self.upBound + 1, self.lowBound):
                count += arr[i][j]
                numOfPoints += 1
        return count / numOfPoints

    def calibrateThreshold(self) -> None:
        npBrightPts = np.asarray(self.brightCalPoints)
        npDarkPts = np.asarray(self.darkCalPoints)

        npDarkPts = 500 + 200*np.random.randn(5000)
        npBrightPts = 1500 + 200*np.random.randn(5000)

        nBrt, binsBrt, patchesBrt = plt.hist(npBrightPts, bins = 100, normed = True, color = 'red')
        nDrk, binsDrk, patchesDrk = plt.hist(npDarkPts, bins = 100, normed = True, color = 'blue')

        plt.show()

        # max = np.max(np.amax(npDarkPts), np.amax(npBrightPts))
        # maxOrder -= 2
        # binSize = np.ceil(10**maxOrder)
        # bins = range(0, 100 * binSize, binSize)
        # darkHist = []
        # brightHist = []
        # for binFloor in bins:
        #     count = 0
        #     for i in self.brightCalPoints:
        #         if binFloor <= i < binFloor + binSize:
        #             count += 1
        #     brightHist.append(count)
        #     count = 0
        #     for i in self.darkCalPoints:
        #         if binFloor <= i < binFloor + binSize:
        #             count += 1
        #     darkHist.append(count)
        #     binFloor += binSize



class IonDetection:

    def __init__(self, arr: np.ndarray, numIons: int = 0, threshold: int = None):
        self.IonDict = SequenceDict()
        self.arr = arr
        self.numIons = numIons
        if threshold is None:
            self._autoThreshold()
            print('Auto Threshold =', self.threshold)
        else:
            self.threshold = threshold

    def addCalCounts(self, arr: np.ndarray, dataType: str) -> None:
        if not (dataType == 'bright' or dataType == 'dark'):
            raise Exception('Invalid Data Type Parameter')
        for key in self.IonDict:
            count = self.IonDict[key].get_averageCounts(arr)
            if dataType == 'bright':
                self.IonDict[key].brightCalPoints.append(count)
            if dataType == 'dark':
                self.IonDict[key].darkCalPoints.append(count)
        return

    def countIons(self, minSig: float = 0.25, maxSig: float = 2, threshold: float = None, overlap: float = 0.9) -> int:
        # print(self.arr)
        filt_img = gaussian(self.arr, 1)
        self.filteredArray = np.asanyarray(filt_img)
        if threshold is None:
            threshold = self.filteredArray.max() * 0.15
        # print(self.arr.max())
        # print(self.filteredArray.max())
        # normFactor = self.arr.max()/self.filteredArray.max()
        # self.filteredArray = np.multiply(self.filteredArray, normFactor)
        # print(self.filteredArray)
        # ionList = blob_log(self.filteredArray, min_sigma = 1, max_sigma = 2, threshold = threshold, overlap = 0.75)
        ionList = blob_dog(self.filteredArray, min_sigma = minSig, max_sigma = maxSig, threshold = threshold,
                           overlap = overlap)
        # print(ionList)
        self.numIons = len(ionList)
        return len(ionList)

    @staticmethod
    def formatKey(idx: int) -> str:
        return 'Ion' + str(idx)

    def set_arr(self, newArr):
        self.arr = newArr

    def clearIons(self):
        self.IonDict = dict()
        self.numIons = 0

    def inROI(self, x: int, y: int) -> bool:
        for key in self.IonDict:
            if self.IonDict[key].is_inROI(x, y):
                return True
        return False

    def idIons(self):
        """
        Identify Ions as bright spots in the passed array.
        """
        arrShape = self.arr.shape
        # print(arrShape)
        brightList = []

        for i in range(arrShape[0]):
            for j in range(arrShape[1]):
                if self.arr[i][j] > self.threshold:
                    brightList.append([i, j])

        aglo = AgglomerativeClustering(self.numIons)
        aglo.fit(brightList)
        brightList = zip(brightList, aglo.labels_)
        sort_brtPnts = [[] for _ in range(self.numIons)]
        for i in brightList:
            sort_brtPnts[i[1]].append(i[0])
        cent = []
        for i in sort_brtPnts:
            i = np.asanyarray(i)
            x = 0
            y = 0
            for j in i:
                x += j[0]
                y += j[1]
            x /= len(i)
            y /= len(i)
            cent.append((x, y))
        sorted(cent, key = lambda point: point[1])
        cent.sort(key=lambda tup: tup[1]) #THIS SORTS THE CENTER BY Y POSITION

        for i in range(self.numIons):
            self.IonDict[self.formatKey(i)] = IonROI((cent[i][0], cent[i][1]), radius = 2.5)

    def showIonROIs(self):
        # Display Ion ROIs on passed array.
        a = np.asanyarray(self.arr)
        self.arr = [[] for _ in range(a.shape[0])]
        for i in range(a.shape[0]):
            for j in range(a.shape[1]):
                self.arr[i].append(a[i][j])
        self.arr = np.asanyarray(self.arr)
        for key in self.IonDict:
            cent = self.IonDict[key].center
            rad = np.round(self.IonDict[key].radius)
            a[int(cent[0])][int(cent[1])] += 5 * self.threshold
            for i in range(int(cent[0] - rad - 1), int(cent[0] + rad + 2), 2):
                for j in range(int(cent[1] - rad - 1), int(cent[1] + rad + 2), 2):
                    if 0 <= i < self.arr.shape[0] and 0 <= j < self.arr.shape[1]:
                        if int(np.absolute(cent[0] - i) == int(rad) and np.absolute(cent[1] - j)) == int(rad):
                            a[i][j] = 100000
        self.arr = a

        return a

    def setDetectThreshold(self, val: int):
        self.threshold = val

    def _autoThreshold(self):
        self.threshold = (self.arr.max() + self.arr.min())/2

class IonList(UiForm, UiBase):
    valueChanged = QtCore.pyqtSignal(object)

    def __init__(self, config, parent=None):
        UiForm.__init__(self)
        UiBase.__init__(self, parent)

        self.config = config
        self.detector = None
        self.IonDict = SequenceDict()
        self.IonTableModel = ParameterTableModel(parameterDict=self.IonDict)

    def setupUi(self, parent):
        UiForm.setupUi(self, parent)

        self.IonTable = ParameterTable()
        self.IonTable.setupUi(parameterDict=self.IonDict)
        self.listView.setModel(self.IonTableModel)
        self.listView.resizeColumnToContents(0)

        self.IonTableModel.valueChanged.connect(
            partial(self.onDataChanged, self.IonTableModel.parameterDict))

        # restoreGuiState(self, self.config.get('IonList.guiState'))

    def onDataChanged(self, ionDict):
        pass

    def onValueChanged(self, ion, data):
        self.valueChanged.emit(self.detector)

    def saveConfig(self):
        self.config['IonList.guiState'] = saveGuiState(self)
