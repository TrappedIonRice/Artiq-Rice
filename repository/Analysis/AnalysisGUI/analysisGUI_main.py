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
        print("Hello")
        self.setWindowTitle("Analysis Window")
        layout=QtWidgets.QVBoxLayout()
        dock_area=DockArea(self)
        # testlabel=QtWidgets.QLabel("Meaningful docks?")
        # layout.addWidget(testlabel)
        central_widget=QtWidgets.QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Plotting
        self.plotdock = Dock("AnalysisPlot", size=(600, 400))
        self.graphWidget = AnalysisPlotWidget()
        self.plotdock.addWidget(self.graphWidget)
        self.plotdock.setGeometry(0, 0, 1000, 500)

        #Search and fitting
        self.searchFitDock=Dock("Search&Fit", size=(600,400))
        self.searchFitDock.setMaximumWidth(600)
        searchFitlayout=QtWidgets.QVBoxLayout()
        self.searchFitWidget=SearchFitWidget(self.graphWidget) # passing plot object to search widget for inheritance
        self.searchFitDock.setLayout(searchFitlayout)
        self.searchFitDock.addWidget(self.searchFitWidget)

        # self.plotdock.hideTitleBar()
        # self.plotdock.hideTitleBar()

        layout.addWidget(dock_area)
        dock_area.addDock(self.searchFitDock)
        dock_area.addDock(self.plotdock,'right',self.searchFitDock)
        #dock_area.addDock(self.plotdock)
        #self.graphWidget.plotdata()#np.arange(10),np.arange(10))

        #self.setGeometry(500, 25, 800, 600)
        self.show()

class SearchFitWidget(QtWidgets.QWidget):

    def __init__(self, analysisplotWidget):
        super(SearchFitWidget,self).__init__()

        #variables
        self.filelist = []
        self.selectedfilelist=[]
        self.fitlist=fitfunc.FIT_DICTIONARY

        self.lastridfile = "C:/Users/TrappedIonRice4/Documents/Artiq-Rice/last_rid.pyon"
        # for data files
        self.default_path="C:/Users/TrappedIonRice4/Documents/Artiq-Rice/results/2024-09-21" # change this to the latest date.

        # latest based on last subdir in /results
        self.parent_directory="C:/Users/TrappedIonRice4/Documents/Artiq-Rice/results"
        all_subdir=[f.name for f in os.scandir(self.parent_directory) if f.is_dir()]
        self.latest_subdir=''.join([self.parent_directory,'/',all_subdir[-1]])

        # latest based on last date
        self.latest_date=datetime.datetime.now()
        self.latest_date_subdir="C:/Users/TrappedIonRice4/Documents/Artiq-Rice/results"+self.latest_date.strftime("%Y-%m-%d")

        # updated_path method
        #self.updated_path=self.latest_date_subdir
        self.updated_path=self.latest_subdir

        # assign updated_path to default_path in the long run.

        self.num_rids = 30  # list out last R rids in file list box
        self.filterScanName = 'executeScan'
        # Defining dictionary to store all the relevant scan datasets
        self.dataDict = {}
        self.selectedDataDict={}
        self.fitTraces= {} # stores {rid: plotitem}
        self.fitCheckboxTraces={}
        self.dataCheckboxTraces={}

        #classes
        self.analysisPlotWidget=analysisplotWidget

        #graphics

        self.searchFitLayout=QtWidgets.QVBoxLayout()
        self.setLayout(self.searchFitLayout)
        # Search section
        self.searchFitHLayout=QtWidgets.QHBoxLayout()
        self.searchLabel=QtWidgets.QLabel('Search for files')
        self.searchFitHLayout.addWidget(self.searchLabel)
        self.searchFitFileExplorerButton=QtWidgets.QPushButton('RID File Explorer')
        self.searchFitHLayout.addWidget(self.searchFitFileExplorerButton)
        self.searchFitLayout.addLayout(self.searchFitHLayout)

        #buttons
        self.plotButtonWidget=QtWidgets.QPushButton('Plot')
        self.clearplotsButtonWidget=QtWidgets.QPushButton('Clear')

        self.buttonsHlayout=QtWidgets.QHBoxLayout()
        # plot button widget
        self.buttonsHlayout.addWidget(self.plotButtonWidget)
        # plot clear button: removes all plots in the plot window and the datasets in dataDict
        self.buttonsHlayout.addWidget(self.clearplotsButtonWidget)
        # autoplot last rid
        self.autoplotCheckBox= QtWidgets.QCheckBox("Autoplot last RID")
        self.buttonsHlayout.addWidget(self.autoplotCheckBox)

        # search specific rid



        # adds the Hlayout of buttons to a Vlayout object
        self.searchFitLayout.addLayout(self.buttonsHlayout)


        # file search table
        self.fileTableWidget=QtWidgets.QTableWidget()
        self.fileTableWidget.setColumnCount(5)
        self.fileTableWidget.setHorizontalHeaderLabels(['rid','Data','Fit','Scan parameter', 'Comments'])
        self.rid_colInd=0
        self.dataChk_colInd=1
        self.fitChk_colInd=2
        self.ScanParameter_colInd=3
        self.Comments_colInd=4
        self.fileTableWidget.setShowGrid(False)  # Hide gridlines (horizontal and vertical)
        
        vscrollbar=QtWidgets.QScrollBar(self)
        self.fileTableWidget.setVerticalScrollBar(vscrollbar)
        self.searchFitLayout.addWidget(self.fileTableWidget)
        self.fileTableWidget.setSelectionMode(2) # Multiselection mode- 4 , single selection mode-2

        # Fitting section
        self.fitselectionColumnWidget=QtWidgets.QWidget()
        self.fitselectionColumnLayout=QtWidgets.QVBoxLayout()
        self.fitselectionColumnWidget.setLayout(self.fitselectionColumnLayout)

        self.fitselectionRowWidget=QtWidgets.QWidget()
        self.fitselectionRowlayout=QtWidgets.QHBoxLayout()
        self.fitselectionRowWidget.setLayout(self.fitselectionRowlayout)
        self.fitselectionRowLabel=QtWidgets.QLabel('Fit Type:')
        self.fitselectionRowlayout.addWidget(self.fitselectionRowLabel)
        self.fitselectionRowComboBox=QtWidgets.QComboBox()#FitStringBox()
        self.fitselectionRowlayout.addWidget(self.fitselectionRowComboBox)
        self.fitselectionRowFitButton=QtWidgets.QPushButton('Fit')
        self.fitselectionRowlayout.addWidget(self.fitselectionRowFitButton)
        self.fitselectionRowPlotButton = QtWidgets.QPushButton('Plot')
        self.fitselectionRowlayout.addWidget(self.fitselectionRowPlotButton)
        self.fitselectionRowClearFitButton = QtWidgets.QPushButton('Clear fit')
        self.fitselectionRowlayout.addWidget(self.fitselectionRowClearFitButton)

        #adding first row of fit selection into Vbox layout
        self.fitselectionColumnLayout.addWidget(self.fitselectionRowWidget)
        #adding fit description to second row of the Vbox layout
        #self.fitdescriptionLabel=QtWidgets.QLabel('A*exp(x)+B')  # placeholder, have to pass the right description
        self.fitdescriptionLabel = QtWidgets.QLabel('')
        self.fitdescriptionLabel.setAlignment(Qt.AlignCenter)
        self.fitselectionColumnLayout.addWidget(self.fitdescriptionLabel)


        #self.searchFitLayout.addWidget(self.fitselectionRowWidget)
        self.searchFitLayout.addWidget(self.fitselectionColumnWidget)
        self.fitTableWidget=QtWidgets.QTableWidget()
        self.searchFitLayout.addWidget(self.fitTableWidget)

        # initializing functions
        self.last_rid = self.extractingLastrid(self.lastridfile)
        self.searchfiles(self.last_rid ,self.num_rids, self.updated_path)
        # With Searchtimer, files will be searched and added at the bottom of existing files every 1s
        self.Searchtimer = QTimer(self)
        self.Searchtimer.setInterval(1000)  # 1 seconds interval to check for updates
        self.Searchtimer.timeout.connect(self.autofunctions) # will continuously check for update with this rate
        self.Searchtimer.start()

        # self.listFiles()

        # fitting functions
        self.fitComboBoxList()
        self.fittingTableParam()

        # action functions
        self.onClickFunctions()

    def onClickFunctions(self): # needs to be updated
        self.plotButtonWidget.clicked.connect(self.plotfiledata)
        self.clearplotsButtonWidget.clicked.connect(self.clearPlots)
        self.autoplotCheckBox.stateChanged.connect(self.autoPlotLastRID)
        self.fitselectionRowFitButton.clicked.connect(self.fitData)
        self.fitselectionRowClearFitButton.clicked.connect(self.clearFitPlot)
        self.fitselectionRowPlotButton.clicked.connect(self.plotFitFunction)
        self.searchFitFileExplorerButton.clicked.connect(self.fileExplorerDialog)

    def fileExplorerDialog(self):
        # Set default directory
        default_directory = os.path.expanduser(self.updated_path)  # Example: Start from the Documents folder
        # Open file dialog starting from the default directory
        file_path, _ = QFileDialog.getOpenFileName(self, "Select a File", default_directory)

        if file_path:
            print(f"Selected File: {file_path}")
            file_path_list=file_path.split('/')
            rid_filename=file_path_list[-1]
            rid_filename_list=rid_filename.split('-')
            rid=int(rid_filename_list[0])
            print(rid)
            joined_list='/'.join(file_path_list[:-2])
            print(joined_list)
            self.searchSingleFile(rid,joined_list)
        # must meet requirement of multiple rids too. Getting too invasive vs having to just enter rid and


    def selectRangesCheckbox(self, rid, row, col, state):
        '''
        Looks for multiple elements checked in a checkbox column and stores an ordered dictionary of row values
        of each rid dataset in the table.
        :param col:
        :return:
        '''

        if col == self.fitChk_colInd:
            if state==Qt.Checked:
                if rid not in self.fitCheckboxTraces:
                    self.fitCheckboxTraces[rid]=row
            elif state== Qt.Unchecked:
                if rid in self.fitCheckboxTraces:
                    del self.fitCheckboxTraces[rid]

        elif col==self.dataChk_colInd:
            if state==Qt.Checked:
                if rid not in self.dataCheckboxTraces:
                    self.dataCheckboxTraces[rid]=row
            elif state== Qt.Unchecked:
                if rid in self.dataCheckboxTraces:
                    del self.dataCheckboxTraces[rid]

        print(self.fitCheckboxTraces)
        print(self.dataCheckboxTraces)

    def clearPlots(self):
        self.analysisPlotWidget.clear()
        self.fileTableWidget.clearSelection()
        datakeylist=list(self.dataCheckboxTraces)
        fitkeylist=list(self.fitCheckboxTraces)
        for rid in datakeylist:
            self.clearDataChkBox(rid)
        for rid in fitkeylist:
            self.clearFitChkBox(rid)
        self.uncolorRIDlabels()


    def clearDataChkBox(self,rid):

        #uncheck box for every row/rid in the dataCheckboxTraces
        row= self.dataCheckboxTraces[rid]
        (self.fileTableWidget.cellWidget(row,self.dataChk_colInd)).setChecked(False)
        #datacheckbox.setChecked(False)
        # this state change should in principle automatically trigger selectRangesCheckBox but let's explicitly do it anyway
        # this should remove the item from dataCheckboxTraces as well.
        self.selectRangesCheckbox(rid, row, self.dataChk_colInd, False)

    def clearFitChkBox(self,rid):
        # uncheck box for every row/rid in the fitCheckboxTraces
        row = self.fitCheckboxTraces[rid]
        # setting check box state to required color.
        (self.fileTableWidget.cellWidget(row, self.fitChk_colInd)).setChecked(False)
        # this state change should in principle automatically trigger selectRangesCheckBox but let's explicitly do it anyway
        # this should remove the item from fitCheckboxTraces as well.
        self.selectRangesCheckbox(rid, row, self.fitChk_colInd, False)

    def clearFitPlot(self):
        last_fit_rid=list(self.fitCheckboxTraces.keys())[-1]
        self.analysisPlotWidget.removeItem(self.fitTraces[last_fit_rid])
        # uncheck and remove last selected rid's checkbox
        self.clearFitChkBox(last_fit_rid)

    def autoPlotLastRID(self):
        state=self.autoplotCheckBox.isChecked()
        #print('Here ' + str(state))
        if state== True:
            row_last_rid=self.getRowMaxRID() # row of maximum value RID among ones filtered for execute Scan
            print(row_last_rid)
            # select last row of file search to appearing selected
            # first extracting last row's checkbox value
            if not (self.fileTableWidget.cellWidget(row_last_rid,self.dataChk_colInd)).isChecked():
                (self.fileTableWidget.cellWidget(row_last_rid, self.dataChk_colInd)).setChecked(True)
            # plot all selected rids again
            self.plotSelectedData()
        else:
            pass

    def getRowMaxRID(self):

        rid_list=[int(self.fileTableWidget.item(row,self.rid_colInd).text())
                  for row in range(self.fileTableWidget.rowCount())]
        #print(max(rid_list))
        return rid_list.index(max(rid_list))

    def autofunctions(self):

        self.updateSearchList()
        #self.date_update() # uncomment it in the main PC for complete operation

    def date_update(self):
        '''
        This should be called only after the first R rids have been listed in the latest subdirectory, which may not be latest date.
        '''
        #self.default_path = "C:/Users/abhim/Documents/Artiq-Rice/results/2024-09-21"  # change this to the latest date.
        self.latest_date = datetime.datetime.now()
        self.updated_path = "C:/Users/TrappedIonRice4/Documents/Artiq-Rice/results/" + self.latest_date.strftime("%Y-%m-%d")

    def uncolorRIDlabels(self):
        '''
        updates all the check boxes to have white background color
        :return:
        '''
        for row in range(self.fileTableWidget.rowCount()):# unselected_data_rows:
            rid_cell = self.fileTableWidget.item(row, self.rid_colInd)
            rid_cell.setBackground(QColor("white"))


    def updateSearchList(self):
        '''
        updates search list only if the last rid has increased
        :return:
        '''

        # self.autoPlotLastRID(self.autoplotCheckBox.isChecked())
        temp_last_rid=self.extractingLastrid(self.lastridfile) #from file
        #print(str(self.last_rid) + "old and new:" + str(temp_last_rid))
        if temp_last_rid>self.last_rid: # only updated the list if the new rid num is larger than the previous one
            #print(str(self.last_rid)+"old and new:"+ str(temp_last_rid))
            self.searchfiles( temp_last_rid,temp_last_rid-self.last_rid-1, self.updated_path) # Add more files to the search list which will be filtered based on the scan type
            self.last_rid = temp_last_rid
            self.autoPlotLastRID()


    def extractingLastrid(self, filename):
        # first get last rid
        with open(filename, 'r') as file:
            first_line = file.readline().strip()  # Read the first line and remove any surrounding whitespace

            # Assuming the first line is of the form "last_rid"
            try:
                value = int(first_line)  # Convert the value part to an integer
                return value
            except (ValueError, IndexError) as e:
                print(f"Error reading integer value: {e}")
                return None

    def searchfiles(self,last_rid, num_rids,rootpath):
        '''

        :param last_rid:
        :param num_rids: num of new rids - 1. eg. if only one last_rid value exists, then num_rids=0 is required
        :param rootpath:
        :return:
        '''
        # first get last rid
        list_rids = list(np.arange(last_rid - num_rids, last_rid + 1, 1))
        # extract all rid files.

        for rid in list_rids:
            self.searchSingleFile(rid,rootpath)


    def searchSingleFile(self,rid,rootpath):

        dict_test = find_results("", rid=int(rid),
                                 root_path=rootpath)  # returns dict of results, used to find file path
        # except:
        #     print("RID: " + str(rid) + " does not exist!")
        # filter only those rid files whose type is executeScan. checking cls
        if dict_test:
            if dict_test[int(rid)][-1]==self.filterScanName:

                dict_hdf5 = load_hdf5_file(dict_test[int(rid)][0])  # returns file as dict
                dict_datasets = dict_hdf5["datasets"]  # dict key where all points are stored in a nested dict

                # extracting xlabel
                scanparam_axis0 = json.loads(dict_datasets['ndscan.rid_' + str(rid) + '.axes'])[0]
                unit = ""
                # if 'unit' in scanparam_axis0['param']['spec'].keys():
                #     unit = '(' + scanparam_axis0['param']['spec']['unit'] + ')'
                xlabel_axis0 = scanparam_axis0['param']['description'] + unit
                comments=""

                # stores the rid and datasets for the rid file
                # if bool(self.dataDict):
                #     self.dataDict.update({int(rid),dict_datasets})
                # else:else
                self.dataDict[int(rid)]=dict_datasets
                # adding elements to row of the table widget
                row_count = self.fileTableWidget.rowCount()  # Get the current number of rows
                self.fileTableWidget.insertRow(row_count)  # Insert a new row at the end
                # Populate the cells of the new row
                fitcheckbox=QCheckBox(self)
                datacheckbox=QCheckBox(self)
                self.fileTableWidget.setItem(row_count,  self.rid_colInd, QTableWidgetItem(str(rid)))
                self.fileTableWidget.setCellWidget(row_count, self.dataChk_colInd, datacheckbox) # Data checkbox
                self.fileTableWidget.setCellWidget(row_count, self.fitChk_colInd, fitcheckbox) #Fit checkbox
                self.fileTableWidget.setItem(row_count, self.ScanParameter_colInd, QTableWidgetItem(xlabel_axis0))
                self.fileTableWidget.setItem(row_count, self.Comments_colInd, QTableWidgetItem(comments))
                datacheckbox.stateChanged.connect(lambda state,r=row_count,col=self.dataChk_colInd,num=rid : self.selectRangesCheckbox(num,r,col,state))
                fitcheckbox.stateChanged.connect(lambda state,r=row_count,col=self.fitChk_colInd,num=rid : self.selectRangesCheckbox(num,r,col,state))

                # make sure that columns 0,3 are unmutable (rid and xlabel_axis0)
                for col in [self.rid_colInd,self.ScanParameter_colInd]:
                    item=self.fileTableWidget.item(row_count,col)
                    if item:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        else:
            print("RID: " + str(rid) + " does not exist!")
        del dict_test

        #
        # samplelist = [str(i) for i in range(4)] # maybe dictionary of {rid: [rid_name, data: 2d vals]} is better.
        # self.filelist=samplelist

    # def listFiles(self):
    #     for i in self.filelist:
    #         self.fileTableWidget.addItem(i)i


    def plotSelectedData(self):

        self.analysisPlotWidget.NselectedDatasets= len(self.dataCheckboxTraces)
        # whitening colors of all cells before any data plot action
        self.uncolorRIDlabels()
        for k,RID in enumerate(self.dataCheckboxTraces.keys()):
            rid= int(RID)
            print(rid)
            dict_datasets=self.dataDict[rid]
            self.selectedDataDict[rid]=dict_datasets
            #plotting the selected dataset
            scanparam_axis0 = json.loads(dict_datasets['ndscan.rid_' + str(rid) + '.axes'])[0]
            unit = ""
            # if 'unit' in scanparam_axis0['param']['spec'].keys():
            #     unit = '(' + scanparam_axis0['param']['spec']['unit'] + ')'
            xlabel_axis0 = scanparam_axis0['param']['description'] + unit
            ylabel='counts'
            # assign data for exp 1 and switch point
            key_name_x = "ndscan.rid_" + str(rid) + ".points.axis_0"  # key name for duration parameter points
            key_name_y = "ndscan.rid_" + str(
                rid) + ".points.channel_counts"  # key name for result parameter points
            key_name_err = "ndscan.rid_" + str(
                rid) + ".points.channel_res_err"  # key name for error parameter points
            # print(dict_datasets)
            x_vals_1 = dict_datasets[key_name_x]
            # for i in range(len(x_vals_1)):
            #     x_vals_1[i]=x_vals_1[i]*10**6
            y_vals_1 = dict_datasets[key_name_y]
            err_vals_1 = dict_datasets[key_name_err]
            # x_vals_1 = np.array(x_vals_1) * 1e-3
            #plt.errorbar(x_vals_1, y_vals_1, color=colorlist[k], yerr=err_vals_1, fmt="-o")
            #plt.plot(x_vals_1, y_vals_1, 'X', color=colorlist[k], label="{0:d}".format(rid))
            #plt.xlabel(xlabel_axis0)
            #plt.ylabel('counts')
            #plot
            self.analysisPlotWidget.plotdata(x_vals_1,y_vals_1,err_vals_1,xlabel_axis0,ylabel,k,rid)

            # changing color of check box cell
            rid_cell = self.fileTableWidget.item(self.dataCheckboxTraces[rid], self.rid_colInd)
            rid_cell.setBackground(self.analysisPlotWidget.colors[k])


    def plotfiledata(self):
        #intended to plot the data from rid file
        self.analysisPlotWidget.clear()
        self.plotSelectedData()
        #self.uncolorRIDlabels()

    def fitComboBoxList(self):
        self.fitselectionRowComboBox.addItems(self.fitlist)
        self.fitselectionRowComboBox.currentIndexChanged.connect(self.fittingTableParam)

    def fittingTableParam(self):

        # undeclared: self.fitlist[fittype].rows
        fittype=self.fitselectionRowComboBox.currentText()
        self.fitdescriptionLabel.setText(self.fitlist[fittype].description)
        num_rows=self.fitlist[fittype].num_params
        cols=self.fitlist[fittype].cols
        self.fitTableWidget.setRowCount(num_rows)
        # Column count
        self.fitTableWidget.setColumnCount(cols)
        self.fitTableWidget.setHorizontalHeaderLabels(['Enable', 'Parameter', 'Initial', 'Fit','Min','Max'])

        # initializing fit table's values with default rom FitFunction
        for row in range(num_rows):
            # Populate the cells of the new row
            checkbox = QCheckBox(self)
            checkbox.setChecked(self.fitlist[fittype].params2Dlist[row][0])
            self.fitTableWidget.setCellWidget(row, 0, checkbox)
            for col in range(1, cols):
                self.fitTableWidget.setItem(row, col, QTableWidgetItem(str(self.fitlist[fittype].params2Dlist[row][col])))

        # Table will fit the screen horizontally
        self.fitTableWidget.horizontalHeader().setStretchLastSection(True)
        self.fitTableWidget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

    def plotFitFunction(self):
        '''
        Plots analytic function based on xvalues of the last selection
        :return:
        '''

        # old method: using only last rid and selection of table cells
        #rid = self.extractLastSelectionRID() # old method

        # new method: using checkbox based ordered dictionaries
        rid=list(self.fitCheckboxTraces.keys())[-1] # last rid checked for fits in the fitCheckboxTraces
        dict_datasets = self.selectedDataDict[rid]
        # plotting the selected dataset

        scanparam_axis0 = json.loads(dict_datasets['ndscan.rid_' + str(rid) + '.axes'])[0]
        unit = ""
        # if 'unit' in scanparam_axis0['param']['spec'].keys():
        #     unit = '(' + scanparam_axis0['param']['spec']['unit'] + ')'
        xlabel_axis0 = scanparam_axis0['param']['description'] + unit
        ylabel = 'counts'
        # assign data for exp 1 and switch point
        key_name_x = "ndscan.rid_" + str(rid) + ".points.axis_0"  # key name for duration parameter points
        key_name_y = "ndscan.rid_" + str(
            rid) + ".points.channel_counts"  # key name for result parameter points
        key_name_err = "ndscan.rid_" + str(
            rid) + ".points.channel_res_err"  # key name for error parameter points
        # print(dict_datasets)
        x_vals_1 = dict_datasets[key_name_x]
        # for i in range(len(x_vals_1)):
        #     x_vals_1[i]=x_vals_1[i]*10**6
        y_vals_1 = dict_datasets[key_name_y]
        err_vals_1 = dict_datasets[key_name_err]

        fittype = self.fitselectionRowComboBox.currentText()
        num_rows = self.fitlist[fittype].num_params
        cols = self.fitlist[fittype].cols

        for row in range(num_rows):
            # Populate the cells of the new row
            checkbox = self.fitTableWidget.cellWidget(row, 0)  # (row, 0, checkbox)
            self.fitlist[fittype].params2Dlist[row][0] = checkbox.isChecked()
            # if checkbox.isChecked():
            for col in range(2, cols):
                self.fitlist[fittype].params2Dlist[row][col] = float(self.fitTableWidget.item(row,
                                                                                              col).text())  # , QTableWidgetItem(str(self.fitlist[fittype].params2Dlist[row][col])))
        yfitfunction=self.fitlist[fittype].functionVal(x_vals_1)

        # removing duplicate fit plot of same rid in the analysis Plot widget, and removing the item from the fitTraces dictionary
        if self.fitTraces and (rid in self.fitTraces.keys()):
            delplotitem = self.fitTraces[rid]
            del self.fitTraces[rid]
            self.analysisPlotWidget.removeItem(delplotitem)

        # order of appending to dictionary is in order of selection. fit should be done to very last rid.
        # Eventually I want to change this to adapt to different rids
        k = list(self.dataCheckboxTraces.keys()).index(rid) # entering value of list as rid to get its index
        fitplotitem = self.analysisPlotWidget.plotfit(x_vals_1, yfitfunction, xlabel_axis0, ylabel, k, rid)
        self.fitTraces[rid] = fitplotitem


    def fitData(self):
        '''
        Currently fits only the last rid plot and doesn't store the fits
        :return:
        '''
        rid=list(self.fitCheckboxTraces.keys())[-1]
        dict_datasets = self.selectedDataDict[rid]
        # plotting the selected dataset

        scanparam_axis0 = json.loads(dict_datasets['ndscan.rid_' + str(rid) + '.axes'])[0]
        unit = ""
        # if 'unit' in scanparam_axis0['param']['spec'].keys():
        #     unit = '(' + scanparam_axis0['param']['spec']['unit'] + ')'
        xlabel_axis0 = scanparam_axis0['param']['description'] + unit
        ylabel = 'counts'
        # assign data for exp 1 and switch point
        key_name_x = "ndscan.rid_" + str(rid) + ".points.axis_0"  # key name for duration parameter points
        key_name_y = "ndscan.rid_" + str(
            rid) + ".points.channel_counts"  # key name for result parameter points
        key_name_err = "ndscan.rid_" + str(
            rid) + ".points.channel_res_err"  # key name for error parameter points
        # print(dict_datasets)
        x_vals_1 = dict_datasets[key_name_x]
        # for i in range(len(x_vals_1)):
        #     x_vals_1[i]=x_vals_1[i]*10**6
        y_vals_1 = dict_datasets[key_name_y]
        err_vals_1 = dict_datasets[key_name_err]

        fittype = self.fitselectionRowComboBox.currentText()
        num_rows = self.fitlist[fittype].num_params
        cols = self.fitlist[fittype].cols

        for row in range(num_rows):
            # Populate the cells of the new row
            checkbox=self.fitTableWidget.cellWidget(row,0)#(row, 0, checkbox)
            self.fitlist[fittype].params2Dlist[row][0]=checkbox.isChecked()
            #if checkbox.isChecked():
            for col in range(2, cols):
                self.fitlist[fittype].params2Dlist[row][col]=float(self.fitTableWidget.item(row, col).text())#, QTableWidgetItem(str(self.fitlist[fittype].params2Dlist[row][col])))
        yfit,params2DlistFit=self.fitlist[fittype].activateFit(x_vals_1,y_vals_1) # currently not using error bars of data
        self.fitlist[fittype].params2Dlist=params2DlistFit

        # updating the text in Fit value column of fit table.
        updateindex=3
        for ind,param in enumerate(self.fitlist[fittype].params2Dlist):
            self.fitTableWidget.setItem(ind, updateindex, QTableWidgetItem(str(param[updateindex])))

        # removing duplicate fit plot of same rid in the analysis Plot widget, and removing the item from the fitTraces dictionary
        if self.fitTraces and (rid in self.fitTraces.keys()) :
            delplotitem=self.fitTraces[rid]
            del self.fitTraces[rid]
            self.analysisPlotWidget.removeItem(delplotitem)

        # order of appending to dictionary is in order of selection. fit should be done to very last rid.
        # Eventually I want to change this to adapt to different rids
        k = list(self.dataCheckboxTraces.keys()).index(rid) # entering value of list as rid to get its index
        fitplotitem=self.analysisPlotWidget.plotfit(x_vals_1, yfit, xlabel_axis0, ylabel, k, rid )
        self.fitTraces[rid]=fitplotitem


        # for col in range(1, cols):
        #     self.fitTableWidget.setItem(row, col, QTableWidgetItem(str(self.fitlist[fittype].params2Dlist[row][col])))


class AnalysisPlotWidget(PlotWidget):

    def __init__(self):
        super(AnalysisPlotWidget,self).__init__()
        self.showGrid(x=True, y=True)
        self.setBackground('w')

        self.colormap = pg.colormap.get("CET-R2")
        self.NselectedDatasets=0
        self.colors = self.colormap.getLookupTable(nPts=self.NselectedDatasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects
        #random.shuffle(self.colors)
        #legend=self.addLegend(offset=(10,10),frame=True, labelTextColor='black', pen=pg.mkPen('k'), brush=pg.mkBrush('w'))

        # for i, color in enumerate(self.color_palette):
        #     y = np.sin(x + i)  # Create a different curve for each iteration
        #     pen = pg.mkPen(color, width=2)  # Use the color from the palette with specified width
        #     self.plot_widget.plot(x, y, pen=pen)

    def plotdata(self, x,y,y_error, xlabel, ylabel,k,rid):

        #colors=['b','r','g','y','m']
        self.colors = self.colormap.getLookupTable(nPts=self.NselectedDatasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects
        ppen = pg.mkPen(self.colors[k], width=2)
        self.plot(x,y, pen=ppen, symbol='o', symbolSize=10, symbolBrush=self.colors[k], name=str(rid))
        #styles = {'color':'r', 'font-size':'20px'}
        # Create error bars
        error_bars = pg.ErrorBarItem(x=x, y=y, top=y_error, bottom=y_error, pen=ppen)
        # Add error bars to the plot
        self.addItem(error_bars)
        styles = {'font-size': '20px'}
        self.setLabel('left',text=ylabel,color='k', size='16pt')
        self.setLabel('bottom',text=xlabel,color='k', size='16pt')

        # plot data: x, y values
        #pen = pg.mkPen(color=(255, 0, 0), width=15, style=QtCore.Qt.DashLine)
        #self.plot(hour, temperature)
        #self.graphWidget.clear()

    def plotfit(self, x,y,xlabel, ylabel,k,rid):

        #colors=['b','r','g','y','m']
        #self.colors = self.colormap.getLookupTable(nPts=self.NselectedDatasets, alpha=True, mode='qcolor')  # Generate 30 QColor objects
        ppen = pg.mkPen(self.colors[k], width=2)
        plotitem=self.plot(x,y, pen=ppen, name=str(rid)+": Fit")
        #styles = {'color':'r', 'font-size':'20px'}
        # Create error bars
        #error_bars = pg.ErrorBarItem(x=x, y=y, top=y_error, bottom=y_error, pen=ppen)
        # Add error bars to the plot
        #self.addItem(error_bars)
        styles = {'font-size': '20px'}
        self.setLabel('left',text=ylabel,color='k', size='16pt')
        self.setLabel('bottom',text=xlabel,color='k', size='16pt')
        return plotitem




def main():
    app = QtWidgets.QApplication(sys.argv)
    print("Hello")
    main = MainWindow()
    print("Hello")
    #main.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()