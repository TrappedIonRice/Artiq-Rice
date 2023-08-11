from ndscan.experiment import *
from statistics import mean
import numpy as np
from math import sin

class runScan(Fragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")  # Necessary for clock sync
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("ttl0")
        self.setattr_result("result")

    @kernel
    def ON(self, pulse_time, freq, channel, const_time, num_repeat, detection_time, inpFreq):

        """Pulses urukul ch0, ch1, ch2, then counts num rising edges (cycles) from ttl0 for x us. Pushes mean
        rising edges for a given num_repeat to result channel"""

        self.initializeUrukul()
        sum_rising_edges = 0

        for i in range(num_repeat):
            for channel_num in range(3):
                if channel == channel_num:
                    self.pulseScanVal(channel, pulse_time, inpFreq)
                else:
                    self.pulseUrukul(channel_num, const_time, freq)
            gate_end_mu = self.ttl0.gate_rising(detection_time)
            delay(500*us)
            sum_rising_edges += self.ttl0.count(gate_end_mu)

        mean_rising_edges = (num_repeat)
        self.result.push(mean_rising_edges)

    @kernel
    def initializeUrukul(self):
        self.core.reset()
        delay(1 * ms)
        self.urukul0_cpld.init()
        self.urukul0_ch0.init()
        self.urukul0_ch1.init()
        self.urukul0_ch2.init()
        self.ttl0.input()
        delay(1 * ms)

    @kernel
    def pulseUrukul(self, numChan, const_time, freq):

        """Pulses either urukul ch0, 1, or 2 based on a dataset-stored channel number, time, and frequency"""

        if numChan == 0:
            self.urukul0_ch0.sw.on()
            self.urukul0_ch0.set(freq)
            delay(const_time[numChan])
            self.urukul0_ch0.sw.off()
        elif numChan == 1:
            self.urukul0_ch1.sw.on()
            self.urukul0_ch1.set(freq)
            delay(const_time[numChan])
            self.urukul0_ch1.sw.off()
        else:
            self.urukul0_ch2.sw.on()
            self.urukul0_ch2.set(freq)
            delay(const_time[numChan])
            self.urukul0_ch2.sw.off()

    @kernel
    def pulseScanVal(self, numChan, time, freq):

        """Pulses urukul ch0, 1, or 2 based on user inputted channel number, time and frequency"""

        if numChan == 0:
            self.urukul0_ch0.sw.on()
            self.urukul0_ch0.set(freq)
            delay(time)
            self.urukul0_ch0.sw.off()
        elif numChan == 1:
            self.urukul0_ch1.sw.on()
            self.urukul0_ch1.set(freq)
            delay(time)
            self.urukul0_ch1.sw.off()
        else:
            self.urukul0_ch2.sw.on()
            self.urukul0_ch2.set(freq)
            delay(time)
            self.urukul0_ch2.sw.off()




class executeScan(ExpFragment):

    """ScanExperiment1"""

    def build_fragment(self):
        self.setattr_param("channel", IntParam, "CHOOSE CHANNEL TO VARY TIME (0, 1, OR 2)", 0)
        self.setattr_param("time", FloatParam, "SET PULSE TIME (US)", 0.0)
        #self.setattr_param("inputFreq", FloatParam, "SET CHANNEL FREQUENCY (MHz)", 0.0)
        #self.setattr_param("inputAmp", FloatParam, "SET CHANNEL AMPLITUDE (FROM 0-1)", 0.0)
        self.setattr_fragment("run", runScan) #Assigns runScan fragment and its attributes/functions to this fragment

    def run_once(self):

        """Retrieves constant values from dataset, then runs experiment"""

        freq = self.get_dataset("freq1") * MHz
        scanFreq = 1 * MHz #self.inputFreq.get() * MHz
        t1 = self.get_dataset("time1") * us
        t2 = self.get_dataset("time2") * us
        t3 = self.get_dataset("time3") * us
        num_repeat = self.get_dataset("repetitions")
        detection_time = self.get_dataset("detection_time")
        const_time = [t1, t2, t3]
        pulse_time = self.time.get() * us

        self.run.ON(pulse_time, freq, self.channel.get(), const_time, num_repeat, detection_time, scanFreq,) #calls ON function in runScan fragment

        print("SCAN COMPLETE")

ScanForTime = make_fragment_scan_exp(executeScan)

