"""Hardware device detection and ONNX Runtime session management.

Probes the local system for CPU and DirectML GPU adapters following
the verified patterns in .agents/skills/windows-ai-hardware/SKILL.md.
Uses in-process DXGI adapter enumeration and an empirical NVML load-fingerprint
to ensure rock-solid hardware identity mapping across Windows DirectML reorderings.
"""

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Optional, Any

import numpy as np
import onnx
from onnx import TensorProto, helper
import onnxruntime as ort
import psutil
from sqlmodel import Session, select

from app.config import MODELS_DIR
from app.db import Device
from app.power import nvml_reader

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# DXGI Adapter Enumeration via dxgi.dll
# -----------------------------------------------------------------------------

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

class DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [
        ("Description", wintypes.WCHAR * 128),
        ("VendorId", wintypes.UINT),
        ("DeviceId", wintypes.UINT),
        ("SubSysId", wintypes.UINT),
        ("Revision", wintypes.UINT),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("AdapterLuid", LUID),
        ("Flags", wintypes.UINT),
    ]

IID_IDXGIFactory1 = GUID(0x770AAE78, 0xF26F, 0x4DBA, (wintypes.BYTE * 8)(*bytes.fromhex("a829253c83d1b387")))


def get_dxgi_adapters() -> list[dict[str, Any]]:
    """Enumerate hardware DXGI adapters in the current process using dxgi.dll."""
    try:
        dxgi = ctypes.oledll.dxgi
        factory = ctypes.c_void_p()
        hr = dxgi.CreateDXGIFactory1(ctypes.byref(IID_IDXGIFactory1), ctypes.byref(factory))
        if hr != 0 or not factory.value:
            return []

        vtable = ctypes.cast(ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p)).contents, ctypes.POINTER(ctypes.c_void_p))
        EnumAdapters1_proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
        EnumAdapters1 = EnumAdapters1_proto(vtable[12])

        GetDesc1_proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(DXGI_ADAPTER_DESC1))

        adapters = []
        for i in range(8):
            adapter = ctypes.c_void_p()
            try:
                hr = EnumAdapters1(factory, i, ctypes.byref(adapter))
                if hr != 0 or not adapter.value:
                    break
            except Exception:
                break

            avtable = ctypes.cast(ctypes.cast(adapter, ctypes.POINTER(ctypes.c_void_p)).contents, ctypes.POINTER(ctypes.c_void_p))
            GetDesc1 = GetDesc1_proto(avtable[10])
            desc = DXGI_ADAPTER_DESC1()
            GetDesc1(adapter, ctypes.byref(desc))

            luid_str = f"{desc.AdapterLuid.HighPart}:{desc.AdapterLuid.LowPart}"
            vendor_hex = f"0x{desc.VendorId:04X}"
            vendor_name = (
                "NVIDIA" if desc.VendorId == 0x10DE else (
                    "AMD" if desc.VendorId == 0x1002 else (
                        "Intel" if desc.VendorId == 0x8086 else "Unknown"
                    )
                )
            )
            is_software = bool(desc.Flags & 2)

            adapters.append({
                "index": i,
                "description": desc.Description,
                "vendor_id": vendor_hex,
                "vendor_name": vendor_name,
                "device_id": desc.DeviceId,
                "luid": luid_str,
                "is_software": is_software,
            })

        Release_proto = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)
        Release = Release_proto(vtable[2])
        Release(factory)
        return adapters
    except Exception as exc:
        logger.error("DXGI enumeration failed: %s", exc)
        return []


# Cached verified GPU mapping: e.g. {"NVIDIA": {...}, "AMD": {...}}
_verified_gpu_mapping: dict[str, dict[str, Any]] = {}


def verify_gpu_identity_mapping(probe_model_path: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Run an identity fingerprint to confirm or swap DirectML adapter assignments.
    
    Runs 300 ms of load on the adapter candidate believed to be NVIDIA.
    Reads NVML telemetry: if GPU util, power, or SM clock jumps, NVIDIA mapping is confirmed.
    If not, tests the other adapter; if that triggers NVML, the mapping is swapped and a warning logged.
    """
    global _verified_gpu_mapping
    adapters = [a for a in get_dxgi_adapters() if not a.get("is_software")]
    if not adapters:
        return {}

    nvidia_cand = next((a for a in adapters if a["vendor_name"] == "NVIDIA"), None)
    amd_cand = next((a for a in adapters if a["vendor_name"] == "AMD"), None)

    if not nvidia_cand:
        _verified_gpu_mapping = {a["vendor_name"]: a for a in adapters}
        return _verified_gpu_mapping

    # If NVML is not available, rely strictly on DXGI VendorId
    if not nvml_reader.is_available:
        mapping = {}
        if nvidia_cand: mapping["NVIDIA"] = nvidia_cand
        if amd_cand: mapping["AMD"] = amd_cand
        _verified_gpu_mapping = mapping
        return mapping

    probe_path = probe_model_path or ensure_probe_model()
    # Test candidate NVIDIA adapter
    cand_idx = nvidia_cand["index"]
    try:
        so = ort.SessionOptions()
        so.enable_mem_pattern = False
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        sess = ort.InferenceSession(probe_path, sess_options=so, providers=[("DmlExecutionProvider", {"device_id": cand_idx})])
        x = np.array([[1.0, 2.0]], dtype=np.float32)
        inp = sess.get_inputs()[0].name
        
        # Warmup
        for _ in range(5):
            sess.run(None, {inp: x})

        time.sleep(0.3)
        m0 = nvml_reader.read_metrics()
        pwr0 = m0.get("gpu_power_w") or 0.0

        t_end = time.perf_counter() + 0.30
        max_util = 0.0
        max_pwr = 0.0
        while time.perf_counter() < t_end:
            sess.run(None, {inp: x})
            m = nvml_reader.read_metrics()
            u = m.get("gpu_util_pct") or 0.0
            p = m.get("gpu_power_w") or 0.0
            if u > max_util: max_util = u
            if p > max_pwr: max_pwr = p

        m_end = nvml_reader.read_metrics()
        clock_end = m_end.get("gpu_clock_sm_mhz") or 0
        pstate_end = m_end.get("gpu_pstate")

        # Confirmation heuristic: util > 10% or power rise > 8W or high SM clock / P0-P2
        nvidia_confirmed = (max_util >= 10.0 or max_pwr > pwr0 + 8.0 or clock_end > 1200 or (pstate_end is not None and pstate_end <= 2))

        if not nvidia_confirmed and amd_cand:
            # Check if other adapter triggers NVML
            other_idx = amd_cand["index"]
            sess_other = ort.InferenceSession(probe_path, sess_options=so, providers=[("DmlExecutionProvider", {"device_id": other_idx})])
            for _ in range(5):
                sess_other.run(None, {inp: x})
            t_end2 = time.perf_counter() + 0.30
            other_max_util = 0.0
            while time.perf_counter() < t_end2:
                sess_other.run(None, {inp: x})
                m2 = nvml_reader.read_metrics()
                u2 = m2.get("gpu_util_pct") or 0.0
                if u2 > other_max_util: other_max_util = u2
            
            if other_max_util >= 10.0:
                logger.warning(
                    "DirectML adapter inversion detected! Swapping NVIDIA adapter from %d to %d (AMD to %d)",
                    cand_idx, other_idx, cand_idx
                )
                nvidia_cand, amd_cand = amd_cand, nvidia_cand

        mapping = {}
        if nvidia_cand: mapping["NVIDIA"] = nvidia_cand
        if amd_cand: mapping["AMD"] = amd_cand
        _verified_gpu_mapping = mapping
        logger.info(
            "Hardware GPU mapping verified: NVIDIA=Adapter %d (%s), AMD=Adapter %d (%s)",
            nvidia_cand["index"] if nvidia_cand else -1,
            nvidia_cand.get("luid", "N/A") if nvidia_cand else "",
            amd_cand["index"] if amd_cand else -1,
            amd_cand.get("luid", "N/A") if amd_cand else "",
        )
        return mapping
    except Exception as exc:
        logger.error("Fingerprint test encountered error: %s; falling back to DXGI vendor table", exc)
        mapping = {}
        if nvidia_cand: mapping["NVIDIA"] = nvidia_cand
        if amd_cand: mapping["AMD"] = amd_cand
        _verified_gpu_mapping = mapping
        return mapping


def resolve_adapter_for_device(device: Device) -> Optional[int]:
    """Resolve the verified DXGI adapter index for a physical Device."""
    if device.kind == "cpu" or device.provider != "DmlExecutionProvider":
        return None

    global _verified_gpu_mapping
    if not _verified_gpu_mapping:
        verify_gpu_identity_mapping()

    is_nvidia = (
        device.vendor == "NVIDIA"
        or (device.label and "NVIDIA" in device.label)
        or (device.vendor_id == "0x10DE")
        or device.key == "dml:1"
    )
    is_amd = (
        device.vendor == "AMD"
        or (device.label and "Radeon" in device.label)
        or (device.vendor_id == "0x1002")
        or device.key == "dml:0"
    )

    if is_nvidia and "NVIDIA" in _verified_gpu_mapping:
        return _verified_gpu_mapping["NVIDIA"]["index"]
    if is_amd and "AMD" in _verified_gpu_mapping:
        return _verified_gpu_mapping["AMD"]["index"]

    # Fallback: parse provider_options_json
    try:
        opts = json.loads(device.provider_options_json or "{}")
        if "device_id" in opts:
            return int(opts["device_id"])
    except Exception:
        pass

    return 0


# -----------------------------------------------------------------------------
# Session Creation & Device Management
# -----------------------------------------------------------------------------

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
    device: Optional[Device] = None,
) -> ort.InferenceSession:
    """Create an ONNX Runtime InferenceSession with device-specific options.

    Follows SKILL.md Section 2:
    - Intra-op thread count tuned to physical CPU core count.
    - DirectML requires enable_mem_pattern = False and ORT_SEQUENTIAL execution.
    - If device is passed, automatically resolves the physical DXGI adapter index.
    """
    so = ort.SessionOptions()
    so.intra_op_num_threads = psutil.cpu_count(logical=False) or 1

    if provider == "DmlExecutionProvider":
        so.enable_mem_pattern = False
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        if device is not None:
            resolved_id = resolve_adapter_for_device(device)
            if resolved_id is not None:
                device_id = resolved_id
        providers = [("DmlExecutionProvider", {"device_id": int(device_id or 0)})]
    elif provider == "QNNExecutionProvider":
        providers = [("QNNExecutionProvider", {"backend_path": "QnnHtp.dll"})]
    else:
        providers = ["CPUExecutionProvider"]

    return ort.InferenceSession(path, sess_options=so, providers=providers)


def detect_devices(probe_model_path: Optional[str] = None) -> list[dict[str, Any]]:
    """Detect CPU and all valid DirectML adapters on this system via DXGI and ORT."""
    probe_path = probe_model_path or ensure_probe_model()
    found: list[dict[str, Any]] = [
        {
            "key": "cpu",
            "label": "CPU",
            "kind": "cpu",
            "provider": "CPUExecutionProvider",
            "options": {},
            "vendor": "CPU",
            "vendor_id": None,
            "luid": None,
        }
    ]

    adapters = [a for a in get_dxgi_adapters() if not a.get("is_software")]
    available_providers = ort.get_available_providers()

    if "DmlExecutionProvider" in available_providers:
        seen_vendors: set[str] = set()
        for a in adapters:
            idx = a["index"]
            vname = a["vendor_name"]
            if vname in seen_vendors and vname != "Unknown":
                continue

            try:
                sess = make_session(probe_path, "DmlExecutionProvider", device_id=idx)
                if sess.get_providers()[0] != "DmlExecutionProvider":
                    continue

                seen_vendors.add(vname)
                kind = "dgpu" if vname == "NVIDIA" else ("igpu" if vname in ("AMD", "Intel") else "unknown")
                # Stable logical key: dml:0 for AMD iGPU, dml:1 for NVIDIA dGPU
                key = "dml:1" if vname == "NVIDIA" else ("dml:0" if vname == "AMD" else f"dml:{idx}")
                label = a["description"]

                found.append({
                    "key": key,
                    "label": label,
                    "kind": kind,
                    "provider": "DmlExecutionProvider",
                    "options": {"device_id": idx, "vendor": vname, "luid": a["luid"]},
                    "vendor": vname,
                    "vendor_id": a["vendor_id"],
                    "luid": a["luid"],
                })
            except Exception as exc:
                logger.debug("DirectML adapter %d probe failed: %s", idx, exc)

    return found


def sync_devices_to_db(session: Session, probe_model_path: Optional[str] = None) -> list[Device]:
    """Sync detected hardware devices into the SQLite database with verified physical mapping."""
    detected = detect_devices(probe_model_path=probe_model_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    detected_keys = {d["key"] for d in detected}

    stored_devices = session.exec(select(Device)).all()
    stored_map = {d.key: d for d in stored_devices}

    result: list[Device] = []

    for item in detected:
        key = item["key"]
        if key in stored_map:
            dev = stored_map[key]
            if not dev.unavailable_reason:
                dev.is_available = True
            dev.provider = item["provider"]
            dev.provider_options_json = json.dumps(item["options"])
            dev.vendor = item.get("vendor")
            dev.vendor_id = item.get("vendor_id")
            dev.luid = item.get("luid")
            dev.label = item["label"]
            dev.kind = item["kind"]
            session.add(dev)
            result.append(dev)
        else:
            dev = Device(
                key=key,
                label=item["label"],
                kind=item["kind"],
                provider=item["provider"],
                provider_options_json=json.dumps(item["options"]),
                vendor=item.get("vendor"),
                vendor_id=item.get("vendor_id"),
                luid=item.get("luid"),
                is_available=True,
                detected_at=now_iso,
            )
            session.add(dev)
            result.append(dev)

    for key, dev in stored_map.items():
        if key not in detected_keys and dev.is_available:
            dev.is_available = False
            session.add(dev)

    session.commit()
    for d in result:
        session.refresh(d)

    return result
