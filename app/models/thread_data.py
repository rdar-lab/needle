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
    dump_index: Optional[int] = None  # Index of the dump this thread appeared in


class ThreadInstance(BaseModel):
    """Single instance of a thread in a specific dump."""
    
    thread_info: ThreadInfo
    dump_index: int  # Which dump this instance is from
    dump_name: str  # Name of the dump file


class ThreadTimeline(BaseModel):
    """Timeline of a thread across multiple dumps."""
    
    thread_id: str  # Unique identifier (tid or nid or name-based)
    name: str
    instances: List[ThreadInstance] = Field(default_factory=list)
    dump_indices: List[int] = Field(default_factory=list)  # Which dumps this thread appeared in
    unique_stacks: int = 0  # Number of unique stack traces
    
    def get_collapsed_stack(self) -> str:
        """Get a collapsed stack representation for this thread across all instances."""
        stacks = []
        for instance in self.instances:
            stack_str = ";".join(reversed(instance.thread_info.stack_trace))
            stacks.append(stack_str)
        return ";".join(stacks)


class DeadlockInfo(BaseModel):
    """Deadlock information."""

    threads: List[str]
    description: str


class ThreadStatistics(BaseModel):
    """Thread statistics."""

    total_threads: int
    unique_threads: int = 0  # Number of unique threads (deduplicated across dumps)
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
    thread_timelines: List[ThreadTimeline] = Field(default_factory=list)  # Thread tracking across dumps


class AnalysisResult(BaseModel):
    """Complete analysis result."""

    threads: List[ThreadInfo]
    statistics: ThreadStatistics
    deadlocks: List[DeadlockInfo]
    raw_summary: str
    raw_content: Optional[str] = None  # Store raw content for re-collapsing
