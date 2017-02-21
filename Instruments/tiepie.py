# -*- coding: utf-8 -*-
# module for TiePie oscilloscope

from guidata.qt.QtGui import (QSplitter, QComboBox, QGridLayout, QLineEdit,
                              QIntValidator, QDoubleValidator, QWidget, QPushButton,
                              QSpinBox, QLabel, QMessageBox)
from guidata.qt.QtCore import (Signal, QMutex, QMutexLocker, )

import numpy as np
import time


import libtiepie

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
        self.triggLevel.setToolTip('http://api.tiepie.com/libtiepie/0.5/triggering_scpch.html#triggering_scpch_level')
        self.triggLevel.setText('0.') # init value otherwise there's trouble with signal changing index of sensitivity
        self.triggLevel.setValidator(QDoubleValidator(0., 1., 3))
        self.hystereses = QLineEdit()
        self.hystereses.setText('0.05')
        self.hystereses.setToolTip('http://api.tiepie.com/libtiepie/0.5/triggering_scpch.html#triggering_scpch_hysteresis')
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
        self.triggCh.currentIndexChanged.connect(self._changeTrigCh)
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
            # http://api.tiepie.com/libtiepie/0.5/group__scp__ch__enabled.html
            self.scp.channels[0].enabled = True # by default all channels are enabled
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
            # TODO: doen't work in module anymore!!
            #self.triggLevel.setText(str(ch.trigger.levels[0]))
            #self.hystereses.setText(str(ch.trigger.hystereses[0]))
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

    def _changeTrigCh(self, newTrig):
        print('new trigger channel', newTrig)
        scope = self.scp
        with QMutexLocker(self.mutex):
            # Disable all channel trigger sources
            for ch in scope.channels:
                ch.trigger.enabled = False
            # enable trigger on newly selected channel
            ch = scope.channels[newTrig]
            ch.trigger.enabled = True
            ch.trigger.kind = libtiepie.TK_RISINGEDGE
            ch.trigger.levels[0] = float(self.triggLevel.text())
            ch.trigger.hystereses[0] = float(self.hystereses.text())
                
        
    def _triggLevelChanged(self):
        with QMutexLocker(self.mutex):
            idx = self.triggCh.currentIndex()
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

if __name__ == '__main__':
    from guidata.qt.QtGui import QApplication
    import sys
    app = QApplication(sys.argv)
    #test = MyApp()
    test = TiePieUi(None)
    test.show()
    app.exec_()
