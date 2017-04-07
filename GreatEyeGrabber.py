# -*- coding: utf-8 -*-
#
# Copyright © 2016-2017 CEA
# Hubertus Bromberger
# Licensed under the terms of the GPL License

"""
Read and plot Great Eye Camera
"""

from guidata.qt.QtGui import (QMainWindow, QMessageBox, 
                              QSpinBox, QHBoxLayout,
                              QVBoxLayout, QGridLayout,  
                              QTabWidget, QLabel, QLineEdit,  
                              QFont, QIcon)
from guidata.qt.QtCore import (Qt, Signal, QThread, QLocale, QDir)
from guidata.qt import PYQT5
#from guidata.qt.compat import getopenfilenames, getsavefilename
#from guiqwt.signals import SIG_MARKER_CHANGED

import sys
#import platform
import os.path as osp
import os
import numpy as np
import time
import datetime

#from guidata.dataset.datatypes import DataSet, ValueProp
#from guidata.dataset.dataitems import (IntItem, FloatArrayItem, StringItem,
#                                       ChoiceItem, FloatItem, DictItem,
#                                       BoolItem)
#from guidata.dataset.qtwidgets import DataSetEditGroupBox
from guidata.configtools import get_icon
from guidata.qthelpers import create_action, add_actions, get_std_icon
from guidata.qtwidgets import DockableWidgetMixin
from guiqwt.plot import CurveWidget, ImageWidget
#from guidata.utils import update_dataset
#from guidata.py3compat import to_text_string

from guiqwt.config import _

# local imports
from scipy.io import savemat
from Helpers.plotSignal import SignalFT, ImageFT, DockablePlotWidget
from Helpers.genericthread import GenericWorker
from Instruments.greatEyes import GreatEyesUi

# set default language to c, so decimal point is '.' not ',' on german systems
QLocale.setDefault(QLocale.c())
APP_NAME = _("XUV Spectrometer")
APP_DESC = _("""Get data from """)
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
    updateCameraPlot = Signal(object)
    updateLineOutPlot = Signal(object)
    def __init__(self):
        QMainWindow.__init__(self)

        self.stopAcqui = False
        
        self.setWindowTitle(APP_NAME)

        ##############
        # Camera image
        self.image_toolbar = self.addToolBar(_("Image Processing Toolbar")) 
        imagevis_toolbar = self.addToolBar(_("Image Visualization Toolbar")) 
        self.imageWidget1 = DockablePlotWidget(self, ImageWidget,
                                              imagevis_toolbar)
        self.image1 = ImageFT(self, self.imageWidget1.get_plot())
        self.image1.addHCursor(1)
        self.image1.addRoi(0, 1, 2048, 1)
        #self.image1.setup(self.image_toolbar)
        
        ###############
        # camera line out
        curveplot_toolbar = self.addToolBar(_("Curve Plotting Toolbar"))
        self.curveWidget1 = DockablePlotWidget(self, CurveWidget,
                                              curveplot_toolbar)
        self.curveWidget1.calcFun.addFun('s', lambda x: x,
                                              lambda x: x)
        plot1 = self.curveWidget1.get_plot()
        self.signal1 = SignalFT(self, plot=plot1)
        

        ##############
        # Main window widgets
        # status bar
        self.status = self.statusBar()
        # widgets
        self.tabwidget = DockableTabWidget(self)
        #self.tabwidget.setMaximumWidth(500)
        self.greateyesUi = GreatEyesUi(self)
        self.tabwidget.addTab(self.greateyesUi, 
                QIcon('icons/Handyscope_HS4.png'), _("greateyes"))
        #self.fileUi = FileUi(self)
        #self.tabwidget.addTab(self.fileUi, get_icon('filesave.png'), _('File'))
        self.add_dockwidget(self.tabwidget, _("Inst. sett."))
#        self.setCentralWidget(self.tabwidget)
        self.dock1 = self.add_dockwidget(self.imageWidget1,
                                              title=_("Camera"))
        self.dock2 = self.add_dockwidget(self.curveWidget1,
                                              title=_("Lineout"))

        ################
        # connect signals
        self.greateyesUi.newPlotData.connect(self.newData)
        self.greateyesUi.message.connect(self.updateStatus)
        self.image1.plot.SIG_MARKER_CHANGED.connect(self.cursorMoved)
        self.greateyesUi.loi.valueChanged.connect(self.cursorMoved)
        self.greateyesUi.deltaPixels.valueChanged.connect(self.cursorMoved)

        #self.curveWidget1.calcFun.idxChanged.connect(self.signal1.funChanged)
        #self.fileUi.saveTxtBtn.released.connect(self.saveDataTxt)
        #self.fileUi.saveHdfBtn.released.connect(self.saveDataHDF5)
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
        # File menu
        '''
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
        '''
        
        ##############
        # Eventually add an internal console (requires 'spyderlib')
        self.console = None
        '''
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
        self.greateyesUi.closeEvent(event)
        if self.console is not None:
            self.console.exit_interpreter()
        event.accept()

    def newData(self, image, timeStamp):
        self.image1.updatePlot(image, 
                timeStamp.isoformat() + ", " +
                str(self.greateyesUi.cameraSettings['temperature']) +
                "°C")
        self.updateLineOut(image)
        self.saveDataHDF5(image, timeStamp)

    def updateStatus(self, msg):
        self.status.showMessage(msg, 10000)

    def updateLineOut(self, image):
        loi  = self.greateyesUi.loi.value()
        dLoi = self.greateyesUi.deltaPixels.value()
        data = image[(loi-dLoi):(loi+dLoi+1),:]
        self.signal1.updatePlot(np.column_stack((np.arange(0,
               data.shape[1]), data.sum(axis=0))))
        self.image1.setHCursor(loi)
        self.image1.setRoi(0, loi-dLoi, 2048, loi+dLoi)

               
    def saveDataHDF5(self, image, timeStamp):
        if not self.greateyesUi.autoSave.isChecked():
            return
        zeit = timeStamp.strftime('%Y%m%d-%H%M%S')
        fileName = self.greateyesUi.directory + "/" + zeit
        #fileName = QDir.toNativeSeparators(fileName)
        print(fileName)

        # save matlab file
        savemat(fileName, {'image': image, 
            'comment': self.greateyesUi.comment.toPlainText(),
            'camera_settings': self.greateyesUi.cameraSettings})
        # save images
        self.image1.plot.save_widget(fileName + '_image.png')
        self.signal1.plot.save_widget(fileName + '_lineout.png')

        self.status.showMessage(fileName + " saved", 10000)

        
        # TODO: maybe put this in status bar
        '''
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText('Data saved')
        msg.exec_()
        '''

    def cursorMoved(self, mouse):
        if not isinstance(mouse, int): # true if cursor moved by mouse
            cursorVal = int(self.image1.getHCursor())
            self.greateyesUi.loi.setValue(cursorVal)
        else:
            cursorVal = self.greateyesUi.loi.value()  
        self.image1.setHCursor(cursorVal)
        roi = self.greateyesUi.deltaPixels.value()
        self.image1.setRoi(0, cursorVal-roi, 2048, cursorVal+roi)


def run():
    from guidata import qapplication
    app = qapplication()
    window = MainWindow()
    window.show()
    app.exec_()


if __name__ == '__main__':
    run()
