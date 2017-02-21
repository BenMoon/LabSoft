# -*- coding: utf-8 -*-

from PyQt5 import QtNetwork
from guidata.qt.QtGui import (QSplitter, QGridLayout, QLineEdit,
                              QWidget, QSpinBox, QIntValidator,
                              QPushButton, QRegExpValidator,
                              QLabel, QMessageBox)
from guidata.qt.QtCore import (QThread, Qt, Signal, QRegExp)

import numpy as np
import time
from datetime import datetime
from queue import Queue

from Helpers.genericthread import GenericWorker

class MaestroUi(QSplitter):
    connected = Signal() # gets emitted if stage was sucessfully connected
    newPlotData = Signal(object)
    updateAvgTxt = Signal(object)
    def __init__(self, parent):
        #super(ObjectFT, self).__init__(Qt.Vertical, parent)
        super().__init__(parent)

        self.meter = None
        self.collectData = True # bool for data collection thread
        self.avgData = Queue() # need data for averaging and set for holding all
        self.measure = False
        self.runDataThr = True
        self.measureData = []


        layoutWidget = QWidget()
        layout = QGridLayout()
        layoutWidget.setLayout(layout)

        ##############
        # gui elements
        self.ipEdit = QLineEdit()
        rx = QRegExp("^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]).){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$")
        self.ipEdit.setValidator(QRegExpValidator(rx))
        self.ipEdit.setText('127.0.0.1')
        self.portEdit = QLineEdit()
        self.portEdit.setValidator(QIntValidator(1, 65535, self))
        self.portEdit.setText('5000')
        self.connectBtn = QPushButton('Connect')
        self.avgSpin = QSpinBox()
        self.avgSpin.setValue(1)
        self.avgSpin.setRange(1, 10000)
        self.currValDisp = QLabel('0.0')
        self.startMeasBtn = QPushButton('Start aq')
        self.stopMeasBtn  = QPushButton('Stop aq')

        ##############
        # put layout together
        layout.addWidget(QLabel('IP Address:'), 0, 0)
        layout.addWidget(self.ipEdit, 1, 0)
        layout.addWidget(QLabel('Port:'), 0, 1)
        layout.addWidget(self.portEdit, 1, 1)
        layout.addWidget(self.connectBtn, 2, 1)
        layout.addWidget(QLabel('Averages'), 4, 0)
        layout.addWidget(self.avgSpin, 5, 0)
        layout.addWidget(self.currValDisp, 5, 1)
        layout.addWidget(self.startMeasBtn, 6, 0)
        layout.addWidget(self.stopMeasBtn, 6, 1)

        self.addWidget(layoutWidget)

        ##############
        # Network stuff
        self.tcpClient = QtNetwork.QTcpSocket()
        self.tcpClient.readyRead.connect(self.__getSocketData)
        self.tcpClient.error.connect(lambda x: print(x))

        ##############
        # make button and stuff functional
        self.connectBtn.released.connect(self.connectMeter)
        self.avgSpin.valueChanged.connect(self.changeAverage)
        self.startMeasBtn.released.connect(self._startMeasure)
        self.stopMeasBtn.released.connect(self._stopMeasure)

        ##############
        # thread for getting data from socket
        self.updateAvgTxt.connect(self.__updateAvgTxt)
        self.dataAq_Thr = QThread()
        self.dataAq_Thr.start()
        self.dataAq_worker = GenericWorker(self.__getData)
        self.dataAq_worker.moveToThread(self.dataAq_Thr)


    def connectMeter(self):
        print('connected')
        self.tcpClient.connectToHost(self.ipEdit.text(), int(self.portEdit.text()))
        self.tcpClient.write('start\n'.encode())
        self.dataAq_worker.start.emit()

    def _startMeasure(self):
        self.measure = True
    def _stopMeasure(self):
        self.measure = False

    #@Slot
    def __updateAvgTxt(self, text):
        '''
        update current value label
        '''
        self.currValDisp.setText(text)


    def changeAverage(self):
        shape = int(self.avgSpin.value())
        self.dispData = np.zeros(shape)
    
    def __getData(self):
        '''
        Function run in thread
        '''
        while self.runDataThr:
            tmpData = np.array(int(self.avgSpin.text())*[[datetime.now(), 0]])
            for i in range(len(tmpData)):
                tmpData[i] = self.avgData.get()
                if self.measure:
                    self.measureData.append(tmpData[i])
            #print('mean', tmpData.mean())
            self.updateAvgTxt.emit(str(tmpData[:,1].mean()))
            if self.measure:
                self.newPlotData.emit(np.asarray(self.measureData))
        self.avgData.task_done()

    #@Slot()
    def __getSocketData(self):
        '''
        to be called if network buffer has more data
        push data to queue
        '''
        self.avgData.put([datetime.now(), float(self.tcpClient.readLine(1024).decode().rstrip())])

    def closeEvent(self, event):
        if self.tcpClient.isOpen():
            self.RunDataThr = False
            self.tcpClient.write('stop\n'.encode())
            time.sleep(0.1)
            self.tcpClient.close()
            print(self.tcpClient.isOpen())
        #if self.console is not None:
        #    self.console.exit_interpreter()
        event.accept()
        
if __name__ == '__main__':
    from guidata.qt.QtGui import QApplication
    import sys
    app = QApplication(sys.argv)
    #test = MyApp()
    test = MaestroUi(None)
    test.show()
    app.exec_()
