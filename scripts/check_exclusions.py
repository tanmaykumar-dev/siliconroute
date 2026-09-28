"""Quick diagnostic: why are devices excluded from recent decisions?"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select
from app.db import Decision, engine, init_db

init_db()
with Session(engine) as session:
    decs = session.exec(select(Decision).where(Decision.id >= 21).order_by(Decision.id)).all()
    for d in decs:
        ctx = json.loads(d.context_json) if d.context_json else {}
        excluded = ctx.get("excluded_candidates", [])
        cands = json.loads(d.candidates_json) if d.candidates_json else []
        cand_keys = [c["device_key"] for c in cands]
        excl_summary = "; ".join(f"{e['device_key']}: {e['reason']}" for e in excluded) if excluded else "none"
        print(f"Dec {d.id:>3}: candidates=[{', '.join(cand_keys)}] excluded=[{excl_summary}]")
