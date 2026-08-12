r"""Texpile Draft 引擎 Python 实现。

移植自 electron/src/draft-service.ts（compileDraft）和 draft-daemon.ts（DraftDaemon）。
原版协议：用 \directlua 在 shipout/before 钩子里调 page_extract(\the\ShipoutBox)，
Lua 端 walker.lua 遍历 node list 输出每页的 NDJSON records；Python 端只做：
1. 拼 jobstring 调 lualatex
2. aux cycle（biber/bibtex + 多遍）
3. 读 _draft/pages.json + page-*.jsonl
4. 解析 draft.log 回填 image 文件名
5. Type1 字体解析（保留原 record 的 font.name/file 字段，由前端解析）

不做：
- Type1 字体 PFB 解析（前端用 vendored pdf.js 处理）
- instant patch 的 locate 算法（前端 DraftView 有 fallback 到全量 compile）
"""
import asyncio
import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

OUT = "_draft"
ONE_INCH_PT = 72.27
LUALATEX_TIMEOUT = 120  # 秒
BIBER_TIMEOUT = 90


def get_engine_dir() -> str:
    """返回 walker.lua / page-extract.lua / texd-loop.lua 所在目录（正斜杠）。"""
    return str(Path(__file__).parent).replace("\\", "/")


def _sha1(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha1(data).hexdigest()


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0


def _seed_bbl(root: Path, out_abs: Path, main_file: str) -> None:
    """拷贝现成的 .bbl 到 _draft/draft.bbl，让第一遍就能解析引用（arXiv 风格）。"""
    bbl = out_abs / "draft.bbl"
    cands: List[Path] = [root / (Path(main_file).stem + ".bbl")]
    # 从 \bibliography{NAME} 提取候选
    try:
        src = (root / main_file).read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\\bibliography\{([^}]+)\}", src)
        if m:
            for b in m.group(1).split(","):
                cands.append(root / (b.strip() + ".bbl"))
    except Exception:
        pass
    # 根目录下唯一的 .bbl
    try:
        all_bbl = [f for f in root.iterdir() if f.suffix == ".bbl"]
        if len(all_bbl) == 1:
            cands.append(all_bbl[0])
    except Exception:
        pass

    seed: Optional[Path] = None
    for c in cands:
        try:
            if c.stat().st_size > 0:
                seed = c
                break
        except Exception:
            continue
    if not seed:
        return

    # 仅在 draft.bbl 缺失/为空/被破坏/过时时重新 seed
    try:
        cur_ok = False
        if bbl.exists() and bbl.stat().st_size > 0:
            txt = bbl.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\\bibitem|\\entry", txt):
                cur_ok = _mtime(bbl) >= _mtime(seed)
        if cur_ok:
            return
        shutil.copyfile(seed, bbl)
    except Exception:
        pass


async def _run(cmd: str, args: List[str], cwd: Path, env: Optional[Dict[str, str]] = None,
               timeout: int = BIBER_TIMEOUT) -> None:
    """跑一个外部命令，失败也不抛（引用解析是增强，不阻塞编译）。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd, *args,
            cwd=str(cwd),
            env=env or os.environ.copy(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
    except FileNotFoundError:
        # 工具未安装 → 引用就不解析，不阻塞
        pass
    except Exception:
        pass


# per-root bcf hash：biber 慢，只在 .bcf 真变了才跑
_last_bcf: Dict[str, str] = {}


async def _aux_cycle(root: Path, out_abs: Path, main_file: str) -> bool:
    """latexmk-lite：biber（biblatex）或 bibtex（经典），返回 .bbl 是否变化。"""
    bbl = out_abs / "draft.bbl"
    bbl_before = f"{_mtime(bbl)}:{_sha1(bbl.read_bytes()) if bbl.exists() else ''}"
    _seed_bbl(root, out_abs, main_file)

    bcf = out_abs / "draft.bcf"
    aux = out_abs / "draft.aux"
    aux_text = aux.read_text(encoding="utf-8", errors="replace") if aux.exists() else ""

    if bcf.exists():
        h = _sha1(bcf.read_bytes())
        if _last_bcf.get(str(root)) != h:
            await _run("biber", ["--input-directory", OUT, "--output-directory", OUT, "draft"], cwd=root)
            _last_bcf[str(root)] = h
    elif re.search(r"\\bibdata\{", aux_text):
        # 经典 bibtex
        try:
            bibs = [f for f in root.iterdir() if f.suffix == ".bib"]
        except Exception:
            bibs = []
        bib_mtimes = [_mtime(f) for f in bibs]
        stale = (not bbl.exists()) or (bib_mtimes and max(bib_mtimes) > _mtime(bbl))
        if stale and bibs:
            prev = bbl.read_bytes() if bbl.exists() else None
            env = os.environ.copy()
            env["BIBINPUTS"] = str(root) + os.pathsep + env.get("BIBINPUTS", "")
            env["BSTINPUTS"] = str(root) + os.pathsep + env.get("BSTINPUTS", "")
            await _run("bibtex", ["draft"], cwd=out_abs, env=env)
            # 失败的 bibtex 可能留下空 bbl，恢复上次的
            ok = bbl.exists() and re.search(r"\\bibitem", bbl.read_text(encoding="utf-8", errors="replace"))
            if not ok and prev and re.search(rb"\\bibitem", prev):
                try:
                    bbl.write_bytes(prev)
                except Exception:
                    pass

    bbl_after = f"{_mtime(bbl)}:{_sha1(bbl.read_bytes()) if bbl.exists() else ''}"
    return bbl_after != bbl_before


def _export_daemon_refs(out_abs: Path) -> None:
    """从 .aux 抽 \bibcite/\newlabel 给 daemon 用（增强，不阻塞）。"""
    try:
        aux = out_abs / "draft.aux"
        if aux.exists():
            lines = aux.read_text(encoding="utf-8", errors="replace").splitlines()
            refs = [l for l in lines if re.match(r"^\\(bibcite|newlabel)\b", l)]
            (out_abs / "live-refs.tex").write_text("\n".join(refs) + "\n", encoding="utf-8")
        bbl = out_abs / "draft.bbl"
        if bbl.exists():
            shutil.copyfile(bbl, out_abs / "texd_daemon.bbl")
    except Exception:
        pass


# 全局编译代际：cancel-on-supersede
_compile_gen = 0
_active_proc: Optional[asyncio.subprocess.Process] = None


async def _engine_pass(engine: str, root: Path, job: str, out_abs: Path, gen: int) -> bool:
    """跑一遍 lualatex。返回是否正常结束（未被 supersede）。"""
    global _active_proc
    if gen != _compile_gen:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            engine,
            "-no-shell-escape", "-interaction=nonstopmode", "-synctex=1",
            f"-output-directory={OUT}", "-jobname=draft", job,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return True  # 引擎未装，由后面的 manifest 检查报错
    except Exception:
        return True

    _active_proc = proc
    try:
        await asyncio.wait_for(proc.wait(), timeout=LUALATEX_TIMEOUT)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
    finally:
        if _active_proc is proc:
            _active_proc = None
    return True


def _resolve_image_files(out_abs: Path, root: Path) -> List[Dict[str, Any]]:
    """从 draft.log 解析 <use FILE> + Requested size: W x H，回填 image record。"""
    files: List[Dict[str, Any]] = []
    try:
        log = (out_abs / "draft.log").read_text(encoding="utf-8", errors="replace")
        # 跨行匹配：use FILE 后 0-300 字符内出现 Requested size
        for m in re.finditer(r"<use ([^>]+)>[\s\S]{0,300}?Requested size: ([\d.]+)pt x ([\d.]+)pt", log):
            files.append({
                "file": m.group(1),
                "w": float(m.group(2)),
                "h": float(m.group(3)),
                "used": False,
            })
    except Exception:
        pass
    return files


def _resolve_image(files: List[Dict[str, Any]], w: float, h: float, root: Path) -> Optional[str]:
    def near(f): return abs(f["w"] - w) < 0.1 and abs(f["h"] - h) < 0.1
    hit = next((f for f in files if not f["used"] and near(f)), None)
    if not hit:
        hit = next((f for f in files if near(f)), None)
    if not hit:
        return None
    hit["used"] = True
    p = Path(hit["file"])
    if not p.is_absolute():
        p = root / hit["file"]
    return str(p).replace("\\", "/")


async def compile_draft(root: str | Path, main_file: str,
                        engine: str = "lualatex",
                        engine_dir: Optional[str] = None) -> Dict[str, Any]:
    """编译整个 .tex 项目，返回 DraftResult。

    Args:
        root: 项目根目录（绝对路径）
        main_file: 主文件相对路径（如 "main.tex" 或 "subdir/main.tex"）
        engine: LaTeX 引擎，默认 lualatex
        engine_dir: walker.lua 等所在目录；None 则用本模块目录

    Returns:
        成功: {ok, ms, passes, count, paperW, paperH, colW, marginX, marginY, pages}
        失败: {ok:false, error, ms, log?, superseded?}
    """
    global _compile_gen, _active_proc
    root = Path(root)
    main_file = main_file.replace("\\", "/")
    if engine_dir is None:
        engine_dir = get_engine_dir()
    engine_dir = engine_dir.replace("\\", "/")
    out_abs = root / OUT

    # supersede 之前的编译（Python 无 ++ 前缀自增，需显式 +1）
    _compile_gen += 1
    gen = _compile_gen
    if _active_proc:
        try:
            _active_proc.kill()
        except Exception:
            pass
        _active_proc = None

    def superseded() -> bool:
        return gen != _compile_gen

    out_abs.mkdir(parents=True, exist_ok=True)
    # 自忽略构建目录
    gi = out_abs / ".gitignore"
    if not gi.exists():
        try:
            gi.write_text("*\n", encoding="utf-8")
        except Exception:
            pass
    # 清理旧的 page 文件
    try:
        for f in out_abs.iterdir():
            if re.match(r"^page-\d+\.jsonl$", f.name) or f.name == "pages.json":
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    # jobstring：注入 page-extract.lua + shipout 钩子 + pdfoutput shim + \input 主文件
    setup = f"\\directlua{{TEXPILE_ENGINE_DIR='{engine_dir}'; TEXPILE_DRAFT_OUT='{OUT}'; dofile('{engine_dir}/page-extract.lua')}}"
    hooks = "\\AtBeginDocument{\\AddToHook{shipout/before}{\\directlua{page_extract(\\the\\ShipoutBox)}}\\AtEndDocument{\\directlua{page_extract_finish()}}}"
    pdf_shim = "\\ifdefined\\pdfoutput\\else\\newcount\\pdfoutput\\fi"
    job = f"{setup}{hooks}{pdf_shim}\\input{{{main_file}}}"

    t0 = time.monotonic()
    aux_existed = (out_abs / "draft.aux").exists()
    _seed_bbl(root, out_abs, main_file)

    await _engine_pass(engine, root, job, out_abs, gen)
    if superseded():
        return {"ok": False, "error": "superseded", "ms": int((time.monotonic() - t0) * 1000), "superseded": True}

    passes = 1
    bbl_changed = await _aux_cycle(root, out_abs, main_file)
    extra = 2 if bbl_changed else (1 if not aux_existed else 0)
    for _ in range(extra):
        if superseded():
            break
        await _engine_pass(engine, root, job, out_abs, gen)
        passes += 1

    if superseded():
        return {"ok": False, "error": "superseded", "ms": int((time.monotonic() - t0) * 1000), "superseded": True}

    _export_daemon_refs(out_abs)
    ms = int((time.monotonic() - t0) * 1000)

    manifest_path = out_abs / "pages.json"
    if not manifest_path.exists():
        # 编译失败：抽 log 的错误行
        log = ""
        try:
            log_text = (out_abs / "draft.log").read_text(encoding="utf-8", errors="replace")
            errs = [l for l in log_text.splitlines() if re.match(r"^!|error", l, re.IGNORECASE)]
            log = "\n".join(errs[-12:])
        except Exception:
            pass
        return {
            "ok": False,
            "error": "Draft compile produced no pages (is lualatex on PATH? see _draft/draft.log)",
            "ms": ms, "log": log,
        }

    try:
        manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"Draft manifest unreadable: {e}", "ms": ms}

    image_files = _resolve_image_files(out_abs, root)

    pages: List[Dict[str, Any]] = []
    for n in range(1, manifest.get("count", 0) + 1):
        p = out_abs / f"page-{n:03d}.jsonl"
        meta = (manifest.get("pages") or [{}])[n - 1] if n <= len(manifest.get("pages") or []) else {}
        records = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        # 回填 image 文件名
        if (image_files and '"t":"image"' in records) or '"t":"font"' in records:
            new_lines = []
            for ln in records.split("\n"):
                if ln.startswith('{"t":"font"'):
                    # 原 texpile 这里调 resolveType1Line 解析 Type1 字体 → {pfb, enc}
                    # TS2 端不解析，保留原样，让前端处理（或后续实现）
                    new_lines.append(ln)
                elif ln.startswith('{"t":"image"') and image_files:
                    try:
                        r = __import__("json").loads(ln)
                        file = _resolve_image(image_files, r.get("w", 0), (r.get("h") or 0) + (r.get("d") or 0), root)
                        if file:
                            r["file"] = file
                            new_lines.append(__import__("json").dumps(r))
                            continue
                    except Exception:
                        pass
                    new_lines.append(ln)
                else:
                    new_lines.append(ln)
            records = "\n".join(new_lines)
        pages.append({
            "n": n,
            "w": meta.get("w", 0),
            "h": meta.get("h", 0),
            "records": records,
        })

    # fallback 页面尺寸
    max_w = max((p["w"] for p in (manifest.get("pages") or [])), default=0)
    max_h = max((p["h"] for p in (manifest.get("pages") or [])), default=0)
    return {
        "ok": True,
        "ms": ms,
        "passes": passes,
        "count": manifest.get("count", len(pages)),
        "paperW": manifest.get("paperW") or (max_w + 2 * ONE_INCH_PT if max_w else 0),
        "paperH": manifest.get("paperH") or (max_h + 2 * ONE_INCH_PT if max_h else 0),
        "colW": manifest.get("colW") or 0,
        "marginX": ONE_INCH_PT,
        "marginY": ONE_INCH_PT,
        "pages": pages,
    }


async def stop_draft() -> Dict[str, Any]:
    """终止运行中的 draft 编译。"""
    global _compile_gen, _active_proc
    _compile_gen += 1  # 让所有在飞 compile 触发 superseded
    if _active_proc:
        try:
            _active_proc.kill()
        except Exception:
            pass
        _active_proc = None
    # 也停 daemon
    await DraftDaemon.stop_all()
    return {"ok": True}


class DraftDaemon:
    """常驻 lualatex daemon：preamble 加载一次，每段排版 ~1-2ms。

    协议（texd-loop.lua）：
      stdin:  HSIZE <hsize>\nGLYPHS\nTEXT\n<single-line text>\nEND\n
      stdout: @@CAP {...}\n@@READY <hsize> <textheight>\n@@R {...}\n[@@G record]...\n@@GEND\n

    串行化：用 asyncio.Lock 保证 stdin 协议不交错。
    """
    _instances: Dict[str, "DraftDaemon"] = {}
    _preamble_hash: Dict[str, str] = {}

    def __init__(self, root: Path, main_file: str, engine_dir: str, engine: str = "lualatex"):
        self.root = root
        self.main_file = main_file.replace("\\", "/")
        self.engine_dir = engine_dir.replace("\\", "/")
        self.engine = engine
        self.out_abs = root / OUT
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.lock = asyncio.Lock()
        self._hsize: float = 0.0
        self._textheight: float = 0.0
        self._last_use: float = 0.0

    @classmethod
    async def get(cls, root: str | Path, main_file: str, engine_dir: str) -> "DraftDaemon":
        """按 preamble hash 缓存 daemon 实例。preamble 变了会 respawn。"""
        root = Path(root)
        main_file = main_file.replace("\\", "/")
        # preamble hash：主文件 mtime + 大小（粗糙但够用）
        try:
            st = (root / main_file).stat()
            phash = f"{st.st_mtime_ns}:{st.st_size}"
        except Exception:
            phash = "unknown"
        key = str(root)
        old = cls._instances.get(key)
        if old and cls._preamble_hash.get(key) != phash:
            await old.kill()
            old = None
        if not old:
            old = DraftDaemon(root, main_file, engine_dir)
            await old._start()
            cls._instances[key] = old
            cls._preamble_hash[key] = phash
        return old

    async def _start(self) -> None:
        """启动 lualatex daemon。"""
        self.out_abs.mkdir(parents=True, exist_ok=True)
        # 构造 wrapper：\input preamble + 注入 texd-loop.lua + 循环调 texd_step
        wrapper_lines = [
            "\\ifdefined\\pdfoutput\\else\\newcount\\pdfoutput\\fi",
            f"\\input{{{self.main_file}}}",
            "\\makeatletter",
            "\\long\\def\\newlabel#1#2{\\expandafter\\gdef\\csname r@#1\\endcsname{#2}}",
            "\\long\\def\\bibcite#1#2{\\expandafter\\gdef\\csname b@#1\\endcsname{#2}}",
            "\\IfFileExists{_draft/live-refs.tex}{\\input{_draft/live-refs.tex}}{}",
            "\\makeatother",
            f"\\directlua{{TEXPILE_ENGINE_DIR='{self.engine_dir}'; dofile('{self.engine_dir}/texd-loop.lua')}}",
            "\\newcount\\texdrun \\texdrun=1",
            "\\loop",
            "  \\directlua{texd_step()}",
            "\\ifnum\\texdrun>0 \\repeat",
            "\\end{document}",
        ]
        wrapper = "\n".join(wrapper_lines)
        wrapper_path = self.out_abs / "texd-daemon.tex"
        wrapper_path.write_text(wrapper, encoding="utf-8")

        try:
            self.proc = await asyncio.create_subprocess_exec(
                self.engine,
                "-no-shell-escape", "-interaction=nonstopmode",
                f"-output-directory={OUT}", "-jobname=texd_daemon",
                "_draft/texd-daemon.tex",
                cwd=str(self.root),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            raise RuntimeError(f"{self.engine} not on PATH")
        # 等待 @@READY
        await self._read_until_ready()

    async def _readline(self, timeout: float = 6.0) -> Optional[str]:
        if not self.proc or not self.proc.stdout:
            return None
        try:
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=timeout)
        except (asyncio.TimeoutError, Exception):
            return None
        if not line:
            return None
        return line.decode("utf-8", errors="replace").rstrip("\r\n")

    async def _read_until_ready(self) -> None:
        """读到 @@READY <hsize> <textheight>。"""
        while True:
            line = await self._readline(timeout=10.0)
            if line is None:
                raise RuntimeError("daemon died before READY")
            if line.startswith("@@READY"):
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        self._hsize = float(parts[1])
                        self._textheight = float(parts[2])
                    except Exception:
                        pass
                return

    async def typeset_paragraph(self, text: str, hsize: Optional[float] = None,
                                want_glyphs: bool = True) -> Dict[str, Any]:
        """排版一段文本，返回 ParagraphResult。"""
        if not self.proc or not self.proc.stdin:
            return {"ok": False, "error": "daemon not running"}
        async with self.lock:
            self._last_use = time.monotonic()
            hs = f"{hsize:.4f}" if hsize is not None else f"{self._hsize:.4f}"
            # text 单行化（\r\n → 空格），保证协议 sentinel 不被破坏
            text_sl = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
            req = f"HSIZE {hs}\n"
            if want_glyphs:
                req += "GLYPHS\n"
            req += f"TEXT\n{text_sl}\nEND\n"
            try:
                self.proc.stdin.write(req.encode("utf-8"))
                await self.proc.stdin.drain()
            except Exception as e:
                return {"ok": False, "error": f"stdin write failed: {e}"}

            stats: Optional[Dict[str, Any]] = None
            records: List[Any] = []
            while True:
                line = await self._readline(timeout=6.0)
                if line is None:
                    return {"ok": False, "error": "daemon timeout"}
                if line.startswith("@@R "):
                    try:
                        stats = __import__("json").loads(line[4:])
                    except Exception:
                        stats = {"error": "stats parse failed"}
                elif line.startswith("@@G "):
                    try:
                        records.append(__import__("json").loads(line[4:]))
                    except Exception:
                        pass
                elif line.startswith("@@GEND"):
                    break
                elif line.startswith("@@CAP"):
                    continue  # 能力探测，忽略
            return {
                "ok": True,
                "records": records,
                "stats": stats,
                "hsize": self._hsize,
                "textheight": self._textheight,
            }

    async def kill(self) -> None:
        if self.proc:
            try:
                if self.proc.stdin:
                    self.proc.stdin.write(b"QUIT\n")
                    await self.proc.stdin.drain()
                try:
                    await asyncio.wait_for(self.proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self.proc.kill()
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    @classmethod
    async def stop_all(cls) -> None:
        for inst in list(cls._instances.values()):
            await inst.kill()
        cls._instances.clear()
        cls._preamble_hash.clear()


async def typeset_paragraph(root: str | Path, main_file: str, text: str,
                            hsize: Optional[float] = None,
                            engine_dir: Optional[str] = None) -> Dict[str, Any]:
    """单段排版的便捷入口。"""
    if engine_dir is None:
        engine_dir = get_engine_dir()
    try:
        daemon = await DraftDaemon.get(root, main_file, engine_dir)
        return await daemon.typeset_paragraph(text, hsize=hsize, want_glyphs=True)
    except Exception as e:
        return {"ok": False, "error": str(e)}
