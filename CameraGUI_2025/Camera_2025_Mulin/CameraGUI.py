import sys
import types

# --- Import your ANDOR module ---
import ANDOR

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QRadioButton, QGroupBox, QLabel)
from PyQt5.QtCore import QObject, pyqtSignal

# --- Import the real Camera class ---
from camera import Camera  # Make sure camera.py is in the same directory


# --- Mocks for other application parts (same as before) ---
class MockPlotDataItem:
    def __init__(self, pen): self.opts = {'pen': pen}

    def setData(self, *args, **kwargs): pass


class MockPlotObject:
    def plot(self, *args, **kwargs): return MockPlotDataItem(pen=kwargs.get('pen', 'r'))

    def clear(self): pass


class MockProject:
    def __init__(self): self.baseDir, self.projectDir = "./", "./images"

    def isEnabled(self, cat, name): return True


class MockScanExperiment:
    def __init__(self):
        scan_list = [types.SimpleNamespace(magnitude=i) for i in range(1, 6)]
        mock_scan = types.SimpleNamespace(list=scan_list)
        self.scanControlWidget = types.SimpleNamespace(getScan=lambda: mock_scan)
        self.camera = None
        self.cameraEnabled = False
        self.plotDict = {"Camera": {"view": MockPlotObject()}}


class MockPulseProgramDialog:
    def __init__(self):
        mock_context = types.SimpleNamespace(parameters={})
        self.pulseProgramSet = {'ScanExperiment': types.SimpleNamespace(currentContext=mock_context)}


class MockGlobalVariablesUi(QObject):
    valueChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.globalDict = {}


class MockConfig:
    def __init__(self): self._config_data = {}

    def get(self, key, default=None): return self._config_data.get(key, default)

    def __contains__(self, key): return key in self._config_data


MockShutterUi = object


# --- Main Application Launcher Window ---
class CameraLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camera Launcher")
        self.setGeometry(100, 100, 300, 200)

        # Instantiate mock objects
        self.project = MockProject()
        self.scanExperiment = MockScanExperiment()
        self.config = MockConfig()
        self.globalVariablesUi = MockGlobalVariablesUi()
        self.shutterUi = MockShutterUi()
        self.pulseProgramDialog = MockPulseProgramDialog()
        self.CameraWindow = None

        # --- Create the UI layout ---
        self.central_widget = QWidget()
        self.layout = QVBoxLayout(self.central_widget)
        self.setCentralWidget(self.central_widget)

        mode_box = QGroupBox("Select Camera Mode")
        mode_layout = QVBoxLayout()
        self.radio_real = QRadioButton("Real Camera (Hardware Required)")
        self.radio_debug = QRadioButton("Debug Mode (Simulated Hardware)")

        # Check the default mode from ANDOR.py
        if ANDOR.DEBUG_MODE:
            self.radio_debug.setChecked(True)
        else:
            self.radio_real.setChecked(True)

        mode_layout.addWidget(self.radio_real)
        mode_layout.addWidget(self.radio_debug)
        mode_box.setLayout(mode_layout)

        self.launch_button = QPushButton("Show Camera")
        self.launch_button.clicked.connect(self.launch_camera_window)

        self.layout.addWidget(mode_box)
        self.layout.addStretch()
        self.layout.addWidget(self.launch_button)

    def launch_camera_window(self):
        """Sets the debug flag in ANDOR.py and then creates the camera window."""

        if self.CameraWindow and self.CameraWindow.isVisible():
            self.CameraWindow.activateWindow()
            return

        # --- KEY CHANGE: Set the global variable in the ANDOR module ---
        if self.radio_real.isChecked():
            ANDOR.DEBUG_MODE = False
            print("Set ANDOR.DEBUG_MODE = False")
        else:
            ANDOR.DEBUG_MODE = True
            print("Set ANDOR.DEBUG_MODE = True")

        # Create the Camera window instance normally.
        # It will now use the ANDOR module with the correct debug setting.
        self.CameraWindow = Camera(
            self.config, self.globalVariablesUi, self.shutterUi,
            self.scanExperiment, self.pulseProgramDialog,
            parent=self
        )
        self.CameraWindow.setupUi(self.CameraWindow)
        self.scanExperiment.camera = self.CameraWindow
        self.scanExperiment.cameraEnabled = True

        self.CameraWindow.show()


# --- Standard Python entry point to run the application ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    launcher = CameraLauncher()
    launcher.show()
    sys.exit(app.exec_())