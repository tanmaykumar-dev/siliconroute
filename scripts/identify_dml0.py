"""Run 8-second identify load test on dml:0 for Task Manager verification."""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from sqlmodel import Session, select
from app.config import IDENTIFY_S
from app.db import Device, engine
from app.devices import make_session
from app.models_gen import generate_mlp

def main():
    with Session(engine) as session:
        dev = session.exec(select(Device).where(Device.key == "dml:0")).first()
        if not dev:
            print("dml:0 device not found in database.")
            return

        print("=" * 80)
        print(f"STARTING {IDENTIFY_S}-SECOND IDENTIFY LOAD TEST ON {dev.key} ({dev.label})")
        print("Please watch Windows Task Manager -> Performance -> GPU graphs right now!")
        print("=" * 80)

        path, _, _, _, _ = generate_mlp(width=1024, layers=4)
        x_in = np.ones((8, 1024), dtype=np.float32)
        sess = make_session(str(path), dev.provider, device_id=0)

        t_start = time.time()
        t_end = t_start + IDENTIFY_S
        inferences = 0
        while time.time() < t_end:
            sess.run(None, {"X": x_in})
            inferences += 1

        print("=" * 80)
        print(f"IDENTIFY LOAD TEST FINISHED: Executed {inferences} inferences on {dev.key} over {IDENTIFY_S}s.")
        print("=" * 80)

if __name__ == "__main__":
    main()
