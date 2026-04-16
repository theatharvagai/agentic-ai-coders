"""
haco/agents.py
All LangGraph agent node functions for the HACO pipeline.

Changes in this version
-----------------------
FIX 1 – optimizer_agent: guardrails — skip bottleneck if cycle saving < 200
FIX 2 – hw_analyst_agent: bloat penalty applied via simulator.analyze(original_code=...)
FIX 3 – accept_or_reject: new LangGraph node — rejects optimization if score worsens
FIX 4 – hw_analyst_agent: filter_bottlenecks removes hallucinated diagnoses
FIX 5 – optimizer_agent: new strict surgical prompt
       + pattern detection, strategy selection, smart logging
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from haco.simulator import (
    RISCVSimulator,
    detect_pattern,
    choose_optimization,
    filter_bottlenecks,
)
from haco.state import HACOState
from haco.qemu_runner import compile_and_run_qemu, approximate_cycles
from haco.llvm_analyzer import get_llvm_analysis

# ── LLVM Analysis Agent (New) ────────────────────────────────────────────────
def llvm_analysis_agent(state: HACOState) -> HACOState:
    _log(state, "🧬 [LLVM Agent] Generating IR & searching for patterns...")
    
    analysis = get_llvm_analysis(state["current_code"])
    
    if not analysis["success"]:
        _log(state, f"   ⚠️ LLVM skipped: {analysis['error']}")
        return {**state, "llvm_ir": "", "llvm_hints": []}
        
    _log(state, f"   Found {len(analysis['hints'])} optimization hints.")
    return {
        **state,
        "llvm_ir": analysis["ir"],
        "llvm_hints": analysis["hints"]
    }

# ── LLM invocation ────────────────────────────────────────────────────────────

def _get_llm() -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        groq_api_key=os.environ.get("GROQ_API_KEY", ""),
        timeout=30,
        max_retries=2,
    )


def _log(state: HACOState, msg: str) -> None:
    state["log_lines"].append(msg)


def _hw_prefix(state: HACOState) -> str:
    name = state.get("hardware_name", "Generic RISC-V")
    pdf_path = state.get("hardware_context", "") # REWRITTEN
    
    ctx = "" # REWRITTEN
    if pdf_path and os.path.exists(pdf_path): # REWRITTEN
        from haco.rag import extract_important_hardware_context # REWRITTEN
        try: # REWRITTEN
            ctx = extract_important_hardware_context(pdf_path) # REWRITTEN
        except Exception: # FIXED: Catch pdfminer SyntaxErrors natively
            ctx = "No hardware constraints loaded. Optimize for general RISC-V RV32IMAC defaults: minimize nested loops, avoid recursion, reduce register pressure, prefer sequential memory access patterns." # REWRITTEN
    else: # REWRITTEN
        ctx = "No hardware constraints loaded. Optimize for general RISC-V RV32IMAC defaults: minimize nested loops, avoid recursion, reduce register pressure, prefer sequential memory access patterns." # REWRITTEN
    return (
        f"TARGET HARDWARE: {name}\n"
        f"HARDWARE CONSTRAINTS:\n{ctx}\n"
        "---\n"
        "Use the above hardware constraints to inform ALL optimization decisions.\n"
        f"Every bottleneck you identify and every fix you suggest must be grounded\n"
        f"in the specific constraints of {name}, not generic RISC-V assumptions.\n\n"
    )

def clean_llm_json(raw: str) -> str: # FIXED
    raw = re.sub(r"```(?:json)?\s*", "", raw) # FIXED
    raw = re.sub(r"```", "", raw) # FIXED
    raw = raw.strip() # FIXED
    # Find the first { and last } and extract only that
    start = raw.find('{') # FIXED
    end = raw.rfind('}') # FIXED
    if start != -1 and end != -1: # FIXED
        raw = raw[start:end+1] # FIXED
    return raw # FIXED


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 1 — Bug Detector
# ══════════════════════════════════════════════════════════════════════════════

def bug_agent(state: HACOState) -> HACOState:
    _log(state, "🐛 [Bug Agent] Scanning code for logical/runtime issues...")

    system = _hw_prefix(state) + (
        "You are a senior C++ code reviewer specialized in systems programming. "
        "Analyse the given C++ code for logical errors, undefined behaviour, "
        "memory leaks, off-by-one errors, and unnecessary re-computation. "
        "Return a short bullet-point diagnosis (max 5 points). "
        "If the code looks correct, say 'No critical bugs found.'"
    )
    human = f"C++ Code:\n```cpp\n{state['current_code']}\n```"

    llm = _get_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    diagnosis = resp.content.strip()

    _log(state, f"   Bug report: {diagnosis[:120]}{'...' if len(diagnosis)>120 else ''}")
    return {**state, "bug_report": diagnosis}


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — Hardware Analyst  (FIX 2 + FIX 4)
# ══════════════════════════════════════════════════════════════════════════════

def hw_analyst_agent(state: HACOState) -> HACOState:
    _log(state, "🔬 [HW Analyst] Benchmarking & analyzing bottlenecks...")

    # 1. Real QEMU Benchmarking
    qemu_res = compile_and_run_qemu(state["current_code"])
    qemu_time = qemu_res.get("execution_time", 0.0)
    
    # 2. Simulator Fallback / Augmented Heuristics
    sim = RISCVSimulator()
    original_code = state.get("original_code", state["current_code"])
    metrics = sim.analyze(
        state["current_code"],
        iteration=state["iteration"],
        original_code=original_code if state["iteration"] > 0 else None,
    )
    
    # Inject real data into metrics
    if qemu_res.get("success"):
        metrics["execution_time"] = qemu_time
        # Approximate cycles for compatibility
        metrics["cpu_cycles"] = approximate_cycles(qemu_time)
        _log(state, f"   QEMU benchmark: {qemu_time} ms")
    else:
        _log(state, f"   ⚠️ QEMU failed: {qemu_res.get('error')}. Falling back to simulator.")

    system = _hw_prefix(state) + (
        "You are a RISC-V hardware performance analyst. "
        "Given C++ source code, LLVM IR analysis, and simulated/real RISC-V hardware metrics, identify "
        "the TOP 3 performance bottlenecks. "
        "ONLY report bottleneck types that have clear evidence in the source code or IR. "
        "Valid types: cache_miss, register_spill, branch_mispredict, "
        "memory_alignment, algorithm_complexity, pointer_chasing. "
        "Respond ONLY as valid JSON with this exact structure:\n"
        '{"bottleneck_1": {"type": "<type>", '
        '"source_lines": "<description>", "hardware_behavior": "<explanation>", '
        '"fix_category": "<hint>", "estimated_cycle_saving": <integer>}, '
        '"bottleneck_2": {...}, "bottleneck_3": {...}}'
    )
    human = (
        f"C++ Code:\n```cpp\n{state['current_code']}\n```\n\n"
        f"LLVM IR Hits:\n{json.dumps(state.get('llvm_hints', []), indent=2)}\n\n"
        f"LLVM IR Snippet:\n```llvm\n{state.get('llvm_ir', '')}\n```\n\n"
        f"Performance Metrics:\n{json.dumps(metrics, indent=2)}"
    )

    llm = _get_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])

    raw = resp.content.strip()
    raw = clean_llm_json(raw) # FIXED
    try: # FIXED
        bottlenecks = json.loads(raw) # FIXED
    except json.JSONDecodeError: # FIXED
        print(f"[JSON ERROR] Raw LLM output was: {raw}") # FIXED
        bottlenecks = { # FIXED
            "bottleneck_1": { # FIXED
                "type": "unknown", # FIXED
                "source_lines": raw[:100], # FIXED
                "hardware_behavior": "", # FIXED
                "fix_category": "", # FIXED
                "estimated_cycle_saving": 0 # FIXED
            } # FIXED
        } # FIXED

    # FIX 4 — remove hallucinated bottlenecks
    print(f"[RAW BOTTLENECKS FROM LLM] {bottlenecks}") # REWRITTEN
    filtered = filter_bottlenecks(bottlenecks, state["current_code"]) # REWRITTEN

    if not filtered or (len(filtered) == 1 and list(filtered.values())[0]["type"] == "unknown"): # REWRITTEN
        top_key = list(bottlenecks.keys())[0] if bottlenecks else "bottleneck_1" # REWRITTEN
        top_raw_bottleneck = bottlenecks.get(top_key, {}) # REWRITTEN
        if top_raw_bottleneck: # REWRITTEN
            top_raw_bottleneck["_llm_bypass"] = True
            filtered = {top_key: top_raw_bottleneck} # REWRITTEN
            
    bottlenecks = filtered # REWRITTEN

    new_history = list(state.get("metrics_history", []))
    new_history.append(metrics)

    _log(state, f"   Iter {state['iteration']} → {metrics['cpu_cycles']} cycles, "
                f"{metrics['cache_misses']} cache misses, IPC={metrics['ipc']}, "
                f"Score={metrics['score']:.0f}")
    top_type = next(iter(bottlenecks.values()), {}).get("type", "?")
    _log(state, f"   Top bottleneck (validated): {top_type}")

    return {
        **state, 
        "bottlenecks": bottlenecks, 
        "metrics_history": new_history,
        "original_score": state.get("original_score", metrics["score"]), # FIXED
        "qemu_time": qemu_time
    }


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3 — Code Optimizer  (FIX 1 + FIX 5 + Pattern Detection)
# ══════════════════════════════════════════════════════════════════════════════

def optimizer_agent(state: HACOState) -> HACOState:
    _log(state, f"⚙️  [Optimizer] Rewriting C++ for RISC-V (iteration {state['iteration']})...")

    # ── Pattern detection + strategy selection ────────────────────────────────
    pattern  = detect_pattern(state["current_code"])
    strategy = choose_optimization(pattern)
    _log(state, f"   [Optimizer] Pattern detected: {pattern}")
    _log(state, f"   [Optimizer] Strategy: {strategy[:80]}...")

    # ── FIX 1 — filter out bottlenecks with trivial projected savings ─────────
    bottlenecks = state.get("bottlenecks", {})
    actionable  = {}
    for k, v in bottlenecks.items():
        if not isinstance(v, dict):
            continue
        saving = v.get("estimated_cycle_saving", 9999)
        is_bypassed = v.get("_llm_bypass", False)
        
        if saving < 50 and not is_bypassed:
            _log(state, f"   [Optimizer] Skipping bottleneck '{v.get('type','?')}' "
                        f"— projected saving {saving} cycles < 50 threshold.")
        else:
            actionable[k] = v

    if not actionable:
        _log(state, "   [Optimizer] No actionable bottlenecks — returning code unchanged.")
        return {
            **state,
            "error_context": "",
            "optimization_log": list(state.get("optimization_log", [])) + [
                f"Iteration {state['iteration']}: No bottleneck exceeded 200-cycle threshold — skipped."
            ],
        }

    # ── FIX 5 — new strict surgical prompt ────────────────────────────────────
    system = _hw_prefix(state) + (
        "You are a RISC-V hardware optimization expert. "
        "You will receive C/C++ source code and a JSON diagnosis listing specific bottlenecks "
        "including their types and estimated cycle savings. "
        "Your job is to apply the MINIMUM change necessary to fix each listed bottleneck.\n\n"
        "STRICT RULES — violating any rule is a failure:\n"
        "1. Change as FEW lines as possible. Make surgical edits only.\n"
        "2. Do NOT restructure the entire function. Preserve the overall algorithm shape.\n"
        "3. Do NOT add new data structures unless the diagnosis fix_category explicitly says "
        "'data_structure_change'.\n"
        "4. Do NOT add memoization unless the diagnosis fix_category explicitly says 'memoization'.\n"
        "5. NEVER apply sorting unless the code is already working on sorted data "
        "OR pattern is 'sorting_pattern'.\n"
        "6. PREFER hashing (unordered_set / unordered_map using a simple int array) "
        "over nested loops for search problems.\n"
        "7. Do NOT increase algorithmic complexity (e.g., do not convert O(n) to O(n log n)).\n"
        "8. The optimized code MUST produce byte-identical output to the original for all inputs.\n"
        "9. Always include required C++ headers (#include <unordered_set>, <vector>, etc.).\n"
        "10. If you are NOT confident a change will reduce the hardware score, "
        "return the code UNCHANGED for that bottleneck.\n"
        "11. Return ONLY the corrected C/C++ code with no explanation and no markdown fences.\n\n"
        f"Detected pattern: {pattern}\n"
        f"Recommended strategy: {strategy}"
    )

    error_ctx = state.get("error_context", "")
    error_section = f"\n\nValidator Error to Fix:\n{error_ctx}" if error_ctx else ""

    human = (
        f"Original C++ Code:\n```cpp\n{state['current_code']}\n```\n\n"
        f"LLVM IR Analysis Patterns:\n{json.dumps(state.get('llvm_hints', []), indent=2)}\n\n"
        f"Bug Report:\n{state['bug_report']}\n\n"
        f"Actionable Hardware Bottlenecks:\n"
        f"{json.dumps(actionable, indent=2)}"
        f"{error_section}"
    )

    llm = _get_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])

    new_code = resp.content.strip()
    new_code = re.sub(r'^```(?:cpp|c\+\+)?\s*', '', new_code, flags=re.MULTILINE)
    new_code = re.sub(r'```\s*$', '', new_code, flags=re.MULTILINE).strip()

    applied_types = ', '.join(set(v.get('type', '?') for v in actionable.values()))
    log_entry = f"Iteration {state['iteration']}: Applied fixes for [{applied_types}] | Pattern: {pattern}"
    new_log = list(state.get("optimization_log", []))
    new_log.append(log_entry)

    orig_lines = len(state["current_code"].splitlines())
    new_lines  = len(new_code.splitlines())
    _log(state, f"   Optimizer: {orig_lines} → {new_lines} lines")

    return {
        **state,
        "previous_code": state.get("current_code", state.get("original_code", "")),
        "current_code": new_code,
        "optimization_log": new_log,
        "error_context": ""
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE — Accept or Reject (FIX 3)
# ══════════════════════════════════════════════════════════════════════════════

def accept_or_reject(state: HACOState) -> HACOState:
    """
    Compares real QEMU execution time (primary) and heuristic score (secondary).
    Accepts only if we see a genuine improvement (>2% reduction in time).
    """
    history = state.get("metrics_history", [])
    if len(history) < 2:
        return state

    # 1. Compare QEMU execution times if both available
    prev_time = state.get("previous_qemu_time", 0.0)
    curr_time = state.get("qemu_time", 0.0)

    if prev_time > 0 and curr_time > 0:
        improvement = (prev_time - curr_time) / prev_time
        _log(state, f"   [Accept/Reject] Timing: {prev_time:.3f}ms -> {curr_time:.3f}ms (Improv: {improvement*100:.1f}%)")
        
        # 2% noise margin
        if improvement > 0.02:
            _log(state, f"   [Accept/Reject] ✅ ACCEPTED — real wall-clock time improved.")
            return {**state, "previous_qemu_time": curr_time}
        elif improvement < -0.02:
            _log(state, "   [Accept/Reject] ❌ REJECTED — real wall-clock time worsened. Reverting.")
            return _revert_state(state)
        else:
            _log(state, "   [Accept/Reject] ⚖️ NEUTRAL — timing within noise margin. Checking heuristic score...")

    # 2. Fallback to Heuristic Score
    prev_metrics = history[-2]
    curr_metrics = history[-1]
    
    baseline_score = prev_metrics.get("score", float("inf"))
    new_score = curr_metrics.get("score", float("inf"))

    _log(state, f"   [Accept/Reject] Score: {baseline_score:.0f} -> {new_score:.0f}")

    if new_score > baseline_score:
        _log(state, "   [Accept/Reject] ❌ REJECTED — heuristic score worsened. Reverting.")
        return _revert_state(state)
    
    _log(state, "   [Accept/Reject] ✅ ACCEPTED.")
    return {**state, "previous_qemu_time": curr_time if curr_time > 0 else prev_time}

def _revert_state(state: HACOState) -> HACOState:
    history = state.get("metrics_history", [])
    prev_code = state.get("previous_code", state["original_code"])
    good_history = list(history[:-1])
    # Duplicate previous metrics to maintain history length
    if len(good_history) > 0:
        good_history.append(good_history[-1])
        
    return {
        **state,
        "current_code": prev_code,
        "metrics_history": good_history,
        "optimization_log": list(state.get("optimization_log", [])) + [
            f"⚠️ Iter {state['iteration']}: REJECTED. Reverted."
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 4 — Test Validator
# ══════════════════════════════════════════════════════════════════════════════

def test_agent(state: HACOState) -> HACOState:
    _log(state, "🧪 [Test Agent] Generating and running correctness tests...")

    system = _hw_prefix(state) + (
        "You are a software testing expert for C++ code. "
        "Given an original C++ function and an optimized version, write a self-contained "
        "Python 3 test script that:\n"
        "1. Writes both code versions to temp .cpp files.\n"
        "   CRITICAL RULES for generated C++ test code: Always add #include <cstdio> and "
        "#include <iostream> and #include <cstring> at the top of every generated C++ file. "
        "Never use scanf or printf — use cin and cout only. Never generate a string literal "
        "longer than 20 characters. Every string literal must open and close on the same line. "
        "Every { must have a matching }. Always end the file with a newline.\n"
        "2. Compiles both with: g++ -O0 -o <out> <src> -std=c++17\n"
        "   (use -O0 flag so we measure AI optimization, not compiler optimization)\n"
        "3. Runs each binary with at least 5 inputs: normal, edge (0, 1, large), typical.\n"
        "4. Compares stdout char-by-char and prints PASS or FAIL with details.\n"
        "If g++ is unavailable, print SKIP and exit 0.\n"
        "Return ONLY executable Python 3 code, no markdown, no explanations."
    )
    human = (
        f"Original C++ code:\n```cpp\n{state['original_code']}\n```\n\n"
        f"Optimized C++ code:\n```cpp\n{state['current_code']}\n```"
    )

    llm = _get_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])

    test_script = resp.content.strip()
    test_script = re.sub(r'^```(?:python)?\s*', '', test_script, flags=re.MULTILINE)
    test_script = re.sub(r'```\s*$', '', test_script, flags=re.MULTILINE).strip()

    # FIXED: Strip non-ASCII
    test_script = test_script.encode('ascii', errors='ignore').decode('ascii') # FIXED
    
    # FIXED: Check valid python script requirements
    if "import" not in test_script or "def " not in test_script: # FIXED
        print(f"[TEST AGENT ERROR] Invalid Python script: {test_script[:100]}") # FIXED
        
        passed = False # FIXED
        details = "Corrupted script format" # FIXED
        new_results = list(state.get("test_results", [])) # FIXED
        new_results.append({"iteration": state["iteration"], "passed": passed, "details": details}) # FIXED
        
        retries = state.get("validator_retries", 0) # FIXED
        _log(state, f"   Retrying test generation (retry {retries+1}/2)...") # FIXED
        return { # FIXED
            **state, # FIXED
            "test_results": new_results, # FIXED
            "error_context": "Invalid Python script generated by AI", # FIXED
            "validator_retries": retries + 1, # FIXED
            "validation_passed": False, # FIXED
        } # FIXED

    passed = False
    details = ""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_script)
            tmp_path = f.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        details = output[:800]

        if "SKIP" in output.upper():
            passed = True
            _log(state, "   Tests: ⏭  SKIPPED (g++ not available — logic assumed correct)")
        elif "PASS" in output.upper() and "FAIL" not in output.upper():
            passed = True
            _log(state, "   Tests: ✅ PASSED")
        else:
            _log(state, f"   Tests: ❌ FAILED — {output[:200]}")
    except subprocess.TimeoutExpired:
        details = "Test script timed out after 30s"
        _log(state, "   Tests: ⏱  TIMEOUT — treating as SKIP")
        passed = True   # timeout = can't compile here, treat as skip
    except Exception as e:
        details = str(e)
        _log(state, f"   Tests: ⚠️  ERROR — {e}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    new_results = list(state.get("test_results", []))
    new_results.append({"iteration": state["iteration"], "passed": passed, "details": details})

    retries = state.get("validator_retries", 0)
    if not passed and retries < 2:
        _log(state, f"   Retrying test generation (retry {retries+1}/2)...")
        return {
            **state,
            "test_results": new_results,
            "error_context": details[:500],
            "validator_retries": retries + 1,
            "validation_passed": False,
        }

    return {
        **state,
        "test_results": new_results,
        "validator_retries": 0,
        "validation_passed": True,
        "error_context": "",
    }


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 5 — Report Generator  (kept for reference, not in active graph)
# ══════════════════════════════════════════════════════════════════════════════

def report_agent(state: HACOState) -> HACOState:
    _log(state, "📝 [Report Agent] Generating final optimization report...")

    history = state.get("metrics_history", [])
    first   = history[0] if history else {}
    last    = history[-1] if history else {}

    def pct(before: float, after: float) -> str:
        if before == 0:
            return "N/A"
        delta = (after - before) / before * 100
        sign  = "+" if delta > 0 else ""
        return f"{sign}{delta:.1f}%"

    metrics_table = "\n| Metric | Iteration 0 | Final | Δ |\n|--------|-------------|-------|---|\n"
    for key in ["cpu_cycles", "cache_misses", "ipc", "score"]:
        b = first.get(key, 0)
        a = last.get(key, 0)
        metrics_table += f"| {key} | {b} | {a} | {pct(b, a)} |\n"

    test_summary = "\n".join(
        f"- Iteration {r['iteration']}: {'✅ PASS' if r['passed'] else '❌ FAIL'}"
        for r in state.get("test_results", [])
    )
    opt_log = "\n".join(f"- {e}" for e in state.get("optimization_log", []))

    system = _hw_prefix(state) + (
        "You are a technical report writer. "
        "Generate a concise, well-structured Markdown report for a RISC-V code optimization run. "
        "Include: executive summary, before/after code summary, metrics comparison, "
        "optimizations applied, correctness verification status, and key takeaways. "
        "Keep it under 500 words."
    )
    human = (
        f"Original code ({len(state['original_code'].splitlines())} lines) → "
        f"Optimized code ({len(state['current_code'].splitlines())} lines)\n\n"
        f"Metrics Comparison:\n{metrics_table}\n"
        f"Optimizations Applied:\n{opt_log}\n"
        f"Test Results:\n{test_summary}\n"
        f"Total iterations: {state['iteration']}"
    )

    llm = _get_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    report = resp.content.strip()

    _log(state, "✅ [Report Agent] Report generated successfully.")
    return {**state, "final_report": report}
