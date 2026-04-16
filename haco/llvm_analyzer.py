import subprocess
import tempfile
import os
import re
import shutil
from typing import Dict, Any, List

def get_llvm_analysis(code_string: str) -> Dict[str, Any]:
    """
    Converts C++ to LLVM IR and extracts analysis hints using the 'opt' tool.
    """
    if shutil.which("clang++") is None:
        return {
            "success": False,
            "error": (
                "clang++ not found. Install LLVM/Clang and add it to PATH. "
                "Windows (winget): winget install LLVM.LLVM"
            ),
            "ir": "",
            "hints": []
        }
    if shutil.which("opt") is None:
        return {
            "success": False,
            "error": (
                "LLVM 'opt' tool not found. Install LLVM tools and add them to PATH. "
                "Windows (winget): winget install LLVM.LLVM"
            ),
            "ir": "",
            "hints": []
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        cpp_file = os.path.join(tmpdir, "code.cpp")
        ir_file = os.path.join(tmpdir, "code.ll")
        
        with open(cpp_file, "w") as f:
            f.write(code_string)
            
        # 1. Convert to LLVM IR
        # -S: Emit assembly/IR
        # -emit-llvm: Specifically output .ll IR
        # -O3: Use high optimization to see final form
        to_ir_cmd = [
            "clang++",
            "-S", "-emit-llvm",
            "-O3",
            "-o", ir_file,
            cpp_file,
            "-std=c++17"
        ]
        
        try:
            ir_proc = subprocess.run(to_ir_cmd, capture_output=True, text=True, timeout=15)
            if ir_proc.returncode != 0:
                return {
                    "success": False,
                    "error": f"Clang IR generation failed: {ir_proc.stderr}",
                    "ir": "",
                    "hints": []
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Clang IR generation timed out", "ir": "", "hints": []}
        except FileNotFoundError:
            return {
                "success": False,
                "error": (
                    "clang++ not found. Install LLVM/Clang and add it to PATH. "
                    "Windows (winget): winget install LLVM.LLVM"
                ),
                "ir": "",
                "hints": []
            }

        # 2. Extract hints using opt analysis
        # We can use multiple analysis passes: 
        # -scalar-evolution (loop bounds)
        # -loop-accesses (dependency analysis)
        # -instcount (instruction mix)
        analysis_cmd = [
            "opt",
            "-analyze",
            "-scalar-evolution",
            "-loop-accesses",
            "-instcount",
            ir_file
        ]
        
        hints = []
        try:
            ana_proc = subprocess.run(analysis_cmd, capture_output=True, text=True, timeout=10)
            analysis_output = ana_proc.stdout + ana_proc.stderr
            
            # Simple regex-based hint extraction
            if "Total number of instructions" in analysis_output:
                hints.append("Instruction count analysis available.")
            if "Loop at depth" in analysis_output:
                hints.append("Nested loops detected at IR level.")
            if "no dependence" in analysis_output:
                hints.append("Parallel loops/vectorization opportunities found.")
            if "aliased" in analysis_output.lower():
                hints.append("Pointer aliasing detected — may prevent optimizations.")
                
            # Read first 100 lines of IR
            with open(ir_file, "r") as f:
                ir_snippet = "".join(f.readlines()[:100])
                
        except Exception as e:
            analysis_output = f"Opt analysis error: {str(e)}"
            ir_snippet = ""

        return {
            "success": True,
            "ir": ir_snippet,
            "analysis": analysis_output[:2000], # truncate long output
            "hints": hints
        }

if __name__ == "__main__":
    # Mock testing with simple loop
    sample_code = """
    #include <vector>
    void compute(std::vector<int>& a, std::vector<int>& b) {
        for(size_t i=0; i<a.size(); i++) a[i] += b[i];
    }
    """
    print("Testing LLVM analyzer...")
    res = get_llvm_analysis(sample_code)
    print(res)
