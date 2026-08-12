# 原子：_load_defects（原 plan_cli.py 第 126 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _load_defects(index_path: str | Path = "") -> list[dict]:
    """读取 extractor 产出的静态缺陷（behavior/flag/merge/defuse），归一为可绑定列表。

    每条：{id, dim, kind, file, line, attr, detail, severity}
      - id 形如 `flag:app.py:1140:clear_without_set`（task --defect 绑定用）
      - dim 为维度名（behavior/flag/merge/defuse）
    """
    path = Path(index_path) if index_path else Path(INDEX_JSON)
    if not path.exists():
        return []
    try:
        idx = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    out: list[dict] = []
    sev = {"no_assignment": "red", "missing_behavior": "red", "clear_without_set": "red",
           "stale_cache": "red", "count_only_arbitration": "red",
           "cross_namespace_key": "red", "unguarded_key_consumer": "orange",
           "external_contract": "orange", "test_missing": "red",
           "test_after_implement": "orange", "loose_match": "yellow",
           "test_unverifiable": "yellow"}
    icon = {"red": "🔴", "orange": "🟠", "yellow": "🟡"}

    for b in idx.get("behavior", []) or []:
        if not (b.get("missing") or []):
            continue
        fid = f"behavior:{b.get('file','')}:{b.get('entry','')}"
        out.append({"id": fid, "dim": "behavior", "kind": "missing_behavior",
                    "file": b.get("file", ""), "line": 0, "attr": b.get("entry", ""),
                    "detail": "缺失副作用: " + ", ".join(b["missing"]),
                    "severity": "red"})
    for i in idx.get("flag_lifecycle", []) or []:
        fid = f"flag:{i.get('file','')}:{i.get('line',0)}:{i.get('kind','')}"
        out.append({"id": fid, "dim": "flag", "kind": i.get("kind", ""),
                    "file": i.get("file", ""), "line": i.get("line", 0),
                    "attr": i.get("attr", ""), "detail": i.get("detail", ""),
                    "severity": sev.get(i.get("kind", ""), "yellow")})
    for i in idx.get("merge_direction", []) or []:
        fid = f"merge:{i.get('file','')}:{i.get('line',0)}"
        out.append({"id": fid, "dim": "merge", "kind": i.get("kind", ""),
                    "file": i.get("file", ""), "line": i.get("line", 0),
                    "attr": i.get("fn", ""), "detail": i.get("detail", ""),
                    "severity": sev.get(i.get("kind", ""), "yellow")})
    for i in (idx.get("defuse") or {}).get("issues", []) or []:
        fid = f"defuse:{i.get('file','')}:{i.get('line',0)}:{i.get('attr','')}"
        out.append({"id": fid, "dim": "defuse", "kind": i.get("kind", ""),
                    "file": i.get("file", ""), "line": i.get("line", 0),
                    "attr": i.get("attr", ""), "detail": i.get("detail", ""),
                    "severity": sev.get(i.get("kind", ""), "yellow")})
    for i in idx.get("id_source", []) or []:
        fid = f"id_source:{i.get('file','')}:{i.get('line',0)}:{i.get('kind','')}"
        out.append({"id": fid, "dim": "id_source", "kind": i.get("kind", ""),
                    "file": i.get("file", ""), "line": i.get("line", 0),
                    "attr": i.get("consumer", ""), "detail": i.get("detail", ""),
                    "severity": sev.get(i.get("kind", ""), "yellow")})
    return out
