import serial
import time
import sys

if __name__=="__main__":
    serialobj=serial.Serial('COM20',9600) # Arduino COM port
    time.sleep(3) # strictly necessary
    serialobj2=serial.Serial('COM3',9600) # Read from COM2, with data written to COM1 from RFramp.py
    filename=r"C:\Users\TrappedIonRice4\Documents\Artiq-Rice\dataset_db.pyon"
    RFkeyword="RFamp_Arduino"
    V=0.1
    while(True):
        try:

            # with open(filename, 'r') as fileobj:
            #     arr = fileobj.readlines()
            #     for i in range(len(arr)):
            #         if RFkeyword in arr[i]:
            #             valstr = arr[i].split(":")[1]  # splitting keyword and value in dataset_sb file
            #             V = float(valstr.split(",")[0])  # extracting RFamp_arduino
            #             break
            # vbit = int((V / 13.89) * (2 ** 18 - 1) + 70635)

            '''
            Reads from virtual COM port continuously and feeds
            data to the real COM3 port connected to the Arduino.
            This avoids the initial delay on restarting the arduino,
            and resetting the arduino
            '''
            command=serialobj2.readline()
            print(command)
            #print(command.decode().strip())
            #command = "V1 " + str(vbit) + '\n'
            #print("{0:s}\t{1:.3f}\n".format(command,V))
            serialobj.write(command)
            serialobj.reset_input_buffer()
            serialobj2.reset_output_buffer()
        except KeyboardInterrupt:
            serialobj.close()
            serialobj2.close()
            sys.exit(0)
