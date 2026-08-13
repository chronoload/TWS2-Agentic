# OpenCode Adapter

## Skill 定义

将 `rmd-workflow/SKILL.md` 的内容复制到 OpenCode 的 skills 目录。

## 配置

在 `opencode.json` 中添加引用：
```json
{
  "references": {
    "rmd-workflow": {
      "path": "rmd-workflow",
      "description": "RMD 写作工作流插件"
    }
  }
}
```

## Dispatch 命令格式

orchestrator 输出的 DispatchCommand JSON 通过 OpenCode 的 `task` 工具执行：
```json
{
  "action": "dispatch",
  "prompt": "<prompt_file 内容 + prompt_context 填充>",
  "subagent_type": "general"
}
```
