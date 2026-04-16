"""
haco/state.py
LangGraph TypedDict state definition for the HACO pipeline.
"""
from typing import TypedDict, List, Optional, Dict, Any


class HACOState(TypedDict):
    # ── Code ──────────────────────────────────────────────────────────────────
    original_code: str         # The raw C++ code the user pasted in
    previous_code: str         # Pre-optimization code for accept/reject gate
    current_code: str          # The code being worked on this iteration
    # ── Pipeline tracking ─────────────────────────────────────────────────────
    iteration: int             # 0-based iteration counter
    max_iterations: int        # Stop condition (default 3)
    # ── Agent outputs ─────────────────────────────────────────────────────────
    bug_report: str            # Bug Agent diagnosis text
    bottlenecks: Dict[str, Any]  # HW Analyst JSON (top 3 bottlenecks)
    optimization_log: List[str]  # One entry per optimizer run
    test_results: List[Dict]   # {iteration, passed, details}
    # ── Hardware simulation ───────────────────────────────────────────────────
    metrics_history: List[Dict]  # [{iteration, cpu_cycles, cache_misses, ...}]
    original_score: float        # Hardware score of the initial unmodified algorithm
    # ── RAG / hardware doc ────────────────────────────────────────────────────
    hardware_name: str         # Target architecture name
    hardware_context: str      # Trimmed, cached optimization rules string
    # ── Convergence / retry ───────────────────────────────────────────────────
    error_context: str         # Populated when test fails → retry to optimizer
    validator_retries: int     # Counts retries within one iteration (max 2)
    # ── LLVM & QEMU Integration (New) ──────────────────────────────────────────
    llvm_ir: str               # Snippet of generated LLVM IR
    llvm_hints: List[str]      # Optimization hints extracted from IR
    qemu_time: float           # Real execution time in ms from QEMU
    previous_qemu_time: float  # Timing for comparison
    # ── Final output ──────────────────────────────────────────────────────────
    final_report: str          # Markdown report from Report Agent
    # ── Live log (appended to during run) ─────────────────────────────────────
    log_lines: List[str]       # Every log line emitted during the run
