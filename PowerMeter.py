# -*- coding: utf-8 -*-
#
# Copyright © 2016-2017 CEA
# Hubertus Bromberger
# Licensed under the terms of the GPL License

"""
Read and plot Gentec Maestro Powermeter
"""

from guidata.qt.QtGui import (QMainWindow, QMessageBox, 
                              QSpinBox, QHBoxLayout,
                              QVBoxLayout, QGridLayout,  
                              QTabWidget, QLabel, QLineEdit,  
                              QFont, QIcon)
from guidata.qt.QtCore import (Qt, Signal, QThread, QLocale)
from guidata.qt import PYQT5
#from guidata.qt.compat import getopenfilenames, getsavefilename
#from guiqwt.signals import SIG_MARKER_CHANGED

import sys
#import platform
import os.path as osp
import os
import numpy as np
import time

#from guidata.dataset.datatypes import DataSet, ValueProp
#from guidata.dataset.dataitems import (IntItem, FloatArrayItem, StringItem,
#                                       ChoiceItem, FloatItem, DictItem,
#                                       BoolItem)
#from guidata.dataset.qtwidgets import DataSetEditGroupBox
from guidata.configtools import get_icon
from guidata.qthelpers import create_action, add_actions, get_std_icon
from guidata.qtwidgets import DockableWidgetMixin
from guiqwt.plot import CurveWidget
#from guidata.utils import update_dataset
#from guidata.py3compat import to_text_string

from guiqwt.config import _

# local imports
from Helpers.plotSignal import SignalFT, DockablePlotWidget
from Helpers.genericthread import GenericWorker
from Instruments.gentec import MaestroUi

# set default language to c, so decimal point is '.' not ',' on german systems
QLocale.setDefault(QLocale.c())
APP_NAME = _("Powermeter")
APP_DESC = _("""Get data from Gentec Maestro using its ethernet interface""")
VERSION = '0.0.1'



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

        ###############
        # Powermeter record
        curveplot_toolbar = self.addToolBar(_("Curve Plotting Toolbar"))
        self.curveWidget1 = DockablePlotWidget(self, CurveWidget,
                                              curveplot_toolbar)
        self.curveWidget1.calcFun.addFun('s', lambda x: x,
                                                 lambda x: x)
        self.curveWidget1.calcFun.addFun('min', lambda x: x/60,
                                                  lambda x: x*60)
        self.curveWidget1.calcFun.addFun('hour', lambda x: x/3600,
                                                  lambda x: x*3600)
        plot1 = self.curveWidget1.get_plot()
        self.signal1 = SignalFT(self, plot=plot1)
        

        ##############
        # Main window widgets
        self.tabwidget = DockableTabWidget(self)
        #self.tabwidget.setMaximumWidth(500)
        self.maestroUi = MaestroUi(self)
        self.tabwidget.addTab(self.maestroUi, QIcon('icons/Handyscope_HS4.png'),
                              _("Maestro"))
        self.add_dockwidget(self.tabwidget, _("Inst. sett."))
#        self.setCentralWidget(self.tabwidget)
        self.dock1 = self.add_dockwidget(self.curveWidget1,
                                              title=_("Powermeter"))

        ################
        # connect signals
        self.maestroUi.newPlotData.connect(self.signal1.updatePlot)
        self.curveWidget1.calcFun.idxChanged.connect(self.signal1.funChanged)
        '''
        self.piUi.startScanBtn.released.connect(self.startMeasureThr)
        self.piUi.stopScanBtn.released.connect(self.stopMeasureThr)
        self.piUi.xAxeChanged.connect(self.tdSignal.updateXAxe)
        self.piUi.xAxeChanged.connect(self.fdSignal.updateXAxe)
        self.piUi.niceBtn.released.connect(self.showMakeNicerWidget)
        self.tiepieUi.scpConnected.connect(self.startOsciThr)
        self.tiepieUi.xAxeChanged.connect(self.osciSignal.updateXAxe)
        self.tiepieUi.yAxeChanged.connect(self.osciSignal.updateYAxe)
        self.tiepieUi.triggLevelChanged.connect(self.osciSignal.setHCursor)
        #self.piUi.centerBtn.released.connect(
        #    lambda x=None: self.piUi.setCenter(self.tdSignal.getVCursor()))
        self.tdSignal.plot.SIG_MARKER_CHANGED.connect(
            lambda x=None: self.piUi.newOffset(self.tdSignal.getVCursor()))

        
        self.tdWidget.calcFun.idxChanged.connect(self.tdSignal.funChanged)
        self.fdWidget.calcFun.idxChanged.connect(self.fdSignal.funChanged)

        self.updateOsciPlot.connect(self.osciSignal.updatePlot)
        self.updateTdPlot.connect(self.tdSignal.updatePlot)
        self.updateFdPlot.connect(lambda data:
            self.fdSignal.updatePlot(self.fdSignal.computeFFT(data)))
        '''
        ################
        # create threads
        #self.osciThr = GenericThread(self.getOsciData)
        '''
        self.osciThr = QThread()
        self.osciThr.start()
        self.osciWorker = GenericWorker(self.getOsciData)
        self.osciWorker.moveToThread(self.osciThr)
        
        #self.measureThr = GenericThread(self.getMeasureData)
        self.measureThr = QThread()
        self.measureThr.start()
        self.measureWorker = GenericWorker(self.getMeasureData)
        self.measureWorker.moveToThread(self.measureThr)
        '''
        
        ################
        # File menu
        file_menu = self.menuBar().addMenu(_("File"))
        self.quit_action = create_action(self, _("Quit"), shortcut="Ctrl+Q",
                                    icon=get_std_icon("DialogCloseButton"),
                                    tip=_("Quit application"),
                                    triggered=self.close)
        saveData = create_action(self, _("Save"), shortcut="Ctrl+S",
                                    icon=get_std_icon("DialogSaveButton"),
                                    tip=_("Save data"),
                                    triggered=self.saveData)
        triggerTest_action = create_action(self, _("Stop Osci"),
                                    shortcut="Ctrl+O",
                                    icon=get_icon('fileopen.png'),
                                    tip=_("Open an image"),
                                    triggered=self.stopOsciThr)
        #add_actions(file_menu, (triggerTest_action, saveData, None, self.quit_action))
        
        ##############
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

    def showMakeNicerWidget(self):
        self.makeNicerWidget = MakeNicerWidget(self)
        self.makeNicerDock = self.add_dockwidget(self.makeNicerWidget, 
            'Make FFT nicer')
        #self.makeNicerDock.setFloating(True)

        #self.fsBrowser = QDockWidget("4D Fermi Surface Browser", self)
        #self.fsWidget = FermiSurface_Widget(self)
        
        #self.fsBrowser.setWidget(self.fsWidget)
        #self.fsBrowser.setFloating(True)
        #self.addDockWidget(Qt.RightDockWidgetArea, self.fsBrowser)

        
    def closeEvent(self, event):
        if self.stage is not None:
            self.stage.CloseConnection()
        if self.console is not None:
            self.console.exit_interpreter()
        event.accept()

    def saveData(self):
        import datetime
        now = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')

        # save time domain
        foo = self.tdWidget.calcFun.functions
        texts = [self.tdWidget.calcFun.itemText(i) for i in range(len(foo))]
        tmp = ['td_x_{:s},td_y_{:s}'.format(i, i) for i in texts] 
        header = ','.join(tmp)
        dataTd = np.zeros((self.tdSignal.getData(foo[0][0])[0].shape[0],
                          2*len(foo)))
        for i, fun in enumerate(foo):
            x, y =  self.tdSignal.getData(fun[0])# [0]: fun, [1]: inverse fun
            dataTd[:,2*i] = x
            dataTd[:,2*i+1] = y
        np.savetxt('data/{:s}_TD.txt'.format(now), dataTd, header=header)
        self.tdSignal.plot.save_widget('data/{:s}_TD.png'.format(now))
        
        # save frequency domain
        foo = self.fdWidget.calcFun.functions
        texts = [self.fdWidget.calcFun.itemText(i) for i in range(len(foo))]
        tmp = ['fd_x_{:s},fd_y_{:s}'.format(i, i) for i in texts] 
        header += ','.join(tmp)
        dataFd = np.zeros((self.fdSignal.getData(foo[0][0])[0].shape[0],
                          2*len(foo)))
        for fun in foo:
            x, y = self.fdSignal.getData(fun[0])
            dataFd[:,2*i] = x
            dataFd[:,2*i+1] = y
        np.savetxt('data/{:s}_FD.txt'.format(now), dataFd, header=header)
        self.fdSignal.plot.save_widget('data/{:s}_FD.png'.format(now))

        # TODO: maybe put this in status bar
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText('Data saved')
        msg.exec_()
               

    #def getStage(self, gcs):
    #    self.stage = gcs
    #    print(dir(self.stage))
    #    print(self.stage.qPOS())

    def startOsciThr(self):
        self.stopOsci = False
        #self.osciThr.start()
        self.osciWorker.start.emit()
    def stopOsciThr(self):
        self.stopOsci = True
        # TODO: not quite shure how to do this with the worker solution.
        # finished signal is emitted but this function should wait for worker to finish?!?
        while(self.osciWorker.isRunning()):
            time.sleep(0.03)
    def getOsciData(self):
        while not self.stopOsci:
            data = self.tiepieUi.getData()
            self.updateOsciPlot.emit(data)
            time.sleep(0.5)

    def startMeasureThr(self):
        # stop osci thread and start measure thread
        self.stopOsciThr()
        
        # rescale tdPlot (updateXAxe)
        self.piUi._xAxeChanged()

        # set vCursor to 0
        self.tdSignal.setVCursor(0)
        self.piUi.setCenter()

        # init x axe frequency domain plot to a min and max
        delays = self.piUi.getDelays_fs()
        data = np.column_stack((delays, np.zeros(len(delays))))
        fdAxe = self.fdSignal.computeFFT(data)
        self.fdSignal.updateXAxe(fdAxe[0,0], fdAxe[-1,0])

        self.stopMeasure = False
        #self.measureThr.start()
        self.measureWorker.start.emit()
    def stopMeasureThr(self):
        self.stopMeasure = True
        while(self.measureWorker.isRunning()):
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
                #data[i,1] = tmp[:,1].mean()
                data[i,1] = self.osciSignal.computeSum()
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
