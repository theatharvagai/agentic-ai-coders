"""
haco/rag.py
Process hardware specifications from PDFs directly using pdfplumber.
No caching system included.
"""
from __future__ import annotations

import re
import pdfplumber

OPTIMIZATION_KEYWORDS = [
    # Pipeline
    "pipeline", "stage", "in-order", "out-of-order", "stall", "hazard",
    "fetch", "decode", "execute", "writeback",
    # Branch
    "branch", "predictor", "BTB", "BHT", "RAS", "mispredict", "penalty",
    # Cache
    "cache", "L1", "L2", "scratchpad", "SRAM", "TCM", "line size",
    "cache miss", "cache hit", "associativity", "eviction",
    # Memory
    "alignment", "misaligned", "trap", "load", "store", "memory access",
    "latency", "throughput",
    # Registers
    "register", "x0", "x31", "ABI", "caller", "callee", "spill",
    "register pressure", "live variable",
    # ISA extensions
    "RV32I", "RV64I", "RV32M", "RV32C", "RV32F", "RV32A",
    "multiply", "divide", "compressed", "atomic",
    # RI5CY specific
    "hardware loop", "post-increment", "SIMD", "MAC", "dot product",
    "packed", "fixed-point",
    # Shakti specific
    "scratchpad", "unified", "in-order", "3-stage", "5-stage",
    # FE310 specific
    "E31", "ITIM", "branch target buffer", "branch history",
    # Performance
    "IPC", "CPI", "cycles per", "instructions per", "clock frequency",
    "MHz", "throughput", "performance"
]


def extract_pdf_text(pdf_path: str) -> str: # REWRITTEN
    full_text = "" # REWRITTEN
    with pdfplumber.open(pdf_path) as pdf: # REWRITTEN
        for page in pdf.pages: # REWRITTEN
            text = page.extract_text() # REWRITTEN
            if text: # REWRITTEN
                full_text += text + "\n" # REWRITTEN
    return full_text # REWRITTEN


def extract_important_hardware_context(pdf_path: str) -> str: # REWRITTEN
    """
    Extract ONLY optimization-relevant content directly from the PDF file.
    Scored paragraphs mapping to RISC-V hardware characteristics are returned natively.
    """
    full_text = extract_pdf_text(pdf_path) # REWRITTEN
    
    if len(full_text.strip()) < 200: # REWRITTEN
        raise ValueError("PDF extracted less than 200 characters. File may be a scanned image or corrupted. Please upload a text-based PDF.") # REWRITTEN
        
    non_ascii = sum(1 for c in full_text if ord(c) > 127) # REWRITTEN
    if non_ascii / len(full_text) > 0.20: # REWRITTEN
        raise ValueError("PDF contains over 20% non-ASCII characters. Likely a binary or scanned file. Please upload a text-based PDF.") # REWRITTEN

    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', full_text) if p.strip()] # REWRITTEN
    
    scored_paragraphs = [] # REWRITTEN
    for p in paragraphs: # REWRITTEN
        score = 0 # REWRITTEN
        p_lower = p.lower() # REWRITTEN
        for kw in OPTIMIZATION_KEYWORDS: # REWRITTEN
            if kw.lower() in p_lower: # REWRITTEN
                score += 3 # REWRITTEN
        if score >= 3: # REWRITTEN
            scored_paragraphs.append((score, p)) # REWRITTEN
            
    scored_paragraphs.sort(key=lambda x: x[0], reverse=True) # REWRITTEN
    
    out_text = "" # REWRITTEN
    for score, text in scored_paragraphs: # REWRITTEN
        if len(out_text) + len(text) + 2 > 2000: # REWRITTEN
            remaining = 2000 - len(out_text) - 4 # REWRITTEN
            if remaining > 0: # REWRITTEN
                out_text += text[:remaining] + "..." # REWRITTEN
            break # REWRITTEN
        out_text += text + "\n\n" # REWRITTEN
        
    return out_text.strip() # REWRITTEN
