
from artiq.experiment import *
import logging


class Idle369On355Pulsed(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")
        self.setattr_device("urukul0_ch1")  # Doppler
        self.setattr_device("ttl6")  # Raman 2 shutter
        self.setattr_device("scheduler")  # MUST be loaded to check termination flag

        self.default_Raman_time = self.get_dataset("355_RamanB1.Time(ms)") * ms
        self.default_SBCtime = self.get_dataset("SBC.tone1.Time(ms)") * ms

        self.setattr_argument("timeRaman", NumberValue(default=self.default_Raman_time, ndecimals=4, unit="ms"))
        self.setattr_argument("timeSBC", NumberValue(default=self.default_SBCtime, ndecimals=4, unit="ms"))
        # self.setattr_argument("timeSBC", NumberValue(default=self.default_SBCtime, ndecimals=4, unit="ms"))

        logger = logging.getLogger("artiq.coredevice.comm_kernel")
        logger.setLevel(logging.WARNING)

    def prepare(self):
        self.dopplerFreq = self.get_dataset("Doppler.Frequency")
        self.dopplerAmp = self.get_dataset("Doppler.Amp")
        self.dopplerTime = self.get_dataset("Doppler.Time(ms)") * ms
        # self.sbcTime = self.get_dataset("SBC.tone1.Time(ms)") * ms
        self.prepOPtime = self.get_dataset("OP.Time(ms)") * ms
        self.detTime = self.get_dataset("Detection.Time(ms)") * ms
        self.target_ULE369freq_idle = self.get_dataset("Experiment_config.ULE369_freq_idle")

    @kernel
    def init_hardware(self):
        self.core.reset()
        self.ttl6.output()
        delay(2 * ms)
        self.urukul0_cpld.init()
        delay(10 * ms)

        self.urukul0_ch1.init()
        self.urukul0_ch1.set_att(0 * dB)
        self.urukul0_ch1.set(frequency=self.dopplerFreq, amplitude=self.dopplerAmp, phase_mode=2)

        self.urukul0_ch1.sw.on()
        self.ttl6.off()

    @kernel
    def single_pulse_sequence(self):
        self.core.break_realtime()

        # Turn on Raman 2 for trap conditioning
        self.ttl6.on()
        delay(500 * ms)
        self.ttl6.off()

        delay(30 * us)

        # Doppler delay
        delay(self.dopplerTime)

        self.ttl6.on()
        delay(self.timeSBC * 30 * 6)
        self.ttl6.off()

        delay(self.prepOPtime)

        self.ttl6.on()
        delay(self.timeRaman)
        self.ttl6.off()

        delay(self.detTime)

        # Block CPU execution until the hardware sequence finishes in real-time
        self.core.wait_until_mu(now_mu())

    def run(self):
        import time

        # 1. Prepare idle dataset and DC control job
        idleEndcapAvg = self.get_dataset("Loading.endcap_avg")
        idleEndcapX = -0.07 # V
        self.set_dataset("DC.EndcapAvg", idleEndcapAvg, broadcast=True, archive=True, persist=True)
        self.set_dataset("DC.EndcapX", idleEndcapX, broadcast=True, archive=True, persist=True)

        DCcontrolId = {
            "file": "RFandDC/DCelectrodes.py",
            "class_name": "DC_Control",
            "arguments": {},
            "log_level": self.scheduler.expid["log_level"],
            "repo_rev": self.scheduler.expid["repo_rev"],
        }

        expid_ULE369controlIdling= {
            "file": "Manual Control/ULE369_Ramp.py",
            "class_name": "ULE369_control",
            "arguments": {"ramp_rate": 2.0 * MHz,
                          "target_frequency": self.target_ULE369freq_idle,
                          "time_step": 100 * ms
                          },
            "log_level": 0,
            "repo_rev": self.scheduler.expid["repo_rev"],
        }

        # Submit the "Relaxed" idle voltages to the bypass pipeline
        self.scheduler.submit("idle", expid_ULE369controlIdling)
        # self.scheduler.submit("dc_update", DCcontrolId)
        print("Waiting for DC electrodes to update to relaxed confinement...")
        time.sleep(2)

        try:
            self.init_hardware()
            print("Hardware initialized. Starting background idler loop...")

            while True:
                self.single_pulse_sequence()

                # If terminated via the GUI panel "Terminate" button
                if self.scheduler.check_termination():
                    print("[TERMINATION] Termination requested by dashboard. Exiting loop...")
                    break  # Just break! Don't do cleanup here anymore.

        except TerminationRequested:
            # This catches the Schedule "Delete" action
            print("[TERMINATION] Forced abort caught (Deleted from schedule).")

        finally:
            # THIS RUNS NO MATTER WHAT: Graceful terminate, Hard Delete, or even a random code crash.

            print("[CLEANUP] Restoring DC electrodes to experiment config...")
            expEndcapAvg = self.get_dataset("Experiment_config.endcap_avg")
            expEndcapX = self.get_dataset("Experiment_config.endcapX")
            self.set_dataset("DC.EndcapAvg", expEndcapAvg, broadcast=True, archive=True, persist=True)
            self.set_dataset("DC.EndcapX", expEndcapX, broadcast=True, archive=True, persist=True)

            # Submit to the bypass pipeline to restore voltages
            self.scheduler.submit("dc_update", DCcontrolId)
            time.sleep(2)  # Give the scheduler a second to register the job before this script dies
            print("[CLEANUP] Restoring lasers to safe OFF state...")
            self.restore_state()


    @kernel
    def restore_state(self):
        """Clears the RTIO FIFO buffer and shuts off all outputs immediately."""
        self.core.reset()
        self.ttl6.off()
        # self.urukul0_ch1.sw.off()
