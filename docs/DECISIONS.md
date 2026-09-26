# Design decisions (append one line per decision: date - decision - why)

- Local web app on localhost instead of a hosted website - the whole point is on-device measurement; a cloud host cannot see the laptop's chips.
- FastAPI (Python) backend - ONNX Runtime, NVML and WMI are all Python-accessible, so one language and one process.
- SQLite in WAL mode - single local file, no server to install, readers never block the writer; busy_timeout avoids "database is locked".
- One benchmark job at a time - parallel benchmarks steal CPU/GPU from each other and corrupt measurements.
- ONNX Runtime execution providers - the same model file runs on CPU, each DirectML GPU, and (later) the Snapdragon NPU via QNN.
- Three predictor forms chosen per device by leave-one-out error - no single formula fits every chip; honest model selection.
- Router judged by decision accuracy and regret vs baselines (always-CPU, always-GPU, ORT policy) - ranking matters more than exact milliseconds.
- Native FastAPI SSE for live telemetry - simpler than WebSockets for one-way server-to-browser streams.
- No fake numbers in app code - every value traces back to a stored measurement; unavailable sensors show "not available".
- 2026-09-27 - DirectML probe without hardcoded names: query adapters 0..3 via minimal ONNX probe model session and verify sess.get_providers()[0] == 'DmlExecutionProvider' - DirectML indices are adapter positions, never guess GPU names.
- 2026-09-27 - CPU name resolution from Windows registry - platform.processor() returns generic family string on Windows; registry contains friendly brand name.
- 2026-09-27 - Exact synthetic FLOPs and parameter formulas matching SPEC Section 3 - enables principled predictor fits without guessing model compute requirements.
- 2026-09-27 - Single worker queue with in-memory lock rejecting concurrent benchmarks with HTTP 409 - prevents contention and protects timing accuracy.
- 2026-09-27 - CPU reference output verification using max relative error threshold 1e-2 - ensures chips giving corrupted numerical results are caught and flagged.
- 2026-09-27 - Adaptive inner-loop timing for sub-millisecond runs - loops k times per sample so sample duration >= 1 ms, preventing micro-jitter distortion on tiny models.
- 2026-09-27 - Robust spread metric (p90 - p10) / median with threshold 0.30 - avoids false 'unstable' flags caused by isolated background OS scheduler spikes.
- 2026-09-27 - DML duplicate adapter check via bit-identical outputs and <5% median diff across >= 3 runs - disables alias adapters without deleting history or guessing names.
- 2026-09-27 - Added 'software' device kind to accommodate Microsoft Basic Render Driver or CPU emulation identified in Phase 3.
