"""Refit devices with sustained-quality filter, compare old vs new fits, crossovers, and the 5 affected configs."""

import json
from pathlib import Path
from sqlmodel import Session, select
from app.db import create_db_engine, Device, Fit, AIModel, Run
from app.predictor import fit_device, calculate_crossover

def run_comparison():
    engine = create_db_engine()
    with Session(engine) as session:
        # 1. Capture Old Fits (68, 69, 70)
        old_fits_map = {}
        for fid in [68, 69, 70]:
            f = session.get(Fit, fid)
            dev = session.get(Device, f.device_id)
            old_fits_map[dev.key] = {
                "fit_id": f.id,
                "device_key": dev.key,
                "device_label": dev.label,
                "model_form": f.model_form,
                "n_samples": f.n_samples,
                "loo_mape_pct": f.loo_mape_pct,
                "t0_ms": f.t0_ms,
                "compute_gflops": f.compute_gflops,
                "bandwidth_gb_s": f.bandwidth_gb_s,
                "bandwidth_dram_gb_s": f.bandwidth_dram_gb_s,
            }

        # Calculate Old Crossovers using old fits
        pairs = [("cpu", "dml:1"), ("cpu", "dml:0"), ("dml:0", "dml:1")]
        configs = [("mlp", 1), ("mlp", 8), ("conv", 1), ("conv", 8)]
        old_crossovers = {}
        for fam, b in configs:
            for da_key, db_key in pairs:
                da = session.exec(select(Device).where(Device.key == da_key)).first()
                db = session.exec(select(Device).where(Device.key == db_key)).first()
                try:
                    co = calculate_crossover(session, da.id, db.id, family=fam, batch=b)
                    old_crossovers[(fam, b, da_key, db_key)] = co.get("summary")
                except Exception as e:
                    old_crossovers[(fam, b, da_key, db_key)] = f"Error: {e}"

        print("================================================================================")
        print("OLD FITS (Included single-sample runs)")
        print("================================================================================")
        for k, v in old_fits_map.items():
            print(f"Device: {v['device_key']} ({v['device_label']}) [Fit #{v['fit_id']}]")
            print(f"  Model Form: {v['model_form']}, Samples: {v['n_samples']}, LOO MAPE: {v['loo_mape_pct']:.2f}%")
            print(f"  t0: {v['t0_ms']:.4f} ms, Compute: {v['compute_gflops']:.1f} GFLOP/s, SRAM/VRAM: {v['bandwidth_gb_s']:.1f} GB/s, DRAM: {v['bandwidth_dram_gb_s']}")

        # 2. Perform Refit
        print("\n================================================================================")
        print("PERFORMING REFIT WITH SUSTAINED-QUALITY FILTER (timed_runs>=10, warmup_runs>=2)...")
        print("================================================================================")
        avail_devs = session.exec(select(Device).where(Device.is_available == True)).all()
        new_fits = [fit_device(session, d.id, target="latency") for d in avail_devs]

        new_fits_map = {}
        for f in new_fits:
            dev = session.get(Device, f.device_id)
            new_fits_map[dev.key] = {
                "fit_id": f.id,
                "device_key": dev.key,
                "device_label": dev.label,
                "model_form": f.model_form,
                "n_samples": f.n_samples,
                "loo_mape_pct": f.loo_mape_pct,
                "t0_ms": f.t0_ms,
                "compute_gflops": f.compute_gflops,
                "bandwidth_gb_s": f.bandwidth_gb_s,
                "bandwidth_dram_gb_s": f.bandwidth_dram_gb_s,
            }

        # Calculate New Crossovers
        new_crossovers = {}
        for fam, b in configs:
            for da_key, db_key in pairs:
                da = session.exec(select(Device).where(Device.key == da_key)).first()
                db = session.exec(select(Device).where(Device.key == db_key)).first()
                try:
                    co = calculate_crossover(session, da.id, db.id, family=fam, batch=b)
                    new_crossovers[(fam, b, da_key, db_key)] = co.get("summary")
                except Exception as e:
                    new_crossovers[(fam, b, da_key, db_key)] = f"Error: {e}"

        print("\n================================================================================")
        print("NEW FITS (Sustained-quality runs only)")
        print("================================================================================")
        for k, v in new_fits_map.items():
            print(f"Device: {v['device_key']} ({v['device_label']}) [Fit #{v['fit_id']}]")
            print(f"  Model Form: {v['model_form']}, Samples: {v['n_samples']}, LOO MAPE: {v['loo_mape_pct']:.2f}%")
            print(f"  t0: {v['t0_ms']:.4f} ms, Compute: {v['compute_gflops']:.1f} GFLOP/s, SRAM/VRAM: {v['bandwidth_gb_s']:.1f} GB/s, DRAM: {v['bandwidth_dram_gb_s']}")

        print("\n================================================================================")
        print("FIT COMPARISON: OLD VS NEW")
        print("================================================================================")
        print(f"{'Device':<8} | {'Metric':<18} | {'Old Fit':<14} | {'New Fit':<14} | {'Delta':<12}")
        print("-" * 72)
        for k in ["cpu", "dml:0", "dml:1"]:
            old_f = old_fits_map.get(k, {})
            new_f = new_fits_map.get(k, {})
            # Samples
            print(f"{k:<8} | {'Samples':<18} | {old_f.get('n_samples'):<14} | {new_f.get('n_samples'):<14} | {new_f.get('n_samples') - old_f.get('n_samples'):<12}")
            # LOO MAPE
            old_m, new_m = old_f.get('loo_mape_pct', 0), new_f.get('loo_mape_pct', 0)
            print(f"{k:<8} | {'LOO MAPE %':<18} | {old_m:<14.2f} | {new_m:<14.2f} | {new_m - old_m:<+12.2f}")
            # t0
            old_t0, new_t0 = old_f.get('t0_ms', 0), new_f.get('t0_ms', 0)
            print(f"{k:<8} | {'t0 (ms)':<18} | {old_t0:<14.4f} | {new_t0:<14.4f} | {new_t0 - old_t0:<+12.4f}")
            # Compute
            old_c, new_c = old_f.get('compute_gflops', 0), new_f.get('compute_gflops', 0)
            print(f"{k:<8} | {'Compute (GFLOP/s)':<18} | {old_c:<14.1f} | {new_c:<14.1f} | {new_c - old_c:<+12.1f}")
            # Bandwidth SRAM/VRAM
            old_bw, new_bw = old_f.get('bandwidth_gb_s', 0), new_f.get('bandwidth_gb_s', 0)
            print(f"{k:<8} | {'VRAM/SRAM (GB/s)':<18} | {old_bw:<14.1f} | {new_bw:<14.1f} | {new_bw - old_bw:<+12.1f}")
            # DRAM
            old_dram = f"{old_f.get('bandwidth_dram_gb_s'):.1f}" if old_f.get('bandwidth_dram_gb_s') is not None else "n/a"
            new_dram = f"{new_f.get('bandwidth_dram_gb_s'):.1f}" if new_f.get('bandwidth_dram_gb_s') is not None else "n/a"
            print(f"{k:<8} | {'DRAM (GB/s)':<18} | {old_dram:<14} | {new_dram:<14} | {'--':<12}")
            print("-" * 72)

        print("\n================================================================================")
        print("CROSSOVER COMPARISON: OLD VS NEW")
        print("================================================================================")
        for fam, b in configs:
            for da_key, db_key in pairs:
                key = (fam, b, da_key, db_key)
                old_summary = old_crossovers.get(key, "n/a")
                new_summary = new_crossovers.get(key, "n/a")
                print(f"[{fam.upper()} Batch {b}] {da_key.upper()} vs {db_key.upper()}:")
                print(f"  Old: {old_summary}")
                print(f"  New: {new_summary}")

        print("\n================================================================================")
        print("THE 5 AFFECTED CONFIGS: MEASURED LOOKUP COMPARISON")
        print("================================================================================")
        affected = [
            ("cpu", "mlp-256w-4l", 1),
            ("cpu", "conv-96c-4l", 8),
            ("cpu", "conv-96c-4l", 32),
            ("dml:0", "conv-96c-4l", 32),
            ("dml:1", "conv-96c-4l", 32),
        ]
        print(f"{'Device':<8} | {'Model':<15} | {'Batch':<5} | {'Old (w/ Single)':<18} | {'New (Sustained Only)':<22} | {'Delta':<10}")
        print("-" * 88)
        for dev_key, model_name, batch in affected:
            dev = session.exec(select(Device).where(Device.key == dev_key)).first()
            model = session.exec(select(AIModel).where(AIModel.name == model_name)).first()

            # 1. Old lookup (including 1-sample runs)
            old_runs = session.exec(
                select(Run).where(
                    Run.device_id == dev.id,
                    Run.ai_model_id == model.id,
                    Run.batch == batch,
                    Run.identity_suspect == False,
                    Run.session_id != None,
                ).order_by(Run.session_id.desc(), Run.id.desc())
            ).all()
            # Group by session_id
            old_sess_groups = {}
            for r in old_runs:
                if r.session_id not in old_sess_groups:
                    old_sess_groups[r.session_id] = []
                old_sess_groups[r.session_id].append(r.median_ms)
            old_latest_sid = max(old_sess_groups.keys())
            old_lookup = float(np.median(old_sess_groups[old_latest_sid]))

            # 2. New lookup (sustained only: timed_runs >= 10, warmup_runs >= 2, run_kind in sustained, verify_sustained)
            new_runs = session.exec(
                select(Run).where(
                    Run.device_id == dev.id,
                    Run.ai_model_id == model.id,
                    Run.batch == batch,
                    Run.unstable == False,
                    Run.identity_suspect == False,
                    Run.timed_runs >= 10,
                    Run.warmup_runs >= 2,
                    Run.run_kind.in_(["sustained", "verify_sustained"]),
                    Run.session_id != None,
                ).order_by(Run.session_id.desc(), Run.id.desc())
            ).all()
            new_sess_groups = {}
            for r in new_runs:
                if r.session_id not in new_sess_groups:
                    new_sess_groups[r.session_id] = []
                new_sess_groups[r.session_id].append(r.median_ms)
            new_latest_sid = max(new_sess_groups.keys())
            new_lookup = float(np.median(new_sess_groups[new_latest_sid]))

            delta_ms = new_lookup - old_lookup
            delta_pct = (delta_ms / old_lookup) * 100.0
            print(f"{dev_key:<8} | {model_name:<15} | {batch:<5} | {old_lookup:<8.3f} ms (s={old_latest_sid:<3}) | {new_lookup:<10.3f} ms (s={new_latest_sid:<3}) | {delta_pct:<+7.1f}%")

if __name__ == "__main__":
    import numpy as np
    run_comparison()
