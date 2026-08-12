# 原子：_gen_data_resources_trace（原 interface_chain_extractor.py 第 2909 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _gen_data_resources_trace(out_dir: Path) -> str:
    """生成数据资源追踪报告（从 SQLite 数据库读取）"""
    db_path = out_dir / "interface_chain.db"
    if not db_path.exists():
        return ""

    import datetime
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    report: list[str] = []
    report.append("# TS2 数据资源追踪报告")
    report.append(f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("---")
    report.append("")

    # 检查数据库表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}

    # 1. 数据池/状态 汇总
    if 'data_pools' in existing_tables:
        report.append("## 1. 数据池/状态汇总")
        report.append("")
        report.append("### 按类型分布")
        report.append("")
        report.append("| 类型 | 数量 | 说明 |")
        report.append("|------|------|------|")

        cursor.execute("SELECT kind, COUNT(*) as cnt FROM data_pools GROUP BY kind ORDER BY cnt DESC")
        kind_desc = {
            'list': '列表数据', 'dict': '字典/映射', 'cache': '缓存',
            'store': '持久化存储', 'pool': '实例池', 'singleton': '单例',
            'vector_store': '向量存储'
        }
        for row in cursor.fetchall():
            kind, cnt = row
            desc = kind_desc.get(kind, kind)
            report.append(f"| `{kind}` | {cnt} | {desc} |")
        report.append("")

    # 2. 核心数据池追踪
    if 'data_pools' in existing_tables:
        report.append("## 2. 核心数据池追踪")
        report.append("")
        report.append("### 2.1 Agent 会话数据池")
        report.append("")
        report.append("| 文件 | 行 | 变量名 | 类型 | 规模/初始化 |")
        report.append("|------|----|--------|------|-------------|")

        cursor.execute("""
            SELECT file, line, name, kind, size_hint 
            FROM data_pools 
            WHERE name LIKE '%agent%' OR name LIKE '%session%' OR name LIKE '%pool%'
            ORDER BY file, line
        """)
        agent_pools = cursor.fetchall()
        if agent_pools:
            for row in agent_pools:
                report.append(f"| `{row[0]}` | {row[1]} | `{row[2]}` | `{row[3]}` | {row[4] or '—'} |")
        else:
            report.append("| — | — | 未检测到 Agent 会话数据池 | — | — |")
        report.append("")

        # 2.2 持久化存储追踪
        report.append("### 2.2 持久化存储追踪")
        report.append("")
        report.append("| 文件 | 行 | 变量名 | 类型 | 规模/初始化 |")
        report.append("|------|----|--------|------|-------------|")

        cursor.execute("""
            SELECT file, line, name, kind, size_hint 
            FROM data_pools 
            WHERE kind IN ('store', 'vector_store')
            ORDER BY file, line
        """)
        stores = cursor.fetchall()
        if stores:
            for row in stores:
                report.append(f"| `{row[0]}` | {row[1]} | `{row[2]}` | `{row[3]}` | {row[4] or '—'} |")
        else:
            report.append("| — | — | 未检测到持久化存储 | — | — |")
        report.append("")

    # 3. 环境变量追踪
    if 'env_vars' in existing_tables:
        report.append("## 3. 环境变量追踪")
        report.append("")
        cursor.execute("SELECT COUNT(*) FROM env_vars")
        env_count = cursor.fetchone()[0]
        report.append(f"共发现 **{env_count}** 处环境变量读取。")
        report.append("")

        # 3.1 关键环境变量
        report.append("### 3.1 关键环境变量")
        report.append("")
        report.append("| 文件 | 行 | 变量名 | 默认值 | 上下文 |")
        report.append("|------|----|--------|--------|--------|")

        cursor.execute("""
            SELECT file, line, name, default_value, context 
            FROM env_vars 
            WHERE name IN ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'TS2_MODEL_ID', 
                            'MIMO_API_KEY', 'BOCHA_API_KEY', 'BAIDU_API_KEY',
                            'SABER_LLM_MODEL', 'EDITOR', 'SHELL', 'CONDA_PREFIX',
                            'API_KEY', 'SECRET_KEY', 'DATABASE_URL', 'REDIS_URL')
            ORDER BY file
        """)
        key_envs = cursor.fetchall()
        if key_envs:
            for row in key_envs:
                default = row[3] or '—'
                report.append(f"| `{row[0]}` | {row[1]} | `{row[2]}` | `{default}` | `{row[4][:40] if row[4] else '—'}` |")
        else:
            report.append("| — | — | 未检测到关键环境变量 | — | — |")
        report.append("")

    # 4. 硬编码常量追踪
    if 'hardcoded' in existing_tables:
        report.append("## 4. 硬编码常量追踪")
        report.append("")
        cursor.execute("SELECT COUNT(*) FROM hardcoded")
        hc_count = cursor.fetchone()[0]
        report.append(f"共发现 **{hc_count}** 处硬编码常量。")
        report.append("")

        # 4.1 硬编码端口
        report.append("### 4.1 硬编码端口")
        report.append("")
        report.append("| 文件 | 行 | 值 |")
        report.append("|------|----|----|")

        cursor.execute("SELECT file, line, value FROM hardcoded WHERE kind='port'")
        ports = cursor.fetchall()
        if ports:
            for row in ports:
                report.append(f"| `{row[0]}` | {row[1]} | `{row[2]}` |")
        else:
            report.append("| — | — | 未检测到硬编码端口 |")
        report.append("")

        # 4.2 硬编码 API 路径
        report.append("### 4.2 硬编码 API 路径")
        report.append("")
        report.append("| 文件 | 行 | 路径 |")
        report.append("|------|----|------|")

        cursor.execute("SELECT file, line, value FROM hardcoded WHERE kind='path' AND value LIKE '/api%' ORDER BY file, line")
        api_paths = cursor.fetchall()
        if api_paths:
            for row in api_paths:
                report.append(f"| `{row[0]}` | {row[1]} | `{row[2]}` |")
        else:
            report.append("| — | — | 未检测到硬编码 API 路径 |")
        report.append("")

    # 5. 静态资源追踪
    if 'static_resources' in existing_tables:
        report.append("## 5. 静态资源追踪")
        report.append("")
        cursor.execute("SELECT COUNT(*) FROM static_resources")
        sr_count = cursor.fetchone()[0]
        report.append(f"共发现 **{sr_count}** 处静态资源引用。")
        report.append("")

        report.append("| 文件 | 行 | 路径 | 类型 | 上下文 |")
        report.append("|------|----|------|------|--------|")

        cursor.execute("SELECT file, line, path, kind, context FROM static_resources ORDER BY file, line")
        resources = cursor.fetchall()
        if resources:
            for row in resources:
                report.append(f"| `{row[0]}` | {row[1]} | `{row[2][:60]}` | `{row[3]}` | `{row[4][:30] if row[4] else '—'}` |")
        else:
            report.append("| — | — | 未检测到静态资源 | — | — |")
        report.append("")

    # 6. 端点数据来源追踪
    if 'endpoints' in existing_tables:
        report.append("## 6. API 端点数据来源追踪")
        report.append("")

        report.append("### 6.1 Agent 会话端点（含数据来源字段）")
        report.append("")
        report.append("| 方法 | 路径 | 处理函数 | 返回数据字段 |")
        report.append("|------|------|----------|--------------|")

        cursor.execute("""
            SELECT method, path, func, response_keys
            FROM endpoints 
            WHERE path LIKE '%agent%' AND func != ''
            ORDER BY path
        """)
        agent_endpoints = cursor.fetchall()
        if agent_endpoints:
            for row in agent_endpoints:
                keys = row[3] or '—'
                source_info = " ✓ 含 source 字段" if 'source' in keys.lower() else ""
                report.append(f"| `{row[0]}` | `{row[1]}` | `{row[2]}` | {keys}{source_info} |")
        else:
            report.append("| — | — | 未检测到 Agent 相关端点 | — |")
        report.append("")

        # 6.2 数据权威性判定逻辑说明
        report.append("### 6.2 数据权威性判定逻辑")
        report.append("")
        report.append("```")
        report.append("source 字段值          权威性       说明")
        report.append("─────────────────────────────────────────────")
        report.append("agent_live             最高         正在流式生成")
        report.append("agent_pool             高           实例在内存池中")
        report.append("session_store          中           仅持久化存储")
        report.append("checkpoint             低           检查点兜底数据")
        report.append("none                   无           无数据")
        report.append("```")
        report.append("")

    # 7. def-use 一致性检查
    if 'defuse_issues' in existing_tables:
        report.append("## 7. Def-Use 属性一致性检查")
        report.append("")

        cursor.execute("SELECT COUNT(*) FROM defuse_issues")
        issue_count = cursor.fetchone()[0]
        report.append(f"共发现 **{issue_count}** 条 def-use 一致性问题。")
        report.append("")

        if issue_count > 0:
            report.append("| 问题类型 | 属性 | 文件 | 行 | 对象 | 默认值 | 描述 |")
            report.append("|----------|------|------|----|------|--------|------|")

            cursor.execute("SELECT * FROM defuse_issues ORDER BY kind, file LIMIT 50")
            issues = cursor.fetchall()
            for row in issues:
                report.append(f"| `{row[0]}` | `{row[1]}` | `{row[2]}` | {row[3]} | `{row[4]}` | `{row[5]}` | {row[6]} |")
            if issue_count > 50:
                report.append(f"| ... | ... | ... | ... | ... | ... | 共 {issue_count} 条问题，详见数据库 |")
        report.append("")

    # 8. 统计摘要
    report.append("## 8. 统计摘要")
    report.append("")
    report.append("| 维度 | 数量 |")
    report.append("|------|------|")

    for table_name, label in [
        ('endpoints', 'API 端点'),
        ('models', '请求模型'),
        ('hardcoded', '硬编码常量'),
        ('env_vars', '环境变量'),
        ('data_pools', '数据池/状态'),
        ('static_resources', '静态资源'),
    ]:
        if table_name in existing_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            report.append(f"| {label} | {count} |")

    report.append("")
    report.append("---")
    report.append("")
    report.append("*报告由 interface_chain_extractor.py 自动生成*")

    conn.close()
    return "\n".join(report)
