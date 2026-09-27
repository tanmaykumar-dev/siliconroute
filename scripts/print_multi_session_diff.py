"""Script to print all model/device/batch measured in more than one session with % difference."""

from collections import defaultdict
import sys
sys.path.insert(0, ".")
from sqlmodel import Session, select
from app.db import engine, Run, Device, AIModel


def main():
    with Session(engine) as s:
        runs = s.exec(select(Run).where(Run.session_id != None)).all()
        models = {m.id: m for m in s.exec(select(AIModel)).all()}
        devices = {d.id: d for d in s.exec(select(Device)).all()}

        groups = defaultdict(list)
        for r in runs:
            m = models.get(r.ai_model_id)
            d = devices.get(r.device_id)
            if m and d:
                groups[(m.name, d.key, r.batch)].append(r)

        multi = {k: v for k, v in groups.items() if len(set(r.session_id for r in v)) > 1}
        print(f"Total multi-session configurations: {len(multi)}\n")
        header = f"{'Model':<16} {'Device':<6} {'B':<3} {'Sessions and Medians (ms)':<50} {'Min ms':<8} {'Max ms':<8} {'Diff %'}"
        print(header)
        print("-" * len(header))
        for (m_name, d_key, b), r_list in sorted(multi.items()):
            sess_map = {}
            for r in r_list:
                sess_map.setdefault(r.session_id, []).append(r.median_ms)
            sess_medians = {s_id: round(sum(vals) / len(vals), 3) for s_id, vals in sess_map.items()}
            vals = list(sess_medians.values())
            min_v = min(vals)
            max_v = max(vals)
            diff_pct = ((max_v - min_v) / min_v) * 100
            sess_str = ", ".join(f"S{s_id}:{v:.3f}" for s_id, v in sorted(sess_medians.items()))
            print(f"{m_name:<16} {d_key:<6} {b:<3} {sess_str:<50} {min_v:<8.3f} {max_v:<8.3f} {diff_pct:>6.1f}%")


if __name__ == "__main__":
    main()
