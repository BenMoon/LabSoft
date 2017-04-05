# module for plotting data in dockwidget


#from __future__ import unicode_literals, print_function, division

from guidata.qt.QtGui import (QSplitter, QComboBox, QVBoxLayout)
from guidata.qt.QtCore import (Qt, Signal)

from guidata.py3compat import to_text_string
from guidata.qtwidgets import DockableWidget
from guiqwt.plot import ImageWidget
from guiqwt.builder import make

import numpy as np




class ObjectFT(QSplitter):
    """Object handling the item list, the selected item properties and plot"""
    def __init__(self, parent, plot, col='b'):
        super(ObjectFT, self).__init__(Qt.Vertical, parent)
        self.plot = plot
        self.curve = make.curve([], [], color=col)
        self.plot.add_item(self.curve)

        self.hCursor = None
        self.vCursor = None
        self.xRange = None # holds limits of bounds
        self.xMinMax = None # holds limits of data min and max, necessary to initialize once before axis change is possible
        self.scaleFun = lambda x: x
        self.scaleFunInv = lambda x: x

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
        self.plot.set_axis_limits('bottom', self.scaleFun(xMin), self.scaleFun(xMax))
        self.xMinMax = (self.scaleFun(xMin), self.scaleFun(xMax))
        #print('updateXAxe', self.xMinMax, xMin, xMax)
        if self.xRange is not None:
            self.xRange.set_range(self.scaleFun(xMin), self.scaleFun(xMax))
        
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

    def funChanged(self, functions):
        '''Slot for changing the x axis scanle function'''
        fun, funInv = functions
        x, y = self.curve.get_data()
        if self.xMinMax is not None:
            xMin, xMax = self.xMinMax
        else:
            #print('Error: please get data first before changing axis')
            #return
            xMin, xMax = x.min(), x.max()
        if xMin != 0:
            xMin = self.scaleFunInv(xMin) # get back to original value
        if xMax != 0:
            xMax = self.scaleFunInv(xMax)
        x    = self.scaleFunInv(x)
        self.scaleFun = fun
        self.scaleFunInv = funInv
        
        #self.updateXAxe(xMin, xMax) # TODO: check if this also workes with FTIR
        # replot data on new axis
        self.updatePlot(np.column_stack((x, y)))
        #print(fun(self.xRange[0]), fun(self.xRange[1]))       

    def computeSum(self):
        '''Compute the integral of signal in given bounds'''
        x, y = self.curve.get_data()
        xMin, xMax = self.xRange.get_range()
        xMinIdx = x.searchsorted(xMin)
        xMaxIdx = x.searchsorted(xMax)
        return y[xMinIdx:xMaxIdx+1].max()# - y[xMinIdx:xMaxIdx+1].min()

    def getData(self, fun):
        x, y = self.curve.get_data()
        return fun(x), y
        

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
        frq = frq[np.arange(1, int(n/2)+1)] # one side frequency range
              
        Y = np.fft.fft(y)/n # fft computing and normalization
        Y = Y[range(int(n/2))]
              
        data = np.column_stack((frq, abs(Y)))
        return data
    
    def smooth(self, x, window_len=11, window='hanning'):
        """smooth the data using a window with requested size.

        This method is based on the convolution of a scaled window with the signal.
        The signal is prepared by introducing reflected copies of the signal
        (with the window size) in both ends so that transient parts are minimized
        in the begining and end part of the output signal.

        input:
            x: the input signal
            window_len: the dimension of the smoothing window; should be an odd integer
            window: the type of window from 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'
                flat window will produce a moving average smoothing.

        output:
            the smoothed signal

        example:

        t=linspace(-2,2,0.1)
        x=sin(t)+randn(len(t))*0.1
        y=smooth(x)

        see also:

        numpy.hanning, numpy.hamming, numpy.bartlett, numpy.blackman, numpy.convolve
        scipy.signal.lfilter

        TODO: the window parameter could be the window itself if an array instead of a string
        NOTE: length(output) != length(input), to correct this: return y[(window_len/2-1):-(window_len/2)] instead of just y.

        http://scipy-cookbook.readthedocs.io/items/SignalSmooth.html
        """

        if x.ndim != 1:
            raise(ValueError, "smooth only accepts 1 dimension arrays.")

        if x.size < window_len:
            raise(ValueError, "Input vector needs to be bigger than window size.")

        if window_len<3:
            return x

        if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
            raise(ValueError, "Window is on of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")

        s=np.r_[x[window_len-1:0:-1],x,x[-1:-window_len:-1]]
        #print(len(s))
        if window == 'flat': #moving average
            w=np.ones(window_len,'d')
        else:
            w=eval('np.'+window+'(window_len)')

        y = np.convolve(w/w.sum(),s,mode='valid')

        return y

class SignalFT(ObjectFT):
    #------ObjectFT API
    def setup(self, toolbar):
        ObjectFT.setup(self, toolbar)


class ImageFT(QSplitter):
    def __init__(self, parent, plot):
        super(ImageFT, self).__init__(Qt.Vertical, parent)
        self.plot = plot
        self.image = make.image(np.zeros((512, 2048)))
        self.plot.add_item(self.image)
        
        self.hCursor = None
        self.roi = None

        self.scaleFun = lambda x: x
        self.scaleFunInv = lambda x: x

    #@Slot(object)
    def updatePlot(self, data, title=''):
        '''New data arrived and thus update the plot'''
        self.image.set_data(data)
        self.plot.setTitle(title)
        self.plot.replot()

    def getData(self, fun):
        pass
        #x, y = self.curve.get_data()
        #return fun(x), y
        
    def addHCursor(self, i):
        self.hCursor = make.hcursor(i)
        self.plot.add_item(self.hCursor)
    def setHCursor(self, i):
        self.hCursor.setYValue(i)

    def addRoi(self, x0=0, y0=0, x1=1, y1=1):
        self.roi = make.rectangle(x0, y0, x1, y1, "ROI")
        self.plot.add_item(self.roi)
    def setRoi(self, x0, y0, x1, y1):
        self.roi.set_rect(x0, y0, x1, y1)


class XAxeCalc(QComboBox):
    idxChanged = Signal(object)
    def __init__(self, parent):
        super(QComboBox, self).__init__(parent)
        self.functions = []
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setAlignment(Qt.AlignCenter)
        self.currentIndexChanged.connect(self.changed)

    def addFun(self, name, fun, funInv):
        self.functions.append((fun, funInv))
        self.addItem(name)

    def changed(self, idx):
        self.idxChanged.emit(self.functions[idx])
    
class DockablePlotWidget(DockableWidget):
    LOCATION = Qt.RightDockWidgetArea
    def __init__(self, parent, plotwidgetclass, toolbar=None):
        super(DockablePlotWidget, self).__init__(parent)
        self.toolbar = toolbar
        self.layout = QVBoxLayout()
        self.plotwidget = plotwidgetclass()
        self.layout.addWidget(self.plotwidget)
        self.calcFun = XAxeCalc(self)
        self.layout.addWidget(self.calcFun)
        self.setLayout(self.layout)
        if toolbar is None:
            self.setupNoTB()
        else:
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
 
    def setupNoTB(self):
        if isinstance(self.plotwidget, ImageWidget):
            self.plotwidget.register_all_image_tools()
        else:
            self.plotwidget.register_all_curve_tools()
       
    #------DockableWidget API
    def visibility_changed(self, enable):
        """DockWidget visibility has changed"""
        DockableWidget.visibility_changed(self, enable)
        self.toolbar.setVisible(enable)
