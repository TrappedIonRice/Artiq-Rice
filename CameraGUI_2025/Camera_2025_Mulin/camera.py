# *****************************************************************
# IonControl:  Copyright 2016 Sandia Corporation
# This Software is released under the GPL license detailed
# in the file "license.txt" in the top-level IonControl directory
# *****************************************************************
"""
Camera.py acquire images live or subjected to an external trigger and displays them.
"""

import os
import os.path
import queue
from collections import deque
from multiprocessing import Queue
import threading
from PyQt5.QtCore import QThread
import time
from contextlib import closing
import copy
import itertools

import PyQt5
import numpy
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal
from pyqtgraph import ImageView, ColorMap

from AndorShutdown import AndorShutdown
from CameraSettings import CameraSettings
from TemperatureMonitor import TemperatureMonitor
from IonDetect import *
import fileSettings
import readImage

import logging
from Configure_Loader import settings
# Go up a directory and then enter ui for camera ui
uipath = os.path.join(os.path.dirname(__file__), '..', 'ui/Camera.ui')
CameraForm, CameraBase = PyQt5.uic.loadUiType(uipath)

# try:
#     import ANDOR
#     camandor = ANDOR.Cam()
#     useAndor = not camandor.error
# except ImportError:
#     useAndor = False
#     print ("Andor not available.")

from Camera_2025_Mulin.ANDOR import Cam, CamTimeoutError, NoCamError
import json

camandor = Cam()
useAndor = True


class AndorTemperatureThread(QThread):  # Class added
    """This Thread monitor the Andor Temperature and displays it in the Status Bar"""
    temp_updated = QtCore.pyqtSignal(object)

    def __init__(self, app):
        QThread.__init__(self)
        self.app = app
        self.app.temperUi.setInitTemp(camandor.gettemperature(), -60)
        self.refreshRate = 0.5
        self.running = True

    def run(self):
        global andortemp
        andortemp = True
        self.app.statusBar().showMessage("Cooling")
        while andortemp and self.running:
            time.sleep(self.refreshRate)
            self.temp_updated.emit(camandor.gettemperature())
        self.stop()

    def stop(self):
        global andortemp
        andortemp = False
        self.app.statusBar().showMessage("Not Cooling")
        while camandor.gettemperature() < 0:
            time.sleep(self.refreshRate)
            self.temp_updated.emit(camandor.gettemperature())


class AndorProperties(object):
    def __init__(self, ampgain = 0, emgain = 0):
        self._ampgain = ampgain
        self._emgain = emgain

    def get_ampgain(self):
        return self._ampgain

    def set_ampgain(self, value):
        self._ampgain = value

    ampgain = property(get_ampgain, set_ampgain)

    def get_emgain(self):
        return self._emgain

    def set_emgain(self, value):
        self._emgain = value

    emgain = property(get_emgain, set_emgain)


class CamTiming(object):
    def __init__(self, exposure, repetition = None, live = True):
        self._exposure = exposure
        self._repetition = repetition
        self._live = live

    def get_exposure(self):
        if self._live:
            return self._exposure
        else:
            if useAndor:  # change this when you test it
                return self._exposure
            else:
                return 0

    def set_exposure(self, value):
        self._exposure = value

    exposure = property(get_exposure, set_exposure)

    def get_repetition(self):
        if self._live:
            return self._repetition
        else:
            if useAndor:
                return self._exposure
            else:
                return 0

    def set_repetition(self, value):
        self._repetition = value

    repetition = property(get_repetition, set_repetition)

    def get_live(self):
        return self._live

    def set_live(self, value = True):
        self._live = bool(value)

    live = property(get_live, set_live)

    def get_external(self):
        return not self.live

    def set_external(self, value):
        self.live = not value

    external = property(get_external, set_external)


# ACQUIRE THREADS
# Store image temporary from camera
class AcquireThread(QThread):
    """Base class for image acquisition threads."""
    image_available = QtCore.pyqtSignal(object, object)
    no_camera = QtCore.pyqtSignal()
    data_available = QtCore.pyqtSignal()

    def __init__(self, app, cam, queue, maxnr):
        QThread.__init__(self)
        self.app = app
        self.cam = cam
        self.queue = queue
        self.maxnr = maxnr

        self.running = False

    def run(self):
        pass

    def message(self, msg):
        self.app.statusBar().showMessage(str(msg))

    def stop(self):
        self.running = False
        self.cam.stop()

    def adjust_timing(self):
        """Adjust camera timing based on current parameters."""
        # set exposure times
        exp = self.app.parHand.getParam('Live exposure time') if self.cam.andormode != 'TriggeredAcquisition' \
            else self.app.parHand.getParam('Exposure time')
        self.app.timing_andor.set_exposure(exp)

        # set timing settings
        try:
            # This whole block is part of the old logic, but we've now cleaned up the
            # set_timing calls inside it to match the new function signature.
            try:
                emgainAdv_val = int(self.app.CameraParameters['EMAdvanced'].value)
                trigger = False
            except KeyError:
                trigger = True
            if trigger:
                if not self.app.timing_andor.get_external():
                    self.cam.set_timing(integration=exp,
                                        ampgain=self.app.properties_andor.get_ampgain(),
                                        emgain=int(self.app.CameraParameters['EMGain'].value),
                                        numExp=self.maxnr)
                else:
                    self.cam.set_timing(integration=exp,
                                        ampgain=self.app.properties_andor.get_ampgain(),
                                        emgain=int(self.app.CameraParameters['EMGain'].value),
                                        numExp=self.maxnr)
            else:
                if not self.app.timing_andor.get_external():
                    self.cam.set_timing(integration=exp,
                                        ampgain=self.app.properties_andor.get_ampgain(),
                                        emgain=int(self.app.CameraParameters['EMGain'].value),
                                        numExp=self.maxnr)
                else:
                    self.cam.set_timing(integration=exp,
                                        ampgain=self.app.properties_andor.get_ampgain(),
                                        emgain=int(self.app.CameraParameters['EMGain'].value),
                                        numExp=self.maxnr)
        except NoCamError:
            self.message("No Camera")
            self.no_camera.emit()
            self.quit()

    def check_overexposure(self, img, threshold = 10000):
        avgCounts = numpy.average(img)
        if avgCounts > threshold:
            self.stop()
            self.message("Camera Overexposed!")
            print('Camera Overexposed! Acquisition Aborted!')

# Acquire thread for live-mode camera
class AcquireThreadAndorLive(AcquireThread):
    def run(self):
        self.running = True
        print('Mode: ', camandor.andormode)
        with closing(self.cam.open()):
            self.adjust_timing()
            exp = self.app.parHand.getParam('Live exposure time') / 1000
            self.cam.start_acquisition()
            while self.running:
                try:
                    # self.cam.wait(exp)
                    time.sleep(exp)
                    # print('Status:', self.cam.get_status())
                    self.message('Live Running')
                    img = self.cam.roidata()
                except CamTimeoutError:
                    self.message('No Images')
                except NoCamError:
                    self.message("No Camera")
                    self.no_camera.emit()
                    self.quit()
                else:
                    self.image_available.emit(img, False)

        self.message('')
        print("Exiting")

#Acquisition of data for real experiment
class AcquireThreadAndor(AcquireThread):
    acquisition_finished = pyqtSignal() #10/7/2025 by MZ

    def run(self):
        self.wait_factor = 10
        self.running = True
        print('Mode: ', camandor.andormode)

        with closing(self.cam.open()):
            # --- START OF FIX ---

            # 1. Attempt to start the acquisition and get the status code
            status = self.cam.start_acquisition()

            # 2. Check if the status code indicates success (20002)
            if status != 20002:
                print("FATAL ERROR: Failed to start acquisition. Thread is exiting.")
                self.running = False  # Ensure the loop is skipped

            # --- END OF FIX ---

            self.imgAcq = 0
            self.timeoutCount = 0
            self.app.ready = True

            # This loop will now only be entered if acquisition started successfully
            while self.running:
                img = None
                try:
                    img = self.cam.roidata()
                except CamTimeoutError:
                    if self.wait_factor: time.sleep(self.app.timing_andor.get_exposure() / self.wait_factor)
                    self.timeoutCount += 1
                except NoCamError:
                    self.message("No Camera")
                    self.no_camera.emit()
                    self.quit()
                else:
                    # ... (rest of the loop) ...
                    self.timeoutCount = 0
                    self.imgAcq += 1
                    self.queue.put(img.astype(numpy.float32))
                    if (self.imgAcq % self.app.CameraParameters['experiments'].value == 0):
                        self.data_available.emit()

                    if (self.imgAcq == self.maxnr):
                        self.running = False

        # After the acquisition loop is finished, check if it was a successful run. 10/7/2025 by MZ
        if self.imgAcq == self.maxnr:
            print("Acquisition complete. Emitting signal for auto-save.")
            self.acquisition_finished.emit()


        if self.app.actionAcquire.isChecked():
            self.app.actionAcquire.setChecked(False)
            self.app.onAcquire()
        print("Thread Exiting Gracefully.")

class AcquireThreadAndorDetect(AcquireThread):

    def run(self):
        # Controls how long the thread waits after a timeout
        # If you're consistently not getting all the images from a scan, try increasing this parameter (0 == infinity)
        # Warning: higher values are likely to cause the program to lag
        self.wait_factor = 900
        #####################
        self.running = True
        # self.scanx = None
        print('Mode: ', camandor.andormode)
        with closing(self.cam.open()):
            self.adjust_timing()
            exp = self.app.timing_andor.get_exposure()
            self.cam.start_acquisition()
            self.imgAcq = 0
            self.timeoutCount = 0

            self.app.ready = True
            t0=time.time()

            while self.running:
                img = None
                if self.timeoutCount/exp > 10:
                    print("timeoutCount = ", self.timeoutCount, "exp = ", exp)
                    break
                try:
                    # self.cam.wait(exp)
                    # time.sleep(exp)
                    img = self.cam.roidata()
                except CamTimeoutError:
                    if self.wait_factor: time.sleep(exp/self.wait_factor)
                    print("Timeout!...ImagAcq = ",self.imgAcq)
                    t1 = time.time()
                    print("t1-t0_timeout = ", t1-t0)
                    self.timeoutCount += 1
                except NoCamError:
                    self.message("No Camera")
                    self.no_camera.emit()
                    self.quit()
                else:
                    t0=time.time()
                    self.timeoutCount = 0
                    # print(img)
                    self.imgAcq += 1
                    self.queue.put(img.astype(numpy.float32))
                    if (self.imgAcq == self.maxnr):
                        self.running = False

        if self.app.actionAcquire.isChecked():
            self.app.actionAcquire.setChecked(False)
            self.app.onAcquire()
        print("Exiting")


class AcquireThreadAndorAutoLoad(AcquireThread):

    def run(self):
        self.curNumOfIons = 0
        self.detector = IonDetection(None, numIons = self.curNumOfIons)
        self.running = True
        print('Mode: ', camandor.andormode)
        with closing(self.cam.open()):
            self.adjust_timing()
            exp = 0.5
            self.cam.start_acquisition()

            while self.running:
                try:
                    img = self.cam.roidata()
                except CamTimeoutError:
                    time.sleep(exp)
                except NoCamError:
                    self.message("No Camera")
                    self.no_camera.emit()
                    self.quit()
                else:
                    # print(img)
                    self.detector.set_arr(img)
                    self.curNumOfIons = self.detector.countIons(minSig = 1, maxSig = 6)

        print("Exiting")

class SaveCameraThread(QThread):
    # Thread that is utilized for saving camera data
    def __init__(self, imagequeue_andor, saved_parameters, ScanExperiment, fileName, rid="N/A"):
        QThread.__init__(self)
        self.imagequeue_andor = imagequeue_andor
        self.saved_parameters = saved_parameters
        self.ScanExperiment = ScanExperiment
        self.fileName = fileName
        self.rid = rid  # <-- Store the RID  Added 10/6/2025 MZ for rid storage


    def run(self):
        # File signature -- to detect incorrect format / data corruption
        sig = np.array([0x00, 0x43, 0x72, 0x79, 0x6f, 0x44, 0x4d, 0x00], np.uint8)
        # Header: single image height, single image width, # of images in scan, # of images in scanpoint
        h, w = self.imagequeue_andor.queue[0].shape
        n = len(self.imagequeue_andor.queue)
        p = self.saved_parameters['experiments']
        header = np.array([h, w, n, p], np.uint32)

        # String of parameters used in experiment, plus some formatting for readability
        if self.fileName is None:
            scanName = self.ScanExperiment.scanControlWidget.settingsName
        else:
            scanName = self.ScanExperiment.scanControlWidget.settingsName + "_" + self.fileName

        directoryName = self.ScanExperiment.scanControlWidget.settingsName
        scanpoints = self.saved_parameters['scanlist']
        globalVars = self.saved_parameters['globalVariables']
        pulserVars = self.saved_parameters['pulserParameters']
        text = "ARTIQ RID: " + str(self.rid) + "\n\n" # write RID into the SIS file10/6/2025 by MZ
        text += str(scanName)
        text += str(scanpoints)
        text += '\nGlobalVar {'
        text += ' ; '.join([str(key) + ' = ' + str(val) for key, val in globalVars.items()])
        text += ' }\nScanVar  { '
        for key, val in pulserVars.items():
            v, s, u = str(val.strvalue).partition(' ')
            try:
                v = float(v)
            except ValueError:
                pass
            if v != 0.0:
                text += ' ' + str(key) + ' = ' + str(val.strvalue) + ' ; '
        text += '}\n'

        text_length = len(text)

        # Convert text to data for writeout
        text = np.array([ord(c) for c in text], np.uint32)
        text_length = np.array([text_length], np.uint32)

        # Create file + directory
        imagesavesubdir = '%s/%s/%s/%s' % (
        time.strftime("%Y"), time.strftime("%Y_%m"), time.strftime("%Y_%m_%d"), directoryName)
        imagesavedir = os.path.join(fileSettings.imagesavepath, imagesavesubdir)
        imagesavefilename = "[%s,%s,%s][%s,%s,%s]%s.sis" % (time.strftime("%Y"), time.strftime("%m"),
                                                            time.strftime("%d"), time.strftime("%H"),
                                                            time.strftime("%M"), time.strftime("%S"), scanName)
        imagesavefilenamefull = os.path.normpath(os.path.join(imagesavedir, imagesavefilename))
        if not os.path.exists(imagesavedir):
            os.makedirs(imagesavedir)

        print("Saving scan as", imagesavefilenamefull)

        # Write to file
        with open(imagesavefilenamefull, 'wb') as f:
            sig.tofile(f)
            header.tofile(f)
            text_length.tofile(f)
            text.tofile(f)
            while self.imagequeue_andor.qsize() > 0:
                np.array(self.imagequeue_andor.get_nowait(), np.uint32).tofile(f)

        print("Save complete!")

# CAMERA CLASS

class Camera(CameraForm, CameraBase):
    dataAvailable = QtCore.pyqtSignal(object)
    OpStates = enum.enum('idle', 'running', 'paused')
    no_roi = QtCore.pyqtSignal()
    liveCount = 0

    class ParamDictHandler:

        def __init__(self, parameterDict):
            self.dict = parameterDict

        def getParam(self, param):
            paramVal = self.dict[param].value
            ret = None

            if str(paramVal.units) == 'us':
                ret = paramVal.magnitude * 0.001
            elif str(paramVal.units) == 'ms':
                ret = paramVal.magnitude
            else:
                ret = paramVal.magnitude * 1000 if param != 'experiments' else paramVal.magnitude

            return ret

    def __init__(self, config, globalVariablesUi, shutterUi, ScanExperiment, pulserProgram, parent = None):
        CameraForm.__init__(self)
        CameraBase.__init__(self, None)

        # Properties to integrate with other components of the code
        self.config = config
        self.configName = 'Camera'
        self.parent = parent
        self.pulserProgram = pulserProgram
        self.pulserParameters = pulserProgram.pulseProgramSet['ScanExperiment'].currentContext.parameters
        self.globalVariables = globalVariablesUi.globalDict
        self.globalVariablesChanged = globalVariablesUi.valueChanged
        self.globalVariablesUi = globalVariablesUi
        self.shutterUi = shutterUi
        self.ScanExperiment = ScanExperiment
        self.ScanList = self.ScanExperiment.scanControlWidget.getScan().list
        self.detectedROI = None
        self.fileName = None
        self.writeToFile = False
        self.bufferTime = 1000


        # Timing and acquisition settings
        self.imaging_mode_andor = "Live"

        self.view = None
        self.settingsUi = None
        self.temperUi = None

        self.imgproducer_andor = None
        self.imgconsumer_andor = None
        self.tempThrd = None
        self.save_camera = None

        self.acquiring_andor = False
        self.currentfolder = None
        self.imaging_andor_useROI = None
        self.busy = None

        self.CameraParameters = None
        self.parHand = None
        self.timing_andor = None
        self.imagequeue_andor = None
        self.scanDataQueue = None
        self.properties_andor = None
        self.imageDisp = None

        self.autoResize = True # Keeps track of whether or not image view needs to be rescaled; reset on crop
        self.ready = False # Is the camera ready to receive external exposure signals?

        # Ion ROIs
        self.ROI_list = []
        self.ROI_data = {}
        self.ROI_plots = {}
        self.camera_plot = self.parent.scanExperiment.plotDict["Camera"]["view"]
        self.points_processed = 0


    def setupUi(self, parent):
        CameraForm.setupUi(self, parent)

        self.setWindowTitle("Andor Camera")

        # Settings
        self.settingsUi = CameraSettings(self.config, self.globalVariablesUi)
        self.settingsUi.setupUi(self.settingsUi)
        self.settingsDock.setWidget(self.settingsUi)
        self.settingsUi.valueChanged.connect(self.onSettingsChanged)
        self.CameraParameters = self.settingsUi.ParameterTableModel.parameterDict
        self.parHand = self.ParamDictHandler(self.CameraParameters)
        self.fileNameEdit.returnPressed.connect(self.onEditFileName)
        self.setName.clicked.connect(self.onEditFileName)
        self.setName.setAutoDefault(True)
        # print(self.parHand.getParam('Exposure time'), self.parHand.getParam('experiments'))

        # Temperature
        self.temperUi = TemperatureMonitor(self)
        self.temperUi.setupUi()
        self.temperatureDock.setWidget(self.temperUi)

        # Image Display
        self.view = ImageView(self, name="MainDisplay")
        # ROI Snap-to-Grid
        self.view.roi.scaleSnap = True
        self.view.roi.translateSnap = True
        self.view.roi.rotateAllowed = False
        self.view.roi.removeHandle(1)
        self.view.roi.setPen('r')
        # We don't use the dynamic ROI-graph
        self.view.roi.sigRegionChanged.disconnect()
        self.view.roiChanged = lambda: None


        # self.colorMap = ColorMap([0, 0.25, 0.5, 0.75, 1],
        #                          [[0, 0, .4], [.55, .55, 1], [1, 1, 1], [1, 1, 0], [1, 0, 0]], ColorMap.RGB)
        # print(self.colorMap.getColors())
        # self.view.setColorMap(self.colorMap)
        self.setCentralWidget(self.view)

        # Arrange the dock widgets
        # self.tabifyDockWidget(self.view, self.settingsDock)

        # Ion List
        # self.ionTable = IonList(self.config)
        # self.ionListDock.setWidget(self.ionTable)
        # self.ionTable.setupUi(self)

        # Queues for image acquisition
        self.currentfolder = ' '
        self.imagequeue_andor = queue.Queue(self.CameraParameters['experiments'].value * len(self.ScanList))
        self.scanDataQueue = queue.Queue(self.CameraParameters['experiments'].value)
        self.timing_andor = CamTiming(exposure = 100, repetition = 1, live = True)
        self.properties_andor = AndorProperties(ampgain = 0, emgain = 0)
        self.imaging_andor_useROI = False

        # Actions
        self.actionSave.triggered.connect(self.onSave)
        self.actionAcquire.triggered.connect(self.onAcquire)
        self.actionCoolCCD.triggered.connect(self.onCoolCCD)
        self.actionLive.triggered.connect(self.onLive)
        self.actionDetect_Ions.triggered.connect(self.onDetecter)
        self.actionCrop_ROI.triggered.connect(self.onCrop)

        # Temperature Thread
        self.tempThrd = AndorTemperatureThread(self)
        self.tempThrd.temp_updated.connect(self.temperUi.updateTemp)
        self.tempThrd.start()

        # Previous Config restoration
        if self.configName + '.MainWindow.State' in self.config:
            QtGui.QMainWindow.restoreState(self, self.config[self.configName + '.MainWindow.State'])
        self.onSettingsChanged()

        # 10/06/2025 by MZ
        # 1. Load last-used settings from the file.
        self.loadSettings()

        # 2. Connect the "changed" signal of each parameter to the auto-save function.
        print("Connecting parameter 'changed' signals to auto-save...")
        for param in self.CameraParameters.values():
            param.changed.connect(self.onSaveSettings)


    @property
    def settings(self):
        return self.settingsUi.settings

    def toggleAcquire(self):
        if self.actionAcquire.isChecked():
            self.actionAcquire.setChecked(False)
            self.onAcquire()
        else:
            self.actionAcquire.setChecked(True)
            self.onAcquire()

    def updateTemp(self, temp):
        """Update temperature UI"""
        self.temperUi.update(temp)

    def displayImage(self, img, auto=False):
        """Displays a new image in the camera window."""
        img = numpy.asanyarray(img)
        self.view.setImage(img, autoRange=self.autoResize, autoLevels=auto)
        # Only resize on first image
        self.autoResize = False
        # On new startup, set levels appropriately
        if self.view.getLevels() == (0, 1):
            self.view.autoLevels()
            self.view.autoRange()
            levels = self.view.getLevels()
            self.view.setLevels(np.mean(levels), levels[1])

        # print(img, img.shape)
        # height = img.shape[0]
        # width = img.shape[1]
        # height = 10
        # width = 10
        # imglog = []
        # for x in range(height):
        #     imglog.append([])
        #     for y in range(width):
        #         imglog[x].append(0)

        # self.imageDisp = QtGui.QImage(height, width, QtGui.QImage.Format_RGB32)
        # for x in range(height):
        #     for y in range(width):
        #         pixBrt = img[x][y]
        #         pixBrt = numpy.random.randint(0, 255)
        #         imglog[x][y] = pixBrt = numpy.random.randint(0, 255)
        #         imglog[x][y] = pixBrt
        #         if pixBrt > 255:
        #             self.imageDisp.setPixel(x, y, QtGui.QColor(255, 0, 0, 255).rgb())
        #         else:
        #             self.imageDisp.setPixel(x, y, QtGui.QColor(pixBrt, pixBrt, pixBrt, 255).rgb())

        # print(imglog)

        # self.pixmap = QtGui.QPixmap.fromImage(self.imageDisp.scaledToWidth(570))
        # scene = QtWidgets.QGraphicsScene()
        # scene.addPixmap(self.pixmap)
        # self.CameraView.setScene(scene)
        # self.CameraView.setCacheMode(QtWidgets.QGraphicsView.CacheNone)

    def displayTable(self, table):
        # pass
        self.ionTable = table
        # self.ionListDock.setWidget(self.ionTable)

    def saveConfig(self):
        self.settings.state = self.saveState()
        self.settings.isVisible = self.isVisible()
        # self.config[self.configName] = self.settings
        # self.config[self.configName + '.MainWindow.State'] = QtWidgets.QMainWindow.saveState(self)
        self.settingsUi.saveConfig()
        # self.ionTable.saveConfig()

    def onEditFileName(self):
        """This edits the filename of the save file"""
        self.fileName = str(self.fileNameEdit.text())

    def onEditFileNameScript(self, name):
        """This edits the filename of the save file for the scripthandler"""
        self.fileName = name

    # Save the image data from the most recent scan
    def onSave(self):
        if self.imaging_mode_andor == "TriggeredAcquisition":
            # 1. Get the ARTIQ RID from your experiment controller.
            #    For now, we'll create a placeholder for now, and we will replace this by the real artiq rid later.
            artiq_rid = f"{time.strftime('%Y-%m-%d_%H%M%S')}_my_scan" #10/6/2025 by MZ
            print(f"Starting save process with ARTIQ RID: {artiq_rid}")

            # 2. Pass the RID when creating the SaveCameraThread.
            self.save_camera = SaveCameraThread(
                self.imagequeue_andor,
                self.saved_parameters,
                self.ScanExperiment,
                self.fileName,
                rid=artiq_rid  # <-- Add the new argument here 10/6/2025 by MZ
            )
            # Increase priority if you want to prioritize saving
            self.save_camera.start(priority=QThread.IdlePriority)
        else:
            print("ERROR: Image saving only available after running an acquisition")

    def onSettingsChanged(self):
        if self.acquiring_andor:
            if self.imaging_mode_andor == 'Live':
                self.onLive()
            elif self.imaging_mode_andor == 'TriggeredAcquisition':
                self.onAcquire()
            else:
                self.stop_acquisition_andor()

        print("Camera Settings Changed")

    def onCoolCCD(self):
        if self.actionCoolCCD.isChecked():
            camandor.start_cooling()
            # AndorTemperatureThread(self).start()
        else:
            camandor.stop_cooling()
            # AndorTemperatureThread(self).stop()

    # def onResetView(self):
    #     # data = self.view.getImageItem()
    #     if self.imaging_mode_andor == 'Live':
    #         self.stop_acquisition_andor()
    #         self.view.close()
    #         self.view = ImageView(self, name = "MainDisplay")
    #         self.setCentralWidget(self.view)
    #         self.view.setColorMap(self.colorMap)
    #         self.start_acquisition_andor()
    #
    #     # self.view.setImage(data)

    # def onClearQueue(self):
    #     self.imagequeue_andor = queue.Queue(self.CameraParameters['experiments'].value * len(self.ScanList))

    def close(self):
        self.actionCoolCCD.setChecked(False)
        self.onCoolCCD()
        self.stop_acquisition_andor()
        self.stop_acquisition_andor()
        self.tempThrd.running = False
        progWind = AndorShutdown(self.parent)
        progWind.show()
        progWind.setProgress(camandor.gettemperature() - 5, 0)

        while not self.tempThrd.isFinished():
            progWind.updateTemp(camandor.gettemperature())
            print('temp =', camandor.gettemperature())
            time.sleep(1)

        progWind.setShutdown()
        camandor.shutdown()
        progWind.close()
        self.temperUi.close()
        self.settingsUi.close()
        self.view.close()
        self.hide()

    def OnIdle(self, event):
        self.busy = 0

    # def OnSingleImageAcquiredAndor(self):
    #
    #     if event.img is not None:
    #         # cut image into halves
    #         img1 = event.img[:, :]
    #
    #         # avoid deadlock if too many images to process
    #         if self.Pending():
    #             self.busy += 1
    #         else:
    #             self.busy = 0
    #
    #         if self.busy > 3:
    #             print("I am busy, skip displaying")
    #             self.show_status_message('.')
    #         else:
    #             self.image1a.show_image(img1, description = "image #%d" % event.imgnr)

    def onLive(self):

        if self.actionLive.isChecked():
            # print("Live ON")
            self.stop_acquisition_andor()
            # self.timing_andor.set_live(True)
            self.imaging_mode_andor = "Live"
            camandor.andormode = self.imaging_mode_andor
            self.start_acquisition_andor()
        else:
            # print("Live OFF")
            self.stop_acquisition_andor()
            # self.timing_andor.set_live(False)
            # if self.actionLive.isChecked():
            #     self.displayImage(None)

    # In camera.py, inside the Camera class...

    def _apply_mode_settings(self, mode_name):
        """
        Reads parameters for a given mode from the JSON config, ensures the
        camera is idle, and then applies the new settings.
        """
        # --- START OF FIX for 20075 error ---
        camandor.stop()  # <-- IMPORTANT: Forcefully idle the camera.
        time.sleep(0.05)  # <-- IMPORTANT: Give the driver a moment to settle.
        # --- END OF FIX ---

        if not settings:
            print("ERROR: Configuration file not loaded. Cannot apply settings.")
            return

        if mode_name not in settings:
            print(f"ERROR: Mode '{mode_name}' not found in configuration file.")
            return

        print(f"Applying settings for mode: '{mode_name}'")

        # 1. Get the settings for the desired mode and the definitions
        mode_params = settings[mode_name]
        definitions = settings["definitions"]

        # 2. Look up the integer codes from the definitions
        trigger_code = definitions["TriggerModeCode"][mode_params["TriggerMode"]]
        read_code = definitions["ReadModeCode"][mode_params["ReadMode"]]
        acq_code = definitions["AcquisitionModeCode"][mode_params["AcquisitionMode"]]

        # 3. Get the other parameters directly
        exposure = mode_params["exposure_time_ms"]
        gain = mode_params["em_gain"]
        use_high_cap = mode_params["use_high_capacity"]
        em_adv = (mode_name == "ExternalTrigger")  # Assuming this logic for now



        # 5. Make a SINGLE call to the high-level set_timing function
        camandor.set_timing(
            integration=exposure,
            emgain=gain,
            triggerMode=trigger_code,
            readMode=read_code,
            acquisitionMode=acq_code,
            useHighCapacity=use_high_cap,
            emAdvancedEnabled=em_adv
        )

    def onAcquire(self):
        if self.actionAcquire.isChecked():
            print("Acquire mode ENABLED.")
            self.stop_acquisition_andor()
            self.actionLive.setChecked(False)
            self.actionLive.setEnabled(False)

            # --- START OF FIX ---

            # 1. Set the internal state to the name the program expects
            self.imaging_mode_andor = "TriggeredAcquisition"
            camandor.andormode = self.imaging_mode_andor

            # 2. Use the JSON key "ExternalTrigger" to apply the correct settings
            self._apply_mode_settings("ExternalTrigger")

            # --- END OF FIX ---

            # 3. Now start_acquisition_andor() will find the correct mode and launch the right thread
            self.start_acquisition_andor()

        else:
            print("Acquire mode DISABLED.")
            self.stop_acquisition_andor()
            self.actionLive.setEnabled(True)

    def onDetecter(self):
        self.stop_acquisition_andor()
        self.actionLive.setChecked(False)
        self.actionLive.setEnabled(False)
        # self.timing_andor.set_live(False)
        self.imaging_mode_andor = "Detecter"
        print('Detecting ROIs...')
        camandor.andormode = self.imaging_mode_andor
        detectThread = self.start_acquisition_andor()
        detectThread.finished.connect(self.stop_acquisition_andor)
        # consumeThrd.tableReady.connect(self.displayTable)

    def onDetecterWriteToFile(self, name):
        self.writeToFile = True
        self.ionFileName = name
        self.onDetecter()

    def onCounter(self):
        self.stop_acquisition_andor()
        self.actionLive.setChecked(False)
        self.actionLive.setEnabled(False)
        # self.timing_andor.set_live(False)
        self.imaging_mode_andor = "AutoLoad"
        print('Loading...')
        camandor.andormode = self.imaging_mode_andor
        self.start_acquisition_andor()

    def offCounter(self):
        self.stop_acquisition_andor()
        self.actionLive.setEnabled(True)

    def startThresholdCalibrator(self):
        self.stop_acquisition_andor()
        self.actionLive.setChecked(False)
        self.actionLive.setEnabled(False)
        # self.timing_andor.set_live(False)
        self.imaging_mode_andor = "Threshold"
        print('Calibrating Thresholds...')
        camandor.andormode = self.imaging_mode_andor
        self.imagequeue_andor = queue.Queue(5000 * len(self.ScanList))
        self.start_acquisition_andor()

    def stopThresholdCalibrator(self):
        self.stop_acquisition_andor()
        self.actionLive.setEnabled(True)

    # When Crop button is clicked, camera should only capture selected region; when unchecked, should capture everything
    def onCrop(self):
        if self.actionCrop_ROI.isChecked():
            pos = self.view.roi.pos()
            size = self.view.roi.size()
            leftBd = int(pos[1] + 1)
            rightBd = int(leftBd + size[1] - 1)
            highBd = int(pos[0] + 1)
            lowBd = int(highBd + size[0] - 1)
            camandor.setSize(1, 1, leftBd, rightBd, highBd, lowBd)
            # Resize and recenter perspective to cropped image
            self.autoResize = True
        else:
            camandor.setSize(1, 1, 1, camandor.frame_width(), 1, camandor.frame_height())

    def start_acquisition_andor(self):
        self.acquiring_andor = True
        print('Start Acquisition')

        # Clear out old data
        if self.imaging_mode_andor == "TriggeredAcquisition":
            self.camera_plot.clear()
            self.updateROIs(self.ROI_list)  # Generate new PlotCurveItems for the ROIs
            self.points_processed = 0
            self.ScanList = self.ScanExperiment.scanControlWidget.getScan().list

            numExp = int(self.CameraParameters['experiments'].value * len(self.ScanList))

            # Increases the number of experiments if cooling shot is checked or local cooling shot is checked
            if self.coolingShotComboBox.currentText() == "Global Cooling Shot":
                numExp += 1
            if self.coolingShotComboBox.currentText() == "Local Cooling Shot":
                numExp += len(self.ScanList)

            self.imagequeue_andor = queue.Queue(numExp)

            print('start_acquisition_andor: numExp = ', numExp)

        # Scan parameters, to be put in file header (NumExpts, ScanPoints, Global Variables, and Pulser Parameters)
        self.saved_parameters = {
            'experiments': int(self.CameraParameters['experiments'].value),
            'scanlist': copy.deepcopy((self.ScanList)),
            #'globalVariables': copy.deepcopy(self.globalVariables),
            #'pulserParameters': copy.deepcopy(self.pulserParameters)
        }


        if self.imaging_mode_andor == "Live":
            # print("In LIVE Mode")
            self.timing_andor.set_live(True)
            self.imgproducer_andor = AcquireThreadAndorLive(self, camandor, self.imagequeue_andor, None)
            self.imgproducer_andor.image_available.connect(self.displayImage)
            self.imgproducer_andor.no_camera.connect(self.stop_acquisition_andor)

        elif self.imaging_mode_andor == "TriggeredAcquisition" or self.imaging_mode_andor == 'Threshold':
            # print("In TRIGGERED ACQUISITION Mode")
            self.timing_andor.set_live(False)
            self.imgproducer_andor = AcquireThreadAndor(self, camandor, self.imagequeue_andor, numExp)
            self.imgproducer_andor.no_camera.connect(self.stop_acquisition_andor)
            self.imgproducer_andor.data_available.connect(self.processScanpointROIs)
            self.imgproducer_andor.finished.connect(self.stop_acquisition_andor)

            self.imgproducer_andor.acquisition_finished.connect(self.onSave) #10/7/2025 by MZ


        elif self.imaging_mode_andor == 'Detecter':
            self.timing_andor.set_live(False)
            self.imagequeue_andor = queue.Queue(6)
            self.imgproducer_andor = AcquireThreadAndorDetect(self, camandor, self.imagequeue_andor, 3)
            self.imgproducer_andor.no_camera.connect(self.stop_acquisition_andor)
            # self.imgproducer_andor.image_available.connect(self.displayImage)
            self.imgproducer_andor.finished.connect(self.calculateROIs)

        elif self.imaging_mode_andor == 'AutoLoad':
            self.timing_andor.set_live(True)
            self.imgproducer_andor = AcquireThreadAndorAutoLoad(self, camandor, self.imagequeue_andor)
            self.imgproducer_andor.no_camera.connect(self.stop_acquisition_andor)

        #Sets the priority for the live mode thread to the lowest priority
        if self.imaging_mode_andor == "Live":
            self.imgproducer_andor.start(priority=QThread.IdlePriority)
        else:
            self.imgproducer_andor.start()

        return self.imgproducer_andor

    def stop_acquisition_andor(self):
        self.ready = False
        if self.acquiring_andor:
            print('Stop Acquisition')
            print("The Imaging queue size is :", self.imagequeue_andor.qsize())

            if self.imgproducer_andor is not None:
                self.imgproducer_andor.stop()

            self.acquiring_andor = False
            self.imgproducer_andor = None

            """This if statement is responsible for autosave feature. It checks to see if enough points were 
            processed so that it can autosave. Currently set to one second."""
            if self.imaging_mode_andor == "TriggeredAcquisition" and self.actionAutoSave.isChecked():
                for _ in range(self.bufferTime):
                    if self.points_processed < len(self.saved_parameters['scanlist']):
                        time.sleep(0.001)
                if self.coolingShotComboBox.currentText() != "None":
                   if self.points_processed == len(self.saved_parameters['scanlist']):
                      self.onSave()
                   else:
                      print("Error autosaving (regular saving still might be functional)")
                    # print("PARAMETERS FOR AUTOSAVE:" + str(self.points_processed) + "other param" +
                    #       str(len(self.saved_parameters['scanlist'])))
                else:
                    if self.points_processed == len(self.saved_parameters['scanlist']):
                        self.onSave()
                    else:
                        print("Error autosaving (regular saving still might be functional)")

    # Replace old ROIs with provided list (called during auto-detection)
    def updateROIs(self, new_ROI_list):
        counter = 0
        for r in self.ROI_list:
            self.view.removeItem(r)
        self.ROI_list = new_ROI_list
        self.ROI_data = {}
        for r in self.ROI_list:
            self.view.addItem(r)
            for h in r.getHandles():
                r.removeHandle(0)
            r.translateSnap = True
            self.ROI_data[r] = []
            self.ROI_plots[r] = self.camera_plot.plot(pen=(counter, len(self.ROI_list)))
            #counter is the color controller (pyqt graph might allow for customization)
            # Coordinate color between graph and bounding box
            r.setPen(self.ROI_plots[r].opts['pen'])
            counter += 1

    # Get average ROI data over the experiments in a scanpoint
    def processScanpointROIs(self):
        # Pull correct slice from imagequeue
        start = self.saved_parameters['experiments']*self.points_processed
        end = start + self.saved_parameters['experiments']
        # Correct for initial cooling shot (if applicable)
        if self.coolingShotComboBox.currentText() == "Global Cooling Shot":
            start += 1
            end += 1
        # Correct for local cooling shots (if applicable)
        if self.coolingShotComboBox.currentText() == "Local Cooling Shot":
            start += self.points_processed+1
            end += self.points_processed+1

        images = list(itertools.islice(self.imagequeue_andor.queue, start, end))
        _image = np.mean(images, axis=0)  # Average value of each pixel over all the experiments
        # Add data
        for roi in self.ROI_list:
            p = roi.pos()
            px, py = int(p[0]), int(p[1])
            s = roi.size()
            sx, sy = int(s[0]), int(s[1])
            self.ROI_data[roi].append(np.mean(_image[px:px+sx, py:py+sy]))
        # Plot data
        for roi in self.ROI_list:
            self.ROI_plots[roi].setData([q.magnitude for q in self.saved_parameters['scanlist'][:len(self.ROI_data[roi])]],self.ROI_data[roi])
        self.points_processed += 1

    # Calculate new ROIs based on the images from the most recent acquisition
    def calculateROIs(self):
        IonDetectArray = []
        imageArray = []

        print("Processing...")

        # ionNumber = 0 => just remove ROIs
        if int(self.CameraParameters['ionNumber'].value) == 0:
            self.updateROIs([])
            self.actionLive.setEnabled(True)
            return

        while self.imagequeue_andor.qsize() > 0:
            try:
                img = self.imagequeue_andor.get(timeout=0)
                # self.message('Consuming')
            except queue.Empty: break
            else:
                img = img.astype(numpy.uint16)
                # print(img.shape)
                detector = IonDetection(img, int(self.CameraParameters['ionNumber'].value))
                IonDetectArray.append(detector)
                imageArray.append(img)

        analysisDict = {}
        for detector in IonDetectArray:
            detector.idIons()

            for i in range(len(IonDetectArray) - 1):
                for j in range(i + 1, len(IonDetectArray)):
                    dict_i = IonDetectArray[i].IonDict
                    dict_j = IonDetectArray[j].IonDict
                    matchingArray = []
                    for key_i in dict_i:
                        iCenter = dict_i[key_i].center
                        minDist = IonDetectArray[i].arr.shape[0]
                        minDistKey = None
                        for key_j in dict_j:
                            jCenter = dict_j[key_j].center
                            distSqr = (iCenter[0] - jCenter[0]) ** 2 + (iCenter[1] - jCenter[1]) ** 2
                            if distSqr < minDist:
                                minDist = distSqr
                                minDistKey = key_j
                        matchingArray.append((key_i, minDistKey, minDist))
                    analysisDict[str(i) + '_' + str(j)] = matchingArray

        for key in analysisDict:
            print(key, analysisDict[key], sep=" -> ")

        #Check that the ImageArray is not empty
        if imageArray==[]:
            print("No Image Detected")
            self.actionLive.setEnabled(True)
            return
        # average over all images
        for i in range(1, len(imageArray)):
            imageArray[0] = numpy.add(imageArray[0], imageArray[i])
        imageArray[0] = numpy.divide(imageArray[0], len(imageArray))

        detector = IonDetection(imageArray[0], int(self.CameraParameters['ionNumber'].value))
        detector.idIons() #THIS IS THE METHOD THAT GETS ALL THE DATA FOR IONS, METHOD IS IN IONDETECT CLASS
        self.detectedROI = detector
        if self.writeToFile is False:
            for key in IonDetectArray[0].IonDict:
                print(key, IonDetectArray[0].IonDict[key])
        else:
            filepath = os.path.join('Z:/Lab/Sandia Box Projects/IonPositions', self.ionFileName)
            if not os.path.exists('Z:/Lab/Sandia Box Projects/IonPositions'):
                os.makedirs('Z:/Lab/Sandia Box Projects/IonPositions')

            try:
                file = open(filepath, "a")
            except IOError:
                file = open(filepath, "w")

            file.write("{Timestamp:" + "[%s/%s/%s][%s:%s:%s]}\n" % (time.strftime("%Y"), time.strftime("%m"),
                                                 time.strftime("%d"), time.strftime("%H"),
                                                 time.strftime("%M"), time.strftime("%S")))
            file.write("{")
            length = len(IonDetectArray[0].IonDict) - 1
            for key in IonDetectArray[0].IonDict:
                try:
                    ionCoordinatesString = (str(IonDetectArray[0].IonDict[key]))
                    ionCoordinatesString = ionCoordinatesString[ionCoordinatesString.index("(") +
                                                              1:ionCoordinatesString.rindex(")")]
                    if IonDetectArray[0].IonDict.index(key) == length:
                        file.write("{" + ionCoordinatesString + "}")
                    else:
                        file.write("{" + ionCoordinatesString + "},\n")
                except:
                    file.write("Something went wrong. \n")
            file.write("}\n\n")

        ionTable = QtWidgets.QTableWidget(detector.numIons + 1, 5, self)
        ionTable.setItem(0, 0, QtWidgets.QTableWidgetItem("Ion Number"))
        ionTable.setItem(0, 1, QtWidgets.QTableWidgetItem("pos x"))
        ionTable.setItem(0, 2, QtWidgets.QTableWidgetItem("pos y"))
        ionTable.setItem(0, 3, QtWidgets.QTableWidgetItem("radius"))
        ionTable.setItem(0, 4, QtWidgets.QTableWidgetItem("ROI area"))
        row = 0

        for key in detector.IonDict:
            ion = detector.IonDict[key]
            row += 1
            ionTable.setItem(row, 0, QtWidgets.QTableWidgetItem(key))
            ionTable.setItem(row, 1, QtWidgets.QTableWidgetItem(str(ion.center[0])))
            ionTable.setItem(row, 2, QtWidgets.QTableWidgetItem(str(ion.center[1])))
            ionTable.setItem(row, 3, QtWidgets.QTableWidgetItem(str(ion.radius)))
            ionTable.setItem(row, 4, QtWidgets.QTableWidgetItem(str(ion.get_height() * ion.get_width())))

        # self.tableReady.emit(ionTable)
        self.actionLive.setEnabled(True)
        # self.detecterFinished.emit()
        self.updateROIs(list(detector.IonDict.values()))
        self.writeToFile = False
        print("Ions Detected")

    # In camera.py, inside the Camera class

    # In camera.py, inside the Camera class
    # 06/10/2025 by MZ
    # In camera.py, inside the Camera class

    def loadSettings(self):
        """Loads settings from user_settings.json and applies them to the GUI."""
        try:
            # First, check if the file is empty. If so, do nothing.
            if os.path.getsize('user_settings.json') == 0:
                print("user_settings.json is empty. Using default values.")
                return

            with open('user_settings.json', 'r') as f:
                loaded_settings = json.load(f)

            # ... (the rest of the function is the same) ...
            print("Loading settings from user_settings.json")
            for key, value in loaded_settings.items():
                if key in self.CameraParameters:
                    if isinstance(value, dict) and 'value' in value and 'unit' in value:
                        reconstructed_value = Q(value['value'], value['unit'])
                        self.CameraParameters[key].update(reconstructed_value)
                    else:
                        self.CameraParameters[key].update(value)
                else:
                    print(f"Warning: Setting '{key}' from file not found in current GUI.")
            print("Settings loaded successfully.")

        except FileNotFoundError:
            print("user_settings.json not found. Using default values.")
        except Exception as e:
            print(f"Error loading settings: {e}")

    # In camera.py, inside the Camera class

    # In camera.py, inside the Camera class

    # In camera.py, inside the Camera class

    def onSaveSettings(self, _=None):
        """Gathers current GUI parameters and saves them to a JSON file."""
        settings_to_save = {}
        for key, param in self.CameraParameters.items():
            value = param.value
            if isinstance(value, Q):
                # --- THIS IS THE FIX ---
                # Convert the .units object to a string using str()
                settings_to_save[key] = {'value': value.magnitude, 'unit': str(value.units)}
            else:
                settings_to_save[key] = value

        try:
            with open('user_settings.json', 'w') as f:
                json.dump(settings_to_save, f, indent=4)
            print(f"Auto-saved settings to user_settings.json at {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Error auto-saving settings: {e}")


    # def OnSaveImageAndor(self):
    #     print("save image")
    #     #imgA = self.image1a.imgview.get_camimage()
    #     #readsis.write_raw_image(settings.imagefile, imgA, True)
    #     #wx.PostEvent(self, StatusMessageEvent(data='s')

if __name__ == '__main__':

    camandor = Cam()
    camandor.open()
    camandor.set_timing(integration=100, repetition=0, ampgain=0, emgain=0)
    camandor.start_cooling()

    CameraGui = Camera('config', 'dbConnection', 'pulserHardware', 'globalVariablesUi', 'shutterUi', 'externalInstrumentObservable')
    Tthread = AndorTemperatureThread(CameraGui,camandor)
    Tthread.start()

    camandor.wait()
    img = camandor.roidata()

    print(img)
    camandor.close()