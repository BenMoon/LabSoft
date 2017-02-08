# -*- coding: utf-8 -*-
"""
Created on Wed Feb  8 09:02:57 2017

@author: 15604la
"""

from guidata.qt.QtCore import (QThread)

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