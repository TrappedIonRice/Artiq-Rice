"""
Author: Nate Dudley

Simple display of Andor temperature properties, including current temperature, temperature change rate, and temperature
set point.
"""

import functools
from functools import partial

from PyQt5 import QtGui, QtCore, QtWidgets
import PyQt5.uic

import os
import sys
from datetime import datetime, timedelta
import pytz
import time

uipath = os.path.join(os.path.dirname(__file__), '..', 'ui/Camera.ui')
UiForm, UiBase = PyQt5.uic.loadUiType(uipath)

class TemperatureMonitor(QtWidgets.QWidget):

    def __init__(self, parent = None):
        QtWidgets.QWidget.__init__(self, parent = None)

        self.layout = QtWidgets.QVBoxLayout()
        self.setPointDisp = None
        self.tempDisp = None
        self.tempRateDisp = None
        self.title = 'Temperature'
        self.setPoint = 0.
        self.currTemp = 0.
        self.prevTemp = 0.
        self.tempRate = 0.
        self.currTime = 0.
        self.prevTime = 0.

    def setupUi(self):
        self.setWindowTitle(self.title)
        # self.setGeometry(100, 100)

        self.setPointDisp = QtWidgets.QLabel()
        self.tempDisp = QtWidgets.QLabel()
        self.tempRateDisp = QtWidgets.QLabel()

        self.setPointDisp.setText('Target Temp = ')
        self.tempDisp.setText('Temp = ')
        self.tempRateDisp.setText('Temp Rate = ')

        self.layout.addWidget(self.setPointDisp)
        self.layout.addWidget(self.tempDisp)
        self.layout.addWidget(self.tempRateDisp)

        self.setLayout(self.layout)

        self.show()

    def setInitTemp(self, tempStart, setPoint):
        self.currTemp = tempStart
        self.setPoint = setPoint
        self.currTime = time.time()
        self.display()


    def updateTemp(self, temp):
        self.prevTemp = self.currTemp
        self.prevTime = self.currTime
        self.currTemp = temp
        self.currTime = time.time()
        try:
            self.tempRate = 60 * ((self.currTemp - self.prevTemp)/(self.currTime - self.prevTime))
        except ZeroDivisionError:
            pass
        self.display()

    def display(self):
        self.setPointDisp.setText('Target Temp = %0.1f C' % self.setPoint)
        self.tempDisp.setText('Temp = %0.1f C' % self.currTemp)
        self.tempRateDisp.setText('Temp Rate = %0.1f C/min' % self.tempRate)

if __name__ == '__main__':
    app = QtGui.QGuiApplication(sys.argv)
    GUI = TemperatureMonitor()
    GUI.setupUi()
    sys.exit(app.exec_())
