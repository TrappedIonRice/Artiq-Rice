from artiq.experiment import *

class AndorArtiq(EnvExperiment):

    def build(self):
        self.setattr_argument("dllFile",StringValue())

    # def prepare(self):
        # fill in code to link up Camera GUI

    def run(self):
        print(self.dllFile)