"""Release a prepared allocation gate independently of the sampler and runner."""

import json
import os
import sys
import time


def main():
    gate = int(sys.argv[1])
    offset = int(sys.argv[2])
    origin = sys.stdin.readline().strip()
    if not origin:
        return 2
    deadline = int(origin) + offset
    while (remaining := deadline - time.monotonic_ns()) > 0:
        time.sleep(remaining / 1e9)
    requested = time.monotonic_ns()
    os.write(gate, b'G')
    released = time.monotonic_ns()
    os.close(gate)
    print(json.dumps(dict(planned_ns=deadline, requested_ns=requested, released_ns=released)), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
