# node_sim.py
import socket
import json
import time
import random
import sys
from config import SERVER_HOST, UDP_PORT, NODES, SIGNAL_CYCLE, SIGNAL_DURATIONS

def run_node(node_id):
    if node_id not in NODES:
        print(f"Invalid node ID '{node_id}'. Choose from: {list(NODES.keys())}")
        sys.exit(1)

    location = NODES[node_id]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    signal_index = 0
    signal_timer = 0
    current_signal = SIGNAL_CYCLE[0]
    seq = 0

    print(f"[Node-{node_id}] Starting at {location} → sending to {SERVER_HOST}:{UDP_PORT}")

    while True:
        # Advance signal cycle
        signal_timer += 1
        if signal_timer >= SIGNAL_DURATIONS[current_signal]:
            signal_timer = 0
            signal_index = (signal_index + 1) % len(SIGNAL_CYCLE)
            current_signal = SIGNAL_CYCLE[signal_index]

        # Simulate vehicle count based on signal
        if current_signal == "RED":
            vehicle_count = random.randint(20, 50)
        elif current_signal == "YELLOW":
            vehicle_count = random.randint(10, 30)
        else:
            vehicle_count = random.randint(0, 20)

        payload = {
            "node_id": node_id,
            "location": location,
            "vehicle_count": vehicle_count,
            "signal": current_signal,
            "timestamp": time.time(),
            "seq": seq,
        }

        data = json.dumps(payload).encode("utf-8")
        sock.sendto(data, (SERVER_HOST, UDP_PORT))
        seq += 1

        print(f"[Node-{node_id}] seq={seq} | {current_signal} | vehicles={vehicle_count}")
        time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python node_sim.py <node_id>")
        print("Example: python node_sim.py A")
        sys.exit(1)
    run_node(sys.argv[1].upper())