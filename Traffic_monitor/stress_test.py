# stress_test.py — run on the CONTROLLER or any machine on the same LAN
import socket
import json
import time
import threading
import random
from config import CONTROLLER_HOST, NODE_SEND_PORT, NODES

DURATION_SEC = 10
NUM_NODES    = 20      # virtual stress nodes (on top of the real 4)
RESULTS_LOCK = threading.Lock()
results      = []


def node_worker(node_id):
    sock  = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent  = 0
    start = time.time()
    while time.time() - start < DURATION_SEC:
        payload = json.dumps({
            "node_id":       f"ST-{node_id}",
            "location":      f"Stress-{node_id}",
            "vehicle_count": random.randint(0, 50),
            "signal":        random.choice(["RED", "GREEN", "YELLOW"]),
            "timestamp":     time.time(),
            "seq":           sent,
        }).encode()
        sock.sendto(payload, (CONTROLLER_HOST, NODE_SEND_PORT))
        sent += 1
    with RESULTS_LOCK:
        results.append(sent)
    sock.close()


if __name__ == "__main__":
    print(f"Stress test: {NUM_NODES} nodes × {DURATION_SEC}s  →  {CONTROLLER_HOST}:{NODE_SEND_PORT}")
    print("-" * 50)
    threads = [threading.Thread(target=node_worker, args=(i,)) for i in range(NUM_NODES)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.time() - t0
    total   = sum(results)
    print(f"Total sent   : {total:,}")
    print(f"Duration     : {elapsed:.2f}s")
    print(f"Throughput   : {int(total/elapsed):,} packets/sec")
    print(f"Per-node avg : {int(total/NUM_NODES):,} packets")
    print("-" * 50)
    print("Check dashboard for received count and loss %.")