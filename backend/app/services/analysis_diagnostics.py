"""Lightweight stage timing and process-memory diagnostics for local analysis."""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


logger = logging.getLogger(__name__)


def _process_memory_mb() -> tuple[float | None, float | None]:
    """Return current and peak RSS on Linux/Windows when available."""
    if sys.platform.startswith("linux"):
        try:
            values = {}
            for line in Path("/proc/self/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    values["current"] = int(line.split()[1]) / 1024
                elif line.startswith("VmHWM:"):
                    values["peak"] = int(line.split()[1]) / 1024
            return values.get("current"), values.get("peak")
        except (OSError, ValueError, IndexError):
            return None, None

    if sys.platform == "win32":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        try:
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
            psapi = ctypes.WinDLL("Psapi.dll", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ProcessMemoryCounters),
                ctypes.c_ulong,
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            success = psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(),
                ctypes.byref(counters),
                counters.cb,
            )
            if success:
                return (
                    counters.WorkingSetSize / (1024 * 1024),
                    counters.PeakWorkingSetSize / (1024 * 1024),
                )
        except (AttributeError, OSError):
            return None, None

    return None, None


def _memory_labels() -> tuple[str, str]:
    current_mb, peak_mb = _process_memory_mb()
    current_label = f"{current_mb:.1f}" if current_mb is not None else "unavailable"
    peak_label = f"{peak_mb:.1f}" if peak_mb is not None else "unavailable"
    return current_label, peak_label


def log_analysis_boundary(video_id: int, stage: str) -> None:
    """Log current and process high-water memory at an analysis boundary."""
    current_mb, peak_mb = _memory_labels()
    logger.info(
        "[analysis] video=%s stage=%s memory_mb=%s peak_memory_mb=%s",
        video_id,
        stage,
        current_mb,
        peak_mb,
    )


@contextmanager
def analysis_stage(video_id: int, stage: str) -> Iterator[dict[str, int | float]]:
    """Log safe stage boundaries, elapsed time, RSS, and numeric result counts."""
    started_at = time.perf_counter()
    measurements: dict[str, int | float] = {}
    current_mb, peak_mb = _memory_labels()
    logger.info(
        "[analysis] video=%s stage=%s start memory_mb=%s peak_memory_mb=%s",
        video_id,
        stage,
        current_mb,
        peak_mb,
    )

    try:
        yield measurements
    except Exception as error:
        current_mb, peak_mb = _memory_labels()
        logger.error(
            "[analysis] video=%s stage=%s failed duration_seconds=%.3f "
            "memory_mb=%s peak_memory_mb=%s error_type=%s",
            video_id,
            stage,
            time.perf_counter() - started_at,
            current_mb,
            peak_mb,
            type(error).__name__,
        )
        raise
    else:
        current_mb, peak_mb = _memory_labels()
        count_details = " ".join(
            f"{name}={value}" for name, value in measurements.items()
        )
        logger.info(
            "[analysis] video=%s stage=%s complete duration_seconds=%.3f "
            "memory_mb=%s peak_memory_mb=%s%s",
            video_id,
            stage,
            time.perf_counter() - started_at,
            current_mb,
            peak_mb,
            f" {count_details}" if count_details else "",
        )