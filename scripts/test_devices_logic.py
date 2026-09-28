import ctypes
from ctypes import wintypes
import json
import logging
import time
from typing import Optional, Any
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.power import nvml_reader

logger = logging.getLogger(__name__)

# DXGI ctypes structures
class GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', wintypes.DWORD),
        ('Data2', wintypes.WORD),
        ('Data3', wintypes.WORD),
        ('Data4', wintypes.BYTE * 8)
    ]

class LUID(ctypes.Structure):
    _fields_ = [('LowPart', wintypes.DWORD), ('HighPart', wintypes.LONG)]

class DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [
        ('Description', wintypes.WCHAR * 128),
        ('VendorId', wintypes.UINT),
        ('DeviceId', wintypes.UINT),
        ('SubSysId', wintypes.UINT),
        ('Revision', wintypes.UINT),
        ('DedicatedVideoMemory', ctypes.c_size_t),
        ('DedicatedSystemMemory', ctypes.c_size_t),
        ('SharedSystemMemory', ctypes.c_size_t),
        ('AdapterLuid', LUID),
        ('Flags', wintypes.UINT)
    ]

IID_IDXGIFactory1 = GUID(0x770aae78, 0xf26f, 0x4dba, (wintypes.BYTE * 8)(*bytes.fromhex('a829253c83d1b387')))

def get_dxgi_adapters() -> list[dict]:
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

if __name__ == "__main__":
    adaps = get_dxgi_adapters()
    print("Enumerated DXGI Adapters:")
    for a in adaps:
        print(f"  [{a['index']}]: {a['vendor_name']} ({a['vendor_id']}) - {a['description']} LUID={a['luid']}")
