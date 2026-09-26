"""
SiliconRoute - Week 1 benchmark
--------------------------------
Builds small test AI models of different sizes, runs each one on every
chip it can find (CPU, and each GPU through DirectML), and saves the
timings to results/benchmark_results.csv plus a graph.

Run:  python benchmark_v1.py
Tip:  keep Task Manager > Performance open while it runs and watch
      which GPU graph jumps. That tells you which DirectML device id
      is your AMD Radeon and which is your NVIDIA card.
"""

import csv
import os
import statistics
import time
from datetime import datetime

import numpy as np
import onnx
import onnxruntime as ort
import psutil
from onnx import TensorProto, helper, numpy_helper

MODEL_DIR = "models"
RESULTS_DIR = "results"
RESULTS_CSV = os.path.join(RESULTS_DIR, "benchmark_results.csv")

# Model sizes to test: (width, number of layers).
# Parameters = width * width * layers. Bigger = more math + more memory.
MODEL_SIZES = [(256, 4), (512, 4), (1024, 4), (2048, 4), (4096, 4)]
BATCH_SIZES = [1, 32]
WARMUP_RUNS = 5   # first runs are slow (setup), so we don't count them
TIMED_RUNS = 30


def make_test_model(width, layers, path):
    """Create a simple neural network (MatMul + ReLU layers) as an ONNX file."""
    rng = np.random.default_rng(seed=0)
    nodes, weights = [], []
    prev = "x"
    for i in range(layers):
        w = (rng.standard_normal((width, width)) / np.sqrt(width)).astype(np.float32)
        weights.append(numpy_helper.from_array(w, name=f"W{i}"))
        nodes.append(helper.make_node("MatMul", [prev, f"W{i}"], [f"mm{i}"]))
        nodes.append(helper.make_node("Relu", [f"mm{i}"], [f"h{i}"]))
        prev = f"h{i}"
    inp = helper.make_tensor_value_info("x", TensorProto.FLOAT, ["batch", width])
    out = helper.make_tensor_value_info(prev, TensorProto.FLOAT, ["batch", width])
    graph = helper.make_graph(nodes, "test_mlp", [inp], [out], weights)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8  # works with most onnxruntime versions
    onnx.save(model, path)
    return width * width * layers


def find_devices():
    """List every chip we can run on: CPU always, plus each DirectML GPU."""
    devices = [("CPU", "CPUExecutionProvider", {})]
    if "DmlExecutionProvider" in ort.get_available_providers():
        probe = os.path.join(MODEL_DIR, "probe.onnx")
        make_test_model(64, 1, probe)
        for device_id in range(4):  # laptops rarely have more than 2-3 GPUs
            try:
                make_session(probe, "DmlExecutionProvider", {"device_id": device_id})
                devices.append((f"GPU{device_id} (DirectML)", "DmlExecutionProvider",
                                {"device_id": device_id}))
            except Exception:
                break  # no more GPUs
    else:
        print("DirectML not found - testing CPU only. "
              "Did you install onnxruntime-directml?")
    return devices


def make_session(path, provider, options):
    so = ort.SessionOptions()
    if provider == "DmlExecutionProvider":
        # DirectML needs these two settings (from the onnxruntime docs)
        so.enable_mem_pattern = False
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(path, sess_options=so, providers=[(provider, options)])


def benchmark(path, width, batch, provider, options):
    sess = make_session(path, provider, options)
    actual_provider = sess.get_providers()[0]  # checks it didn't silently fall back to CPU
    x = np.random.default_rng(1).standard_normal((batch, width)).astype(np.float32)
    for _ in range(WARMUP_RUNS):
        sess.run(None, {"x": x})
    times_ms = []
    for _ in range(TIMED_RUNS):
        start = time.perf_counter()
        sess.run(None, {"x": x})
        times_ms.append((time.perf_counter() - start) * 1000)
    return actual_provider, times_ms


def battery_state():
    b = psutil.sensors_battery()
    if b is None:
        return "", ""
    return b.percent, b.power_plugged


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print("onnxruntime version:", ort.__version__)
    print("Available providers:", ort.get_available_providers())

    devices = find_devices()
    print("Devices found:", [d[0] for d in devices], "\n")

    new_file = not os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "device", "provider_used", "width", "layers",
                             "params", "model_mb", "batch", "median_ms", "mean_ms",
                             "min_ms", "stdev_ms", "items_per_sec",
                             "battery_percent", "plugged_in"])
        for width, layers in MODEL_SIZES:
            path = os.path.join(MODEL_DIR, f"mlp_w{width}_l{layers}.onnx")
            params = make_test_model(width, layers, path)
            model_mb = os.path.getsize(path) / 1e6
            for device_name, provider, options in devices:
                for batch in BATCH_SIZES:
                    try:
                        used, t = benchmark(path, width, batch, provider, options)
                    except Exception as e:
                        print(f"  FAILED {device_name} w={width} batch={batch}: {e}")
                        continue
                    median = statistics.median(t)
                    pct, plugged = battery_state()
                    writer.writerow([datetime.now().isoformat(timespec="seconds"),
                                     device_name, used, width, layers, params,
                                     round(model_mb, 2), batch, round(median, 4),
                                     round(statistics.mean(t), 4), round(min(t), 4),
                                     round(statistics.stdev(t), 4),
                                     round(batch / (median / 1000), 1), pct, plugged])
                    print(f"{device_name:18} params={params:>11,} batch={batch:>3} "
                          f"median={median:8.3f} ms")
    print(f"\nSaved results to {RESULTS_CSV}")
    make_graph()


def make_graph():
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to get the graph.")
        return
    rows = list(csv.DictReader(open(RESULTS_CSV)))
    plt.figure(figsize=(9, 6))
    for device in sorted({r["device"] for r in rows}):
        for batch in sorted({int(r["batch"]) for r in rows}):
            pts = sorted((int(r["params"]), float(r["median_ms"])) for r in rows
                         if r["device"] == device and int(r["batch"]) == batch)
            if pts:
                xs, ys = zip(*pts)
                plt.plot(xs, ys, marker="o", label=f"{device}, batch {batch}")
    plt.xscale("log")
    plt.yscale("log")
    plt.xlabel("Model size (parameters)")
    plt.ylabel("Median time per run (ms)")
    plt.title("Which chip is fastest at which model size?")
    plt.grid(True, which="both", alpha=0.3)
    plt.legend()
    out = os.path.join(RESULTS_DIR, "latency_vs_size.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print("Saved graph to", out)


if __name__ == "__main__":
    main()
