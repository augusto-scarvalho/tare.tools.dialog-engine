"""Portable resource discovery and conservative auto-sizing for Watson Dialog tools.

The helpers in this module never grant authority and do not change semantics.
They only choose bounded execution widths from resources visible to the current
process.  Optional psutil support improves telemetry but is not required.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path when invoked directly
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

_MIB = 1024 * 1024
DEFAULT_MAX_INPUT_BYTES = 50 * _MIB


def resolve_max_input_bytes(value: int | None) -> int:
    if value is not None:
        if value < 0:
            raise ValueError("max_input_bytes não pode ser negativo")
        return value
    env_max = os.environ.get("WATSON_DIALOG_MAX_BYTES", "")
    if env_max.isdigit():
        return int(env_max)
    return DEFAULT_MAX_INPUT_BYTES



def _usable_cpu_count() -> int:
    process_count = getattr(os, "process_cpu_count", None)
    if callable(process_count):
        value = process_count()
        if value:
            return max(1, int(value))
    try:
        affinity = os.sched_getaffinity(0)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        affinity = None
    if affinity:
        return max(1, len(affinity))
    return max(1, int(os.cpu_count() or 1))


def _available_memory_bytes() -> int | None:
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().available)
    except Exception:
        pass

    if os.name == "posix":
        try:
            pages = int(os.sysconf("SC_AVPHYS_PAGES"))
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            return pages * page_size
        except (AttributeError, OSError, ValueError):
            return None
    return None


def _temp_free_bytes(path: Path | None = None) -> int | None:
    target = path or Path(tempfile.gettempdir())
    try:
        return int(shutil.disk_usage(target).free)
    except OSError:
        return None


@dataclass(frozen=True)
class ResourceBudget:
    usable_cpus: int
    available_memory_bytes: int | None
    temp_free_bytes: int | None
    max_jobs_cap: int

    @classmethod
    def detect(cls, temp_dir: Path | None = None) -> ResourceBudget:
        usable_cpus = _usable_cpu_count()
        env_cap = os.environ.get("WATSON_DIALOG_MAX_JOBS", "")
        # Keep a conservative default ceiling for subprocess-heavy work, but
        # scale it with larger machines instead of pinning every host to 8.
        default_cap = max(1, min(16, usable_cpus))
        max_jobs_cap = int(env_cap) if env_cap.isdigit() and int(env_cap) > 0 else default_cap
        return cls(
            usable_cpus=usable_cpus,
            available_memory_bytes=_available_memory_bytes(),
            temp_free_bytes=_temp_free_bytes(temp_dir),
            max_jobs_cap=max_jobs_cap,
        )

    def auto_jobs(
        self,
        task_count: int,
        *,
        estimated_worker_memory_bytes: int = 512 * _MIB,
        cpu_fraction: float = 0.5,
    ) -> int:
        """Return a conservative worker count for independent subprocess work.

        The CPU rule intentionally keeps headroom because mutation/unit-test
        subprocesses are CPU-heavy and concurrent Python runtimes amplify RSS.
        Users can override the result explicitly with ``--jobs N``.
        """
        if task_count <= 0:
            return 1
        cpu_jobs = max(1, int(self.usable_cpus * cpu_fraction))
        if self.usable_cpus >= 2:
            cpu_jobs = max(1, cpu_jobs)
        memory_jobs = task_count
        if self.available_memory_bytes and estimated_worker_memory_bytes > 0:
            # Keep 25% of currently available memory uncommitted.
            usable_memory = int(self.available_memory_bytes * 0.75)
            memory_jobs = max(1, usable_memory // estimated_worker_memory_bytes)
        return max(1, min(task_count, cpu_jobs, memory_jobs, self.max_jobs_cap))

    def logical_shards(
        self,
        worker_count: int,
        task_count: int,
        oversubscription: int = 4,
        min_tasks_per_shard: int = 8,
    ) -> int:
        if task_count <= 0:
            return 1
        workers = max(1, min(worker_count, task_count))
        desired = workers * max(1, oversubscription)
        useful_cap = max(workers, (task_count + max(1, min_tasks_per_shard) - 1) // max(1, min_tasks_per_shard))
        return max(1, min(task_count, desired, useful_cap))

    def to_dict(self) -> dict[str, int | None]:
        return {
            "usable_cpus": self.usable_cpus,
            "available_memory_bytes": self.available_memory_bytes,
            "temp_free_bytes": self.temp_free_bytes,
            "max_jobs_cap": self.max_jobs_cap,
        }


def resolve_jobs(value: str | int, task_count: int, budget: ResourceBudget | None = None) -> int:
    if isinstance(value, int):
        if value < 1:
            raise ValueError("jobs deve ser pelo menos 1")
        return min(value, max(1, task_count))
    rendered = str(value).strip().lower()
    if rendered == "auto":
        return (budget or ResourceBudget.detect()).auto_jobs(task_count)
    if rendered.isdigit() and int(rendered) > 0:
        return min(int(rendered), max(1, task_count))
    raise ValueError("jobs deve ser 'auto' ou um inteiro positivo")
