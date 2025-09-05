from artiq.experiment import *
import numpy as np
import serial
import time as timelib


class RFControl_Arduino(EnvExperiment):
    def build(self):
        # Please make sure to enter the right units.
        #self.setattr_device("core")
        self.lowerlim=-0.3 # 0.001V before
        self.upperlim = 9.9 # 9.9V before
        self.dataReprate= 100
        self.setattr_argument("ramp_rate", NumberValue(default=0.01,ndecimals=6, max=0.1, min=0.0001)) # default, 0.01V default ramp
        #self.setattr_argument("ramp_rate", NumberValue(default=0.005,ndecimals=6, max=0.05, min=-0.05)) # only beat note lock for RF

        self.setattr_argument("target_amplitude", NumberValue(default=0, min=self.lowerlim, max=self.upperlim, ndecimals=6))
        self.setattr_argument("time_step", NumberValue(default=100 * ms, unit="ms", min=0*ms, ndecimals=6))
        self.setattr_argument("num_points", NumberValue(default = 1000))
        self.amplitude=self.get_dataset("RFamp_Arduino")
        #self.setattr_device("scheduler")
        self.setattr_device("ccb")  # needed to make plots displaying the counts
        self.serialobj = serial.Serial(port="COM2",baudrate=9600)


    def prepare(self):
        # amplitude ramp plot
        self.set_dataset("RFamp_Arduino.Amplitude", np.full(int(self.num_points), float(np.nan)), broadcast=True, archive=True)
        self.set_dataset("RFamp_Arduino.Time", np.full(int(self.num_points), float(np.nan)), broadcast=True, archive=True)
        self.int_points = int(self.num_points)
        command = "${artiq_applet}plot_xy RFamp_Arduino.Amplitude --x RFamp_Arduino.Time"
        self.ccb.issue("create_applet", "RF setpoint Ramp", command)

    #@rpc(flags={"async"})
    def ArduinoWrite(self, V):
        vbit=int((V/13.89)*(2**18-1)+70635)
        command="V1 "+str(vbit)+'\n'
        self.serialobj.write(bytes(command,'utf-8'))
        self.serialobj.reset_input_buffer()

    def krun(self):
        amp = self.amplitude
        idx = 0
        time = 0.0
        starttime = timelib.time()

        if self.target_amplitude > amp:
            while amp < self.target_amplitude:

                ampplus=(amp + self.ramp_rate)
                self.ArduinoWrite(ampplus)
                timelib.sleep(1*ms)
                self.set_dataset("RFamp_Arduino", ampplus, broadcast=True, persist=True)

                #for multiple points
                if (idx % self.dataReprate == 0):
                   self.changeDataset(ampplus, time,self.dataReprate,idx)
                amp=ampplus
                timelib.sleep(self.time_step)
                time += (self.time_step)# * 1000
                idx +=1
                timelib.sleep(2 * ms)
                print("{0:.3f}s : RF {1:.3f}".format(timelib.time() - starttime,amp))


        else:

            while amp > self.target_amplitude:

                ampminus=(amp - self.ramp_rate)
                self.ArduinoWrite(ampminus)
                timelib.sleep(1 * ms)
                self.set_dataset("RFamp_Arduino", ampminus, broadcast=True, persist=True)

                # for multiple points
                if(idx % self.dataReprate == 0):
                   self.changeDataset(ampminus, time, self.dataReprate,idx)

                # for testing a few points
                amp=ampminus
                timelib.sleep(self.time_step)
                time += self.time_step# * 1000
                idx += 1
                timelib.sleep(2 * ms)
                print("{0:.3f}s : RF {1:.3f}".format(timelib.time() - starttime,amp))

        print("Ramp complete")
        self.ArduinoWrite(self.target_amplitude)
        timelib.sleep(2 * ms)
        self.set_dataset("RFamp_Arduino",self.target_amplitude, broadcast=True, persist=True )
        timelib.sleep(2 * ms)
        #self.serialobj.close()
        '''
        '''
    #@kernel
    def changeDataset(self,amp,tm,mod,idx):
        self.mutate_dataset("RFamp_Arduino.Amplitude", idx // mod, amp)
        self.mutate_dataset("RFamp_Arduino.Time", idx // mod, tm)

    # @rpc(flags={"async"})
    # def check_termination(self):
    #     try:
    #         if self.scheduler.check_pause():
    #             self.core.comm.close()
    #             self.scheduler.pause()
    #     except TerminationRequested:
    #         print("Terminated gracefully")
    #         return

    #@kernel
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