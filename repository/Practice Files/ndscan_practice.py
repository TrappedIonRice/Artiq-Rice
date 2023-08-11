from ndscan.experiment import *
import random
import time

class Readout(Fragment):
    def build_fragment(self):
        self.setattr_result("y_val")
        self.setattr_result("x_val")
        print("BUILDFRAG1")
    def assign_random_values(self, rng):
        for i in range(rng):
            self.y_val.push(random.random())
            self.x_val.push(random.random())
            time.sleep(0.1)
        print("ASSIGNING")

class ndPrac(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("readout", Readout)
        self.setattr_result("rng")
        print("BUILDFRAG2")
    def run_once(self):
        self.readout.assign_random_values(10)
        self.rng.push(4)
        print("RUNONCE")

MyPracticeScan = make_fragment_scan_exp(ndPrac)
#
class ndPracRunner(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("subScanPrac", ndPrac)
        setattr_subscan(self, "scan", self.subScanPrac, [(self.subScanPrac, "rng")], expose_analysis_results=True)
    def run_once(self):
        self.scan.run([(self.scan.rng,
                        LinearGenerator(0, 10,
                                        10, True))])

MyPracticeSubScan = make_fragment_scan_exp(ndPracRunner)



"""
class Readout(Fragment):
    def build_fragment(self):
        self.setattr_result("rand_y")
    def give_rand_pval(self):
        self.rand_y.push(random.randint(1,20))

class ndPrac(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("readout", Readout)
        self.setattr_param("x_val", IntParam, "X VALUE", 1, min = 0)
        self.setattr_result("x_val_res")
        #self.setattr_param("y_val", IntParam, "Y VALUE", 1, min = 0)
        #self.setattr_param("num_points", IntParam, "Number of points", 10)
        #self.setattr_param("more_points", IntParam, "More points", 10)

    def run_once(self):
        #self.num_points.push(random.randint(1,20))
        #self.more_points.push(random.randint(1,20))
        #self.x_val.get()
        #self.y_val.get()
        self.readout.give_rand_pval(self)
        self.x_val_res.push(self.x_val.get())
        time.sleep(0.1)

    def get_default_analyses(self):
        return [
            OnlineFit("point", data =
                      {
                          "x": self.x_val,
                          "y": self.readout.rand_y
                      }
                     ),
            OnlineFit("point2",
                      {
                          "x": self.x_val,
                          "y": self.readout.rand_y
                      }
                      )
        ]
MyPracticeScan = make_fragment_scan_exp(ndPrac)
"""