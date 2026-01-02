"""Thread dump data models."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class ThreadInfo(BaseModel):
    """Individual thread information."""

    name: str
    tid: Optional[str] = None  # Thread ID (optional for some JVM threads)
    nid: Optional[str] = None  # Native thread ID (optional for some JVM threads)
    priority: int = 0
    state: str  # Standard Thread.State: RUNNABLE, BLOCKED, WAITING, TIMED_WAITING
    raw_state: Optional[str] = None  # Raw state from header (for JVM internal threads)
    detailed_state: Optional[str] = None  # Detailed state with reason
    cpu_time: Optional[str] = None
    elapsed_time: Optional[str] = None
    stack_trace: List[str] = Field(default_factory=list)
    thread_group: Optional[str] = None
    pool_name: Optional[str] = None
    is_daemon: bool = False


class DeadlockInfo(BaseModel):
    """Deadlock information."""

    threads: List[str]
    description: str


class ThreadStatistics(BaseModel):
    """Thread statistics."""

    total_threads: int
    java_version: Optional[str] = None  # Java version string like "11.0.27+6-LTS mixed mode"
    timestamp: Optional[str] = None  # Thread dump timestamp from "Full thread dump" line
    state_distribution: Dict[str, int]
    detailed_state_distribution: Dict[str, int]  # Detailed state with reasons
    thread_pools: Dict[str, int]
    thread_pools_detailed: Dict[str, Dict[str, int]]  # Thread pool with state distribution
    thread_groups: Dict[str, int]
    daemon_threads: int
    non_daemon_threads: int
    gc_threads: int = 0  # GC (Garbage Collection) threads count


class AnalysisResult(BaseModel):
    """Complete analysis result."""

    threads: List[ThreadInfo]
    statistics: ThreadStatistics
    deadlocks: List[DeadlockInfo]
    raw_summary: str
    raw_content: Optional[str] = None  # Store raw content for re-collapsing
