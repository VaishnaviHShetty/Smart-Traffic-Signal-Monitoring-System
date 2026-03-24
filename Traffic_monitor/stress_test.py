# stress_test.py
import socket
import json
import time
import threading
import random
from config import SERVER_HOST, UDP_PORT

DURATION_SEC    = 10
NUM_NODES       = 10
RESULTS_LOCK    = threading.Lock()
results         = []


def node_worker(node_id):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
        sock.sendto(payload, (SERVER_HOST, UDP_PORT))
        sent += 1

    with RESULTS_LOCK:
        results.append(sent)

    sock.close()


if __name__ == "__main__":
    print(f"Stress test: {NUM_NODES} nodes × {DURATION_SEC}s")
    print("-" * 40)

    threads = [threading.Thread(target=node_worker, args=(i,))
               for i in range(NUM_NODES)]

    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - t0

    total_sent = sum(results)
    print(f"Total packets sent : {total_sent:,}")
    print(f"Duration           : {elapsed:.2f}s")
    print(f"Throughput         : {int(total_sent / elapsed):,} packets/sec")
    print(f"Per node avg       : {int(total_sent / NUM_NODES):,} packets")
    print("-" * 40)
    print("Check the dashboard for server-side received count and loss %.")
