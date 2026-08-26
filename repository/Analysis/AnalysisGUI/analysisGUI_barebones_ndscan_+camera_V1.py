import sys
import os
import time
import json
import random
import datetime
import numpy as np
import scipy.optimize

from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor

import pyqtgraph as pg
from pyqtgraph import PlotWidget
from pyqtgraph.dockarea import *

# Experiment / ARTIQ imports
from ndscan.experiment import *
from oitg import *
from oitg.results import *
from oitg.fitting import *
import FitFunctions_barebones_ndscan as fitfunc

'''
Simple Analysis GUI for experiment feedback (1D Plots & 2D Heatmaps).
'''


class DockArea(DockArea):
    ## Prevent the Dock from being resized to the point of disappearing
    def makeContainer(self, typ):
        new = super(DockArea, self).makeContainer(typ)
        new.setChildrenCollapsible(False)
        return new


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super(MainWindow, self).__init__()
        print("Initializing Analysis Window...")
        self.setWindowTitle("Analysis Window")

        layout = QtWidgets.QVBoxLayout()
        dock_area = DockArea(self)

        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Plotting Dock
        self.plotdock = Dock("AnalysisPlot", size=(600, 400))
        self.graphWidget = AnalysisPlotWidget()  # Defined in Part 2
        self.plotdock.addWidget(self.graphWidget)
        self.plotdock.setGeometry(0, 0, 1000, 500)

        # Search and Fitting Dock
        self.searchFitDock = Dock("Search&Fit", size=(600, 400))
        self.searchFitDock.setMaximumWidth(600)
        searchFitlayout = QtWidgets.QVBoxLayout()
        self.searchFitWidget = SearchFitWidget(self.graphWidget)
        self.searchFitDock.setLayout(searchFitlayout)
        self.searchFitDock.addWidget(self.searchFitWidget)

        layout.addWidget(dock_area)
        dock_area.addDock(self.searchFitDock)
        dock_area.addDock(self.plotdock, 'right', self.searchFitDock)

        self.show()


# Assume fitfunc, find_results, load_hdf5_file are imported from your project utilities


class SearchFitWidget(QtWidgets.QWidget):

    def __init__(self, analysisplotWidget):
        super(SearchFitWidget, self).__init__()

        # --- PATH CONFIGURATION ---
        self.base_path = "C:/Users/TrappedIonRice4/Documents/Artiq-Rice"
        self.lastridfile = os.path.join(self.base_path, "last_rid.pyon")
        self.results_path = os.path.join(self.base_path, "results")

        # Determine latest subdirectory
        try:
            if os.path.exists(self.results_path):
                all_subdir = [f.name for f in os.scandir(self.results_path) if f.is_dir()]
                all_subdir.sort()
                self.latest_subdir = os.path.join(self.results_path,
                                                  all_subdir[-1]) if all_subdir else self.results_path
            else:
                self.latest_subdir = self.results_path
        except Exception as e:
            print(f"Error finding subdirectories: {e}")
            self.latest_subdir = self.results_path

        self.updated_path = self.latest_subdir

        # Variables
        self.filelist = []
        self.selectedfilelist = []
        self.fitlist = getattr(fitfunc, 'FIT_DICTIONARY', {}) if 'fitfunc' in globals() else {}
        self.num_rids = 200

        # Extended filter list to support both 1D and 2D scan experiment classes
        self.filterScanNames = [
            'executeScan',
            'BarebonesArtiqScanV1',
            'BarebonesArtiqScanV2',
            'BarebonesArtiqScan2DV1'
        ]

        self.dataDict = {}
        self.selectedDataDict = {}
        self.fitTraces = {}
        self.fitCheckboxTraces = {}
        self.dataCheckboxTraces = {}

        # References
        self.analysisPlotWidget = analysisplotWidget

        # --- GRAPHICS LAYOUT ---
        self.searchFitLayout = QtWidgets.QVBoxLayout()
        self.setLayout(self.searchFitLayout)
        self.searchFitLayout.setSpacing(10)
        self.searchFitLayout.setContentsMargins(10, 10, 10, 10)

        # ----------------------------
        # SECTION 1: SEARCH & FILES
        # ----------------------------
        self.searchFitHLayout = QtWidgets.QHBoxLayout()
        self.searchFitHLayout.setSpacing(10)

        self.searchLabel = QtWidgets.QLabel('Search for files')
        self.searchFitHLayout.addWidget(self.searchLabel)
        self.searchFitFileExplorerButton = QtWidgets.QPushButton('RID File Explorer')
        self.searchFitHLayout.addWidget(self.searchFitFileExplorerButton)
        self.searchFitHLayout.addStretch()
        self.searchFitLayout.addLayout(self.searchFitHLayout)

        # Data Action Buttons
        self.buttonsHlayout = QtWidgets.QHBoxLayout()
        self.buttonsHlayout.setSpacing(15)

        self.plotButtonWidget = QtWidgets.QPushButton('Plot')
        self.clearplotsButtonWidget = QtWidgets.QPushButton('Clear')
        self.autoplotCheckBox = QtWidgets.QCheckBox("Autoplot last RID")

        self.buttonsHlayout.addWidget(self.plotButtonWidget)
        self.buttonsHlayout.addWidget(self.clearplotsButtonWidget)
        self.buttonsHlayout.addWidget(self.autoplotCheckBox)
        self.buttonsHlayout.addStretch()
        self.searchFitLayout.addLayout(self.buttonsHlayout)

        # Original
        # # File Table
        # self.fileTableWidget = QtWidgets.QTableWidget()
        # self.fileTableWidget.setColumnCount(5)
        # self.fileTableWidget.setHorizontalHeaderLabels(['rid', 'Data', 'Fit', 'Scan parameter', 'Comments'])
        # self.rid_colInd = 0
        # self.dataChk_colInd = 1
        # self.fitChk_colInd = 2
        # self.ScanParameter_colInd = 3
        # self.Comments_colInd = 4
        # self.fileTableWidget.setShowGrid(False)
        # vscrollbar = QtWidgets.QScrollBar(self)
        # self.fileTableWidget.setVerticalScrollBar(vscrollbar)
        # self.fileTableWidget.setSelectionMode(2)

        # File Table
        self.fileTableWidget = QtWidgets.QTableWidget()
        self.fileTableWidget.setColumnCount(5)
        self.fileTableWidget.setHorizontalHeaderLabels(['rid', 'Data', 'Fit', 'Scan parameter', 'Comments'])
        self.rid_colInd = 0
        self.dataChk_colInd = 1
        self.fitChk_colInd = 2
        self.ScanParameter_colInd = 3
        self.Comments_colInd = 4
        # --- NEW: Set explicit column widths & header stretch modes ---
        header = self.fileTableWidget.horizontalHeader()
        # 1. Set fixed widths for narrow columns
        self.fileTableWidget.setColumnWidth(self.rid_colInd, 60)
        self.fileTableWidget.setColumnWidth(self.dataChk_colInd, 45)
        self.fileTableWidget.setColumnWidth(self.fitChk_colInd, 45)
        # 2. Lock narrow column sizes & set text columns to stretch dynamically
        header.setSectionResizeMode(self.rid_colInd, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(self.dataChk_colInd, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(self.fitChk_colInd, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(self.ScanParameter_colInd, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(self.Comments_colInd, QtWidgets.QHeaderView.Stretch)
        self.fileTableWidget.setShowGrid(False)
        vscrollbar = QtWidgets.QScrollBar(self)
        self.fileTableWidget.setVerticalScrollBar(vscrollbar)
        self.fileTableWidget.setSelectionMode(2)

        self.searchFitLayout.addWidget(self.fileTableWidget)

        # ----------------------------
        # SEPARATOR
        # ----------------------------
        self.searchFitLayout.addSpacing(20)

        # ----------------------------
        # SECTION 2: FITTING
        # ----------------------------
        self.fitselectionColumnWidget = QtWidgets.QWidget()
        self.fitselectionColumnLayout = QtWidgets.QVBoxLayout()
        self.fitselectionColumnWidget.setLayout(self.fitselectionColumnLayout)
        self.fitselectionColumnLayout.setContentsMargins(0, 0, 0, 0)

        # --- Dropdown for different camera ROIs ---
        # --- NEW: ROI Control Row (Above Fit Row) ---
        self.roiRowWidget = QtWidgets.QWidget()
        self.roiRowLayout = QtWidgets.QHBoxLayout()
        self.roiRowLayout.setSpacing(10)
        self.roiRowWidget.setLayout(self.roiRowLayout)

        self.roi_label = QtWidgets.QLabel("Camera ROI:", self)
        self.roi_selector = QtWidgets.QComboBox(self)
        self.roi_selector.addItem("All ROIs")
        self.roi_selector.setToolTip("Select which Camera ROI to plot and fit individually")
        self.roi_label.setVisible(False)  # Hidden by default
        self.roi_selector.setVisible(False)  # Hidden by default

        self.roiRowLayout.addWidget(self.roi_label)
        self.roiRowLayout.addWidget(self.roi_selector)
        self.roiRowLayout.addStretch()

        # Add the ROI row first so it appears on top
        self.fitselectionColumnLayout.addWidget(self.roiRowWidget)
        # --------------------------------------------

        # Fit Control Row
        self.fitselectionRowWidget = QtWidgets.QWidget()
        self.fitselectionRowlayout = QtWidgets.QHBoxLayout()
        self.fitselectionRowlayout.setSpacing(10)
        self.fitselectionRowWidget.setLayout(self.fitselectionRowlayout)

        self.fitselectionRowLabel = QtWidgets.QLabel('Fit Type:')
        self.fitselectionRowComboBox = QtWidgets.QComboBox()
        self.fitselectionRowFitButton = QtWidgets.QPushButton('Fit')
        self.fitselectionRowPlotButton = QtWidgets.QPushButton('Plot Fn')
        self.fitselectionRowClearFitButton = QtWidgets.QPushButton('Clear fit')

        self.autoFitCheckbox = QtWidgets.QCheckBox("Auto Fit & Plot")
        self.autoFitCheckbox.setChecked(False)
        self.autoFitCheckbox.setToolTip("Automatically run fit when new scan arrives")
        self.autoFitCheckbox.stateChanged.connect(self.toggleAutoFitLastRow)

        self.fitselectionRowlayout.addWidget(self.fitselectionRowLabel)
        self.fitselectionRowlayout.addWidget(self.fitselectionRowComboBox)
        self.fitselectionRowlayout.addWidget(self.fitselectionRowFitButton)
        self.fitselectionRowlayout.addWidget(self.fitselectionRowPlotButton)
        self.fitselectionRowlayout.addWidget(self.fitselectionRowClearFitButton)
        self.fitselectionRowlayout.addSpacing(15)
        self.fitselectionRowlayout.addWidget(self.autoFitCheckbox)
        self.fitselectionRowlayout.addStretch()

        self.fitselectionColumnLayout.addWidget(self.fitselectionRowWidget)

        # Description Label
        self.fitdescriptionLabel = QtWidgets.QLabel('')
        self.fitdescriptionLabel.setAlignment(Qt.AlignCenter)
        self.fitselectionColumnLayout.addWidget(self.fitdescriptionLabel)

        self.searchFitLayout.addWidget(self.fitselectionColumnWidget)

        # Fit Parameter Table
        self.fitTableWidget = QtWidgets.QTableWidget()
        self.searchFitLayout.addWidget(self.fitTableWidget)

        # --- INITIALIZATION ---
        self.last_rid = self.extractingLastrid(self.lastridfile)
        if self.last_rid is None:
            self.last_rid = 0

        self.searchfiles(self.last_rid, self.num_rids, self.updated_path)

        self.Searchtimer = QTimer(self)
        self.Searchtimer.setInterval(1000)
        self.Searchtimer.timeout.connect(self.autofunctions)
        self.Searchtimer.start()

        if hasattr(self, 'fitComboBoxList'):
            self.fitComboBoxList()
        if hasattr(self, 'fittingTableParam'):
            self.fittingTableParam()

        self.onClickFunctions()

    def onClickFunctions(self):
        self.plotButtonWidget.clicked.connect(self.plotfiledata)
        self.clearplotsButtonWidget.clicked.connect(self.clearPlots)
        self.autoplotCheckBox.stateChanged.connect(self.autoPlotLastRID)
        self.fitselectionRowFitButton.clicked.connect(getattr(self, 'fitData', lambda: None))
        self.fitselectionRowClearFitButton.clicked.connect(self.clearFitPlot)
        self.fitselectionRowPlotButton.clicked.connect(getattr(self, 'plotFitFunction', lambda: None))
        self.searchFitFileExplorerButton.clicked.connect(self.fileExplorerDialog)

        # for ROI selector when plotting data from the camera
        self.roi_selector.currentIndexChanged.connect(self.on_roi_selection_changed)


####################################################
    ######### For ROIS when plotting camera data #################
    def update_roi_dropdown_visibility(self):
        """Checks if any active plot is a camera scan and updates the dropdown."""
        has_camera = False
        available_rois = set()

        # Check all currently plotted RIDs to see if any are camera data
        for rid in self.dataCheckboxTraces:
            data = self.get_data_from_rid(rid)
            if data and data.get("is_camera", False):
                has_camera = True
                if isinstance(data.get('y'), dict):
                    # Collect all ROI names
                    available_rois.update(data['y'].keys())

        if has_camera:
            self.roi_label.setVisible(True)
            self.roi_selector.setVisible(True)

            current_selection = self.roi_selector.currentText()

            # Temporarily block signals so we don't trigger multiple plot redraws while populating
            self.roi_selector.blockSignals(True)
            self.roi_selector.clear()
            self.roi_selector.addItem("All ROIs")

            for roi in sorted(available_rois):
                self.roi_selector.addItem(roi)

            # Restore previous selection if it exists
            index = self.roi_selector.findText(current_selection)
            if index >= 0:
                self.roi_selector.setCurrentIndex(index)
            else:
                self.roi_selector.setCurrentIndex(0)

            self.roi_selector.blockSignals(False)
        else:
            self.roi_label.setVisible(False)
            self.roi_selector.setVisible(False)

    def get_filtered_data(self, rid):
        """Returns the data dictionary, dynamically filtering out unselected ROIs."""
        # 1. Fetch the raw data
        data = self.get_data_from_rid(rid)
        if not data:
            return None

        # 2. If it's camera data, filter it based on the dropdown
        if data.get("is_camera"):
            selected_roi = self.roi_selector.currentText()

            # If a specific ROI is selected (not "All ROIs"), filter the dictionaries
            if selected_roi != "All ROIs" and isinstance(data.get('y'), dict) and selected_roi in data['y']:

                # Make a shallow copy so we don't accidentally delete data from the master cache
                filtered_data = data.copy()

                # Keep ONLY the selected ROI in the 'y' and 'err' dictionaries
                filtered_data['y'] = {selected_roi: data['y'][selected_roi]}

                if data.get('err') and isinstance(data['err'], dict) and selected_roi in data['err']:
                    filtered_data['err'] = {selected_roi: data['err'][selected_roi]}
                else:
                    filtered_data['err'] = {selected_roi: None}

                return filtered_data

        # 3. If it's not a camera, or "All ROIs" is selected, return the unfiltered data
        return data

    def on_roi_selection_changed(self):
        """Triggered when the user changes the ROI dropdown."""
        for rid in list(self.dataCheckboxTraces.keys()):

            # Check the UNFILTERED data to see if it's a camera
            base_data = self.get_data_from_rid(rid)
            if base_data and base_data.get("is_camera", False):
                self.analysisPlotWidget.remove_dataset(rid)

                # Grab the FILTERED data to plot the newly selected ROI
                filtered_data = self.get_filtered_data(rid)

                color_idx = list(self.dataCheckboxTraces.keys()).index(rid)
                self.analysisPlotWidget.add_dataset(
                    rid=rid,
                    data=filtered_data,
                    color_idx=color_idx,
                    total_count=len(self.dataCheckboxTraces)
                )

        if hasattr(self, 'fittingTableParam'):
            self.fittingTableParam()
############################################################################

    # --------------------------------------------------------------------------
    # CHECKBOX & SELECTION LOGIC
    # --------------------------------------------------------------------------
    def selectRangesCheckbox(self, rid, col, state):
        actual_row = self.findRowByRID(rid)
        if actual_row is None:
            return
        row = actual_row

        # Check if checked (state == 2 or Qt.Checked)
        is_checked = (state == 2 or state == QtCore.Qt.Checked)

        # 1. FIT Checkbox
        if col == self.fitChk_colInd:
            data = self.get_data_from_rid(rid)
            if data and data.get("is_2d", False):
                if is_checked:
                    print(f"RID {rid} is a 2D Scan. 1D Fitting is disabled for 2D data.")
                    fit_widget = self.fileTableWidget.cellWidget(row, self.fitChk_colInd)
                    if fit_widget:
                        chk = fit_widget.findChild(QtWidgets.QCheckBox)
                        if chk:
                            chk.setChecked(False)
                    return

            if is_checked:
                if rid not in self.fitCheckboxTraces:
                    self.fitCheckboxTraces[rid] = row
            else:
                if rid in self.fitCheckboxTraces:
                    del self.fitCheckboxTraces[rid]

                if hasattr(self, 'fitTraces') and rid in self.fitTraces:
                    self.analysisPlotWidget.removeItem(self.fitTraces[rid])
                    del self.fitTraces[rid]

            if hasattr(self, 'fittingTableParam'):
                self.fittingTableParam()

        # 2. DATA Checkbox
        elif col == self.dataChk_colInd:
            if is_checked:
                self.dataCheckboxTraces[rid] = row
                data = self.get_data_from_rid(rid)
                if data:
                    self.analysisPlotWidget.add_dataset(
                        rid=rid,
                        data=data,
                        color_idx=len(self.dataCheckboxTraces) - 1,
                        total_count=len(self.dataCheckboxTraces)
                    )
            else:
                if rid in self.dataCheckboxTraces:
                    del self.dataCheckboxTraces[rid]

                self.analysisPlotWidget.remove_dataset(rid)

            # Sync table row background colors with plot trace colors
            self.updateTableRIDColors()

            # --- NEW: Update Dropdown visibility when data checkboxes change ---
            self.update_roi_dropdown_visibility()

    def updateTableRIDColors(self):
        """Highlights RID table cells with the matching color of their plot trace."""
        if not hasattr(self.analysisPlotWidget, 'get_rid_colors'):
            return

        rid_colors = self.analysisPlotWidget.get_rid_colors()

        for row in range(self.fileTableWidget.rowCount()):
            rid_cell = self.fileTableWidget.item(row, self.rid_colInd)
            if not rid_cell:
                continue

            try:
                rid = int(rid_cell.text())
            except ValueError:
                continue

            if rid in rid_colors:
                color = rid_colors[rid]
                rid_cell.setBackground(QtGui.QBrush(color))

                # Contrast logic for text legibility
                luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
                text_color = QtGui.QColor("white") if luminance < 128 else QtGui.QColor("black")
                rid_cell.setForeground(QtGui.QBrush(text_color))

            elif rid in self.dataCheckboxTraces:
                # Fallback color for 2D scans
                rid_cell.setBackground(QtGui.QBrush(QtGui.QColor("#e6f2ff")))
                rid_cell.setForeground(QtGui.QBrush(QtGui.QColor("black")))
            else:
                # Reset unchecked rows to standard white
                rid_cell.setBackground(QtGui.QBrush(QtGui.QColor("white")))
                rid_cell.setForeground(QtGui.QBrush(QtGui.QColor("black")))

    def plotSelectedData(self):
        """Full rebuild pass used by 'Plot' button or autoplot."""
        self.analysisPlotWidget.clear_all()
        for k, RID in enumerate(list(self.dataCheckboxTraces.keys())):
            rid = int(RID)
            data = self.get_data_from_rid(rid)
            if data:
                self.analysisPlotWidget.add_dataset(
                    rid=rid,
                    data=data,
                    color_idx=k,
                    total_count=len(self.dataCheckboxTraces)
                )
        self.updateTableRIDColors()

    def clearDataChkBox(self, rid):
        if rid in self.dataCheckboxTraces:
            row = self.dataCheckboxTraces[rid]
            widget = self.fileTableWidget.cellWidget(row, self.dataChk_colInd)
            if widget:
                chk_box = widget.findChild(QtWidgets.QCheckBox)
                if chk_box:
                    chk_box.blockSignals(True)
                    chk_box.setChecked(False)
                    chk_box.blockSignals(False)

    def clearFitChkBox(self, rid):
        if rid in self.fitCheckboxTraces:
            row = self.fitCheckboxTraces[rid]
            widget = self.fileTableWidget.cellWidget(row, self.fitChk_colInd)
            if widget:
                chk_box = widget.findChild(QtWidgets.QCheckBox)
                if chk_box:
                    chk_box.blockSignals(True)
                    chk_box.setChecked(False)
                    chk_box.blockSignals(False)

    def clearPlots(self):
        """Clears 1D line items, 2D heatmaps, crosshairs, colorbars, and unchecks data/fit boxes."""
        self.analysisPlotWidget.clear_all()
        self.fileTableWidget.clearSelection()

        datakeylist = list(self.dataCheckboxTraces.keys())
        fitkeylist = list(self.fitCheckboxTraces.keys())

        for rid in datakeylist:
            self.clearDataChkBox(rid)
        for rid in fitkeylist:
            self.clearFitChkBox(rid)

        self.updateTableRIDColors()

    def clearFitPlot(self):
        if self.fitCheckboxTraces:
            last_fit_rid = list(self.fitCheckboxTraces.keys())[-1]
            if last_fit_rid in self.fitTraces:
                self.analysisPlotWidget.removeItem(self.fitTraces[last_fit_rid])
                del self.fitTraces[last_fit_rid]
            self.clearFitChkBox(last_fit_rid)

    # --------------------------------------------------------------------------
    # HELPER UTILITIES
    # --------------------------------------------------------------------------
    def findRowByRID(self, rid):
        items = self.fileTableWidget.findItems(str(rid), QtCore.Qt.MatchExactly)
        if items:
            return items[0].row()
        return None

    def fileExplorerDialog(self):
        default_directory = os.path.expanduser(self.updated_path)
        file_path, _ = QFileDialog.getOpenFileName(self, "Select a File", default_directory)

        if file_path:
            file_path_list = file_path.split('/')
            rid_filename = file_path_list[-1]
            rid_filename_list = rid_filename.split('-')
            rid = int(rid_filename_list[0])
            joined_list = '/'.join(file_path_list[:-2])
            self.searchSingleFile(rid, joined_list)

    def autoPlotLastRID(self):
        if self.autoplotCheckBox.isChecked():
            row_last_rid = self.getRowMaxRID()
            widget = self.fileTableWidget.cellWidget(row_last_rid, self.dataChk_colInd)
            if widget:
                chk_box = widget.findChild(QtWidgets.QCheckBox)
                if chk_box and not chk_box.isChecked():
                    chk_box.setChecked(True)
            self.plotSelectedData()

    def getRowMaxRID(self):
        rid_list = [int(self.fileTableWidget.item(row, self.rid_colInd).text())
                    for row in range(self.fileTableWidget.rowCount())]
        return rid_list.index(max(rid_list)) if rid_list else 0

    def autofunctions(self):
        self.check_date_update()
        self.updateSearchList()

    def check_date_update(self):
        """Dynamically updates self.updated_path to the latest daily subdirectory."""
        try:
            if os.path.exists(self.results_path):
                all_subdir = [f.name for f in os.scandir(self.results_path) if f.is_dir()]
                all_subdir.sort()
                if all_subdir:
                    latest_path = os.path.join(self.results_path, all_subdir[-1])
                    if os.path.normpath(self.updated_path) != os.path.normpath(latest_path):
                        print(f"New scan folder detected. Updating path to: {latest_path}")
                        self.updated_path = latest_path
        except Exception as e:
            print(f"Error updating directory path: {e}")

    def uncolorRIDlabels(self):
        for row in range(self.fileTableWidget.rowCount()):
            rid_cell = self.fileTableWidget.item(row, self.rid_colInd)
            if rid_cell:
                rid_cell.setBackground(QColor("white"))

    def updateSearchList(self):
        """Checks for new RIDs asynchronously without locking UI or dropping RIDs."""
        if not hasattr(self, 'search_attempt_counter'):
            self.search_attempt_counter = 0

        self.check_date_update()
        target_last_rid = self.extractingLastrid(self.lastridfile)

        if target_last_rid is None or target_last_rid <= self.last_rid:
            self.search_attempt_counter = 0
            return

        next_rid = self.last_rid + 1
        status = self.searchSingleFile(next_rid, self.updated_path)

        if status is True:
            # File loaded successfully
            self.last_rid = next_rid
            self.search_attempt_counter = 0
            if hasattr(self, 'autoPlotLastRID'):
                self.autoPlotLastRID()

        elif status is None:
            # File exists but is filtered out -> skip instantly
            self.last_rid = next_rid
            self.search_attempt_counter = 0

        elif status is False:
            # File not ready yet -> increment counter and retry next tick
            self.search_attempt_counter += 1
            if self.search_attempt_counter >= 50000:
                print(f"Skipping RID {next_rid} (file not ready/found after 50000 background attempts).")
                self.last_rid = next_rid
                self.search_attempt_counter = 0


    def extractingLastrid(self, filename):
        try:
            if not os.path.exists(filename):
                return None
            with open(filename, 'r') as file:
                content = file.readline().strip()
                return int(content) if content else None
        except (ValueError, IndexError, IOError):
            return None

    def searchfiles(self, last_rid, num_rids, rootpath):
        list_rids = list(np.arange(max(0, last_rid - num_rids), last_rid + 1, 1))
        for rid in list_rids:
            self.searchSingleFile(rid, rootpath)

    def toggleAutoFitLastRow(self, state):
        if state == Qt.Checked:
            row_count = self.fileTableWidget.rowCount()
            if row_count == 0:
                return

            last_row = row_count - 1

            rid_item = self.fileTableWidget.item(last_row, self.rid_colInd)
            if rid_item:
                rid = int(rid_item.text())
                data = self.get_data_from_rid(rid)
                if data and data.get("is_2d", False):
                    print("Auto-fit skipped: Last RID is a 2D Scan.")
                    return

            data_widget = self.fileTableWidget.cellWidget(last_row, self.dataChk_colInd)
            data_chk = data_widget.findChild(QtWidgets.QCheckBox) if data_widget else None

            fit_widget = self.fileTableWidget.cellWidget(last_row, self.fitChk_colInd)
            fit_chk = fit_widget.findChild(QtWidgets.QCheckBox) if fit_widget else None

            if fit_chk and not fit_chk.isChecked():
                if data_chk and not data_chk.isChecked():
                    data_chk.setChecked(True)

                fit_chk.setChecked(True)
                self.fileTableWidget.selectRow(last_row)
                if hasattr(self, 'fitData'):
                    QTimer.singleShot(100, self.fitData)

    def enforceRowLimit(self):
        """Safely removes the oldest row when table exceeds capacity without signal leaks."""
        while self.fileTableWidget.rowCount() > self.num_rids:
            oldest_rid_item = self.fileTableWidget.item(0, self.rid_colInd)
            if oldest_rid_item is None:
                return

            try:
                oldest_rid = int(oldest_rid_item.text())
            except ValueError:
                oldest_rid = None

            # Block signals on row 0 cell widgets before removing row
            for col in [self.dataChk_colInd, self.fitChk_colInd]:
                widget = self.fileTableWidget.cellWidget(0, col)
                if widget:
                    chk = widget.findChild(QtWidgets.QCheckBox)
                    if chk:
                        chk.blockSignals(True)

            if oldest_rid is not None:
                if oldest_rid in self.fitTraces:
                    self.analysisPlotWidget.removeItem(self.fitTraces[oldest_rid])
                    del self.fitTraces[oldest_rid]

                self.dataDict.pop(oldest_rid, None)
                self.selectedDataDict.pop(oldest_rid, None)
                self.fitCheckboxTraces.pop(oldest_rid, None)
                self.dataCheckboxTraces.pop(oldest_rid, None)

            self.fileTableWidget.removeRow(0)

            # Re-map row indices safely
            for rid in list(self.fitCheckboxTraces.keys()):
                actual_row = self.findRowByRID(rid)
                if actual_row is not None:
                    self.fitCheckboxTraces[rid] = actual_row

            for rid in list(self.dataCheckboxTraces.keys()):
                actual_row = self.findRowByRID(rid)
                if actual_row is not None:
                    self.dataCheckboxTraces[rid] = actual_row

    # ==============================================================================
    # SEARCH & DATA EXTRACTION METHODS
    # ==============================================================================

    @staticmethod
    def clean_str(val, remove_units=False):
        import re
        if val is None:
            return ""

        if isinstance(val, np.ndarray):
            val = val.item() if val.size > 0 else ""

        if isinstance(val, bytes):
            val = val.decode('utf-8', errors='ignore')

        s = str(val).strip()
        s = re.sub(r"^b['\"](.*)['\"]$", r"\1", s, flags=re.DOTALL)

        for char in ["'", '"']:
            s = s.replace(char, "")

        if remove_units:
            s = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", "", s)
            s = re.sub(r"[\s_]+(?:ms|us|µs|s|ns|Hz|kHz|MHz|GHz|V|mV|A|mA|dBm|deg|rad)\b", "", s, flags=re.IGNORECASE)

        return s.strip()

    @staticmethod
    def format_axis_unit(label_str, unit_str=""):
        import re
        label_str = label_str.strip()
        unit_str = unit_str.strip()

        if unit_str:
            clean_unit = re.sub(r"[\[\]\(\)]", "", unit_str).strip()
            clean_desc = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", "", label_str).strip()
            clean_desc = re.sub(r"[\s_]+" + re.escape(clean_unit) + r"\b", "", clean_desc, flags=re.IGNORECASE).strip()
            return f"{clean_desc} [{clean_unit}]"

        if "(" in label_str and ")" in label_str:
            return re.sub(r"\((.*?)\)", r"[\1]", label_str)

        if "[" in label_str and "]" in label_str:
            return label_str

        match = re.search(r"^(.*?)(?:[\s_]+)(ms|us|µs|s|ns|Hz|kHz|MHz|GHz|V|mV|A|mA|dBm|deg|rad)$", label_str, re.IGNORECASE)
        if match:
            desc, unit = match.group(1).strip(), match.group(2).strip()
            return f"{desc} [{unit}]"

        return label_str

    def extract_table_scan_param(self, rid, dict_datasets):
        """
        Returns table-formatted parameter text without units/brackets:
          - Bare 2D:   'B-(param_x, param_y)'
          - NDScan 2D: 'N-(param_x, param_y)'
          - Bare 1D:   'B-(param_x)'
          - NDScan 1D: 'N-(param_x)'
        """
        import json
        import re

        def clean_p(raw):
            if raw is None:
                return ""
            if isinstance(raw, np.ndarray):
                raw = raw.item() if raw.size > 0 else ""
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode('utf-8', errors='ignore')
            # Remove parens (), brackets [], and trailing spaces
            s = str(raw).strip()
            s = re.sub(r'\[.*?\]|\(.*?\)', '', s).strip()
            return s

        ndscan_key = f'ndscan.rid_{rid}.axes'

        # --- 1. NDSCAN PARSING ---
        if ndscan_key in dict_datasets:
            try:
                axes_raw = dict_datasets[ndscan_key]
                if isinstance(axes_raw, np.ndarray) and axes_raw.ndim == 0:
                    axes_raw = axes_raw.item()
                if isinstance(axes_raw, (bytes, bytearray)):
                    axes_raw = axes_raw.decode('utf-8', errors='ignore')
                axes_list = json.loads(axes_raw) if isinstance(axes_raw, str) else axes_raw

                if isinstance(axes_list, list) and len(axes_list) >= 2:
                    px = clean_p(axes_list[0].get('param', {}).get('description', 'X Axis'))
                    py = clean_p(axes_list[1].get('param', {}).get('description', 'Y Axis'))
                    return f"N-({px}, {py})"
                elif isinstance(axes_list, list) and len(axes_list) >= 1:
                    px = clean_p(axes_list[0].get('param', {}).get('description', 'Scan Param'))
                    return f"N-({px})"
            except Exception:
                pass

        # --- 2. BARE ARTIQ 2D PARSING ---
        if "ScanDataPlot.z_vals" in dict_datasets:
            px = clean_p(dict_datasets.get("ScanDataPlot.x_label", "X Axis"))
            py = clean_p(dict_datasets.get("ScanDataPlot.y_label", "Y Axis"))
            return f"B-({px}, {py})"

        # --- 3. BARE ARTIQ 1D PARSING ---
        px = clean_p(dict_datasets.get("ScanDataPlot.x_label", getattr(self, 'rid_xlabels', {}).get(rid, "Scan Param")))
        return f"B-({px})"

    def searchSingleFile(self, rid, rootpath):
        """
        Returns True (Success), False (Not Ready/Error), or None (Filtered).
        """
        rid = int(rid)
        try:
            dict_test = find_results("", rid=rid, root_path=rootpath)
        except Exception:
            return False

        if not dict_test or rid not in dict_test:
            return False

        # ---------------------------------------------------------
        # Check 1: Is it the right scan type? (Handles nested lists)
        # ---------------------------------------------------------
        scan_type = dict_test[rid][-1]

        allowed_scans = set()
        for item in self.filterScanNames:
            if isinstance(item, (list, tuple, set)):
                allowed_scans.update(str(x) for x in item)
            else:
                allowed_scans.add(str(item))

        if isinstance(scan_type, (list, tuple, set)):
            is_allowed = any(str(st) in allowed_scans for st in scan_type)
        else:
            is_allowed = str(scan_type) in allowed_scans

        if not is_allowed:
            return None  # <--- CRITICAL: Returns None so the timer knows to skip instantly

        try:
            # Load the HDF5 file
            dict_hdf5 = load_hdf5_file(dict_test[rid][0])
            dict_datasets = dict_hdf5.get("datasets", {})
            dict_archive = dict_hdf5.get("archive", {})

            # ---------------------------------------------------------
            # Check 2: Handle Metadata (NDScan vs Bare)
            # ---------------------------------------------------------
            axes_raw = dict_datasets.get(f'ndscan.rid_{rid}.axes', '[]')

            if isinstance(axes_raw, np.ndarray) and axes_raw.ndim == 0:
                axes_raw = axes_raw.item()
            if isinstance(axes_raw, (bytes, bytearray)):
                axes_raw = axes_raw.decode('utf-8', errors='ignore')

            try:
                axes_list = json.loads(axes_raw) if isinstance(axes_raw, str) else []
            except Exception:
                axes_list = []

            xlabel_axis0 = ""
            is_valid_file = False

            if isinstance(axes_list, list) and len(axes_list) > 0:  # ndscan
                scanparam_axis0 = axes_list[0]
                unit = scanparam_axis0.get('param', {}).get('spec', {}).get('unit', '')
                unit_str = f" ({unit})" if unit else ""
                xlabel_axis0 = scanparam_axis0.get('param', {}).get('description', '') + unit_str
                is_valid_file = True

            elif "ScanDataPlot.x_label" in dict_datasets:
                val = dict_datasets["ScanDataPlot.x_label"]
                if isinstance(val, np.ndarray):
                    val = val.item() if val.size > 0 else ""

                if isinstance(val, (bytes, bytearray)):
                    xlabel_axis0 = val.decode('utf-8', errors='ignore')
                else:
                    xlabel_axis0 = str(val)

                is_valid_file = True

            if not is_valid_file:
                return False  # Not ready

            # ---------------------------------------------------------
            # --- Add to Table ---
            # ---------------------------------------------------------
            self.dataDict[rid] = dict_datasets

            if not hasattr(self, 'rid_labels'):
                self.rid_labels = {}
            self.rid_labels[rid] = xlabel_axis0

            row_count = self.fileTableWidget.rowCount()
            self.fileTableWidget.insertRow(row_count)

            fitcheckbox = QCheckBox(self)
            datacheckbox = QCheckBox(self)

            data_widget = QtWidgets.QWidget()
            data_layout = QtWidgets.QHBoxLayout(data_widget)
            data_layout.addWidget(datacheckbox)
            data_layout.setAlignment(Qt.AlignCenter)
            data_layout.setContentsMargins(0, 0, 0, 0)

            fit_widget = QtWidgets.QWidget()
            fit_layout = QtWidgets.QHBoxLayout(fit_widget)
            fit_layout.addWidget(fitcheckbox)
            fit_layout.setAlignment(Qt.AlignCenter)
            fit_layout.setContentsMargins(0, 0, 0, 0)

            table_scan_param_label = self.extract_table_scan_param(rid, dict_datasets)

            ### NEW ####
            scan_param_item = QTableWidgetItem(table_scan_param_label)
            scan_param_item.setTextAlignment(QtCore.Qt.AlignCenter)

            self.fileTableWidget.setItem(row_count, self.rid_colInd, QTableWidgetItem(str(rid)))
            self.fileTableWidget.setCellWidget(row_count, self.dataChk_colInd, data_widget)
            self.fileTableWidget.setCellWidget(row_count, self.fitChk_colInd, fit_widget)
            self.fileTableWidget.setItem(row_count, self.ScanParameter_colInd, scan_param_item)
            self.fileTableWidget.setItem(row_count, self.Comments_colInd, QTableWidgetItem(""))
            ############



            datacheckbox.stateChanged.connect(
                lambda state, num=rid, col=self.dataChk_colInd: self.selectRangesCheckbox(num, col, state))
            fitcheckbox.stateChanged.connect(
                lambda state, num=rid, col=self.fitChk_colInd: self.selectRangesCheckbox(num, col, state))

            for col in [self.rid_colInd, self.ScanParameter_colInd]:
                item = self.fileTableWidget.item(row_count, col)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

            # Force GUI to refresh and scroll to the new row
            self.fileTableWidget.scrollToBottom()
            self.fileTableWidget.viewport().update()

            if self.autoFitCheckbox.isChecked():
                datacheckbox.setChecked(True)
                fitcheckbox.setChecked(True)
                self.fileTableWidget.selectRow(row_count)
                if hasattr(self, 'fitData'):
                    QTimer.singleShot(100, self.fitData)

            self.enforceRowLimit()
            return True

        except Exception as e:
            print(f"[RID {rid}] Error processing: {e}")
            return False

    # def get_data_from_rid(self, rid):
    #     """Extracts plot-ready data dictionary with robust unit & description parsing."""
    #     import json
    #     import numpy as np
    #
    #     rid = int(rid)
    #     if rid not in self.dataDict:
    #         return None
    #
    #     dict_datasets = self.dataDict[rid]
    #
    #     def process_axis_units(vals, desc, unit="", is_ndscan=True):
    #         if vals is None or len(vals) == 0:
    #             return vals, desc
    #
    #         vals = np.array(vals)
    #
    #         if isinstance(desc, np.ndarray) and desc.ndim == 0:
    #             desc = desc.item()
    #         if isinstance(desc, (bytes, bytearray)):
    #             desc = desc.decode('utf-8', errors='ignore')
    #         elif desc is None:
    #             desc = ""
    #         else:
    #             desc = str(desc)
    #
    #         if isinstance(unit, np.ndarray) and unit.ndim == 0:
    #             unit = unit.item()
    #         if isinstance(unit, (bytes, bytearray)):
    #             unit = unit.decode('utf-8', errors='ignore')
    #         elif unit is None:
    #             unit = ""
    #         else:
    #             unit = str(unit)
    #
    #         if is_ndscan:
    #             desc_lower = f"{desc} {unit}".lower()
    #             if unit == 's' or 'time' in desc_lower:
    #                 vals = vals * 1e3
    #                 if " (s)" in desc:
    #                     label = desc.replace(" (s)", " (ms)")
    #                 elif desc.strip().endswith("[s]"):
    #                     label = desc.replace("[s]", "[ms]")
    #                 else:
    #                     label = f"{desc} (ms)"
    #             elif unit == 'Hz' or 'freq' in desc_lower:
    #                 vals = vals * 1e-6
    #                 if " (Hz)" in desc or " (hz)" in desc:
    #                     label = desc.replace(" (Hz)", " (MHz)").replace(" (hz)", " (MHz)")
    #                 elif desc.strip().endswith("[Hz]") or desc.strip().endswith("[hz]"):
    #                     label = desc.replace("[Hz]", "[MHz]").replace("[hz]", "[MHz]")
    #                 else:
    #                     label = f"{desc} (MHz)"
    #             else:
    #                 unit_str = f" ({unit})" if unit and not desc.endswith(f"({unit})") else ""
    #                 label = f"{desc}{unit_str}"
    #         else:
    #             label = desc
    #             if " (s)" in label:
    #                 label = label.replace(" (s)", " (ms)")
    #             elif label.strip().endswith("[s]"):
    #                 label = label.replace("[s]", "[ms]")
    #
    #         return vals, label
    #
    #     def find_desc_and_unit(obj):
    #         d, u = "", ""
    #         if isinstance(obj, dict):
    #             if 'description' in obj and isinstance(obj['description'], str): d = obj['description']
    #             if 'unit' in obj and isinstance(obj['unit'], str): u = obj['unit']
    #             for v in obj.values():
    #                 sub_d, sub_u = find_desc_and_unit(v)
    #                 if not d: d = sub_d
    #                 if not u: u = sub_u
    #         elif isinstance(obj, list):
    #             for item in obj:
    #                 sub_d, sub_u = find_desc_and_unit(item)
    #                 if not d: d = sub_d
    #                 if not u: u = sub_u
    #         return d, u
    #
    #     # --- CAMERA DATA CHECK ---
    #     has_camera = False
    #     cam_key = None
    #     for k in dict_datasets.keys():
    #         k_str = k.decode('utf-8') if isinstance(k, (bytes, bytearray)) else str(k)
    #         if 'Camera.y' in k_str:
    #             has_camera = True
    #             cam_key = k
    #             break
    #
    #     # --- ROBUST CAMERA EXTRACTION HELPER ---
    #     def extract_camera_data(fallback_x_vals, fallback_xlabel):
    #         cam_raw = dict_datasets[cam_key]
    #
    #         if isinstance(cam_raw, (bytes, bytearray)):
    #             cam_raw = cam_raw.decode('utf-8')
    #
    #         # 1. Try to parse as JSON first (NDScan style)
    #         cam_data = None
    #         if isinstance(cam_raw, str):
    #             try:
    #                 cam_data = json.loads(cam_raw)
    #             except Exception:
    #                 pass
    #
    #         # 2. If not JSON, it's a native HDF5 array (Barebones style)
    #         if cam_data is None:
    #             cam_data = np.array(dict_datasets[cam_key])
    #
    #         y_dict_rois = {}
    #         err_dict_rois = {}
    #
    #         # Case A: Data is a Dictionary (NDScan)
    #         if isinstance(cam_data, dict):
    #             for roi, roi_data in cam_data.items():
    #                 if isinstance(roi_data, dict) and 'value' in roi_data:
    #                     vals = np.array(roi_data['value'])
    #                 else:
    #                     vals = np.array(roi_data)
    #
    #                 if vals.ndim == 1:
    #                     y_dict_rois[roi] = vals
    #                 elif vals.ndim == 2:
    #                     y_dict_rois[roi] = vals[:, 0]
    #                     err_dict_rois[roi] = vals[:, 1] if vals.shape[1] > 1 else None
    #                     # err_dict_rois[roi] = None  # Force to None to test if weights are breaking the fit
    #
    #         # Case B: Data is a raw array/list (Barebones)
    #         else:
    #             vals = np.array(cam_data)
    #             if vals.ndim == 1:
    #                 y_dict_rois["Camera ROI"] = vals
    #             elif vals.ndim == 2:
    #                 for col in range(vals.shape[1]):
    #                     y_dict_rois[f"ROI {col}"] = vals[:, col]
    #
    #         # Determine X Values (Check for Camera.x, ScanDataPlot.x_vals, or use fallback)
    #         cam_key_str = cam_key.decode('utf-8') if isinstance(cam_key, bytes) else str(cam_key)
    #         x_cam_key_str = cam_key_str.replace('.y', '.x')
    #         x_cam_key_bytes = x_cam_key_str.encode('utf-8')
    #
    #         x_vals_cam = None
    #
    #         if x_cam_key_str in dict_datasets or x_cam_key_bytes in dict_datasets:
    #             x_k = x_cam_key_str if x_cam_key_str in dict_datasets else x_cam_key_bytes
    #             x_raw = dict_datasets[x_k]
    #
    #             try:
    #                 if isinstance(x_raw, (bytes, bytearray)):
    #                     x_raw_parsed = json.loads(x_raw.decode('utf-8'))
    #                 elif isinstance(x_raw, str):
    #                     x_raw_parsed = json.loads(x_raw)
    #                 else:
    #                     x_raw_parsed = np.array(x_raw)
    #
    #                 # Check if it's a dictionary (metadata) or a single string rather than an array of numbers
    #                 if isinstance(x_raw_parsed, dict) or (
    #                         isinstance(x_raw_parsed, np.ndarray) and x_raw_parsed.dtype.kind in {'U', 'S'}):
    #                     pass  # It's metadata (e.g. ROI names), ignore it.
    #                 else:
    #                     x_vals_cam = np.array(x_raw_parsed)
    #             except Exception:
    #                 pass
    #
    #         # If Camera.x wasn't valid numeric scan data, use standard fallbacks
    #         if x_vals_cam is None:
    #             if b'ScanDataPlot.x_vals' in dict_datasets or 'ScanDataPlot.x_vals' in dict_datasets:
    #                 x_k = b'ScanDataPlot.x_vals' if b'ScanDataPlot.x_vals' in dict_datasets else 'ScanDataPlot.x_vals'
    #                 x_vals_cam = np.array(dict_datasets[x_k])
    #             else:
    #                 x_vals_cam = fallback_x_vals
    #
    #         # Truncate arrays to match the shortest length
    #         min_len = len(x_vals_cam)
    #         for r_vals in y_dict_rois.values():
    #             min_len = min(min_len, len(r_vals))
    #
    #         for r_name in list(y_dict_rois.keys()):
    #             y_dict_rois[r_name] = y_dict_rois[r_name][:min_len]
    #             if err_dict_rois.get(r_name) is not None:
    #                 err_dict_rois[r_name] = err_dict_rois[r_name][:min_len]
    #
    #         return {
    #             "is_2d": False,
    #             "is_camera": True,
    #             "x": x_vals_cam[:min_len],
    #             "y": y_dict_rois,
    #             "err": err_dict_rois,
    #             "xlabel": fallback_xlabel,
    #             "ylabel": "Camera Counts"
    #         }
    #
    #     # --- TYPE A: NDSCAN ---
    #     ndscan_key = f'ndscan.rid_{rid}.axes'
    #     if ndscan_key in dict_datasets:
    #         try:
    #             axes_raw = dict_datasets[ndscan_key]
    #             if isinstance(axes_raw, np.ndarray) and axes_raw.ndim == 0: axes_raw = axes_raw.item()
    #             if isinstance(axes_raw, (bytes, bytearray)): axes_raw = axes_raw.decode('utf-8')
    #             axes_list = json.loads(axes_raw) if isinstance(axes_raw, str) else axes_raw
    #
    #             key_name_y = f"ndscan.rid_{rid}.points.channel_counts"
    #             key_name_err = f"ndscan.rid_{rid}.points.channel_res_err"
    #
    #             raw_y = np.array(dict_datasets[key_name_y]) if key_name_y in dict_datasets else np.array([])
    #             is_2d_scan = isinstance(axes_list, list) and len(axes_list) >= 2
    #
    #             if is_2d_scan or (raw_y.ndim == 2 and len(raw_y) > 0 and not has_camera):
    #                 axis_0_key = f"ndscan.rid_{rid}.points.axis_0"
    #                 axis_1_key = f"ndscan.rid_{rid}.points.axis_1"
    #                 raw_x0 = np.array(dict_datasets[axis_0_key]) if axis_0_key in dict_datasets else np.array([])
    #                 raw_x1 = np.array(dict_datasets[axis_1_key]) if axis_1_key in dict_datasets else np.array([])
    #
    #                 if raw_y.ndim == 2:
    #                     z_mat = raw_y
    #                     x_vals_uniq = raw_x0 if len(raw_x0) == z_mat.shape[0] else np.arange(z_mat.shape[0])
    #                     y_vals_uniq = raw_x1 if len(raw_x1) == z_mat.shape[1] else np.arange(z_mat.shape[1])
    #                 else:
    #                     _, idx0 = np.unique(raw_x0, return_index=True)
    #                     x_vals_uniq = raw_x0[np.sort(idx0)]
    #                     _, idx1 = np.unique(raw_x1, return_index=True)
    #                     y_vals_uniq = raw_x1[np.sort(idx1)]
    #                     if len(x_vals_uniq) * len(y_vals_uniq) == len(raw_y):
    #                         z_mat = raw_y.reshape((len(x_vals_uniq), len(y_vals_uniq)))
    #                     else:
    #                         z_mat = np.full((len(x_vals_uniq), len(y_vals_uniq)), np.nan)
    #                         for px, py, val in zip(raw_x0, raw_x1, raw_y):
    #                             xi = np.where(x_vals_uniq == px)[0]
    #                             yi = np.where(y_vals_uniq == py)[0]
    #                             if len(xi) > 0 and len(yi) > 0: z_mat[xi[0], yi[0]] = val
    #
    #                 x_desc = getattr(self, 'rid_xlabels', {}).get(rid, "")
    #                 y_desc = getattr(self, 'rid_ylabels', {}).get(rid, "")
    #                 x_unit, y_unit = "", ""
    #                 if isinstance(axes_list, list) and len(axes_list) >= 2:
    #                     if not x_desc: x_desc = axes_list[0].get('param', {}).get('description', 'X Axis')
    #                     x_unit = axes_list[0].get('param', {}).get('unit', '')
    #                     if not y_desc: y_desc = axes_list[1].get('param', {}).get('description', 'Y Axis')
    #                     y_unit = axes_list[1].get('param', {}).get('unit', '')
    #
    #                 x_vals, xlabel = process_axis_units(x_vals_uniq, x_desc, x_unit, is_ndscan=True)
    #                 y_vals, ylabel = process_axis_units(y_vals_uniq, y_desc, y_unit, is_ndscan=True)
    #                 return {"is_2d": True, "is_camera": False, "x": x_vals, "y": y_vals, "z": z_mat, "xlabel": xlabel,
    #                         "ylabel": ylabel, "zlabel": "counts"}
    #
    #             else:
    #                 # 1D Scan NDScan Fallbacks
    #                 key_name_x = f"ndscan.rid_{rid}.points.axis_0"
    #                 description, raw_unit = find_desc_and_unit(axes_list)
    #                 fallback_label = getattr(self, 'rid_xlabels', {}).get(rid, getattr(self, 'rid_labels', {}).get(rid,
    #                                                                                                                "Scan Parameter"))
    #                 final_desc = description if description else fallback_label
    #
    #                 if key_name_x in dict_datasets:
    #                     raw_x = np.array(dict_datasets[key_name_x])
    #                 else:
    #                     raw_x = np.arange(len(raw_y)) if len(raw_y) > 0 else np.array([])
    #
    #                 x_vals, xlabel = process_axis_units(raw_x, final_desc, raw_unit, is_ndscan=True)
    #
    #                 if has_camera:
    #                     return extract_camera_data(x_vals, xlabel)
    #                 else:
    #                     # Standard PMT NDScan
    #                     y_vals = raw_y
    #                     err_vals = np.array(dict_datasets[key_name_err]) if key_name_err in dict_datasets else None
    #
    #                     min_len = min(len(x_vals), len(y_vals))
    #                     if err_vals is not None and len(err_vals) > 0:
    #                         min_len = min(min_len, len(err_vals))
    #                         err_vals = err_vals[:min_len]
    #
    #                     return {
    #                         "is_2d": False,
    #                         "is_camera": False,
    #                         "x": x_vals[:min_len],
    #                         "y": y_vals[:min_len],
    #                         "err": err_vals[:min_len] if err_vals is not None else None,
    #                         "xlabel": xlabel,
    #                         "ylabel": "counts"
    #                     }
    #
    #         except Exception as e:
    #             print(f"Error parsing NDScan RID {rid}: {e}")
    #
    #     # --- TYPE B: BARE ARTIQ 2D ---
    #     elif "ScanDataPlot.z_vals" in dict_datasets and not has_camera:
    #         z_mat = np.array(dict_datasets["ScanDataPlot.z_vals"])
    #         if z_mat.ndim == 2:
    #             raw_x = np.array(dict_datasets.get("ScanDataPlot.x_vals", np.arange(z_mat.shape[0])))
    #             raw_y_axis = np.array(dict_datasets.get("ScanDataPlot.y_vals", np.arange(z_mat.shape[1])))
    #             x_desc = dict_datasets.get("ScanDataPlot.x_label", getattr(self, 'rid_xlabels', {}).get(rid, "X Axis"))
    #             y_desc = dict_datasets.get("ScanDataPlot.y_label", getattr(self, 'rid_ylabels', {}).get(rid, "Y Axis"))
    #
    #             x_vals, xlabel = process_axis_units(raw_x, x_desc, is_ndscan=False)
    #             y_vals, ylabel = process_axis_units(raw_y_axis, y_desc, is_ndscan=False)
    #             return {"is_2d": True, "is_camera": False, "x": x_vals, "y": y_vals, "z": z_mat, "xlabel": xlabel,
    #                     "ylabel": ylabel, "zlabel": "counts"}
    #
    #     # --- TYPE C: BARE ARTIQ 1D (Or Bare Camera) ---
    #     elif "ScanDataPlot.x_vals" in dict_datasets or b"ScanDataPlot.x_vals" in dict_datasets or has_camera:
    #
    #         # Safely grab x_vals if they exist, otherwise empty array
    #         x_k = 'ScanDataPlot.x_vals'
    #         if b'ScanDataPlot.x_vals' in dict_datasets: x_k = b'ScanDataPlot.x_vals'
    #         raw_x = np.array(dict_datasets[x_k]) if x_k in dict_datasets else np.array([])
    #
    #         x_desc = dict_datasets.get("ScanDataPlot.x_label", getattr(self, 'rid_xlabels', {}).get(rid, getattr(self,
    #                                                                                                              'rid_labels',
    #                                                                                                              {}).get(
    #             rid, "Bare Scan")))
    #         x_vals, xlabel = process_axis_units(raw_x, x_desc, is_ndscan=False)
    #
    #         if has_camera:
    #             return extract_camera_data(x_vals, xlabel)
    #         else:
    #             # Standard PMT Barebones
    #             y_k = 'ScanDataPlot.y_vals' if 'ScanDataPlot.y_vals' in dict_datasets else b'ScanDataPlot.y_vals'
    #             y_vals = np.array(dict_datasets[y_k]) if y_k in dict_datasets else np.array([])
    #
    #             err_vals = None
    #             for err_k in ["ScanDataPlot.yerr_vals", b"ScanDataPlot.yerr_vals", "ScanDataPlot.y_error",
    #                           b"ScanDataPlot.y_error"]:
    #                 if err_k in dict_datasets:
    #                     err_vals = np.array(dict_datasets[err_k])
    #                     break
    #
    #             min_len = min(len(x_vals), len(y_vals))
    #             if err_vals is not None and len(err_vals) > 0:
    #                 min_len = min(min_len, len(err_vals))
    #                 err_vals = err_vals[:min_len]
    #
    #             return {"is_2d": False, "is_camera": False, "x": x_vals[:min_len], "y": y_vals[:min_len],
    #                     "err": err_vals[:min_len] if err_vals is not None else None, "xlabel": xlabel,
    #                     "ylabel": "counts"}
    #
    #     return None

    def get_data_from_rid(self, rid):
        """Extracts plot-ready data dictionary with robust unit & description parsing."""
        import json
        import numpy as np

        rid = int(rid)
        if rid not in self.dataDict:
            return None

        dict_datasets = self.dataDict[rid]

        # --- UNIFIED SINGLE-PASS UNIT PROCESSOR ---
        def process_axis_units(vals, desc="", unit=""):
            if vals is None or len(vals) == 0:
                return vals, desc

            vals = np.array(vals, dtype=float)

            if isinstance(desc, np.ndarray) and desc.ndim == 0: desc = desc.item()
            desc = desc.decode('utf-8', errors='ignore') if isinstance(desc, (bytes, bytearray)) else str(desc or "")

            if isinstance(unit, np.ndarray) and unit.ndim == 0: unit = unit.item()
            unit = unit.decode('utf-8', errors='ignore') if isinstance(unit, (bytes, bytearray)) else str(unit or "")

            desc_clean = desc.strip()
            desc_lower = f"{desc_clean} {unit}".lower()

            # Detect Time parameters (e.g. unit="s", "wait_time", "delay", "t_pulse", "duration")
            is_time = (
                    unit.lower() == 's' or
                    ' (s)' in desc_clean.lower() or
                    desc_clean.lower().endswith('[s]') or
                    any(w in desc_lower for w in ['time', 'delay', 'wait', 'duration', 'width', 'length'])
            )

            # Detect Frequency parameters (e.g. unit="Hz", "freq", "detuning")
            is_freq = (
                    unit.lower() == 'hz' or
                    ' (hz)' in desc_clean.lower() or
                    desc_clean.lower().endswith('[hz]') or
                    'freq' in desc_lower
            )

            if is_time:
                # Scale seconds -> milliseconds if not already converted
                if not ('(ms)' in desc_clean.lower() or '[ms]' in desc_clean.lower()):
                    vals = vals * 1e3
                    if " (s)" in desc_clean:
                        label = desc_clean.replace(" (s)", " (ms)")
                    elif desc_clean.endswith("[s]"):
                        label = desc_clean[:-3] + " [ms]"
                    else:
                        label = f"{desc_clean} (ms)"
                else:
                    label = desc_clean
            elif is_freq:
                # Scale Hz -> MHz if not already converted
                if not ('(mhz)' in desc_clean.lower() or '[mhz]' in desc_clean.lower()):
                    vals = vals * 1e-6
                    if " (Hz)" in desc_clean or " (hz)" in desc_clean:
                        label = desc_clean.replace(" (Hz)", " (MHz)").replace(" (hz)", " (MHz)")
                    elif desc_clean.endswith("[Hz]") or desc_clean.endswith("[hz]"):
                        label = desc_clean[:-4] + " [MHz]"
                    else:
                        label = f"{desc_clean} (MHz)"
                else:
                    label = desc_clean
            else:
                label = desc_clean
                if unit and not (f"({unit})" in label or f"[{unit}]" in label):
                    label = f"{label} ({unit})"

            return vals, label

        def find_desc_and_unit(obj):
            d, u = "", ""
            if isinstance(obj, dict):
                if 'description' in obj and isinstance(obj['description'], str): d = obj['description']
                if 'unit' in obj and isinstance(obj['unit'], str): u = obj['unit']
                for v in obj.values():
                    sub_d, sub_u = find_desc_and_unit(v)
                    if not d: d = sub_d
                    if not u: u = sub_u
            elif isinstance(obj, list):
                for item in obj:
                    sub_d, sub_u = find_desc_and_unit(item)
                    if not d: d = sub_d
                    if not u: u = sub_u
            return d, u

        # --- CAMERA DATA CHECK ---
        has_camera = False
        cam_key = None
        for k in dict_datasets.keys():
            k_str = k.decode('utf-8') if isinstance(k, (bytes, bytearray)) else str(k)
            if 'Camera.y' in k_str:
                has_camera = True
                cam_key = k
                break

        # --- ROBUST CAMERA EXTRACTION HELPER ---
        def extract_camera_data(raw_fallback_x, raw_desc, raw_unit=""):
            cam_raw = dict_datasets[cam_key]

            if isinstance(cam_raw, (bytes, bytearray)):
                cam_raw = cam_raw.decode('utf-8')

            cam_data = None
            if isinstance(cam_raw, str):
                try:
                    cam_data = json.loads(cam_raw)
                except Exception:
                    pass

            if cam_data is None:
                cam_data = np.array(dict_datasets[cam_key])

            y_dict_rois = {}
            err_dict_rois = {}

            if isinstance(cam_data, dict):
                for roi, roi_data in cam_data.items():
                    if isinstance(roi_data, dict) and 'value' in roi_data:
                        vals = np.array(roi_data['value'], dtype=float)
                    else:
                        vals = np.array(roi_data, dtype=float)

                    if vals.ndim == 1:
                        y_dict_rois[roi] = vals
                    elif vals.ndim == 2:
                        y_dict_rois[roi] = vals[:, 0]
                        if vals.shape[1] > 1:
                            e_vals = np.nan_to_num(vals[:, 1], nan=0.0)
                            e_vals[e_vals <= 0] = np.nan
                            err_dict_rois[roi] = e_vals
                        else:
                            err_dict_rois[roi] = None
            else:
                vals = np.array(cam_data, dtype=float)
                if vals.ndim == 1:
                    y_dict_rois["Camera ROI"] = vals
                elif vals.ndim == 2:
                    for col in range(vals.shape[1]):
                        y_dict_rois[f"ROI {col}"] = vals[:, col]

            # Determine RAW X Values first before converting units
            cam_key_str = cam_key.decode('utf-8') if isinstance(cam_key, bytes) else str(cam_key)
            x_cam_key_str = cam_key_str.replace('.y', '.x')
            x_cam_key_bytes = x_cam_key_str.encode('utf-8')

            x_vals_cam = None
            if x_cam_key_str in dict_datasets or x_cam_key_bytes in dict_datasets:
                x_k = x_cam_key_str if x_cam_key_str in dict_datasets else x_cam_key_bytes
                x_raw = dict_datasets[x_k]

                try:
                    if isinstance(x_raw, (bytes, bytearray)):
                        x_raw_parsed = json.loads(x_raw.decode('utf-8'))
                    elif isinstance(x_raw, str):
                        x_raw_parsed = json.loads(x_raw)
                    else:
                        x_raw_parsed = np.array(x_raw)

                    if not (isinstance(x_raw_parsed, dict) or (
                            isinstance(x_raw_parsed, np.ndarray) and x_raw_parsed.dtype.kind in {'U', 'S'})):
                        x_vals_cam = np.array(x_raw_parsed, dtype=float)
                except Exception:
                    pass

            if x_vals_cam is None:
                if b'ScanDataPlot.x_vals' in dict_datasets or 'ScanDataPlot.x_vals' in dict_datasets:
                    x_k = b'ScanDataPlot.x_vals' if b'ScanDataPlot.x_vals' in dict_datasets else 'ScanDataPlot.x_vals'
                    x_vals_cam = np.array(dict_datasets[x_k], dtype=float)
                else:
                    x_vals_cam = raw_fallback_x

            # SINGLE-PASS UNIT CONVERSION ON FINAL CHOSEN X ARRAY
            x_vals_cam, final_xlabel = process_axis_units(x_vals_cam, raw_desc, raw_unit)

            min_len = len(x_vals_cam)
            for r_vals in y_dict_rois.values():
                min_len = min(min_len, len(r_vals))

            for r_name in list(y_dict_rois.keys()):
                y_dict_rois[r_name] = y_dict_rois[r_name][:min_len]
                if err_dict_rois.get(r_name) is not None:
                    err_dict_rois[r_name] = err_dict_rois[r_name][:min_len]

            primary_roi_key = list(y_dict_rois.keys())[0] if y_dict_rois else None
            y_primary = y_dict_rois[primary_roi_key] if primary_roi_key else np.array([])

            return {
                "is_2d": False,
                "is_camera": True,
                "x": x_vals_cam[:min_len],
                "y": y_dict_rois,
                "y_primary": y_primary,
                "err": err_dict_rois,
                "xlabel": final_xlabel,
                "ylabel": "Camera Counts"
            }

        # --- TYPE A: NDSCAN ---
        ndscan_key = f'ndscan.rid_{rid}.axes'
        if ndscan_key in dict_datasets:
            try:
                axes_raw = dict_datasets[ndscan_key]
                if isinstance(axes_raw, np.ndarray) and axes_raw.ndim == 0: axes_raw = axes_raw.item()
                if isinstance(axes_raw, (bytes, bytearray)): axes_raw = axes_raw.decode('utf-8')
                axes_list = json.loads(axes_raw) if isinstance(axes_raw, str) else axes_raw

                key_name_y = f"ndscan.rid_{rid}.points.channel_counts"
                key_name_err = f"ndscan.rid_{rid}.points.channel_res_err"

                raw_y = np.array(dict_datasets[key_name_y], dtype=float) if key_name_y in dict_datasets else np.array(
                    [])
                is_2d_scan = isinstance(axes_list, list) and len(axes_list) >= 2

                if is_2d_scan or (raw_y.ndim == 2 and len(raw_y) > 0 and not has_camera):
                    axis_0_key = f"ndscan.rid_{rid}.points.axis_0"
                    axis_1_key = f"ndscan.rid_{rid}.points.axis_1"
                    raw_x0 = np.array(dict_datasets[axis_0_key],
                                      dtype=float) if axis_0_key in dict_datasets else np.array([])
                    raw_x1 = np.array(dict_datasets[axis_1_key],
                                      dtype=float) if axis_1_key in dict_datasets else np.array([])

                    if raw_y.ndim == 2:
                        z_mat = raw_y
                        x_vals_uniq = raw_x0 if len(raw_x0) == z_mat.shape[0] else np.arange(z_mat.shape[0])
                        y_vals_uniq = raw_x1 if len(raw_x1) == z_mat.shape[1] else np.arange(z_mat.shape[1])
                    else:
                        _, idx0 = np.unique(raw_x0, return_index=True)
                        x_vals_uniq = raw_x0[np.sort(idx0)]
                        _, idx1 = np.unique(raw_x1, return_index=True)
                        y_vals_uniq = raw_x1[np.sort(idx1)]
                        if len(x_vals_uniq) * len(y_vals_uniq) == len(raw_y):
                            z_mat = raw_y.reshape((len(x_vals_uniq), len(y_vals_uniq)))
                        else:
                            z_mat = np.full((len(x_vals_uniq), len(y_vals_uniq)), np.nan)
                            for px, py, val in zip(raw_x0, raw_x1, raw_y):
                                xi = np.where(x_vals_uniq == px)[0]
                                yi = np.where(y_vals_uniq == py)[0]
                                if len(xi) > 0 and len(yi) > 0: z_mat[xi[0], yi[0]] = val

                    x_desc = getattr(self, 'rid_xlabels', {}).get(rid, "")
                    y_desc = getattr(self, 'rid_ylabels', {}).get(rid, "")
                    x_unit, y_unit = "", ""
                    if isinstance(axes_list, list) and len(axes_list) >= 2:
                        if not x_desc: x_desc = axes_list[0].get('param', {}).get('description', 'X Axis')
                        x_unit = axes_list[0].get('param', {}).get('unit', '')
                        if not y_desc: y_desc = axes_list[1].get('param', {}).get('description', 'Y Axis')
                        y_unit = axes_list[1].get('param', {}).get('unit', '')

                    x_vals, xlabel = process_axis_units(x_vals_uniq, x_desc, x_unit)
                    y_vals, ylabel = process_axis_units(y_vals_uniq, y_desc, y_unit)
                    return {"is_2d": True, "is_camera": False, "x": x_vals, "y": y_vals, "z": z_mat, "xlabel": xlabel,
                            "ylabel": ylabel, "zlabel": "counts"}

                else:
                    key_name_x = f"ndscan.rid_{rid}.points.axis_0"
                    description, raw_unit = find_desc_and_unit(axes_list)
                    fallback_label = getattr(self, 'rid_xlabels', {}).get(rid, getattr(self, 'rid_labels', {}).get(rid,
                                                                                                                   "Scan Parameter"))
                    final_desc = description if description else fallback_label

                    if key_name_x in dict_datasets:
                        raw_x = np.array(dict_datasets[key_name_x], dtype=float)
                    else:
                        raw_x = np.arange(len(raw_y)) if len(raw_y) > 0 else np.array([])

                    if has_camera:
                        return extract_camera_data(raw_x, final_desc, raw_unit)
                    else:
                        x_vals, xlabel = process_axis_units(raw_x, final_desc, raw_unit)
                        y_vals = raw_y
                        err_vals = np.array(dict_datasets[key_name_err],
                                            dtype=float) if key_name_err in dict_datasets else None

                        min_len = min(len(x_vals), len(y_vals))
                        if err_vals is not None and len(err_vals) > 0:
                            min_len = min(min_len, len(err_vals))
                            err_vals = err_vals[:min_len]

                        return {
                            "is_2d": False,
                            "is_camera": False,
                            "x": x_vals[:min_len],
                            "y": y_vals[:min_len],
                            "err": err_vals[:min_len] if err_vals is not None else None,
                            "xlabel": xlabel,
                            "ylabel": "counts"
                        }

            except Exception as e:
                print(f"Error parsing NDScan RID {rid}: {e}")

        # --- TYPE B: BARE ARTIQ 2D ---
        elif "ScanDataPlot.z_vals" in dict_datasets and not has_camera:
            z_mat = np.array(dict_datasets["ScanDataPlot.z_vals"], dtype=float)
            if z_mat.ndim == 2:
                # FIX: z_mat.shape[0] is num_y, z_mat.shape[1] is num_x
                raw_x = np.array(dict_datasets.get("ScanDataPlot.x_vals", np.arange(z_mat.shape[1])), dtype=float)
                raw_y_axis = np.array(dict_datasets.get("ScanDataPlot.y_vals", np.arange(z_mat.shape[0])), dtype=float)

                x_desc = dict_datasets.get("ScanDataPlot.x_label", getattr(self, 'rid_xlabels', {}).get(rid, "X Axis"))
                y_desc = dict_datasets.get("ScanDataPlot.y_label", getattr(self, 'rid_ylabels', {}).get(rid, "Y Axis"))

                x_vals, xlabel = process_axis_units(raw_x, x_desc)
                y_vals, ylabel = process_axis_units(raw_y_axis, y_desc)
                return {"is_2d": True, "is_camera": False, "x": x_vals, "y": y_vals, "z": z_mat, "xlabel": xlabel,
                        "ylabel": ylabel, "zlabel": "counts"}

        # --- TYPE C: BARE ARTIQ 1D (Or Bare Camera) ---
        elif "ScanDataPlot.x_vals" in dict_datasets or b"ScanDataPlot.x_vals" in dict_datasets or has_camera:
            x_k = 'ScanDataPlot.x_vals'
            if b'ScanDataPlot.x_vals' in dict_datasets: x_k = b'ScanDataPlot.x_vals'
            raw_x = np.array(dict_datasets[x_k], dtype=float) if x_k in dict_datasets else np.array([])

            x_desc = dict_datasets.get("ScanDataPlot.x_label", getattr(self, 'rid_xlabels', {}).get(rid, getattr(self,
                                                                                                                 'rid_labels',
                                                                                                                 {}).get(
                rid, "Bare Scan")))

            if has_camera:
                return extract_camera_data(raw_x, x_desc)
            else:
                x_vals, xlabel = process_axis_units(raw_x, x_desc)
                y_k = 'ScanDataPlot.y_vals' if 'ScanDataPlot.y_vals' in dict_datasets else b'ScanDataPlot.y_vals'
                y_vals = np.array(dict_datasets[y_k], dtype=float) if y_k in dict_datasets else np.array([])

                err_vals = None
                for err_k in ["ScanDataPlot.yerr_vals", b"ScanDataPlot.yerr_vals", "ScanDataPlot.y_error",
                              b"ScanDataPlot.y_error"]:
                    if err_k in dict_datasets:
                        err_vals = np.array(dict_datasets[err_k], dtype=float)
                        break

                min_len = min(len(x_vals), len(y_vals))
                if err_vals is not None and len(err_vals) > 0:
                    min_len = min(min_len, len(err_vals))
                    err_vals = err_vals[:min_len]

                return {"is_2d": False, "is_camera": False, "x": x_vals[:min_len], "y": y_vals[:min_len],
                        "err": err_vals[:min_len] if err_vals is not None else None, "xlabel": xlabel,
                        "ylabel": "counts"}

        return None

    # --------------------------------------------------------------------------
    # PLOTTING HANDLERS
    # --------------------------------------------------------------------------
    def plotfiledata(self):
        """Bridge function connected to the 'Plot' button."""
        self.plotSelectedData()

    def plotSelectedData(self):
        """Full rebuild pass: clears plot and re-adds all checked 1D/2D datasets and syncs table colors."""
        self.analysisPlotWidget.clear_all()

        total_checked = len(self.dataCheckboxTraces)
        for k, RID in enumerate(list(self.dataCheckboxTraces.keys())):
            rid = int(RID)
            data = self.get_data_from_rid(rid)
            if data:
                self.analysisPlotWidget.add_dataset(
                    rid=rid,
                    data=data,
                    color_idx=k,
                    total_count=total_checked
                )

        self.updateTableRIDColors()

    # --------------------------------------------------------------------------
    # FITTING LOGIC
    # --------------------------------------------------------------------------
    def fitComboBoxList(self):
        self.fitselectionRowComboBox.addItems(list(self.fitlist.keys()))
        self.fitselectionRowComboBox.currentIndexChanged.connect(self.fittingTableParam)

        index = self.fitselectionRowComboBox.findText("Sinusoid")
        if index != -1:
            self.fitselectionRowComboBox.setCurrentIndex(index)

    def fittingTableParam(self):
        fittype = self.fitselectionRowComboBox.currentText()
        if not fittype or fittype not in self.fitlist:
            return

        fit_obj = self.fitlist[fittype]
        self.fitdescriptionLabel.setText(getattr(fit_obj, 'description', ''))

        try:
            rid, x_vals, y_vals, xlabel = self._get_active_fit_data()
        except ValueError:
            rid, x_vals, y_vals, xlabel = None, None, None, ""

        if rid is not None and x_vals is not None:
            print(f"Auto-guessing parameters for {fittype} on RID {rid}...")
            if hasattr(fit_obj, 'guess_parameters'):

                # --- NEW: Unwrap dictionary and convert to numpy arrays ---
                if isinstance(y_vals, dict):
                    roi_key = list(y_vals.keys())[0]
                    y_vals = y_vals[roi_key]

                import numpy as np
                x_vals = np.array(x_vals, dtype=float)
                y_vals = np.array(y_vals, dtype=float)
                # ----------------------------------------------------------

                fit_obj.guess_parameters(x_vals, y_vals, x_label=xlabel)

        num_rows = getattr(fit_obj, 'num_params', 0)
        cols = getattr(fit_obj, 'cols', 6)

        self.fitTableWidget.setRowCount(num_rows)
        self.fitTableWidget.setColumnCount(cols)
        self.fitTableWidget.setHorizontalHeaderLabels(['Enable', 'Parameter', 'Initial', 'Fit', 'Min', 'Max'])

        for row in range(num_rows):
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(fit_obj.params2Dlist[row][0])
            chk_widget = QtWidgets.QWidget()
            chk_layout = QtWidgets.QHBoxLayout(chk_widget)
            chk_layout.addWidget(checkbox)
            chk_layout.setAlignment(QtCore.Qt.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.fitTableWidget.setCellWidget(row, 0, chk_widget)

            self.fitTableWidget.setItem(row, 1, QtWidgets.QTableWidgetItem(str(fit_obj.params2Dlist[row][1])))

            val = fit_obj.params2Dlist[row][2]
            self.fitTableWidget.setItem(row, 2, QtWidgets.QTableWidgetItem(str(val)))

            self.fitTableWidget.setItem(row, 3, QtWidgets.QTableWidgetItem(""))

            min_val = fit_obj.params2Dlist[row][4]
            self.fitTableWidget.setItem(row, 4, QtWidgets.QTableWidgetItem(str(min_val)))

            max_val = fit_obj.params2Dlist[row][5]
            self.fitTableWidget.setItem(row, 5, QtWidgets.QTableWidgetItem(str(max_val)))

        self.fitTableWidget.horizontalHeader().setStretchLastSection(True)
        self.fitTableWidget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

    def _get_active_fit_data(self):
        if not self.fitCheckboxTraces:
            print("No data selected for fitting.")
            return None, None, None, None

        rid = list(self.fitCheckboxTraces.keys())[-1]
        data = self.get_data_from_rid(rid)

        if data is None or data.get("is_2d", False):
            print(f"RID {rid} is 2D or invalid for 1D fitting.")
            return None, None, None, None

        return rid, data["x"], data["y"], data["xlabel"]

    def _update_fit_params_from_table(self, fittype):
        fit_obj = self.fitlist[fittype]
        num_rows = fit_obj.num_params
        cols = fit_obj.cols

        for row in range(num_rows):
            chk_widget = self.fitTableWidget.cellWidget(row, 0)
            checkbox = chk_widget.findChild(QCheckBox) if chk_widget else None
            if checkbox:
                fit_obj.params2Dlist[row][0] = checkbox.isChecked()

            for col in range(2, cols):
                item = self.fitTableWidget.item(row, col)
                if item and item.text():
                    try:
                        fit_obj.params2Dlist[row][col] = float(item.text())
                    except ValueError:
                        print(f"Warning: Invalid value in fit table row {row} col {col}")

    def plotFitFunction(self):
        """Generates initial parameter fit curve using functionVal prior to fitting."""
        rid, x_vals, y_vals, xlabel = self._get_active_fit_data()
        if rid is None or x_vals is None:
            return

        fittype = self.fitselectionRowComboBox.currentText()
        if not fittype or fittype not in self.fitlist:
            return

        self._update_fit_params_from_table(fittype)
        fit_obj = self.fitlist[fittype]

        x_smooth = np.linspace(np.min(x_vals), np.max(x_vals), 500)

        try:
            y_smooth = fit_obj.functionVal(x_smooth)

            if not hasattr(self, 'fitTraces'):
                self.fitTraces = {}

            if rid in self.fitTraces:
                self.analysisPlotWidget.removeItem(self.fitTraces[rid])
                del self.fitTraces[rid]

            keys_as_ints = [int(k) for k in self.dataCheckboxTraces.keys()]
            k = keys_as_ints.index(rid) if rid in keys_as_ints else 0

            fitplotitem = self.analysisPlotWidget.plotfit(x_smooth, y_smooth, xlabel, 'counts', k, rid)
            self.fitTraces[rid] = fitplotitem

        except Exception as e:
            print(f"Error evaluating fit function for RID {rid}: {e}")

    def fitData(self):
        """
        Runs the fit for ALL RIDs currently checked in the 'Fit' column.
        Plots dashed rainbow fit curves matching dataset trace colors and updates parameter table.
        """
        fittype = self.fitselectionRowComboBox.currentText()
        if not fittype or fittype not in self.fitlist:
            return

        if not hasattr(self, 'fitCheckboxTraces'):
            self.fitCheckboxTraces = {}

        if not hasattr(self, 'fitTraces'):
            self.fitTraces = {}

        fit_obj = self.fitlist[fittype]

        # -------------------------------------------------------------
        # ITERATE OVER ALL CHECKED RIDS IN THE FIT COLUMN
        # -------------------------------------------------------------
        for rid in list(self.fitCheckboxTraces.keys()):
            rid = int(rid)

            # 1. Fetch dataset dictionary for this specific RID using FILTERED data
            data = self.get_filtered_data(rid)
            if not data or data.get("is_2d", False):
                print(f"Skipping fit for RID {rid}: No valid 1D data found.")
                continue

            x_vals = data.get("x")
            y_vals = data.get("y")
            xlabel = data.get("xlabel", "")
            ylabel = data.get("ylabel", "counts")

            if x_vals is None or len(x_vals) == 0:
                print(f"Skipping fit for RID {rid}: Empty dataset.")
                continue

            # --- NEW: Completely unwrap dictionary and convert to 1D numpy arrays ---
            if isinstance(y_vals, dict):
                roi_key = list(y_vals.keys())[0]
                y_vals = y_vals[roi_key]

            import numpy as np
            x_vals = np.array(x_vals, dtype=float)
            y_vals = np.array(y_vals, dtype=float)
            # ------------------------------------------------------------------------

            # ---> DIAGNOSTIC PRINT BLOCK <---
            print(f"\n--- DIAGNOSTIC FOR RID {rid} ---")
            print(f"X shape: {x_vals.shape}, Y shape: {y_vals.shape}")
            print(f"X contains NaN: {np.isnan(x_vals).any()}, Y contains NaN: {np.isnan(y_vals).any()}")
            print(f"X contains Inf: {np.isinf(x_vals).any()}, Y contains Inf: {np.isinf(y_vals).any()}")
            print(f"X min/max: {np.min(x_vals):.3e} / {np.max(x_vals):.3e}")
            print(f"Y min/max: {np.min(y_vals):.3e} / {np.max(y_vals):.3e}")
            print("--------------------------------\n")
            # --------------------------------

            # 2. Load parameters from fit table into fit object
            self._update_fit_params_from_table(fittype)

            try:
                # 3. Perform Fit using activateFit()
                _, params2DlistFit = fit_obj.activateFit(x_vals, y_vals)
                fit_obj.params2Dlist = params2DlistFit

                # self.fitTableWidget.blockSignals(True)

                # 4. Update the "Fit" column in the parameter table
                for ind, param in enumerate(params2DlistFit):
                    fit_val = param[3]
                    fmt = f"{fit_val:.4e}" if abs(fit_val) < 0.001 and fit_val != 0 else f"{fit_val:.4f}"
                    self.fitTableWidget.setItem(ind, 3, QtWidgets.QTableWidgetItem(fmt))

                # self.fitTableWidget.blockSignals(False)

                # 5. Generate Smooth Fit Curve using functionVal()
                initial_guesses_backup = [row[2] for row in fit_obj.params2Dlist]
                for row in fit_obj.params2Dlist:
                    row[2] = row[3]  # Swap Initial with Fit Result temporarily

                x_smooth = np.linspace(np.min(x_vals), np.max(x_vals), 500)
                y_smooth = fit_obj.functionVal(x_smooth)

                # Restore Initial Guesses for next loop iteration / manual adjustments
                for i, row in enumerate(fit_obj.params2Dlist):
                    row[2] = initial_guesses_backup[i]

                # 6. Remove existing trace if re-fitting
                if rid in self.fitTraces:
                    self.analysisPlotWidget.removeItem(self.fitTraces[rid])
                    del self.fitTraces[rid]

                # 7. Match color index 'k' to trace index in dataCheckboxTraces
                keys_as_ints = [int(k) for k in self.dataCheckboxTraces.keys()]
                k = keys_as_ints.index(rid) if rid in keys_as_ints else 0

                # Render dashed fit trace on plot widget using CET-R2 colormap
                fitplotitem = self.analysisPlotWidget.plotfit(x_smooth, y_smooth, xlabel, ylabel, k, rid)
                self.fitTraces[rid] = fitplotitem

            except Exception as e:
                print(f"Fitting failed for RID {rid}: {e}")

# ==============================================================================
# ANALYSIS PLOT WIDGET CLASS (1D Plots + 2D Heatmaps)
# ==============================================================================
import pyqtgraph as pg
import numpy as np
from PyQt5 import QtGui, QtCore  # Use PySide6 / PyQt6 if using PySide


class AnalysisPlotWidget(pg.PlotWidget):

    def __init__(self, parent=None):
        super(AnalysisPlotWidget, self).__init__(parent)
        self.showGrid(x=True, y=True)
        self.setBackground('w')

        # 1D plots use the CET-R2 rainbow colormap
        self.colormap_1d = pg.colormap.get("CET-R2")

        # Keep your 2D heatmap colormap separate (e.g., viridis/plasma)
        self.colormap_2d = pg.colormap.get("viridis")

        self.rid_items = {}

        # Hover coordinate data state
        self.x_vals = None
        self.y_vals = None
        self.z_mat = None
        self.is_2d = False

        # Tile-Snapping Crosshair Lines & Hover Text
        crosshair_pen = pg.mkPen('gray', width=1, style=QtCore.Qt.DashLine)
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=crosshair_pen)
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=crosshair_pen)
        self.v_line.setZValue(90)
        self.h_line.setZValue(90)

        self.hover_text = pg.TextItem(
            anchor=(-0.05, 1.05),
            fill=pg.mkBrush(255, 255, 255, 230),
            border=pg.mkPen('k', width=1)
        )
        self.hover_text.setZValue(100)

        self._ensure_hover_items()
        self.proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

    def _ensure_hover_items(self):
        """Ensures crosshair lines and hover text item remain attached."""
        if self.hover_text not in self.plotItem.items:
            self.addItem(self.hover_text, ignoreBounds=True)
            self.hover_text.setVisible(False)
        if self.v_line not in self.plotItem.items:
            self.addItem(self.v_line, ignoreBounds=True)
            self.v_line.setVisible(False)
        if self.h_line not in self.plotItem.items:
            self.addItem(self.h_line, ignoreBounds=True)
            self.h_line.setVisible(False)

    def add_dataset(self, rid, data, color_idx=0, total_count=1):
        """Adds or updates a dataset for a specific RID when its checkbox is checked."""
        rid = int(rid)

        # Remove old instance if re-adding
        if rid in self.rid_items:
            self.remove_dataset(rid)

        # Ensure legend exists for ROI names
        if self.plotItem.legend is None:
            self.addLegend()

        is_2d = data.get("is_2d", False)
        is_camera = data.get("is_camera", False)  # Extract our new flag

        if is_2d:
            # Remove any existing 2D scan heatmaps to prevent overlapping 2D layers
            for existing_rid in list(self.rid_items.keys()):
                if self.rid_items[existing_rid]['is_2d']:
                    self.remove_dataset(existing_rid)

            img_item = pg.ImageItem()
            z_mat = data["z"]  # Shape: (num_y, num_x)
            x_vals = data["x"]  # Length: num_x
            y_vals = data["y"]  # Length: num_y

            # --- FIX: Transpose z_mat to shape (num_x, num_y) for PyQtGraph ---
            img_item.setImage(z_mat.T)

            plasma_cmap = pg.colormap.get("plasma")
            lut = plasma_cmap.getLookupTable(nPts=256)
            img_item.setLookupTable(lut)

            z_min = float(np.nanmin(z_mat)) if not np.isnan(z_mat).all() else 0.0
            z_max = float(np.nanmax(z_mat)) if not np.isnan(z_mat).all() else 1.0
            if z_min == z_max:
                z_max += 1.0
            img_item.setLevels([z_min, z_max])

            if len(x_vals) > 1 and len(y_vals) > 1:
                dx = (x_vals[-1] - x_vals[0]) / (len(x_vals) - 1)
                dy = (y_vals[-1] - y_vals[0]) / (len(y_vals) - 1)
                rect = QtCore.QRectF(
                    x_vals[0] - dx / 2.0,
                    y_vals[0] - dy / 2.0,
                    (x_vals[-1] - x_vals[0]) + dx,
                    (y_vals[-1] - y_vals[0]) + dy
                )
                img_item.setRect(rect)

            self.addItem(img_item)

            colorbar = None
            try:
                colorbar = pg.ColorBarItem(values=(z_min, z_max), cmap=plasma_cmap, interactive=False)
                colorbar.setColorMap(plasma_cmap)
                colorbar.setImageItem(img_item, insert_in=self.plotItem)

                cb_font = QtGui.QFont()
                cb_font.setPointSize(14)
                cb_font.setBold(False)
                cb_axis = colorbar.getAxis('right')
                cb_axis.setTickFont(cb_font)
                cb_axis.setTextPen('k')
                cb_axis.setPen('k')
            except Exception as e:
                print(f"ColorBarItem warning: {e}")

            self.rid_items[rid] = {
                'curves': [],
                'image': img_item,
                'colorbar': colorbar,
                'is_2d': True,
                'is_camera': is_camera,
                'x': x_vals,
                'y': y_vals,
                'z': z_mat
            }

            self.is_2d = True
            self.x_vals, self.y_vals, self.z_mat = x_vals, y_vals, z_mat
            self._apply_axis_styles(data["xlabel"], data["ylabel"], title=f"RID {rid}")

        else:
            x = np.asarray(data["x"])
            items_list = []

            # ---------------------------------------------------------
            # 1D CAMERA MULTI-ROI PLOTTING
            # ---------------------------------------------------------
            if is_camera:
                y_dict = data["y"]
                err_dict = data.get("err", {})

                # --- NEW: Use CET-R2 colormap for Camera ROIs instead of categorical palette ---
                num_rois = len(y_dict)
                roi_colors = self.colormap_1d.getLookupTable(nPts=max(1, num_rois), alpha=True, mode='qcolor')

                for i, (roi_name, y_vals) in enumerate(y_dict.items()):
                    y = np.asarray(y_vals)
                    min_len = min(len(x), len(y))
                    x_sub, y_sub = x[:min_len], y[:min_len]

                    # Pick the color from the generated CET-R2 palette
                    color = roi_colors[i % len(roi_colors)]
                    ppen = pg.mkPen(color, width=2)

                    curve = self.plot(
                        x_sub, y_sub,
                        pen=ppen,
                        symbol='o',
                        symbolSize=8,
                        symbolBrush=color,
                        name=f"{rid}: {roi_name}"
                    )
                    items_list.append(curve)

                    err_vals = err_dict.get(roi_name)
                    if err_vals is not None:
                        err_vals = np.asarray(err_vals)[:min_len]
                        if len(err_vals) == min_len:
                            error_bars = pg.ErrorBarItem(x=x_sub, y=y_sub, top=err_vals, bottom=err_vals, pen=ppen)
                            self.addItem(error_bars)
                            items_list.append(error_bars)

                self.rid_items[rid] = {
                    'curves': items_list,
                    'image': None,
                    'colorbar': None,
                    'is_2d': False,
                    'is_camera': True,
                    'x': x,
                    'y': y_dict,
                    'z': None
                }

            # ---------------------------------------------------------
            # 1D PMT SINGLE-TRACE PLOTTING
            # ---------------------------------------------------------
            else:
                y = np.asarray(data["y"])
                min_len = min(len(x), len(y))
                if len(x) != len(y):
                    x = x[:min_len]
                    y = y[:min_len]

                # Generate color from CET-R2
                colors = self.colormap_1d.getLookupTable(nPts=max(1, total_count), alpha=True, mode='qcolor')
                current_color = colors[color_idx % len(colors)]
                ppen = pg.mkPen(current_color, width=2)

                curve = self.plot(
                    x, y,
                    pen=ppen,
                    symbol='o',
                    symbolSize=10,
                    symbolBrush=current_color,
                    name=str(rid)
                )
                items_list.append(curve)

                y_error = data.get("err")
                if y_error is not None:
                    y_error = np.asarray(y_error)[:min_len]
                    if len(y_error) == min_len:
                        error_bars = pg.ErrorBarItem(x=x, y=y, top=y_error, bottom=y_error, pen=ppen)
                        self.addItem(error_bars)
                        items_list.append(error_bars)

                self.rid_items[rid] = {
                    'curves': items_list,
                    'image': None,
                    'colorbar': None,
                    'is_2d': False,
                    'is_camera': False,
                    'x': x,
                    'y': y,
                    'z': None
                }

            self.is_2d = False
            self.x_vals, self.y_vals, self.z_mat = x, None, None
            self._apply_axis_styles(data["xlabel"], data["ylabel"])

        self._recolor_1d_curves()
        self._ensure_hover_items()

    def _recolor_1d_curves(self):
        """Recolors active 1D PMT curves (ignores Camera ROIs to preserve distinct colors)."""
        d_1d = [r for r, d in self.rid_items.items() if not d.get('is_2d', False) and not d.get('is_camera', False)]
        if not d_1d:
            return

        colors = self.colormap_1d.getLookupTable(nPts=max(1, len(d_1d)), alpha=True, mode='qcolor')

        for idx, rid in enumerate(d_1d):
            color = colors[idx % len(colors)]
            pen = pg.mkPen(color, width=2)

            item_data = self.rid_items[rid]

            # Recolor main trace items
            for item in item_data.get('curves', []):
                if isinstance(item, pg.PlotDataItem):
                    item.setPen(pen)
                    item.setSymbolBrush(color)
                elif isinstance(item, pg.ErrorBarItem):
                    item.setData(pen=pen)

    def remove_dataset(self, rid):
        """Removes graphics items and colorbars ONLY for the specified RID upon unchecking."""
        rid = int(rid)
        if rid not in self.rid_items:
            return

        item_dict = self.rid_items.pop(rid)

        # 1. Remove 1D curves & errorbars
        for item in item_dict['curves']:
            try:
                self.removeItem(item)
            except Exception:
                pass

        # 2. Remove 2D ImageItem
        if item_dict['image'] is not None:
            try:
                self.removeItem(item_dict['image'])
            except Exception:
                pass

        # 3. Safely remove ColorBarItem from layout grid
        if item_dict['colorbar'] is not None:
            cb = item_dict['colorbar']
            try:
                cb.setImageItem(None)
            except Exception:
                pass
            try:
                self.plotItem.layout.removeItem(cb)
            except Exception:
                pass
            try:
                self.removeItem(cb)
                cb.deleteLater()
            except Exception:
                pass

        # 4. Handle state when plot becomes empty vs when other datasets remain
        if not self.rid_items:
            self._reset_state()
        else:
            self._recolor_1d_curves()

    def _reset_state(self):
        """Resets plot metadata, titles, and hover elements without re-entering clear loops."""
        self.is_2d = False
        self.x_vals = None
        self.y_vals = None
        self.z_mat = None
        if hasattr(self, 'hover_text'):
            self.hover_text.setVisible(False)
        if hasattr(self, 'v_line'):
            self.v_line.setVisible(False)
        if hasattr(self, 'h_line'):
            self.h_line.setVisible(False)
        self.setTitle("")
        self._ensure_hover_items()

    def clear_all(self):
        """Wipes all active dataset items, colorbars, and resets the canvas cleanly."""
        rids = list(self.rid_items.keys())
        for r in rids:
            self.remove_dataset(r)

        self.rid_items.clear()

        # Direct call to internal plotItem to bypass super() __getattr__ limitations
        if hasattr(self, 'plotItem'):
            self.plotItem.clear()

        self._reset_state()

    def clear(self):
        self.clear_all()

    def _apply_axis_styles(self, xlabel, ylabel, title=""):
        styled_xlabel = f'<span style="font-size: 16pt; color: black;">{xlabel}</span>'
        styled_ylabel = f'<span style="font-size: 16pt; color: black;">{ylabel}</span>'

        self.setLabel('bottom', text=styled_xlabel)
        self.setLabel('left', text=styled_ylabel)

        if title:
            styled_title = f'<span style="font-size: 20pt; color: black;">{title}</span>'
            self.setTitle(styled_title)
        else:
            self.setTitle("")

        tick_font = QtGui.QFont()
        tick_font.setPointSize(14)
        tick_font.setBold(False)

        bottom_axis = self.getAxis('bottom')
        left_axis = self.getAxis('left')

        bottom_axis.setTickFont(tick_font)
        left_axis.setTickFont(tick_font)

        bottom_axis.setTextPen('k')
        left_axis.setTextPen('k')
        bottom_axis.setPen('k')
        left_axis.setPen('k')

    def _on_mouse_moved(self, evt):
        if evt is None:
            return

        pos = evt[0]
        if not self.plotItem.sceneBoundingRect().contains(pos):
            self.hover_text.setVisible(False)
            self.v_line.setVisible(False)
            self.h_line.setVisible(False)
            return

        mouse_point = self.plotItem.vb.mapSceneToView(pos)
        x_coord = mouse_point.x()
        y_coord = mouse_point.y()

        z_str = "N/A"
        x_tile_center = x_coord
        y_tile_center = y_coord
        has_valid_tile = False

        if self.is_2d and self.z_mat is not None and self.x_vals is not None and self.y_vals is not None:
            x_min, x_max = min(self.x_vals[0], self.x_vals[-1]), max(self.x_vals[0], self.x_vals[-1])
            y_min, y_max = min(self.y_vals[0], self.y_vals[-1]), max(self.y_vals[0], self.y_vals[-1])

            if x_min <= x_coord <= x_max and y_min <= y_coord <= y_max:
                x_idx = int(np.abs(self.x_vals - x_coord).argmin())
                y_idx = int(np.abs(self.y_vals - y_coord).argmin())

                if x_idx < self.z_mat.shape[0] and y_idx < self.z_mat.shape[1]:
                    val = self.z_mat[x_idx, y_idx]
                    z_str = f"{val:.4g}" if not np.isnan(val) else "NaN"

                    x_tile_center = self.x_vals[x_idx]
                    y_tile_center = self.y_vals[y_idx]
                    has_valid_tile = True

        if has_valid_tile:
            self.v_line.setPos(x_tile_center)
            self.h_line.setPos(y_tile_center)
            self.v_line.setVisible(True)
            self.h_line.setVisible(True)
        else:
            self.v_line.setVisible(False)
            self.h_line.setVisible(False)

        table_html = f"""
        <table style="color: black; font-size: 10pt; font-family: monospace; border-collapse: collapse; padding: 2px;">
            <tr><td style="text-align: right; font-weight: bold; padding-right: 4px;">x:</td><td>{x_tile_center:.4g}</td></tr>
            <tr><td style="text-align: right; font-weight: bold; padding-right: 4px;">y:</td><td>{y_tile_center:.4g}</td></tr>
            <tr><td style="text-align: right; font-weight: bold; padding-right: 4px;">z:</td><td>{z_str}</td></tr>
        </table>
        """
        self.hover_text.setHtml(table_html)
        self.hover_text.setPos(x_coord, y_coord)
        self.hover_text.setVisible(True)

    def get_rid_colors(self):
        """Returns a dictionary mapping active 1D PMT RID -> QColor."""
        d_1d = [r for r, d in self.rid_items.items() if not d.get('is_2d', False) and not d.get('is_camera', False)]
        if not d_1d:
            return {}
        colors = self.colormap_1d.getLookupTable(nPts=max(1, len(d_1d)), alpha=True, mode='qcolor')
        return {r: colors[i % len(colors)] for i, r in enumerate(d_1d)}

    @property
    def colormap(self):
        """Ensures any legacy fit functions looking for .colormap automatically use .colormap_1d."""
        return self.colormap_1d

    def plotfit(self, x, y, xlabel, ylabel, k, rid):
        """Plots a 1D fit curve using the exact color assigned to this RID's data trace."""
        rid = int(rid)

        # Default fallback color
        fit_color = pg.mkColor('r')

        # 1. Fetch exact color directly from the plotted data curve for this RID
        if rid in self.rid_items and self.rid_items[rid].get('curves'):
            # Find the main data trace (PlotDataItem) and extract its exact pen color
            for item in self.rid_items[rid]['curves']:
                if isinstance(item, pg.PlotDataItem):
                    fit_color = item.opts['pen'].color()
                    break
        else:
            # Fallback if the data trace isn't plotted but we are forcing a fit
            colors = self.colormap_1d.getLookupTable(nPts=max(1, k+1), alpha=True, mode='qcolor')
            fit_color = colors[k % len(colors)]

        # 2. Create solid pen matching the exact trace color
        # --- CHANGED: style=QtCore.Qt.SolidLine ---
        ppen = pg.mkPen(color=fit_color, width=3, style=QtCore.Qt.SolidLine)

        # 3. Plot fit trace
        plotitem = self.plot(x, y, pen=ppen, name=f"{rid}: Fit")

        # Re-apply rich-text styling and tick sizes to keep axis font legible
        self._apply_axis_styles(xlabel, ylabel)

        return plotitem

# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main():
    app = QtWidgets.QApplication(sys.argv)
    print("Starting Application...")
    main_win = MainWindow()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
