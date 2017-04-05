# -*- coding: utf-8 -*-
"""
Created on Fri Nov 18 10:12:40 2016

@author: Hubertus Bromberger
Very good example for ctypes to found here:
https://gist.github.com/nzjrs/990493

Program was only tested with  greateyes GE 2048 512BI UV1
should in principle work for all other greateys cameras
"""

import sys
from ctypes import *
import time

from guidata.qt.QtGui import (QSplitter, QComboBox, QGridLayout, QLineEdit,
                              QIntValidator, QWidget, QPushButton,
                              QSpinBox, QLabel, QMessageBox, QCheckBox,
                              QFileDialog, QPlainTextEdit)
from guidata.qt.QtCore import (QThread, Signal, QMutex, QMutexLocker, )


from Helpers.genericthread import GenericWorker


class GreatEyesUi(QSplitter):
    '''
    Handling user interface to manage greateys cameras
    '''
    newPlotData = Signal(object)
    def __init__(self, parent):
        super().__init__(parent)

        self.camera = None
        self.directory = 'H:'

        layoutWidget = QWidget()
        layout = QGridLayout()
        layoutWidget.setLayout(layout)

        ###############
        # GUI elements
        self.openCamBtn = QPushButton('Connect camera')
        self.readoutSpeedCombo = QComboBox()
        # this really should not be hard coded but received from dll
        self.readoutSpeedCombo.addItems(["1 MHz", 
            "1.8 MHz",
            "2.3 MHz",
            "2.8 MHz",
            "250 kHz",
            "500 kHz"])
        self.exposureTimeEdit = QLineEdit()
        self.exposureTimeEdit.setText('1000') # default exposure 1s
        self.exposureTimeEdit.setValidator(QIntValidator(1, 2**31)) # ms
        self.binningXCombo = QComboBox()
        self.binningXCombo.addItems(["No binning",
                  "Binning of 2 columns",
                  "Binning of 4 columns",
                  "Binning of 8 columns",
                  "Binning of 16 columns",
                  "Binning of 32 columns",
                  "Binning of 64 columns",
                  "Binning of 128 columns",
                  "Full horizontal binning"])
        self.binningYCombo = QComboBox()
        self.binningYCombo.addItems(["No binning",
                  "Binning of 2 lines",
                  "Binning of 4 lines",
                  "Binning of 8 lines",
                  "Binning of 16 lines",
                  "Binning of 32 lines",
                  "Binning of 64 lines",
                  "Binning of 128 lines",
                  "Binning of 256 lines"])
        self.temperatureEdit = QLineEdit()
        self.temperatureEdit.setText("-10")
        self.temperatureEdit.setValidator(QIntValidator(-100, 20))
        self.updateInterEdit = QLineEdit()
        self.updateInterEdit.setText("2")
        self.updateInterEdit.setValidator(QIntValidator(1, 3600))
        self.loi = QSpinBox()
        self.loi.setRange(1, 511) # one pixel less as the camera has
        self.deltaPixels = QSpinBox()
        self.deltaPixels.setRange(0, 256)
        self.autoSave = QCheckBox("Auto save")
        self.getDirectory = QPushButton('Choose Dir')
        self.dirPath = QLineEdit(self.directory)
        self.comment = QPlainTextEdit()

        ##############
        # put elements in layout
        layout.addWidget(self.openCamBtn, 0, 1)
        layout.addWidget(QLabel('readout speed'), 1, 0)
        layout.addWidget(self.readoutSpeedCombo, 1, 1)
        layout.addWidget(QLabel('exposure time (ms)'), 2, 0)
        layout.addWidget(self.exposureTimeEdit, 2, 1)
        layout.addWidget(QLabel('binning X'), 3, 0)
        layout.addWidget(self.binningXCombo, 3, 1)
        layout.addWidget(QLabel('binning Y'), 4, 0)
        layout.addWidget(self.binningYCombo, 4, 1)
        layout.addWidget(QLabel('temperature (°C)'), 5, 0)
        layout.addWidget(self.temperatureEdit, 5, 1)
        layout.addWidget(QLabel('update every n-seconds'), 6, 0)
        layout.addWidget(self.updateInterEdit, 6, 1)
        layout.addWidget(QLabel('Pixel of interest'), 7, 0)
        layout.addWidget(self.loi, 7, 1)
        layout.addWidget(QLabel('Δ pixels'), 8, 0)
        layout.addWidget(self.deltaPixels, 8, 1)
        layout.addWidget(self.autoSave, 9, 1)
        layout.addWidget(self.getDirectory, 10, 0)
        layout.addWidget(self.dirPath, 10, 1)
        layout.addWidget(QLabel('Comment:'), 11, 0)
        layout.addWidget(self.comment, 12, 0, 1, 2)
        layout.setRowStretch(13, 10)

        self.addWidget(layoutWidget)


        #################
        # connect elements for functionality
        self.openCamBtn.released.connect(self.__openCam)
        self.getDirectory.released.connect(self.__chooseDir)
        
        ################
        # thread for updating position
        self.currImage_thread = QThread() # create the QThread
        self.currImage_thread.start()

        # This causes my_worker.run() to eventually execute in my_thread:
        self.currImage_worker = GenericWorker(self.__getCurrImage)
        self.currImage_worker.moveToThread(self.currImage_thread)
       


    def __openCam(self):
        self.camera = greatEyes()
        if not self.camera.connected:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText('Sorry, could not connect to camera :(\n' + 
                    self.camera.status)
            msg.exec_()
            #return
        self.openCamBtn.setText('Camera connected')
        self.openCamBtn.setStyleSheet('QPushButton {color: green;}')

        self.readoutSpeedCombo.setEnabled(False)
        self.exposureTimeEdit.setEnabled(False)
        self.exposureTimeEdit.setEnabled(False)
        self.binningXCombo.setEnabled(False)
        self.binningYCombo.setEnabled(False)
        self.temperatureEdit.setEnabled(False)
        self.updateInterEdit.setEnabled(False)

        # start aquisition
        self.__startCurrImageThr()

    def __chooseDir(self):
        self.directory = QFileDialog.getExistingDirectory(self,
                "Choose directory",
                self.directory)
        self.dirPath.setText(self.directory)
        print(self.directory)


    def __startCurrImageThr(self):
        #self.stopCurrPosThr = False
        self.currImage_worker.start.emit()
    def __stopCurrImageThr(self):
        pass
        #self.stopCurrPosThr = True
        #while(self.currPosThr.isRunning()):
        #    time.sleep(0.03)
    def __getCurrImage(self):
        from scipy import mgrid
        import numpy as np
        X, Y = mgrid[-256:256, -1024:1025]
        while True:
            z = np.exp(-0.5*(X**2+Y**2)/np.random.uniform(30000, 40000))*np.cos(0.1*X+0.1*Y) 
            self.newPlotData.emit(z)
            time.sleep(int(self.updateInterEdit.text()))



class greatEyes:
    def __init__(self, readoutSpeed=0, exposureTime=1e3, binningX=0, binningY=0):
        # load dll
        self.greateyesLib = WinDLL('greateyes.dll')
        self.tempCalibNumber = 42223# you get this number via software, camera info
        
        # get set by setCameraParameters()
        self.numPixelInX = 0
        self.numPixelInY = 0
        self.pixelSize = 0
        self.connected = False
        self.status = ""

        if not self.connectCamera():
            return None
        if not self.setCameraParameter(readoutSpeed, exposureTime, 
                           binningX, binningY):
            return None
        
        self.connected = True
        # Set temperture
        self.initTempControl()
        self.setTemperture()
        print('Current temperature {:d}°C'.format(self.getTemperature()))
        
        
    def getDummyImage(self):
        return np.random.random((10,10))

    def checkSDKVersion(self):
        ###
        # check SDK version
        # only get first number, probably needs iterating through char array...
        func = self.greateyesLib.GetDLLVersion
        func.restype = POINTER(c_char)
        func.argtypes = [POINTER(c_int)]
        l = c_int()
        data = func(byref(l))
        print(data,l,data.contents)

    def connectCamera(self):
        ###
        # connect camera
        getCamera = self.greateyesLib.CheckCamera
        getCamera.retype = c_bool
        getCamera.argtypes = [POINTER(c_int), POINTER(POINTER(c_char)), POINTER(c_int)]
        modelId   = c_int()
        model     = POINTER(c_char)()
        statusMsg = c_int()
        status = {6: 'New camera detected',
                  0: 'Camera OK and connected',
                  1: 'No camera connected',
                  2: 'Could not open USBDevice',
                  3: 'WriteConfigTable failes',
                  4: 'WriteReadRequest failed',
                  7: 'Unknown ModelID'}
        if getCamera(byref(modelId), byref(model), byref(statusMsg)):
            #print(modelId, model.contents, statusMsg)
            print(status[int(statusMsg.value)])
            self.status = status[int(statusMsg.value)]
            return True
        else:
            print(status[int(statusMsg.value)])
            self.status = status[int(statusMsg.value)]
            return False

    def setCameraParameter(self, readoutSpeed, exposureTime, 
                           binningX, binningY):
        ###
        # set camera parameters
        camSettings = self.greateyesLib.CamSettings
        camSettings.retype = c_bool
        camSettings.argtypes = [c_int, c_int, c_int, c_int, 
                                POINTER(c_int), POINTER(c_int),
                                POINTER(c_int), POINTER(c_int),
                                c_int]
        readSpeed = c_int(int(readoutSpeed))
        exposure  = c_int(int(exposureTime))
        binningX     = c_int(int(0))
        binningY     = c_int(int(0))
        numPixelInX  = c_int()
        numPixelInY  = c_int()
        pixelSize    = c_int()
        statusMsg    = c_int()
        addr         = c_int(0)
        status = {0: 'Camera OK and connected',
                  3: 'WriteConfigTable failes',
                  7: 'Unknown ModelID',
                  8: 'Out of range'}
        if camSettings(readSpeed, exposure, binningX, binningY, 
                                 byref(numPixelInX), byref(numPixelInY),
                                 byref(pixelSize), byref(statusMsg), addr):
            print('Set camera parameters status:', status[int(statusMsg.value)])
            self.numPixelInX = int(numPixelInX.value)
            self.numPixelInY = int(numPixelInY.value)
            self.pixelSize = int(pixelSize.value)
            return True
        else:
            print('Set camera parameters status:', status[int(statusMsg.value)])
            return False
        
        
    def initTempControl(self):
        ###
        # initialize temperature control
        tempertureControlSetup = self.greateyesLib.TemperatureControl_Setup
        tempertureControlSetup.retypes  = c_int
        tempertureControlSetup.argtypes = [c_int, POINTER(c_int), c_int]
        coolingOption = c_int(self.tempCalibNumber) 
        statusMsg     = c_int()
        tempLevels = tempertureControlSetup(coolingOption, byref(statusMsg), c_int(0))
        print('Number of cooling levels:', tempLevels)

    def setTemperture(self, setTemp=-9):
        ###
        # set cooling level
        setTemperatureControl = self.greateyesLib.TemperatureControl_SetTemperatureLevel
        setTemperatureControl.retypes = c_bool
        setTemperatureControl.argtypes = [c_int, POINTER(c_int), c_int]
        statusMsg = c_int()
        #[20, 15, 10, 5, 0, -5, -10, -15, -20, -25, -30,... -100]
        tempList = np.arange(20, -101, -5) # available tempertures I extracted from greatVision sw
        tempIndex = tempList.shape[0]-tempList[::-1].searchsorted(setTemp)
        print(u'Setting temperature to {:d}°C'.format(tempList[tempIndex]))
        if setTemperatureControl(c_int(tempIndex), byref(statusMsg), c_int(0)):
            print('Camera temperature controller is set')
        else:
            print('An error occured in setting the temperature')

    def getTemperature(self):
        ###
        # Get Temperature from Chip
        getTemperature = self.greateyesLib.TemperatureControl_GetTemperature
        getTemperature.retype = c_bool
        getTemperature.argtypes = [c_int, POINTER(c_int), POINTER(c_int), c_int]
        temperature = c_int()
        statusMsg   = c_int()
        if getTemperature(c_int(0), byref(temperature), byref(statusMsg), c_int(0)):
            return temperature.value
        #getTemperatureBool = getTemperature(c_int(1), byref(temperature), byref(statusMsg), c_int(0))
        #print("backside temperature:", temperature.value)

    def getImage(self):
        ###
        # Get image
        getImage = self.greateyesLib.PerformMeasurement_Blocking
        getImage.retype   = c_bool
        getImage.argtypes = [c_bool, c_bool, c_bool, c_bool, c_int, 
                             POINTER(c_ushort), POINTER(c_int), POINTER(c_int),
                             POINTER(c_int), c_int]
        correctBias = c_bool()
        showSync    = c_bool()
        showShutter = c_bool()
        triggerMode = c_bool()
        triggerTimeout = c_int()
        # http://stackoverflow.com/questions/13553353/python-handling-c-malloc-variables-with-ctypes
        dll = CDLL('msvcrt')
        n = dll.malloc(self.numPixelInX * self.numPixelInY * sizeof(c_short))
        pIndataStart   = cast(n, POINTER(c_ushort))
        writeBytes  = c_int()
        readBytes   = c_int()
        statusMsg   = c_int()
        addr        = c_int(0)
        getImageBool = getImage(correctBias, showSync, showShutter, triggerMode, triggerTimeout,
                                pIndataStart, byref(writeBytes), byref(readBytes),
                                byref(statusMsg), addr)
        imageData = np.array(np.ones(self.numPixelInX * self.numPixelInY), dtype=np.short)
        for i in range(self.numPixelInX * self.numPixelInY):
            imageData[i] = pIndataStart[i]
        return imageData.reshape(self.numPixelInY, self.numPixelInX)[:,::-1]
        #from guiqwt import pyplot
        #pyplot.imshow(imageData)
        #pyplot.show()


    def closeCamera(self):
        ###
        # close camera
        closeCamera = self.greateyesLib.CloseCamera
        closeCamera.retype = c_bool
        closeCamera.argtype = [c_int, c_bool]
        closeCameraBool = closeCamera(c_int(0), c_bool(False))

        
def main():
    a = greatEyes()
    
if __name__ == '__main__':
    #main()
    from guidata.qt.QtGui import QApplication
    import sys
    app = QApplication(sys.argv)
    test = GreatEyesUi(None)
    test.show()
    app.exec_()
