import subprocess
import tempfile
import os
import time
import re
import shutil
from typing import Dict, Any

def compile_and_run_qemu(code_string: str, optimization_flag: str = "-O3") -> Dict[str, Any]:
    """
    Compiles C++ code for RISC-V and runs it in QEMU to measure execution time.
    """
    compiler_candidates = ["riscv64-linux-gnu-g++", "riscv64-unknown-elf-g++"]
    qemu_user_bin = "qemu-riscv64"
    qemu_system_bin = "qemu-system-riscv64"
    compiler = next((c for c in compiler_candidates if shutil.which(c) is not None), None)
    qemu_user_ok = shutil.which(qemu_user_bin) is not None
    qemu_system_ok = shutil.which(qemu_system_bin) is not None

    if compiler is None:
        return {
            "success": False,
            "error": (
                "RISC-V cross compiler not found. Expected one of: "
                f"{', '.join(compiler_candidates)}. "
                "Windows (MSYS2): pacman -S mingw-w64-ucrt-x86_64-riscv64-unknown-elf-gcc"
            ),
            "execution_time": 0.0,
            "stdout": ""
        }
    if not qemu_user_ok:
        detail = (
            f"{qemu_user_bin} not found. Install QEMU user emulator and add it to PATH."
        )
        if qemu_system_ok:
            detail += (
                f" Detected {qemu_system_bin}, but HACO needs user-mode "
                f"{qemu_user_bin} for direct ELF execution."
            )
        return {
            "success": False,
            "error": detail,
            "execution_time": 0.0,
            "stdout": ""
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        cpp_file = os.path.join(tmpdir, "code.cpp")
        bin_file = os.path.join(tmpdir, "code.bin")
        
        with open(cpp_file, "w") as f:
            f.write(code_string)
            
        # 1. Compile with RISC-V cross-compiler
        # -static is required for qemu-user
        compile_cmd = [
            compiler,
            "-static",
            optimization_flag,
            "-o", bin_file,
            cpp_file,
            "-std=c++17"
        ]
        
        try:
            comp_proc = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=15)
            if comp_proc.returncode != 0:
                return {
                    "success": False,
                    "error": f"Compilation failed: {comp_proc.stderr}",
                    "execution_time": 0.0,
                    "stdout": ""
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Compilation timed out", "execution_time": 0.0, "stdout": ""}
        except FileNotFoundError:
            return {
                "success": False,
                "error": (
                    f"{compiler} not found. Install a RISC-V cross compiler and add it to PATH. "
                    "Windows (MSYS2): pacman -S mingw-w64-ucrt-x86_64-riscv64-unknown-elf-gcc"
                ),
                "execution_time": 0.0,
                "stdout": ""
            }

        # 2. Run in QEMU
        # We run multiple times to average out noise
        run_cmd = [qemu_user_bin, bin_file]
        times = []
        last_stdout = ""
        
        try:
            for _ in range(3):
                start = time.perf_counter()
                run_proc = subprocess.run(run_cmd, capture_output=True, text=True, timeout=10)
                end = time.perf_counter()
                
                if run_proc.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Runtime error: {run_proc.stderr}",
                        "execution_time": 0.0,
                        "stdout": ""
                    }
                times.append((end - start) * 1000) # milliseconds
                last_stdout = run_proc.stdout
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timed out", "execution_time": 0.0, "stdout": ""}
        except FileNotFoundError:
            return {
                "success": False,
                "error": (
                    f"{qemu_user_bin} not found. Install QEMU user emulator and add it to PATH."
                ),
                "execution_time": 0.0,
                "stdout": ""
            }

        avg_time = sum(times) / len(times)
        return {
            "success": True,
            "execution_time": round(avg_time, 4),
            "stdout": last_stdout,
            "min_time": round(min(times), 4)
        }

def approximate_cycles(execution_time_ms: float, target_freq_mhz: float = 100.0) -> int:
    """
    Approximates cycles: Cycles = Time * Frequency
    """
    return int(execution_time_ms * (target_freq_mhz * 1000))

if __name__ == "__main__":
    # Mock testing with simple loop
    sample_code = """
    #include <iostream>
    int main() {
        long sum = 0;
        for(long i=0; i<1000000; i++) sum += i;
        std::cout << sum << std::endl;
        return 0;
    }
    """
    print("Testing QEMU runner...")
    res = compile_and_run_qemu(sample_code)
    print(res)
