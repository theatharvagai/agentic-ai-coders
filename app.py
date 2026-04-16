"""
app.py — HACO Streamlit Dashboard
Single-page, no-scroll layout for a 1080p desktop.
Run: streamlit run app.py
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx
from dotenv import load_dotenv

# ── Env & path setup ──────────────────────────────────────────────────────────
load_dotenv(override=True) # FIXED: Force reload dynamic keys
sys.path.insert(0, str(Path(__file__).parent))

# ── Sample presets ────────────────────────────────────────────────────────────
SAMPLES = {
    "🔢 Recursive Fibonacci": Path("samples/fibonacci.cpp").read_text(encoding="utf-8"),
    "🔍 Naive String Search": Path("samples/string_search.cpp").read_text(encoding="utf-8"),
    "⚡ Recursive Power Function": Path("samples/power_fn.cpp").read_text(encoding="utf-8"),
}

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HACO — Hardware-Aware Code Optimizer",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS — single page, no scroll, dark premium theme ──────────────────
st.markdown("""
<style>
/* Import modern fonts */
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');

/* Dynamic Background Mesh */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #05050a !important;
    background-image: 
        radial-gradient(at 0% 0%, rgba(63, 23, 107, 0.3) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(20, 89, 133, 0.3) 0px, transparent 50%) !important;
    color: #e2e8f0 !important;
    font-family: 'Outfit', sans-serif !important;
}
/* Hide Streamlit default UI */
header[data-testid="stHeader"] { display: none !important; }
#MainMenu, footer { visibility: hidden !important; }

/* Glassmorphic Sidebar */
[data-testid="stSidebar"] {
    background: rgba(10, 15, 25, 0.5) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }

/* Futuristic Header Panel */
.haco-header {
    background: rgba(20, 25, 45, 0.4);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 16px 28px;
    display: flex;
    align-items: center;
    gap: 20px;
    margin-bottom: 24px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}
.haco-title {
    font-family: 'Outfit', sans-serif;
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #a78bfa 0%, #38bdf8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    text-shadow: 0px 2px 10px rgba(167, 139, 250, 0.2);
}
.haco-sub {
    font-size: 13px;
    color: #94a3b8;
    margin: 4px 0 0 0;
    font-weight: 300;
    letter-spacing: 0.5px;
}

/* Glowing Badges */
.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 30px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-right: 8px;
    text-transform: uppercase;
    box-shadow: inset 0 0 10px rgba(255,255,255,0.02);
}
.badge-idle    { background: rgba(30, 41, 59, 0.6); color: #94a3b8; border: 1px solid rgba(255,255,255,0.1); }
.badge-running { background: rgba(14, 165, 233, 0.15); color: #38bdf8; border: 1px solid #0ea5e9; text-shadow: 0 0 8px #38bdf8; box-shadow: 0 0 15px rgba(14,165,233,0.3); }
.badge-done    { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid #22c55e; text-shadow: 0 0 8px #4ade80; }
.badge-error   { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid #ef4444; }
.badge-ls      { background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid #6366f1; }

/* Interactive Glass Metric Cards */
.metric-card {
    background: rgba(20, 25, 40, 0.4);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 12px;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    position: relative;
    overflow: hidden;
}
.metric-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; width: 100%; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(167, 139, 250, 0.5), transparent);
    opacity: 0;
    transition: opacity 0.3s ease;
}
.metric-card:hover {
    transform: translateY(-4px);
    background: rgba(30, 35, 55, 0.6);
    border-color: rgba(167, 139, 250, 0.3);
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4), 0 0 15px rgba(167, 139, 250, 0.1);
}
.metric-card:hover::before { opacity: 1; }
.metric-label { font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
.metric-value { font-size: 24px; font-weight: 700; color: #ffffff; font-family: 'JetBrains Mono', monospace; }
.metric-delta-pos { color: #4ade80; font-size: 13px; font-weight: 700; background: rgba(74, 222, 128, 0.1); padding: 2px 6px; border-radius: 4px; margin-left: 6px; }
.metric-delta-neg { color: #f87171; font-size: 13px; font-weight: 700; background: rgba(248, 113, 113, 0.1); padding: 2px 6px; border-radius: 4px; margin-left: 6px; }

/* Cyberpunk Log Terminal */
.log-terminal {
    background: rgba(5, 5, 10, 0.7);
    border: 1px solid rgba(56, 189, 248, 0.2);
    border-radius: 12px;
    padding: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.6;
    color: #cbd5e1;
    height: 280px;
    overflow-y: auto;
    box-shadow: inset 0 0 30px rgba(0,0,0,0.8);
    position: relative;
}
.log-terminal::-webkit-scrollbar { width: 6px; }
.log-terminal::-webkit-scrollbar-thumb { background: rgba(56, 189, 248, 0.3); border-radius: 10px; }
.log-terminal .log-step  { color: #38bdf8; font-weight: 700; }
.log-terminal .log-agent { color: #c084fc; font-weight: 700; text-shadow: 0 0 5px rgba(192, 132, 252, 0.4); }
.log-terminal .log-ok    { color: #4ade80; }
.log-terminal .log-warn  { color: #fbbf24; }
.log-terminal .log-err   { color: #f87171; font-weight: 700; }

/* Premium Buttons */
.stButton > button {
    background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%) !important;
    color: white !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    letter-spacing: 0.5px !important;
    padding: 10px !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 25px rgba(168, 85, 247, 0.5) !important;
    border-color: rgba(255,255,255,0.3) !important;
}
.stButton > button:disabled {
    background: rgba(30, 41, 59, 0.5) !important;
    color: #64748b !important;
    border-color: transparent !important;
    box-shadow: none !important;
    transform: none !important;
}

/* Translucent Text Areas */
.stTextArea textarea {
    background: rgba(15, 20, 30, 0.6) !important;
    color: #f8fafc !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
    line-height: 1.5 !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 10px !important;
    transition: all 0.3s ease !important;
}
.stTextArea textarea:focus {
    border-color: #38bdf8 !important;
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2) !important;
    background: rgba(20, 25, 40, 0.8) !important;
}
.stTextArea label {
    font-family: 'Outfit', sans-serif !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    color: #e2e8f0 !important;
    margin-bottom: 8px !important;
}

/* Base Spacing & Layout */
.element-container { margin-bottom: 8px !important; }
section[data-testid="stSidebar"] > div { padding: 20px 10px; }
.block-container { padding: 2rem 3rem !important; max-width: 1400px !important; }
hr { border: 0 !important; height: 1px !important; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent) !important; margin: 24px 0 !important; }

/* Neon Progress Bar */
.stProgress > div > div {
    background: linear-gradient(90deg, #38bdf8, #a855f7) !important;
    box-shadow: 0 0 10px rgba(168, 85, 247, 0.5) !important;
}
</style>
""", unsafe_allow_html=True)


# ── Session state init ─────────────────────────────────────────────────────────
def _init_session():
    defaults = {
        "running":        False,
        "log_lines":      [],
        "orig_code":      SAMPLES["🔢 Recursive Fibonacci"],
        "opt_code":       "",
        "before_metrics": {},
        "after_metrics":  {},
        "final_report":   "",
        "iteration":      0,
        "status":         "idle",
        "hardware_name":  "Generic RV32IMAC",
        "hardware_context": "",
        "rag_log_msg":    "",
        "preset":         "🔢 Recursive Fibonacci",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_session()


# ── Metric helper ──────────────────────────────────────────────────────────────
def _delta_html(before: float, after: float, lower_is_better: bool = True) -> str:
    if before == 0:
        return ""
    delta = (after - before) / before * 100
    if lower_is_better:
        good = delta < 0
    else:
        good = delta > 0
    cls = "metric-delta-pos" if good else "metric-delta-neg"
    sign = "+" if delta > 0 else ""
    return f'<span class="{cls}">{sign}{delta:.1f}%</span>'


# ── Run pipeline in background thread ─────────────────────────────────────────
def _run_pipeline(code: str, hw_name: str, hw_context: str, rag_log_msg: str, max_iter: int):
    """Called in a thread; mutates st.session_state safely via simple writes."""
    from haco.graph import get_graph
    from haco.state import HACOState

    initial_state: HACOState = {
        "original_code":      code,
        "previous_code":      code,
        "current_code":       code,
        "iteration":          0,
        "max_iterations":     max_iter,
        "bug_report":         "",
        "bottlenecks":        {},
        "optimization_log":   [],
        "test_results":       [],
        "metrics_history":    [],
        "hardware_name":      hw_name,
        "hardware_context":   hw_context,
        "error_context":      "",
        "validator_retries":  0,
        "validation_passed":  True,
        "llvm_ir":            "",
        "llvm_hints":         [],
        "qemu_time":          0.0,
        "previous_qemu_time": 0.0,
        "final_report":       "",
        "log_lines":          [],
    }

    st.session_state.log_lines = ["🚀 Pipeline started...", rag_log_msg]
    st.session_state.status = "running"

    graph = get_graph()

    try:
        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_state in event.items():
                # Sync logs
                new_logs = node_state.get("log_lines", [])
                if new_logs:
                    st.session_state.log_lines = new_logs

                # Sync iteration counter
                if "iteration" in node_state:
                    st.session_state.iteration = node_state["iteration"]

                # Sync metrics
                history = node_state.get("metrics_history", [])
                if history:
                    st.session_state.before_metrics = history[0]
                    st.session_state.after_metrics  = history[-1]

                # Sync optimized code
                if "current_code" in node_state and node_name == "optimizer_agent":
                    st.session_state.opt_code = node_state["current_code"]

        st.session_state.status = "done"
        st.session_state.log_lines.append("✅ Pipeline complete!")

    except Exception as e:
        st.session_state.status = "error"
        err_type = type(e).__name__
        tb_snippet = traceback.format_exc(limit=5).strip()
        st.session_state.log_lines.append(f"❌ Error [{err_type}]: {e}")
        st.session_state.log_lines.append("🧵 Traceback (most recent calls):")
        st.session_state.log_lines.append(tb_snippet[:1200] if tb_snippet else "No traceback available.")
    finally:
        st.session_state.running = False


def _tool_status(tool_name: str) -> tuple[bool, str]:
    """Return (is_available, resolved_path_or_empty)."""
    resolved = shutil.which(tool_name)
    return (resolved is not None, resolved or "")


def _tool_status_any(tool_names: list[str]) -> tuple[bool, str, str]:
    """Return (is_available, matched_tool_name_or_empty, resolved_path_or_empty)."""
    for tool in tool_names:
        resolved = shutil.which(tool)
        if resolved:
            return True, tool, resolved
    return False, "", ""


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

# ── HEADER ────────────────────────────────────────────────────────────────────
status_map = {
    "idle":    ("badge-idle",    "⚫ Idle"),
    "running": ("badge-running", "🔵 Running"),
    "done":    ("badge-done",    "🟢 Done"),
    "error":   ("badge-error",   "🔴 Error"),
}
s_cls, s_txt = status_map.get(st.session_state.status, status_map["idle"])
ls_active = bool(os.environ.get("LANGCHAIN_API_KEY", ""))
ls_badge = '<span class="badge badge-ls">⚡ LangSmith Active</span>' if ls_active else '<span class="badge badge-idle">LangSmith Inactive</span>'

st.markdown(f"""
<div class="haco-header">
  <div>
    <p class="haco-title">🔧 HACO — Hardware-Aware Code Optimizer</p>
    <p class="haco-sub">Multi-Agent LangGraph · RISC-V Simulator · Groq llama-3.3-70b-versatile</p>
  </div>
  <div style="margin-left:auto; display:flex; align-items:center; gap:8px;">
    <span class="badge {s_cls}">{s_txt}</span>
    {ls_badge}
    <span class="badge badge-idle">Iter: {st.session_state.iteration}/3</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")

    # Local toolchain capabilities
    with st.expander("🧰 Capabilities", expanded=False):
        capabilities = [
            (["clang++"], "LLVM C++ frontend"),
            (["opt"], "LLVM optimization analysis tool"),
            (["riscv64-linux-gnu-g++", "riscv64-unknown-elf-g++"], "RISC-V cross compiler"),
            (["qemu-riscv64", "qemu-system-riscv64"], "RISC-V emulator"),
        ]
        available_count = 0
        for tool_bins, label in capabilities:
            ok, matched_tool, path = _tool_status_any(tool_bins)
            if ok:
                available_count += 1
                st.success(f"✅ {label}: `{matched_tool}`")
                st.caption(path)
                if label == "RISC-V emulator" and matched_tool == "qemu-system-riscv64":
                    st.caption("Note: user-mode `qemu-riscv64` is preferred for direct ELF execution.")
            else:
                st.warning(f"⚠️ {label}: missing (`{' | '.join(tool_bins)}`)")

        if available_count < len(capabilities):
            st.info(
                "Missing tools are optional. HACO will still run using simulator fallback where possible."
            )

    st.divider()

    # API keys
    with st.expander("🔑 API Keys", expanded=not bool(os.environ.get("GROQ_API_KEY"))):
        groq_key = st.text_input("Groq API Key", value=os.environ.get("GROQ_API_KEY", ""),
                                type="password", key="groq_key_input")
        ls_key  = st.text_input("LangSmith API Key", value=os.environ.get("LANGCHAIN_API_KEY", ""),
                                type="password", key="ls_key_input")
        if st.button("💾 Apply Keys"):
            if groq_key:
                os.environ["GROQ_API_KEY"] = groq_key
            if ls_key:
                os.environ["LANGCHAIN_API_KEY"] = ls_key
                os.environ["LANGCHAIN_TRACING_V2"] = "true"
                os.environ["LANGCHAIN_PROJECT"] = "HACO"
            st.success("Keys applied!")
            st.rerun()

    st.divider()

    # Preset selector
    st.markdown("**📋 Preset Code**")
    preset = st.selectbox(
        "Choose sample",
        list(SAMPLES.keys()),
        index=list(SAMPLES.keys()).index(st.session_state.preset),
        label_visibility="collapsed",
    )
    if preset != st.session_state.preset:
        st.session_state.preset   = preset
        st.session_state.orig_code = SAMPLES[preset]
        st.session_state.opt_code  = ""
        st.session_state.before_metrics = {}
        st.session_state.after_metrics  = {}
        st.session_state.final_report   = ""
        st.session_state.log_lines      = []
        st.session_state.status         = "idle"
        st.session_state.iteration      = 0
        st.rerun()

    st.divider()

    # Hardware doc upload
    st.markdown("**📁 Hardware Selection**")
    
    hw_opts = [
        "Generic RV32IMAC",
        "SiFive HiFive1 (FE310-G000) — IoT Embedded, 32-bit RV32IMAC",
        "Shakti C-Class (IIT Madras) — India's Indigenous RISC-V, 32-64 bit",
        "PULPino RI5CY (ETH Zurich) — Ultra-Low-Power DSP, 4-stage pipeline"
    ]
    hw_name = st.selectbox(
        "Select Target Hardware Architecture",
        hw_opts,
        index=0
    )
    st.session_state.hardware_name = hw_name
    
    uploaded = st.file_uploader(
        "Upload Hardware Spec PDF for selected architecture",
        type=["txt", "pdf"],
        label_visibility="collapsed",
    )
    
    status_label = st.empty()
    
    if uploaded:
        save_path = "temp_hw.pdf" # REWRITTEN
        with open(save_path, "wb") as f: # REWRITTEN
            f.write(uploaded.getbuffer()) # REWRITTEN
            
        st.session_state.hardware_context = save_path # REWRITTEN
        st.session_state.rag_log_msg = "✅ PDF natively mapped for pipeline extraction" # REWRITTEN
        status_label.success("✅ PDF loaded and ready for extraction") # REWRITTEN
    else:
        status_label.caption("⚠️ No spec loaded — using generic RISC-V defaults")
        st.session_state.hardware_context = "" # REWRITTEN
        st.session_state.rag_log_msg = "⚠️ No spec loaded — using generic RISC-V defaults" # REWRITTEN

    st.divider()

    # Max iterations
    max_iter = st.slider("Max Iterations", 1, 5, 3)

    st.divider()

    # Run / Reset buttons
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        run_clicked = st.button(
            "▶ Run",
            disabled=st.session_state.running,
            use_container_width=True,
        )
    with col_r2:
        reset_clicked = st.button("↺ Reset", use_container_width=True)

    if reset_clicked:
        for k in ["opt_code","before_metrics","after_metrics","final_report",
                  "log_lines","status","iteration","running"]:
            st.session_state[k] = [] if "metrics" in k or "log" in k or "results" in k else "" if "code" in k or "report" in k or "status" in k else False if "running" in k else 0 if "iteration" in k else "idle" if k == "status" else ""
        st.session_state.status  = "idle"
        st.session_state.running = False
        st.session_state.iteration = 0
        st.rerun()

    if run_clicked and not st.session_state.running:
        if not os.environ.get("GROQ_API_KEY"):
            st.error("⚠️ Set your Groq API key first!")
        else:
            st.session_state.running   = True
            st.session_state.status    = "running"
            st.session_state.log_lines = []
            st.session_state.opt_code  = ""
            st.session_state.before_metrics = {}
            st.session_state.after_metrics  = {}
            st.session_state.final_report   = ""
            st.session_state.iteration = 0

            thread = threading.Thread(
                target=_run_pipeline,
                args=(
                    st.session_state.orig_code,
                    st.session_state.hardware_name,
                    st.session_state.hardware_context,
                    st.session_state.rag_log_msg,
                    max_iter
                ),
                daemon=True,
            )
            add_script_run_ctx(thread)
            thread.start()
            st.rerun()


# ── MAIN AREA ─────────────────────────────────────────────────────────────────
main_col1, main_col2 = st.columns([1, 1], gap="small")

# ── Code panels ───────────────────────────────────────────────────────────────
with main_col1:
    user_code = st.text_area(
        "📄 Original C++ Code",
        value=st.session_state.orig_code,
        height=240,
        key="orig_code_widget",
    )
    st.session_state.orig_code = user_code

with main_col2:
    opt_val = st.session_state.opt_code if st.session_state.opt_code else "// Optimized code will appear here after running the pipeline..."
    st.text_area(
        "✨ Optimized C++ Code",
        value=opt_val,
        height=240,
        disabled=True,
    )

# ── Progress ──────────────────────────────────────────────────────────────────
if st.session_state.running:
    # Cycle progress hint
    progress_val = min(st.session_state.iteration / max(max_iter, 1), 0.95)
    st.progress(progress_val)
    time.sleep(1)
    st.rerun()
elif st.session_state.status == "done":
    st.progress(1.0)

st.divider()

# ── Metrics + Chart ───────────────────────────────────────────────────────────
metrics_col, chart_col = st.columns([1.1, 1.4], gap="small")

with metrics_col:
    m_before = st.session_state.before_metrics
    m_after  = st.session_state.after_metrics

    mc1, mc2 = st.columns(2, gap="small")

    metric_defs = [
        ("Exec Time (ms)", "execution_time", True),
        ("CPU Cycles",   "cpu_cycles",   True),
        ("Cache Misses", "cache_misses", True),
        ("IPC",          "ipc",          False),
        ("Score",        "score",        True),
    ]

    with mc1:
        st.markdown('<p style="font-size:12px;font-weight:600;color:#818cf8;margin-bottom:4px;">📊 BEFORE (Iter 0)</p>', unsafe_allow_html=True)
        for label, key, lib in metric_defs:
            val = m_before.get(key, "—")
            val_str = f"{val:.3f}" if isinstance(val, float) else str(val)
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">{label}</div>
              <div class="metric-value">{val_str}</div>
            </div>""", unsafe_allow_html=True)

    with mc2:
        st.markdown('<p style="font-size:12px;font-weight:600;color:#4ade80;margin-bottom:4px;">📊 AFTER (Final)</p>', unsafe_allow_html=True)
        for label, key, lib in metric_defs:
            val_b = m_before.get(key, 0) or 0
            val_a = m_after.get(key, "—")
            val_str = f"{val_a:.3f}" if isinstance(val_a, float) else str(val_a)
            delta_html = _delta_html(val_b, val_a if isinstance(val_a, (int, float)) else 0, lib) if m_after else ""
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">{label} {delta_html}</div>
              <div class="metric-value">{val_str}</div>
            </div>""", unsafe_allow_html=True)

with chart_col:
    st.markdown('<p style="font-size:12px;font-weight:600;color:#c084fc;margin-bottom:4px;">📈 Before vs After</p>', unsafe_allow_html=True)

    if m_before and m_after:
        chart_keys   = ["cpu_cycles", "cache_misses", "branch_mispredicts"]
        chart_labels = ["CPU Cycles", "Cache Misses", "Branch Mispredicts"]
        b_vals = [m_before.get(k, 0) for k in chart_keys]
        a_vals = [m_after.get(k, 0)  for k in chart_keys]

        fig = go.Figure(data=[
            go.Bar(name="Before", x=chart_labels, y=b_vals,
                   marker_color="#6366f1", opacity=0.85,
                   text=[f"{v:,}" for v in b_vals], textposition="auto",
                   textfont=dict(size=10, color="white")),
            go.Bar(name="After",  x=chart_labels, y=a_vals,
                   marker_color="#4ade80", opacity=0.85,
                   text=[f"{v:,}" for v in a_vals], textposition="auto",
                   textfont=dict(size=10, color="white")),
        ])
        fig.update_layout(
            barmode="group",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", family="Inter", size=11),
            margin=dict(l=10, r=10, t=10, b=30),
            height=250,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center",
                        font=dict(size=11)),
            xaxis=dict(gridcolor="#1e2d45", tickfont=dict(size=10)),
            yaxis=dict(gridcolor="#1e2d45", tickfont=dict(size=10)),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown("""
        <div style="background:#0f1320;border:1px solid #1e2d45;border-radius:8px;
                    height:250px;display:flex;align-items:center;justify-content:center;
                    color:#334155;font-size:12px;text-align:center;">
            Chart appears after pipeline run
        </div>""", unsafe_allow_html=True)

st.divider()

# ── Terminal Log ──────────────────────────────────────────────────────────────
st.markdown('<p style="font-size:12px;font-weight:600;color:#38bdf8;margin-bottom:4px;">🖥️ Live Agent Log</p>', unsafe_allow_html=True)
log_lines = st.session_state.log_lines or ["Waiting for pipeline to start..."]

# Color-code log lines
def _colorize(line: str) -> str:
    if line.startswith("🚀") or line.startswith("✅") or "PASS" in line:
        return f'<span class="log-ok">{line}</span>'
    elif "Agent" in line or "agent" in line:
        return f'<span class="log-agent">{line}</span>'
    elif "❌" in line or "ERROR" in line or "FAIL" in line:
        return f'<span class="log-err">{line}</span>'
    elif "⚠️" in line or "WARN" in line:
        return f'<span class="log-warn">{line}</span>'
    elif "Step" in line or "Iteration" in line or "🔧" in line:
        return f'<span class="log-step">{line}</span>'
    return line

colored_log = "<br>".join(_colorize(l) for l in log_lines[-50:])
st.markdown(
    f'<div class="log-terminal">{colored_log}</div>',
    unsafe_allow_html=True,
)

# ── Auto-refresh while running ─────────────────────────────────────────────────
if st.session_state.running:
    time.sleep(2)
    st.rerun()
