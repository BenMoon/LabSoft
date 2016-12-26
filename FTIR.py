# -*- coding: utf-8 -*-
#
# Copyright © 2016-2017 CEA
# Hubertus Bromberger
# Licensed under the terms of the GPL License

"""
FTIR, program to record a spectrum using a michelson interferometer
"""

from __future__ import unicode_literals, print_function, division

from guidata.qt.QtGui import (QMainWindow, QMessageBox, QSplitter, QComboBox,
                              QMessageBox, QSpinBox,
                              QVBoxLayout, QGridLayout, QWidget, 
                              QTabWidget, QLabel, QLineEdit,
                              QDoubleValidator, QIntValidator, QValidator,
                              QMenu, QApplication, QCursor, QFont, QPushButton,
                              QSlider, QIcon, QFrame, QSizePolicy)
from guidata.qt.QtCore import (Qt, QT_VERSION_STR, PYQT_VERSION_STR, Signal,
                               Slot, QThread, QMutex, QMutexLocker, QLocale)
from guidata.qt import PYQT5
from guidata.qt.compat import getopenfilenames, getsavefilename
#from guiqwt.signals import SIG_MARKER_CHANGED

import sys
import platform
import os.path as osp
import os
import numpy as np
import time
from scipy.constants import c

#from guidata.dataset.datatypes import DataSet, ValueProp
#from guidata.dataset.dataitems import (IntItem, FloatArrayItem, StringItem,
#                                       ChoiceItem, FloatItem, DictItem,
#                                       BoolItem)
#from guidata.dataset.qtwidgets import DataSetEditGroupBox
from guidata.configtools import get_icon
from guidata.qthelpers import create_action, add_actions, get_std_icon
from guidata.qtwidgets import DockableWidget, DockableWidgetMixin
#from guidata.utils import update_dataset
from guidata.py3compat import to_text_string

from guiqwt.config import _
from guiqwt.plot import CurveWidget, ImageWidget
from guiqwt.builder import make

from pipython import GCSDevice, pitools
import libtiepie

# set default language to c, so decimal point is '.' not ',' on german systems
QLocale.setDefault(QLocale.c())
APP_NAME = _("FTIR")
APP_DESC = _("""Record a spectrum using a michelson<br>
interferometer with a delay stage""")
VERSION = '0.0.1'

nAir = 1.000292
c0   = c/nAir
# t = x/c
fsDelay = c0*1e-15*1e3/2 # eine fs auf delay stage im mm, 1fs=fsDelay, 1mm=1/fsDelay
fwhm = 2*np.sqrt(2*np.log(2))

def dummyPulse(x):
    A, mu, s, y0 = 1, 0, 40, 0
    return A*np.exp(-0.5*((x-mu)/s)**2)*np.cos(2*np.pi*0.1*x)+y0

class ObjectFT(QSplitter):
    """Object handling the item list, the selected item properties and plot"""
    def __init__(self, parent, plot):
        super(ObjectFT, self).__init__(Qt.Vertical, parent)
        self.plot = plot
        self.curve = make.curve([], [], color='b')
        self.plot.add_item(self.curve)

        self.hCursor = None
        self.vCursor = None
        self.xRange = None # holds limits of bounds
        self.xMinMax = () # holds limits of data min and max
        self.scaleFun = lambda x: x

        #print(dir(self.plot))
        #print(self.plot.itemList())
        #print(dir(self.plot.items))

    def addHCursor(self, i):
        self.hCursor = make.hcursor(i)
        self.plot.add_item(self.hCursor)
    def setHCursor(self, i):
        self.hCursor.setYValue(i)

    def addVCursor(self, i):
        self.vCursor = make.vcursor(i)
        self.plot.add_item(self.vCursor)
    def setVCursor(self, i):
        self.vCursor.setXValue(i)
    def getVCursor(self):
        return self.vCursor.xValue()

    def addBounds(self):
        self.xRange = make.range(0., 1.)
        self.plot.add_item(self.xRange)
        #print(dir(self.xRange))
        #print(self.xRange.get_item_parameters())
             
    #@Slot(object, object)
    def updateXAxe(self, xMin=0, xMax=1000):
        self.plot.set_axis_limits('bottom', xMin, xMax)
        self.xMinMax = (xMin, xMax)
        if self.xRange is not None:
            self.xRange.set_range(xMin, xMax)
        
    #@Slot(object, object)
    def updateYAxe(self, yMin=0, yMax=1):
        self.plot.set_axis_limits('left', yMin, yMax)
        #print('hcuror', self.hCursor.yValue(), 'yMax', yMax)
        #self.hCursor.setYValue(yMax*triggLevel)
        
    #@Slot(object)
    def updatePlot(self, data):
        '''New data arrived and thus update the plot'''
        #self.curve.set_data(data[:,0], data[:,1])
        self.curve.set_data(self.scaleFun(data[:,0]), data[:,1])
        #self.plot.plot.replot()

    def funChanged(self, fun):
        '''Slot for changing the x axis scanle function'''
        xMin, xMax = self.xMinMax
        #print('funChange', xMin, xMax)
        xMin /= self.scaleFun(1) # get back to original value
        xMax /= self.scaleFun(1)
        self.scaleFun = fun
        
        #print(self.scaleFun(xMin))
        self.updateXAxe(fun(xMin), fun(xMax))
        #print(fun(self.xRange[0]), fun(self.xRange[1]))

    def computeSum(self):
        '''Compute the integral of signal in given bounds'''
        x, y = self.curve.get_data()
        xMin, xMax = self.xRange.get_range()
        xMinIdx = x.searchsorted(xMin)
        xMaxIdx = x.searchsorted(xMax)
        return y[xMinIdx:xMaxIdx+1].sum()

    def computeFFT(self, data=None):
        '''assumes x to be fs, thus the fft should be THz'''
        if data is None:
            x, y = self.curve.get_data()
        else:
            x, y = data[:,0], data[:,1]
        Fs = 1/(x[1] - x[0]) # sampling rate
        #Ts = 1/Fs # sampling interval
              
        n = len(y) # length of the signal
        k = np.arange(n)
        T = n/Fs
        frq = k/T # two sides frequency range
        frq = frq[range(int(n/2))] # one side frequency range
              
        Y = np.fft.fft(y)/n # fft computing and normalization
        Y = Y[range(int(n/2))]
              
        data = np.column_stack((frq, abs(Y)))
        return data

class SignalFT(ObjectFT):
    #------ObjectFT API
    def setup(self, toolbar):
        ObjectFT.setup(self, toolbar)

class TiePieUi(QSplitter):
    '''
    Handling user interface to manage TiePie HS4/Diff Oscilloscope
    '''
    scpConnected = Signal()
    xAxeChanged = Signal(object, object)
    yAxeChanged = Signal(object, object)
    triggLevelChanged = Signal(object)
    def __init__(self, parent):
        #super(ObjectFT, self).__init__(Qt.Vertical, parent)
        super().__init__(parent)

        self.scp = None # variable to hold oscilloscope object
        self.mutex = QMutex()
        
        layoutWidget = QWidget()
        layout = QGridLayout()
        layoutWidget.setLayout(layout)

        self.openDevBtn = QPushButton('Open Osci')
        # channel stuff
        self.measCh = QComboBox()
        self.chSens = QComboBox()
        self.triggCh = QComboBox()
        self.frequency  = QLineEdit()
        self.frequency.setValidator(QIntValidator())
        self.recordLen = QLineEdit()
        self.recordLen.setValidator(QIntValidator())
        self.delay = QLineEdit()
        self.delay.setValidator(QDoubleValidator())
        # trigger stuff
        self.triggLevel = QLineEdit()
        self.triggLevel.setText('0.') # init value otherwise there's trouble with signal changing index of sensitivity
        self.triggLevel.setValidator(QDoubleValidator(0., 1., 3))
        self.hystereses = QLineEdit()
        self.hystereses.setValidator(QDoubleValidator(0., 1., 3))
        self.triggKind = QComboBox()     
        # do averages
        self.averages = QSpinBox()
        self.averages.setValue(1)
        self.averages.setRange(1, 10000)
        
        # put layout together
        layout.addWidget(self.openDevBtn, 0, 0)
        layout.addWidget(QLabel('Measuring Ch'), 1, 0)
        layout.addWidget(self.measCh, 1, 1)
        layout.addWidget(QLabel('Ch sensitivity'), 2, 0)
        layout.addWidget(self.chSens, 2, 1)
        layout.addWidget(QLabel('Sample freq. (kHz)'), 3, 0)
        layout.addWidget(self.frequency, 3, 1)
        layout.addWidget(QLabel('Record length'), 4, 0)
        layout.addWidget(self.recordLen, 4, 1)
        layout.addWidget(QLabel('Delay'), 5, 0)
        layout.addWidget(self.delay, 5, 1)
        layout.addWidget(QLabel('Trigger Ch'), 6, 0)
        layout.addWidget(self.triggCh, 6, 1)
        layout.addWidget(QLabel('Trigger Level (%)'), 7, 0)
        layout.addWidget(self.triggLevel, 7, 1)
        layout.addWidget(QLabel('Hystereses'), 8, 0)
        layout.addWidget(self.hystereses, 8, 1)
        layout.addWidget(QLabel('Trigger kind'), 9, 0)
        layout.addWidget(self.triggKind, 9, 1)
        layout.addWidget(QLabel('Averages'), 10, 0)
        layout.addWidget(self.averages, 10, 1)
        layout.setRowStretch(11, 10)
        layout.setColumnStretch(2,10)

        self.addWidget(layoutWidget)

        # connect UI to get things working
        self.openDevBtn.released.connect(self.openDev)
        self.chSens.currentIndexChanged.connect(self._changeSens)
        self.frequency.returnPressed.connect(self._changeFreq)
        self.recordLen.returnPressed.connect(self._changeRecordLength)
        self.triggLevel.returnPressed.connect(self._triggLevelChanged)
        self.triggLevel.textChanged.connect(self._check_state)        
        self.hystereses.returnPressed.connect(self._setHystereses)
        self.hystereses.textChanged.connect(self._check_state)

    def openDev(self):
        # search for devices
        libtiepie.device_list.update()
        # try to open an oscilloscope with block measurement support
        for item in libtiepie.device_list:
            if item.can_open(libtiepie.DEVICETYPE_OSCILLOSCOPE):
                self.scp = item.open_oscilloscope()
                if self.scp.measure_modes & libtiepie.MM_BLOCK:
                    break
                else:
                    self.scp = None
        # init UI
        #print(self.scp.name, 'found')
        if self.scp is not None:
            # Set measure mode:
            self.scp.measure_mode = libtiepie.MM_BLOCK
            
            # Set sample frequency:
            self.scp.sample_frequency = 1e6  # 1 MHz

            # Set record length:
            self.scp.record_length = 10000  # 10000 samples
            
            # Set pre sample ratio:
            self.scp.pre_sample_ratio = 0  # 0 %

            # Set trigger timeout:
            self.scp.trigger_time_out = 100e-3  # 100 ms
            

            # Enable channel 1 for measurement
            self.scp.channels[0].enabled = True
            self.scp.range = 0.2
            self.scp.coupling = libtiepie.CK_DCV # DC Volt
            
            # Disable all channel trigger sources
            for ch in self.scp.channels:
                ch.trigger.enabled = False
            # Setup channel trigger on 1
            ch = self.scp.channels[0]
            ch.trigger.enabled = True
            ch.trigger.kind = libtiepie.TK_RISINGEDGE
            ch.trigger.levels[0] = 0.5 # 50%
            ch.trigger.hystereses[0] = 0.05 # 5%

            
            # update UI
            # channel
            self.measCh.addItems(['Ch{:d}'.format(i) for i in range(self.scp.channels.count)])
            self.chSens.addItems(['{:.1f} V'.format(i) for i in self.scp.channels[0].ranges])
            self.frequency.setValidator(QIntValidator(1, 1e-3*self.scp.sample_frequency_max))
            self.frequency.setText('{:d}'.format(int(self.scp.sample_frequency*1e-3)))
            self.recordLen.setValidator(QIntValidator(1, self.scp.record_length_max))
            self.recordLen.setText('{:d}'.format(self.scp.record_length))
            # trigger
            self.triggCh.addItems(['Ch{:d}'.format(i) for i in range(self.scp.channels.count)])
            self.triggLevel.setText(str(ch.trigger.levels[0]))
            self.hystereses.setText(str(ch.trigger.hystereses[0]))
            self.triggKind.addItems(['{:s}'.format(i) for i in 
                libtiepie.trigger_kind_str(ch.trigger.kinds).split(', ')])
            
            self.openDevBtn.setEnabled(False)
            
            # tell the world that the scope is connected
            self.xAxeChanged.emit(0, 1/int(self.frequency.text())*1e-3*int(self.recordLen.text()))
            self.yAxeChanged.emit(-1*self.scp.range, self.scp.range)
            self.triggLevelChanged.emit(
                ch.trigger.levels[0]*2*self.scp.range-self.scp.range)
            self.scpConnected.emit()
            
        else:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText('No supported device found')
            msg.exec_()

    def getData(self):
        # function called thread for updating plot
        avg = int(self.averages.text())
        with QMutexLocker(self.mutex):
            x = np.linspace(0,
                            1/self.scp.sample_frequency*self.scp.record_length,
                            self.scp.record_length)
            y = np.zeros((avg, self.scp.record_length))
            for i in range(avg):
                self.scp.start()
                while not self.scp.is_data_ready:
                    time.sleep(0.01)
                y[i,:] = self.scp.get_data()[self.measCh.currentIndex()]
        return np.column_stack((x, y.mean(axis=0)))

    #@Slot
    def _changeSens(self, i):
        with QMutexLocker(self.mutex):
            yMax = self.scp.channels[0].ranges[i]
            self.scp.range = yMax
            self.yAxeChanged.emit(-1*yMax, yMax)
            self.triggLevelChanged.emit(
                float(self.triggLevel.text())*2*yMax-yMax)

    def _triggLevelChanged(self):
        with QMutexLocker(self.mutex):
            idx = self.measCh.currentIndex()
            ch = self.scp.channels[idx]
            ch.trigger.levels[0] = float(self.triggLevel.text())
            self.triggLevelChanged.emit(
                float(self.triggLevel.text())*2*self.scp.range-self.scp.range)
            
    def _changeFreq(self):
        with QMutexLocker(self.mutex):
            self.scp.sample_frequency = int(self.frequency.text())*1e3
            self.xAxeChanged.emit(0, 1/self.scp.sample_frequency*self.scp.record_length)

    def _changeRecordLength(self):
        with QMutexLocker(self.mutex):
            self.scp.record_length = int(self.recordLen.text())
            self.xAxeChanged.emit(0, 1/self.scp.sample_frequency*self.scp.record_length)

    def _setHystereses(self):
        with QMutexLocker(self.mutex):
            self.scp.hystereses = float(self.hystereses.text())
        
    def _check_state(self, *args, **kwargs):
        '''https://snorfalorpagus.net/blog/2014/08/09/validating-user-input-in-pyqt4-using-qvalidator/'''
        sender = self.sender()
        validator = sender.validator()
        state = validator.validate(sender.text(), 0)[0]
        if state == QValidator.Acceptable:
            color = '#FFFFFF' # green
        elif state == QValidator.Intermediate:
            color = '#fff79a' # yellow
        else:
            color = '#f6989d' # red
        sender.setStyleSheet('QLineEdit { background-color: %s }' % color)

     
class PiStageUi(QSplitter):
    stageConnected = Signal()
    stopScan = Signal()
    xAxeChanged = Signal(object, object)
    updateCurrPos = Signal(object)
    def __init__(self, parent):
        #super(ObjectFT, self).__init__(Qt.Vertical, parent)
        super().__init__(parent)

        self.stage = None
        self.offset = 0. # offset from 0 where t0 is (mm)
        self.newOff = 0.
        self.stageRange = (0, 0)

        layoutWidget = QWidget()
        layout = QGridLayout()
        layoutWidget.setLayout(layout)
       
        # put layout together
        self.openStageBtn = QPushButton("Open stage")
        self.initStageBtn = QPushButton("Init stage")
        
        #absolute move
        #current position
        self.currentPos = QLabel('')
        #self.currentPos.setValidator(QDoubleValidator())
        #relative move (mm)
        self.deltaMove_mm = QLineEdit()
        self.deltaMove_mm.setText('0')
        self.deltaMove_mm.setValidator(QDoubleValidator())
        self.deltaMovePlus_mm = QPushButton('+')
        self.deltaMoveMinus_mm = QPushButton('-')
        #relative move (fs)
        self.deltaMove_fs = QLineEdit()
        self.deltaMovePlus_fs = QPushButton('+')
        self.deltaMoveMinus_fs = QPushButton('-')
        #velocity
        self.velocityLabel = QLabel('Velocity:')
        self.velocity = QSlider(Qt.Horizontal)
        self.velocity.setMinimum(0)
        self.velocity.setMaximum(2000) # unit in µm; TODO: try to get max vel. from controller

        # scan from (fs)
        self.scanFrom = QLineEdit()
        self.scanFrom.setText('-100')
        self.scanFrom.setValidator(QIntValidator())
        # scan to (fs)
        self.scanTo = QLineEdit()
        self.scanTo.setText('100')
        self.scanTo.setValidator(QIntValidator())
        # scan stepsize (fs)
        self.scanStep = QLineEdit()
        self.scanStep.setText('10')
        self.scanStep.setValidator(QDoubleValidator())
        # center here button
        self.centerBtn = QPushButton('Center here')
        self.centerBtn.setToolTip('Center scan at current stage position')
        self.startScanBtn = QPushButton("Start scan")
        self.stopScanBtn = QPushButton("Stop scan")
        # spacer line
        hLine = QFrame()
        hLine.setFrameStyle(QFrame.HLine)
        hLine.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)

        # put layout together
        layout.addWidget(self.openStageBtn, 0, 0)
        layout.addWidget(self.initStageBtn, 0, 1)
        layout.addWidget(QLabel("Current pos (mm):"), 1, 0)
        layout.addWidget(self.currentPos, 1, 1)
        layout.addWidget(self.velocityLabel, 2, 0)
        layout.addWidget(self.velocity, 3, 0, 1, 2)
        layout.addWidget(QLabel('Move relative (mm)'), 4, 0)
        layout.addWidget(self.deltaMove_mm, 5, 0, 1, 2)
        layout.addWidget(self.deltaMoveMinus_mm, 6, 0)
        layout.addWidget(self.deltaMovePlus_mm, 6, 1)
        layout.addWidget(QLabel('Move relative (fs)'), 7, 0)
        layout.addWidget(self.deltaMove_fs, 8, 0, 1, 2)
        layout.addWidget(self.deltaMoveMinus_fs, 9, 0)
        layout.addWidget(self.deltaMovePlus_fs, 9, 1)
        
        layout.addWidget(hLine, 10, 0, 1, 2)
        layout.addWidget(QLabel('Scan from (fs)'), 11, 0)
        layout.addWidget(self.scanFrom, 11, 1)
        layout.addWidget(QLabel('Scan to (fs)'), 12, 0)
        layout.addWidget(self.scanTo, 12, 1)
        layout.addWidget(QLabel('Stepsize (fs)'), 13, 0)
        layout.addWidget(self.scanStep, 13, 1)
        layout.addWidget(self.startScanBtn, 14, 0)
        layout.addWidget(self.stopScanBtn, 14, 1)
        layout.addWidget(self.centerBtn, 15, 1)
        layout.setRowStretch(16, 10)
        layout.setColumnStretch(2,10)

        self.addWidget(layoutWidget)

        # make button and stuff functional
        self.openStageBtn.released.connect(self.connectStage)
        self.initStageBtn.released.connect(self.initStage)
        self.scanFrom.returnPressed.connect(self._xAxeChanged)
        self.scanTo.returnPressed.connect(self._xAxeChanged)
        self.centerBtn.released.connect(self._centerHere)
        self.deltaMovePlus_mm.released.connect(
            lambda x=1: self.moveRel_mm(float(self.deltaMove_mm.text())))
        self.deltaMoveMinus_mm.released.connect(
            lambda x=-1: self.moveRel_mm(float(self.deltaMove_mm.text()), x))
        # thread for updating position
        self.currPosThr = GenericThread(self.__getCurrPos)
        self.updateCurrPos.connect(self.__updateCurrPos)
        

    def connectStage(self):
        gcs = GCSDevice()
        try:
            gcs.InterfaceSetupDlg()
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText(gcs.qIDN())
            msg.exec_()
            self.stage = gcs
            self.openStageBtn.setEnabled(False)
        except:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText('Could not connect stage')
            msg.exec_()

    def initStage(self):
        # TODO put this in thread and show egg clock
        if self.stage is not None:
            # TODO: give choice to select stage
            pitools.startup(self.stage, stages='M-112.1DG-NEW', refmode='FNL')
            # TODO: show dialog for waiting
            self.velocityLabel.setText(
                'Velocity: {:f}mm/s'.format(self.stage.qVEL()['1']))
            self.velocity.setValue(int(1000*self.stage.qVEL()['1']))
            self.stageConnected.emit()
            self._xAxeChanged()
            self.currentPos.setText('{:.7f}'.format(
                self.stage.qPOS()['1']))
            self.__startCurrPosThr()
            self.stageRange = (self.stage.qTMN()['1'],
                               self.stage.qTMX()['1'])
            self.scanStep.validator().setBottom(0)
            self.initStageBtn.setEnabled(False)
        else:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText('No stage connected')
            msg.exec_()

    def gotoPos_mm(self, x):
        '''Move stage to absolute position in mm'''
        if self.stageRange[0] <= x <= self.stageRange[1]:
            self.stage.MOV(self.stage.axes, x)
            while not pitools.ontarget(self.stage, '1')['1']:
                time.sleep(0.05)
        else:
            print('Requested postition', x, 'outside of range', self.stageRange)

    def gotoPos_fs(self, x):
        '''Move stage to absolute position in mm'''
        self.gotoPos_mm(self._calcAbsPos(x))

    def moveRel_mm(self, x=0, sign=1):
        '''Moves stage relative to current position'''
        # TODO raise message if outside of range
        currPos = float(self.currentPos.text())
        if self.stageRange[0] <= sign*x+currPos <= self.stageRange[1]:
               self.stage.MVR(self.stage.axes, sign*x)
        else:
            print('Requested postition', x, 'outside of range', self.stageRange)

    def moveRel_fs(self, x=0, sign=1):
        '''Moves stage relative to current position; expexts fs'''
        # TODO raise message if outside of range
        self.moveRel_mm(self._calcAbsPos(x), sign)
        
    def _calcAbsPos(self, x):
        '''Calculate absolute position on stage from given femtosecond value
           gets x in fs and returns position mm'''
        return (x*fsDelay) + self.offset
 
    def getDelays_mm(self):
        '''expects fs and returns mm'''
        von = self._calcAbsPos(float(self.scanFrom.text()))
        bis = self._calcAbsPos(float(self.scanTo.text()))
        #stepSize = int(self.scanStep.text())
        stepSize = float(self.scanStep.text())*fsDelay
        return np.linspace(von, bis, (np.abs(von)+bis)/stepSize)

    def getDelays_fs(self):
        '''expects fs and returns mm'''
        von = float(self.scanFrom.text())
        bis = float(self.scanTo.text())
        #stepSize = int(self.scanStep.text())
        stepSize = float(self.scanStep.text())
        return np.linspace(von, bis, (np.abs(von)+bis)/stepSize)

    def _xAxeChanged(self):
        self.xAxeChanged.emit(int(self.scanFrom.text()), int(self.scanTo.text()))

    def setCenter(self):
        '''Slot which recieves the new center position
           in fs and sets offset in mm
        '''
        if self.newOff != 0:
            self.offset += (self.newOff*fsDelay)
            print('offset', self.offset, self.newOff)
            self.newOff = 0.

    def newOffset(self, newOffset):
        self.newOff = newOffset

    def _centerHere(self):
        self.offset = self.stage.qPOS()['1']

    def __startCurrPosThr(self):
        self.stopCurrPosThr = False
        self.currPosThr.start()
    def __stopCurrPosThr(self):
        self.stopCurrPosThr = True
        while(self.currPosThr.isRunning()):
            time.sleep(0.03)
    def __getCurrPos(self):
        oldPos = self.stage.qPOS()['1']
        while not self.stopCurrPosThr:
            newPos = self.stage.qPOS()['1']
            if oldPos != newPos:
                oldPos = newPos
                self.updateCurrPos.emit(newPos)
            time.sleep(0.5)
    def __updateCurrPos(self, newPos):
        self.currentPos.setText('{:.7f}'.format(newPos))
        
class XAxeCalc(QComboBox):
    idxChanged = Signal(object)
    def __init__(self, parent):
        super(QComboBox, self).__init__(parent)
        self.functions = []
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setAlignment(Qt.AlignCenter)
        self.currentIndexChanged.connect(self.changed)

    def addFun(self, name, fun):
        self.functions.append(fun)
        self.addItem(name)

    def changed(self, idx):
        self.idxChanged.emit(self.functions[idx])
    
class DockablePlotWidget(DockableWidget):
    LOCATION = Qt.RightDockWidgetArea
    def __init__(self, parent, plotwidgetclass, toolbar):
        super(DockablePlotWidget, self).__init__(parent)
        self.toolbar = toolbar
        self.layout = QVBoxLayout()
        self.plotwidget = plotwidgetclass()
        self.layout.addWidget(self.plotwidget)
        self.calcFun = XAxeCalc(self)
        self.layout.addWidget(self.calcFun)
        self.setLayout(self.layout)
        self.setup()
        
    def get_plot(self):
        return self.plotwidget.plot
        
    def setup(self):
        title = to_text_string(self.toolbar.windowTitle())
        self.plotwidget.add_toolbar(self.toolbar, title)
        if isinstance(self.plotwidget, ImageWidget):
            self.plotwidget.register_all_image_tools()
        else:
            self.plotwidget.register_all_curve_tools()
        
    #------DockableWidget API
    def visibility_changed(self, enable):
        """DockWidget visibility has changed"""
        DockableWidget.visibility_changed(self, enable)
        self.toolbar.setVisible(enable)
            

class DockableTabWidget(QTabWidget, DockableWidgetMixin):
    LOCATION = Qt.LeftDockWidgetArea
    def __init__(self, parent):
        if PYQT5:
            super(DockableTabWidget, self).__init__(parent, parent=parent)
        else:
            QTabWidget.__init__(self, parent)
            DockableWidgetMixin.__init__(self, parent)


try:
    try:
        # Spyder 2
        from spyderlib.widgets.internalshell import InternalShell
    except ImportError:
        # Spyder 3
        from spyder.widgets.internalshell import InternalShell
    class DockableConsole(InternalShell, DockableWidgetMixin):
        LOCATION = Qt.BottomDockWidgetArea
        def __init__(self, parent, namespace, message, commands=[]):
            InternalShell.__init__(self, parent=parent, namespace=namespace,
                                   message=message, commands=commands,
                                   multithreaded=True)
            DockableWidgetMixin.__init__(self, parent)
            self.setup()
            
        def setup(self):
            font = QFont("Courier new")
            font.setPointSize(10)
            self.set_font(font)
            self.set_codecompletion_auto(True)
            self.set_calltips(True)
            try:
                # Spyder 2
                self.setup_completion(size=(300, 180), font=font)
            except TypeError:
                pass
            try:
                self.traceback_available.connect(self.show_console)
            except AttributeError:
                pass
            
        def show_console(self):
            self.dockwidget.raise_()
            self.dockwidget.show()
except ImportError:
    DockableConsole = None

class GenericThread(QThread):
    def __init__(self, function, *args, **kwargs):
        QThread.__init__(self)
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def __del__(self):
        self.wait()

    def run(self):
        self.function(*self.args, **self.kwargs)
        return

class SiftProxy(object):
    def __init__(self, win):
        self.win = win
        #self.s = self.win.signalft.objects

class MainWindow(QMainWindow):
    updateOsciPlot = Signal(object)
    updateTdPlot = Signal(object)
    updateFdPlot = Signal(object)
    def __init__(self):
        QMainWindow.__init__(self)

        self.stage = None
        self.stopOsci = False
        self.stopMeasure = False
        
        self.setWindowTitle(APP_NAME)

        # Osci live
        curveplot_toolbar = self.addToolBar(_("Curve Plotting Toolbar"))
        self.osciCurveWidget = DockablePlotWidget(self, CurveWidget,
                                              curveplot_toolbar)
        self.osciCurveWidget.calcFun.addFun('s', lambda x: x)
        self.osciCurveWidget.calcFun.addFun('ms', lambda x: x*1e3)
        self.osciCurveWidget.calcFun.addFun('µs', lambda x: x*1e6)
        osciPlot = self.osciCurveWidget.get_plot()
        #osciPlot.set_axis_title('bottom', 'Time (s)')
        #osciplot.add_item(make.legend("TR"))
        self.osciSignal = SignalFT(self, plot=osciPlot)
        self.osciSignal.addHCursor(0)
        self.osciSignal.addBounds()
        
        # Time domain plot
        self.tdWidget = DockablePlotWidget(self, CurveWidget,
                                              curveplot_toolbar)
        self.tdWidget.calcFun.addFun('fs', lambda x: x)
        self.tdWidget.calcFun.addFun('µm', lambda x: x*fsDelay*1e3)
        self.tdWidget.calcFun.addFun('mm', lambda x: x*fsDelay)
        tdPlot = self.tdWidget.get_plot()
        #tdPlot.add_item(make.legend("TR"))
        self.tdSignal  = SignalFT(self, plot=tdPlot)
        self.tdSignal.addVCursor(0)

        # Frequency domain plot
        self.fdWidget = DockablePlotWidget(self, CurveWidget,
                                              curveplot_toolbar)
        self.fdWidget.calcFun.addFun('PHz', lambda x: x)
        self.fdWidget.calcFun.addFun('THz', lambda x: x*1e3)
        self.fdWidget.calcFun.addFun('µm', lambda x: c0/x)
        self.fdWidget.calcFun.addFun('eV', lambda x: x)
        fdplot = self.fdWidget.get_plot()
        #fqdplot.add_item(make.legend("TR"))
        self.fdSignal  = SignalFT(self, plot=fdplot)

        # Main window widgets
        self.tabwidget = DockableTabWidget(self)
        #self.tabwidget.setMaximumWidth(500)
        self.tiepieUi = TiePieUi(self)
        self.piUi = PiStageUi(self)
        #self.stage = self.piUi.stage
        self.tabwidget.addTab(self.tiepieUi, QIcon('Handyscope_HS4.png'),
                              _("Osci"))
        self.tabwidget.addTab(self.piUi, get_icon('piController.png'),
                              _("Stage"))
        self.add_dockwidget(self.tabwidget, _("Inst. sett."))
#        self.setCentralWidget(self.tabwidget)
        self.osci_dock = self.add_dockwidget(self.osciCurveWidget,
                                              title=_("Osciloscope"))
        self.td_dock = self.add_dockwidget(self.tdWidget,
                                              title=_("Time Domain"))
        self.fd_dock = self.add_dockwidget(self.fdWidget,
                                              title=_("Frequency Domain"))


        # connect signals
        self.piUi.startScanBtn.released.connect(self.startMeasureThr)
        self.piUi.stopScanBtn.released.connect(self.stopMeasureThr)
        self.piUi.xAxeChanged.connect(self.tdSignal.updateXAxe)
        self.tiepieUi.scpConnected.connect(self.startOsciThr)
        self.tiepieUi.xAxeChanged.connect(self.osciSignal.updateXAxe)
        self.tiepieUi.yAxeChanged.connect(self.osciSignal.updateYAxe)
        self.tiepieUi.triggLevelChanged.connect(self.osciSignal.setHCursor)
        #self.piUi.centerBtn.released.connect(
        #    lambda x=None: self.piUi.setCenter(self.tdSignal.getVCursor()))
        self.tdSignal.plot.SIG_MARKER_CHANGED.connect(
            lambda x=None: self.piUi.newOffset(self.tdSignal.getVCursor()))

        self.osciCurveWidget.calcFun.idxChanged.connect(self.osciSignal.funChanged)
        self.tdWidget.calcFun.idxChanged.connect(self.tdSignal.funChanged)
        self.fdWidget.calcFun.idxChanged.connect(self.fdSignal.funChanged)

        self.updateOsciPlot.connect(self.osciSignal.updatePlot)
        self.updateTdPlot.connect(self.tdSignal.updatePlot)
        self.updateFdPlot.connect(lambda data:
            self.fdSignal.updatePlot(self.fdSignal.computeFFT(data)))
        
        # create threads
        self.osciThr = GenericThread(self.getOsciData)
        self.measureThr = GenericThread(self.getMeasureData)
        
        

        # File menu
        file_menu = self.menuBar().addMenu(_("File"))
        self.quit_action = create_action(self, _("Quit"), shortcut="Ctrl+Q",
                                    icon=get_std_icon("DialogCloseButton"),
                                    tip=_("Quit application"),
                                    triggered=self.close)
        triggerTest_action = create_action(self, _("Stop Osci"),
                                    shortcut="Ctrl+O",
                                    icon=get_icon('fileopen.png'),
                                    tip=_("Open an image"),
                                    triggered=self.stopOsciThr)
        add_actions(file_menu, (triggerTest_action, None, self.quit_action))
        

        # Eventually add an internal console (requires 'spyderlib')
        self.sift_proxy = SiftProxy(self)
        if DockableConsole is None:
            self.console = None
        else:
            import time, scipy.signal as sps, scipy.ndimage as spi
            ns = {'ftir': self.sift_proxy,
                  'np': np, 'sps': sps, 'spi': spi,
                  'os': os, 'sys': sys, 'osp': osp, 'time': time}
            msg = "Example: ftir.s[0] returns signal object #0\n"\
                  "Modules imported at startup: "\
                  "os, sys, os.path as osp, time, "\
                  "numpy as np, scipy.signal as sps, scipy.ndimage as spi"
            self.console = DockableConsole(self, namespace=ns, message=msg)
            self.add_dockwidget(self.console, _("Console"))
            '''
            try:
                self.console.interpreter.widget_proxy.sig_new_prompt.connect(
                                            lambda txt: self.refresh_lists())
            except AttributeError:
                print('sift: spyderlib is outdated', file=sys.stderr)
            '''

        # Show main window and raise the signal plot panel
        self.show()

    #------GUI refresh/setup
    def add_dockwidget(self, child, title):
        """Add QDockWidget and toggleViewAction"""
        dockwidget, location = child.create_dockwidget(title)
        self.addDockWidget(location, dockwidget)
        return dockwidget

    
    def closeEvent(self, event):
        if self.stage is not None:
            self.stage.CloseConnection()
        if self.console is not None:
            self.console.exit_interpreter()
        event.accept()

    #def getStage(self, gcs):
    #    self.stage = gcs
    #    print(dir(self.stage))
    #    print(self.stage.qPOS())

    def startOsciThr(self):
        self.stopOsci = False
        self.osciThr.start()
    def stopOsciThr(self):
        self.stopOsci = True
        while(self.osciThr.isRunning()):
            time.sleep(0.03)
    def getOsciData(self):
        while not self.stopOsci:
            data = self.tiepieUi.getData()
            self.updateOsciPlot.emit(data)
            time.sleep(0.5)

    def startMeasureThr(self):
        # rescale tdPlot (updateXAxe)
        self.piUi._xAxeChanged()
        # set vCursor to 0
        self.tdSignal.setVCursor(0)
        self.piUi.setCenter()
        self.stopOsciThr()
        self.stopMeasure = False
        self.measureThr.start()
    def stopMeasureThr(self):
        self.stopMeasure = True
        while(self.measureThr.isRunning()):
            time.sleep(0.03)
        self.startOsciThr()
    def getMeasureData(self):
        delays = self.piUi.getDelays_fs()
        data = np.column_stack((delays, np.zeros(len(delays))))
        for i, delay in enumerate(delays):
            if not self.stopMeasure:
                self.piUi.gotoPos_fs(delay)
                tmp = self.tiepieUi.getData()
                self.updateOsciPlot.emit(tmp)
                #print('measuring at', delay)
                #y = dummyPulse(delay)
                #data[i,1] = y
                data[i,1] = tmp[:,1].mean()
                #time.sleep(0.05)
                self.updateTdPlot.emit(data)
                self.updateFdPlot.emit(data)
            else:
                break
        self.startOsciThr()
    """
    def _newCenter(self):
        '''Function call when 'Center Here' triggered'''
        newOffset = self.tdSignal.getVCursor()
        self.piUi._centerPos(newOffset)
    """     


def run():
    from guidata import qapplication
    app = qapplication()
    window = MainWindow()
    window.show()
    app.exec_()


if __name__ == '__main__':
    run()
