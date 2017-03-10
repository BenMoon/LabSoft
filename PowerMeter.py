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
from Helpers.fileui import FileUi
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
        self.fileUi = FileUi(self)
        self.tabwidget.addTab(self.maestroUi, QIcon('icons/Handyscope_HS4.png'),
                              _("Maestro"))
        self.tabwidget.addTab(self.fileUi, get_icon('filesave.png'), _('File'))
        self.add_dockwidget(self.tabwidget, _("Inst. sett."))
#        self.setCentralWidget(self.tabwidget)
        self.dock1 = self.add_dockwidget(self.curveWidget1,
                                              title=_("Powermeter"))

        ################
        # connect signals
        self.maestroUi.newPlotData.connect(self.signal1.updatePlot)
        self.curveWidget1.calcFun.idxChanged.connect(self.signal1.funChanged)
        self.fileUi.saveTxtBtn.released.connect(self.saveDataTxt)
        self.fileUi.saveHdfBtn.released.connect(self.saveDataHDF5)
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
                                    triggered=self.saveDataHDF5)
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
        
    def closeEvent(self, event):
        self.maestroUi.closeEvent(event)
        if self.console is not None:
            self.console.exit_interpreter()
        event.accept()

    def saveDataTxt(self):
        import datetime
        now = datetime.datetime.now().strftime('%Y%m%d-%H%M%S_Maestro')

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
        for i, fun in enumerate(foo):
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
               
    def saveDataHDF5(self, fileName=None):
        import datetime
        import h5py

        # isoformat, seconds, value
        if fileName is None:
            now = datetime.datetime.now().strftime('%Y%m%d-%H%M%S_Power')
        else:
            now = fileName + '_Power'
        with h5py.File('data/{:s}.h5'.format(now)) as f:
            f.attrs['comments'] = self.fileUi.comment.toPlainText()
            f.attrs['detector'] = ''
            f.attrs['detector_settings'] = ''

            # save powermeter data
            dt = np.dtype([('iso_time', 'S26'), 
                   ('seconds', np.float),
                   ('power', np.float)])
            data = np.asarray(self.maestroUi.measureData, dtype=dt)
            dset = f.create_dataset('power', data=data)
            dset.attrs['device'] = 'Gentec Maestro'
            dset.attrs['device_serial'] = '1234'
            self.signal1.plot.save_widget('data/{:s}.png'.format(now))    

        # TODO: maybe put this in status bar
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText('Data saved')
        msg.exec_()


def run():
    from guidata import qapplication
    app = qapplication()
    window = MainWindow()
    window.show()
    app.exec_()


if __name__ == '__main__':
    run()
