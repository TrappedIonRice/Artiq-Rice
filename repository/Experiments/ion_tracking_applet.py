#!/usr/bin/env python3
"""
Ion tracking applet (ARTIQ dashboard): one point per detection of the tracking events (ion_tracking_mixin.py).

  points      ion offset from the setpoint (0 = on setpoint), error bars = standard error of the detection
  colour      green  = in band (the event ends, the scan point(s) run)
              blue   = detection without a decision: setpoint collection / confirming second detection
              orange = out of band, correction applied after this detection
              red    = out of band and given up (limit reached / lost) or measure-only
  grey band   +-deadband of that detection (it widens when the detection is noisy)
  red steps   EndcapX correction in force when the detection was taken
Install (once) so that it can be launched like the stock applets, `python -m ion_tracking_applet`:
    copy this file into the site-packages folder of the ARTIQ environment, found with
        python -c "import artiq, os; print(os.path.dirname(os.path.dirname(artiq.__file__)))"
    check in that environment:   python -m ion_tracking_applet --help
    then set CUSTOM_APPLET = True near the top of ion_tracking_mixin.py (it then starts `${python} -m ion_tracking_applet ...`).
26/10/02 gt
"""
import numpy as np
import pyqtgraph
from PyQt5 import QtGui
from artiq.applets.simple import TitleApplet

COL = {"in": (27, 158, 119), "wait": (31, 120, 180), "fix": (230, 120, 20), "bad": (200, 30, 50)}


class TrackPlot(pyqtgraph.PlotWidget):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.setBackground(None)
        self.showGrid(x=True, y=True, alpha=0.25)
        self.setLabel("bottom", "time [s]")
        self.setLabel("left", "ion offset from setpoint [%s]" % args.unit)
        self.addLine(y=0, pen=pyqtgraph.mkPen((120, 120, 120), width=1))
        self.band_hi = self.plot(pen=pyqtgraph.mkPen((140, 140, 140), width=1, style=pyqtgraph.QtCore.Qt.DashLine))
        self.band_lo = self.plot(pen=pyqtgraph.mkPen((140, 140, 140), width=1, style=pyqtgraph.QtCore.Qt.DashLine))
        self.corr = self.plot(pen=pyqtgraph.mkPen((200, 30, 50), width=2))
        self.err = pyqtgraph.ErrorBarItem(beam=0.0, pen=pyqtgraph.mkPen((90, 90, 90)))
        self.addItem(self.err)
        self.pts = pyqtgraph.ScatterPlotItem(size=9, pen=pyqtgraph.mkPen(None))
        self.addItem(self.pts)
        leg = self.addLegend(offset=(-10, 10))
        for name, key in (("in band", "in"), ("no decision (collect / confirm)", "wait"),
                          ("out of band: corrected", "fix"), ("out of band: given up / measure only", "bad")):
            leg.addItem(pyqtgraph.ScatterPlotItem(size=9, pen=pyqtgraph.mkPen(None), brush=pyqtgraph.mkBrush(*COL[key])), name)
        leg.addItem(self.corr, "correction in force")
        leg.addItem(self.band_hi, "deadband")

    def _get(self, data, key):
        if not key:
            return None
        v = data.get(key, (False, None))[1]
        return None if v is None else np.asarray(v, dtype=float)

    def data_changed(self, data, mods, title):
        a = self.args
        arrs = [self._get(data, getattr(a, k)) for k in ("t", "y", "err", "v", "band", "status", "inband")]
        t, y = arrs[0], arrs[1]
        if t is None or y is None:
            return
        n = min(len(x) for x in arrs if x is not None)        # the datasets are appended one after the other
        t, y, err, v, band, status, inband = [None if x is None else x[:n] for x in arrs]
        if n == 0:
            return
        key = np.where(status == 1, "wait", np.where(status == 2, "fix", np.where(status == 3, "bad",
                       np.where(inband > 0.5, "in", "bad")))) if status is not None else np.array(["in"] * n)
        brushes = [pyqtgraph.mkBrush(*COL[k]) for k in key]
        self.pts.setData(x=t, y=y, brush=brushes)
        if err is not None:
            ok = np.isfinite(err) & np.isfinite(y)
            self.err.setData(x=t[ok], y=y[ok], height=2 * err[ok])
        if v is not None:                                       # steps: the value holds until the next detection
            self.corr.setData(np.repeat(t, 2)[1:], np.repeat(v, 2)[:-1])
        if band is not None:
            self.band_hi.setData(t, band, connect="finite")
            self.band_lo.setData(t, -band, connect="finite")


def main():
    applet = TitleApplet(TrackPlot)
    applet.argparser.add_argument("--unit", default="mV")
    for name, hlp, req in (("t", "time [s]", True), ("y", "offset from setpoint", True), ("err", "its standard error", False),
                           ("v", "correction in force", False), ("band", "deadband", False),
                           ("status", "decision after the detection", False), ("inband", "1 = in band", False)):
        applet.add_dataset(name, hlp, required=req)
    applet.run()


if __name__ == "__main__":
    main()