"""Thread tracking across multiple dumps."""

from typing import List, Dict, Tuple
from app.models.thread_data import ThreadInfo, ThreadInstance, ThreadTimeline


class ThreadTracker:
    """Track threads across multiple dumps and identify unique threads."""
    
    def __init__(self):
        self.timelines: Dict[str, ThreadTimeline] = {}
    
    def identify_thread(self, thread: ThreadInfo) -> str:
        """
        Generate a unique identifier for a thread.
        
        Priority:
        1. Use nid (native thread ID) if available - most reliable
        2. Use tid (thread ID) if available
        3. Fall back to name-based identifier for GC threads and others without IDs
        
        Args:
            thread: ThreadInfo object
            
        Returns:
            Unique identifier string
        """
        # Prefer nid (native thread ID) as it's most stable
        if thread.nid:
            return f"nid:{thread.nid}"
        
        # Fall back to tid
        if thread.tid:
            return f"tid:{thread.tid}"
        
        # For threads without IDs (like GC threads), use name
        # Remove numeric suffixes to group similar threads
        name = thread.name
        # Remove trailing #digits or -digits
        import re
        name_normalized = re.sub(r'[#-]\d+$', '', name)
        return f"name:{name_normalized}"
    
    def add_thread(self, thread: ThreadInfo, dump_index: int, dump_name: str):
        """
        Add a thread instance to the tracker.
        
        Args:
            thread: ThreadInfo object
            dump_index: Index of the dump (0-based)
            dump_name: Name of the dump file
        """
        # Set dump_index on the thread
        thread.dump_index = dump_index
        
        # Identify the thread
        thread_id = self.identify_thread(thread)
        
        # Create instance
        instance = ThreadInstance(
            thread_info=thread,
            dump_index=dump_index,
            dump_name=dump_name
        )
        
        # Add to timeline or create new timeline
        if thread_id not in self.timelines:
            self.timelines[thread_id] = ThreadTimeline(
                thread_id=thread_id,
                name=thread.name,
                instances=[instance],
                dump_indices=[dump_index]
            )
        else:
            timeline = self.timelines[thread_id]
            timeline.instances.append(instance)
            if dump_index not in timeline.dump_indices:
                timeline.dump_indices.append(dump_index)
    
    def get_timelines(self) -> List[ThreadTimeline]:
        """Get all thread timelines."""
        return list(self.timelines.values())
    
    def get_unique_thread_count(self) -> int:
        """Get count of unique threads."""
        return len(self.timelines)
    
    def get_all_thread_instances(self) -> List[ThreadInfo]:
        """
        Get all thread instances as a flat list.
        Used for backward compatibility with single-dump analysis.
        """
        all_threads = []
        for timeline in self.timelines.values():
            for instance in timeline.instances:
                all_threads.append(instance.thread_info)
        return all_threads
    
    def analyze_unique_stacks(self):
        """Analyze and count unique stack traces for each thread."""
        for timeline in self.timelines.values():
            unique_stacks = set()
            for instance in timeline.instances:
                # Create a stack signature
                stack_sig = ";".join(instance.thread_info.stack_trace)
                unique_stacks.add(stack_sig)
            timeline.unique_stacks = len(unique_stacks)
    
    def get_collapsed_stacks_per_thread(self) -> Dict[str, Dict[str, int]]:
        """
        Get collapsed stacks grouped by thread ID.
        
        Returns:
            Dictionary mapping thread_id to {stack: count}
        """
        result = {}
        for thread_id, timeline in self.timelines.items():
            stacks = {}
            for instance in timeline.instances:
                # Reverse stack to get root->leaf order
                stack_frames = list(reversed(instance.thread_info.stack_trace))
                # Clean frames
                cleaned_frames = []
                for frame in stack_frames:
                    if frame.startswith("at "):
                        frame = frame[3:]
                    if "(" in frame:
                        frame = frame[:frame.index("(")]
                    cleaned_frames.append(frame.strip())
                
                if cleaned_frames:
                    stack_key = ";".join(cleaned_frames)
                    stacks[stack_key] = stacks.get(stack_key, 0) + 1
            
            result[thread_id] = stacks
        
        return result
    
    def get_merged_collapsed_stacks(self) -> Dict[str, int]:
        """
        Get all stacks collapsed and merged across all threads.
        This is for generating the overall flamegraph.
        
        Returns:
            Dictionary mapping stack to total count
        """
        merged = {}
        per_thread = self.get_collapsed_stacks_per_thread()
        
        for thread_stacks in per_thread.values():
            for stack, count in thread_stacks.items():
                merged[stack] = merged.get(stack, 0) + count
        
        return merged
