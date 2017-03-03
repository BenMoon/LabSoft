# module for plotting data in dockwidget


#from __future__ import unicode_literals, print_function, division

from guidata.qt.QtGui import (QSplitter, QPushButton, QVBoxLayout, QLabel, QWidget, QTextEdit)
from guidata.qt.QtCore import (Qt, Signal)

import numpy as np



class FileUi(QSplitter):
    def __init__(self, parent):
        super(FileUi, self).__init__(Qt.Vertical, parent)

        layoutWidget = QWidget()
        layout = QVBoxLayout()
        layoutWidget.setLayout(layout)

        self.comment = QTextEdit()
        self.fileName = None
        self.saveTxtBtn = QPushButton('Save Txt')
        self.saveHdfBtn = QPushButton('Save HDF5')

        layout.addWidget(QLabel('Comment:'))
        layout.addWidget(self.comment)
        layout.addWidget(self.saveTxtBtn)
        layout.addWidget(self.saveHdfBtn)
        
        self.addWidget(layoutWidget)



        
if __name__ == '__main__':
    from guidata.qt.QtGui import QApplication
    import sys
    app = QApplication(sys.argv)
    #test = MyApp()
    test = FileUi(None)
    test.show()
    app.exec_()
