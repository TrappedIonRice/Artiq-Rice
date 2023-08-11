from ndscan.experiment import *
import artiq.language as aq
from artiq.language import kernel

class MyExp(aq.EnvExperiment):
    def build(self):
