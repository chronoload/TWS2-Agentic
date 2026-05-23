# WebAnalyze II 快速参考指南

## 🎯 依赖关系简图

```
┌─────────────────────────────────────────────────────┐
│                    main.py                          │
│              启动程序入口点                           │
└──────────────────┬──────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
    ┌────────────┐        ┌──────────────┐
    │ DebugGUI   │        │ MainGUI      │
    │ 调试界面   │        │ 主界面       │
    └────────────┘        └──────┬───────┘
                                 │
                ┌────────────────┼────────────────┐
                ▼                ▼                ▼
            ┌─────────┐    ┌──────────┐    ┌──────────┐
            │ Tabs    │    │ Manager  │    │ System   │
            ├─────────┤    ├──────────┤    ├──────────┤
            │ Crawl   │    │Shortcut  │    │ Settings │
            │ Results │    │Download  │    │ Config   │
            │Resources│    │Resource  │    │ History  │
            │ GitHub  │    │Selector  │    └──────────┘
            │ History │    └──────────┘
            │Settings │
            └─────────┘
```

---

## 📊 数据流向

### 爬取流程数据流

```
用户点击 "开始爬取"
    ↓
start_crawling() [main_gui.py]
    ↓
创建线程: _crawl_worker()
    ↓
SearchEngine.crawl_website() [core/search_engine.py]
    ↓
获取结果: results (List[Dict[str, Any]])
    ↓
发送消息: message_queue.put(('update_results', results))
    ↓
ResultsTab.update_results(results) [components/results_tab.py]
    ↓
存储数据: self.current_pages = results
    ↓
Button方法可访问: results_tab.current_pages ✅
```

### 资源流程数据流

```
爬取完成后获取资源
    ↓
SearchEngine.get_resources_info() [core/search_engine.py]
    ↓
获取资源: resources_info (Dict)
    ↓
发送消息: message_queue.put(('update_resources', resources_info))
    ↓
ResourcesTab.update_resources(resources_info) [components/resources_tab.py]
    ↓
存储数据: self.current_resources = resources_info['all_resources']
    ↓
Button方法可访问: resources_tab.current_resources ✅
```

---

## 🔄 Button方法调用关系

### export_results() 数据流

```
按钮: "导出结果" (ResultsTab)
    ↓
export_results() [main_gui.py]
    ├─ Check: hasattr(self.results_tab, 'current_pages')
    ├─ Check: self.results_tab.current_pages not empty
    ├─ Get: data = self.results_tab.current_pages
    └─ Export: json.dump(data, filepath)
```

### _download_page_resources() 数据流

```
按钮: "下载资源" (ResultsTab中的行操作)
    ↓
_download_page_resources(page_data) [main_gui.py]
    ├─ Check: hasattr(self.resources_tab, 'current_resources')
    ├─ Check: self.resources_tab.current_resources not empty
    ├─ Get: all_resources = self.resources_tab.current_resources
    ├─ Filter: where resource.source_page == page_data.url
    └─ Show: download_manager.show_download_dialog(filtered_resources)
```

### _download_html_pages() 数据流

```
按钮: "下载HTML" (Results标签页)
    ↓
_download_html_pages() [main_gui.py]
    ├─ Check: hasattr(self.results_tab, 'current_pages')
    ├─ Check: self.results_tab.current_pages not empty
    ├─ Get: all_pages = self.results_tab.current_pages
    ├─ Process: for page_data in all_pages
    │   ├─ Get HTML: page_data.get('html', '')
    │   └─ Save: write to file
    └─ Complete: show success message
```

### _export_text() 数据流

```
按钮: "导出文本" (Results标签页)
    ↓
_export_text() [main_gui.py]
    ├─ Check: hasattr(self.results_tab, 'current_pages')
    ├─ Check: self.results_tab.current_pages not empty
    ├─ Get: data = self.results_tab.current_pages
    └─ Export: text format to file
```

---

## 🏗️ 导入链清单

### ✅ 已验证的导入链

| 模块 | 导入自 | 状态 |
|------|--------|------|
| gui/shortcuts.py | Tk基础库 | ✅ |
| gui/download_manager.py | gui/event_bus | ✅ |
| gui/resource_selector.py | gui/enhanced_logger | ✅ |
| gui/enhanced_logger.py | gui/event_bus | ✅ |
| gui/error_handler.py | gui/enhanced_logger, gui/event_bus | ✅ |
| gui/main_gui.py | 所有GUI组件 | ✅ |
| core/search_engine.py | 核心库 | ✅ |

---

## 📍 关键数据源位置

```
results_tab.current_pages
├─ 来源: ResultsTab.update_results()
├─ 类型: List[Dict[str, Any]]
├─ 内容: 
│   └─ Dict keys: url, title, content, html, links, images, 
│                 meta_description, headers, word_count, etc.
└─ 访问点:
    ├─ export_results()
    ├─ _download_html_pages()
    └─ _export_text()

resources_tab.current_resources
├─ 来源: ResourcesTab.update_resources()
├─ 类型: List[Dict[str, Any]]
├─ 内容:
│   └─ Dict keys: url, title, category, filename, 
│                 source_page, download, etc.
└─ 访问点:
    └─ _download_page_resources()

crawl_tab.settings
├─ 来源: CrawlTab 表单字段
├─ 类型: Dict[str, Any]
├─ 内容:
│   └─ url, keywords, max_depth, max_concurrent, etc.
└─ 访问点:
    └─ get_config()

config_manager.configs
├─ 来源: ConfigHistoryManager 文件存储
├─ 类型: List[Dict[str, Any]]
└─ 访问点:
    ├─ load_history()
    ├─ _delete_history()
    └─ _restore_config()
```

---

## 🛠️ 常见修复模式

### 模式 1: 访问Button方法中的标签页数据

```python
# ✅ 正确做法
if not hasattr(self.results_tab, 'current_pages'):
    messagebox.showinfo("提示", "没有数据")
    return

if not self.results_tab.current_pages:
    messagebox.showinfo("提示", "没有数据")
    return

data = self.results_tab.current_pages
# 处理data...

# ❌ 错误做法
data = self.current_pages  # main_gui中没有这个属性！
```

### 模式 2: 回调中使用标签页数据

```python
# ✅ 正确做法
def _bind_tab_callbacks(self):
    self.results_tab.on_export_callback = self.export_results
    
# 当按钮点击时，调用export_results()，它会访问results_tab

# ❌ 错误做法
def export_results(self):
    data = self.main_gui.current_pages  # 这个不存在！
```

### 模式 3: 在标签页之间传递数据

```python
# ✅ 正确做法
# 直接从资源tab获取
page_resources = [r for r in self.resources_tab.current_resources 
                  if r.get('source_page') == page_url]

# ❌ 错误做法
# 期望main_gui存储了副本
page_resources = [r for r in self.current_resources 
                  if r.get('source_page') == page_url]
```

---

## 🚀 快速启动步骤

### 1. 验证环境

```bash
# 检查编译
python -m py_compile gui/shortcuts.py gui/download_manager.py

# 检查导入
python -c "from gui.main_gui import AdvancedWebAnalyzerGUI"
```

### 2. 启动应用

```bash
python main.py
```

### 3. 测试Button功能

- [ ] 进行一次网站爬取
- [ ] 点击 "导出结果" 验证export_results()
- [ ] 点击 "下载资源" 验证_download_page_resources()
- [ ] 点击 "下载HTML" 验证_download_html_pages()
- [ ] 点击 "导出文本" 验证_export_text()

---

## ⚠️ 常见问题排查

### 问题: "AttributeError: 'NoneType' object has no attribute 'current_pages'"

**原因**: results_tab未初始化或未正确绑定

**解决**:
```python
# 检查这些行是否在_create_layout中
self.results_tab = ResultsTab(self.notebook, log_callback=self.log)
self.notebook.add(self.results_tab.frame, text="📊 结果展示")
```

### 问题: "ModuleNotFoundError: No module named 'event_bus'"

**原因**: 使用了绝对导入而非相对导入

**解决**:
```python
# ✅ 正确
from .event_bus import Events, event_bus

# ❌ 错误
from event_bus import Events, event_bus
```

### 问题: Button方法说"没有数据"但应该有数据

**原因**: 数据未从搜索线程正确传递到标签页

**解决**:
1. 检查message_queue是否发送了('update_results', results)
2. 检查ResultsTab.update_results()是否正确赋值self.current_pages
3. 检查是否有多个ResultsTab实例

---

## 📚 关键源文件导航

| 文件 | 用途 | 关键方法 |
|------|------|---------|
| [gui/main_gui.py](gui/main_gui.py) | 主界面协调 | export_results, _download_page_resources |
| [gui/components/results_tab.py](gui/components/results_tab.py) | 结果展示 | update_results, current_pages |
| [gui/components/resources_tab.py](gui/components/resources_tab.py) | 资源管理 | update_resources, current_resources |
| [gui/shortcuts.py](gui/shortcuts.py) | 快捷键系统 | ShortcutManager, register |
| [gui/download_manager.py](gui/download_manager.py) | 下载管理 | DownloadManager, start_download |
| [core/search_engine.py](../core/search_engine.py) | 爬虫引擎 | crawl_website, get_resources_info |

---

## 🔗 相关文档

- [DEPENDENCY_ANALYSIS_AND_FIXES.md](DEPENDENCY_ANALYSIS_AND_FIXES.md) - 详细分析报告
- [DEPENDENCY_FIX_REPORT.md](DEPENDENCY_FIX_REPORT.md) - 修复总结报告
- [PROJECT_ANALYSIS_REPORT.md](PROJECT_ANALYSIS_REPORT.md) - 项目架构分析

---

**最后更新**: 2026-02-13 15:30  
**状态**: ✅ 生产就绪
