# -*- coding: utf-8 -*-

# class to provide access to Pi stages

from guidata.qt.QtGui import (QSplitter, QGridLayout, QLineEdit,
                              QIntValidator, QDoubleValidator, QWidget, QPushButton,
                              QLabel, QMessageBox, QSlider, QFrame, QSizePolicy)
from guidata.qt.QtCore import (QThread, Qt, Signal)

import numpy as np
import time

from pipython import GCSDevice, pitools
from Helpers.genericthread import GenericWorker

from scipy.constants import c
nAir = 1.000292
c0   = c/nAir
# t = x/c
fsDelay = c0*1e-15*1e3/2 # eine fs auf delay stage im mm, 1fs=fsDelay, 1mm=1/fsDelay

class PiStageUi(QSplitter):
    stageConnected = Signal() # gets emitted if stage was sucessfully connected
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
        self.niceBtn = QPushButton('Make it nice')
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
        layout.addWidget(self.niceBtn, 16, 1)
        layout.setRowStretch(17, 10)
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
        
        ################
        # thread for updating position
        #self.currPosThr = GenericThread(self.__getCurrPos)
        self.updateCurrPos.connect(self.__updateCurrPos)
        self.currPos_thread = QThread() # create the QThread
        self.currPos_thread.start()

        # This causes my_worker.run() to eventually execute in my_thread:
        self.currPos_worker = GenericWorker(self.__getCurrPos)
        self.currPos_worker.moveToThread(self.currPos_thread)
        # my_worker.finished.connect(self.xxx)

        #self.threadPool.append(my_thread)
        #self.my_worker = my_worker
        

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
            ## Create and display the splash screen
            #splash_pix = QPixmap('icons/piController.png')
            #splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
            #splash.setMask(splash_pix.mask())
            #splash.show()
            # TODO: give choice to select stage
            pitools.startup(self.stage, stages='M-112.1DG-NEW', refmode='FNL')
            #splash.close()
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
        #self.currPosThr.start()
        self.currPos_worker.start.emit()
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
        
if __name__ == '__main__':
    from guidata.qt.QtGui import QApplication
    import sys
    app = QApplication(sys.argv)
    #test = MyApp()
    test = PiStageUi(None)
    test.show()
    app.exec_()
