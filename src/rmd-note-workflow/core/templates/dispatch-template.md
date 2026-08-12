# 分发命令模板

orchestrator 生成 DispatchCommand 时使用此模板。每个角色对应一种 action。

## DispatchCommand JSON Schema

```json
{
  "action": "write | review | research | debug_compile",
  "role": "writer | fact_reviewer | coherence_reviewer | necessity_reviewer | continuity_reviewer | researcher | debugger_compiler",
  "prompt_file": "core/prompts/{role}.md",
  "prompt_context": {
    "project_name": "{{content.project.name}}",
    "reference_lesson_path": "{{content.reference.lesson}}",
    "reference_lines": "{{content.reference.lines}}",
    "quality_standards_path": "core/quality/quality-standards.md",
    "framework_path": "frameworks/{batch_id}-framework.md",
    "output_dir": "{{content.structure.layout == 'section-based' ? content.structure.dir_pattern : '.'}}",
    "lessons": ["L{N}", ...],
    "previous_batch_last": "L{M}_xxx.Rmd"
  },
  "output_paths": ["Notes/{L{N}_{slug}.Rmd", ...],
  "options": {
    "max_retry": 3,
    "timeout": null
  }
}
```

## Action 说明

### write
- Writer 按 framework 写 Rmd
- prompt_context 包含 framework、范本、质量标准路径
- output_paths 是目标 Rmd 文件路径

### review
- 5 种 reviewer 各自独立分发
- prompt_context 包含待审 Rmd 路径 + framework 路径
- 每个 reviewer 输出独立报告

### research
- Researcher 补缺
- prompt_context 包含缺失内容描述 + 关联文档

### debug_compile
- Debugger/Compiler 验证代码+编译
- prompt_context 包含 Rmd 路径 + data 依赖路径
