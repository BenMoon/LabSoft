# module for plotting data in dockwidget


#from __future__ import unicode_literals, print_function, division

from guidata.qt.QtGui import (QSplitter, QPushButton, QVBoxLayout, QHBoxLayout,
                              QGroupBox, QCheckBox, QLabel, QWidget, QPlainTextEdit)
from guidata.qt.QtCore import (Qt, Signal)

import numpy as np



class FileUi(QSplitter):
    def __init__(self, parent):
        super(FileUi, self).__init__(Qt.Vertical, parent)

        layoutWidget = QWidget()
        layout = QVBoxLayout()
        layoutWidget.setLayout(layout)

        self.comment = QPlainTextEdit()
        self.fileName = None
        self.saveTxtCheck = QCheckBox('Save Txt')
        self.saveHdfCheck = QCheckBox('Save HDF5')
        self.saveTxtBtn = QPushButton('Save Txt')
        self.saveHdfBtn = QPushButton('Save HDF5')

        #############
        # stream group
        streamGroup = QGroupBox('Stream data to file:')
        streamGroup.setFlat(True)
        streamGroupLayout = QHBoxLayout()
        streamGroupLayout.addWidget(self.saveTxtCheck)
        streamGroupLayout.addWidget(self.saveHdfCheck)
        streamGroup.setLayout(streamGroupLayout)

        ##############
        # save static file
        saveGroup = QGroupBox('Save now to file:')
        saveGroup.setFlat(True)
        saveGroupLayout = QHBoxLayout()
        saveGroupLayout.addWidget(self.saveTxtBtn)
        saveGroupLayout.addWidget(self.saveHdfBtn)
        saveGroup.setLayout(saveGroupLayout)

        ##############
        # put layout together
        layout.addWidget(QLabel('Comment:'))
        layout.addWidget(self.comment)
        layout.addWidget(streamGroup)
        layout.addWidget(saveGroup)
        self.addWidget(layoutWidget)

        ##############
        # connnect stuff for functionality
        self.saveTxtCheck.stateChanged.connect(self.__makeFileName)
        self.saveHdfCheck.stateChanged.connect(self.__makeFileName)

    def __makeFileName(self, state):
        from datetime import datetime
        
        print(state)
        if state == 2:
            self.fileName = datetime.now().strftime('%Y%m%d-%H%M%S')
        else:
            self.fileName = None
        print(self.fileName)

           
if __name__ == '__main__':
    from guidata.qt.QtGui import QApplication
    import sys
    app = QApplication(sys.argv)
    #test = MyApp()
    test = FileUi(None)
    test.show()
    app.exec_()
