import serial
import time
#
# ser = serial.Serial('COM7', 9600, timeout=3, xonxoff=True)
# ser.write(b'*IDN?\r\n')
# time.sleep(0.5)
# response = ser.read(100)  # read up to 100 bytes
# print("Response:", response.decode(errors='ignore').strip())
# ser.close()



import serial
import time
import csv
import os
import matplotlib.pyplot as plt
from datetime import datetime

# --- User Configuration ---
COM_PORT = 'COM8'  # Replace with your actual port
# SAVE_FOLDER = r'Z:\Lab Rice\Experimental Projects\Monolithic Trap\DC short burning\20250429-pickoff'
SAVE_FOLDER = r'Z:\Lab Rice\Experimental Projects\Monolithic Trap\DC Electrodes Monitoring\26_02_02_pin_6_front_feedthrough_Keithley_2000'
READ_INTERVAL = 2  # seconds

# --- Serial Setup ---
ser = serial.Serial(
    port=COM_PORT,
    baudrate=9600,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=2
)

# --- Initialize Multimeter to Measure DC Voltage ---
def configure_voltage_mode():
    #ser.write(b':CONF:VOLT:DC\n')   # Configure for DC voltage
    ser.write(b':CONF:VOLT:AC\n')   # Configure for AC voltage
    time.sleep(0.2)

# def read_voltage():
#     ser.write(b':ID?\n')
#     res=ser.readline().decode(errors='ignore').strip()
#     print(res)
#     ser.write(b':READ?\n')
#     time.sleep(0.5)
#     response = ser.readline().decode(errors='ignore').strip()
#     if response:
#         return float(response)
#     else:
#         raise IOError("No response from Keithley 2000")

# 26/02/02 gt
def read_voltage():
    # Clear the buffers before asking
    ser.reset_input_buffer()

    # Use \r\n to ensure the Keithley sees the "Enter" key
    ser.write(b':FETCH?\r\n')

    time.sleep(0.1)  # Give the slow 2000 hardware a moment
    response = ser.readline().decode(errors='ignore').strip()

    if response:
        # The 2000 often sends strings like '+0.123456E+00'
        # We convert that directly to a float
        return float(response)
    else:
        # If we get here, the cable or the 'RS232 ON' setting is wrong
        raise IOError("No response from Keithley 2000 - Check RS232 Menu & Cable")

# --- Setup CSV Logging ---
timestamp_str = datetime.now().strftime('%Y-%m-%d_%H%M%S')
filename = f'keithley2000_voltage_{timestamp_str}.csv'
os.makedirs(SAVE_FOLDER, exist_ok=True)
csv_path = os.path.join(SAVE_FOLDER, filename)

with open(csv_path, 'w', newline='') as csvfile:
    csv.writer(csvfile).writerow(['Timestamp', 'Voltage (V)'])

# --- Setup Live Plotting ---
plt.ion()
fig, ax = plt.subplots()
voltages, timestamps = [], []

line, = ax.plot([], [], 'b-', label='Voltage (V)')
ax.set_xlabel('Time (s)')
ax.set_ylabel('Voltage (V)', color='b')
ax.set_title('Keithley 2000 Real-Time Voltage')
ax.grid(True)
fig.legend(loc="upper right")

start_time = time.time()

# --- Main Measurement Loop ---
try:
    configure_voltage_mode()
    print(f"Logging voltage data to: {csv_path}")

    while True:
        now = time.time() - start_time
        timestamp = datetime.now().isoformat()

        voltage = read_voltage()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Voltage = {voltage:.6f} V")

        # Store data
        timestamps.append(now)
        voltages.append(voltage)

        # Log to CSV
        with open(csv_path, 'a', newline='') as csvfile:
            csv.writer(csvfile).writerow([timestamp, voltage])

        # Update plot
        line.set_data(timestamps, voltages)
        ax.relim()
        ax.autoscale_view()
        plt.pause(0.01)

        time.sleep(READ_INTERVAL)

except KeyboardInterrupt:
    print("Measurement stopped.")
finally:
    ser.close()
    plt.ioff()
    plt.show()
