from ndscan.experiment import *

class getDataset(ExpFragment):
    def build_fragment(self):
        print("BUILT")
    def run_once(self):
        print(self.get_dataset('freq1'))


GetDataset = make_fragment_scan_exp(getDataset)


