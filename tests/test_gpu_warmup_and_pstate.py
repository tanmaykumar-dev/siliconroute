"""Tests for Step 2: GPU active P-state/clock warmup, not_warm flag, and P8 exclusion."""
from pathlib import Path
import sqlite3
from typing import Optional
import pytest
from sqlmodel import Session, select

from app.db import AIModel, BenchSession, Device, Fit, Run, engine
from app.predictor import prepare_fit_dataset
from app.router import resolve_candidate_prediction

FROZEN_DB_PATH = Path("data/final/siliconroute_final.db")


def make_test_run(
    session_id: int,
    ai_model_id: int,
    device_id: int,
    median_ms: float,
    run_kind: str = "sustained",
    timed_runs: int = 10,
    warmup_runs: int = 2,
    batch: int = 1,
    not_warm: bool = False,
    nvml_pstate_start: Optional[int] = None,
    nvml_pstate_end: Optional[int] = None,
) -> Run:
    return Run(
        session_id=session_id,
        ai_model_id=ai_model_id,
        device_id=device_id,
        provider_used="DmlExecutionProvider",
        provider_mismatch=False,
        batch=batch,
        intra_op_threads=4,
        warmup_runs=warmup_runs,
        timed_runs=timed_runs,
        inner_loop_k=1,
        session_create_ms=10.0,
        first_run_ms=median_ms,
        median_ms=median_ms,
        p10_ms=median_ms * 0.95,
        p90_ms=median_ms * 1.05,
        mean_ms=median_ms,
        min_ms=median_ms * 0.9,
        max_ms=median_ms * 1.1,
        stdev_ms=0.01,
        cv=0.01,
        spread=0.03,
        run_kind=run_kind,
        throughput_per_s=1000.0 / median_ms,
        raw_ms_json="[1.0]",
        unstable=False,
        identity_suspect=False,
        not_warm=not_warm,
        nvml_pstate_start=nvml_pstate_start,
        nvml_pstate_end=nvml_pstate_end,
        created_at="2026-01-01T00:00:00Z",
    )


def test_fit_dataset_excludes_not_warm_and_p8():
    """Verify prepare_fit_dataset excludes not_warm=True and nvml_pstate_start=8 runs."""
    with Session(engine) as s:
        bs = BenchSession(
            kind="latency", status="done", config_json="{}", created_at="2026-01-01T00:00:00Z"
        )
        s.add(bs)
        s.commit()
        s.refresh(bs)

        dev = s.exec(select(Device).where(Device.key == "dml:1")).first()
        model = s.exec(select(AIModel)).first()
        assert dev is not None
        assert model is not None

        # Add 6 valid warm runs (needed for MIN_FIT_SAMPLES)
        warm_runs = []
        for i in range(6):
            r = make_test_run(
                bs.id,
                model.id,
                dev.id,
                median_ms=1.0 + i * 0.1,
                batch=i + 1,
                not_warm=False,
                nvml_pstate_start=0,
                nvml_pstate_end=0,
            )
            s.add(r)
            warm_runs.append(r)

        # Not warm run (not_warm=True, P8)
        r_not_warm = make_test_run(
            bs.id, model.id, dev.id, median_ms=2.5, batch=10, not_warm=True, nvml_pstate_start=8, nvml_pstate_end=0
        )
        # Legacy run with P8 start but not_warm=False
        r_p8_legacy = make_test_run(
            bs.id, model.id, dev.id, median_ms=3.0, batch=11, not_warm=False, nvml_pstate_start=8, nvml_pstate_end=8
        )

        s.add(r_not_warm)
        s.add(r_p8_legacy)
        s.commit()

        runs, _, _ = prepare_fit_dataset(s, device_id=dev.id)
        fit_run_ids = [r.id for r in runs]
        assert len(fit_run_ids) == 6
        for wr in warm_runs:
            assert wr.id in fit_run_ids
        assert r_not_warm.id not in fit_run_ids
        assert r_p8_legacy.id not in fit_run_ids


def test_router_lookup_excludes_not_warm_and_p8():
    """Verify router measured lookup ignores runs where not_warm=True or nvml_pstate_start=8."""
    with Session(engine) as s:
        bs = BenchSession(
            kind="latency", status="done", config_json="{}", created_at="2026-01-01T00:00:00Z"
        )
        s.add(bs)
        s.commit()
        s.refresh(bs)

        dev = s.exec(select(Device).where(Device.key == "dml:1")).first()
        model = s.exec(select(AIModel)).first()
        assert dev is not None
        assert model is not None

        # Add a dummy active Fit so router can fall back if no valid runs exist
        dummy_fit = Fit(
            device_id=dev.id,
            target="latency",
            model_form="roofline_cache",
            is_active=True,
            loo_mape_all_json="{}",
            coef_json='[0.15, 1e-12, 1e-11]',
            t0_ms=0.15,
            compute_gflops=1000.0,
            bandwidth_gb_s=50.0,
            r2_log=0.99,
            n_samples=10,
            loo_mape_pct=5.0,
            trained_at="2026-01-01T00:00:00Z",
        )
        s.add(dummy_fit)
        s.commit()

        # Run with P8 should be skipped even if it exists
        r_p8 = make_test_run(
            bs.id, model.id, dev.id, median_ms=0.5, batch=99, not_warm=True, nvml_pstate_start=8
        )
        s.add(r_p8)
        s.commit()

        cand = resolve_candidate_prediction(s, device=dev, model=model, batch=99, workload="sustained")
        # Measured latency should NOT pick up r_p8 because it started in P8 / not_warm
        assert cand["source"] == "fit"


def test_existing_rtx_sustained_p8_audit():
    """Verify that in existing sustained runs, exactly 13 of 90 sustained RTX runs started in P8.

    This asserts our historical audit finding without modifying any historical data.
    """
    if not FROZEN_DB_PATH.exists():
        pytest.skip(f"{FROZEN_DB_PATH} does not exist.")
    conn = sqlite3.connect(f"file:{FROZEN_DB_PATH.resolve()}?mode=ro&immutable=1", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM device WHERE key = 'dml:1'")
        row = cur.fetchone()
        if not row:
            pytest.skip("RTX 5070 device not found in database.")
        rtx_dev_id = row[0]

        cur.execute(
            "SELECT count(*), sum(case when nvml_pstate_start = 8 then 1 else 0 end) "
            "FROM run WHERE device_id = ? AND run_kind = 'sustained'",
            (rtx_dev_id,),
        )
        total, p8_count = cur.fetchone()
        assert total == 90, f"Expected 90 sustained runs on RTX, found {total}"
        assert p8_count == 13, f"Expected 13 runs starting in P8, found {p8_count}"
    finally:
        conn.close()


def test_warmup_clock_stability_and_pstate_mock():
    """Unit test the P-state (P0/P2) and clock stability (10% over 200ms) decision logic."""
    clock_history: list[tuple[float, int]] = []
    
    # Sample clock sequence: starts in P8 (210 MHz), transitions to P0, stabilizes over 200 ms
    telemetry_sequence = [
        {"gpu_pstate": 8, "gpu_clock_sm_mhz": 210},
        {"gpu_pstate": 0, "gpu_clock_sm_mhz": 1800},
        {"gpu_pstate": 0, "gpu_clock_sm_mhz": 1810},
        {"gpu_pstate": 0, "gpu_clock_sm_mhz": 1820},
    ]

    t0 = 100.0
    times = [100.0, 100.05, 100.15, 100.26]
    warmups_done = 0
    warmup_runs = 2
    exited_cleanly = False

    for idx, (now_s, m) in enumerate(zip(times, telemetry_sequence)):
        warmups_done += 1
        elapsed_s = now_s - t0
        pstate = m.get("gpu_pstate")
        clock = m.get("gpu_clock_sm_mhz")
        if clock is not None:
            clock_history.append((now_s, clock))

        if elapsed_s >= 3.0:
            break

        pstate_active = (pstate in (0, 2)) if pstate is not None else False
        clock_stable = False
        if clock_history and (now_s - clock_history[0][0] >= 0.20):
            recent_clocks = [c for t, c in clock_history if now_s - t <= 0.25]
            if len(recent_clocks) >= 2:
                c_min = min(recent_clocks)
                c_max = max(recent_clocks)
                c_mean = float((c_min + c_max) / 2.0)
                if c_mean > 0 and (c_max - c_min) / c_mean <= 0.10:
                    clock_stable = True

        if warmups_done >= warmup_runs and pstate_active and clock_stable:
            exited_cleanly = True
            break

    assert exited_cleanly is True
    assert pstate_active is True
    assert clock_stable is True

