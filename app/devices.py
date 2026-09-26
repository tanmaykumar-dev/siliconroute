"""Hardware device detection and ONNX Runtime session management.

Probes the local system for CPU and DirectML GPU adapters following
the verified patterns in .agents/skills/windows-ai-hardware/SKILL.md.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Optional

import onnx
from onnx import TensorProto, helper
import onnxruntime as ort
import psutil
from sqlmodel import Session, select

from app.config import MODELS_DIR
from app.db import Device

logger = logging.getLogger(__name__)


def ensure_probe_model() -> str:
    """Ensure a minimal valid ONNX probe model exists for adapter testing."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    probe_path = MODELS_DIR / "probe.onnx"
    if not probe_path.exists():
        x = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 2])
        y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 2])
        node = helper.make_node("Relu", ["X"], ["Y"], name="probe_relu")
        graph = helper.make_graph([node], "probe_graph", [x], [y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
        model.ir_version = 8
        onnx.save(model, str(probe_path))
    return str(probe_path)


def make_session(
    path: str,
    provider: str,
    device_id: Optional[int] = None,
) -> ort.InferenceSession:
    """Create an ONNX Runtime InferenceSession with device-specific options.

    Follows SKILL.md Section 2:
    - Intra-op thread count tuned to physical CPU core count.
    - DirectML requires enable_mem_pattern = False and ORT_SEQUENTIAL execution.
    """
    so = ort.SessionOptions()
    so.intra_op_num_threads = psutil.cpu_count(logical=False) or 1

    if provider == "DmlExecutionProvider":
        so.enable_mem_pattern = False
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        providers = [("DmlExecutionProvider", {"device_id": int(device_id or 0)})]
    elif provider == "QNNExecutionProvider":
        providers = [("QNNExecutionProvider", {"backend_path": "QnnHtp.dll"})]
    else:
        providers = ["CPUExecutionProvider"]

    return ort.InferenceSession(path, sess_options=so, providers=providers)


def detect_devices(probe_model_path: Optional[str] = None) -> list[dict]:
    """Detect CPU and all valid DirectML adapters on this system.

    Never guesses GPU names; DirectML indices represent adapter positions.
    """
    probe_path = probe_model_path or ensure_probe_model()
    found: list[dict] = [
        {
            "key": "cpu",
            "label": "CPU",
            "kind": "cpu",
            "provider": "CPUExecutionProvider",
            "options": {},
        }
    ]

    available_providers = ort.get_available_providers()
    if "DmlExecutionProvider" in available_providers:
        for device_id in range(4):
            try:
                sess = make_session(probe_path, "DmlExecutionProvider", device_id=device_id)
                # Verify provider was actually used and did not fall back
                if sess.get_providers()[0] != "DmlExecutionProvider":
                    break
                found.append(
                    {
                        "key": f"dml:{device_id}",
                        "label": f"DirectML GPU {device_id}",
                        "kind": "unknown",
                        "provider": "DmlExecutionProvider",
                        "options": {"device_id": device_id},
                    }
                )
            except Exception as exc:
                logger.debug("DirectML adapter %d probe failed or absent: %s", device_id, exc)
                break

    return found


def sync_devices_to_db(session: Session, probe_model_path: Optional[str] = None) -> list[Device]:
    """Sync detected hardware devices into the SQLite database.

    Preserves user labels for existing devices while updating availability.
    """
    detected = detect_devices(probe_model_path=probe_model_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    detected_keys = {d["key"] for d in detected}

    # Fetch all currently stored devices
    stored_devices = session.exec(select(Device)).all()
    stored_map = {d.key: d for d in stored_devices}

    result: list[Device] = []

    for item in detected:
        key = item["key"]
        if key in stored_map:
            dev = stored_map[key]
            dev.is_available = True
            dev.provider = item["provider"]
            dev.provider_options_json = json.dumps(item["options"])
            session.add(dev)
            result.append(dev)
        else:
            dev = Device(
                key=key,
                label=item["label"],
                kind=item["kind"],
                provider=item["provider"],
                provider_options_json=json.dumps(item["options"]),
                is_available=True,
                detected_at=now_iso,
            )
            session.add(dev)
            result.append(dev)

    # Any stored device not detected is marked unavailable
    for key, dev in stored_map.items():
        if key not in detected_keys and dev.is_available:
            dev.is_available = False
            session.add(dev)

    session.commit()
    for d in result:
        session.refresh(d)

    return result
