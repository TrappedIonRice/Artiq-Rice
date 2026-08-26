from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor
from oitg.results import find_results
from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
from pyqtgraph.dockarea import *
import sys  # We need sys so that we can pass argv to QApplication
import numpy as np
import os
from ndscan.experiment import *
from oitg import *
import time
from oitg.results import *
from oitg.fitting import *
import numpy as np
import matplotlib
# %matplotlib tk
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import scipy.optimize
import pylab as plt
import pickle
import json
# from mpl_interactions import ioff, panhandler, zoom_factory
import oitg
import matplotlib.ticker as mticker
import FitFunctions as fitfunc
import random
import datetime

'''
Simple Analysis GUI for experiment feedback.

'''


class DockArea(DockArea):
    ## This is to prevent the Dock from being resized to te point of disappear
    def makeContainer(self, typ):
        new = super(DockArea, self).makeContainer(typ)
        new.setChildrenCollapsible(False)
        return new


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        # super(MainWindow, self).__init__(*args, **kwargs)

        # Load the UI Page
        # uic.loadUi('analysisUi.ui', self) # From .ui file
        self.setWindowTitle("Data Analysis GUI")
        self.area = DockArea()
        self.setCentralWidget(self.area)
        self.resize(1500, 800)
        self.move(100, 100)
        self.setWindowIcon(QtGui.QIcon('oitg_logo.png'))

        # Create Docks
        self.search_dock = Dock("Search", size=(200, 400))
        self.fit_dock = Dock("Fit", size=(200, 400))
        self.plot_dock = Dock("Plot", size=(800, 400))
        self.fit_param_dock = Dock("Fit Parameters", size=(200, 200))

        # Add Docks to Dock Area
        self.area.addDock(self.search_dock, 'left')
        self.area.addDock(self.fit_dock, 'left')
        self.area.addDock(self.plot_dock, 'right')
        self.area.addDock(self.fit_param_dock, 'bottom', self.fit_dock)
        self.area.moveDock(self.fit_dock, 'above', self.search_dock)

        # Initialise empty rid list
        self.rid_list = []
        # Store the RID of the last scan plotted by the autoplotter
        self.last_autoplotted_rid = None

        # Add Search dock widgets
        self.populate_search_dock()

        # Add Fit dock widgets
        self.populate_fit_dock()

        # Add Plot dock widgets
        self.populate_plot_dock()

        # Add Fit param dock widgets
        self.populate_fit_param_dock()

        # Colormap for plotting
        self.N_max_datasets = 30
        self.colormap = matplotlib.cm.get_cmap('plasma')
        self.colors = self.colormap(np.linspace(0, 1, self.N_max_datasets))
        self.colors = [tuple(int(x * 255) for x in c) for c in self.colors]
        # self.colors = self.colormap.getLookupTable(nPts=self.N_max_datasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects

        # List of plotted datasets
        self.NselectedDatasets = 0
        self.plotted_rids = []
        self.plotted_fits = []

        # Setup timer for automatic file list updates
        # This addresses Request 1
        self.file_update_timer = QTimer(self)
        self.file_update_timer.timeout.connect(self.periodic_file_update)
        self.file_update_timer.start(5000)  # Update every 5000 ms (5 seconds)
        print("File watcher started: updating every 5 seconds.")

    def update_rid_list(self):
        # Update list of rids
        self.r = find_results()
        self.rid_list = self.r.rid

    def populate_search_dock(self):
        # Create layout for search dock
        self.search_layout = pg.LayoutWidget()
        self.search_dock.addWidget(self.search_layout)

        # Add widgets to search layout
        self.search_rid_label = QLabel("Available RIDs")
        self.search_rid_list = QListWidget()
        self.search_rid_list.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Allow multiple selection
        self.search_rid_list.itemSelectionChanged.connect(self.search_rid_selection_changed)
        self.search_autoplot_last = QCheckBox("Autoplot last RID")
        self.search_autoplot_last.stateChanged.connect(self.autoplot_last_rid)  # Connect to new autoplot function

        # Add a button to clear the plot
        self.search_clear_plot_button = QPushButton("Clear Plot")
        self.search_clear_plot_button.clicked.connect(self.clear_plot)

        # Populate rid list
        if not self.rid_list:
            self.update_rid_list()

        for rid in self.rid_list:
            item = QListWidgetItem(str(rid))
            self.search_rid_list.addItem(item)

        # Add widgets to layout
        self.search_layout.addWidget(self.search_rid_label, row=0, col=0)
        self.search_layout.addWidget(self.search_rid_list, row=1, col=0)
        self.search_layout.addWidget(self.search_autoplot_last, row=2, col=0)
        self.search_layout.addWidget(self.search_clear_plot_button, row=3, col=0)

    def populate_fit_dock(self):
        # Create layout for fit dock
        self.fit_layout = pg.LayoutWidget()
        self.fit_dock.addWidget(self.fit_layout)

        # Add widgets to fit layout
        self.fit_rid_label = QLabel("Available RIDs")
        self.fit_rid_list = QListWidget()
        self.fit_rid_list.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Allow multiple selection
        self.fit_rid_list.itemSelectionChanged.connect(self.fit_rid_selection_changed)
        self.fit_function_label = QLabel("Fit function")
        self.fit_function_combo = QComboBox()
        self.fit_function_combo.addItems(fitfunc.fit_func_dict.keys())  # Add fit functions from FitFunctions.py
        self.fit_function_combo.currentTextChanged.connect(self.fit_function_changed)

        self.fit_button = QPushButton("Fit")
        self.fit_button.clicked.connect(self.fit_selected_rids)

        # Populate rid list
        if not self.rid_list:
            self.update_rid_list()

        for rid in self.rid_list:
            item = QListWidgetItem(str(rid))
            self.fit_rid_list.addItem(item)

        # Add widgets to layout
        self.fit_layout.addWidget(self.fit_rid_label, row=0, col=0)
        self.fit_layout.addWidget(self.fit_rid_list, row=1, col=0)
        self.fit_layout.addWidget(self.fit_function_label, row=2, col=0)
        self.fit_layout.addWidget(self.fit_function_combo, row=3, col=0)
        self.fit_layout.addWidget(self.fit_button, row=4, col=0)

    def populate_plot_dock(self):
        # Add plot widget
        self.graphWidget = pg.PlotWidget()
        self.graphWidget.setBackground('w')
        self.graphWidget.addLegend()
        self.plot_dock.addWidget(self.graphWidget)

    def populate_fit_param_dock(self):
        # Add fit param table
        self.fit_param_table = QTableWidget()
        self.fit_param_table.setColumnCount(6)
        self.fit_param_table.setHorizontalHeaderLabels(["Fit?", "Param", "Initial", "Fitted", "Min", "Max"])
        self.fit_param_dock.addWidget(self.fit_param_table)

        # Initialise table
        self.fit_function_changed()

    # New function to handle periodic file updates (Request 1)
    def periodic_file_update(self):
        """
        Called by QTimer to periodically check for new RID files
        and update the GUI lists.
        """
        # 1. Store current selections to restore them later
        current_search_rids = [item.text() for item in self.search_rid_list.selectedItems()]
        current_fit_rids = [item.text() for item in self.fit_rid_list.selectedItems()]

        # 2. Update the master RID list from the file system
        self.update_rid_list()

        # 3. Repopulate the UI lists
        # We clear and repopulate. A more complex diff-based update
        # could be done but this is simpler and more robust.
        self.search_rid_list.clear()
        for rid in self.rid_list:
            self.search_rid_list.addItem(str(rid))

        self.fit_rid_list.clear()
        for rid in self.rid_list:
            self.fit_rid_list.addItem(str(rid))

        # 4. Restore selections
        for i in range(self.search_rid_list.count()):
            item = self.search_rid_list.item(i)
            if item.text() in current_search_rids:
                item.setSelected(True)

        for i in range(self.fit_rid_list.count()):
            item = self.fit_rid_list.item(i)
            if item.text() in current_fit_rids:
                item.setSelected(True)

        # 5. Handle autoplot (Request 2)
        # If the checkbox is checked, find and plot the latest scan
        if self.search_autoplot_last.isChecked():
            self.find_and_plot_latest_scan()

    # New function to find and plot the latest scan (Request 2)
    def find_and_plot_latest_scan(self):
        """
        Iterates backwards through the rid_list to find the
        most recent 'executeScan' type RID and plots it.
        """
        if not self.rid_list:
            print("Autoplot: No RIDs found.")
            return

        for rid_str in reversed(self.rid_list):
            try:
                rid = int(rid_str)
                scan = load_scan(rid)

                # Check if it's the right type of scan
                if scan.scan_type_id == 'executeScan':
                    # Check if this is a *new* scan we haven't plotted yet
                    if rid != self.last_autoplotted_rid:
                        print(f"Autoplotting new RID: {rid}")
                        self.plot_rid_search(rid)
                        self.last_autoplotted_rid = rid

                    # Found the latest valid scan, so we stop searching
                    return
            except Exception as e:
                # This could happen if the file is still being written or is corrupted
                print(f"Error loading RID {rid_str} for autoplot: {e}")
                # We continue searching backwards in case of a bad file

    def search_rid_selection_changed(self):
        # Get selected rids
        selected_rids = [int(item.text()) for item in self.search_rid_list.selectedItems()]

        # Plot selected rids
        self.plot_selected_rids(selected_rids)

    def fit_rid_selection_changed(self):
        pass

    def fit_function_changed(self):
        # Get selected fit function
        self.selected_fit_function_name = self.fit_function_combo.currentText()

        # Get fit function object
        self.selected_fit_function = fitfunc.fit_func_dict[self.selected_fit_function_name]()

        # Get fit function params
        self.fit_function_params = self.selected_fit_function.params2Dlist

        # Update fit param table
        self.fit_param_table.setRowCount(len(self.fit_function_params))
        for i, row in enumerate(self.fit_function_params):
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if j == 0:
                    # Add checkbox
                    checkbox = QCheckBox()
                    checkbox.setChecked(val)
                    self.fit_param_table.setCellWidget(i, j, checkbox)
                else:
                    self.fit_param_table.setItem(i, j, item)

    def fit_selected_rids(self):
        # Get selected rids
        selected_rids = [int(item.text()) for item in self.fit_rid_list.selectedItems()]

        # Fit each rid
        for k, rid in enumerate(selected_rids):
            self.fit_rid(rid, k)

    def fit_rid(self, rid, k):
        # Get scan
        scan = load_scan(rid)

        # Get x and y data
        x = scan.image_data_array[0, 0, :, 0]
        y = scan.image_data_array[0, 0, :, 1]

        # --- NEW CODE START --- (REMOVED)
        # --- NEW CODE END ---

        # Get fit function
        fit_function = self.selected_fit_function.fitFunction

        # Get fit params (this will now read the smart guesses)
        p0, bounds = self.get_fit_params()

        # Fit
        try:
            popt, pcov = curve_fit(fit_function, x, y, p0=p0, bounds=bounds, maxfev=100000)

            # Get fitted y values
            y_fit = fit_function(x, *popt)

            # Plot fit
            self.plot_fit(x, y_fit, "x", "y", k, rid)

            # Update fit param table
            self.update_fit_param_table(popt)
        except Exception as e:
            print(f"Error fitting RID {rid}: {e}")

    def update_fit_param_table(self, popt):
        # Update fit param table
        for i, val in enumerate(popt):
            item = QTableWidgetItem(str(round(val, 3)))
            self.fit_param_table.setItem(i, 3, item)

    def get_fit_params(self):
        # Get fit params from table
        p0 = []
        min_bounds = []
        max_bounds = []

        for i in range(self.fit_param_table.rowCount()):
            # Check if param is enabled for fit
            if self.fit_param_table.cellWidget(i, 0).isChecked():
                # Add to p0
                p0.append(float(self.fit_param_table.item(i, 2).text()))

                # Add to bounds
                min_bounds.append(float(self.fit_param_table.item(i, 4).text()))
                max_bounds.append(float(self.fit_param_table.item(i, 5).text()))

        bounds = (min_bounds, max_bounds)

        return p0, bounds

    def plot_selected_rids(self, selected_rids):
        # Plot data for each rid
        for k, rid in enumerate(selected_rids):
            # Check if rid already plotted
            if rid not in self.plotted_rids:
                # Plot rid
                self.plot_rid_search(rid)

                # Add to list of plotted rids
                self.plotted_rids.append(rid)
                self.NselectedDatasets += 1

    # Modified function for autoplotting (Request 2)
    def autoplot_last_rid(self, state):
        """
        Called when the 'Autoplot last RID' checkbox is
        checked or unchecked.
        """
        if state == QtCore.Qt.Checked:
            # When user *first* checks the box,
            # immediately try to plot the latest scan
            print("Autoplot enabled by user.")
            self.find_and_plot_latest_scan()
        else:
            print("Autoplot disabled by user.")
            # Optionally, you could clear the last_autoplotted_rid
            # self.last_autoplotted_rid = None
            pass  # Unchecking just stops the periodic plotting

    def plot_rid_search(self, rid):
        # Get scan
        scan = load_scan(rid)

        # Get x and y data
        x = scan.image_data_array[0, 0, :, 0]
        y = scan.image_data_array[0, 0, :, 1]

        # Get x and y labels
        xlabel = "x"
        ylabel = "y"

        # Get a color
        k = self.NselectedDatasets

        # Plot data
        self.plot_data(x, y, xlabel, ylabel, k, rid)

    def plot_data(self, x, y, xlabel, ylabel, k, rid):
        # Create plot
        ppen = pg.mkPen(self.colors[k], width=2)
        self.graphWidget.plot(x, y, pen=ppen, name=str(rid),
                              symbol='o', symbolSize=10, symbolBrush=(self.colors[k]))

        # Add labels
        self.graphWidget.setLabel('left', text=ylabel, color='k', size='16pt')
        self.graphWidget.setLabel('bottom', text=xlabel, color='k', size='16pt')

    def plot_fit(self, x, y, xlabel, ylabel, k, rid):
        # Create plot
        ppen = pg.mkPen(self.colors[k], width=2, style=QtCore.Qt.DashLine)
        self.graphWidget.plot(x, y, pen=ppen, name=str(rid) + ": Fit")

        # Add labels
        self.graphWidget.setLabel('left', text=ylabel, color='k', size='16pt')
        self.graphWidget.setLabel('bottom', text=xlabel, color='k', size='16pt')

    def clear_plot(self):
        self.graphWidget.clear()
        self.plotted_rids = []
        self.NselectedDatasets = 0
        self.last_autoplotted_rid = None  # Reset autoplotter state
        self.graphWidget.addLegend()


class CustomPlotWidget(pg.PlotWidget):
    def __init__(self, *args, **kwargs):
        super(CustomPlotWidget, self).__init__(*args, **kwargs)

    def plotdata(self, x, y, y_error, xlabel, ylabel, k, rid):
        # colors=['b','r','g','y','m']
        # self.colors = self.colormap.getLookupTable(nPts=self.NselectedDatasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects
        ppen = pg.mkPen(self.colors[k], width=2)
        plotitem = self.plot(x, y, pen=ppen, name=str(rid))
        plotitem.setSymbol('o')
        plotitem.setSymbolBrush(self.colors[k])
        # styles = {'color':'r', 'font-size':'20px'}
        # Create error bars
        error_bars = pg.ErrorBarItem(x=x, y=y, top=y_error, bottom=y_error, pen=ppen)
        # Add error bars to the plot
        self.addItem(error_bars)
        styles = {'font-size': '20px'}
        self.setLabel('left', text=ylabel, color='k', size='16pt')
        self.setLabel('bottom', text=xlabel, color='k', size='16pt')

        # plot data: x, y values
        # pen = pg.mkPen(color=(255, 0, 0), width=15, style=QtCore.Qt.DashLine)
        # self.plot(hour, temperature)
        # self.graphWidget.clear()

    def plotfit(self, x, y, xlabel, ylabel, k, rid):
        # colors=['b','r','g','y','m']
        # self.colors = self.colormap.getLookupTable(nPts=self.NselectedDatasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects
        ppen = pg.mkPen(self.colors[k], width=2)
        plotitem = self.plot(x, y, pen=ppen, name=str(rid) + ": Fit")
        # styles = {'color':'r', 'font-size':'20px'}
        # Create error bars
        # error_bars = pg.ErrorBarItem(x=x, y=y, top=y_error, bottom=y_error, pen=ppen)
        # Add error bars to the plot
        # self.addItem(error_bars)
        styles = {'font-size': '20px'}
        self.setLabel('left', text=ylabel, color='k', size='16pt')
        self.setLabel('bottom', text=xlabel, color='k', size='16pt')

        # plot data: x, y values
        # pen = pg.mkPen(color=(255, 0, 0), width=15, style=QtCore.Qt.DashLine)
        # self.plot(hour, temperature)
        # self.graphWidget.clear()

    def clear(self):
        self.clearPlots()
        self.clear()


def main():
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()