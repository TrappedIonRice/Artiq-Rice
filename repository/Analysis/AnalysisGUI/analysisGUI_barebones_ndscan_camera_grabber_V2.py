import sys
import os
import re
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
Supports camera / grabber ROI data (all ROIs on one plot, or one subplot per ROI).
'''

# Channel / dataset names that are treated as grabber ROIs when parsing ndscan
# channels (case-insensitive regex). Edit this if your ROI channels are named differently.
# ==============================================================================
# GLOBAL SETTINGS  (edit these to tune the GUI)
# ==============================================================================
# --- Paths / polling ---------------------------------------------------------
BASE_PATH = "C:/Users/TrappedIonRice4/Documents/Artiq-Rice"   # contains last_rid.pyon and results/
NUM_RIDS = 200              # max rows kept in the RID table
SEARCH_INTERVAL_MS = 1000   # how often to look for new RIDs
RID_WAIT_S = 30.0           # how long to wait on the NEWEST rid before moving on
MISSED_RETRY_S = 5.0        # how often to retry skipped rids
MISSED_KEEP_S = 600.0       # stop retrying a skipped rid after this long
SCAN_CLASS_NAMES = [        # experiment classes the GUI will list
    'executeScan',
    'BarebonesArtiqScanV1',
    'BarebonesArtiqScanV2',
    'BarebonesArtiqScan2DV1',
    'BarebonesArtiqScan2DGrabberV2',
]

# --- Y axis of 1D plots when the "Y axis 0-1" box is checked ------------------
Y_RANGE_MIN = -0.05
Y_RANGE_MAX = 1.05

# --- Fonts: main plot (point sizes) -------------------------------------------
AXIS_LABEL_PT = 18          # axis titles ("Detuning (MHz)", ...)
TICK_PT = 16                # numbers on the axes
TITLE_PT = 24               # plot header (RID numbers)
COLORBAR_TICK_PT = 16       # numbers on heatmap colorbars
LEGEND_PT = 14              # legend entries
HOVER_FONT_PT = 11          # x/y/z hover box on heatmaps
TITLE_BOLD = True
TITLE_DEFAULT_COLOR = "#000000"   # RID colour when the data has no single trace colour (heatmaps, ROI data)
TITLE_RID_SEPARATOR = "&nbsp;&nbsp;&nbsp;"   # between RIDs when several are plotted

# --- Fonts: ROI subplot grid (point sizes) ------------------------------------
SUB_AXIS_LABEL_PT = 13
SUB_TICK_PT = 12
SUB_TITLE_PT = 15
SUB_COLORBAR_TICK_PT = 11
SUB_LEGEND_PT = 11

# --- Traces / colours ---------------------------------------------------------
LINE_WIDTH = 2              # data line width
FIT_LINE_WIDTH = 3          # fit curve width
SYMBOL_SIZE_1D = 10         # marker size, single-trace plots
SYMBOL_SIZE_ROI = 8         # marker size, camera/grabber ROI traces
COLORMAP_1D = "CET-R2"      # colours assigned to different RIDs / ROIs
COLORMAP_2D = "plasma"      # heatmaps

def html_span(text, color="#000000", pt=12, bold=False):
    """Small helper for coloured, sized rich-text (axis labels / titles)."""
    weight = "font-weight: bold;" if bold else ""
    return f'<span style="font-size: {pt}pt; color: {color}; {weight}">{text}</span>'


def add_legend(target, pt):
    """Add a legend with a given label size (falls back gracefully on old pyqtgraph)."""
    try:
        return target.addLegend(labelTextSize=f"{pt}pt")
    except TypeError:
        return target.addLegend()

GRABBER_CHANNEL_REGEX = re.compile(r"roi|grabber", re.IGNORECASE)


def make_colorbar(z_min, z_max, cmap):
    """ColorBarItem across pyqtgraph versions (colorMap= in >=0.12, cmap= in older ones)."""
    try:
        return pg.ColorBarItem(values=(z_min, z_max), colorMap=cmap, interactive=False)
    except TypeError:
        return pg.ColorBarItem(values=(z_min, z_max), cmap=cmap, interactive=False)


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

        # Plotting Dock: a stack holding the normal single plot and the ROI subplot grid
        self.plotdock = Dock("AnalysisPlot", size=(600, 400))
        self.graphWidget = AnalysisPlotWidget()
        self.subplotWidget = GrabberSubplotWidget()
        self.plotStack = QtWidgets.QStackedWidget()
        self.plotStack.addWidget(self.graphWidget)
        self.plotStack.addWidget(self.subplotWidget)
        self.plotdock.addWidget(self.plotStack)
        self.plotdock.setGeometry(0, 0, 1000, 500)

        # Search and Fitting Dock
        self.searchFitDock = Dock("Search&Fit", size=(600, 400))
        self.searchFitDock.setMaximumWidth(600)
        searchFitlayout = QtWidgets.QVBoxLayout()
        self.searchFitWidget = SearchFitWidget(self.graphWidget, self.subplotWidget, self.plotStack)
        self.searchFitDock.setLayout(searchFitlayout)
        self.searchFitDock.addWidget(self.searchFitWidget)

        layout.addWidget(dock_area)
        dock_area.addDock(self.searchFitDock)
        dock_area.addDock(self.plotdock, 'right', self.searchFitDock)

        self.show()


# Assume fitfunc, find_results, load_hdf5_file are imported from your project utilities


class SearchFitWidget(QtWidgets.QWidget):

    def __init__(self, analysisplotWidget, subplotWidget=None, plotStack=None):
        super(SearchFitWidget, self).__init__()

        # --- PATH CONFIGURATION ---
        self.base_path = BASE_PATH
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
        self._prev_path = None  # previous day's folder (set by check_date_update)

        # Variables
        self.filelist = []
        self.selectedfilelist = []
        self.fitlist = getattr(fitfunc, 'FIT_DICTIONARY', {}) if 'fitfunc' in globals() else {}
        self.num_rids = NUM_RIDS

        # --- RID polling state (see updateSearchList) ---
        self._search_busy = False       # re-entrancy guard for the timer callback
        self._pending = {}              # rid -> time we first failed to find it
        self._missed = {}               # rid -> time we gave up waiting (retried in background)
        self._last_missed_check = 0.0
        self.rid_wait_s = RID_WAIT_S          # how long to wait on the NEWEST rid before moving on
        self.missed_retry_s = MISSED_RETRY_S       # how often to retry skipped rids
        self.missed_keep_s = MISSED_KEEP_S      # stop retrying a skipped rid after this long

        # Extended filter list to support both 1D and 2D scan experiment classes
        self.filterScanNames = list(SCAN_CLASS_NAMES)

        self.dataDict = {}
        self.selectedDataDict = {}
        self.fitTraces = {}
        self.fitCheckboxTraces = {}
        self.dataCheckboxTraces = {}

        # References
        self.analysisPlotWidget = analysisplotWidget
        self.subplotWidget = subplotWidget
        self.plotStack = plotStack

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
        self.yRangeCheck = QtWidgets.QCheckBox("Y axis 0-1")
        self.yRangeCheck.setChecked(True)
        self.yRangeCheck.setToolTip("Fix the y axis of all 1D plots (and ROI subplots) to 0..1.\n"
                                    "Uncheck to autoscale (e.g. for raw counts above 1). 2D heatmaps are unaffected.")
        self.buttonsHlayout.addWidget(self.yRangeCheck)
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
        header = self.fileTableWidget.horizontalHeader()
        self.fileTableWidget.setColumnWidth(self.rid_colInd, 60)
        self.fileTableWidget.setColumnWidth(self.dataChk_colInd, 45)
        self.fileTableWidget.setColumnWidth(self.fitChk_colInd, 45)
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

        # --- ROI Control Row (above Fit row), only visible for camera/grabber data ---
        self.roiRowWidget = QtWidgets.QWidget()
        self.roiRowLayout = QtWidgets.QHBoxLayout()
        self.roiRowLayout.setSpacing(10)
        self.roiRowWidget.setLayout(self.roiRowLayout)

        self.roi_label = QtWidgets.QLabel("Camera ROI:", self)
        self.roi_selector = QtWidgets.QComboBox(self)
        self.roi_selector.addItem("All ROIs")
        self.roi_selector.setToolTip("Select which Camera ROI to plot and fit individually")

        # NEW: one plot for all ROIs (default) vs. one subplot per ROI
        self.roiCombineCheck = QtWidgets.QCheckBox("Plot all ROIs on one plot")
        self.roiCombineCheck.setChecked(True)
        self.roiCombineCheck.setToolTip(
            "Checked: all ROIs share one plot (2D data: sum of the selected ROIs).\n"
            "Unchecked: every ROI gets its own subplot (2D data: one heatmap per ROI).")

        self.roi_label.setVisible(False)
        self.roi_selector.setVisible(False)
        self.roiCombineCheck.setVisible(False)

        self.roiRowLayout.addWidget(self.roi_label)
        self.roiRowLayout.addWidget(self.roi_selector)
        self.roiRowLayout.addWidget(self.roiCombineCheck)
        self.roiRowLayout.addStretch()

        self.fitselectionColumnLayout.addWidget(self.roiRowWidget)

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
        self.Searchtimer.setInterval(SEARCH_INTERVAL_MS)
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
        self.yRangeCheck.stateChanged.connect(self.on_yrange_toggled)
        self.on_yrange_toggled()  # apply the default (checked) to the plot widgets
        self.fitselectionRowFitButton.clicked.connect(getattr(self, 'fitData', lambda: None))
        self.fitselectionRowClearFitButton.clicked.connect(self.clearFitPlot)
        self.fitselectionRowPlotButton.clicked.connect(getattr(self, 'plotFitFunction', lambda: None))
        self.searchFitFileExplorerButton.clicked.connect(self.fileExplorerDialog)

        # ROI controls for camera / grabber data
        self.roi_selector.currentIndexChanged.connect(self.on_roi_selection_changed)
        self.roiCombineCheck.stateChanged.connect(self.on_roi_selection_changed)

    ####################################################
    # PLOT ROUTING (single plot vs. ROI subplot grid)
    ####################################################
    def _use_subplots_for(self, data):
        """Camera/grabber data goes to the subplot grid when 'all ROIs on one plot' is unchecked."""
        return (self.subplotWidget is not None
                and bool(data) and bool(data.get('is_camera', False))
                and not self.roiCombineCheck.isChecked())

    def _plot_add(self, rid, data, color_idx, total_count):
        if self._use_subplots_for(data):
            self.analysisPlotWidget.remove_dataset(rid)
            self.subplotWidget.add_dataset(rid, data, color_idx, total_count)
        else:
            if self.subplotWidget is not None:
                self.subplotWidget.remove_dataset(rid)
            self.analysisPlotWidget.add_dataset(rid=rid, data=data, color_idx=color_idx, total_count=total_count)
        self._update_stack()

    def _plot_remove(self, rid):
        self.analysisPlotWidget.remove_dataset(rid)
        if self.subplotWidget is not None:
            self.subplotWidget.remove_dataset(rid)
        self._update_stack()

    def _plot_clear(self):
        self.analysisPlotWidget.clear_all()
        if self.subplotWidget is not None:
            self.subplotWidget.clear_all()
        self._update_stack()

    def on_yrange_toggled(self, *_):
        flag = self.yRangeCheck.isChecked()
        self.analysisPlotWidget.set_y_unit_range(flag)
        if self.subplotWidget is not None:
            self.subplotWidget.set_y_unit_range(flag)

    def _update_stack(self):
        """Show the subplot grid whenever it holds data, otherwise the normal plot."""
        if self.plotStack is None or self.subplotWidget is None:
            return
        if self.subplotWidget.has_data():
            self.plotStack.setCurrentWidget(self.subplotWidget)
        else:
            self.plotStack.setCurrentWidget(self.analysisPlotWidget)

    ####################################################
    ######### ROIs when plotting camera/grabber data ###
    ####################################################
    def update_roi_dropdown_visibility(self):
        """Checks if any active plot is camera/grabber data and updates the ROI controls."""
        has_camera = False
        available_rois = set()

        for rid in self.dataCheckboxTraces:
            data = self.get_data_from_rid(rid)
            if data and data.get("is_camera", False):
                has_camera = True
                available_rois.update(data.get('roi_names', []))

        if has_camera:
            self.roi_label.setVisible(True)
            self.roi_selector.setVisible(True)
            self.roiCombineCheck.setVisible(True)

            current_selection = self.roi_selector.currentText()

            self.roi_selector.blockSignals(True)
            self.roi_selector.clear()
            self.roi_selector.addItem("All ROIs")
            for roi in sorted(available_rois):
                self.roi_selector.addItem(roi)

            index = self.roi_selector.findText(current_selection)
            self.roi_selector.setCurrentIndex(index if index >= 0 else 0)
            self.roi_selector.blockSignals(False)
        else:
            self.roi_label.setVisible(False)
            self.roi_selector.setVisible(False)
            self.roiCombineCheck.setVisible(False)

    def get_filtered_data(self, rid):
        """Returns the data dictionary, dynamically filtering out unselected ROIs."""
        data = self.get_data_from_rid(rid)
        if not data:
            return None

        if data.get("is_camera"):
            selected_roi = self.roi_selector.currentText()

            # 2D grabber data: pick one ROI's heatmap (default 'z' is the sum of all ROIs)
            if data.get("is_2d"):
                z_rois = data.get("z_rois", {})
                if selected_roi != "All ROIs" and selected_roi in z_rois:
                    out = data.copy()
                    out['z_rois'] = {selected_roi: z_rois[selected_roi]}
                    out['z'] = z_rois[selected_roi]
                    out['roi_label'] = selected_roi
                    return out
                return data

            # 1D camera data
            if selected_roi != "All ROIs" and isinstance(data.get('y'), dict) and selected_roi in data['y']:
                filtered_data = data.copy()
                filtered_data['y'] = {selected_roi: data['y'][selected_roi]}
                if data.get('err') and isinstance(data['err'], dict) and selected_roi in data['err']:
                    filtered_data['err'] = {selected_roi: data['err'][selected_roi]}
                else:
                    filtered_data['err'] = {selected_roi: None}
                filtered_data['roi_names'] = [selected_roi]
                return filtered_data

        return data

    def on_roi_selection_changed(self, *_):
        """Triggered when the ROI dropdown or the 'all ROIs on one plot' box changes."""
        rids = []
        for rid in list(self.dataCheckboxTraces.keys()):
            base_data = self.get_data_from_rid(rid)
            if base_data and base_data.get("is_camera", False):
                rids.append(rid)

        for rid in rids:
            self._plot_remove(rid)

        keys = list(self.dataCheckboxTraces.keys())
        for rid in rids:
            filtered_data = self.get_filtered_data(rid)
            if filtered_data:
                self._plot_add(rid, filtered_data, keys.index(rid), len(keys))

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
                data = self.get_filtered_data(rid)
                if data:
                    self._plot_add(rid, data, len(self.dataCheckboxTraces) - 1, len(self.dataCheckboxTraces))
            else:
                if rid in self.dataCheckboxTraces:
                    del self.dataCheckboxTraces[rid]
                self._plot_remove(rid)

            self.updateTableRIDColors()
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

                luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
                text_color = QtGui.QColor("white") if luminance < 128 else QtGui.QColor("black")
                rid_cell.setForeground(QtGui.QBrush(text_color))

            elif rid in self.dataCheckboxTraces:
                # Fallback color for 2D scans / camera data
                rid_cell.setBackground(QtGui.QBrush(QtGui.QColor("#e6f2ff")))
                rid_cell.setForeground(QtGui.QBrush(QtGui.QColor("black")))
            else:
                rid_cell.setBackground(QtGui.QBrush(QtGui.QColor("white")))
                rid_cell.setForeground(QtGui.QBrush(QtGui.QColor("black")))

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
        """Clears 1D line items, 2D heatmaps, subplots, crosshairs, colorbars, and unchecks data/fit boxes."""
        self._plot_clear()
        self.fileTableWidget.clearSelection()

        datakeylist = list(self.dataCheckboxTraces.keys())
        fitkeylist = list(self.fitCheckboxTraces.keys())

        for rid in datakeylist:
            self.clearDataChkBox(rid)
        for rid in fitkeylist:
            self.clearFitChkBox(rid)

        # The checkboxes were unchecked with signals blocked, so forget them explicitly
        # (otherwise the next 'Plot' / autoplot would resurrect the cleared RIDs).
        self.dataCheckboxTraces.clear()
        self.fitCheckboxTraces.clear()
        self.fitTraces.clear()

        self.updateTableRIDColors()
        self.update_roi_dropdown_visibility()

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

    # --------------------------------------------------------------------------
    # RID POLLING (timer driven)
    # --------------------------------------------------------------------------
    def autofunctions(self):
        # Re-entrancy guard + catch-all: an exception or a slow tick must never
        # leave the list permanently stuck.
        if self._search_busy:
            return
        self._search_busy = True
        try:
            self.updateSearchList()
        except Exception as e:
            print(f"Error while updating RID list (will retry next tick): {e}")
        finally:
            self._search_busy = False

    def check_date_update(self):
        """Dynamically updates self.updated_path to the latest daily subdirectory."""
        try:
            if os.path.exists(self.results_path):
                all_subdir = sorted(f.name for f in os.scandir(self.results_path) if f.is_dir())
                if all_subdir:
                    latest_path = os.path.join(self.results_path, all_subdir[-1])
                    self._prev_path = (os.path.join(self.results_path, all_subdir[-2])
                                       if len(all_subdir) > 1 else None)
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

    def _search_rid_anywhere(self, rid):
        """Look in today's folder, then the previous day's (a run can straddle midnight)."""
        status = self.searchSingleFile(rid, self.updated_path)
        if status is False and self._prev_path:
            status = self.searchSingleFile(rid, self._prev_path)
        return status

    def updateSearchList(self):
        """
        Picks up new RIDs without ever getting stuck on a single one.

        Old behaviour: wait on rid N+1 for up to 50000 ticks (~14 h). Any RID that never
        produced a loadable result file (aborted run, failed experiment, odd file) froze
        the whole list until the GUI was restarted.

        Now: if a newer RID is already announced (or we waited rid_wait_s on the newest one)
        we move on and keep retrying the skipped RID in the background for a while.
        """
        self.check_date_update()
        now = time.monotonic()

        # 1) Background retry of skipped RIDs (late-finishing runs show up when ready)
        if self._missed and now - self._last_missed_check >= self.missed_retry_s:
            self._last_missed_check = now
            for rid in sorted(self._missed):
                status = self._search_rid_anywhere(rid)
                if status is not False:
                    del self._missed[rid]
                    if status is True:
                        self.autoPlotLastRID()
                elif now - self._missed[rid] > self.missed_keep_s:
                    print(f"Giving up on RID {rid} (no loadable result file after {self.missed_keep_s:.0f} s).")
                    del self._missed[rid]

        # 2) Advance through new RIDs
        target_last_rid = self.extractingLastrid(self.lastridfile)
        if target_last_rid is None or target_last_rid <= self.last_rid:
            return

        t0 = time.monotonic()
        while self.last_rid < target_last_rid and time.monotonic() - t0 < 0.5:
            next_rid = self.last_rid + 1
            status = self._search_rid_anywhere(next_rid)

            if status is False:
                first_seen = self._pending.setdefault(next_rid, now)
                newer_exists = next_rid < target_last_rid
                waited_long = (time.monotonic() - first_seen) > self.rid_wait_s
                if newer_exists or waited_long:
                    print(f"RID {next_rid} not ready; moving on and retrying in background.")
                    self._missed[next_rid] = time.monotonic()
                    self._pending.pop(next_rid, None)
                    self.last_rid = next_rid
                    continue
                break  # newest RID may still be being written; try again next tick

            self._pending.pop(next_rid, None)
            self.last_rid = next_rid
            if status is True:
                self.autoPlotLastRID()

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

                if oldest_rid in self.dataCheckboxTraces:
                    self._plot_remove(oldest_rid)

                self.dataDict.pop(oldest_rid, None)
                self.selectedDataDict.pop(oldest_rid, None)
                self.fitCheckboxTraces.pop(oldest_rid, None)
                self.dataCheckboxTraces.pop(oldest_rid, None)

            self.fileTableWidget.removeRow(0)

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
        def clean_p(raw):
            if raw is None:
                return ""
            if isinstance(raw, np.ndarray):
                raw = raw.item() if raw.size > 0 else ""
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode('utf-8', errors='ignore')
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
        Returns True (Success), False (Not Ready/Error), or None (Filtered / already loaded).
        """
        rid = int(rid)

        # Already in the table (e.g. found late by the background retry)
        if rid in self.dataDict:
            return None

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
            return None

        try:
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

            scan_param_item = QTableWidgetItem(table_scan_param_label)
            scan_param_item.setTextAlignment(QtCore.Qt.AlignCenter)

            self.fileTableWidget.setItem(row_count, self.rid_colInd, QTableWidgetItem(str(rid)))
            self.fileTableWidget.setCellWidget(row_count, self.dataChk_colInd, data_widget)
            self.fileTableWidget.setCellWidget(row_count, self.fitChk_colInd, fit_widget)
            self.fileTableWidget.setItem(row_count, self.ScanParameter_colInd, scan_param_item)
            self.fileTableWidget.setItem(row_count, self.Comments_colInd, QTableWidgetItem(""))

            datacheckbox.stateChanged.connect(
                lambda state, num=rid, col=self.dataChk_colInd: self.selectRangesCheckbox(num, col, state))
            fitcheckbox.stateChanged.connect(
                lambda state, num=rid, col=self.fitChk_colInd: self.selectRangesCheckbox(num, col, state))

            for col in [self.rid_colInd, self.ScanParameter_colInd]:
                item = self.fileTableWidget.item(row_count, col)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

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
            self.dataDict.pop(rid, None)
            return False

    # --------------------------------------------------------------------------
    # GRABBER / CAMERA ROI EXTRACTION
    # --------------------------------------------------------------------------
    def _extract_grabber_rois(self, rid, dd, n_points=None):
        """
        Returns (rois, errs): dicts {roi_name: flat ndarray (one value per scan point)}.

        Looks for (a) ndscan channels whose name matches GRABBER_CHANNEL_REGEX
        ('ndscan.rid_<rid>.points.channel_<name>', optional '<name>_err'), else
        (b) a JSON/array dataset '...Grabber.y' / '...Camera.y'.
        """
        def dec(k):
            return k.decode('utf-8', errors='ignore') if isinstance(k, (bytes, bytearray)) else str(k)

        keymap = {dec(k): k for k in dd.keys()}
        rois, errs = {}, {}

        # (a) ndscan channels
        prefix = f"ndscan.rid_{rid}.points.channel_"
        for ks, k in keymap.items():
            if not ks.startswith(prefix):
                continue
            name = ks[len(prefix):]
            if name.lower().endswith("err") or not GRABBER_CHANNEL_REGEX.search(name):
                continue
            try:
                rois[name] = np.array(dd[k], dtype=float).ravel()
            except Exception:
                continue
            err_key = keymap.get(prefix + name + "_err")
            if err_key is not None:
                try:
                    errs[name] = np.array(dd[err_key], dtype=float).ravel()
                except Exception:
                    pass
        if rois:
            return rois, errs

        # (b) Grabber.y / Camera.y style dataset
        for ks, k in keymap.items():
            if not re.search(r"(Grabber|Camera)\.y", ks):
                continue
            raw = dd[k]
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode('utf-8', errors='ignore')
            data = None
            if isinstance(raw, str):
                try:
                    data = json.loads(raw)
                except Exception:
                    data = None
            if data is None:
                data = np.array(raw)

            def split_val_err(vals):
                vals = np.array(vals, dtype=float)
                if vals.ndim == 2 and vals.shape[1] == 2 and (n_points is None or vals.shape[0] == n_points):
                    return vals[:, 0], vals[:, 1]
                return vals.ravel(), None

            if isinstance(data, dict):
                for roi, roi_data in data.items():
                    v = roi_data['value'] if isinstance(roi_data, dict) and 'value' in roi_data else roi_data
                    rois[str(roi)], e = split_val_err(v)
                    if e is not None:
                        errs[str(roi)] = e
            else:
                arr = np.array(data, dtype=float)
                if arr.ndim == 1:
                    rois["Camera ROI"] = arr
                elif arr.ndim == 2:
                    for col in range(arr.shape[1]):
                        rois[f"ROI {col}"] = arr[:, col]
            if rois:
                return rois, errs

        return {}, {}

    # --------------------------------------------------------------------------
    # BARE-ARTIQ GRABBER DATA  (BarebonesArtiqScan2DGrabberV2 -> _grabber_plot)
    # Datasets: ScanDataPlotGrabber.ROI<k>.{x_vals,y_vals,yerr_vals}  (1D)
    #           ScanDataPlotGrabber.ROI<k>.{x_vals,y_vals,z_vals}     (2D, z is (num_y, num_x))
    # Axis values are already in display units (ms / MHz), so no rescaling here.
    # --------------------------------------------------------------------------
    _BARE_GRABBER_RE = re.compile(r"^ScanDataPlotGrabber\.(ROI\d+)\.(x_vals|y_vals|yerr_vals|z_vals)$")

    def _bare_grabber_data(self, dd):
        def dec(k):
            return k.decode('utf-8', errors='ignore') if isinstance(k, (bytes, bytearray)) else str(k)

        per = {}
        flat = {dec(k): v for k, v in dd.items()}
        for ks, v in flat.items():
            m = self._BARE_GRABBER_RE.match(ks)
            if m:
                per.setdefault(m.group(1), {})[m.group(2)] = v
        if not per:
            return None
        names = sorted(per, key=lambda n: int(n[3:]))

        def label(key, default):
            raw = flat.get(key, default)
            if isinstance(raw, np.ndarray):
                raw = raw.item() if raw.size > 0 else default
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode('utf-8', errors='ignore')
            return str(raw)

        xlabel = label("ScanDataPlot.x_label", "Scan parameter")

        if any('z_vals' in per[n] for n in names):
            z_rois = {n: np.array(per[n]['z_vals'], dtype=float) for n in names if 'z_vals' in per[n]}
            z_rois = {n: z for n, z in z_rois.items() if z.ndim == 2}
            if not z_rois:
                return None
            first = next(iter(z_rois))
            ny, nx = z_rois[first].shape
            x = np.array(per[first].get('x_vals', []), dtype=float)
            y = np.array(per[first].get('y_vals', []), dtype=float)
            if len(x) != nx:
                x = np.arange(nx, dtype=float)
            if len(y) != ny:
                y = np.arange(ny, dtype=float)
            stack = np.array(list(z_rois.values()))
            z_sum = np.where(np.all(np.isnan(stack), axis=0), np.nan, np.nansum(stack, axis=0))
            return {
                "is_2d": True, "is_camera": True,
                "x": x, "y": y, "z": z_sum, "z_rois": z_rois,
                "roi_names": list(z_rois.keys()), "roi_label": "All ROIs (sum)",
                "xlabel": xlabel, "ylabel": label("ScanDataPlot.y_label", "Y Axis"),
                "zlabel": "counts / pixel"
            }

        y_dict, err_dict, xs = {}, {}, None
        for n in names:
            if 'y_vals' not in per[n] or 'x_vals' not in per[n]:
                continue
            xv = np.atleast_1d(np.array(per[n]['x_vals'], dtype=float))
            yv = np.atleast_1d(np.array(per[n]['y_vals'], dtype=float))
            m = min(len(xv), len(yv))
            ev = per[n].get('yerr_vals')
            ev = np.atleast_1d(np.array(ev, dtype=float)) if ev is not None else None
            if ev is not None and len(ev) >= m:
                ev = np.nan_to_num(ev[:m], nan=0.0)
                ev[ev <= 0] = np.nan
            else:
                ev = None
            y_dict[n], err_dict[n] = yv[:m], ev
            xs = xv[:m] if xs is None else xs[:min(len(xs), m)]
        if not y_dict or xs is None or len(xs) == 0:
            return None
        L = len(xs)
        y_dict = {n: v[:L] for n, v in y_dict.items()}
        err_dict = {n: (e[:L] if e is not None else None) for n, e in err_dict.items()}
        return {
            "is_2d": False, "is_camera": True,
            "x": xs, "y": y_dict, "y_primary": next(iter(y_dict.values())), "err": err_dict,
            "roi_names": list(y_dict.keys()),
            "xlabel": xlabel, "ylabel": "Counts / pixel"
        }

    def get_data_from_rid(self, rid):
        """Extracts plot-ready data dictionary with robust unit & description parsing."""
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

            is_time = (
                    unit.lower() == 's' or
                    ' (s)' in desc_clean.lower() or
                    desc_clean.lower().endswith('[s]') or
                    any(w in desc_lower for w in ['time', 'delay', 'wait', 'duration', 'width', 'length'])
            )

            is_freq = (
                    unit.lower() == 'hz' or
                    ' (hz)' in desc_clean.lower() or
                    desc_clean.lower().endswith('[hz]') or
                    'freq' in desc_lower
            )

            if is_time:
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
            if 'Camera.y' in k_str or 'Grabber.y' in k_str:
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
                "roi_names": list(y_dict_rois.keys()),
                "xlabel": final_xlabel,
                "ylabel": "Camera Counts"
            }

        # --- 1D GRABBER (ndscan ROI channels) ---
        def build_grabber_1d(rois, err_rois, raw_x, desc, unit):
            x_vals, xlabel = process_axis_units(raw_x, desc, unit)
            min_len = len(x_vals)
            for v in rois.values():
                min_len = min(min_len, len(v))
            y_dict, err_dict = {}, {}
            for name, v in rois.items():
                y_dict[name] = v[:min_len]
                e = err_rois.get(name)
                if e is not None and len(e) >= min_len:
                    e = np.nan_to_num(e[:min_len], nan=0.0)
                    e[e <= 0] = np.nan
                    err_dict[name] = e
                else:
                    err_dict[name] = None
            first = next(iter(y_dict.values()), np.array([]))
            return {
                "is_2d": False, "is_camera": True,
                "x": x_vals[:min_len], "y": y_dict, "y_primary": first, "err": err_dict,
                "roi_names": list(y_dict.keys()),
                "xlabel": xlabel, "ylabel": "Camera Counts"
            }

        # --- 2D GRABBER: one (num_y, num_x) heatmap per ROI ---
        def build_grabber_2d(rois, raw_x0, raw_x1, x_desc, x_unit, y_desc, y_unit):
            x_u, xi = np.unique(raw_x0, return_inverse=True)
            y_u, yi = np.unique(raw_x1, return_inverse=True)
            xi, yi = xi.ravel(), yi.ravel()
            z_rois = {}
            for name, vals in rois.items():
                n = min(len(vals), len(xi), len(yi))
                z = np.full((len(y_u), len(x_u)), np.nan)
                z[yi[:n], xi[:n]] = vals[:n]
                z_rois[name] = z
            stack = np.array(list(z_rois.values()))
            z_sum = np.where(np.all(np.isnan(stack), axis=0), np.nan, np.nansum(stack, axis=0))
            x_vals, xlabel = process_axis_units(x_u, x_desc, x_unit)
            y_vals, ylabel = process_axis_units(y_u, y_desc, y_unit)
            return {
                "is_2d": True, "is_camera": True,
                "x": x_vals, "y": y_vals, "z": z_sum, "z_rois": z_rois,
                "roi_names": list(z_rois.keys()), "roi_label": "All ROIs (sum)",
                "xlabel": xlabel, "ylabel": ylabel, "zlabel": "counts"
            }

        # --- TYPE G: BARE GRABBER (ScanDataPlotGrabber.ROI<k>.*) ---
        bare_grabber = self._bare_grabber_data(dict_datasets)
        if bare_grabber is not None:
            return bare_grabber

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

                    # ---- Grabber ROI data (2D scan with per-ROI results) ----
                    if is_2d_scan:
                        g_rois, _g_errs = self._extract_grabber_rois(rid, dict_datasets, len(raw_x0))
                        if g_rois and len(raw_x0) > 0 and len(raw_x1) > 0:
                            gx_desc, gx_unit = find_desc_and_unit(axes_list[0])
                            gy_desc, gy_unit = find_desc_and_unit(axes_list[1])
                            return build_grabber_2d(g_rois, raw_x0, raw_x1, gx_desc, gx_unit, gy_desc, gy_unit)

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

                    g1_rois, g1_errs = ({}, {}) if has_camera else self._extract_grabber_rois(rid, dict_datasets)

                    if has_camera:
                        return extract_camera_data(raw_x, final_desc, raw_unit)
                    elif g1_rois:
                        return build_grabber_1d(g1_rois, g1_errs, raw_x, final_desc, raw_unit)
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
                if any(GRABBER_CHANNEL_REGEX.search(str(k)) for k in dict_datasets.keys()):
                    print(f"  RID {rid} dataset keys: {[str(k) for k in dict_datasets.keys()]}")

        # --- TYPE B: BARE ARTIQ 2D ---
        elif "ScanDataPlot.z_vals" in dict_datasets and not has_camera:
            z_mat = np.array(dict_datasets["ScanDataPlot.z_vals"], dtype=float)
            if z_mat.ndim == 2:
                # z_mat.shape[0] is num_y, z_mat.shape[1] is num_x
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
        """Full rebuild pass: clears plots and re-adds all checked datasets and syncs table colors."""
        self._plot_clear()

        total_checked = len(self.dataCheckboxTraces)
        for k, RID in enumerate(list(self.dataCheckboxTraces.keys())):
            rid = int(RID)
            data = self.get_filtered_data(rid)
            if data:
                self._plot_add(rid, data, k, total_checked)

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

                if isinstance(y_vals, dict):
                    roi_key = list(y_vals.keys())[0]
                    y_vals = y_vals[roi_key]

                x_vals = np.array(x_vals, dtype=float)
                y_vals = np.array(y_vals, dtype=float)

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
        Plots fit curves matching dataset trace colors and updates parameter table.
        """
        fittype = self.fitselectionRowComboBox.currentText()
        if not fittype or fittype not in self.fitlist:
            return

        if not hasattr(self, 'fitCheckboxTraces'):
            self.fitCheckboxTraces = {}

        if not hasattr(self, 'fitTraces'):
            self.fitTraces = {}

        fit_obj = self.fitlist[fittype]

        for rid in list(self.fitCheckboxTraces.keys()):
            rid = int(rid)

            data = self.get_filtered_data(rid)
            if not data or data.get("is_2d", False):
                print(f"Skipping fit for RID {rid}: No valid 1D data found.")
                continue

            if self._use_subplots_for(data):
                print(f"Skipping fit for RID {rid}: fit overlay is not available in ROI-subplot mode "
                      f"(tick 'Plot all ROIs on one plot' to fit).")
                continue

            x_vals = data.get("x")
            y_vals = data.get("y")
            xlabel = data.get("xlabel", "")
            ylabel = data.get("ylabel", "counts")

            if x_vals is None or len(x_vals) == 0:
                print(f"Skipping fit for RID {rid}: Empty dataset.")
                continue

            if isinstance(y_vals, dict):
                roi_key = list(y_vals.keys())[0]
                y_vals = y_vals[roi_key]

            x_vals = np.array(x_vals, dtype=float)
            y_vals = np.array(y_vals, dtype=float)

            print(f"\n--- DIAGNOSTIC FOR RID {rid} ---")
            print(f"X shape: {x_vals.shape}, Y shape: {y_vals.shape}")
            print(f"X contains NaN: {np.isnan(x_vals).any()}, Y contains NaN: {np.isnan(y_vals).any()}")
            print(f"X contains Inf: {np.isinf(x_vals).any()}, Y contains Inf: {np.isinf(y_vals).any()}")
            print(f"X min/max: {np.min(x_vals):.3e} / {np.max(x_vals):.3e}")
            print(f"Y min/max: {np.min(y_vals):.3e} / {np.max(y_vals):.3e}")
            print("--------------------------------\n")

            self._update_fit_params_from_table(fittype)

            try:
                _, params2DlistFit = fit_obj.activateFit(x_vals, y_vals)
                fit_obj.params2Dlist = params2DlistFit

                for ind, param in enumerate(params2DlistFit):
                    fit_val = param[3]
                    fmt = f"{fit_val:.4e}" if abs(fit_val) < 0.001 and fit_val != 0 else f"{fit_val:.4f}"
                    self.fitTableWidget.setItem(ind, 3, QtWidgets.QTableWidgetItem(fmt))

                initial_guesses_backup = [row[2] for row in fit_obj.params2Dlist]
                for row in fit_obj.params2Dlist:
                    row[2] = row[3]

                x_smooth = np.linspace(np.min(x_vals), np.max(x_vals), 500)
                y_smooth = fit_obj.functionVal(x_smooth)

                for i, row in enumerate(fit_obj.params2Dlist):
                    row[2] = initial_guesses_backup[i]

                if rid in self.fitTraces:
                    self.analysisPlotWidget.removeItem(self.fitTraces[rid])
                    del self.fitTraces[rid]

                keys_as_ints = [int(k) for k in self.dataCheckboxTraces.keys()]
                k = keys_as_ints.index(rid) if rid in keys_as_ints else 0

                fitplotitem = self.analysisPlotWidget.plotfit(x_smooth, y_smooth, xlabel, ylabel, k, rid)
                self.fitTraces[rid] = fitplotitem

            except Exception as e:
                print(f"Fitting failed for RID {rid}: {e}")


# ==============================================================================
# ROI SUBPLOT GRID (one subplot per ROI; several 2D heatmaps at once)
# ==============================================================================
class GrabberSubplotWidget(pg.GraphicsLayoutWidget):
    """
    Shows camera/grabber data as a grid of subplots.
      - 2D data: one heatmap (with its own colorbar) per (RID, ROI)
      - 1D data: one plot per ROI, with every checked RID overlaid
    """

    def __init__(self, parent=None):
        super(GrabberSubplotWidget, self).__init__(parent)
        self.setBackground('w')
        self.colormap_1d = pg.colormap.get(COLORMAP_1D)
        self.datasets = {}
        self._dirty = False
        self.y_unit_range = True

    def set_y_unit_range(self, flag):
        self.y_unit_range = bool(flag)
        if self.datasets:
            self._schedule_rebuild()

    def has_data(self):
        return bool(self.datasets)

    def add_dataset(self, rid, data, color_idx=0, total_count=1):
        self.datasets[int(rid)] = data
        self._schedule_rebuild()

    def remove_dataset(self, rid):
        if self.datasets.pop(int(rid), None) is not None:
            self._schedule_rebuild()

    def clear_all(self):
        self.datasets.clear()
        self.clear()

    # Coalesce bursts of add/remove calls (e.g. a full replot) into a single rebuild
    def _schedule_rebuild(self):
        if not self._dirty:
            self._dirty = True
            QTimer.singleShot(0, self._rebuild)

    @staticmethod
    def _style(plot, xlabel, ylabel, title_html):
        plot.setLabel('bottom', text=html_span(xlabel, "black", SUB_AXIS_LABEL_PT))
        plot.setLabel('left', text=html_span(ylabel, "black", SUB_AXIS_LABEL_PT))
        plot.setTitle(title_html)
        plot.showGrid(x=True, y=True)
        tick_font = QtGui.QFont()
        tick_font.setPointSize(SUB_TICK_PT)
        for name in ('bottom', 'left'):
            ax = plot.getAxis(name)
            ax.setTickFont(tick_font)
            ax.setPen('k')
            ax.setTextPen('k')

    def _rebuild(self):
        self._dirty = False
        self.clear()

        panels = []
        for rid, data in self.datasets.items():
            if data.get('is_2d'):
                for roi, z in data.get('z_rois', {}).items():
                    panels.append(('2d', rid, roi, data, z))

        roi_groups = {}
        for rid, data in self.datasets.items():
            if not data.get('is_2d') and isinstance(data.get('y'), dict):
                for roi in data['y'].keys():
                    roi_groups.setdefault(roi, []).append((rid, data))
        for roi in sorted(roi_groups):
            panels.append(('1d', None, roi, roi_groups[roi], None))

        n = len(panels)
        if n == 0:
            return
        ncols = int(np.ceil(np.sqrt(n)))

        for i, (kind, rid, roi, data, z) in enumerate(panels):
            row, col = divmod(i, ncols)
            plot = self.addPlot(row=row, col=col)
            try:
                if kind == '2d':
                    self._draw_2d(plot, rid, roi, data, z)
                else:
                    self._draw_1d(plot, roi, data)
            except Exception as e:
                print(f"Subplot error ({kind}, RID {rid}, ROI {roi}): {e}")

    def _draw_2d(self, plot, rid, roi, data, z):
        x_vals, y_vals = np.asarray(data["x"]), np.asarray(data["y"])
        img = pg.ImageItem()
        img.setImage(z.T)  # (num_x, num_y) for pyqtgraph

        cmap = pg.colormap.get(COLORMAP_2D)
        img.setLookupTable(cmap.getLookupTable(nPts=256))

        all_nan = np.isnan(z).all()
        z_min = 0.0 if all_nan else float(np.nanmin(z))
        z_max = 1.0 if all_nan else float(np.nanmax(z))
        if z_min == z_max:
            z_max += 1.0
        img.setLevels([z_min, z_max])

        if len(x_vals) > 1 and len(y_vals) > 1:
            dx = (x_vals[-1] - x_vals[0]) / (len(x_vals) - 1)
            dy = (y_vals[-1] - y_vals[0]) / (len(y_vals) - 1)
            img.setRect(QtCore.QRectF(x_vals[0] - dx / 2.0, y_vals[0] - dy / 2.0,
                                      (x_vals[-1] - x_vals[0]) + dx, (y_vals[-1] - y_vals[0]) + dy))
        plot.addItem(img)

        try:
            bar = make_colorbar(z_min, z_max, cmap)
            bar.setColorMap(cmap)
            bar.setImageItem(img, insert_in=plot)
            cb_font = QtGui.QFont()
            cb_font.setPointSize(SUB_COLORBAR_TICK_PT)
            cb_axis = bar.getAxis('right')
            cb_axis.setTickFont(cb_font)
            cb_axis.setTextPen('k')
            cb_axis.setPen('k')
        except Exception as e:
            print(f"ColorBarItem warning: {e}")

        self._style(plot, data.get("xlabel", ""), data.get("ylabel", ""),
                    html_span(f"RID {rid} - {roi}", TITLE_DEFAULT_COLOR, SUB_TITLE_PT, TITLE_BOLD))

    def _draw_1d(self, plot, roi, rid_data):
        colors = self.colormap_1d.getLookupTable(nPts=max(1, len(rid_data)), alpha=True, mode='qcolor')
        if len(rid_data) > 1:
            add_legend(plot, SUB_LEGEND_PT)
        xlabel = ylabel = ""
        title_parts = [html_span(f"{roi}:", TITLE_DEFAULT_COLOR, SUB_TITLE_PT, TITLE_BOLD)]
        for idx, (rid, data) in enumerate(rid_data):
            color = colors[idx % len(colors)]
            title_parts.append(html_span(f"RID {rid}", color.name(), SUB_TITLE_PT, TITLE_BOLD))
            pen = pg.mkPen(color, width=LINE_WIDTH)
            x = np.asarray(data["x"])
            y = np.asarray(data["y"][roi])
            n = min(len(x), len(y))
            plot.plot(x[:n], y[:n], pen=pen, symbol='o', symbolSize=SYMBOL_SIZE_ROI, symbolBrush=color, name=str(rid))
            err = (data.get("err") or {}).get(roi) if isinstance(data.get("err"), dict) else None
            if err is not None:
                err = np.asarray(err)[:n]
                if len(err) == n:
                    plot.addItem(pg.ErrorBarItem(x=x[:n], y=y[:n], top=err, bottom=err, pen=pen))
            xlabel, ylabel = data.get("xlabel", ""), data.get("ylabel", "")
        self._style(plot, xlabel, ylabel, " ".join(title_parts))
        if self.y_unit_range:
            plot.setYRange(Y_RANGE_MIN, Y_RANGE_MAX, padding=0)


# ==============================================================================
# ANALYSIS PLOT WIDGET CLASS (1D Plots + 2D Heatmaps)
# ==============================================================================
class AnalysisPlotWidget(pg.PlotWidget):

    def __init__(self, parent=None):
        super(AnalysisPlotWidget, self).__init__(parent)
        self.showGrid(x=True, y=True)
        self.setBackground('w')

        # 1D plots use the CET-R2 rainbow colormap
        self.colormap_1d = pg.colormap.get(COLORMAP_1D)

        # Keep your 2D heatmap colormap separate (e.g., viridis/plasma)
        self.colormap_2d = pg.colormap.get(COLORMAP_2D)

        self.rid_items = {}
        self.y_unit_range = True  # fix y axis to 0..1 for 1D plots

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

        if rid in self.rid_items:
            self.remove_dataset(rid)

        if self.plotItem.legend is None:
            add_legend(self, LEGEND_PT)

        is_2d = data.get("is_2d", False)
        is_camera = data.get("is_camera", False)

        if is_2d:
            # Remove any existing 2D scan heatmaps to prevent overlapping 2D layers
            for existing_rid in list(self.rid_items.keys()):
                if self.rid_items[existing_rid]['is_2d']:
                    self.remove_dataset(existing_rid)

            img_item = pg.ImageItem()
            z_mat = data["z"]  # Shape: (num_y, num_x)
            x_vals = data["x"]  # Length: num_x
            y_vals = data["y"]  # Length: num_y

            img_item.setImage(z_mat.T)

            plasma_cmap = pg.colormap.get(COLORMAP_2D)
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
                colorbar = make_colorbar(z_min, z_max, plasma_cmap)
                colorbar.setColorMap(plasma_cmap)
                colorbar.setImageItem(img_item, insert_in=self.plotItem)

                cb_font = QtGui.QFont()
                cb_font.setPointSize(COLORBAR_TICK_PT)
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
                'z': z_mat,
                'roi_label': data.get("roi_label")
            }

            self.is_2d = True
            self.x_vals, self.y_vals, self.z_mat = x_vals, y_vals, z_mat
            self._apply_axis_styles(data["xlabel"], data["ylabel"])

        else:
            x = np.asarray(data["x"])
            items_list = []

            # ---------------------------------------------------------
            # 1D CAMERA MULTI-ROI PLOTTING
            # ---------------------------------------------------------
            if is_camera:
                y_dict = data["y"]
                err_dict = data.get("err", {})

                num_rois = len(y_dict)
                roi_colors = self.colormap_1d.getLookupTable(nPts=max(1, num_rois), alpha=True, mode='qcolor')

                for i, (roi_name, y_vals) in enumerate(y_dict.items()):
                    y = np.asarray(y_vals)
                    min_len = min(len(x), len(y))
                    x_sub, y_sub = x[:min_len], y[:min_len]

                    color = roi_colors[i % len(roi_colors)]
                    ppen = pg.mkPen(color, width=LINE_WIDTH)

                    curve = self.plot(
                        x_sub, y_sub,
                        pen=ppen,
                        symbol='o',
                        symbolSize=SYMBOL_SIZE_ROI,
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

                colors = self.colormap_1d.getLookupTable(nPts=max(1, total_count), alpha=True, mode='qcolor')
                current_color = colors[color_idx % len(colors)]
                ppen = pg.mkPen(current_color, width=LINE_WIDTH)

                curve = self.plot(
                    x, y,
                    pen=ppen,
                    symbol='o',
                    symbolSize=SYMBOL_SIZE_1D,
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
        self.apply_y_range()
        self._update_title()

    def _update_title(self):
        """Header = the RID number(s), each in the colour of its trace (black if it has no single colour)."""
        if not self.rid_items:
            self.setTitle("")
            return
        colors = self.get_rid_colors()
        parts = []
        for rid, d in self.rid_items.items():
            col = colors.get(rid)
            hexc = col.name() if col is not None else TITLE_DEFAULT_COLOR
            txt = f"RID {rid}"
            if d.get('is_2d') and d.get('roi_label'):
                txt += f" - {d['roi_label']}"
            parts.append(html_span(txt, hexc, TITLE_PT, TITLE_BOLD))
        self.setTitle(TITLE_RID_SEPARATOR.join(parts))

    def set_y_unit_range(self, flag):
        self.y_unit_range = bool(flag)
        self.apply_y_range()

    def apply_y_range(self):
        """Pin y to 0..1 for 1D plots when enabled; otherwise (or for 2D heatmaps) autoscale."""
        vb = self.plotItem.vb
        has_2d = any(d.get('is_2d') for d in self.rid_items.values())
        if self.y_unit_range and self.rid_items and not has_2d:
            vb.setYRange(Y_RANGE_MIN, Y_RANGE_MAX, padding=0)
        else:
            vb.enableAutoRange(axis=pg.ViewBox.YAxis)

    def _recolor_1d_curves(self):
        """Recolors active 1D PMT curves (ignores Camera ROIs to preserve distinct colors)."""
        d_1d = [r for r, d in self.rid_items.items() if not d.get('is_2d', False) and not d.get('is_camera', False)]
        if not d_1d:
            return

        colors = self.colormap_1d.getLookupTable(nPts=max(1, len(d_1d)), alpha=True, mode='qcolor')

        for idx, rid in enumerate(d_1d):
            color = colors[idx % len(colors)]
            pen = pg.mkPen(color, width=LINE_WIDTH)

            item_data = self.rid_items[rid]

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

        for item in item_dict['curves']:
            try:
                self.removeItem(item)
            except Exception:
                pass

        if item_dict['image'] is not None:
            try:
                self.removeItem(item_dict['image'])
            except Exception:
                pass

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

        if not self.rid_items:
            self._reset_state()
        else:
            self._recolor_1d_curves()
        self._update_title()

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

        if hasattr(self, 'plotItem'):
            self.plotItem.clear()

        self._reset_state()

    def clear(self):
        self.clear_all()

    def _apply_axis_styles(self, xlabel, ylabel):
        self.setLabel('bottom', text=html_span(xlabel, "black", AXIS_LABEL_PT))
        self.setLabel('left', text=html_span(ylabel, "black", AXIS_LABEL_PT))

        tick_font = QtGui.QFont()
        tick_font.setPointSize(TICK_PT)
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

                nx, ny = len(self.x_vals), len(self.y_vals)
                val = None
                if self.z_mat.shape == (ny, nx):  # documented layout (num_y, num_x)
                    val = self.z_mat[y_idx, x_idx]
                elif self.z_mat.shape == (nx, ny):
                    val = self.z_mat[x_idx, y_idx]

                if val is not None:
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
        <table style="color: black; font-size: {HOVER_FONT_PT}pt; font-family: monospace; border-collapse: collapse; padding: 2px;">
            <tr><td style="text-align: right; font-weight: bold; padding-right: 4px;">x:</td><td>{x_tile_center:.7g}</td></tr>
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

        fit_color = pg.mkColor('r')

        if rid in self.rid_items and self.rid_items[rid].get('curves'):
            for item in self.rid_items[rid]['curves']:
                if isinstance(item, pg.PlotDataItem):
                    fit_color = item.opts['pen'].color()
                    break
        else:
            colors = self.colormap_1d.getLookupTable(nPts=max(1, k+1), alpha=True, mode='qcolor')
            fit_color = colors[k % len(colors)]

        ppen = pg.mkPen(color=fit_color, width=FIT_LINE_WIDTH, style=QtCore.Qt.SolidLine)

        plotitem = self.plot(x, y, pen=ppen, name=f"{rid}: Fit")

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