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
                              QDoubleValidator, QIntValidator,
                              QMenu, QApplication, QCursor, QFont, QPushButton,
                              QSlider, QIcon)
from guidata.qt.QtCore import (Qt, QT_VERSION_STR, PYQT_VERSION_STR, Signal,
                               Slot, QThread, QMutex, QMutexLocker)
from guidata.qt import PYQT5
from guidata.qt.compat import getopenfilenames, getsavefilename

import sys
import platform
import os.path as osp
import os
import numpy as np
import time

from guidata.dataset.datatypes import DataSet, ValueProp
from guidata.dataset.dataitems import (IntItem, FloatArrayItem, StringItem,
                                       ChoiceItem, FloatItem, DictItem,
                                       BoolItem)
from guidata.dataset.qtwidgets import DataSetEditGroupBox
from guidata.configtools import get_icon
from guidata.qthelpers import create_action, add_actions, get_std_icon
from guidata.qtwidgets import DockableWidget, DockableWidgetMixin
from guidata.utils import update_dataset
from guidata.py3compat import to_text_string

from guiqwt.config import _
from guiqwt.plot import CurveWidget, ImageWidget
from guiqwt.builder import make

from pipython import GCSDevice, pitools
import libtiepie

APP_NAME = _("FTIR")
APP_DESC = _("""Record a spectrum using a michelson<br>
interferometer with a delay stage""")
VERSION = '0.0.1'

class ObjectFT(QSplitter):
    """Object handling the item list, the selected item properties and plot"""
    def __init__(self, parent, plot):
        super(ObjectFT, self).__init__(Qt.Vertical, parent)
        self.plot = plot
        self.curve = make.curve(np.arange(1000), np.zeros(1000), color='b')
        
        self.plot.add_item(self.curve)

    @Slot(object, object)
    def updateXAxes(self, xMin=0, xMax=1000):
        self.plot.set_axis_limits('bottom', xMin, xMax)
        
    
    @Slot(object)
    def updatePlot(self, data):
        self.curve.setData(data[:,0], data[:,1])
        #self.plot.plot.replot()
        


class SignalFT(ObjectFT):
    #------ObjectFT API
    def setup(self, toolbar):
        ObjectFT.setup(self, toolbar)

class TiePieUi(QSplitter):
    '''
    Handling user interface to manage TiePie HS4/Diff Oscilloscope
    '''
    scpConnected = Signal()
    axisChanged = Signal(object, object)
    def __init__(self, parent):
        #super(ObjectFT, self).__init__(Qt.Vertical, parent)
        super().__init__(parent)

        self.scp = None # variable to hold oscilloscope object
        self.mutex = QMutex()
        
        layoutWidget = QWidget()
        layout = QGridLayout()
        layoutWidget.setLayout(layout)

        self.openDevBtn = QPushButton('Open Osci')
        self.measCh = QComboBox()
        #self.measCh.addItems(('Ch1', 'Ch2', 'Ch3', 'Ch4'))
        self.chSens = QComboBox()
        self.triggCh = QComboBox()
        self.triggLevel =  QLineEdit()
        self.triggLevel.setValidator(QDoubleValidator(0, 1, 3))
        self.frequency  = QLineEdit()
        self.frequency.setValidator(QIntValidator())
        self.recordLen = QLineEdit()
        self.recordLen.setValidator(QIntValidator())
        self.delay = QLineEdit()
        self.delay.setValidator(QDoubleValidator())
        self.averages = QSpinBox()
        self.averages.setValue(1)
        self.averages.setRange(1, 10000)
        
        # put layout together
        layout.addWidget(self.openDevBtn, 0, 0)
        layout.addWidget(QLabel('Measuring Ch'), 1, 0)
        layout.addWidget(self.measCh, 1, 1)
        layout.addWidget(QLabel('Ch sensitivity'), 2, 0)
        layout.addWidget(self.chSens, 2, 1)
        layout.addWidget(QLabel('Trigger Ch'), 3, 0)
        layout.addWidget(self.triggCh, 3, 1)
        layout.addWidget(QLabel('Trigger Level'), 4, 0)
        layout.addWidget(self.triggLevel, 4, 1)
        layout.addWidget(QLabel('Sample freq. (kHz)'), 5, 0)
        layout.addWidget(self.frequency, 5, 1)
        layout.addWidget(QLabel('Record length'), 6, 0)
        layout.addWidget(self.recordLen, 6, 1)
        layout.addWidget(QLabel('Delay'), 7, 0)
        layout.addWidget(self.delay, 7, 1)
        layout.addWidget(QLabel('Averages'), 8, 0)
        layout.addWidget(self.averages, 8, 1)
        layout.setRowStretch(9, 10)
        layout.setColumnStretch(2,10)

        self.addWidget(layoutWidget)

        # connect UI to get things working
        self.openDevBtn.released.connect(self.openDev)
        self.frequency.returnPressed.connect(self._changeFreq)
        self.recordLen.returnPressed.connect(self._changeRecordLength)

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
            self.scp.range = 8
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
            self.measCh.addItems(['Ch{:d}'.format(i) for i in range(self.scp.channels.count)])
            self.chSens.addItems(['{:.1f} V'.format(i) for i in self.scp.channels[0].ranges])
            self.triggCh.addItems(['Ch{:d}'.format(i) for i in range(self.scp.channels.count)])
            self.frequency.setValidator(QIntValidator(1, 1e-3*self.scp.sample_frequency_max))
            self.frequency.setText('{:d}'.format(int(self.scp.sample_frequency*1e-3)))
            self.triggLevel.setText(str(ch.trigger.levels[0]))
            self.recordLen.setValidator(QIntValidator(1, self.scp.record_length_max))
            self.recordLen.setText('{:d}'.format(self.scp.record_length))
            self.openDevBtn.setEnabled(False)
            
            # the world that the scope is connected
            self.axisChanged.emit(0, 1/int(self.frequency.text())*1e-3*int(self.recordLen.text()))
            self.scpConnected.emit()
            
        else:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText('No supported device found')
            msg.exec_()

    def getData(self):
        # function called thread for updating plot
        with QMutexLocker(self.mutex):
            self.scp.start()
            while not self.scp.is_data_ready:
                time.sleep(0.01)
            y = self.scp.get_data()[self.measCh.currentIndex()]
            x = np.linspace(0,
                            1/self.scp.sample_frequency*self.scp.record_length,
                            self.scp.record_length)
            return np.column_stack((x, y))

    def _changeFreq(self):
        with QMutexLocker(self.mutex):
            self.scp.sample_frequency = int(self.frequency.text())*1e3
            self.axisChanged.emit(0, 1/self.scp.sample_frequency*self.scp.record_length)

    def _changeRecordLength(self):
        with QMutexLocker(self.mutex):
            self.scp.record_length = int(self.recordLen.text())
            self.axisChanged.emit(0, 1/self.scp.sample_frequency*self.scp.record_length)

     
class PiStageUi(QSplitter):
    stageConnected = Signal()
    def __init__(self, parent):
        #super(ObjectFT, self).__init__(Qt.Vertical, parent)
        super().__init__(parent)

        self.stage = None

        layoutWidget = QWidget()
        layout = QGridLayout()
        layoutWidget.setLayout(layout)
       
        # put layout together
        self.openStageBtn = QPushButton("Open stage")
        self.initStageBtn = QPushButton("Init stage")
        
        
        #absolute move
        #current position
        self.currentPosition = QLineEdit()
        self.currentPosition.setValidator(QDoubleValidator())
        #relative move (mm)
        self.deltaMove_mm = QLineEdit()
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
        self.velocity.setMaximum(2000) # TODO: try to get max vel. from controller

        # put layout together
        layout.addWidget(self.openStageBtn, 0, 0)
        layout.addWidget(self.initStageBtn, 0, 1)
        layout.addWidget(QLabel("Current pos (mm)"), 1, 0)
        layout.addWidget(self.currentPosition, 1, 1)
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
        layout.setRowStretch(10, 10)
        layout.setColumnStretch(2,10)

        self.addWidget(layoutWidget)

        # make button and stuff functional
        self.openStageBtn.released.connect(self.connectStage)
        self.initStageBtn.released.connect(self.initStage)

    def connectStage(self):
        gcs = GCSDevice()
        try:
            gcs.InterfaceSetupDlg()
            #print(gcs.qIDN())
            #print(gcs.qPOS())
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText(gcs.qIDN())
            msg.exec_()
            self.stage = gcs
        except:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText('Could not connect stage')
            msg.exec_()

    def initStage(self):
        if self.stage is not None:
            # TODO: give choice to select stage
            pitools.startup(self.stage, stages='M-112.1DG-NEW', refmode='FNL')
            # TODO: show dialog for waiting
            self.velocityLabel.setText(
                'Velocity: {:f}mm/s'.format(self.stage.qVEL()['1']))
            self.velocity.setValue(int(1000*self.stage.qVEL()['1']))
            self.stageConnected.emit()
        else:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText('No stage connected')
            msg.exec_()

    def gotoPos(self):
        self.stage.MOV(self.stage.axes, 20)
        while not pitools.ontarget(self.stage, '1'):
            print('moving')
            time.sleep(1)
        
class ScanningUi(QSplitter):
    def __init__(self, parent):
        #super(ObjectFT, self).__init__(Qt.Vertical, parent)
        super().__init__(parent)

        layoutWidget = QWidget()
        layout = QGridLayout()
        layoutWidget.setLayout(layout)

        
        # scan from (fs)
        self.scanFrom = QLineEdit()
        self.scanFrom.setValidator(QDoubleValidator())
        # scan to (fs)
        self.scanTo = QLineEdit()
        self.scanTo.setValidator(QDoubleValidator())
        # center here button
        self.centerBtn = QPushButton('Center here')
        self.goBtn = QPushButton("Scan")
        self.stopBtn = QPushButton("Stop")
        
        # put layout together
        layout.addWidget(QLabel('Scan from'), 0, 0)
        layout.addWidget(self.scanFrom, 0, 1)
        layout.addWidget(QLabel('Scan to'), 1, 0)
        layout.addWidget(self.scanTo, 1, 1)
        layout.addWidget(self.centerBtn, 2, 1)
        layout.addWidget(self.goBtn, 4, 0)
        layout.addWidget(self.stopBtn, 4, 1)
        layout.setRowStretch(5,10)
        #layout.setRowStretch(3,1)
        layout.setColumnStretch(2,10)

        self.addWidget(layoutWidget)

        # make button and stuff functional
        

class DockablePlotWidget(DockableWidget):
    LOCATION = Qt.RightDockWidgetArea
    def __init__(self, parent, plotwidgetclass, toolbar):
        super(DockablePlotWidget, self).__init__(parent)
        self.toolbar = toolbar
        layout = QVBoxLayout()
        self.plotwidget = plotwidgetclass()
        layout.addWidget(self.plotwidget)
        self.setLayout(layout)
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
        self.function(*self.args,**self.kwargs)
        return

class SiftProxy(object):
    def __init__(self, win):
        self.win = win
        #self.s = self.win.signalft.objects


class MainWindow(QMainWindow):
    updateOsciPlot = Signal(object)
    def __init__(self):
        QMainWindow.__init__(self)

        self.stage = None
        self.stopOsci = False
        
        self.setWindowTitle(APP_NAME)

        # Osci live
        curveplot_toolbar = self.addToolBar(_("Curve Plotting Toolbar"))
        self.osciCurveWidget = DockablePlotWidget(self, CurveWidget,
                                              curveplot_toolbar)
        osciPlot = self.osciCurveWidget.get_plot()
        #osciplot.add_item(make.legend("TR"))
        self.osciSignal = SignalFT(self, plot=osciPlot)        
        
        # Time Domain
        self.tdWidget = DockablePlotWidget(self, CurveWidget,
                                              curveplot_toolbar)
        tdPlot = self.tdWidget.get_plot()
        #tdPlot.add_item(make.legend("TR"))
        self.tdSignal  = SignalFT(self, plot=tdPlot)

        # Frequency Domain
        self.fqdWidget = DockablePlotWidget(self, CurveWidget,
                                              curveplot_toolbar)
        fqdplot = self.fqdWidget.get_plot()
        #fqdplot.add_item(make.legend("TR"))
        self.fqSignal  = SignalFT(self, plot=fqdplot)

        # Main window widgets
        self.tabwidget = DockableTabWidget(self)
        #self.tabwidget.setMaximumWidth(500)
        self.tiepieUi = TiePieUi(self)
        self.piUi = PiStageUi(self)
        #self.stage = self.piUi.stage
        self.scanningUi = ScanningUi(self)
        self.tabwidget.addTab(self.tiepieUi, QIcon('Handyscope_HS4.png'),
                              _("Osci"))
        self.tabwidget.addTab(self.piUi, get_icon('piController.png'),
                              _("Stage"))
        self.tabwidget.addTab(self.scanningUi, get_icon('image.png'),
                              _("Scanning"))
        self.add_dockwidget(self.tabwidget, _("Inst. sett."))
#        self.setCentralWidget(self.tabwidget)
        self.osci_dock = self.add_dockwidget(self.osciCurveWidget,
                                              title=_("Osciloscope"))
        self.td_dock = self.add_dockwidget(self.tdWidget,
                                              title=_("Time Domain"))
        self.fqd_dock = self.add_dockwidget(self.fqdWidget,
                                              title=_("Frequency Domain"))


        # connect signals
        #self.piUi.stageConnected.connect(self.s)
        self.tiepieUi.scpConnected.connect(self.startOsciThr)
        self.tiepieUi.axisChanged.connect(self.osciSignal.updateXAxes)
        self.osciThr = GenericThread(self.getOsciData)
        self.updateOsciPlot.connect(self.osciSignal.updatePlot)
        

        
        # File menu
        file_menu = self.menuBar().addMenu(_("File"))
        self.quit_action = create_action(self, _("Quit"), shortcut="Ctrl+Q",
                                    icon=get_std_icon("DialogCloseButton"),
                                    tip=_("Quit application"),
                                    triggered=self.close)
        triggerTest_action = create_action(self, _("test..."),
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
            msg = "Example: sift.s[0] returns signal object #0\n"\
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
        

def run():
    from guidata import qapplication
    app = qapplication()
    window = MainWindow()
    window.show()
    app.exec_()


if __name__ == '__main__':
    run()


