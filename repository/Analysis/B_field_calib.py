import numpy as np
import matplotlib.pyplot as plt

# Define your data points
x = np.array([18.5,18,19,19.5,20,20.5

])
y = np.array([17,22,13.6,12.8, 13.6,  16.8
])

# Perform a quadratic fit (2nd-degree polynomial)
coefficients = np.polyfit(x, y, 2)

# Get the fitted polynomial function
polynomial = np.poly1d(coefficients)

# Generate x values for plotting the fitted curve
x_fit = np.linspace(min(x), max(x), 100)
y_fit = polynomial(x_fit)

# Plot the original data points and the quadratic fit
plt.scatter(x, y, color='red', label='Data Points')
plt.plot(x_fit, y_fit, label='Quadratic Fit', color='blue')


# Add labels and legend
plt.xlabel('x')
plt.ylabel('y')
plt.title('Quadratic Fit')
plt.legend()

# Display the plot
plt.show()

# Print the coefficients of the quadratic fit
print("Quadratic fit coefficients: a = {}, b = {}, c = {}".format(coefficients[0], coefficients[1], coefficients[2]))









'''

class repetitionScan(Fragment):
    def build_fragment(self):
        ...
        # declaring all devices being used
    @kernel    
    def scanON(self, <arguments>):
        #custom function that takes arguments from paramScan and executes N repetitions to gather statistics for the data.
        #
        ...
    
    
    
class paramScan(ExpFragment):
    .....
    







'''
'''
while (i < num_repeat):
    # delay(30 * us)  # This delay will exist between repetitions

    # self.ttl5.on()
    # if doppler_time> 0.0:

    self.urukul0_ch1.set_att(0 * dB)
    self.urukul0_ch2.set_att(0 * dB)
    self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
    self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
    self.urukul0_ch2.sw.on()
    self.urukul1_ch3.sw.on()
    delay(doppler_time)
    # self.ttl.gate_rising(doppler_time)

    # self.urukul0_ch2.set_att(30 * dB)
    self.urukul0_ch1.sw.off()
    self.urukul0_ch2.sw.off()
    self.urukul1_ch3.sw.off()
    # self.ttl5.off()

    # 2nd doppler cooling stage
    # self.urukul0_ch1.set(frequency=doppler_freq+10*MHz, amplitude=0.8, phase_mode=2)
    # self.urukul0_ch1.sw.on()
    # self.urukul0_ch2.sw.on()
    # delay(0.5*ms)
    # # self.ttl.gate_rising(doppler_time)
    # # self.urukul0_ch2.set_att(30 * dB)
    # self.urukul0_ch1.sw.off()
    # self.urukul0_ch2.sw.off()

    # self.urukul0_ch1.set_att(30 * dB)
    # delay(0.05*ms)
    # y = self.ttl.fetch_count()
    # self.sum_rising_edges_cooling = self.sum_rising_edges_cooling + y
    # delay(0.05*ms)

    # delay(5.5*ms)
    # Pulsed SBC

    self.urukul2_ch0.set(frequency=SBCFrequency435_1, amplitude=SBCAmplitude435_1, phase_mode=2)
    # self.urukul2_ch0.set(frequency=SBCFrequency435_2, amplitude=SBCAmplitude435_2, phase_mode=2)

    # self.urukul0_ch1.set(frequency=freq_935, amplitude=SBCAmplitude935, phase_mode=2)
    self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
    self.urukul1_ch1.set_att(0 * dB)
    self.urukul2_ch0.set_att(0 * dB)
    # delay(2.35*ms)
    # Outer 2
    if SBCTime > 0:
        for cyc in range(10):
            # self.ttl5.on()
            self.urukul2_ch0.sw.on()
            self.ttl6.on()
            delay(0.01 * ms)
            self.urukul2_ch0.sw.off()
            self.ttl6.off()
            # self.ttl5.off()
            #        self.urukul1_ch0.sw.on()
            #        delay(SBCTime)
            #        self.urukul1_ch0.sw.off()
            #       self.urukul0_ch2.sw.on()
            self.urukul1_ch1.sw.on()
            delay(0.03 * ms)
            #        self.urukul0_ch2.sw.off()
            self.urukul1_ch1.sw.off()
        for cyc in range(30):
            self.urukul2_ch0.sw.on()
            self.ttl6.on()
            # self.ttl5.on()
            delay(0.025 * ms)
            self.urukul2_ch0.sw.off()
            self.ttl6.off()
            # self.ttl5.off()
            #        self.urukul1_ch0.sw.on()
            #        delay(SBCTime)
            #        self.urukul1_ch0.sw.off()
            #       self.urukul0_ch2.sw.on()
            self.urukul1_ch1.sw.on()
            delay(0.03 * ms)
            #        self.urukul0_ch2.sw.off()
            self.urukul1_ch1.sw.off()
        # for cyc in range(20):
        #     self.urukul2_ch0.sw.on()
        #     self.ttl6.on()
        #     delay(0.002 * ms)
        #     self.urukul2_ch0.sw.off()
        #     self.ttl6.off()
        #     #        self.urukul1_ch0.sw.on()
        #     #        delay(SBCTime)
        #     #        self.urukul1_ch0.sw.off()
        #     #       self.urukul0_ch2.sw.on()
        #     self.urukul1_ch1.sw.on()
        #     delay(0.03 * ms)
        #     #        self.urukul0_ch2.sw.off()
        #     self.urukul1_ch1.sw.off()
        #
        # for cyc in range(40):
        #     self.urukul2_ch0.sw.on()
        #     self.ttl6.on()
        #     delay(0.12 * ms)
        #     self.urukul2_ch0.sw.off()
        #     self.ttl6.off()
        #     #        self.urukul1_ch0.sw.on()
        #     #        delay(SBCTime)
        #     #        self.urukul1_ch0.sw.off()
        #     #       self.urukul0_ch2.sw.on()
        #     self.urukul1_ch1.sw.on()
        #     delay(0.03 * ms)
        #     #        self.urukul0_ch2.sw.off()
        #     self.urukul1_ch1.sw.off()

        # CSBC Raman
        # self.urukul2_ch0.sw.on()
        # self.ttl6.on()
        # self.urukul1_ch1.sw.on()
        # delay(SBCTime)
        # self.urukul2_ch0.sw.off()
        # self.ttl6.off()
        # self.urukul1_ch1.sw.off()

    # Outer 1
    # self.urukul2_ch0.set(frequency=SBCFrequency435_2, amplitude=SBCAmplitude435_2, phase_mode=2)
    # for cyc in range(10):
    #     self.urukul2_ch0.sw.on()
    #     self.ttl6.on()
    #     delay(0.1 * ms)
    #     self.urukul2_ch0.sw.off()
    #     self.ttl6.off()
    #     #        self.urukul1_ch0.sw.on()
    #     #        delay(SBCTime)
    #     #        self.urukul1_ch0.sw.off()
    #     #       self.urukul0_ch2.sw.on()
    #     self.urukul1_ch1.sw.on()
    #     delay(0.03 * ms)
    #     #        self.urukul0_ch2.sw.off()
    #     self.urukul1_ch1.sw.off()

    # # Inner
    # self.urukul2_ch0.set(frequency=SBCFrequency435_2, amplitude=SBCAmplitude435_2, phase_mode=2)
    #
    # #if SBCTime > 0:
    # for cyc in range(40):
    #     self.urukul2_ch0.sw.on()
    #     self.ttl6.on()
    #     delay(SBCTime)
    #     self.urukul2_ch0.sw.off()
    #     self.ttl6.off()
    #     #        self.urukul1_ch0.sw.on()
    #     #        delay(SBCTime)
    #     #        self.urukul1_ch0.sw.off()
    #     #       self.urukul0_ch2.sw.on()
    #     self.urukul1_ch1.sw.on()
    #     delay(0.05 * ms)
    #     #        self.urukul0_ch2.sw.off()
    #     self.urukul1_ch1.sw.off()

    # OP state prep with 935

    # self.urukul0_ch2.set_att(0 * dB)
    if OP_time > 0.01 * us:
        self.urukul1_ch1.set(frequency=OP_freq, amplitude=OP_amp, phase_mode=2)
        self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
        self.urukul1_ch1.set_att(0 * dB)
        self.urukul0_ch2.set_att(0 * dB)
        # self.ttl5.on()
        self.urukul1_ch1.sw.on()
        # self.urukul1_ch3.sw.on()
        # self.urukul0_ch2.sw.on()
        delay(OP_time)
        delay_mu(1)
        self.urukul1_ch1.sw.off()
        # self.urukul1_ch3.sw.off()
        # self.urukul0_ch2.sw.off()
        # self.ttl5.off()
        # self.urukul0_ch2.set_att(30 * dB)
        # delay(5 * us)
        # delay(100*us) # DO Not remove or else OP scan will not execute properly.
        # self.urukul1_ch1.sw.on()
        # self.urukul0_ch2.sw.on()

    # self.urukul1_ch1.sw.off()

    # Using channel 0 of urukul 0
    # Ramsey first pi 435 pulse

    # delay(-1*us) # important for syncing. Must be before setting up the DDS config or else there is some gradual ampltiude ramp of 435 DDS

    # MW ramsey

    # # self.urukul1_ch2.set_att(0 * dB)
    # self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
    # #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
    # self.urukul1_ch2.set_att(0 * dB)
    # self.urukul1_ch2.sw.on()
    # delay(PiBy2Time435_1)
    # delay_mu(1)
    # # self.urukul1_ch2.set_att(30 * dB)
    # self.urukul1_ch2.sw.off()
    # #delay(0.05*ms)
    #
    # # # wait time
    # delay(wait_time)
    # delay_mu(1)
    #
    # # wait time with 355 on
    # #
    # # self.urukul1_ch3.sw.on()
    # # self.urukul2_ch0.sw.on() # Raman 1
    # # #self.ttl6.on() # Raman 2
    # # delay(wait_time)
    # # delay_mu(1)
    # # self.urukul2_ch0.sw.off() # Raman 1
    # # #self.ttl6.off() # Raman 2
    # # self.urukul1_ch3.sw.off()
    #
    #
    #
    # # Ramsey second pi 435 pulse
    #
    # self.urukul1_ch2.set(frequency=RamseyFrequency435, amplitude=RamseyAmplitude435, phase_mode=2)
    # #self.urukul1_ch2.set(frequency=MW_freq, amplitude=RamseyAmplitude435, phase_mode=2)
    # # self.urukul1_ch2.set_att(0 * dB)
    # self.urukul1_ch2.sw.on()
    # self.urukul1_ch2.set_att(0 * dB)
    # delay(PiBy2Time435_2)
    # delay_mu(1)
    # # self.urukul1_ch2.set_att(30 * dB)
    # self.urukul1_ch2.sw.off()
    #
    # #delay(0.05*ms)

    # 435 interaction

    # self.urukul0_ch2.sw.on() # 935 repumper
    # if choice435==1:
    #     self.urukul0_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
    #     self.urukul0_ch0.sw.on()
    #     delay(Time435)
    #     self.urukul0_ch0.sw.off()
    # elif choice435==2:
    #     #delay(10*us) # a delay because suspectected pulse sequence was not running properly. Have to revisit it.
    #     self.urukul1_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
    #     self.urukul1_ch0.sw.on()
    #     delay(Time435)
    #     self.urukul1_ch0.sw.off()
    # self.urukul0_ch2.sw.off() # 935 repumper

    # For dual drive

    # self.urukul0_ch0.set(frequency=Frequency435, amplitude=Amplitude435, phase_mode=2)
    # self.urukul1_ch0.set(frequency=prepfreq435, amplitude=Amplitude435, phase_mode=2)
    # self.urukul0_ch0.sw.on()
    # self.urukul1_ch0.sw.on()
    # delay(Time435)
    # self.urukul0_ch0.sw.off()
    # self.urukul1_ch0.sw.off()

    # delay(50 * us)

    # # 935 PUMPING INTERACTION
    # delay(10 * us)
    # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
    # self.urukul0_ch2.sw.on()
    # delay(ClearoutTime935)
    # self.urukul0_ch2.sw.off()
    # delay(10 * us)

    # MW interaction
    if MW_time > 0.01 * us:
        self.urukul1_ch2.set(frequency=MW_freq, amplitude=MW_amp, phase_mode=2)
        # self.urukul1_ch2.set_att(0 * dB)
        self.urukul1_ch2.set_att(0 * dB)
        self.urukul1_ch2.sw.on()
        delay(MW_time)
        # delay(-0.01*us)
        delay_mu(1)
        # self.urukul1_ch2.set_att(30 * dB)
        self.urukul1_ch2.sw.off()

    # 355 Turning on global switch
    # self.urukul1_ch3.set_att(0 * dB)
    # self.urukul1_ch3.sw.on()
    # delay_mu(1)
    # delay(10*us) # essential or else underflow
    # self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
    # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
    # delay(0.1 * ms)
    # self.ttl5.on()

    # Raman 1 + 2
    # delay(1*ms)
    if Raman_time > 0.01 * us:
        self.urukul2_ch0.set(frequency=FrequencyRaman1, amplitude=AmplitudeRaman1, phase_mode=2)
        # self.urukul2_ch1.set(frequency=FrequencyRaman2, amplitude=AmplitudeRaman2, phase_mode=2)
        self.urukul2_ch0.set_att(0 * dB)
        self.ttl5.on()
        self.urukul1_ch3.sw.on()
        self.urukul2_ch0.sw.on()
        self.ttl6.on()
        # self.urukul2_ch1.sw.on()
        delay(0.25 * us)  # AOM delay
        delay(Raman_time)
        # delay_mu(1)
        # self.urukul2_ch0.set_att(30 * dB)
        self.urukul2_ch0.sw.off()
        self.ttl6.off()
        self.ttl5.off()
        self.urukul1_ch3.sw.off()
        # self.urukul2_ch1.sw.off()
        # self.urukul2_ch0.set_att(30 * dB)
        # self.urukul1_ch3.sw.off()
    # self.ttl5.off()
    # delay(0.05*ms)

    # 935 clearout
    # # delay(10 * us)
    # self.urukul0_ch2.set(frequency=freq_935, amplitude=ClearoutPower935, phase_mode=2)
    # self.urukul0_ch2.sw.on()
    # delay(ClearoutTime935)
    # self.urukul0_ch2.sw.off()
    # delay(10 * us)

    # self.urukul0_ch3.sw.on()
    # #delay(200*us)
    # delay(wait_time)
    # self.urukul0_ch3.sw.off()
    # # # self.urukul0_ch2.sw.off()
    # delay(wait_time)

    # delay(500*ms)

    # Detection w. 935

    if det_time > 0.01 * us:
        self.urukul0_ch3.set(frequency=det_freq, amplitude=det_amp, phase_mode=2)
        # delay(AOMdelay)
        self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
        # delay(AOMdelay)

        # self.urukul1_ch1.set_att(30 * dB)
        # self.urukul1_ch1.set(frequency=OP_freq, amplitude=det_amp, phase_mode=2)
        #
        # self.urukul1_ch1.sw.off()

        # a little bit of Doppler for pumping out dark state
        # self.urukul0_ch1.set(frequency=doppler_freq, amplitude=0.8, phase_mode=2)
        # self.urukul0_ch1.sw.on()

        # self.urukul0_ch3.set_att(0 * dB)

        #
        self.urukul1_ch3.sw.on()
        self.urukul0_ch2.sw.on()  # 935 on
        self.urukul0_ch3.sw.on()
        # self.ttl5.on()

        # for simple detection using edge counter
        # delay(50*us)
        # with parallel:
        # delay(-5*us)
        self.ttl.gate_rising(det_time)
        # self.pulseDetection(det_time)
        # delay_mu(1)

        # without edge counter
        # detcounts_time = self.ttl.gate_rising(detTime)

        # with parallel:
        #     with sequential:# Q: How to access number of scan points?
        #         maxttl2=(detTime/pulse_time) # detection has to be greater than pulse time
        #         maxttl=int(maxttl2)
        #         for i in range(maxttl):
        #             self.ttl4.pulse(detTime*i/(maxttl2*2.0))
        #             delay(detTime/(maxttl2*2.0))

        # Detection off
        # delay(50*us)
        # self.urukul0_ch2.set_att(30 * dB)
        # self.urukul0_ch3.set_att(30 * dB)

        self.urukul0_ch3.sw.off()
        self.urukul0_ch2.sw.off()  # 935 on
        # self.urukul0_ch1.sw.off()
        self.urukul1_ch3.sw.off()
        # self.ttl5.off()

    # delay(50 * us)

    # continue Doppler+935

    self.urukul0_ch1.set(frequency=doppler_freq, amplitude=doppler_amp, phase_mode=2)
    self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)
    self.urukul0_ch1.set_att(0 * dB)
    self.urukul0_ch2.set_att(0 * dB)
    self.urukul0_ch1.sw.on()
    self.urukul0_ch2.sw.on()
    # self.urukul0_ch2.set(frequency=freq_935, amplitude=0.8, phase_mode=2)

    # delay(30 * us)
    # self.urukul0_ch1.sw.on()  # can't use dictionary under kernel
    #  self.ttl5.off()
    # extra computations always left at the end of the scan, or else RTIO underflow occurs for Kasli. Problem doesn't persist with Kasli SOC.

    # self.sum_rising_edges = self.sum_rising_edges + x
    # delay(3*ms)
    # delay_mu(1)

    x = self.ttl.fetch_count()
    # self.ttl.set_config(count_rising=True, count_falling=False, send_count_event=False, reset_to_zero=True)
    self.histpoints[i] = x
    delay(10 * us)

    i = i + 1


'''