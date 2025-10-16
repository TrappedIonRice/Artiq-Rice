import sys

from PyQt5 import QtCore, QtGui, QtWidgets
from Camera.camera import Camera
import json

from GlobalVariables.GlobalVariablesUi import GlobalVariablesUi



app = QtWidgets.QApplication(sys.argv)

with open("ConfigGroup.json", encoding="utf-8") as f:
    # with open("Default.json", encoding="utf-8") as f:
    config = json.load(f)
# print(config)

globVUi = GlobalVariablesUi(config)
globVUi.setupUi(globVUi)
CameraGui = Camera(config, globVUi)
CameraGui.setupUi(CameraGui)
CameraGui.show()
sys.exit(app.exec_())