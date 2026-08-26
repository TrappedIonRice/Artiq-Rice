#!/usr/bin/env python3

import numpy as np
import PyQt5  # make sure pyqtgraph imports Qt5
from PyQt5.QtCore import QTimer
import pyqtgraph

from artiq.applets.simple import TitleApplet

# 26/01/08 gt
#import argparse
#parser = argparse.ArgumentParser()
#parser.add_argument("y", type=str)
#parser.add_argument("--x", type=str, default=None)
#parser.add_argument("--error", type=str, default=None)
#parser.add_argument("--fit", type=str, default=None)
#parser.add_argument("--title", type=str, default=None)
# Add these two for axis labels:
#parser.add_argument("--xlabel", type=str, default=None, help="Label for X axis")
#parser.add_argument("--ylabel", type=str, default=None, help="Label for Y axis")
#args = parser.parse_args()
##########

class XYPlot(pyqtgraph.PlotWidget):
    def __init__(self, args):
        super().__init__() # 26/01/08 gt
        pyqtgraph.PlotWidget.__init__(self)
        self.args = args
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.length_warning)
        self.mismatch = {'X values': False,
                         'Error bars': False,
                         'Fit values': False}
        
        # 26/01/08 gt
        self.xlabel = getattr(args, "xlabel", None)
        self.ylabel = getattr(args, "ylabel", None)

    def data_changed(self, data, mods, title):
        try:
            y = data[self.args.y][1]
        except KeyError:
            return
        x = data.get(self.args.x, (False, None))[1]
        if x is None:
            x = np.arange(len(y))
        error = data.get(self.args.error, (False, None))[1]
        fit = data.get(self.args.fit, (False, None))[1]

        if not len(y) or len(y) != len(x):
            self.mismatch['X values'] = True
        else:
            self.mismatch['X values'] = False
        if error is not None and hasattr(error, "__len__"):
            if not len(error):
                error = None
            elif len(error) != len(y):
                self.mismatch['Error bars'] = True
            else:
                self.mismatch['Error bars'] = False
        if fit is not None:
            if not len(fit):
                fit = None
            elif len(fit) != len(y):
                self.mismatch['Fit values'] = True
            else:
                self.mismatch['Fit values'] = False
        if not any(self.mismatch.values()):
            self.timer.stop()
        else:
            if not self.timer.isActive():
                self.timer.start(1000)
            return

        self.clear()
        self.plot(x, y, pen=None, symbol="o")
        self.setTitle(title)
        if self.xlabel:
            self.setLabel('bottom', xlabel) # 26/01/08 gt
        if self.ylabel:
            self.setLabel('left', ylabel) # 26/01/08 gt
        if error is not None:
            # See https://github.com/pyqtgraph/pyqtgraph/issues/211
            if hasattr(error, "__len__") and not isinstance(error, np.ndarray):
                error = np.array(error)
            errbars = pyqtgraph.ErrorBarItem(
                x=np.array(x), y=np.array(y), height=error)
            self.addItem(errbars)
        if fit is not None:
            xi = np.argsort(x)
            self.plot(x[xi], fit[xi])

    def length_warning(self):
        self.clear()
        text = "⚠️ dataset lengths mismatch:\n"
        errors = ', '.join([k for k, v in self.mismatch.items() if v])
        text = ' '.join([errors, "should have the same length as Y values"])
        self.addItem(pyqtgraph.TextItem(text))

# 26/01/08 gt
class MyTitleApplet(TitleApplet):
    def __init__(self, PlotClass, xlabel=None, ylabel=None):
        super().__init__(PlotClass)
        self._custom_xlabel = xlabel
        self._custom_ylabel = ylabel
    
    def run(self):
        super().run() # creates self.plot
        # Attach labels to args
        self.plot.args.xlabel = self._custom_xlabel
        self.plot.args.ylabel = self._custom_ylabel


def main():
    # applet = TitleApplet(XYPlot) # 26/01/08 gt
    applet = MyTitleApplet(XYPlot, xlabel="xlabel", ylabel="ylabel") # 26/01/08 gt
    applet.add_dataset("y", "Y values")
    applet.add_dataset("x", "X values", required=False)
    #applet.add_argument("xlabel", type=str, default=None,
    #                help="Label for X axis") # 26/01/08 gt
    #applet.add_argument("ylabel", type=str, default=None,
    #                help="Label for Y axis") # 26/01/08 gt
    applet.add_dataset("error", "Error bars for each X value", required=False)
    applet.add_dataset("fit", "Fit values for each X value", required=False)
    applet.run()

if __name__ == "__main__":
    main()
