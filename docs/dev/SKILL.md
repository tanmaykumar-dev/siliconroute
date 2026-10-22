---
name: windows-ai-hardware
description: Verified code patterns for ONNX Runtime CPU/DirectML/QNN sessions, GPU device enumeration and the identify test, NVML GPU power/energy/temperature, WMI battery discharge rate, psutil battery, Windows power scheme, SQLite WAL pragmas with SQLModel, FastAPI native SSE fed from a background thread, a single-job worker, and weighted NNLS fitting. Use when writing or debugging devices.py, benchmark.py, energy.py, power.py, telemetry.py, jobs.py, db.py or predictor.py.
---

# Windows AI hardware patterns for SiliconRoute

Items marked TESTED were run successfully (Linux sandbox, FastAPI 0.141,
SQLModel 0.0.47). Windows-only items (DirectML, NVML, WMI) follow the official
APIs but must be verified on the laptop — print real output when you do.

## 1. SQLite engine with pragmas (TESTED: journal_mode=wal, busy_timeout=5000)
```python
from sqlalchemy import event
from sqlmodel import create_engine

engine = create_engine("sqlite:///data/siliconroute.db",
                       connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def _set_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")    # readers never block the writer
    cur.execute("PRAGMA synchronous=NORMAL")  # recommended with WAL
    cur.execute("PRAGMA busy_timeout=5000")   # wait up to 5 s instead of "database is locked"
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()
```
Rules: one `Session(engine)` per thread (`with Session(engine) as db:`),
commit quickly, batch inserts (e.g. telemetry every 10 s).

## 2. ONNX Runtime session per device
```python
import onnxruntime as ort
import psutil

def make_session(path: str, provider: str, device_id: int | None = None) -> ort.InferenceSession:
    so = ort.SessionOptions()
    so.intra_op_num_threads = psutil.cpu_count(logical=False) or 1
    if provider == "DmlExecutionProvider":
        so.enable_mem_pattern = False                        # required by DirectML
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL # required by DirectML
        providers = [("DmlExecutionProvider", {"device_id": int(device_id or 0)})]
    elif provider == "QNNExecutionProvider":                 # Snapdragon NPU (future)
        providers = [("QNNExecutionProvider", {"backend_path": "QnnHtp.dll"})]
    else:
        providers = ["CPUExecutionProvider"]
    return ort.InferenceSession(path, sess_options=so, providers=providers)

# After creating: provider_used = sess.get_providers()[0]
# Unsupported ops may still fall back to CPU inside a DML session; the
# synthetic families (MatMul, Conv, Relu, Softmax) are DML-supported.
```
Install ONLY `onnxruntime-directml` on Windows (it includes the CPU provider).
DirectML is in maintenance mode but still ships with Windows; Windows ML is
the future path (roadmap, not v1).

## 3. Detect devices (CPU + every DirectML adapter)
```python
def detect_devices(probe_model_path: str) -> list[dict]:
    found = [{"key": "cpu", "provider": "CPUExecutionProvider", "options": {}, "kind": "cpu"}]
    if "DmlExecutionProvider" in ort.get_available_providers():
        for device_id in range(4):
            try:
                s = make_session(probe_model_path, "DmlExecutionProvider", device_id)
                if s.get_providers()[0] != "DmlExecutionProvider":
                    break
                found.append({"key": f"dml:{device_id}", "provider": "DmlExecutionProvider",
                              "options": {"device_id": device_id}, "kind": "unknown"})
            except Exception:
                break   # no adapter with this index
    return found
```
Names are unknown: label them with the identify test (heavy model for 8 s on
one device; the user watches Task Manager → Performance → which GPU jumps).
If an NVIDIA GPU is visible to NVML, show its name (`nvmlDeviceGetName`) as a
HINT next to the unlabeled devices — do not auto-assign it.

## 4. NVML (NVIDIA only; package `nvidia-ml-py`, import `pynvml`)
```python
import pynvml

def nvml_open():
    try:
        pynvml.nvmlInit()
        return pynvml.nvmlDeviceGetHandleByIndex(0) if pynvml.nvmlDeviceGetCount() else None
    except pynvml.NVMLError:
        return None

def nvml_read(h) -> dict:
    out = {}
    for key, fn in {
        "gpu_power_w": lambda: pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0,      # mW -> W
        "gpu_temp_c": lambda: float(pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)),
        "gpu_util_pct": lambda: float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu),
        "gpu_mem_used_mb": lambda: pynvml.nvmlDeviceGetMemoryInfo(h).used / 1e6,
    }.items():
        try:
            out[key] = fn()
        except pynvml.NVMLError:
            out[key] = None   # "not available"
    return out

def nvml_energy_mj(h):
    """Total energy counter in mJ since driver load; None if not supported."""
    try:
        return float(pynvml.nvmlDeviceGetTotalEnergyConsumption(h))
    except pynvml.NVMLError:
        return None
```
GPU energy for a load window = counter_after - counter_before (mJ).

## 5. Battery discharge rate via WMI (whole-laptop power when unplugged)
```python
class BatteryReader:
    """Create AND use in the same thread (COM is per-thread)."""
    def __init__(self) -> None:
        self._conn = None

    def read(self) -> dict | None:
        try:
            if self._conn is None:
                import pythoncom, wmi
                pythoncom.CoInitialize()
                self._conn = wmi.WMI(namespace="root\\wmi")
            rows = self._conn.query(
                "SELECT DischargeRate, PowerOnline FROM BatteryStatus WHERE Voltage > 0")
            if not rows:
                return None
            r = rows[0]
            return {"discharge_w": (r.DischargeRate or 0) / 1000.0,   # mW -> W
                    "power_online": bool(r.PowerOnline)}
        except Exception:
            return None
```
DischargeRate reads 0 while plugged in → energy "not available" when charging.
Firmware updates it slowly (seconds), hence 15 s idle + 30 s load windows.

## 6. psutil + power scheme
```python
import psutil, subprocess

def battery_state() -> tuple[float | None, bool | None]:
    b = psutil.sensors_battery()
    return (None, None) if b is None else (float(b.percent), bool(b.power_plugged))

def power_scheme() -> str | None:
    try:
        return subprocess.run(["powercfg", "/getactivescheme"], capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None
```
`psutil.cpu_percent(interval=None)` needs one priming call at startup.
CPU temperature is not available on Windows through psutil → "not available".

## 7. FastAPI native SSE fed by a background thread (TESTED end-to-end)
```python
import asyncio
from fastapi import Request
from fastapi.sse import EventSourceResponse   # FastAPI >= 0.135

subscribers: set[asyncio.Queue] = set()
state = {"loop": None}          # set in lifespan: state["loop"] = asyncio.get_running_loop()

def _safe_put(q: asyncio.Queue, item: dict) -> None:
    if not q.full():
        q.put_nowait(item)

def publish(sample: dict) -> None:            # call from the sampler THREAD
    loop = state["loop"]
    if loop is not None:
        for q in list(subscribers):
            loop.call_soon_threadsafe(_safe_put, q, sample)

@router.get("/api/telemetry/stream", response_class=EventSourceResponse)
async def telemetry_stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    subscribers.add(q)
    try:
        while not await request.is_disconnected():
            try:
                yield await asyncio.wait_for(q.get(), timeout=5)
            except asyncio.TimeoutError:
                continue
    finally:
        subscribers.discard(q)
```
Browser: `const es = new EventSource('/api/telemetry/stream'); es.onmessage = e => update(JSON.parse(e.data));`

## 8. Single job worker (TESTED: second submit while busy is refused)
```python
import queue, threading

_jobs: queue.Queue = queue.Queue()
_lock = threading.Lock()
current = {"session_id": None, "done": 0, "total": 0, "item": None, "cancel": False}

def try_submit(session_id: int, fn) -> bool:
    with _lock:
        if current["session_id"] is not None:
            return False                      # API turns this into 409
        current.update(session_id=session_id, done=0, total=0, item=None, cancel=False)
    _jobs.put((session_id, fn))
    return True

def worker_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            session_id, fn = _jobs.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            fn(current)                        # fn updates done/total/item, checks cancel
        finally:
            with _lock:
                current["session_id"] = None
```

## 9. Weighted NNLS fit + leave-one-out (TESTED: recovers known parameters exactly)
```python
import numpy as np
from scipy.optimize import nnls

def fit_nnls(X: np.ndarray, t_ms: np.ndarray) -> np.ndarray:
    """Non-negative least squares minimising RELATIVE error (weights 1/t)."""
    w = 1.0 / t_ms
    coef, _ = nnls(X * w[:, None], t_ms * w)
    return coef

def loo_mape(X: np.ndarray, t_ms: np.ndarray, fit, predict) -> float:
    errs = []
    for i in range(len(t_ms)):
        m = np.ones(len(t_ms), bool); m[i] = False
        c = fit(X[m], t_ms[m])
        errs.append(abs(predict(X[i:i+1], c)[0] - t_ms[i]) / t_ms[i])
    return 100.0 * float(np.mean(errs))
# F1 design matrix: np.column_stack([np.ones(n), work_gflop, data_gb])
```
