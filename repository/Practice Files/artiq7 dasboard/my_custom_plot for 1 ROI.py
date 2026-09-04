#!/usr/bin/env python3

import numpy as np
import PyQt5  # make sure pyqtgraph imports Qt5
from PyQt5.QtCore import QTimer
import pyqtgraph

from artiq.applets.simple import TitleApplet


class CustomXYPlot(pyqtgraph.PlotWidget):
    def __init__(self, args):
        pyqtgraph.PlotWidget.__init__(self)
        self.args = args
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.length_warning)
        self.mismatch = {
            'X values': False,
            'Error bars': False,
            'Fit values': False
        }

        

        self.showGrid(x=True, y=True, alpha=0.3)

        #(Legend)
        self.addLegend()

        
        self.setLabel('left', 'Average Count per Pixel')
        self.setLabel('bottom', 'Time', units='s')
        # --------------------------------------------------------

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
        self.setTitle(title)

        
        self.plot(
            x, y,
            pen=pyqtgraph.mkPen('b', width=1.5),  
            symbol="o",                            
            symbolBrush='b',                       
            symbolPen='b',                         
            symbolSize=9,                          
            name="ROI 16 Realtime Count"           
        )

        
        if error is not None:
            if hasattr(error, "__len__") and not isinstance(error, np.ndarray):
                error = np.array(error)
            
    
            red_pen = pyqtgraph.mkPen('b', width=1.5)
            errbars = pyqtgraph.ErrorBarItem(
                x=np.array(x), 
                y=np.array(y), 
                height=error, 
                pen=red_pen
            )
            self.addItem(errbars)


        if fit is not None:
            xi = np.argsort(x)
            self.plot(
                x[xi], fit[xi], 
                pen=pyqtgraph.mkPen('g', width=2), 
                name="Fit Curve"
            )

    def length_warning(self):
        self.clear()
        text = "⚠️ dataset lengths mismatch:\n"
        errors = ', '.join([k for k, v in self.mismatch.items() if v])
        text = ' '.join([errors, "should have the same length as Y values"])
        self.addItem(pyqtgraph.TextItem(text))


def main():
    applet = TitleApplet(CustomXYPlot)
    applet.add_dataset("y", "Y values")
    applet.add_dataset("x", "X values", required=False)
    applet.add_dataset("error", "Error bars for each X value", required=False)
    applet.add_dataset("fit", "Fit values for each X value", required=False)
    applet.run()


if __name__ == "__main__":
    main()