# -*- coding: utf-8 -*-
"""
Created on Wed Feb  8 09:02:57 2017

@author: Hubertus Bromberger
"""
from guidata.qt.QtCore import QObject, QThread, Signal, Slot


class GenericWorker(QObject):
    '''
    http://stackoverflow.com/questions/20324804/how-to-use-qthread-correctly-in-pyqt-with-movetothread
    http://ilearnstuff.blogspot.de/2012/09/qthread-best-practices-when-qthread.html
    '''
    start = Signal()
    finished = Signal()
    def __init__(self, function, *args, **kwargs):
        super(GenericWorker, self).__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.running = False
        self.start.connect(self.run)
        self.finished.connect(self.__changeRunning)

    @Slot()
    def run(self, *args, **kwargs):
        #print(args, kwargs)
        self.running = True
        self.function(*self.args, **self.kwargs)
        self.finished.emit()
        
    @Slot()
    def __changeRunning(self):
        '''
        Change running status variable
        '''
        self.running = False
        
    def isRunning(self):
        '''
        Query status of worker
        '''       
        return self.running




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
