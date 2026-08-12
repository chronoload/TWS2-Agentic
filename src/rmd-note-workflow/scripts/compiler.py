"""Rmd 编译引擎：扫描→预处理→并发编译→重试失败"""

import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from ._base import Config, setup_logging
from .preprocessor import preprocess_rmd, safe_filename, kill_zombie_rscript
from .scanner import scan_rmd

logger = setup_logging()


@dataclass
class CompileResult:
    file_path: str
    success: bool
    log: str = ""
    error_detail: str = ""
    duration: float = 0.0


@dataclass
class CompileReport:
    target_dir: str
    output_format: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    timeout: int = 0
    skipped: int = 0
    duration: float = 0.0
    results: list[CompileResult] = field(default_factory=list)
    failure_log_path: str = ""

    def summary(self) -> str:
        lines = [
            f"=== 编译汇总 ===",
            f"目录: {self.target_dir}",
            f"格式: {self.output_format}",
            f"总数: {self.total}, 通过: {self.passed}, 失败: {self.failed}, 超时: {self.timeout}, 跳过: {self.skipped}",
            f"耗时: {self.duration:.1f}s ({self.duration/60:.1f}m)",
        ]
        if self.failure_log_path:
            lines.append(f"失败日志: {self.failure_log_path}")
        return "\n".join(lines)


class Compiler:
    """Rmd 并发编译引擎"""

    def __init__(self, config: Config):
        self.config = config
        self.workers = config.get("infra.compilation.workers", 4)
        self.timeout = config.get("infra.output_formats.pdf.timeout", 600)
        self.preprocess_inline_r = config.get("infra.compilation.preprocess_inline_r", True)
        self.safe_filenames = config.get("infra.compilation.safe_filenames", True)
        self.kill_zombies = config.get("infra.compilation.kill_zombies", True)
        self._compiling_lock = threading.Lock()
        self._compiling_set: set[str] = set()
        self._completed_set: set[str] = set()
        self._failure_log: list[dict] = []
        self._failure_lock = threading.Lock()
        self._print_lock = threading.Lock()

    def compile_directory(self, target_dir: str, output_format: str = "pdf") -> CompileReport:
        """并发编译目录下所有 Rmd"""
        target = Path(target_dir)
        report = CompileReport(target_dir=str(target), output_format=output_format)
        start_time = time.time()

        if self.kill_zombies:
            killed = kill_zombie_rscript()
            if killed:
                logger.info(f"清理了 {killed} 个僵尸 Rscript 进程")

        # 收集 Rmd 文件
        rmd_files = sorted(target.glob("*.Rmd")) + sorted(target.glob("*.rmd"))
        rmd_files = list({f for f in rmd_files})  # 去重
        report.total = len(rmd_files)

        if not rmd_files:
            report.duration = time.time() - start_time
            return report

        # 并发编译
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._compile_one_wrapped, str(f), output_format, str(target)): f
                for f in rmd_files
            }
            for future in as_completed(futures):
                result = future.result()
                report.results.append(result)
                if result.success:
                    report.passed += 1
                elif "TIMEOUT" in result.error_detail:
                    report.timeout += 1
                else:
                    report.failed += 1

        report.duration = time.time() - start_time

        # 写入失败日志
        failure_log_path = target / self.config.get("infra.compilation.failure_log", "_compile_failures.csv")
        if self._failure_log:
            with open(failure_log_path, "w", encoding="utf-8") as f:
                f.write("file,reason,detail\n")
                for entry in self._failure_log:
                    f.write(f'"{entry["file"]}","{entry["reason"]}","{entry["detail"]}"\n')
            report.failure_log_path = str(failure_log_path)

        # 写入汇总
        summary_path = target / self.config.get("infra.compilation.summary_log", "_compile_summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(report.summary())

        return report

    def _compile_one_wrapped(self, rmd_path: str, output_format: str, target_dir: str) -> CompileResult:
        """包装编译单个文件（含锁保护）"""
        abs_path = os.path.abspath(rmd_path)

        # 预检：跳过已有 PDF
        pdf_path = Path(rmd_path).with_suffix(".pdf")
        with self._compiling_lock:
            if abs_path in self._completed_set:
                return CompileResult(file_path=rmd_path, success=True, log="已编译过")
            if abs_path in self._compiling_set:
                return CompileResult(file_path=rmd_path, success=True, log="编译中")
            self._compiling_set.add(abs_path)

        try:
            result = self.compile_one(rmd_path, output_format)
            with self._compiling_lock:
                self._completed_set.add(abs_path)
            return result
        except Exception as e:
            with self._compiling_lock:
                self._completed_set.add(abs_path)
            self._log_failure(rmd_path, "exception", str(e))
            return CompileResult(file_path=rmd_path, success=False, error_detail=str(e))
        finally:
            with self._compiling_lock:
                self._compiling_set.discard(abs_path)

    def compile_one(self, rmd_path: str, output_format: str) -> CompileResult:
        """编译单个 Rmd 文件"""
        start = time.time()
        path = Path(rmd_path)

        # 1. 格式扫描
        scan = scan_rmd(rmd_path)
        if not scan.ok:
            return CompileResult(
                file_path=rmd_path, success=False,
                log=scan.summary(),
                error_detail=f"格式扫描失败: {[e.message for e in scan.errors]}",
                duration=time.time() - start,
            )

        # 2. 预处理
        if self.preprocess_inline_r:
            temp_dir = Path(self.config.get("infra.assets.temp", "temp"))
            temp_dir.mkdir(parents=True, exist_ok=True)
            processed_path = preprocess_rmd(rmd_path, temp_dir / path.name)
        else:
            processed_path = path

        # 3. 渲染
        try:
            cmd = self._build_render_cmd(str(processed_path), output_format)
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout, cwd=str(path.parent),
            )
            if result.returncode == 0:
                return CompileResult(
                    file_path=rmd_path, success=True,
                    log=result.stdout[-500:] if result.stdout else "",
                    duration=time.time() - start,
                )
            else:
                error_detail = result.stderr[-500:] if result.stderr else result.stdout[-500:]
                self._log_failure(rmd_path, "render_error", error_detail)
                return CompileResult(
                    file_path=rmd_path, success=False,
                    log=result.stdout[-500:] if result.stdout else "",
                    error_detail=error_detail,
                    duration=time.time() - start,
                )
        except subprocess.TimeoutExpired:
            self._log_failure(rmd_path, "timeout", f"TIMEOUT after {self.timeout}s")
            return CompileResult(
                file_path=rmd_path, success=False,
                error_detail=f"TIMEOUT after {self.timeout}s",
                duration=time.time() - start,
            )

    def _build_render_cmd(self, rmd_path: str, output_format: str) -> list[str]:
        """构建 R 渲染命令"""
        # 使用 Rscript 调用 rmarkdown::render
        r_script = f"""
        library(rmarkdown)
        knitr::opts_hooks$set(error = function(options) {{ options$error = TRUE; options }})
        render("{rmd_path}", output_format = NULL, envir = new.env())
        """
        return ["Rscript", "-e", r_script]

    def _log_failure(self, fname: str, reason: str, detail: str) -> None:
        with self._failure_lock:
            self._failure_log.append({"file": fname, "reason": reason, "detail": detail})

    def retry_failed(self, failure_log_path: str) -> CompileReport:
        """重编译失败日志中的文件"""
        log_path = Path(failure_log_path)
        if not log_path.exists():
            return CompileReport(target_dir="", output_format="pdf")

        target_dir = log_path.parent
        failed_files = []
        with open(log_path, "r", encoding="utf-8") as f:
            next(f)  # skip header
            for line in f:
                parts = line.strip().split(",")
                if parts:
                    fname = parts[0].strip('"')
                    full_path = target_dir / fname
                    if full_path.exists():
                        failed_files.append(str(full_path))

        # 清除已完成集合，允许重新编译
        with self._compiling_lock:
            for f in failed_files:
                self._completed_set.discard(os.path.abspath(f))

        report = CompileReport(target_dir=str(target_dir), output_format="pdf")
        start = time.time()

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._compile_one_wrapped, f, "pdf", str(target_dir)): f
                for f in failed_files
            }
            for future in as_completed(futures):
                result = future.result()
                report.results.append(result)
                if result.success:
                    report.passed += 1
                else:
                    report.failed += 1

        report.total = len(failed_files)
        report.duration = time.time() - start
        return report
