#!/usr/bin/env python3

import numpy as np
import PyQt5  # make sure pyqtgraph imports Qt5
import pyqtgraph

from artiq.applets.simple import TitleApplet


class CustomMultiColorXYPlot(pyqtgraph.PlotWidget):
    def __init__(self, args):
        pyqtgraph.PlotWidget.__init__(self)
        self.args = args

    
        self.showGrid(x=True, y=True, alpha=0.3)
        self.addLegend()
        self.setLabel('left', 'Average Count per Pixel')
        self.setLabel('bottom', 'Time', units='s')

    def extract_series(self, x_arg, y_arg, err_arg, color):

        y_name = getattr(self.args, y_arg, None)
        if not y_name or y_name not in self.current_data:
            return []

        y = self.current_data[y_name][1]
        if y is None or len(y) == 0:
            return []

        x_name = getattr(self.args, x_arg, None)
        x = self.current_data.get(x_name, (False, None))[1] if x_name else None
        if x is None or len(x) != len(y):
            x = np.arange(len(y))

        err_name = getattr(self.args, err_arg, None)
        error = self.current_data.get(err_name, (False, None))[1] if err_name else None

        pts = []
        for i in range(len(y)):
            e = error[i] if (error is not None and i < len(error)) else None
            pts.append((x[i], y[i], e, color))
        return pts

    def data_changed(self, data, mods, title):
        self.current_data = data
        self.clear()
        self.setTitle(title)
        color_blue = (0, 0, 255)
        color_red = (255, 0, 0)
        color_purple = (160, 32, 240)

        
        pts_blue = self.extract_series("blue_x", "blue_y", "blue_err", color_blue)
        pts_red = self.extract_series("red_x", "red_y", "red_err", color_red)
        pts_purple = self.extract_series("purple_x", "purple_y", "purple_err", color_purple)

        
        all_points = pts_blue + pts_red + pts_purple
        if not all_points:
            return

        all_points.sort(key=lambda pt: pt[0])

        
        self.plot([], [], pen=pyqtgraph.mkPen(color_blue, width=1.5), symbol="o",
                  symbolBrush=color_blue, symbolPen=color_blue, symbolSize=8, name="ROI 15 > 50%")
        self.plot([], [], pen=pyqtgraph.mkPen(color_red, width=1.5), symbol="o",
                  symbolBrush=color_red, symbolPen=color_red, symbolSize=8, name="ROI 14 > 50%")
        self.plot([], [], pen=pyqtgraph.mkPen(color_purple, width=1.5), symbol="o",
                  symbolBrush=color_purple, symbolPen=color_purple, symbolSize=8, name="Equal (50% / 50%)")

        
        for i in range(len(all_points) - 1):
            p_curr = all_points[i]
            p_next = all_points[i + 1]
            next_color = p_next[3]  

            self.plot(
                [p_curr[0], p_next[0]],
                [p_curr[1], p_next[1]],
                pen=pyqtgraph.mkPen(next_color, width=1.5)
            )

        
        for pt in all_points:
            x_val, y_val, err_val, col = pt

            self.plot(
                [x_val], [y_val],
                symbol="o",
                symbolBrush=col,
                symbolPen=col,
                symbolSize=8
            )

            if err_val is not None:
                errbar = pyqtgraph.ErrorBarItem(
                    x=np.array([x_val]),
                    y=np.array([y_val]),
                    height=np.array([err_val]),
                    pen=pyqtgraph.mkPen(col, width=1.5)
                )
                self.addItem(errbar)


def main():
    applet = TitleApplet(CustomMultiColorXYPlot)

    
    applet.add_dataset("y", "Default Y (Optional)", required=False)
    applet.add_dataset("x", "Default X (Optional)", required=False)

    
    applet.add_dataset("blue_y", "Y values (Blue)", required=False)
    applet.add_dataset("blue_x", "X values (Blue)", required=False)
    applet.add_dataset("blue_err", "Error bars (Blue)", required=False)

    
    applet.add_dataset("red_y", "Y values (Red)", required=False)
    applet.add_dataset("red_x", "X values (Red)", required=False)
    applet.add_dataset("red_err", "Error bars (Red)", required=False)

    
    applet.add_dataset("purple_y", "Y values (Purple)", required=False)
    applet.add_dataset("purple_x", "X values (Purple)", required=False)
    applet.add_dataset("purple_err", "Error bars (Purple)", required=False)

    applet.run()


if __name__ == "__main__":
    main()