from artiq.experiment import *
import numpy as np
import serial
import time as timelib


class ULE369_control(EnvExperiment):
    def build(self):

        self.setattr_device("core")
        self.setattr_device("urukul2_ch3")
        # Please make sure to enter the right units.
        # self.setattr_device("core")
        self.lowerlim = 90*MHz  # 0.001V before
        self.upperlim = 135*MHz  # 9.9V before
        #self.dataReprate = 100
        self.setattr_argument("ramp_rate", NumberValue(default=1*MHz, ndecimals=6, max=5*MHz, unit="MHz",
                                                       min=0.0001*MHz))  # default, freq in MHz per step
        # self.setattr_argument("ramp_rate", NumberValue(default=0.005,ndecimals=6, max=0.05, min=-0.05)) # only beat note lock for RF

        self.setattr_argument("target_frequency",
                              NumberValue(default=100*MHz, min=self.lowerlim, max=self.upperlim,unit="MHz", ndecimals=6))
        self.setattr_argument("time_step", NumberValue(default=100 * ms, unit="ms", min=0 * ms, ndecimals=6))
        #self.setattr_argument("num_points", NumberValue(default=1000))
        self.frequency = self.get_dataset("369_ULE.Frequency") # Hz
        # self.setattr_device("scheduler")
        #self.setattr_device("ccb")  # needed to make plots displaying the counts
        #self.serialobj = serial.Serial(port="COM2", baudrate=9600)

    def prepare(self):
        # frequency ramp plot
        # self.set_dataset("RFamp_Arduino.frequency", np.full(int(self.num_points), float(np.nan)), broadcast=True,
        #                  archive=True)
        # self.set_dataset("RFamp_Arduino.Time", np.full(int(self.num_points), float(np.nan)), broadcast=True,
        #                  archive=True)
        # self.int_points = int(self.num_points)
        # command = "${artiq_applet}plot_xy RFamp_Arduino.frequency --x RFamp_Arduino.Time"
        # self.ccb.issue("create_applet", "RF setpoint Ramp", command)


        pass

    # @rpc(flags={"async"})
    # def ArduinoWrite(self, V):
    #     vbit = int((V / 13.89) * (2 ** 18 - 1) + 70635)
    #     command = "V1 " + str(vbit) + '\n'
    #     self.serialobj.write(bytes(command, 'utf-8'))
    #     self.serialobj.reset_input_buffer()

    @kernel
    def set_frequency(self, freq_val): # assumes that the ULE urukul is already on

        #self.core.break_realtime()
        #delay(100*ms)
        self.urukul2_ch3.set(frequency=freq_val)
        #delay(10*ms)

    @kernel
    def init_core(self):
        self.core.reset()

    @rpc
    def print_result(self,tm, freq):
        print("{0:.3f}s: ULE369 freq {1:.3f}".format(tm, freq/MHz))

    @kernel
    def krun(self):
        self.init_core()
        freq = self.frequency
        idx = 0
        time = 0.0
        #starttime = self.core.mu_to_seconds(now_mu())

        if self.target_frequency > freq:
            while freq < self.target_frequency:

                freqplus = (freq + self.ramp_rate)
                #self.ArduinoWrite(freqplus)

                self.set_frequency(freqplus)
                delay(1 * ms)
                self.set_dataset("369_ULE.Frequency", freqplus, broadcast=True, persist=True)

                # for multiple points
                # if (idx % self.dataReprate == 0):
                #     self.changeDataset(ampplus, time, self.dataReprate, idx)
                freq = freqplus
                delay(self.time_step)
                time += (self.time_step)  # * 1000
                idx += 1
                delay(2*ms)
                #timelib.sleep(2 * ms)
                #self.print_result(time,freq)
                #print("{0:.3f}s : ULE369 freq {1:.3f}".format(timelib.time() - starttime, freq))


        else:

            while freq > self.target_frequency:

                freqminus = (freq - self.ramp_rate)
                #self.ArduinoWrite(freqminus)
                self.set_frequency(freqminus)
                delay(1 * ms)
                self.set_dataset("369_ULE.Frequency", freqminus, broadcast=True, persist=True)

                # for multiple points
                # if (idx % self.dataReprate == 0):
                #     self.changeDataset(ampminus, time, self.dataReprate, idx)

                # for testing a few points
                freq = freqminus
                delay(self.time_step)
                time += self.time_step  # * 1000
                idx += 1
                delay(2 * ms)
                # print("{0:.3f}s : RF {1:.3f}".format(timelib.time() - starttime, freq))
                #self.print_result(time, freq)

        # self.ArduinoWrite(self.target_frequency)
        self.set_frequency(self.target_frequency)
        delay(2 * ms)
        self.set_dataset("369_ULE.Frequency", self.target_frequency, broadcast=True, persist=True)
        delay(2 * ms)

        print("Ramp complete")
        # self.serialobj.close()
        '''
        '''

    # @kernel
    # def changeDataset(self, amp, tm, mod, idx):
    #     self.mutate_dataset("RFamp_Arduino.frequency", idx // mod, amp)
    #     self.mutate_dataset("RFamp_Arduino.Time", idx // mod, tm)

    # @rpc(flags={"async"})
    # def check_termination(self):
    #     try:
    #         if self.scheduler.check_pause():
    #             self.core.comm.close()
    #             self.scheduler.pause()
    #     except TerminationRequested:
    #         print("Terminated gracefully")
    #         return

    # @kernel
    def run(self):
        self.krun()


'''



    #self.serialobj.close()
serialobj=serial.Serial("COM3",9600, timeout=5)
timelib.sleep(3)
#3 very important otherwise
# serialobj.port="COM3"
# serialobj.baudrate=9600
# serialobj.timeout=0.5
# serialobj.open()
try:
    V=0.5
    vbit=(V/13.89)*(2**18-1)+70635
    command='V1 {0}\n'.format(vbit)
    print(command)
    #serialobj.close()
    #print(serialobj.is_open)
    serialobj.write(command.encode())
    #serialobj.reset_input_buffer()
    #serialobj.close()

    V=0.8
    vbit=(V/13.89)*(2**18-1)+70635
    command='V1 {0}\n'.format(vbit)
    #print(command)
    #command="V1 75000\n"
    #serialobj.close()
    #print(serialobj.is_open)
    serialobj.write(command.encode())


except:
    pass

serialobj.close()

'''