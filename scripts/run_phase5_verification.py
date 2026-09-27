"""Phase 5 Router Verification Script.

Executes 20 verified routing decisions across small, medium, and large
MLP and Conv models at batches 1, 8, and 32 in Fastest and Balanced modes,
including 3 decisions executed immediately after 10 seconds of GPU idle.

Prints the complete decision table and baseline comparison statistics.
"""

import json
import os
from pathlib import Path
import sys
import time

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.db import AIModel, Decision, Device, engine, init_db
from app.router import compute_decision_statistics, execute_verification, route_model


def run_phase5():
    init_db()
    with Session(engine) as session:
        # Map models by name
        all_models = {m.name: m for m in session.exec(select(AIModel)).all()}
        all_devices = {d.id: d for d in session.exec(select(Device)).all()}

        # Verify key models exist
        target_model_names = [
            "mlp-256w-4l",   # Small MLP (1 MB)
            "mlp-1024w-4l",  # Medium MLP (16 MB)
            "mlp-3072w-4l",  # Large MLP (144 MB)
            "conv-16c-4l",   # Small Conv (0.04 MB)
            "conv-64c-4l",   # Medium Conv (0.6 MB)
            "conv-96c-4l",   # Large Conv (1.3 MB)
        ]

        for name in target_model_names:
            if name not in all_models:
                print(f"Error: model '{name}' not found in database!")
                sys.exit(1)

        print("=" * 80)
        print("SILICONROUTE PHASE 5: EXECUTING 20 VERIFIED ROUTING DECISIONS ON HARDWARE")
        print("=" * 80)

        # 17 standard decisions covering small/medium/large x batches 1, 8, 32 x modes
        plan = [
            # Small MLP
            ("mlp-256w-4l", 1, "fastest", False),
            ("mlp-256w-4l", 8, "fastest", False),
            ("mlp-256w-4l", 32, "balanced", False),
            # Medium MLP
            ("mlp-1024w-4l", 1, "fastest", False),
            ("mlp-1024w-4l", 8, "fastest", False),
            ("mlp-1024w-4l", 32, "balanced", False),
            # Large MLP
            ("mlp-3072w-4l", 1, "fastest", False),
            ("mlp-3072w-4l", 8, "fastest", False),
            ("mlp-3072w-4l", 32, "balanced", False),
            # Small Conv
            ("conv-16c-4l", 1, "fastest", False),
            ("conv-16c-4l", 8, "fastest", False),
            ("conv-16c-4l", 32, "balanced", False),
            # Medium Conv
            ("conv-64c-4l", 1, "fastest", False),
            ("conv-64c-4l", 8, "fastest", False),
            ("conv-64c-4l", 32, "balanced", False),
            # Large Conv
            ("conv-96c-4l", 1, "fastest", False),
            ("conv-96c-4l", 8, "fastest", False),
            # Plus 3 decisions right after 10 s of GPU idle
            ("mlp-256w-4l", 1, "fastest", True),
            ("mlp-1024w-4l", 1, "fastest", True),
            ("mlp-3072w-4l", 1, "fastest", True),
        ]

        verified_records = []

        for idx, (m_name, batch, mode, idle_wait) in enumerate(plan, 1):
            model = all_models[m_name]
            idle_tag = ""
            if idle_wait:
                print(f"\n[{idx}/20] Sleeping 10 s to ensure GPU enters P8 deep sleep state...")
                time.sleep(10.0)
                idle_tag = " [10s Idle Wake]"

            print(f"[{idx}/20] Routing {m_name} (B={batch}, mode={mode}){idle_tag}...", end=" ", flush=True)

            # 1. Routing decision
            dec_dict = route_model(
                session=session,
                model_id=model.id,
                batch=batch,
                mode=mode,
                allow_explore=False,  # Pure router policy evaluation
            )

            # 2. Hardware verification across all candidates
            dec_record = execute_verification(session, dec_dict, runs_count=10)
            verified_records.append(dec_record)

            chosen_dev = all_devices.get(dec_record.chosen_device_id)
            best_dev = all_devices.get(dec_record.best_device_id_actual)
            win_str = "WIN" if dec_record.was_best else f"REGRET {dec_record.regret_pct:.1f}%"
            print(f"-> Chose {chosen_dev.key if chosen_dev else '?'} | Actual: {dec_record.actual_ms:.3f} ms | Best: {best_dev.key if best_dev else '?'} | {win_str}")

        print("\n" + "=" * 110)
        print("VERIFIED DECISIONS SUMMARY TABLE (20 RUNS)")
        print("=" * 110)
        header = f"{'ID':<4} | {'Model':<14} | {'B':<2} | {'Mode':<8} | {'Chosen':<6} | {'Source':<8} | {'Pred (ms)':<9} | {'Act (ms)':<8} | {'Best':<6} | {'Match?':<6} | {'Regret %':<8}"
        print(header)
        print("-" * 110)

        for d in verified_records:
            model = all_models.get(session.get(AIModel, d.ai_model_id).name)
            chosen_dev = all_devices.get(d.chosen_device_id)
            best_dev = all_devices.get(d.best_device_id_actual)
            cands = json.loads(d.candidates_json)
            chosen_cand = next((c for c in cands if c["device_id"] == d.chosen_device_id), {})
            source = chosen_cand.get("source", "fit")
            pred_ms = chosen_cand.get("effective_latency_ms", 0.0)
            match_str = "Yes" if d.was_best else "No"

            row = (
                f"{d.id:<4} | {model.name:<14} | {d.batch:<2} | {d.mode:<8} | "
                f"{chosen_dev.key:<6} | {source:<8} | {pred_ms:<9.3f} | {d.actual_ms:<8.3f} | "
                f"{best_dev.key:<6} | {match_str:<6} | {d.regret_pct:<8.2f}%"
            )
            print(row)

        print("-" * 110)

        # Baseline Statistics
        stats = compute_decision_statistics(session)
        print("\n" + "=" * 80)
        print("ROUTER VS BASELINES COMPARISON (VERIFIED RUNS)")
        print("=" * 80)
        print(f"Total Verified Decisions: {stats['total_verified']}")
        print(f"")
        print(f"{'Policy / Baseline':<28} | {'Accuracy %':<10} | {'Mean Regret %':<14} | {'P90 Regret %':<12}")
        print("-" * 72)

        sr = stats["siliconroute"]
        print(f"{'SiliconRoute (Measured-First)':<28} | {sr['accuracy_pct']:<10.1f}% | {sr['mean_regret_pct']:<14.2f}% | {sr['p90_regret_pct']:<12.2f}%")

        b = stats["baselines"]
        cpu = b["always_cpu"]
        print(f"{'Always-CPU Baseline':<28} | {cpu['accuracy_pct']:<10.1f}% | {cpu['mean_regret_pct']:<14.2f}% | {cpu['p90_regret_pct']:<12.2f}%")

        rtx = b["always_rtx"]
        print(f"{'Always-RTX Baseline (dml:1)':<28} | {rtx['accuracy_pct']:<10.1f}% | {rtx['mean_regret_pct']:<14.2f}% | {rtx['p90_regret_pct']:<12.2f}%")

        fit_only = b["fit_only_router"]
        print(f"{'Fit-Only Router Baseline':<28} | {fit_only['accuracy_pct']:<10.1f}% | {fit_only['mean_regret_pct']:<14.2f}% | {fit_only['p90_regret_pct']:<12.2f}%")

        ort = b["ort_policy"]
        print(f"{'ORT MAX_PERF Policy (dml:0)':<28} | {ort['accuracy_pct']:<10.1f}% | {ort['mean_regret_pct']:<14.2f}% | {ort['p90_regret_pct']:<12.2f}%")
        print("-" * 72)
        print("=" * 80)


if __name__ == "__main__":
    run_phase5()
