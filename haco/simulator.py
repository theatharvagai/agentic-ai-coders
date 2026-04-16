"""
haco/simulator.py
Pure-Python RISC-V hardware cost model.
No external binaries required — works on Windows/Mac/Linux everywhere.

The simulator performs static analysis of C++ source code and applies
heuristic rules to estimate hardware performance for a hypothetical 
single-issue in-order RISC-V RV64GC core with:
  - 32 integer registers (x0–x31)
  - Direct-mapped 32KB L1 data cache, 64-byte cache lines
  - No branch predictor (static prediction)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Dict, Any


# ─── Constants ────────────────────────────────────────────────────────────────
BASE_CYCLES_PER_INSTR = 1
CACHE_MISS_PENALTY    = 50    # cycles
BRANCH_MISPREDICT     = 3     # cycles
FUNCTION_CALL_COST    = 10    # cycles (save/restore frame, ra)

# ─── Heuristic weights ────────────────────────────────────────────────────────
W_NESTED_LOOP   = 800          # extra cycles per extra nesting level
W_RECURSION     = 1200         # extra cycles (stack frames, ra spill)
W_RANGE_LEN     = 40           # cache-miss-like cost per occurrence
W_POINTER_ARITH = 20           # indirect memory access
W_BRANCH        = 15           # every if/while/for adds branch cost
W_VECTOR_OP     = -30          # reward: vectorisable ops cheaper
W_MEMO          = -500         # reward: memoisation cuts recursion cost
W_HASHMAP       = -20          # reward: O(1) lookup
W_LOCALITY      = -10          # reward: sequential access patterns

# ─── Complexity penalty (FIX 2) ──────────────────────────────────────────────
# If optimized code is >40% longer than original, it is likely more complex
CODE_BLOAT_THRESHOLD = 0.40   # 40% longer
CODE_BLOAT_PENALTY   = 500    # extra cycles

# ─── Score formula weights (FIX 3) ───────────────────────────────────────────
SCORE_W_CYCLES     = 1.0
SCORE_W_CACHE      = 40.0
SCORE_W_MISPREDICT = 80.0


# ─── Pattern Detection (FIX 1) ───────────────────────────────────────────────

def detect_pattern(code: str) -> str: # FIXED
    # 1. 3 or more nested loops
    has_triple_nested = bool(re.search(r'\b(?:for|while)\b[^{}]*\{[^{}]*\b(?:for|while)\b[^{}]*\{[^{}]*\b(?:for|while)\b', code))
    
    # 2. pointer indirection
    has_ptr_ptr = bool(re.search(r'\w+\*\*', code) or re.search(r'\*\*\s*\w+', code) or "**" in code)
    
    # 3. recursion
    has_recursion = bool(re.search(r'\b(?!(?:for|while|if|switch|catch|def)\b)(\w+)\s*\([^)]*\)\s*\{[^}]*\b\1\s*\(', code, re.DOTALL))
    if "def " in code and not has_recursion:
        has_recursion = bool(re.search(r'\bdef\s+(\w+)\s*\(.*?\b\1\s*\(', code, re.DOTALL))
        
    # 4. sorting
    has_sorting = bool(re.search(r'std::sort|std::map|\.sort\b|<map>', code))
    
    if has_triple_nested: return "nested_loop_search"
    elif has_ptr_ptr: return "pointer_indirection"
    elif has_recursion: return "recursion"
    elif has_sorting: return "sorting"
    else: return "general"


def choose_optimization(pattern: str) -> str:
    """
    Returns the recommended optimization strategy for a given pattern.
    """
    strategies = {
        "nested_loop_search": (
            "This code has a triple nested loop O(n^3). You MUST replace the innermost two loops with an unordered_map or boolean frequency array.\n"
            "Do NOT introduce any new nested loops in your solution.\n"
            "Do NOT use VLAs (variable length arrays like int arr[n]) — these cause stack allocation overhead on RISC-V.\n"
            "The target solution should be O(n) time using a hash frequency table.\n"
            "Concrete example of what to do:\n"
            "  Instead of: for j in range: for k in range: if arr[j]==arr[k]\n"
            "  Do this: build freq_map[val]++ in one pass, then check freq_map[target] > 1 in O(1)"
        ),
        "sorting_pattern": (
            "Data is already sorted or ordering is required. "
            "Use two-pointer technique to avoid nested loops."
        ),
        "recursion": (
            "Convert recursion to iterative using a stack or DP table. "
            "If memoization is needed, use a plain int array, NOT unordered_map."
        ),
        "simple_iteration": (
            "Apply minor surgical optimizations only: "
            "hoist loop invariants, use register variables, avoid redundant branches."
        ),
        "general": (
            "Make minimal changes only. "
            "Do NOT restructure the algorithm."
        ),
    }
    return strategies.get(pattern, strategies["general"])


# ─── Bottleneck evidence filter (FIX 4) ──────────────────────────────────────

def filter_bottlenecks(bottlenecks: dict, code: str) -> dict:
    """
    Removes hallucinated bottlenecks that have no evidence in the source code.
    Only keeps bottlenecks that match observable code features.
    """
    has_array_access = bool(re.search(r'\w+\[', code))
    var_count        = len(re.findall(r'\b(?:int|float|double|char|long|bool|auto)\s+\w+', code))
    branch_count     = len(re.findall(r'\b(if|else|for|while|do|switch|case|break|continue|\?)\b', code))
    has_pointers     = bool(re.search(r'\*\w+|\w+\s*->', code))
    has_recursion    = bool(re.search(r'\b(?!(?:for|while|if|switch|catch)\b)(\w+)\s*\([^)]*\)\s*\{[^}]*\b\1\s*\(', code, re.DOTALL))
    has_nested_loops = len(re.findall(r'\bfor\b|\bwhile\b', code)) >= 2

    valid = {}
    evidence_map = {
        "cache_miss":         has_array_access,
        "register_spill":     var_count > 8,
        "branch_mispredict":  branch_count > 5,
        "pointer_chasing":    has_pointers,
        "algorithm_complexity": has_recursion or has_nested_loops,
        "memory_alignment":   has_array_access or has_pointers,
    }

    for key, bval in bottlenecks.items():
        if not isinstance(bval, dict):
            continue
        btype = bval.get("type", "")
        # Check evidence; if type not in map, keep it (unknown types pass through)
        has_evidence = evidence_map.get(btype, True)
        if has_evidence:
            valid[key] = bval

    # If filtering removed everything, return the first one as-is
    if not valid and bottlenecks:
        first_key = next(iter(bottlenecks))
        valid[first_key] = bottlenecks[first_key]

    return valid


@dataclass
class SimMetrics:
    cpu_cycles: int        = 0
    total_instructions: int = 0
    cache_hits: int        = 0
    cache_misses: int      = 0
    branch_mispredicts: int = 0
    register_pressure: str = "LOW"   # LOW / MEDIUM / HIGH
    ipc: float             = 1.0
    score: float           = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "cpu_cycles":         self.cpu_cycles,
            "total_instructions": self.total_instructions,
            "cache_hits":         self.cache_hits,
            "cache_misses":       self.cache_misses,
            "cache_miss_rate":    self._miss_rate(),
            "branch_mispredicts": self.branch_mispredicts,
            "register_pressure":  self.register_pressure,
            "ipc":                round(self.ipc, 3),
            "score":              round(self.score, 4),
        }

    def _miss_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return round(self.cache_misses / total, 3) if total > 0 else 0.0


class RISCVSimulator:
    """
    Statically analyses C++ source code and returns a SimMetrics dict.

    Algorithm
    ---------
    1. Count structural features from the source text using regex.
    2. Apply heuristic multipliers to estimate instruction count.
    3. Apply RISC-V-specific penalties (cache, branches, register spills).
    4. Derive IPC and composite score using formal formula:
       Score = cycles + (cache_misses * 40) + (branch_mispredicts * 80)
    """

    def analyze(self, code: str, iteration: int = 0,
                original_code: str | None = None) -> Dict[str, Any]:
        """
        Analyze code. If original_code is given, applies bloat penalty
        when the optimized code is more than 40% longer (FIX 2).
        """
        m = self._analyse_code(code)

        # ─── Complexity / Bloat Penalty (FIX 2) ──────────────────────────────
        if original_code is not None:
            orig_lines = max(len(original_code.splitlines()), 1)
            new_lines  = max(len(code.splitlines()), 1)
            if (new_lines - orig_lines) / orig_lines > CODE_BLOAT_THRESHOLD:
                m.cpu_cycles += CODE_BLOAT_PENALTY
                # Recalculate score with penalty
                m.score = self._compute_score(m)

        m_dict = m.as_dict()
        m_dict["iteration"] = iteration
        return m_dict

    def compute_score_raw(self, cycles: int, cache_misses: int,
                          branch_mispredicts: int) -> float:
        """Explicit score formula for comparison logic."""
        return cycles * SCORE_W_CYCLES \
             + cache_misses * SCORE_W_CACHE \
             + branch_mispredicts * SCORE_W_MISPREDICT

    def _compute_score(self, m: SimMetrics) -> float:
        """Compute score from SimMetrics using the formal formula."""
        raw = self.compute_score_raw(m.cpu_cycles, m.cache_misses,
                                     m.branch_mispredicts)
        return round(raw, 4)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _analyse_code(self, code: str) -> SimMetrics:
        lines = code.splitlines()
        m = SimMetrics()

        # ── 1. Count structural features ──────────────────────────────────────
        language = "python" if "def " in code else "cpp"
        nest_depth        = self._max_nesting_depth(code)
        recursive_calls   = self._count_recursion(code)
        branch_count      = self._count_branches(code)
        memory_accesses   = self._count_memory_accesses(code)
        has_range_len     = len(re.findall(r'range\s*\(\s*len\s*\(', code))
        has_pointer_arith = len(re.findall(r'\*\w+|\w+\[', code))
        has_vector_ops    = len(re.findall(r'std::(vector|array|sort|transform)|\.sort\(', code))
        has_memo          = len(re.findall(r'memo|cache|dp\[|visited\[', code, re.I))
        has_hashmap       = len(re.findall(r'std::(unordered_map|unordered_set|map\b|set\b)|set\(|\{\}', code))
        has_locality      = len(re.findall(r'\+\+i|\+\+j|seq|contiguous', code, re.I))
        line_count        = max(len(lines), 1)

        loops = len(re.findall(r'\bfor\b|\bwhile\b', code))
        hidden_loops = len(re.findall(r'\b(?:not )?in\b', code)) if language == "python" else len(re.findall(r'std::(find|count)', code))
        is_nested = loops > 1 or (loops == 1 and hidden_loops > 0)

        # ── 2. Base instruction estimate (REVISED for massive loop penalty)
        base_instructions = line_count * 4   # avg 4 RISC-V instrs per src line
        
        loop_penalty = 50
        if is_nested:
            loop_penalty += 3000   # BIG penalty for O(n^2) patterns
        loop_penalty += loops * 250
        
        recursion_penalty = recursive_calls * 4000  # Massive penalty for recursion overhead

        total_instr = (base_instructions + loop_penalty + recursion_penalty
                       + branch_count * 3           # cmp + branch + nop
                       + memory_accesses * 2
                       - has_vector_ops * 50
                       - has_memo * 200)
        total_instr = max(total_instr, 50)
        m.total_instructions = total_instr

        # ── 3. Cache model ────────────────────────────────────────────────────
        miss_sources = (has_pointer_arith * W_POINTER_ARITH +
                        has_range_len   * W_RANGE_LEN -
                        has_locality    * abs(W_LOCALITY) -
                        has_hashmap     * abs(W_HASHMAP))
        base_miss_rate = 0.05
        extra_miss_rate = miss_sources / 10_000.0
        miss_rate = max(0.01, min(0.80, base_miss_rate + extra_miss_rate))

        raw_mem_accesses = memory_accesses + nest_depth * 20
        m.cache_misses = int(raw_mem_accesses * miss_rate)
        m.cache_hits   = int(raw_mem_accesses * (1 - miss_rate))

        # ── 4. Branch misprediction model ─────────────────────────────────────
        mispredict_rate = 0.15
        if recursive_calls > 0:
            mispredict_rate = 0.25
        if has_memo > 0:
            mispredict_rate = 0.10
        m.branch_mispredicts = int(branch_count * mispredict_rate)

        # ── 5. Register pressure (Antigravity massive penalty fix) ────────────
        live_vars = nest_depth * 4 + branch_count * 2 + (line_count // 5)
        raw_lw_sw_estimate = memory_accesses * 2
        
        if live_vars > 28 or raw_lw_sw_estimate > 10:
            m.register_pressure = "HIGH"
            total_instr += 1000 # Massive penalty for excessive load/store spills
        elif live_vars > 16:
            m.register_pressure = "MEDIUM"
        else:
            m.register_pressure = "LOW"

        # ── 6. CPU cycles ─────────────────────────────────────────────────────
        cycle_count = (
            total_instr * BASE_CYCLES_PER_INSTR
            + m.cache_misses      * CACHE_MISS_PENALTY
            + m.branch_mispredicts * BRANCH_MISPREDICT
            + recursive_calls     * FUNCTION_CALL_COST
        )
        cycle_count -= has_memo * 200
        cycle_count -= has_vector_ops * 50
        m.cpu_cycles = max(cycle_count, 100)

        # ── 7. IPC ────────────────────────────────────────────────────────────
        raw_ipc = m.total_instructions / m.cpu_cycles if m.cpu_cycles > 0 else 1.0
        m.ipc = round(min(max(raw_ipc, 0.1), 4.0), 3)

        # ── 8. Composite score — FORMAL FORMULA (FIX 3) ──────────────────────
        # Score = cycles * 1.0 + cache_misses * 40 + branch_mispredicts * 80
        m.score = self._compute_score(m)

        return m

    # ── Feature extractors ─────────────────────────────────────────────────────

    def _max_nesting_depth(self, code: str) -> int:
        max_depth = depth = 0
        for ch in code:
            if ch == '{':
                depth += 1
                max_depth = max(max_depth, depth)
            elif ch == '}':
                depth = max(depth - 1, 0)
        return max_depth

    def _count_recursion(self, code: str) -> int:
        fn_names = re.findall(r'\b(\w+)\s*\([^)]*\)\s*\{', code)
        count = 0
        for name in set(fn_names):
            pattern = rf'\b{re.escape(name)}\s*\('
            count += max(len(re.findall(pattern, code)) - 1, 0)
        return count

    def _count_branches(self, code: str) -> int:
        keywords = r'\b(if|else|for|while|do|switch|case|break|continue|\?)\b'
        return len(re.findall(keywords, code))

    def _count_memory_accesses(self, code: str) -> int:
        patterns = [
            r'\w+\[',           # array index
            r'\*\w+',           # pointer deref
            r'\.at\(',          # .at() bounds check
            r'std::(cout|cin)', # I/O (memory mapped)
            r'new\s+\w+',       # heap allocation
            r'malloc\(',        # malloc
            r'std::vector',     # heap-backed container
        ]
        total = 0
        for p in patterns:
            total += len(re.findall(p, code))
        return total


# ── Quick smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample = """
    int fib(int n) {
        if (n <= 1) return n;
        return fib(n-1) + fib(n-2);
    }
    """
    sim = RISCVSimulator()
    result = sim.analyze(sample, iteration=0)
    for k, v in result.items():
        print(f"  {k:25s}: {v}")
    
    print(f"\nPattern: {detect_pattern(sample)}")
    print(f"Strategy: {choose_optimization(detect_pattern(sample))}")
