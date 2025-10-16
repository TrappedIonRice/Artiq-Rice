#!/usr/bin/python
# -*- coding: latin-1 -*-
"""High level interface to Andor iXon+ emCCD camera."""
from pyAndorSDK2 import atmcd, atmcd_errors
from pyAndorSDK2 import atmcd_codes as codes
import numpy
from ctypes import *
from time import *
import time
import os

# dllpath = os.path.join(os.path.dirname(__file__), '..', 'Camera/atmcd64d')
# print(dllpath)
# windll.LoadLibrary(dllpath)

# If no camera is connected, set DEBUG_MODE to True so that the program will create fake images
DEBUG_MODE = False


# hack to releas GIL during wait
# MVll = ctypes.windll.mvDeviceManager
# llWait = MVll.DMR_ImageRequestWaitFor
# llWait.argtypes = [ctypes.c_int,
# ctypes.c_int,
# ctypes.c_int,
# ctypes.POINTER(ctypes.c_int)]
# llWait.restype = ctypes.c_int

class NoCamError(Exception):
    def __init__(self):
        Exception.__init__(self, 'No Camera')


class CamTimeoutError(Exception):
    def __init__(self):
        super(CamTimeoutError, self).__init__(self, 'Timeout')


class TimeoutError(Exception):
    def __init__(self):
        Exception.__init__(self, 'Timeout')


class Cam(object):

    def __init__(self, ConfigGroup):
        self.sdk = atmcd()
        self.AndorMode = 'Live'

        self.width = 512
        self.height = 512
        self.ImageNumber = 0
        self.ConfigGroup = ConfigGroup
        self.AndorConfig = self.ConfigGroup['Live']
        self.ROI = dict()
        self.TimeOut = 2000
        self.effHeight = 0
        self.effWidth = 0

    def Link(self):
        ret = self.sdk.Initialize("")
        if ret == atmcd_errors.Error_Codes.DRV_SUCCESS:
            self.error = False
            print("Andor initialized")
            print('Andor camera s/n:', self.sdk.GetCameraSerialNumber())
            (ret, self.width, self.height) = self.sdk.GetDetector()
        else:
            self.error = True
            print("Andor not available Cam")
    def open(self):
        print('Andor open')

        self.sdk.SetFrameTransferMode(0)
        self.sdk.SetHSSpeed(0, 0)

        (ret, index, speed) = self.sdk.GetFastestRecommendedVSSpeed()

        valid = self.sdk.SetVSSpeed(index)
        if valid == 20002:
            print("successful SetVSSpeed")
        else:
            print('SetVSSpeed = ', valid)

        (ret, VSSpeed) = self.sdk.GetVSSpeed(index)
        self.sdk.SetVSAmplitude(0)

        print('{index, speed, VSpeed}:', index, ',', speed, ',', VSSpeed)
        return self

    def close(self):
        print('Andor close')

    def shutdown(self):
        self.sdk.ShutDown()
        print('Andor shutdown')

    def stop(self):
        print('Andor stop')
        self.sdk.AbortAcquisition()
        # self.sdk.SetShutter(0, 1, 0, 0) # 0 Low=open, 1 shutter to be permanently open

    def GetTemperature(self):
        """Get temperature of CCD"""
        (ret, tep) = self.sdk.GetTemperature()
        return tep

    # def wait(self, timeout = 10):
    #     """Check if new image is available, and waits for specified time. Raises CamTimeoutError if no new image
    #     available."""
    #
    #     time.sleep(timeout)  # --------------------------------#
    #     status = c_int()
    #     currentnumberimages = c_int()
    #     self.sdk.GetTotalNumberImagesAcquired(byref(currentnumberimages))
    #     print("currentnumberimages = ", currentnumberimages.value)
    #
    #     if self.AndorMode == 'Live' or self.AndorMode == 'AutoLoad':
    #         if currentnumberimages.value != self.ImageNumber:
    #             print('Image #', currentnumberimages.value)
    #             self.ImageNumber = currentnumberimages.value
    #         else:
    #             raise CamTimeoutError
    #     if self.AndorMode == 'TriggeredAcquisition_1':
    #         self.sdk.GetStatus(byref(status))
    #         print("status = ", status.value)
    #         if status.value == 20073:
    #             self.ImageNumber = currentnumberimages.value
    #         else:
    #             raise CamTimeoutError

    def start_cooling(self, setPoint=-60):
        # tmin = c_int()
        # tmax = c_int()
        # self.sdk.GetTemperatureRange(byref(tmin), byref(tmax))
        # self.sdk.SetTemperature(tmin.value)
        self.sdk.SetTemperature(setPoint)
        self.sdk.CoolerON()
        print("Andor start cooling, set target temperature {}".format(setPoint))
        # print('  set min temp = ', tmin.value)

    def stop_cooling(self):
        self.sdk.CoolerOFF()
        print("Andor stop cooling")
        print("temp = ", self.GetTemperature())

    def frame_height(self):
        (xsize, ysize) = self.sdk.GetDetector()
        return ysize

    def frame_width(self):
        (xsize, ysize) = self.sdk.GetDetector()
        return ysize

    def Configure(self, configuration, onCrop = False):
        if configuration != self.AndorMode:
            self.AndorMode = configuration
            self.AndorConfig = self.ConfigGroup.get(self.AndorMode)
        print(self.ConfigGroup)
        print(self.ConfigGroup[configuration])
        config = self.AndorConfig
        print(config)
        self.sdk.SetTriggerMode(config["TriggerMode"])
        self.sdk.SetAcquisitionMode(config["AcquisitionMode"])
        self.sdk.SetReadMode(config["ReadMode"])
        self.sdk.SetHighCapacity(config["UseHighCapacity"])

        if config["TriggerMode"] == codes.Trigger_Mode.INTERNAL \
                or config["TriggerMode"] == codes.Trigger_Mode.EXTERNAL \
                or config["TriggerMode"] == codes.Trigger_Mode.EXTERNAL_START:
            self.sdk.SetExposureTime(config["ExposureTime"] / 1000)

        if config["AcquisitionMode"] == codes.Acquisition_Mode.KINETICS \
                or config["AcquisitionMode"] == codes.Acquisition_Mode.FAST_KINETICS:
            self.sdk.SetNumberKinetics(config["TotalShots"])
            self.sdk.SetKineticCycleTime(config["CycleTime"] / 1000)

        if config["AcquisitionMode"] == codes.Acquisition_Mode.ACCUMULATE \
                or config["AcquisitionMode"] == codes.Acquisition_Mode.KINETICS:
            self.sdk.SetNumberAccumulations(config["Accumulation"])

        if config['UseROI']:
            if onCrop:
                ROI = self.ROI
            else:
                ROI = config["ROI"]
            self.sdk.SetImage(1, 1, ROI["H1"], ROI["H2"], ROI["V1"], ROI["V2"])
            self.effWidth = ROI['V2'] - ROI['V1'] + 1
            self.effHeight = ROI['H2'] - ROI['H1'] + 1
            self.ROI = ROI
        else:
            self.sdk.SetImage(1, 1, 1, 512, 1, 512)
            self.effWidth = 512
            self.effHeight = 512
            self.ROI = {'H1': 1, 'H2': 512, 'V1': 1, 'V2': 512}
        self.sdk.SetEMGainMode(3)
        if config["EMCCDGain"] >= 300:
            self.sdk.SetEMAdvanced(1)

        self.sdk.SetEMCCDGain(config["EMCCDGain"])

    # def set_timing(self, integration=100, repetition=0, ampgain=0, emgain=0, numExp=1, numScan=1, emgainAdv=0):
    #     print('Andor Imaging mode: ', self.AndorMode)
    #     fakeim = 50 if DEBUG_MODE else 0
    #     # ==============================In normal operation set fakeim=0, just for debugging====================================
    #
    #     # 0 internal 1 external 7 external exposure 10 software trigger
    #     self.width = self.frame_width() + fakeim
    #     self.height = self.frame_height() + fakeim
    #     if self.width <= 0 or self.height <= 0:
    #         raise NoCamError
    #     triggerMode = None
    #     acquisitionMode = None
    #     hBin = 1
    #     vBin = 1
    #     hTrim = 0
    #     vTrim = 0
    #
    #     repetition = 0
    #     emGainUse = 0
    #     emAdvMode = 0
    #     highcapacity = 0
    #     if self.AndorMode == 'FastKinetics':
    #         print('Setting camera parameters for fast kinetics.')
    #         # self.width = self.frame_width() + fakeim
    #         # self.height = self.frame_height() + fakeim
    #         # self.sdk.SetAcquisitionMode(4)  # 1 single mode 2 accumulate mode 5 run till abort
    #         # self.sdk.SetFastKinetics(501,2,c_float(3.0e-3),4,1,1)
    #         acquisitionMode = 4
    #         triggerMode = 0
    #         emGainUse = emgain
    #         emAdvMode = 0
    #
    #         self.sdk.SetFastKinetics(501, 2, c_float(integration * 1.0e-3), 4, 1, 1)
    #     elif self.AndorMode == 'Live' or self.AndorMode == 'AutoLoad':
    #         print('Setting camera parameters for live mode.')
    #         # self.width = self.frame_width() + fakeim
    #         # self.height = self.frame_height() + fakeim
    #         # self.sdk.SetAcquisitionMode(5)  # 1 single mode 2 accumulate mode 5 run till abort
    #         acquisitionMode = 5
    #         triggerMode = 0
    #         self.sdk.SetTriggerMode(triggerMode)
    #         self.sdk.SetAcquisitionMode(acquisitionMode)
    #
    #         emGainUse = emgain
    #         emAdvMode = 0
    #
    #         # self.sdk.SetEMAdvanced(0)
    #
    #     elif self.AndorMode == 'TriggeredAcquisition':
    #         print('Setting camera parameters for Triggered Acquisition mode')
    #         print('Andor.set_timing: numExp = ', numExp)
    #         # self.sdk.SetAcquisitionMode(5)  # 1 single mode 2 accumulate mode 5 run till abort
    #         acquisitionMode = 3
    #         triggerMode = 7
    #         print("triggerMode = ", triggerMode)
    #         self.sdk.SetTriggerMode(triggerMode)
    #         self.sdk.SetAcquisitionMode(acquisitionMode)
    #
    #         valid = self.sdk.SetNumberKinetics(numExp)
    #         if valid == 20002:
    #             print("successful SetNumberKinetics")
    #         else:
    #             print('SetNumberKinetics = ', valid)
    #
    #         valid = self.sdk.SetNumberAccumulations(1)
    #         if valid == 20002:
    #             print("successful SetNumberAccumulations")
    #         else:
    #             print('SetNumberAccumulations = ', valid)
    #
    #         emGainUse = emgainAdv
    #         emAdvMode = 1
    #         highcapacity = 1
    #
    #     elif self.AndorMode == 'Detecter':
    #         print('Setting camera parameters for Detecter Acquisition mode')
    #         print('Andor.set_timing: numExp = ', numExp)
    #         # self.sdk.SetAcquisitionMode(5)  # 1 single mode 2 accumulate mode 5 run till abort
    #         acquisitionMode = 3
    #         triggerMode = 0
    #         print("triggerMode = ", triggerMode)
    #         self.sdk.SetTriggerMode(triggerMode)
    #         self.sdk.SetAcquisitionMode(acquisitionMode)
    #
    #         valid = self.sdk.SetNumberKinetics(numExp)
    #         if valid == 20002:
    #             print("successful SetNumberKinetics")
    #         else:
    #             print('SetNumberKinetics = ', valid)
    #
    #         valid = self.sdk.SetNumberAccumulations(1)
    #         if valid == 20002:
    #             print("successful SetNumberAccumulations")
    #         else:
    #             print('SetNumberAccumulations = ', valid)
    #         # self.sdk.SetEMAdvanced(0)
    #
    #         # print('Set FTCCD Code:', self.sdk.SetFrameTransferMode(1))
    #
    #         emGainUse = emgain
    #         emAdvMode = 0
    #
    #
    #     else:
    #         acquisitionMode = 5
    #         triggerMode = 0
    #
    #     print('Andor set timings:')
    #     print('  set exposure time =', integration, 'ms')
    #     print('  set repetition time =', repetition, 'ms')
    #
    #     cExp = c_float(integration * 1.0e-3)
    #     self.sdk.SetExposureTime(cExp)
    #
    #     print('SetImg Code:', self.sdk.SetImage(hBin, vBin,
    #                                             self.hStart, self.hEnd,
    #                                             self.vStart, self.vEnd))
    #     # print('SetImg Code:', self.sdk.SetImage(hBin, vBin, hStart, hEnd, vStart, vEnd))
    #     self.effWidth = self.hEnd - self.hStart + 1
    #     self.effHeight = self.vEnd - self.vStart + 1
    #     # self.effWidth = self.width
    #     # self.effHeight = self.height
    #     # self.effHeight = 8
    #
    #     # print('SetCrop Code:', self.sdk.SetIsolatedCropMode(1, 64, 512, 8, 1))
    #     # print('SetCrop Code:', self.sdk.SetIsolatedCropModeEx(1, 64, 496, 8, 1, 224, 8))
    #     # self.effHeight = int(self.height/64)
    #     # self.effWidth = 496
    #
    #     readexposure = c_float()
    #     readaccumulate = c_float()
    #     readkinetic = c_float()
    #     readouttime = c_float()
    #     self.sdk.GetAcquisitionTimings(byref(readexposure), byref(readaccumulate), byref(readkinetic))
    #     print('ReadOut Code:', self.sdk.GetReadOutTime(byref(readouttime)))
    #
    #     print('Andor read timings:')
    #     print('  read exposure time =', readexposure.value * 1000, 'ms')
    #     print('  read accumulate time =', readaccumulate.value * 1000, 'ms')
    #     print('  read kinetic time =', readkinetic.value * 1000, 'ms')
    #     print('  read readoutMax time =', readouttime.value * 1000, 'ms')
    #     print('Andor image size:', self.effWidth, 'x', self.effHeight)
    #
    #     gainvalue = c_float()
    #     self.sdk.GetPreAmpGain(ampgain, byref(gainvalue))
    #     print('Andor preamp gain #%d' % ampgain, '=', gainvalue.value)
    #     self.sdk.SetPreAmpGain(ampgain)
    #
    #     if emAdvMode == 1:
    #         print("EMAdvanced = On")
    #     else:
    #         print("EMAdvanced = Off")
    #     print('Andor EM gain = ', emGainUse, 'emAdvMode = ', emAdvMode)
    #
    #     self.sdk.SetEMGainMode(3)  # Real EM Gain
    #
    #     valid = self.sdk.SetEMAdvanced(emAdvMode)  # 0 for off, 1 for on
    #     if valid == 20002:
    #         print("SetEMAdvanced ok")
    #     else:
    #         print("SetEMAdvanced error = ", valid)
    #
    #     valid = self.sdk.SetEMCCDGain(emGainUse)  # accept values 0-300
    #     if valid == 20002:
    #         print("SetEMCCDGain ok")
    #     else:
    #         print("SetEMCCDGain error = ", valid)
    #
    #     valid = self.sdk.SetHighCapacity(highcapacity)  # accept values 0-300
    #     if valid == 20002:
    #         print("SetHighCapacity ok")
    #     else:
    #         print("SetHighCapacity error = ", valid)

    def start_acquisition(self):
        acq = self.sdk.StartAcquisition()
        if acq == 20002:
            print('Acquisition started successfully')
        else:
            print("Acquisition error = ", acq)
        self.ImageNumber = 0

    def stop_acquisition(self):
        (ret, self.ImageNumber) = self.sdk.GetTotalNumberImagesAcquired()
        acq = self.sdk.AbortAcquisition()
        if acq == 20002:
            print('Acquisition Aborted successfully')
        else:
            print("error = ", acq)

    def get_status(self):
        numImg = self.sdk.GetTotalNumberImagesAcquired()
        return str((self.sdk.GetStatus(), numImg))

    def get_num_newImgs(self):

        (startIdx, stopIdx) = self.sdk.GetNumberNewImages()
        value = stopIdx - startIdx
        return value

    def retrieveData(self):
        if DEBUG_MODE:
            img = numpy.zeros((self.effHeight, self.effWidth))
            self.imgoutRandModifier_IonSim(img)
            return img

        imgsize = (self.effHeight * self.effWidth)

        ret = self.sdk.WaitForAcquisitionTimeOut(self.TimeOut)

        if ret == atmcd_errors.Error_Codes.DRV_NO_NEW_DATA:
            raise CamTimeoutError
        else:
            (ret, img) = self.sdk.GetMostRecentImage16(imgsize)
            img = numpy.reshape(img, (self.effHeight, self.effWidth))
            return img

    # def roidata(self):
    #     if self.effHeight <= 0 or self.effWidth <= 0:
    #         raise NoCamError()
    #
    #     starttime = time.time()
    #
    #     if self.AndorMode == 'Live' or self.AndorMode == 'AutoLoad':
    #         # print('Retrieving image: ', self.effWidth, 'x', self.effHeight, self.AndorMode)
    #         imgtype = c_long * (self.effWidth * self.effHeight)
    #         img = imgtype()
    #         valid = self.sdk.GetMostRecentImage(img, c_long(self.effWidth * self.effHeight))
    #         if valid == 20024: raise CamTimeoutError
    #         # self.sdk.GetOldestImage(img, c_long(self.effWidth * self.effHeight))
    #         imgout = numpy.ctypeslib.as_array(img)
    #         imgout = numpy.reshape(imgout, (self.effHeight, self.effWidth))
    #     elif self.AndorMode == 'TriggeredAcquisition':
    #         imgtype = c_long * (self.effWidth * self.effHeight)
    #         img = imgtype()
    #         valid = self.sdk.GetOldestImage(img, c_long(self.effWidth * self.effHeight))
    #         if valid == 20024: raise CamTimeoutError
    #         # print('Retrieving image: ', self.effWidth, 'x', self.effHeight, self.AndorMode)
    #         imgout = numpy.ctypeslib.as_array(img)
    #         imgout = numpy.reshape(imgout, (self.effHeight, self.effWidth))
    #     elif self.AndorMode == 'Detecter':
    #         imgtype = c_long * (self.effWidth * self.effHeight)
    #         img = imgtype()
    #         valid = self.sdk.GetOldestImage(img, c_long(self.effWidth * self.effHeight))
    #         if valid == 20024: raise CamTimeoutError
    #         # print('Retrieving image: ', self.effWidth, 'x', self.effHeight, self.AndorMode)
    #         imgout = numpy.ctypeslib.as_array(img)
    #         imgout = numpy.reshape(imgout, (self.effHeight, self.effWidth))
    #     elif self.AndorMode == 'FastKinetics':
    #         # print('Retrieving images: ', self.effWidth, 'x', self.effHeight, self.AndorMode)
    #         imgtype = c_long * (self.effWidth * self.effHeight)
    #         img = imgtype()
    #         self.sdk.GetAcquiredData(img, c_long(self.effWidth * self.effHeight))
    #         imgout = numpy.ctypeslib.as_array(img)
    #         imgout = numpy.reshape(imgout, (self.effHeight, self.effWidth))
    #         self.sdk.StartAcquisition()
    #
    #     endtime = time.time()
    #     # print('  readout time = ', endtime - starttime, ' s')
    #     if DEBUG_MODE: self.imgoutRandModifier_IonSim(imgout)
    #     return imgout

    def setCrop(self, hBin, vBin, hStart, hEnd, vStart, vEnd):
        print('Changing ROI to {h} x {w} * {b}'.format(h=hEnd - hStart + 1, w=vEnd - vStart + 1, b=(hBin, vBin)))
        # Save settings
        ROI = {"H1": hStart, "H2": hEnd, "V1": vStart, "V2": vEnd}
        self.ROI = ROI
        # Compensate for "frame_width() == 0"
        # if DEBUG_MODE:
        #     if not self.hEnd:
        #         self.hEnd = 512
        #         self.vEnd = 512

    def imgoutRandModifier(self, imgout):

        effHeight, effWidth = imgout.shape[0], imgout.shape[1]
        for i in range(effHeight):
            for j in range(effWidth):
                imgout[i][j] = imgout[i][j] + numpy.random.randint(0, 2) if self.hStart <= i + 1 < self.hEnd and \
                                                                            self.vStart <= j + 1 < self.vEnd else 0

                # if __name__ == '__main__':
                # cam = Cam()
                # cam.open()
                # cam.start_cooling()
                # print(cam.gettemperature())
                # time.sleep(5)
                # print(cam.gettemperature())
                # cam.wait()
                # img = cam.roidata()
                # print()
                # cam.close()

    # Simulates camera data more accurately -- brightness clustered around several 'ions'
    def imgoutRandModifier_IonSim(self, imgout):
        ionList = [(25, i) for i in range(10, 80, 5)]  # Sample ion chain, change as needed

        effHeight, effWidth = imgout.shape[0], imgout.shape[1]
        sampling = 10  # Higher sampling -> lower variances, smoother contrast
        h1 = self.ROI['H1']
        h2 = self.ROI['H2']
        v1 = self.ROI['V1']
        v2 = self.ROI['V2']

        sleep(0.001)

        # L_2 norm of 2 points
        def dist(u, v):
            return (numpy.abs(u[0] - v[0]) ** 2 + numpy.abs(u[1] - v[1]) ** 2) ** 0.5

        # inv prop to max dist from ions
        def prob(x, y):
            return 1 / max(min([dist((x, y), ion) for ion in ionList]), 1)

        for i in range(effHeight):
            for j in range(effWidth):
                if h1 <= i + 1 < h2 and v1 <= j + 1 < v2:
                    imgout[i][j] = j* numpy.random.binomial(sampling, prob(i, j))
                else:
                    imgout[i][j] = 0
