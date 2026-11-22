from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class FpsSample:
    fps: float | None
    source: str  # rtss | none
    detail: str = ""


class FpsMonitor:
    """
    Best-effort FPS via RivaTuner Statistics Server shared memory.
    Opens existing mapping only — never creates a fake block.
    """

    _MAPPING_NAME = "RTSSSharedMemoryV2"

    def sample(self) -> FpsSample:
        try:
            return self._sample_rtss()
        except Exception as exc:  # noqa: BLE001
            return FpsSample(None, "none", str(exc)[:80])

    def _sample_rtss(self) -> FpsSample:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        OpenFileMappingW = kernel32.OpenFileMappingW
        OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        OpenFileMappingW.restype = wintypes.HANDLE

        MapViewOfFile = kernel32.MapViewOfFile
        MapViewOfFile.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_size_t,
        ]
        MapViewOfFile.restype = wintypes.LPVOID

        UnmapViewOfFile = kernel32.UnmapViewOfFile
        UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
        UnmapViewOfFile.restype = wintypes.BOOL

        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL

        FILE_MAP_READ = 0x0004
        handle = OpenFileMappingW(FILE_MAP_READ, False, self._MAPPING_NAME)
        if not handle:
            return FpsSample(None, "none", "未偵測到 RTSS")

        view = MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 128 * 1024)
        if not view:
            CloseHandle(handle)
            return FpsSample(None, "none", "無法對應 RTSS 記憶體")

        try:
            buf = ctypes.string_at(view, 128 * 1024)
            if len(buf) < 24:
                return FpsSample(None, "none", "RTSS 記憶體過短")

            signature, version = struct.unpack_from("<II", buf, 0)
            if signature != 0x52545353:  # 'RTSS'
                return FpsSample(None, "none", "RTSS 簽名不符")

            if version < 0x00020000:
                return FpsSample(None, "none", f"RTSS 版本過舊 ({version:#x})")

            entry_size, arr_offset, arr_size = struct.unpack_from("<III", buf, 0x08)
            if entry_size < 0x100 or arr_size <= 0 or arr_offset <= 0:
                return FpsSample(None, "none", "RTSS 結構無法解析")

            best_fps = 0.0
            best_name = ""
            for i in range(min(arr_size, 256)):
                off = arr_offset + i * entry_size
                if off + 0x100 > len(buf):
                    break
                pid = struct.unpack_from("<I", buf, off)[0]
                if pid == 0:
                    continue
                name_bytes = bytes(buf[off + 0x0C : off + 0x0C + 260]).split(b"\x00", 1)[0]
                try:
                    name = name_bytes.decode("utf-8", "ignore") or name_bytes.decode(
                        "mbcs", "ignore"
                    )
                except Exception:
                    name = ""

                fps = 0.0
                for rel in (0x2C, 0x30, 0x34, 0x40, 0x44):
                    try:
                        candidate = struct.unpack_from("<f", buf, off + rel)[0]
                    except struct.error:
                        continue
                    if 1.0 <= candidate <= 1000.0:
                        fps = candidate
                        break
                if fps > best_fps:
                    best_fps = fps
                    best_name = name

            if best_fps <= 0:
                return FpsSample(None, "rtss", "RTSS 已連線但尚無 FPS")
            detail = best_name.split("\\")[-1] if best_name else "RTSS"
            return FpsSample(best_fps, "rtss", detail)
        finally:
            UnmapViewOfFile(view)
            CloseHandle(handle)
