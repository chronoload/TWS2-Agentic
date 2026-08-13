-- env_mapping.lua
-- Pandoc Lua filter: fenced div class → LaTeX 定理类环境
-- 兼容 EnvironmentMapping 规范
-- 支持 Book / CUMCM / Beamer 三种场景

local env_list = {
  -- 定理类
  "theorem", "proposition", "corollary", "lemma", "claim",
  -- 定义类
  "definition", "example", "problem",
  -- 备注类
  "remark", "note", "solution", "assumption",
  -- CUMCM 扩展
  "conjecture", "axiom", "principle",
}

function Div(el)
  -- 定理 / 定义 / 备注类环境
  for _, env in ipairs(env_list) do
    if el.classes[1] == env then
      local content = pandoc.write(
        pandoc.Pandoc(el.content),
        { format = "latex", extensions = {} }
      )
      content = content:gsub("\n+$", "")
      return pandoc.RawBlock("latex",
        "\\begin{" .. env .. "}\n" ..
        content .. "\n" ..
        "\\end{" .. env .. "}"
      )
    end
  end

  -- proof 环境（amsthm 自带 QED）
  if el.classes[1] == "proof" then
    local content = pandoc.write(
      pandoc.Pandoc(el.content),
      { format = "latex", extensions = {} }
    )
    content = content:gsub("\n+$", "")
    return pandoc.RawBlock("latex",
      "\\begin{proof}\n" ..
      content .. "\n" ..
      "\\end{proof}"
    )
  end

  -- cbox 彩色盒子（tcolorbox），通过 {title="..."} 传参
  if el.classes[1] == "cbox" then
    local title = el.attributes["title"] or ""
    local content = pandoc.write(
      pandoc.Pandoc(el.content),
      { format = "latex", extensions = {} }
    )
    content = content:gsub("\n+$", "")
    return pandoc.RawBlock("latex",
      "\\begin{cbox}[" .. title .. "]\n" ..
      content .. "\n" ..
      "\\end{cbox}"
    )
  end

  -- Beamer block 环境
  if el.classes[1] == "block" then
    local title = el.attributes["title"] or ""
    local content = pandoc.write(
      pandoc.Pandoc(el.content),
      { format = "latex", extensions = {} }
    )
    content = content:gsub("\n+$", "")
    return pandoc.RawBlock("latex",
      "\\begin{block}{" .. title .. "}\n" ..
      content .. "\n" ..
      "\\end{block}"
    )
  end

  if el.classes[1] == "alert" then
    local title = el.attributes["title"] or ""
    local content = pandoc.write(
      pandoc.Pandoc(el.content),
      { format = "latex", extensions = {} }
    )
    content = content:gsub("\n+$", "")
    return pandoc.RawBlock("latex",
      "\\begin{alertblock}{" .. title .. "}\n" ..
      content .. "\n" ..
      "\\end{alertblock}"
    )
  end

  if el.classes[1] == "example-block" then
    local title = el.attributes["title"] or ""
    local content = pandoc.write(
      pandoc.Pandoc(el.content),
      { format = "latex", extensions = {} }
    )
    content = content:gsub("\n+$", "")
    return pandoc.RawBlock("latex",
      "\\begin{exampleblock}{" .. title .. "}\n" ..
      content .. "\n" ..
      "\\end{exampleblock}"
    )
  end
end
