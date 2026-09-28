import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import numpy as np
import onnxruntime as ort
from app.power import nvml_reader
from scripts.dxgi_enum import get_dxgi_adapters

adaps = get_dxgi_adapters()
for a in adaps:
    print(f"DXGI Adapter [{a['index']}]: {a['vendor_name']} - {a['description']} (LUID={a['luid']})")

model_path = "models/mlp_1024w_4l.onnx"
x = np.random.randn(8, 1024).astype(np.float32)

for dev_id in [0, 1]:
    # Idle wait so GPU power cools to idle
    time.sleep(2.0)
    
    so = ort.SessionOptions()
    so.enable_mem_pattern = False
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    sess = ort.InferenceSession(model_path, sess_options=so, providers=[("DmlExecutionProvider", {"device_id": dev_id})])
    
    # Warmup
    input_name = sess.get_inputs()[0].name
    for _ in range(5):
        sess.run(None, {input_name: x})
        
    time.sleep(0.5)
    pstate_start = nvml_reader.read_metrics().get("gpu_pstate")
    pwr_start = nvml_reader.read_metrics().get("gpu_power_w") or 0.0
    util_start = nvml_reader.read_metrics().get("gpu_util_pct") or 0.0
    
    # Run 300ms continuous load
    t_end = time.perf_counter() + 0.35
    inf_count = 0
    max_util = 0
    max_pwr = 0
    while time.perf_counter() < t_end:
        sess.run(None, {input_name: x})
        inf_count += 1
        m = nvml_reader.read_metrics()
        u = m.get("gpu_util_pct") or 0
        p = m.get("gpu_power_w") or 0.0
        if u > max_util: max_util = u
        if p > max_pwr: max_pwr = p

    m_end = nvml_reader.read_metrics()
    pstate_end = m_end.get("gpu_pstate")
    clock_end = m_end.get("gpu_clock_sm_mhz")
    
    print(f"\n--- DirectML device_id = {dev_id} ---")
    print(f"  Inferences run in 350ms: {inf_count}")
    print(f"  Start: P-state={pstate_start}, Power={pwr_start:.1f} W, Util={util_start}%")
    print(f"  Peak during load: Power={max_pwr:.1f} W, Util={max_util}%")
    print(f"  End: P-state={pstate_end}, SM Clock={clock_end} MHz")
    is_nvidia = (max_util >= 15 or max_pwr > pwr_start + 10.0)
    print(f"  -> NVML Detects NVIDIA Load: {is_nvidia}")
