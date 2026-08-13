# app.js 架构文档

> 原生 Vanilla JS SPA，约 12,000 行，由 `static/index.html` 加载

---

## 1. 服务端路由

`server/app.py:5256` — `/static` 目录通过 Starlette `StaticFiles` 挂载：
- `/static/app.js` → `static/app.js`
- `/static/style.css` → `static/style.css`
- `/static/vditor/...` → Vditor 编辑器资源

`app.js` 在 `static/index.html` 末尾加载：
```html
<script src="/static/app.js"></script>
```

---

## 2. 整体架构分层

```
┌──────────────────────────────────────────────────────────────┐
│                    app.js (SPA)                               │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Auth     │  │ TS2Client│  │ Global   │  │ Editor       │ │
│  │ Layer    │  │ API Class│  │ State    │  │ Service      │ │
│  │ L:9-56   │  │ L:58-346 │  │ L:374-444│  │ L:448-787    │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Vditor   │  │ PDF      │  │ Monaco   │  │ File Tree    │ │
│  │ Editor   │  │ Viewer   │  │ Editor   │  │ & Manager    │ │
│  │ L:791-947│  │ L:1164-  │  │ (external│  │ L:1610-1810  │ │
│  │          │  │   1560   │  │  lib)    │  │              │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Nav Tabs │  │ Tasks    │  │ Bookmarks│  │ SaberSystem  │ │
│  │ L:1561-  │  │ Kanban   │  │ L:2398-  │  │ Dashboard    │ │
│  │  1607    │  │ L:2116-  │  │  2550    │  │ L: (TS2Cli.) │ │
│  │          │  │  2397    │  │          │  │              │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Courses  │  │ Projects │  │ Source   │  │ Slides /     │ │
│  │ & Exec   │  │          │  │ Browser  │  │ Mindmap /    │ │
│  │ L:3136-  │  │ L:2551-  │  │ L:2609-  │  │ Jupyter      │ │
│  │  3500+   │  │  2608    │  │  3043    │  │ (iframe)     │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ WebSocket│  │ Split    │  │ Electron │                   │
│  │ L:256-296│  │ Pane     │  │ Title Bar│                   │
│  │          │  │ L:~3500+ │  │ L:350-370│                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 核心模块详解

### 3.1 鉴权层 (Auth Layer, L:9-56)

```javascript
function checkAuth()       // 请求 /api/system/authInfo 判断是否需要鉴权
function showAuthDialog()  // 显示授权弹框
function doLogin()         // 提交流 code/token，或工作区独立授权
function switchWorkspace() // 工作区模式：独立授权，不依赖 session cookie
```

- 无鉴权时弹框覆盖整个界面
- 工作区支持独立授权码（`_pendingSwitchPath` 机制）
- Code + Token 双凭证，后端任一个匹配即可

### 3.2 TS2Client API 类 (L:58-346)

```javascript
class TS2Client {
  api(endpoint, body)      // 底层 fetch 封装，自动处理 401/403
  getFile / putFile        // 读写文件 (REST API)
  readDir / search         // 浏览文件 (REST API)
  downloadBinary(path)     // 二进制下载，arrayBuffer
  downloadFile(path)       // 触发下载（<a> 标签）
  connectWS() / sendWS()   // WebSocket 连接与消息
  getTasks / createTask    // 任务 CRUD
  getBookmarks             // 书签
  getCourses / getCourseProgress / updateLessonStatus  // 课程
  agentChat / getAgentSessions  // AI Agent
  saber*                   // SaberSystem 全部 API
}
```

- 所有请求使用原生 `fetch()`，无 axios 依赖
- 401 → `showAuthDialog()`
- WebSocket 自动重连（3 秒间隔）

### Agent 会话管理 (Agent Session, ~L:9600-10750)

```javascript
state.agentMessages    // 聊天消息数组
state.agentStreaming   // 流式请求状态
state.agentXHR         // 当前活动的 XHR（用于中止）
```

**关键函数：**

| 函数 | 位置 | 功能 |
|------|------|------|
| `initAgentPanel()` | ~L:9648 | 初始化 Agent 面板，自动恢复上次会话 |
| `_restoreLastSession()` | ~L:9657 | 从数据库恢复最近一次会话 |
| `sendAgentMessage()` | ~L:10137 | 发送消息（流式 → 同步回退） |
| `sendAgentStream()` | ~L:10175 | SSE 流式请求，支持30秒超时和部分数据恢复 |
| `sendAgentSync()` | ~L:10442 | 同步回退请求 |
| `cancelAgentChat()` | ~L:10467 | 中止流式请求 |
| `addAgentMessage()` | ~L:9736 | 添加消息并渲染，同时新增对话流导航块 |
| `renderAgentMessages()` | ~L:9822 | 渲染所有消息（含data-index属性支持导航跳转） |
| `toggleFlowNav()` | ~L:10756 | 切换对话流导航侧边栏 |
| `_addFlowNavBlock()` | ~L:10771 | 为每条消息添加导航块（图标+标签） |
| `_jumpToFlowBlock()` | ~L:10815 | 点击导航块跳转到对应消息 |
| `flowNavPrev()` / `flowNavNext()` | ~L:10825 | 导航上下翻页 |
| `_resetFlowNav()` | ~L:10837 | 新建会话时清空导航 |
| `switchToSession()` | ~L:10702 | 切换到指定会话（同步session_id） |
| `createNewSession()` | ~L:10676 | 创建新会话（清空对话流导航） |

**对话流导航：**
- 参考 tkinter `AgentAssistantWindow._nav_blocks` 设计
- 侧边栏（默认折叠），点击"📑"按钮展开
- 每条消息对应一个导航块，显示角色图标（👤用户/🤖助手/🔧工具）和内容预览
- 点击导航块跳转到对应消息（`scrollIntoView`）
- 底部⬆/⬇按钮上下翻页
- 新建会话或切换会话时自动清空/重建导航
- 纯前端实现，不注入 agent 后端状态

**SSE 流式增强：**
- 30秒无响应超时（收到数据后重置计时器）
- 网络中断时尝试恢复部分已接收数据
- 出错时自动回退到同步请求
- 用户可随时点击"停止"中止流式请求

### 3.3 全局状态 (Global State, L:374-444)

```javascript
const state = {
  currentDir, openTabs, recentFiles,
  fileContents, originalContents, activeTab,
  expandedDirs, contextTarget, activeNavTab,
  tasks, bookmarks, projects, courses,
  vditorReady, vditor, dirCache,
  editorMode, pdfDoc, viewingPdf,
  agentMessages, mediaAttachments,
  dashboard: { life, attention, ideals, plans, tasks, ... }
}
```

单一全局 `state` 对象，所有模块直接读写。无响应式框架，通过手工 `render*()` 函数同步 DOM。

### 3.4 Editor Service (L:448-787)

统一的编辑器入口，按文件类型分发：

| 文件类型 | 处理方式 | 行号 |
|---------|---------|------|
| `.pdf` | 内置 PDF Viewer（pdfjs） | L:458-476 |
| `.docx/.xlsx/.pptx` | 服务端转换为 PDF 后渲染 | L:478-480 |
| `.kmind` | iframe 加载思维导图 | L:482-504 |
| `.html/.htm` | `window.open()` 新标签页 | L:506-509 |
| 代码文件 (`.py/.js/.ts` 等) | Monaco Editor（单例 `__monaco__` 标签页） | L:511-551 |
| 其他文本文件 | Vditor（富文本 Markdown 编辑器） | L:552-581 |

支持：
- 分屏模式：`openInPane(path, paneId)` / `switchInPane(path, paneId)` (L:680-786)
- 拖拽排序标签页 (L:1840-1886)
- 最近文件记录 (L:672-677)

### 3.5 Vditor 编辑器 (L:791-947)

```javascript
function initVditor()           // 主编辑器初始化 (L:791-884)
function initPaneVditor(paneId) // 分屏 Vditor 初始化 (L:887-947)
```

- CDN: `/static/vditor`（本地资源，非 CDN）
- 初始化在首次编辑文件时懒执行
- 支持 hint/autocomplete
- 文件上传通过 `upload.url = /api/file/upload`
- `after` 回调标记 `state.vditorReady`
- `input` 回调自动同步内容到 `state.fileContents` 并标记修改

### 3.6 PDF Viewer (L:1164-1560)

- 使用 pdfjsLib 解析渲染
- 高清渲染：`devicePixelRatio * 1.5` 超采样
- 文本层覆盖（支持选中复制）
- 目录/大纲：`loadPdfOutline()` / `_renderOutlineItems()`
- AI 阅读面板（调用 `client.agentChat()` 做 PDF Q&A）
- 分屏 PDF：`loadPdfInPane()` / `renderPanePdfPage()` (L:950-1018)
- Office 文档转 PDF：`openOfficeAsPdf()` (L:1519-1559)

### 3.7 文件树 (L:1610-1810)

```javascript
async function loadFileTree(subdir)  // 加载目录缓存
function renderFileTree()            // 渲染树
function onTreeItemClick(entry)      // 单击展开/打开
function onTreeItemContext(e, entry) // 右键菜单
```

- 懒加载：目录展开时 `client.readDir()` 后才缓存
- `state.dirCache` 缓存避免重复请求
- 目录排序：目录在前，文件在后，按名字排序
- 支持搜索模式：在搜索结果中也可打开文件

**右键菜单选项：**

| 动作 | 说明 |
|------|------|
| `open` | 打开文件/展开目录 |
| `rename` | 重命名文件 |
| `duplicate` | 复制文件/文件夹 |
| `download` | 下载文件 |
| `addResource` | 添加为课程资源 |
| `openWith` | 选择打开方式（IDE选择器） |
| `externalEdit` | 外部编辑器打开 |
| `collabOpen` | 协同打开副本 |
| **`copyPath`** | **复制文件/文件夹路径到剪贴板** |
| **`fillAgent`** | **将路径填入Agent对话框并切换到Agent面板** |
| `delete` | 删除文件/文件夹 |

### 3.8 导航标签页 (L:1561-1607)

```javascript
function switchNavTab(tabName)  // 切换面板
```
- `files` — 文件树与编辑器
- `tasks` — 看板/Kanban
- `bookmarks` — 书签网格
- `projects` — 项目列表 + 源码浏览器
- `courses` — 课程 + 执行面板
- `agent` — AI 对话 Agent
- `slides` — 幻灯片编辑器
- `stats` — 统计面板
- `dashboard` — SaberSystem 仪表盘

### 3.9 模块功能

| 模块 | 行号 | 说明 |
|------|------|------|
| Electron Title Bar | L:350-370 | 无边框窗口的标题栏控制 |
| 路径栏 Breadcrumb | L:2048-2079 | 可点击的路径分段导航 |
| 任务看板 Kanban | L:2116-2397 | 三列看板，支持拖拽移动、日期过滤 |
| 书签 | L:2398-2550 | 网格展示、分类筛选、从剪贴板添加 |
| 项目 & 源码浏览器 | L:2551-3043 | 项目列表 → 源码目录浏览 → Monaco 编辑 |
| 最近文件 | L:3044-3134 | 下拉面板 + 欢迎页展示 |
| 课程 | L:3136-3237+ | 课表排序、进度跟踪、执行面板 |
| 思维导图 | L:1380-1517 | iframe 加载 `/static/mindmap/`，消息通信 |
| 幻灯片 | (约 L:3500+) | 基于 Markdown 的幻灯片编辑器 |
| Jupyter | (约 L:6000+) | 嵌入 iframe，与 Jupyter 内核通信 |
| 仪表盘 | (TBD) | SaberSystem 数据显示 |

---

## 4. WebSocket 通信 (L:256-296)

```javascript
connectWS()  // ws://host/ws?app=web-xxx&id=sess-xxx&type=main
sendWS(cmd, param)  // JSON 消息
handleWSMessage(msg)  // 分发处理（全局函数）
```

- 自动重连（3 秒间隔）
- 用于实时通知、协作更新

---

## 5. Auth 数据流

```
用户打开 / ──→ checkAuth()
  ├── 无需鉴权 ──→ 加载完成
  ├── 需要凭证 ──→ showAuthDialog() → doLogin() → loginAuth API → location.reload()
  └── 工作区模式 ──→ showAuthDialog() → switchWorkspace(code, apiCode)

API 请求 ──→ TS2Client.api()
  ├── 401 ──→ showAuthDialog() 弹框重新登录
  └── 403 ──→ 返回 { code: 403, msg: '无权访问' }
```

无持久化 token 存储。鉴权依赖服务端 session cookie（`loginAuth` 后设置）。

---

## 6. 模块间通信

- 全局 `state` 对象：所有数据
- 全局 `client` (TS2Client 实例)：所有 API
- DOM 事件监听：用户交互
- `handleWSMessage()`：WebSocket 消息分发
- iframe `postMessage()`：与 mindmap/slides 子应用通信

---

## 7. 主题系统

`static/style.css` 定义两套 CSS 变量：
- `html[data-theme="dark"]` — 黑夜模式（默认）
- `html[data-theme="light"]` — 白天模式

切换：`document.documentElement.setAttribute('data-theme', 'light')`

Vditor 和 Monaco 的主题跟随全局切换。
