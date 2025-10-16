from PyQt5 import QtCore, QtGui, QtWidgets
from Camera.camera import Camera
from GlobalVariables.GlobalVariablesUi import GlobalVariablesUi

import sys

app = QtWidgets.QApplication(sys.argv)

config = {}

globVUi = GlobalVariablesUi(config)
globVUi.setupUi(globVUi)
CameraGui = Camera(config, globVUi, None, None, None, None)
CameraGui.setupUi(CameraGui)
CameraGui.show()
sys.exit(app.exec_())