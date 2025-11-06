
# example to establish socket connection

import socket
from sipyco import pyon

HOST = "127.0.0.1"
PORT = 5000

scan_params = {
    "start": 0.0,
    "stop": 1.0,
    "num_pts": 5,
    "num_reps": 10,
}

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    print("[ARTIQ] Connected to AWG.")

    # 1️⃣ Send scan configuration
    s.sendall(pyon.encode(scan_params).encode())
    print(f"[ARTIQ] Sent scan parameters: {scan_params}")

    # 2️⃣ Wait for READY message
    data = s.recv(4096).decode()
    reply = pyon.decode(data)
    print(f"[ARTIQ] Received from AWG: {reply}")

    if reply["status"] == "READY":
        print("[ARTIQ] Starting trigger sequence...")
        # TODO: Replace this print loop with actual TTL pulses
        for pt in reply["scan_points"]:
            print(f"[ARTIQ] Triggering for scan point {pt:.4f}")

    # 3️⃣ Notify AWG that all triggers are done
    done_msg = {"status": "DONE"}
    s.sendall(pyon.encode(done_msg).encode())
    print("[ARTIQ] Sent DONE message to AWG.")