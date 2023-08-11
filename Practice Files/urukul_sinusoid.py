from artiq.coredevice.ad9910 import RAM_MODE_CONT_RAMPUP
from artiq.coredevice.urukul import *
from artiq.experiment import *

#import numpy as np

class Basic_sinusoid(EnvExperiment):
	
	def build(self):

		# Set up class experiment using devices from device_db
		
		self.setattr_device("core")
		self.setattr_device("urukul0_cpld") # Necessary for clock sync
		self.setattr_device("urukul0_ch0")
		#self.setattr_device("urukul0_ch1")
		
	@kernel
	def run(self):
		
		# Reset the core device and initialize devices
		# that are going to be used
		self.core.reset()
		self.urukul0_cpld.init()
		self.urukul0_ch0.init()
		#self.urukul0_ch1.init()
		
		self.urukul0_ch0.cfg_sw(True)
		self.urukul0_ch0.set_att(6.*dB) # Attenuate by 6 dB
		#self.urukul0_ch1.set_att(6.*dB)
		
		#with parallel:
		self.urukul0_ch0.set(1*MHz) # Set frequency to specified multiplier in MHz
			#self.urukul0_ch1.set(2*MHz)
			
class TTL_test(EnvExperiment):
	
	def build(self):
		self.setattr_device("core")
		self.setattr_device("ttl4")
		
	@kernel
	def run(self):
		delay(16.667*ms)
		self.ttl4.pulse(10*ms)
		delay(5*ms)

class RAM_modulation_sinusoid(EnvExperiment):

	# Class that modulates a basic sinusoid. Attempts to delay, amplify, deamplify,
	# ramp, and damp DDS signals. Uses TTL Signaling to help read signals with
	# an oscilloscope.
	# This class writes to the Control Function Registers, which gets read to
	# modulate the DDS signal.
	# Note that TTL Updates are Atomic and DDS Updates are NOT Atomic. This means
	# DDS signaling and TTL signaling read the master clock differently, and will
	# thus be out of phase.

	def build(self):

		# Set up class experiment using devices from device_db
		
		self.setattr_device("core")
		self.setattr_device("urukul0_cpld") # Necessary for clock sync
		self.setattr_device("urukul0_ch0") # Use DDS Channel 0
		self.setattr_device("ttl4") # Use TTL Channel 4

	def prepare(self):
		
		# Define the DDS signal that will be outputted as a list
		# Then, allocate the number of elements in that list into
		# a list of all zeros
		
		self.amp=[0.0, 0.0, 0.0, 0.7, 0.0, 0.7, 0.7]
		self.asf_ram = [0] * len(self.amp) # asf is the amplitude scale factor
	
	@kernel
	def init_urukul(self, urukul0):
		
		# Initializes an urukul channel that is passed as a parameter
		# Must be used for all DDS signaling purposes,
		# and can be used to initialize multiple channels with
		# different channel passed as arguments upon function call
		
		self.core.break_realtime()
		urukul0.init() # Initialize the channel
		urukul0.set_att(6.*dB) # Initialize the attenuation of the channel
		urukul0.cfg_sw(True) # Set CPLD CFG RF switch state.
		
	@kernel
	def configure_ram_mode(self, urukul0):
		
		# Configures the RAM mode for signal generation for a channel passed in
		# as an argument upon function call

		self.core.break_realtime()
		urukul0.set_cfr1(ram_enable=0)  # Sets the Control Function Register #1 (0x00) MSb
		# (AD9910 Datasheet, Pg. 49)

		self.core.break_realtime()

		# self.urukul0_cpld.io_update.pulse_mu(8)

		self.urukul0_cpld.set_profile(0)  # Set the PROFILE pins

		urukul0.set_profile_ram(start=0, end=len(self.asf_ram) - 1,
								step=250, profile=0, mode=RAM_MODE_CONT_RAMPUP)
		# Sets the RAM Profile Settings for the specified profile

		self.urukul0_cpld.io_update.pulse_mu(8)
		urukul0.amplitude_to_ram(self.amp, self.asf_ram)
		urukul0.write_ram(self.asf_ram)
		urukul0.set(frequency=1 * MHz)  # , ram_destination = RAM_DEST_ASF
		
		with parallel:
			self.ttl4.pulse((len(self.amp))*us)
			urukul0.set_cfr1(ram_enable = 1, ram_destination = 2)

		# self.urukul0_cpld.io_update.pulse_mu(8)

	@kernel
	def run(self):
		
		self.core.reset()
		self.core.break_realtime()
		self.ttl4.output()
		self.urukul0_cpld.init()
		self.init_urukul(self.urukul0_ch0)
		
		self.configure_ram_mode(self.urukul0_ch0)
		# delay(16.667*ms)
		# while(True):

		self.configure_ram_mode(self.urukul0_ch0)
		# delay(16.667*ms)


class Amplitude_modulation(EnvExperiment):

	# Class that modulates a basic sinusoid. Attempts to delay, amplify, deamplify,
	# ramp, and damp DDS signals. Uses TTL Signaling to help read signals with
	# an oscilloscope.
	# This class writes to the Control Function Registers, which gets read to
	# modulate the DDS signal.
	# Note that TTL Updates are Atomic and DDS Updates are NOT Atomic. This means
	# DDS signaling and TTL signaling read the master clock differently, and will
	# thus be out of phase.

	def build(self):
		# Set up class experiment using devices from device_db

		self.setattr_device("core")
		self.setattr_device("urukul0_cpld")  # Necessary for clock sync
		self.setattr_device("urukul0_ch0")  # Use DDS Channel 0
		self.setattr_device("ttl4")  # Use TTL Channel 4
		self.amplitude = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
		#self.amplitude = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
		self.pulse_length = 6.0 * us

	@kernel
	def run(self):

		self.core.reset()
		self.ttl4.output()
		self.core.break_realtime()

		delay(1*ms)
		self.urukul0_cpld.init()
		self.ttl4.off()
		delay(2*ms)
		self.urukul0_ch0.init()
		delay(1*ms)
		self.urukul0_cpld.set_att(0, 6.0*dB)

		for amp in self.amplitude:

			self.urukul0_ch0.set(frequency=1 * MHz, amplitude=amp, ref_time_mu=0)
			# delay_mu(8)
			with parallel:
				self.ttl4.pulse(self.pulse_length)
				self.urukul0_ch0.sw.pulse(self.pulse_length)
