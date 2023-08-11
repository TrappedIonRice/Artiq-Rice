from ndscan.experiment import *

class TestDataset(EnvExperiment):
    def run(self):
        print(self.get_dataset("temp_dataset"))
        num = 5*s
        print(num)
        num = 5*MHz
        print(num)