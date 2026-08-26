# from PyQt5 import QtWidgets, QtGui, QtCore
# from PyQt5.QtWidgets import *
# from PyQt5.QtCore import QTimer, Qt
# from PyQt5.QtGui import QColor
# from pyqtgraph import PlotWidget, plot
# import pyqtgraph as pg
# from pyqtgraph.dockarea import *
# import sys  # We need sys so that we can pass argv to QApplication
# import numpy as np
# import os
# from ndscan.experiment import *
# from oitg import *
# import time
# from oitg.results import *
# from oitg.fitting import *
# import numpy as np
# import matplotlib
# # %matplotlib tk
# import matplotlib.pyplot as plt
# from scipy.optimize import curve_fit
# import scipy.optimize
# import pylab as plt
# import pickle
# import json
# # from mpl_interactions import ioff, panhandler, zoom_factory
# import oitg
# import matplotlib.ticker as mticker
# import FitFunctions_barebones_ndscan as fitfunc
# import random
# import datetime
#
# '''
# Simple Analysis GUI for experiment feedback.
#
# '''
#
#
#
# class DockArea(DockArea):
#     ## This is to prevent the Dock from being resized to te point of disappear
#     def makeContainer(self, typ):
#         new = super(DockArea, self).makeContainer(typ)
#         new.setChildrenCollapsible(False)
#         return new
#
# class MainWindow(QtWidgets.QMainWindow):
#
#     def __init__(self):
#         QtWidgets.QMainWindow.__init__(self)
#         print("Hello")
#         self.setWindowTitle("Analysis Window")
#         layout=QtWidgets.QVBoxLayout()
#         dock_area=DockArea(self)
#         # testlabel=QtWidgets.QLabel("Meaningful docks?")
#         # layout.addWidget(testlabel)
#         central_widget=QtWidgets.QWidget()
#         central_widget.setLayout(layout)
#         self.setCentralWidget(central_widget)
#
#         # Plotting
#         self.plotdock = Dock("AnalysisPlot", size=(600, 400))
#         self.graphWidget = AnalysisPlotWidget()
#         self.plotdock.addWidget(self.graphWidget)
#         self.plotdock.setGeometry(0, 0, 1000, 500)
#
#         #Search and fitting
#         self.searchFitDock=Dock("Search&Fit", size=(600,400))
#         self.searchFitDock.setMaximumWidth(600)
#         searchFitlayout=QtWidgets.QVBoxLayout()
#         self.searchFitWidget=SearchFitWidget(self.graphWidget) # passing plot object to search widget for inheritance
#         self.searchFitDock.setLayout(searchFitlayout)
#         self.searchFitDock.addWidget(self.searchFitWidget)
#
#         # self.plotdock.hideTitleBar()
#         # self.plotdock.hideTitleBar()
#
#         layout.addWidget(dock_area)
#         dock_area.addDock(self.searchFitDock)
#         dock_area.addDock(self.plotdock,'right',self.searchFitDock)
#         #dock_area.addDock(self.plotdock)
#         #self.graphWidget.plotdata()#np.arange(10),np.arange(10))
#
#         #self.setGeometry(500, 25, 800, 600)
#         self.show()
#
# class SearchFitWidget(QtWidgets.QWidget):
#
#     # 26/01/06 gt
#     def __init__(self, analysisplotWidget):
#         super(SearchFitWidget, self).__init__()
#
#         # --- PATH CONFIGURATION ---
#         self.base_path = "C:/Users/TrappedIonRice4/Documents/Artiq-Rice"
#         self.lastridfile = os.path.join(self.base_path, "last_rid.pyon")
#         self.results_path = os.path.join(self.base_path, "results")
#
#         # Determine latest subdirectory
#         try:
#             if os.path.exists(self.results_path):
#                 all_subdir = [f.name for f in os.scandir(self.results_path) if f.is_dir()]
#                 all_subdir.sort()
#                 self.latest_subdir = os.path.join(self.results_path,
#                                                   all_subdir[-1]) if all_subdir else self.results_path
#             else:
#                 self.latest_subdir = self.results_path
#         except Exception as e:
#             print(f"Error finding subdirectories: {e}")
#             self.latest_subdir = self.results_path
#
#         self.updated_path = self.latest_subdir
#
#         # Variables
#         self.filelist = []
#         self.selectedfilelist = []
#         self.fitlist = fitfunc.FIT_DICTIONARY
#         self.num_rids = 200
#         self.filterScanNames = ['executeScan', 'BarebonesArtiqScanV2', 'BarebonesArtiqScan2DV1']
#
#         self.dataDict = {}
#         self.selectedDataDict = {}
#         self.fitTraces = {}
#         self.fitCheckboxTraces = {}
#         self.dataCheckboxTraces = {}
#
#         # Classes
#         self.analysisPlotWidget = analysisplotWidget
#
#         # --- GRAPHICS LAYOUT ---
#         self.searchFitLayout = QtWidgets.QVBoxLayout()
#         self.setLayout(self.searchFitLayout)
#
#         # 1. ADD SPACING TO MAIN LAYOUT (Global Settings)
#         self.searchFitLayout.setSpacing(10)  # 10px gap between vertical elements
#         self.searchFitLayout.setContentsMargins(10, 10, 10, 10)  # 10px margin around the edges
#
#         # ----------------------------
#         # SECTION 1: SEARCH & FILES
#         # ----------------------------
#         self.searchFitHLayout = QtWidgets.QHBoxLayout()
#         self.searchFitHLayout.setSpacing(10)  # Space between search label and button
#
#         self.searchLabel = QtWidgets.QLabel('Search for files')
#         self.searchFitHLayout.addWidget(self.searchLabel)
#         self.searchFitFileExplorerButton = QtWidgets.QPushButton('RID File Explorer')
#         self.searchFitHLayout.addWidget(self.searchFitFileExplorerButton)
#         self.searchFitHLayout.addStretch()  # Push to left
#         self.searchFitLayout.addLayout(self.searchFitHLayout)
#
#         # Data Action Buttons
#         self.buttonsHlayout = QtWidgets.QHBoxLayout()
#         self.buttonsHlayout.setSpacing(15)  # Bigger space between main action buttons
#
#         self.plotButtonWidget = QtWidgets.QPushButton('Plot')
#         self.clearplotsButtonWidget = QtWidgets.QPushButton('Clear')
#         self.autoplotCheckBox = QtWidgets.QCheckBox("Autoplot last RID")
#
#         self.buttonsHlayout.addWidget(self.plotButtonWidget)
#         self.buttonsHlayout.addWidget(self.clearplotsButtonWidget)
#         self.buttonsHlayout.addWidget(self.autoplotCheckBox)
#         self.buttonsHlayout.addStretch()
#         self.searchFitLayout.addLayout(self.buttonsHlayout)
#
#         # File Table
#         self.fileTableWidget = QtWidgets.QTableWidget()
#         self.fileTableWidget.setColumnCount(5)
#         self.fileTableWidget.setHorizontalHeaderLabels(['rid', 'Data', 'Fit', 'Scan parameter', 'Comments'])
#         self.rid_colInd = 0
#         self.dataChk_colInd = 1
#         self.fitChk_colInd = 2
#         self.ScanParameter_colInd = 3
#         self.Comments_colInd = 4
#         self.fileTableWidget.setShowGrid(False)
#         vscrollbar = QtWidgets.QScrollBar(self)
#         self.fileTableWidget.setVerticalScrollBar(vscrollbar)
#         self.fileTableWidget.setSelectionMode(2)
#
#         self.searchFitLayout.addWidget(self.fileTableWidget)
#
#         # ----------------------------
#         # SEPARATOR
#         # ----------------------------
#         self.searchFitLayout.addSpacing(20)  # Add 20px gap before fitting section
#
#         # ----------------------------
#         # SECTION 2: FITTING
#         # ----------------------------
#         self.fitselectionColumnWidget = QtWidgets.QWidget()
#         self.fitselectionColumnLayout = QtWidgets.QVBoxLayout()
#         self.fitselectionColumnWidget.setLayout(self.fitselectionColumnLayout)
#         self.fitselectionColumnLayout.setContentsMargins(0, 0, 0, 0)  # Remove internal margins
#
#         # Fit Control Row
#         self.fitselectionRowWidget = QtWidgets.QWidget()
#         self.fitselectionRowlayout = QtWidgets.QHBoxLayout()
#         self.fitselectionRowlayout.setSpacing(10)  # Space between fit buttons
#         self.fitselectionRowWidget.setLayout(self.fitselectionRowlayout)
#
#         self.fitselectionRowLabel = QtWidgets.QLabel('Fit Type:')
#         self.fitselectionRowComboBox = QtWidgets.QComboBox()
#         self.fitselectionRowFitButton = QtWidgets.QPushButton('Fit')
#         self.fitselectionRowPlotButton = QtWidgets.QPushButton('Plot Fn')
#         self.fitselectionRowClearFitButton = QtWidgets.QPushButton('Clear fit')
#
#         self.autoFitCheckbox = QtWidgets.QCheckBox("Auto Fit & Plot")
#         self.autoFitCheckbox.setChecked(False)
#         self.autoFitCheckbox.setToolTip("Automatically run fit when new scan arrives")
#         # Connect the checkbox signal to the function above
#         self.autoFitCheckbox.stateChanged.connect(self.toggleAutoFitLastRow)
#
#         self.fitselectionRowlayout.addWidget(self.fitselectionRowLabel)
#         self.fitselectionRowlayout.addWidget(self.fitselectionRowComboBox)
#         self.fitselectionRowlayout.addWidget(self.fitselectionRowFitButton)
#         self.fitselectionRowlayout.addWidget(self.fitselectionRowPlotButton)
#         self.fitselectionRowlayout.addWidget(self.fitselectionRowClearFitButton)
#         self.fitselectionRowlayout.addSpacing(15)  # Extra gap before checkbox
#         self.fitselectionRowlayout.addWidget(self.autoFitCheckbox)
#         self.fitselectionRowlayout.addStretch()
#
#         self.fitselectionColumnLayout.addWidget(self.fitselectionRowWidget)
#
#         # Description Label
#         self.fitdescriptionLabel = QtWidgets.QLabel('')
#         self.fitdescriptionLabel.setAlignment(Qt.AlignCenter)
#         self.fitselectionColumnLayout.addWidget(self.fitdescriptionLabel)
#
#         self.searchFitLayout.addWidget(self.fitselectionColumnWidget)
#
#         # Fit Parameter Table
#         self.fitTableWidget = QtWidgets.QTableWidget()
#         self.searchFitLayout.addWidget(self.fitTableWidget)
#
#         # --- INITIALIZATION ---
#         self.last_rid = self.extractingLastrid(self.lastridfile)
#         if self.last_rid is None: self.last_rid = 0
#
#         self.searchfiles(self.last_rid, self.num_rids, self.updated_path)
#
#         self.Searchtimer = QTimer(self)
#         self.Searchtimer.setInterval(1000)
#         self.Searchtimer.timeout.connect(self.autofunctions)
#         self.Searchtimer.start()
#
#         self.fitComboBoxList()
#         self.fittingTableParam()
#         self.onClickFunctions()
#
#     def onClickFunctions(self): # needs to be updated
#         self.plotButtonWidget.clicked.connect(self.plotfiledata)
#         self.clearplotsButtonWidget.clicked.connect(self.clearPlots)
#         self.autoplotCheckBox.stateChanged.connect(self.autoPlotLastRID)
#         self.fitselectionRowFitButton.clicked.connect(self.fitData)
#         self.fitselectionRowClearFitButton.clicked.connect(self.clearFitPlot)
#         self.fitselectionRowPlotButton.clicked.connect(self.plotFitFunction)
#         self.searchFitFileExplorerButton.clicked.connect(self.fileExplorerDialog)
#
#     def fileExplorerDialog(self):
#         # Set default directory
#         default_directory = os.path.expanduser(self.updated_path)  # Example: Start from the Documents folder
#         # Open file dialog starting from the default directory
#         file_path, _ = QFileDialog.getOpenFileName(self, "Select a File", default_directory)
#
#         if file_path:
#             print(f"Selected File: {file_path}")
#             file_path_list=file_path.split('/')
#             rid_filename=file_path_list[-1]
#             rid_filename_list=rid_filename.split('-')
#             rid=int(rid_filename_list[0])
#             print(rid)
#             joined_list='/'.join(file_path_list[:-2])
#             print(joined_list)
#             self.searchSingleFile(rid,joined_list)
#         # must meet requirement of multiple rids too. Getting too invasive vs having to just enter rid and
#
#     # 26/01/29 gt: for moving window to work
#     def findRowByRID(self, rid):
#         """
#         Robustly finds the current row index of a given RID.
#         """
#         # Search column 0 (RID column) for the specific text
#         items = self.fileTableWidget.findItems(str(rid), QtCore.Qt.MatchExactly)
#
#         # We assume RIDs are unique, so we take the first match
#         if items:
#             return items[0].row()
#         return None
#
#     # 26/01/06 gt
#     def selectRangesCheckbox(self, rid, row, col, state):
#         '''
#         Looks for multiple elements checked in a checkbox column and stores an ordered dictionary of row values.
#         Triggers table update if the Fit checkbox is toggled.
#         Shows data plot and fit with data shen Data and Fit checkboxes are checked
#         '''
#
#         # 26/01/29 gt: for moving window
#         # The 'row' argument comes from a lambda created in the past.
#         # It might be stale if rows were deleted. We find the real row now.
#         actual_row = self.findRowByRID(rid)
#
#         if actual_row is None:
#             # The RID might have been deleted by the window limit just as we clicked
#             print(f"Warning: RID {rid} not found in table (scrolled off?).")
#             return
#
#         row = actual_row  # Update the variable to the correct index
#
#         # 1. Handle FIT Checkbox
#         if col == self.fitChk_colInd:
#             if state == Qt.Checked:
#                 if rid not in self.fitCheckboxTraces:
#                     self.fitCheckboxTraces[rid] = row
#
#             elif state == Qt.Unchecked:
#                 if rid in self.fitCheckboxTraces:
#                     del self.fitCheckboxTraces[rid]
#
#                 # Remove specific fit curve
#                 if hasattr(self, 'fitTraces') and rid in self.fitTraces:
#                     self.analysisPlotWidget.removeItem(self.fitTraces[rid])
#                     del self.fitTraces[rid]
#
#         # 2. Handle DATA Checkbox
#         elif col == self.dataChk_colInd:
#             if state == Qt.Checked:
#                 if rid not in self.dataCheckboxTraces:
#                     self.dataCheckboxTraces[rid] = row
#                 self.fileTableWidget.cellWidget(row, self.dataChk_colInd).layout().itemAt(0).widget().setChecked(True)
#                 self.plotfiledata()
#             elif state == Qt.Unchecked:
#                 if rid in self.dataCheckboxTraces:
#                     del self.dataCheckboxTraces[rid]
#                 self.plotfiledata()
#
#                 # Debug prints
#         print(f"Fit Traces: {self.fitCheckboxTraces}")
#         print(f"Data Traces: {self.dataCheckboxTraces}")
#
#         # 2. TRIGGER THE GUI UPDATE (New)
#         # If the user touched the 'Fit' checkbox, update the parameter table immediately.
#         if col == self.fitChk_colInd:
#             self.fittingTableParam()
#
#     def clearPlots(self):
#         self.analysisPlotWidget.clear()
#         self.fileTableWidget.clearSelection()
#         datakeylist=list(self.dataCheckboxTraces)
#         fitkeylist=list(self.fitCheckboxTraces)
#         for rid in datakeylist:
#             self.clearDataChkBox(rid)
#         for rid in fitkeylist:
#             self.clearFitChkBox(rid)
#         self.uncolorRIDlabels()
#
#     # 26/01/06 gt
#     def clearDataChkBox(self, rid):
#         row = self.dataCheckboxTraces[rid]
#
#         # Get wrapper -> find child -> set Checked
#         widget = self.fileTableWidget.cellWidget(row, self.dataChk_colInd)
#         if widget:
#             chk_box = widget.findChild(QtWidgets.QCheckBox)
#             if chk_box:
#                 chk_box.setChecked(False)
#
#         # Explicitly update internal state just in case
#         self.selectRangesCheckbox(rid, row, self.dataChk_colInd, False)
#
#     # 26/01/06 gt
#     def clearFitChkBox(self, rid):
#         row = self.fitCheckboxTraces[rid]
#
#         widget = self.fileTableWidget.cellWidget(row, self.fitChk_colInd)
#         if widget:
#             chk_box = widget.findChild(QtWidgets.QCheckBox)
#             if chk_box:
#                 chk_box.setChecked(False)
#
#         self.selectRangesCheckbox(rid, row, self.fitChk_colInd, False)
#
#     def clearFitPlot(self):
#         last_fit_rid=list(self.fitCheckboxTraces.keys())[-1]
#         self.analysisPlotWidget.removeItem(self.fitTraces[last_fit_rid])
#         # uncheck and remove last selected rid's checkbox
#         self.clearFitChkBox(last_fit_rid)
#
#     # 26/01/06 gt
#     def autoPlotLastRID(self):
#         state = self.autoplotCheckBox.isChecked()
#         if state:
#             row_last_rid = self.getRowMaxRID()
#
#             # Get the wrapper widget
#             widget = self.fileTableWidget.cellWidget(row_last_rid, self.dataChk_colInd)
#             if widget:
#                 # Find the checkbox inside the wrapper
#                 chk_box = widget.findChild(QtWidgets.QCheckBox)
#                 if chk_box and not chk_box.isChecked():
#                     chk_box.setChecked(True)
#
#             self.plotSelectedData()
#
#     def getRowMaxRID(self):
#
#         rid_list=[int(self.fileTableWidget.item(row,self.rid_colInd).text())
#                   for row in range(self.fileTableWidget.rowCount())]
#         #print(max(rid_list))
#         return rid_list.index(max(rid_list))
#
#     # 26/01/06 gt
#     def autofunctions(self):
#         # We can add a date check here to ensure we are looking in the right folder
#         # if the experiment runs past midnight
#         self.check_date_update()
#         self.updateSearchList()
#
#     # 26/01/06 gt
#     def check_date_update(self):
#         # Simple check to see if a new date folder exists
#         try:
#             today = datetime.datetime.now().strftime("%Y-%m-%d")
#             today_path = os.path.join(self.results_path, today)
#             # If the folder for today exists and is different from current, update it
#             if os.path.exists(today_path) and os.path.normpath(self.updated_path) != os.path.normpath(today_path):
#                 print(f"Date change detected. Updating path to: {today_path}")
#                 self.updated_path = today_path
#         except Exception:
#             pass
#
#     def uncolorRIDlabels(self):
#         '''
#         updates all the check boxes to have white background color
#         :return:
#         '''
#         for row in range(self.fileTableWidget.rowCount()):# unselected_data_rows:
#             rid_cell = self.fileTableWidget.item(row, self.rid_colInd)
#             rid_cell.setBackground(QColor("white"))
#
#     # 26/01/06 gt
#     def updateSearchList(self):
#         """
#         Checks for new RIDs. Silent retries until found.
#         Counts attempts and prints only on success.
#         """
#         # Initialize counter if it doesn't exist (drop-in replacement)
#         if not hasattr(self, 'search_attempt_counter'):
#             self.search_attempt_counter = 0
#
#         # We can add a date check here to ensure we are looking in the right folder
#         self.check_date_update()
#
#         # 1. Read what ARTIQ thinks is the last RID
#         target_last_rid = self.extractingLastrid(self.lastridfile)
#
#         # Safety checks
#         if target_last_rid is None:
#             return  # File locked or empty
#
#         # If we are up to date, reset counter and do nothing
#         if target_last_rid <= self.last_rid:
#             self.search_attempt_counter = 0
#             return
#
#             # 2. Try to fetch the next RID in the sequence
#         next_rid = self.last_rid + 1
#
#         # Increment attempt counter
#         self.search_attempt_counter += 1
#
#         # 3. Attempt to load the specific file
#         # This will return False if file isn't on disk OR if it's the wrong type
#         success = self.searchSingleFile(next_rid, self.updated_path)
#
#         if success:
#             # Case A: Success!
#             print(f"Successfully added RID {next_rid} after {self.search_attempt_counter} attempts.")
#             self.last_rid = next_rid
#             self.search_attempt_counter = 0  # Reset
#             self.autoPlotLastRID()
#         else:
#             # Case B: Failed.
#             # We need to distinguish between "Not on disk yet" (Retry) and "Wrong Type" (Skip).
#             try:
#                 dict_test = find_results("", rid=int(next_rid), root_path=self.updated_path)
#
#                 if not dict_test:
#                     # File not physically found yet.
#                     # DO NOT print. Just return and let the timer retry.
#                     pass
#                 else:
#                     # File found, but searchSingleFile returned False.
#                     # This means it is the wrong scan type or has no parameters.
#                     # We MUST skip it, or we will get stuck in an infinite loop.
#                     print(f"RID {next_rid} exists but is skipped (Wrong type/No params).")
#                     self.last_rid = next_rid
#                     self.search_attempt_counter = 0
#             except Exception as e:
#                 # If unexpected error, silence it for now to avoid spam
#                 pass
#
#     # 26/01/06 gt
#     def extractingLastrid(self, filename):
#         """
#         Safely reads the last RID from the file.
#         Returns None if the file is being written to or is empty.
#         """
#         try:
#             if not os.path.exists(filename):
#                 return None
#
#             with open(filename, 'r') as file:
#                 content = file.readline().strip()
#                 if not content:
#                     return None
#                 return int(content)
#         except (ValueError, IndexError, IOError):
#             # IOError handles permission issues if ARTIQ has the file locked
#             return None
#
#     def searchfiles(self,last_rid, num_rids,rootpath):
#         '''
#
#         :param last_rid:
#         :param num_rids: num of new rids - 1. eg. if only one last_rid value exists, then num_rids=0 is required
#         :param rootpath:
#         :return:
#         '''
#         # first get last rid
#         list_rids = list(np.arange(last_rid - num_rids, last_rid + 1, 1))
#         # extract all rid files.
#
#         for rid in list_rids:
#             self.searchSingleFile(rid,rootpath)
#
#     def toggleAutoFitLastRow(self, state):
#         """
#         Triggered when Auto Fit Checkbox is clicked.
#         If turned ON, it grabs the last row, checks the boxes, and runs the fit.
#         """
#         if state == Qt.Checked:
#             row_count = self.fileTableWidget.rowCount()
#             if row_count == 0:
#                 return
#
#             last_row = row_count - 1
#
#             # 1. Get the Data Checkbox (using the wrapper fix)
#             data_widget = self.fileTableWidget.cellWidget(last_row, self.dataChk_colInd)
#             data_chk = data_widget.findChild(QtWidgets.QCheckBox) if data_widget else None
#
#             # 2. Get the Fit Checkbox
#             fit_widget = self.fileTableWidget.cellWidget(last_row, self.fitChk_colInd)
#             fit_chk = fit_widget.findChild(QtWidgets.QCheckBox) if fit_widget else None
#
#             # 3. If Fit is currently unchecked, activate everything
#             if fit_chk and not fit_chk.isChecked():
#                 print(f"Auto-triggering fit for row {last_row}...")
#
#                 # Ensure data is checked first
#                 if data_chk and not data_chk.isChecked():
#                     data_chk.setChecked(True)
#
#                 # Check the fit box (this triggers selectRangesCheckbox -> updates dictionaries)
#                 fit_chk.setChecked(True)
#
#                 # Visual selection
#                 self.fileTableWidget.selectRow(last_row)
#
#                 # Run the fit (Timer ensures signals finish propagating first)
#                 QTimer.singleShot(100, self.fitData)
#
#     # 26/01/23 gt: added this to only keep in memory last num_rid files
#     def enforceRowLimit(self):
#         """
#         Ensures table does not exceed self.num_rids.
#         Removes oldest data (Row 0) and shifts index trackers for remaining rows.
#         """
#         while self.fileTableWidget.rowCount() > self.num_rids:
#
#             # 1. Identify the oldest RID (always at row 0)
#             oldest_rid_item = self.fileTableWidget.item(0, self.rid_colInd)
#             if oldest_rid_item is None:
#                 return  # Safety check
#
#             oldest_rid = int(oldest_rid_item.text())
#
#             # 2. Remove Plots from Graph
#             if oldest_rid in self.fitTraces:
#                 self.analysisPlotWidget.removeItem(self.fitTraces[oldest_rid])
#                 del self.fitTraces[oldest_rid]
#
#             # (Optional) If you track data plots separately, remove them here too
#             # e.g. if oldest_rid in self.dataTraces: ...
#
#             # 3. Clear Data Memory
#             if oldest_rid in self.dataDict:
#                 del self.dataDict[oldest_rid]
#             if oldest_rid in self.selectedDataDict:
#                 del self.selectedDataDict[oldest_rid]
#
#             # 4. Remove from Checkbox Dictionaries (The ones being deleted)
#             if oldest_rid in self.fitCheckboxTraces:
#                 del self.fitCheckboxTraces[oldest_rid]
#             if oldest_rid in self.dataCheckboxTraces:
#                 del self.dataCheckboxTraces[oldest_rid]
#
#             # 5. REMOVE THE ROW
#             # This shifts Row 1 -> Row 0, Row 2 -> Row 1, etc.
#             self.fileTableWidget.removeRow(0)
#
#             # 6. UPDATE INDICES [CRITICAL]
#             # All remaining RIDs have moved up by one row. We must update the maps.
#             for rid in self.fitCheckboxTraces:
#                 self.fitCheckboxTraces[rid] -= 1
#
#             for rid in self.dataCheckboxTraces:
#                 self.dataCheckboxTraces[rid] -= 1
#
#     # 26/01/06 gt
#     def searchSingleFile(self, rid, rootpath):
#         """
#         Fetches a specific RID.
#         Returns True if the file was valid (executeScan + has parameter) and added.
#         Returns False otherwise.
#         """
#         rid = int(rid)
#         try:
#             # Find the file path for this RID
#             dict_test = find_results("", rid=int(rid), root_path=rootpath)
#         except Exception:
#             return False
#
#         if not dict_test:
#             # RID file not created yet (might take a second after updating last_rid)
#             return False
#
#         # Check 1: Is it the right scan type?
#         scan_type = dict_test[int(rid)][-1]
#         if scan_type not in self.filterScanNames:  # self.filterScanNames is ['executeScan', BarebonesArtiqScanV1]
#             return False
#
#         try:
#             # Load the HDF5 file
#             dict_hdf5 = load_hdf5_file(dict_test[int(rid)][0])
#             dict_datasets = dict_hdf5.get("datasets", {})
#             dict_archive = dict_hdf5.get("archive", {})
#
#             # ---------------------------------------------------------
#             # Check 2: Handle Metadata (NDScan vs Bare)
#             # ---------------------------------------------------------
#             # 1. Attempt to find standard NDScan axes
#             axes_json = dict_datasets.get('ndscan.rid_' + str(rid) + '.axes', '[]')
#             axes_list = json.loads(axes_json)
#
#             xlabel_axis0 = ""
#             is_valid_file = False
#
#             if len(axes_list) > 0: # ndscan
#                 scanparam_axis0 = axes_list[0]
#                 unit = scanparam_axis0['param']['spec'].get('unit', '')
#                 unit_str = f" ({unit})" if unit else ""
#                 xlabel_axis0 = scanparam_axis0['param']['description'] + unit_str
#                 is_valid_file = True
#
#             elif "ScanDataPlot.x_label" in dict_datasets:
#                 # --- Case B: Explicit Label (Added by you) ---
#                 val = dict_datasets["ScanDataPlot.x_label"]
#                 # 1. Handle NumPy arrays (0-d or 1-d)
#                 if isinstance(val, np.ndarray):
#                     if val.size > 0:
#                         val = val.item()  # Extract scalar value
#                     else:
#                         val = ""
#
#                 # 2. Handle Bytes (decode to string)
#                 if isinstance(val, bytes):
#                     xlabel_axis0 = val.decode('utf-8')
#                 else:
#                     xlabel_axis0 = str(val)
#
#                 is_valid_file = True
#
#             if not is_valid_file:
#                 return False
#
#             # ---------------------------------------------------------
#             # --- Add to Table ---
#             self.dataDict[int(rid)] = dict_datasets
#
#             # [CRITICAL ADDITION] Save the label so the helper can find it later
#             if not hasattr(self, 'rid_labels'):
#                 self.rid_labels = {}
#             self.rid_labels[int(rid)] = xlabel_axis0
#
#             row_count = self.fileTableWidget.rowCount()
#             self.fileTableWidget.insertRow(row_count)
#
#             # Create checkboxes
#             fitcheckbox = QCheckBox(self)
#             datacheckbox = QCheckBox(self)
#
#             # Center widgets for checkboxes
#             data_widget = QtWidgets.QWidget()
#             data_layout = QtWidgets.QHBoxLayout(data_widget)
#             data_layout.addWidget(datacheckbox)
#             data_layout.setAlignment(Qt.AlignCenter)
#             data_layout.setContentsMargins(0, 0, 0, 0)
#
#             fit_widget = QtWidgets.QWidget()
#             fit_layout = QtWidgets.QHBoxLayout(fit_widget)
#             fit_layout.addWidget(fitcheckbox)
#             fit_layout.setAlignment(Qt.AlignCenter)
#             fit_layout.setContentsMargins(0, 0, 0, 0)
#
#             # Populate row
#             self.fileTableWidget.setItem(row_count, self.rid_colInd, QTableWidgetItem(str(rid)))
#             self.fileTableWidget.setCellWidget(row_count, self.dataChk_colInd, data_widget)  # Use widget wrapper
#             self.fileTableWidget.setCellWidget(row_count, self.fitChk_colInd, fit_widget)  # Use widget wrapper
#             self.fileTableWidget.setItem(row_count, self.ScanParameter_colInd, QTableWidgetItem(xlabel_axis0))
#             self.fileTableWidget.setItem(row_count, self.Comments_colInd, QTableWidgetItem(""))
#
#             # Connect signals
#             # CRITICAL: These must be connected BEFORE we programmatically check the boxes below
#             datacheckbox.stateChanged.connect(
#                 lambda state, r=row_count, col=self.dataChk_colInd, num=rid: self.selectRangesCheckbox(num, r, col,
#                                                                                                        state))
#             fitcheckbox.stateChanged.connect(
#                 lambda state, r=row_count, col=self.fitChk_colInd, num=rid: self.selectRangesCheckbox(num, r, col,
#                                                                                                       state))
#
#             # Make read-only
#             for col in [self.rid_colInd, self.ScanParameter_colInd]:
#                 item = self.fileTableWidget.item(row_count, col)
#                 if item: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
#
#             # ---------------------------------------------------------
#             # AUTO FIT LOGIC
#             # ---------------------------------------------------------
#             if self.autoFitCheckbox.isChecked():
#                 print(f"Auto-fitting RID {rid}...")
#
#                 # 1. Programmatically check the boxes.
#                 datacheckbox.setChecked(True)
#                 fitcheckbox.setChecked(True)
#
#                 # 2. Visually select the row (optional, but good for UX)
#                 self.fileTableWidget.selectRow(row_count)
#
#                 # 3. Trigger the fit function
#                 QTimer.singleShot(100, self.fitData)
#
#             # 26/01/23 gt: to maintain only last 10 rids
#             self.enforceRowLimit()
#
#             return True
#
#         except Exception as e:
#             print(f"Error processing RID {rid}: {e}")
#             return False
#
#     # 26/01/30: handle units properly
#     def get_data_from_rid(self, rid, dict_datasets=None):
#
#         if dict_datasets is None:
#             if rid in self.dataDict:
#                 dict_datasets = self.dataDict[rid]
#             else:
#                 return None, None, None, None
#
#         x_vals, y_vals, err_vals, xlabel = None, None, None, None
#
#         # --- TYPE A: NDSCAN ---
#         ndscan_key = 'ndscan.rid_' + str(rid) + '.axes'
#         if ndscan_key in dict_datasets:
#             try:
#                 # 1. Extract raw metadata first
#                 scanparam_axis0 = json.loads(dict_datasets[ndscan_key])[0]
#                 raw_unit = scanparam_axis0['param']['spec'].get('unit', '')
#                 description = scanparam_axis0['param']['description']
#
#                 # Data keys
#                 key_name_x = "ndscan.rid_" + str(rid) + ".points.axis_0"
#                 key_name_y = "ndscan.rid_" + str(rid) + ".points.channel_counts"
#                 key_name_err = "ndscan.rid_" + str(rid) + ".points.channel_res_err"
#
#                 # 2. Convert Data AND Label simultaneously
#                 raw_x = np.array(dict_datasets[key_name_x])
#
#                 # Check based on UNIT, not just label text (more robust)
#                 if raw_unit == 's' or 'time' in description.lower():
#                     x_vals = raw_x * 1e3  # s -> ms
#                     xlabel = f"{description} (ms)"  # Force label to ms
#
#                 elif raw_unit == 'Hz' or 'freq' in description.lower():
#                     x_vals = raw_x * 1e-6  # Hz -> MHz
#                     xlabel = f"{description} (MHz)"  # Force label to MHz
#
#                 else:
#                     x_vals = raw_x
#                     # Keep original unit if it exists
#                     unit_str = f" ({raw_unit})" if raw_unit else ""
#                     xlabel = description + unit_str
#
#                 y_vals = np.array(dict_datasets[key_name_y])
#                 err_vals = np.array(dict_datasets[key_name_err])
#
#             except Exception as e:
#                 print(f"Error parsing NDScan RID {rid}: {e}")
#                 return None, None, None, None
#
#         # --- TYPE B: BARE ARTIQ / AWG ---
#         elif "ScanDataPlot.x_vals" in dict_datasets:
#             x_vals = np.array(dict_datasets["ScanDataPlot.x_vals"])
#             y_vals = np.array(dict_datasets["ScanDataPlot.y_vals"])
#
#             # Errors
#             if "ScanDataPlot.yerr_vals" in dict_datasets:
#                 err_vals = np.array(dict_datasets["ScanDataPlot.yerr_vals"])
#             else:
#                 err_vals = np.zeros(len(y_vals))
#
#             # Label: Retrieve the one we saved in searchSingleFile
#             if hasattr(self, 'rid_labels') and rid in self.rid_labels:
#                 xlabel = self.rid_labels[rid]
#             else:
#                 xlabel = "Bare Scan (x_vals)"
#
#             # get right units
#             if xlabel:
#                 # If the values are already MS but labeled S, just swap the string
#                 if " (s)" in xlabel:
#                     xlabel = xlabel.replace(" (s)", " (ms)")
#                 elif xlabel.strip().endswith("[s]"):
#                     xlabel = xlabel.replace("[s]", "[ms]")
#
#         # in case the experiment was aborted, x, y might differ by 1 in length and plotting/fitting crash.
#         # Here we shorten the longest array
#         if x_vals is not None and y_vals is not None:
#             # 1. Find the minimum common length
#             min_len = min(len(x_vals), len(y_vals))
#
#             # If errors exist, they must also limit the length
#             if err_vals is not None and len(err_vals) > 0:
#                 min_len = min(min_len, len(err_vals))
#
#             # 2. Slice everything to match that length
#             x_vals = x_vals[:min_len]
#             y_vals = y_vals[:min_len]
#
#             if err_vals is not None and len(err_vals) > 0:
#                 err_vals = err_vals[:min_len]
#
#         return x_vals, y_vals, err_vals, xlabel
#
#     # 26/01/19 gt: for barebones data
#     def plotSelectedData(self):
#         self.analysisPlotWidget.NselectedDatasets = len(self.dataCheckboxTraces)
#         self.uncolorRIDlabels()
#
#         for k, RID in enumerate(self.dataCheckboxTraces.keys()):
#             rid = int(RID)
#
#             # USE THE NEW HELPER
#             x_vals, y_vals, err_vals, xlabel = self.get_data_from_rid(rid)
#
#             if x_vals is None:
#                 print(f"Skipping RID {rid}: No valid data found.")
#                 continue
#
#             ylabel = 'counts'
#
#             self.analysisPlotWidget.plotdata(x_vals, y_vals, err_vals, xlabel, ylabel, k, rid)
#
#             # Color the table cell
#             rid_cell = self.fileTableWidget.item(self.dataCheckboxTraces[rid], self.rid_colInd)
#             if rid_cell: rid_cell.setBackground(self.analysisPlotWidget.colors[k])
#
#         self.fittingTableParam()
#
#     def plotfiledata(self):
#         #intended to plot the data from rid file
#         self.analysisPlotWidget.clear()
#         self.plotSelectedData()
#         #self.uncolorRIDlabels()
#
#     def fitComboBoxList(self):
#         self.fitselectionRowComboBox.addItems(self.fitlist)
#         self.fitselectionRowComboBox.currentIndexChanged.connect(self.fittingTableParam)
#
#         # 26/01/06 gt: set default fit type
#         # This will automatically trigger 'fittingTableParam' because of the connection above
#         index = self.fitselectionRowComboBox.findText("Sinusoid")
#         if index != -1:
#             self.fitselectionRowComboBox.setCurrentIndex(index)
#
#     def fittingTableParam(self):
#         fittype = self.fitselectionRowComboBox.currentText()
#         if not fittype or fittype not in self.fitlist:
#             return
#
#         fit_obj = self.fitlist[fittype]
#         self.fitdescriptionLabel.setText(fit_obj.description)
#
#         # --- Run Auto-Guess Logic Here ---
#         # 1. Grab data AND xlabel (for unit detection)
#         try:
#             rid, x_vals, y_vals, xlabel = self._get_active_fit_data()
#         except ValueError:
#             # Handle case where _get_active_fit_data might return fewer items
#             # or if no data is selected
#             rid, x_vals, y_vals, xlabel = None, None, None, ""
#
#         if rid is not None and x_vals is not None:
#             # 2. Run the intelligent guess on the FIT OBJECT
#             # Pass xlabel so it knows if it is ms or s
#             print(f"Auto-guessing parameters for {fittype} on RID {rid}...")
#             if hasattr(fit_obj, 'guess_parameters'):
#                 fit_obj.guess_parameters(x_vals, y_vals, x_label=xlabel)
#
#         # --------------------------------------
#
#         num_rows = fit_obj.num_params
#         # Safely get columns (usually 6 based on your structure)
#         cols = getattr(fit_obj, 'cols', 6)
#
#         self.fitTableWidget.setRowCount(num_rows)
#         self.fitTableWidget.setColumnCount(cols)
#         self.fitTableWidget.setHorizontalHeaderLabels(['Enable', 'Parameter', 'Initial', 'Fit', 'Min', 'Max'])
#
#         # Populate the table with the (now updated) values
#         for row in range(num_rows):
#             # Checkbox for Enable
#             checkbox = QCheckBox()
#             checkbox.setChecked(fit_obj.params2Dlist[row][0])
#             chk_widget = QtWidgets.QWidget()
#             chk_layout = QtWidgets.QHBoxLayout(chk_widget)
#             chk_layout.addWidget(checkbox)
#             chk_layout.setAlignment(Qt.AlignCenter)
#             chk_layout.setContentsMargins(0, 0, 0, 0)
#             self.fitTableWidget.setCellWidget(row, 0, chk_widget)
#
#             # Text Items (Name, Initial, Fit(Empty), Min, Max)
#             # Note: Your list is [Fixed, Name, Guess, Step, Min, Max]
#             # But Table is:     [Check, Name, Guess, Result, Min, Max]
#
#             # Name
#             self.fitTableWidget.setItem(row, 1, QTableWidgetItem(str(fit_obj.params2Dlist[row][1])))
#
#             # Initial Guess
#             val = fit_obj.params2Dlist[row][2]
#             self.fitTableWidget.setItem(row, 2, QTableWidgetItem(str(val)))
#
#             # Fit Result (Leave empty initially)
#             self.fitTableWidget.setItem(row, 3, QTableWidgetItem(""))
#
#             # Min (Index 4 in your list)
#             min_val = fit_obj.params2Dlist[row][4]
#             self.fitTableWidget.setItem(row, 4, QTableWidgetItem(str(min_val)))
#
#             # Max (Index 5 in your list)
#             max_val = fit_obj.params2Dlist[row][5]
#             self.fitTableWidget.setItem(row, 5, QTableWidgetItem(str(max_val)))
#
#         self.fitTableWidget.horizontalHeader().setStretchLastSection(True)
#         self.fitTableWidget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
#
#     # 26/01/19 gt
#     def _get_active_fit_data(self):
#         """
#         Returns data for the currently selected file in the fit table.
#         Refactored to use get_data_from_rid for unified Bare/NDScan support.
#         """
#         if not self.fitCheckboxTraces:
#             print("No data selected for fitting.")
#             return None, None, None, None
#
#         # Get the last selected RID
#         rid = list(self.fitCheckboxTraces.keys())[-1]
#
#         # --- USE THE UNIFIED HELPER ---
#         # This automatically handles NDScan vs. Bare vs. AWG logic
#         # and retrieves the correct label we saved in searchSingleFile.
#         x_vals, y_vals, _, xlabel = self.get_data_from_rid(rid)
#
#         if x_vals is None:
#             print(f"Error: Could not extract fit data for RID {rid}")
#             return None, None, None, None
#
#         return rid, x_vals, y_vals, xlabel
#
#     # 26/01/06 gt
#     def _update_fit_params_from_table(self, fittype):
#         """
#         Scrapes the current values from the GUI table and updates the FitObject.
#         This ensures your manual edits are respected.
#         """
#         fit_obj = self.fitlist[fittype]
#         num_rows = fit_obj.num_params
#         cols = fit_obj.cols
#
#         for row in range(num_rows):
#             # 1. Get Checkbox state
#             chk_widget = self.fitTableWidget.cellWidget(row, 0)
#             checkbox = chk_widget.findChild(QCheckBox) if chk_widget else None
#             if checkbox:
#                 fit_obj.params2Dlist[row][0] = checkbox.isChecked()
#
#             # 2. Get Numerical Values (Start from col 2: Initial, Fit, Min, Max)
#             # We specifically care about col 2 (Initial) which the user might have edited
#             for col in range(2, cols):
#                 item = self.fitTableWidget.item(row, col)
#                 if item and item.text():
#                     try:
#                         fit_obj.params2Dlist[row][col] = float(item.text())
#                     except ValueError:
#                         print(f"Warning: Invalid value in fit table row {row} col {col}")
#
#     # 26/01/06 gt
#     def plotFitFunction(self):
#         """
#         Plots the Initial Guess currently typed in the table.
#         """
#         rid, x_vals, y_vals, xlabel = self._get_active_fit_data()
#         if rid is None: return
#
#         fittype = self.fitselectionRowComboBox.currentText()
#
#         # 1. Force update from Table UI -> Internal Object (Index 2)
#         self._update_fit_params_from_table(fittype)
#
#         # 2. Safety check: ensure we have a valid domain
#         if len(x_vals) == 0: return
#         x_smooth = np.linspace(np.min(x_vals), np.max(x_vals), 500)
#
#         # 3. Calculate Y (Reads Index 2 by default)
#         try:
#             yfitfunction = self.fitlist[fittype].functionVal(x_smooth)
#         except Exception as e:
#             print(f"Error calculating Initial Function: {e}")
#             return
#
#         # 4. Plotting
#         if rid in self.fitTraces:
#             self.analysisPlotWidget.removeItem(self.fitTraces[rid])
#             del self.fitTraces[rid]
#
#         k = list(self.dataCheckboxTraces.keys()).index(rid) if rid in self.dataCheckboxTraces else 0
#
#         # Debug: Print first few Y values to ensure it's not a flat 0 line
#         # print(f"Plotting Initial: X range {x_smooth[0]:.2f}-{x_smooth[-1]:.2f}, Y sample {yfitfunction[:3]}")
#
#         fitplotitem = self.analysisPlotWidget.plotfit(x_smooth, yfitfunction, xlabel, 'counts', k, rid)
#         self.fitTraces[rid] = fitplotitem
#
#     # 26/01/22 gt: to fit all clicked
#     def fitData(self):
#         """
#         Runs the fit for ALL RIDs currently checked in the 'Fit' column.
#         Plots the curves and updates the table colors.
#         """
#         fittype = self.fitselectionRowComboBox.currentText()
#
#         # 0. Ensure we have the selection dictionary
#         if not hasattr(self, 'fitCheckboxTraces'):
#             self.fitCheckboxTraces = {}
#
#         # -------------------------------------------------------------
#         # ITERATE OVER ALL CHECKED RIDS
#         # -------------------------------------------------------------
#         for rid in list(self.fitCheckboxTraces.keys()):
#             rid = int(rid)
#
#             # 1. Get data for this specific RID
#             # (We use the helper we made earlier instead of _get_active_fit_data)
#             x_vals, y_vals, _, xlabel = self.get_data_from_rid(rid)
#
#             if x_vals is None or len(x_vals) == 0:
#                 print(f"Skipping fit for RID {rid}: No data found.")
#                 continue
#
#             # 2. Load Initial Guesses from Table into the Object
#             # Note: This uses the ONE table of parameters for ALL fits.
#             # If you want individual guesses per file, this logic gets more complex.
#             # For now, we assume the same initial guess applies to all selected files.
#             self._update_fit_params_from_table(fittype)
#
#             try:
#                 # 3. Perform the Fit
#                 # activateFit returns (success_flag, params_list)
#                 _, params2DlistFit = self.fitlist[fittype].activateFit(x_vals, y_vals)
#
#                 # Update the fit object's params so functionVal uses them
#                 self.fitlist[fittype].params2Dlist = params2DlistFit
#
#                 # 4. Update the "Fit" Column in the Table (Index 3)
#                 # WARNING: If you fit multiple files, this table will show values
#                 # for the LAST file processed. This is unavoidable without a UI redesign.
#                 for ind, param in enumerate(params2DlistFit):
#                     fit_val = param[3]
#                     fmt = f"{fit_val:.4e}" if abs(fit_val) < 0.001 and fit_val != 0 else f"{fit_val:.4f}"
#                     self.fitTableWidget.setItem(ind, 3, QTableWidgetItem(fmt))
#
#                 # 5. Generate Smooth Fit Curve
#                 # (Swap trick: Use Fit results temporarily to generate the curve)
#                 initial_guesses_backup = [row[2] for row in self.fitlist[fittype].params2Dlist]
#                 for row in self.fitlist[fittype].params2Dlist:
#                     row[2] = row[3]  # Swap Initial with Fit Result
#
#                 x_smooth = np.linspace(np.min(x_vals), np.max(x_vals), 500)
#                 y_smooth = self.fitlist[fittype].functionVal(x_smooth)
#
#                 # Restore Initial Guesses so the next loop iteration starts clean
#                 for i, row in enumerate(self.fitlist[fittype].params2Dlist):
#                     row[2] = initial_guesses_backup[i]
#
#                 # 6. Plot the Result
#                 # Remove existing fit for this RID if it exists
#                 if not hasattr(self, 'fitTraces'): self.fitTraces = {}
#
#                 if rid in self.fitTraces:
#                     self.analysisPlotWidget.removeItem(self.fitTraces[rid])
#                     del self.fitTraces[rid]
#
#                 # Calculate Color Index 'k'
#                 # Use the DATA checkbox list to ensure colors match the data points
#                 keys_as_ints = [int(k) for k in self.dataCheckboxTraces.keys()]
#                 if rid in keys_as_ints:
#                     k = keys_as_ints.index(rid)
#                 else:
#                     k = 0  # Fallback
#
#                 # Plot
#                 fitplotitem = self.analysisPlotWidget.plotfit(x_smooth, y_smooth, xlabel, 'counts', k, rid)
#                 self.fitTraces[rid] = fitplotitem
#
#             except Exception as e:
#                 print(f"Fitting failed for RID {rid}: {e}")
#
# class AnalysisPlotWidget(PlotWidget):
#
#     def __init__(self):
#         super(AnalysisPlotWidget,self).__init__()
#         self.showGrid(x=True, y=True)
#         self.setBackground('w')
#
#         self.colormap = pg.colormap.get("CET-R2")
#         self.NselectedDatasets=0
#         self.colors = self.colormap.getLookupTable(nPts=self.NselectedDatasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects
#
#     def plotdata(self, x,y,y_error, xlabel, ylabel,k,rid):
#
#         #colors=['b','r','g','y','m']
#         self.colors = self.colormap.getLookupTable(nPts=self.NselectedDatasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects
#         ppen = pg.mkPen(self.colors[k], width=2)
#         self.plot(x,y, pen=ppen, symbol='o', symbolSize=10, symbolBrush=self.colors[k], name=str(rid))
#         #styles = {'color':'r', 'font-size':'20px'}
#         # Create error bars
#         error_bars = pg.ErrorBarItem(x=x, y=y, top=y_error, bottom=y_error, pen=ppen)
#         # Add error bars to the plot
#         self.addItem(error_bars)
#         styles = {'font-size': '20px'}
#         self.setLabel('left',text=ylabel,color='k', size='16pt')
#         self.setLabel('bottom',text=xlabel,color='k', size='16pt')
#
#
#     def plotfit(self, x,y,xlabel, ylabel,k,rid):
#
#         #colors=['b','r','g','y','m']
#         #self.colors = self.colormap.getLookupTable(nPts=self.NselectedDatasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects
#         ppen = pg.mkPen(self.colors[k], width=2)
#         plotitem=self.plot(x,y, pen=ppen, name=str(rid)+": Fit")
#         #styles = {'color':'r', 'font-size':'20px'}
#         # Create error bars
#         #error_bars = pg.ErrorBarItem(x=x, y=y, top=y_error, bottom=y_error, pen=ppen)
#         # Add error bars to the plot
#         #self.addItem(error_bars)
#         styles = {'font-size': '20px'}
#         self.setLabel('left',text=ylabel,color='k', size='16pt')
#         self.setLabel('bottom',text=xlabel,color='k', size='16pt')
#         return plotitem
#
#
#
#
# def main():
#     app = QtWidgets.QApplication(sys.argv)
#     print("Hello")
#     main = MainWindow()
#     print("Hello")
#     #main.show()
#     sys.exit(app.exec_())
#
#
# if __name__ == '__main__':
#     main()


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

        # File Table
        self.fileTableWidget = QtWidgets.QTableWidget()
        self.fileTableWidget.setColumnCount(5)
        self.fileTableWidget.setHorizontalHeaderLabels(['rid', 'Data', 'Fit', 'Scan parameter', 'Comments'])
        self.rid_colInd = 0
        self.dataChk_colInd = 1
        self.fitChk_colInd = 2
        self.ScanParameter_colInd = 3
        self.Comments_colInd = 4
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
            if self.search_attempt_counter >= 25:
                print(f"Skipping RID {next_rid} (file not ready/found after 25 background attempts).")
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

            self.fileTableWidget.setItem(row_count, self.rid_colInd, QTableWidgetItem(str(rid)))
            self.fileTableWidget.setCellWidget(row_count, self.dataChk_colInd, data_widget)
            self.fileTableWidget.setCellWidget(row_count, self.fitChk_colInd, fit_widget)
            self.fileTableWidget.setItem(row_count, self.ScanParameter_colInd, QTableWidgetItem(xlabel_axis0))
            self.fileTableWidget.setItem(row_count, self.Comments_colInd, QTableWidgetItem(""))

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

    def get_data_from_rid(self, rid):
        """Extracts plot-ready data dictionary with robust unit & description parsing."""
        rid = int(rid)
        if rid not in self.dataDict:
            return None

        dict_datasets = self.dataDict[rid]

        def process_axis_units(vals, desc, unit="", is_ndscan=True):
            if vals is None or len(vals) == 0:
                return vals, desc

            vals = np.array(vals)

            # Convert HDF5 bytes/0D arrays to standard string
            if isinstance(desc, np.ndarray) and desc.ndim == 0:
                desc = desc.item()
            if isinstance(desc, (bytes, bytearray)):
                desc = desc.decode('utf-8', errors='ignore')
            elif desc is None:
                desc = ""
            else:
                desc = str(desc)

            if isinstance(unit, np.ndarray) and unit.ndim == 0:
                unit = unit.item()
            if isinstance(unit, (bytes, bytearray)):
                unit = unit.decode('utf-8', errors='ignore')
            elif unit is None:
                unit = ""
            else:
                unit = str(unit)

            if is_ndscan:
                desc_lower = f"{desc} {unit}".lower()

                # NDScan Time Scans (s -> ms)
                if unit == 's' or 'time' in desc_lower:
                    vals = vals * 1e3
                    if " (s)" in desc:
                        label = desc.replace(" (s)", " (ms)")
                    elif desc.strip().endswith("[s]"):
                        label = desc.replace("[s]", "[ms]")
                    else:
                        label = f"{desc} (ms)"

                # NDScan Frequency Scans (Hz -> MHz)
                elif unit == 'Hz' or 'freq' in desc_lower:
                    vals = vals * 1e-6
                    if " (Hz)" in desc or " (hz)" in desc:
                        label = desc.replace(" (Hz)", " (MHz)").replace(" (hz)", " (MHz)")
                    elif desc.strip().endswith("[Hz]") or desc.strip().endswith("[hz]"):
                        label = desc.replace("[Hz]", "[MHz]").replace("[hz]", "[MHz]")
                    else:
                        label = f"{desc} (MHz)"
                else:
                    unit_str = f" ({unit})" if unit and not desc.endswith(f"({unit})") else ""
                    label = f"{desc}{unit_str}"

            else:
                # Bare ARTIQ: No mathematical scaling, just string label formatting
                label = desc
                if " (s)" in label:
                    label = label.replace(" (s)", " (ms)")
                elif label.strip().endswith("[s]"):
                    label = label.replace("[s]", "[ms]")

            return vals, label

        def find_desc_and_unit(obj):
            d, u = "", ""
            if isinstance(obj, dict):
                if 'description' in obj and isinstance(obj['description'], str):
                    d = obj['description']
                if 'unit' in obj and isinstance(obj['unit'], str):
                    u = obj['unit']
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

        # TYPE A: NDSCAN
        ndscan_key = f'ndscan.rid_{rid}.axes'
        if ndscan_key in dict_datasets:
            try:
                axes_raw = dict_datasets[ndscan_key]

                if isinstance(axes_raw, np.ndarray) and axes_raw.ndim == 0:
                    axes_raw = axes_raw.item()
                if isinstance(axes_raw, (bytes, bytearray)):
                    axes_raw = axes_raw.decode('utf-8')

                axes_list = json.loads(axes_raw) if isinstance(axes_raw, str) else axes_raw

                key_name_y = f"ndscan.rid_{rid}.points.channel_counts"
                key_name_err = f"ndscan.rid_{rid}.points.channel_res_err"

                if key_name_y in dict_datasets:
                    raw_y = np.array(dict_datasets[key_name_y])
                    is_2d_scan = isinstance(axes_list, list) and len(axes_list) >= 2

                    if is_2d_scan or raw_y.ndim == 2:
                        axis_0_key = f"ndscan.rid_{rid}.points.axis_0"
                        axis_1_key = f"ndscan.rid_{rid}.points.axis_1"

                        raw_x0 = np.array(dict_datasets[axis_0_key]) if axis_0_key in dict_datasets else np.array([])
                        raw_x1 = np.array(dict_datasets[axis_1_key]) if axis_1_key in dict_datasets else np.array([])

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
                                    if len(xi) > 0 and len(yi) > 0:
                                        z_mat[xi[0], yi[0]] = val

                        x_desc = getattr(self, 'rid_xlabels', {}).get(rid, "")
                        y_desc = getattr(self, 'rid_ylabels', {}).get(rid, "")
                        x_unit, y_unit = "", ""

                        if isinstance(axes_list, list) and len(axes_list) >= 2:
                            if not x_desc:
                                x_desc = axes_list[0].get('param', {}).get('description', 'X Axis')
                            x_unit = axes_list[0].get('param', {}).get('unit', '')

                            if not y_desc:
                                y_desc = axes_list[1].get('param', {}).get('description', 'Y Axis')
                            y_unit = axes_list[1].get('param', {}).get('unit', '')

                        if not x_desc: x_desc = "X Axis"
                        if not y_desc: y_desc = "Y Axis"

                        x_vals, xlabel = process_axis_units(x_vals_uniq, x_desc, x_unit, is_ndscan=True)
                        y_vals, ylabel = process_axis_units(y_vals_uniq, y_desc, y_unit, is_ndscan=True)

                        return {
                            "is_2d": True,
                            "x": x_vals,
                            "y": y_vals,
                            "z": z_mat,
                            "xlabel": xlabel,
                            "ylabel": ylabel,
                            "zlabel": "counts"
                        }

                    else:
                        key_name_x = f"ndscan.rid_{rid}.points.axis_0"
                        description, raw_unit = find_desc_and_unit(axes_list)
                        fallback_label = getattr(self, 'rid_xlabels', {}).get(
                            rid, getattr(self, 'rid_labels', {}).get(rid, "Scan Parameter")
                        )
                        final_desc = description if description else fallback_label

                        raw_x = np.array(dict_datasets[key_name_x]) if key_name_x in dict_datasets else np.arange(
                            len(raw_y))
                        x_vals, xlabel = process_axis_units(raw_x, final_desc, raw_unit, is_ndscan=True)

                        y_vals = raw_y
                        err_vals = np.array(dict_datasets[key_name_err]) if key_name_err in dict_datasets else None

                        min_len = min(len(x_vals), len(y_vals))
                        if err_vals is not None and len(err_vals) > 0:
                            min_len = min(min_len, len(err_vals))
                            err_vals = err_vals[:min_len]

                        return {
                            "is_2d": False,
                            "x": x_vals[:min_len],
                            "y": y_vals[:min_len],
                            "err": err_vals[:min_len] if err_vals is not None else None,
                            "xlabel": xlabel,
                            "ylabel": "counts"
                        }

            except Exception as e:
                print(f"Error parsing NDScan RID {rid}: {e}")

        # TYPE B: BARE ARTIQ 2D
        elif "ScanDataPlot.z_vals" in dict_datasets:
            z_mat = np.array(dict_datasets["ScanDataPlot.z_vals"])
            if z_mat.ndim == 2:
                raw_x = np.array(dict_datasets.get("ScanDataPlot.x_vals", np.arange(z_mat.shape[0])))
                raw_y_axis = np.array(dict_datasets.get("ScanDataPlot.y_vals", np.arange(z_mat.shape[1])))

                x_desc = dict_datasets.get("ScanDataPlot.x_label", "")
                if not x_desc: x_desc = getattr(self, 'rid_xlabels', {}).get(rid, "X Axis")

                y_desc = dict_datasets.get("ScanDataPlot.y_label", "")
                if not y_desc: y_desc = getattr(self, 'rid_ylabels', {}).get(rid, "Y Axis")

                x_vals, xlabel = process_axis_units(raw_x, x_desc, is_ndscan=False)
                y_vals, ylabel = process_axis_units(raw_y_axis, y_desc, is_ndscan=False)

                return {
                    "is_2d": True,
                    "x": x_vals,
                    "y": y_vals,
                    "z": z_mat,
                    "xlabel": xlabel,
                    "ylabel": ylabel,
                    "zlabel": "counts"
                }

        # TYPE C: BARE ARTIQ 1D
        elif "ScanDataPlot.x_vals" in dict_datasets:
            raw_x = np.array(dict_datasets["ScanDataPlot.x_vals"])
            y_vals = np.array(dict_datasets["ScanDataPlot.y_vals"])

            if "ScanDataPlot.yerr_vals" in dict_datasets:
                err_vals = np.array(dict_datasets["ScanDataPlot.yerr_vals"])
            elif "ScanDataPlot.y_error" in dict_datasets:
                err_vals = np.array(dict_datasets["ScanDataPlot.y_error"])
            else:
                err_vals = None

            x_desc = dict_datasets.get("ScanDataPlot.x_label", "")
            if not x_desc:
                x_desc = getattr(self, 'rid_xlabels', {}).get(
                    rid, getattr(self, 'rid_labels', {}).get(rid, "Bare Scan")
                )

            x_vals, xlabel = process_axis_units(raw_x, x_desc, is_ndscan=False)

            min_len = min(len(x_vals), len(y_vals))
            if err_vals is not None and len(err_vals) > 0:
                min_len = min(min_len, len(err_vals))
                err_vals = err_vals[:min_len]

            return {
                "is_2d": False,
                "x": x_vals[:min_len],
                "y": y_vals[:min_len],
                "err": err_vals[:min_len] if err_vals is not None else None,
                "xlabel": xlabel,
                "ylabel": "counts"
            }

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
                fit_obj.guess_parameters(x_vals, y_vals, x_label=xlabel)

        num_rows = getattr(fit_obj, 'num_params', 0)
        cols = getattr(fit_obj, 'cols', 6)

        self.fitTableWidget.setRowCount(num_rows)
        self.fitTableWidget.setColumnCount(cols)
        self.fitTableWidget.setHorizontalHeaderLabels(['Enable', 'Parameter', 'Initial', 'Fit', 'Min', 'Max'])

        for row in range(num_rows):
            checkbox = QCheckBox()
            checkbox.setChecked(fit_obj.params2Dlist[row][0])
            chk_widget = QtWidgets.QWidget()
            chk_layout = QtWidgets.QHBoxLayout(chk_widget)
            chk_layout.addWidget(checkbox)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.fitTableWidget.setCellWidget(row, 0, chk_widget)

            self.fitTableWidget.setItem(row, 1, QTableWidgetItem(str(fit_obj.params2Dlist[row][1])))

            val = fit_obj.params2Dlist[row][2]
            self.fitTableWidget.setItem(row, 2, QTableWidgetItem(str(val)))

            self.fitTableWidget.setItem(row, 3, QTableWidgetItem(""))

            min_val = fit_obj.params2Dlist[row][4]
            self.fitTableWidget.setItem(row, 4, QTableWidgetItem(str(min_val)))

            max_val = fit_obj.params2Dlist[row][5]
            self.fitTableWidget.setItem(row, 5, QTableWidgetItem(str(max_val)))

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

            # 1. Fetch dataset dictionary for this specific RID
            data = self.get_data_from_rid(rid)
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

            # 2. Load parameters from fit table into fit object
            self._update_fit_params_from_table(fittype)

            try:
                # 3. Perform Fit using activateFit()
                _, params2DlistFit = fit_obj.activateFit(x_vals, y_vals)
                fit_obj.params2Dlist = params2DlistFit

                # 4. Update the "Fit" column in the parameter table
                for ind, param in enumerate(params2DlistFit):
                    fit_val = param[3]
                    fmt = f"{fit_val:.4e}" if abs(fit_val) < 0.001 and fit_val != 0 else f"{fit_val:.4f}"
                    self.fitTableWidget.setItem(ind, 3, QTableWidgetItem(fmt))

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

        is_2d = data.get("is_2d", False)

        if is_2d:
            # Remove any existing 2D scan heatmaps to prevent overlapping 2D layers
            for existing_rid in list(self.rid_items.keys()):
                if self.rid_items[existing_rid]['is_2d']:
                    self.remove_dataset(existing_rid)

            img_item = pg.ImageItem()
            z_mat = data["z"]
            x_vals = data["x"]
            y_vals = data["y"]

            img_item.setImage(z_mat)
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

            # Insert ColorBar into layout grid
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
                'x': x_vals,
                'y': y_vals,
                'z': z_mat
            }

            self.is_2d = True
            self.x_vals, self.y_vals, self.z_mat = x_vals, y_vals, z_mat
            self._apply_axis_styles(data["xlabel"], data["ylabel"], title=f"RID {rid}")

        else:
            # Render 1D Trace using CET-R2 Rainbow Colormap
            x = np.asarray(data["x"])
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
                name=str(rid) )
            items_list = [curve]
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
                'x': x,
                'y': y,
                'z': None}

            self.is_2d = False
            self.x_vals, self.y_vals, self.z_mat = x, y, None
            self._apply_axis_styles(data["xlabel"], data["ylabel"])

        self._recolor_1d_curves()
        self._ensure_hover_items()

    def _recolor_1d_curves(self):
        """Recolors all active 1D curves, symbols, error bars, and fit curves."""
        d_1d = [r for r, d in self.rid_items.items() if not d.get('is_2d', False)]
        if not d_1d:
            return

        colors = self.colormap_1d.getLookupTable(nPts=max(1, len(d_1d)), alpha=True, mode='qcolor')

        for idx, rid in enumerate(d_1d):
            color = colors[idx % len(colors)]
            pen = pg.mkPen(color, width=2)
            dash_pen = pg.mkPen(color, width=2, style=QtCore.Qt.DashLine)

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
        """Returns a dictionary mapping active 1D RID -> QColor using colormap_1d."""
        d_1d = [r for r, d in self.rid_items.items() if not d.get('is_2d', False)]
        if not d_1d:
            return {}
        colors = self.colormap_1d.getLookupTable(nPts=max(1, len(d_1d)), alpha=True, mode='qcolor')
        return {r: colors[i % len(colors)] for i, r in enumerate(d_1d)}

    @property
    def colormap(self):
        """Ensures any legacy fit functions looking for .colormap automatically use .colormap_1d."""
        return self.colormap_1d

    def plotfit(self, x, y, xlabel, ylabel, k, rid):
        """Plots a 1D fit curve using the exact rainbow color assigned to this RID."""
        rid = int(rid)

        # 1. Fetch color assigned to this RID
        rid_colors = self.get_rid_colors()

        if rid in rid_colors:
            fit_color = rid_colors[rid]
        else:
            d_1d = [r for r, d in self.rid_items.items() if not d.get('is_2d', False)]
            n_pts = max(1, len(d_1d))
            colors = self.colormap_1d.getLookupTable(nPts=n_pts, alpha=True, mode='qcolor')
            fit_color = colors[k % len(colors)]

        # 2. Create dashed pen matching trace color
        ppen = pg.mkPen(color=fit_color, width=2, style=QtCore.Qt.SolidLine)

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
