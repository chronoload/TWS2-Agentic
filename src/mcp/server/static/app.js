// ─── TS2 Client ──────────────────────────────────────────────

let API_BASE = location.origin;
const EXPOSED_DIRS = ['Notes', 'bookmarks', 'data', 'datahub', 'projects'];

// ─── Auth state ──────────────────────────────────────────────
let _pendingSwitchPath = ''; // 登录成功后自动重试的工作区路径

function showAuthDialog() {
  const overlay = document.getElementById('authOverlay');
  if (overlay) overlay.style.display = 'flex';
}

function hideAuthDialog() {
  const overlay = document.getElementById('authOverlay');
  if (overlay) overlay.style.display = 'none';
}

async function doLogin() {
  const code = document.getElementById('authCodeInput')?.value || '';
  const token = document.getElementById('authTokenInput')?.value || '';
  if (_pendingSwitchPath) {
    // 工作区授权模式：独立校验，不依赖 cookie
    await switchWorkspace(_pendingSwitchPath, code);
  } else {
    // 远程登录模式：同时发送 code 和 token
    const res = await fetch(`${API_BASE}/api/system/loginAuth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, token }),
    });
    const data = await res.json();
    if (data.code === 0) {
      hideAuthDialog();
      location.reload();
    } else {
      modalAlert(data.msg || '授权码或 Token 错误，请重试');
    }
  }
}

async function checkAuth() {
  try {
    const res = await fetch(`${API_BASE}/api/system/authInfo`);
    const data = await res.json();
    const d = data.data || {};
    // 只有需要鉴权 且 有可检查的授权码/token 时才弹框
    if (d.needAuth && (d.hasAuthCode || d.hasToken) && !d.workspaceAccess?.some(ws => ws.accessible)) {
      showAuthDialog();
      return false;
    }
    return true;
  } catch (e) {
    return true;
  }
}

class TS2Client {
  constructor() {
    this.ws = null;
    this.appId = 'web-' + Math.random().toString(36).substr(2, 6);
    this.sessionId = 'sess-' + Math.random().toString(36).substr(2, 6);
    this.wsConnected = false;
    this.reconnectTimer = null;
  }

  async api(endpoint, body = {}) {
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.status === 401) {
        // session 过期或无效，弹授权框重新登录
        showAuthDialog();
        return { code: 401, msg: '未授权，请登录' };
      }
      if (res.status === 403) {
        return { code: 403, msg: '无权访问' };
      }
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  async getFile(path) { return await this.api('/api/file/getFile', { path }); }
  async putFile(path, content) { return await this.api('/api/file/putFile', { path, content }); }
  async removeFile(path) { return await this.api('/api/file/removeFile', { path }); }
  async renameFile(oldPath, newPath) { return await this.api('/api/file/renameFile', { old_path: oldPath, new_path: newPath }); }
  async readDir(path = '') { return await this.api('/api/file/readDir', { path }); }
  async search(query, subdir = '') { return await this.api('/api/file/search', { query, subdir }); }

  async downloadBinary(path) {
    try {
      const encodedPath = path.split('/').map(s => encodeURIComponent(s)).join('/');
      const res = await fetch(`${API_BASE}/api/file/download/${encodedPath}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.arrayBuffer();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  async getStats() {
    try {
      const res = await fetch(`${API_BASE}/api/system/stats`);
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  async api_patch(path, body = {}) {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  async api_del(path) {
    try {
      const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  async api_put(path, body = {}) {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  async api_get(path) {
    try {
      const res = await fetch(`${API_BASE}${path}`);
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  async getTasks() { return await this.api('/api/data/tasks', {}); }
  async getBookmarks() { return await this.api('/api/data/bookmarks', {}); }
  async addBookmark(data) { return await this.api('/api/data/bookmarks/add', data); }
  async getProjects() { return await this.api('/api/data/projects', {}); }
  async updateTask(taskId, updates) { return await this.api('/api/data/tasks/update', { id: taskId, ...updates }); }
  async createTask(task) { return await this.api('/api/data/tasks/create', task); }
  async deleteTask(taskId) { return await this.api('/api/data/tasks/delete', { id: taskId }); }
  async syncFull(tasks, bookmarks, projects) { return await this.api('/api/sync/full', { tasks, bookmarks, projects }); }

  async getCourses() { return await this.api('/api/data/courses', {}); }
  async getCourseProgress(courseId) { return await this.api('/api/data/courses/progress', { course_id: courseId }); }
  async updateLessonStatus(courseId, lessonNumber, status) {
    return await this.api('/api/data/courses/lessonStatus', { course_id: courseId, lesson_number: lessonNumber, status });
  }

  async agentChat(message, history = [], sessionId, attachments) {
    const payload = { message, history, context: { source: 'web' }, session_id: sessionId || '' };
    if (attachments) payload.attachments = attachments;
    return await this.api('/api/agent/chat', payload);
  }

  async getAgentSessions() {
    try {
      const res = await fetch(`${API_BASE}/api/agent/sessions`);
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }
  async createAgentSession() {
    return this.api('/api/agent/sessions/create');
  }
  async switchAgentSession(sessionId) {
    return this.api('/api/agent/sessions/switch', { session_id: sessionId });
  }
  async deleteAgentSession(sessionId) {
    return this.api('/api/agent/sessions/delete', { session_id: sessionId });
  }

  async getAgentCheckpoints(sessionId) {
    try {
      const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
      const res = await fetch(`${API_BASE}/api/agent/checkpoints${params}`);
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }
  async getAgentCheckpointDiff(commitHash) {
    try {
      const res = await fetch(`${API_BASE}/api/agent/checkpoints/${commitHash}/diff`);
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }
  async restoreAgentCheckpoint(commitHash, restoreType) {
    return this.api('/api/agent/checkpoints/' + commitHash + '/restore', { restore_type: restoreType });
  }

  async uploadFiles(files, targetPath = '') {
    const formData = new FormData();
    for (const file of files) {
      formData.append('files', file);
    }
    formData.append('path', targetPath);
    try {
      const res = await fetch(`${API_BASE}/api/file/upload`, {
        method: 'POST',
        body: formData,
      });
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  getDownloadUrl(path) { return `${API_BASE}/api/file/download/${path.split('/').map(s => encodeURIComponent(s)).join('/')}`; }

  async getPushDashboard() {
    try {
      const res = await fetch(`${API_BASE}/api/push/dashboard`);
      return await res.json();
    } catch (e) {
      return { code: -1, msg: e.message };
    }
  }

  downloadFile(path) {
    const a = document.createElement('a');
    a.href = this.getDownloadUrl(path);
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  connectWS() {
    var base = API_BASE.replace(/^http/, 'ws');
    var url = base + '/ws?app=' + this.appId + '&id=' + this.sessionId + '&type=main';

    try {
      this.ws = new WebSocket(url);
    } catch (e) {
      console.error('WS connect error:', e);
      this.reconnectTimer = setTimeout(() => this.connectWS(), 5000);
      return;
    }

    this.ws.onopen = () => {
      this.wsConnected = true;
      updateWsStatus(true);
    };

    this.ws.onclose = () => {
      this.wsConnected = false;
      updateWsStatus(false);
      this.reconnectTimer = setTimeout(() => this.connectWS(), 3000);
    };

    this.ws.onerror = () => {
      this.wsConnected = false;
      updateWsStatus(false);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleWSMessage(msg);
      } catch (e) {}
    };
  }

  sendWS(cmd, param = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ cmd, reqId: Date.now(), param }));
    }
  }

  // ─── SaberSystem Dashboard API（对接 /api/saber/* 端点）───
  // Ideal
  async saberListIdeals() { return await this.api_get('/api/saber/ideals'); }
  async saberCreateIdeal(title, description = '') { return await this.api('/api/saber/ideals', { title, description }); }
  async saberGetIdeal(id) { return await this.api_get(`/api/saber/ideals/${id}`); }
  async saberUpdateIdeal(id, data) { return await this.api_patch(`/api/saber/ideals/${id}`, data); }
  async saberDeleteIdeal(id) { return await this.api_del(`/api/saber/ideals/${id}`); }

  // Goal
  async saberListGoals(idealId) { return await this.api_get(`/api/saber/goals?ideal_id=${encodeURIComponent(idealId)}`); }
  async saberCreateGoal(data) { return await this.api('/api/saber/goals', data); }
  async saberGetGoal(id) { return await this.api_get(`/api/saber/goals/${id}`); }
  async saberUpdateGoal(id, data) { return await this.api_patch(`/api/saber/goals/${id}`, data); }
  async saberDeleteGoal(id) { return await this.api_del(`/api/saber/goals/${id}`); }

  // Goal → Plan generation
  async saberGeneratePlans(goalId) { return await this.api(`/api/saber/goals/${goalId}/generate-plans`, {}); }

  // Plan
  async saberListPlans(goalId) { return await this.api_get(`/api/saber/plans?goal_id=${encodeURIComponent(goalId)}`); }
  async saberCreatePlan(data) { return await this.api('/api/saber/plans', data); }
  async saberGetPlan(planId) { return await this.api_get(`/api/saber/plans/${planId}`); }
  async saberUpdatePlan(planId, data) { return await this.api_put(`/api/saber/plans/${planId}`, data); }
  async saberDeletePlan(id) { return await this.api_del(`/api/saber/plans/${id}`); }
  async saberListTasks(planId) { return await this.api_get(`/api/saber/plans/${planId}/tasks`); }
  async saberAddTask(planId, data) { return await this.api(`/api/saber/plans/${planId}/steps`, data); }
  async saberGetTask(id) { return await this.api_get(`/api/saber/tasks/${id}`); }
  async saberUpdateTask(taskId, data) { return await this.api_patch(`/api/saber/tasks/${taskId}`, data); }
  async saberDeleteTask(id) { return await this.api_del(`/api/saber/tasks/${id}`); }

  // Optimizer
  async saberCheckImbalance() { return await this.api_get('/api/saber/optimizer/imbalance'); }

  // Life
  async saberGetLife(userId = 'default') { return await this.api_get(`/api/saber/life?user_id=${userId}`); }
  async saberGetAttention(userId = 'default') { return await this.api_get(`/api/saber/life/attention?user_id=${userId}`); }
  async saberRecoverAttention(userId, hours, quality) {
    return await this.api('/api/saber/life/attention/recover', { user_id: userId, hours, quality });
  }

  // Agent 决策
  async saberGenerateDecision(planId) {
    return await this.api(`/api/saber/plans/${planId}/decisions`, {});
  }
  async saberSelectDecision(dpId, optionId, wasAdopted, modificationRatio) {
    return await this.api(`/api/saber/decisions/${dpId}/select`, {
      option_id: optionId, was_adopted: wasAdopted, user_modification_ratio: modificationRatio,
    });
  }
  async saberLogAgent(data) { return await this.api('/api/saber/agent/log', data); }
  async saberGetIntensity(planId) { return await this.api_get(`/api/saber/agent/intensity?plan_id=${planId}`); }
  async saberCreateTask(planId, data) { return await this.api(`/api/saber/plans/${planId}/tasks`, data); }
  async saberDeliverTask(taskId, artifacts, notes) {
    let url = `/api/saber/tasks/${taskId}/deliver?notes=${encodeURIComponent(notes || '')}`;
    if (artifacts && artifacts.length) {
      artifacts.forEach(a => { url += `&artifacts=${encodeURIComponent(a)}`; });
    }
    return await this.api(url, null, 'POST');
  }
  async saberStartGitTracking(taskId) { return await this.api(`/api/saber/tasks/${taskId}/git-start`, null, 'POST'); }
  async saberCaptureGitDiff(taskId) { return await this.api(`/api/saber/tasks/${taskId}/git-capture`, null, 'POST'); }
  async saberAgentChat(planId, message) { return await this.api('/api/saber/agent/chat', { plan_id: planId, message }); }
}

// ─── Electron Frameless Title Bar ─────────────────────────────

(function initTitleBar() {
  var api = null;
  try { api = window.electronAPI; } catch(e) {}
  if (!api || !api.win) return;
  var tb = document.getElementById('titlebar');
  if (!tb) return;
  tb.style.display = 'flex';
  document.body.classList.add('titlebar-visible');
  document.getElementById('tbMinimize')?.addEventListener('click', function() { api.win.minimize(); });
  var maxBtn = document.getElementById('tbMaximize');
  if (maxBtn) {
    maxBtn.addEventListener('click', function() {
      api.win.isMaximized().then(function(m) {
        if (m) { api.win.unmaximize(); maxBtn.textContent = '□'; }
        else { api.win.maximize(); maxBtn.textContent = '❐'; }
      });
    });
    api.win.isMaximized().then(function(m) { if (m) maxBtn.textContent = '❐'; });
  }
  document.getElementById('tbClose')?.addEventListener('click', function() { api.win.close(); });
})();

// ─── State ──────────────────────────────────────────────────

const client = new TS2Client();
const state = {
  currentDir: '',
  currentWorkspaceRoot: '',
  openTabs: [],
  recentFiles: JSON.parse(localStorage.getItem('ts2_recent_files') || '[]'),
  activeTab: null,
  fileContents: {},
  originalContents: {},
  expandedDirs: new Set(),
  contextTarget: null,
  activeNavTab: 'files',
  tasks: [],
  bookmarks: [],
  bookmarkCategories: [],
  bookmarkFilter: '',
  projects: [],
  courses: [],
  courseSearchQuery: '',
  courseProgress: {},
  courseDueReviews: {},
  courseResources: {},
  expandedCourse: null,
  vditorReady: false,
  vditor: null,
  dirCache: {},
  editorMode: 'vditor', // 'vditor' or 'plain'
  viewingPdf: false,
  pdfDoc: null,
  pdfPageNum: 1,
  pdfPageCount: 0,
  pdfZoom: 1.0,
  pdfPath: null,
  pdfViewState: {},
  pdfDualPage: false,
  pdfCache: {},
  // Execution state
  execCourseId: null,
  execLessonIdx: null,
  timerInterval: null,
  timerSeconds: 0,
  timerRunning: false,
  timerPaused: false,
  // Agent state
  agentMessages: [],
  agentStreaming: false,
  agentXHR: null,  // 当前流式请求的 XHR 引用
  streamingToolCalls: [],  // 流式工具调用（内联显示在 assistant 消息中）
  _checkpointVersion: 0,  // Crush VersionedMap: 检查点版本号
  // 多模态附件
  mediaAttachments: [],  // [{id, kind, dataUrl, mime, filename, placeholder}]
  // 源码浏览器
  srcCurrentPath: '',
  srcSelectedFile: '',
  agentHistory: [],
  pushDashboard: null,
  pushVisible: true,
  timetables: null,
  // SaberSystem Dashboard state（Pilot 仪表盘）
  dashboard: {
    life: null,           // LifeResource
    attention: null,      // AttentionCapital
    ideals: [],           // Ideal 列表（含 _goals/_plans 子结构）
    selectedPlanId: null, // 当前选中的 Plan
    intensity: null,      // { proficiency, intensity, retired }
    currentDecision: null,// 当前 DecisionPoint
    selectedPlan: null,   // 当前 Plan 对象
    tasks: [],            // 当前 Plan 的任务
    constraints: [],      // 当前 Plan 的约束
    copilotLogs: [],      // 副驾驶日志 [{tag, content, time}]
    copilotCollapsed: true,
    topology: null,       // 拓扑数据 {tree, topological_order, critical_path, has_cycle}
    violations: null,     // 违规数据 {violations, compliance_status}
    expandedPlans: {},    // 子 Plan 展开状态 {planId: true/false}
  },
};

// ─── Editor Service (解耦编辑器与面包屑/文件树) ──────────

const editorService = {
  async open(path) {
    // 如果活动 pane 是分屏编辑器，在该 pane 中打开
    if (_splitActive && _activePaneId !== '0' && _activePaneId !== _agentPaneId) {
      await this.openInPane(path, _activePaneId);
      return;
    }

    const ext = path.includes('.') ? ('.' + path.split('.').pop().toLowerCase()) : '';
    if (ext === '.pdf') {
      if (state.openTabs.find(t => t.path === path)) {
        this.switchTo(path);
        return;
      }
      var pdfName = path.split('/').pop();
      state.openTabs.push({ path, name: pdfName, modified: false, _isPdf: true });
      addTab(path, pdfName);
      var ok = await _loadAndRenderPdf(path);
      if (ok) {
        this.switchTo(path);
        this._addRecent(path, pdfName);
        showToast(`已打开: ${pdfName}`, 'info');
      } else {
        closeTab(path);
      }
      return;
    }
    if (ext === '.docx' || ext === '.xlsx' || ext === '.pptx') {
      await openOfficeAsPdf(path);
      return;
    }
    if (ext === '.kmind') {
      if (state.openTabs.find(t => t.path === path)) {
        this.switchTo(path);
        return;
      }
      var oldKmindTab = state.openTabs.find(t => t._isKmind);
      if (oldKmindTab) closeTab(oldKmindTab.path);
      var kmindRes = await client.getFile(path);
      if (kmindRes.code !== 0 || !kmindRes.data) {
        var kmindSrcRes = await client.api('/api/data/projects/readFile', { path });
        if (kmindSrcRes.code !== 0 || !kmindSrcRes.data) { showToast('打开失败', 'error'); return; }
        kmindRes = kmindSrcRes;
      }
      var kmindContent = kmindRes.data.content;
      var kmindFileName = path.split('/').pop();
      state.fileContents[path] = kmindContent;
      state.openTabs.push({ path: path, name: kmindFileName, modified: false, _isKmind: true });
      addTab(path, kmindFileName);
      this.switchTo(path);
      this._addRecent(path, kmindFileName);
      // After switch, load data into iframe
      setTimeout(function() { kmindLoadData(path, kmindContent); }, 300);
      return;
    }
    if (ext === '.html' || ext === '.htm') {
      const encodedPath = path.split('/').map(s => encodeURIComponent(s)).join('/');
      window.open(API_BASE + '/api/file/download/' + encodedPath + '?preview=true', '_blank');
      return;
    }
    // 代码/脚本文件 → Monaco Editor（每个文件独立标签页）
    var _codeExts = ['.py','.js','.ts','.jsx','.tsx','.r','.cpp','.c','.h','.java','.go','.rs','.rb','.php','.swift','.kt','.scala','.sh','.bash','.zsh','.ps1','.bat','.sql','.css','.scss','.less','.vue','.svelte','.yaml','.yml','.toml','.json','.xml','.tex','.gradle','.sbt','.pl','.pm','.lua','.hs','.clj','.ex','.erl'];
    if (_codeExts.includes(ext)) {
      var monoRes = await client.getFile(path);
      if (monoRes.code !== 0 || !monoRes.data) { showToast('打开失败', 'error'); return; }
      // 保存当前 Monaco 内容
      if (_monacoCurrentFile && _monacoEditor) {
        _monacoFiles[_monacoCurrentFile] = _monacoEditor.getValue();
      }
      _monacoCurrentFile = path;
      _monacoFiles[path] = monoRes.data.content;
      _monacoSrcFile = null;
      var monoName = path.split('/').pop();
      var existingTab = state.openTabs.find(function(t) { return t.path === path; });
      if (existingTab) {
        existingTab.modified = false;
        this.switchTo(path);
      } else {
        state.openTabs.push({ path: path, name: monoName, modified: false, _isMonaco: true });
        addTab(path, monoName);
        this.switchTo(path);
        this._addRecent(path, monoName);
      }
      // 初始化/加载 Monaco
      if (!_monacoEditor) {
        document.getElementById('monacoEditorWrap').innerHTML = '';
        _initMonaco(document.getElementById('monacoEditorWrap'), monoRes.data.content, path);
      } else {
        _loadMonacoFile(path);
      }
      showToast('已打开: ' + monoName, 'info');
      return;
    }
    if (state.openTabs.find(t => t.path === path)) {
      this.switchTo(path);
      return;
    }
    // 先尝试 FileSyncEngine（EXPOSED_DIRS 内的文件），失败则 fallback 到项目源码 API
    let content = null, entry = null;
    const res = await client.getFile(path);
    if (res.code === 0 && res.data) {
      content = res.data.content;
      entry = res.data.entry;
    } else {
      // fallback: 尝试项目源码 API（不受 EXPOSED_DIRS 限制）
      const srcRes = await client.api('/api/data/projects/readFile', { path });
      if (srcRes.code === 0 && srcRes.data) {
        content = srcRes.data.content;
        entry = { name: srcRes.data.name || path.split('/').pop(), path, is_dir: false, ext: srcRes.data.ext || '' };
      }
    }
    if (content === null) {
      showToast('打开失败: 文件未找到', 'error');
      return;
    }
    state.fileContents[path] = content;
    state.originalContents[path] = content;
    const name = entry ? (entry.name || path.split('/').pop()) : path.split('/').pop();
    state.openTabs.push({ path, name, modified: false });
    addTab(path, name);
    this.switchTo(path);
    this._addRecent(path, name);
    showToast(`已打开: ${name}`, 'info');
  },

  openWithContent(path, content) {
    if (state.openTabs.find(t => t.path === path)) {
      this.switchTo(path);
      return;
    }
    const name = path.split('/').pop();
    state.fileContents[path] = content;
    state.originalContents[path] = content;
    state.openTabs.push({ path, name, modified: false });
    addTab(path, name);
    this.switchTo(path);
    this._addRecent(path, name);
    showToast(`已打开: ${name}`, 'info');
  },

  switchTo(path) {
    // 保存前一个浏览器页签的状态
    var prevTab = state.openTabs.find(function(t) { return t.path === state.activeTab; });
    if (prevTab && prevTab._isBrowser) {
      var f = document.getElementById('browserFrame');
      var inp = document.getElementById('browserUrlInput');
      if (f && inp) {
        prevTab._browserUrl = f.getAttribute('data-url') || inp.value || 'about:blank';
      }
    }
    // 切走 Monaco 时保存当前内容（在更新 activeTab 之前）
    if (_monacoCurrentFile && _monacoEditor) {
      var prevTab = state.openTabs.find(function(t) { return t.path === state.activeTab; });
      if (prevTab && prevTab._isMonaco) _monacoFiles[_monacoCurrentFile] = _monacoEditor.getValue();
    }
    state.activeTab = path;
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.path === path));
    document.querySelectorAll('.tree-item').forEach(t => t.classList.toggle('active', t.dataset.path === path));
    updatePathBar(path);
    document.getElementById('statusPath').textContent = path;
    updateKnitButtonVisibility(path);
    var tab = state.openTabs.find(t => t.path === path);
    var ext = path.includes('.') ? ('.' + path.split('.').pop().toLowerCase()) : '';
    if (ext === '.pdf') {
      document.getElementById('slidesEditorView').style.display = 'none';
      document.getElementById('welcomeScreen').style.display = 'none';
      document.getElementById('vditor').style.display = 'none';
      document.getElementById('plainEditor').style.display = 'none';
      document.getElementById('pdfViewer').style.display = 'flex';
      document.getElementById('kmindEditorView').style.display = 'none';
      document.getElementById('jupyterEditorView').style.display = 'none';
      document.getElementById('monacoEditorView').style.display = 'none';
      document.getElementById('browserView').style.display = 'none';
      if (state.pdfPath !== path) _loadAndRenderPdf(path);
      return;
    }
    if (tab && tab._isSlides) {
      document.getElementById('pdfViewer').style.display = 'none';
      document.getElementById('welcomeScreen').style.display = 'none';
      document.getElementById('vditor').style.display = 'none';
      document.getElementById('plainEditor').style.display = 'none';
      document.getElementById('slidesEditorView').style.display = 'flex';
      document.getElementById('kmindEditorView').style.display = 'none';
      document.getElementById('jupyterEditorView').style.display = 'none';
      document.getElementById('monacoEditorView').style.display = 'none';
      document.getElementById('browserView').style.display = 'none';
      // 将 slides 编辑器移回主容器（如果在分屏中的话）
      _moveSlidesEditorToMain();
      // 切换笔记数据（多标签页缓存）
      _slidesSwitchToNotebook(path);
      return;
    }
    if (tab && tab._isKmind) {
      document.getElementById('pdfViewer').style.display = 'none';
      document.getElementById('welcomeScreen').style.display = 'none';
      document.getElementById('vditor').style.display = 'none';
      document.getElementById('plainEditor').style.display = 'none';
      document.getElementById('slidesEditorView').style.display = 'none';
      document.getElementById('kmindEditorView').style.display = 'flex';
      document.getElementById('jupyterEditorView').style.display = 'none';
      document.getElementById('monacoEditorView').style.display = 'none';
      document.getElementById('browserView').style.display = 'none';
      return;
    }
    if (tab && tab._isJupyter) {
      document.getElementById('pdfViewer').style.display = 'none';
      document.getElementById('welcomeScreen').style.display = 'none';
      document.getElementById('vditor').style.display = 'none';
      document.getElementById('plainEditor').style.display = 'none';
      document.getElementById('slidesEditorView').style.display = 'none';
      document.getElementById('kmindEditorView').style.display = 'none';
      document.getElementById('jupyterEditorView').style.display = 'flex';
      document.getElementById('monacoEditorView').style.display = 'none';
      document.getElementById('browserView').style.display = 'none';
      return;
    }
    if (tab && tab._isMonaco) {
      document.getElementById('pdfViewer').style.display = 'none';
      document.getElementById('welcomeScreen').style.display = 'none';
      document.getElementById('vditor').style.display = 'none';
      document.getElementById('plainEditor').style.display = 'none';
      document.getElementById('slidesEditorView').style.display = 'none';
      document.getElementById('kmindEditorView').style.display = 'none';
      document.getElementById('jupyterEditorView').style.display = 'none';
      document.getElementById('monacoEditorView').style.display = 'flex';
      document.getElementById('browserView').style.display = 'none';
      if (_monacoEditor) {
        var uri = _monacoApi.Uri.file(path);
        var cur = _monacoEditor.getModel();
        if (!cur || cur.uri.toString() !== uri.toString()) _loadMonacoFile(path);
        setTimeout(function() { _monacoEditor.layout(); }, 50);
      }
      return;
    }
    if (tab && tab._isBrowser) {
      document.getElementById('pdfViewer').style.display = 'none';
      document.getElementById('welcomeScreen').style.display = 'none';
      document.getElementById('vditor').style.display = 'none';
      document.getElementById('plainEditor').style.display = 'none';
      document.getElementById('slidesEditorView').style.display = 'none';
      document.getElementById('kmindEditorView').style.display = 'none';
      document.getElementById('jupyterEditorView').style.display = 'none';
      document.getElementById('monacoEditorView').style.display = 'none';
      document.getElementById('browserView').style.display = 'flex';
      // 恢复当前浏览器页签的状态
      _restoreBrowserFrame(tab);
      return;
    }
    showEditor();
    setEditorContent(state.fileContents[path] || '');
  },

  _addRecent(path, name) {
    state.recentFiles = state.recentFiles.filter(f => f.path !== path);
    state.recentFiles.unshift({ path, name, time: Date.now() });
    if (state.recentFiles.length > 20) state.recentFiles.length = 20;
    try { localStorage.setItem('ts2_recent_files', JSON.stringify(state.recentFiles)); } catch(e) {}
    _saveSession();
  },

  /* 在分屏 pane 中打开文件 */
  async openInPane(path, paneId) {
    var ext = path.includes('.') ? ('.' + path.split('.').pop().toLowerCase()) : '';

    // 浏览器标签页
    if (path.startsWith('__browser__')) {
      var srcTab = state.openTabs.find(function(t) { return t.path === path; });
      var tabs = state['paneTabs_' + paneId] || [];
      if (tabs.find(t => t.path === path)) { this.switchInPane(path, paneId); return; }
      tabs.push({ path: path, name: srcTab ? srcTab.name : '浏览器', modified: false, _isBrowser: true, _browserUrl: srcTab ? srcTab._browserUrl || '' : '' });
      state['paneTabs_' + paneId] = tabs;
      var tabsEl = document.getElementById('editorTabs-' + paneId);
      if (tabsEl) { tabsEl.appendChild(_createPaneTabEl(path, srcTab ? srcTab.name : '浏览器', paneId, false)); }
      this.switchInPane(path, paneId);
      return;
    }

    // PDF 在分屏 pane 中用轻量查看器
    if (ext === '.pdf') {
      var tabs = state['paneTabs_' + paneId] || [];
      if (tabs.find(t => t.path === path)) { this.switchInPane(path, paneId); return; }
      var name = path.split('/').pop();
      tabs.push({ path, name, modified: false, _isPdf: true });
      state['paneTabs_' + paneId] = tabs;
      state['paneFileContents_' + paneId][path] = '';
      // 添加 tab
      var tabsEl = document.getElementById('editorTabs-' + paneId);
      if (tabsEl) {
        var tabBtn = _createPaneTabEl(path, name, paneId, true);
        tabsEl.appendChild(tabBtn);
      }
      this.switchInPane(path, paneId);
      // 加载 PDF 到分屏 canvas
      await loadPdfInPane(path, paneId);
      this._addRecent(path, name);
      return;
    }

    // HTML 文件在浏览器中打开
    if (ext === '.html' || ext === '.htm') {
      const encodedPath = path.split('/').map(s => encodeURIComponent(s)).join('/');
      window.open(API_BASE + '/api/file/download/' + encodedPath + '?preview=true', '_blank');
      return;
    }

    var tabs = state['paneTabs_' + paneId] || [];
    if (tabs.find(t => t.path === path)) {
      this.switchInPane(path, paneId);
      return;
    }
    let content = null;
    const res = await client.getFile(path);
    if (res.code === 0 && res.data) {
      content = res.data.content;
    } else {
      const srcRes = await client.api('/api/data/projects/readFile', { path });
      if (srcRes.code === 0 && srcRes.data) content = srcRes.data.content;
    }
    if (content === null) { showToast('打开失败: 文件未找到', 'error'); return; }

    var name = path.split('/').pop();
    state['paneFileContents_' + paneId][path] = content;
    state['paneOriginalContents_' + paneId] = state['paneOriginalContents_' + paneId] || {};
    state['paneOriginalContents_' + paneId][path] = content;
    var isCode = _isCodeFile(path);
    tabs.push({ path, name, modified: false, _isMonaco: isCode });
    state['paneTabs_' + paneId] = tabs;

    // 添加 tab 按钮
    var tabsEl = document.getElementById('editorTabs-' + paneId);
    if (tabsEl) {
      var tabBtn = _createPaneTabEl(path, name, paneId, false);
      tabsEl.appendChild(tabBtn);
    }

    this.switchInPane(path, paneId);
    this._addRecent(path, name);
    showToast('已打开: ' + name, 'info');
  },

  switchInPane(path, paneId) {
    // 保存前一个 pane 标签页的状态
    var prevPath = state['paneActiveTab_' + paneId];
    if (prevPath) {
      var prevTab = (state['paneTabs_' + paneId] || []).find(function(t) { return t.path === prevPath; });
      if (prevTab && prevTab._isBrowser) {
        var f = document.getElementById('paneBrowserFrame-' + paneId);
        var inp = document.getElementById('paneBrowserUrl-' + paneId);
        if (f && inp) {
          var val = inp.value.trim();
          if (val && !val.startsWith('http://') && !val.startsWith('https://')) val = 'https://' + val;
          prevTab._browserUrl = val;
        }
      } else if (prevTab && prevTab._isMonaco && state['paneMonaco_' + paneId]) {
        state['paneFileContents_' + paneId][prevPath] = state['paneMonaco_' + paneId].getValue();
      } else if (prevTab) {
        var prevVditor = state['paneVditor_' + paneId];
        if (prevVditor && state['paneVditorReady_' + paneId] && !prevTab._isPdf && !prevTab._isSlides) {
          state['paneFileContents_' + paneId][prevPath] = prevVditor.getValue();
        }
      }
    }

    state['paneActiveTab_' + paneId] = path;
    // 更新 tab 高亮
    var tabsEl = document.getElementById('editorTabs-' + paneId);
    if (tabsEl) {
      tabsEl.querySelectorAll('.tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.path === path);
      });
    }
    // 更新标题
    var titleEl = document.getElementById('paneTitle-' + paneId);
    if (titleEl) {
      var tab = (state['paneTabs_' + paneId] || []).find(function(t) { return t.path === path; });
      titleEl.textContent = (tab && tab._isBrowser ? '🌐 ' : '📄 ') + path.split('/').pop();
    }
    // 隐藏空提示
    var wrapper = document.getElementById('editorWrapper-' + paneId);
    if (wrapper) {
      var hintEl = wrapper.querySelector('.pane-empty-hint');
      if (hintEl) hintEl.style.display = 'none';
    }
    if (!wrapper) return;

    var tab = (state['paneTabs_' + paneId] || []).find(function(t) { return t.path === path; });

    if (tab && tab._isBrowser) {
      var vditorEl = document.getElementById('paneVditor-' + paneId);
      if (vditorEl) vditorEl.style.display = 'none';
      var pdfContainer = document.getElementById('panePdfContainer-' + paneId);
      if (pdfContainer) pdfContainer.style.display = 'none';
      var browserContainer = document.getElementById('paneBrowserContainer-' + paneId);
      if (browserContainer) {
        browserContainer.style.display = 'flex';
        var frame = document.getElementById('paneBrowserFrame-' + paneId);
        var inp = document.getElementById('paneBrowserUrl-' + paneId);
        if (frame && inp) {
          if (tab._browserUrl && tab._browserUrl !== frame.src) {
            frame.removeAttribute('srcdoc');
            _setFrameSandbox(frame, true);
            frame.src = '/api/browser/proxy?url=' + encodeURIComponent(tab._browserUrl);
            inp.value = tab._browserUrl;
          } else if (!tab._browserUrl) {
            inp.value = '';
            frame.removeAttribute('src');
            _setFrameSandbox(frame, false);
            _renderStartPageInPane(paneId);
          }
        }
      }
      var titleEl = document.getElementById('paneTitle-' + paneId);
      if (titleEl) titleEl.textContent = '🌐 ' + (tab.name || '浏览器');
    } else if (tab && tab._isPdf) {
      // 显示 PDF canvas
      var vditorEl = document.getElementById('paneVditor-' + paneId);
      if (vditorEl) vditorEl.style.display = 'none';
      var pdfContainer = document.getElementById('panePdfContainer-' + paneId);
      if (pdfContainer) pdfContainer.style.display = 'flex';
    } else if (tab && tab._isSlides) {
      // 隐藏 pane 默认编辑器，显示 slides 编辑器 UI
      var vditorEl = document.getElementById('paneVditor-' + paneId);
      if (vditorEl) vditorEl.style.display = 'none';
      var pdfContainer = document.getElementById('panePdfContainer-' + paneId);
      if (pdfContainer) pdfContainer.style.display = 'none';
      // 移入 slides 编辑器 DOM（含导航、大纲、Vditor 等全套 UI）
      _moveSlidesEditorToPane(paneId);
      // 切换笔记数据
      _slidesSwitchToNotebook(path);
    } else if (tab && tab._isMonaco) {
      var vditorEl = document.getElementById('paneVditor-' + paneId);
      if (vditorEl) vditorEl.style.display = 'none';
      var monacoEl = document.getElementById('paneMonaco-' + paneId);
      if (monacoEl) monacoEl.style.display = '';
      var pdfContainer = document.getElementById('panePdfContainer-' + paneId);
      if (pdfContainer) pdfContainer.style.display = 'none';
      var content = state['paneFileContents_' + paneId][path] || '';
      _ensurePaneMonaco(paneId, content, path);
    } else {
      var vditorEl = document.getElementById('paneVditor-' + paneId);
      if (vditorEl) vditorEl.style.display = '';
      var monacoEl = document.getElementById('paneMonaco-' + paneId);
      if (monacoEl) monacoEl.style.display = 'none';
      var pdfContainer = document.getElementById('panePdfContainer-' + paneId);
      if (pdfContainer) pdfContainer.style.display = 'none';
      // 设置 Vditor 内容
      var vditorInstance = state['paneVditor_' + paneId];
      var content = state['paneFileContents_' + paneId][path] || '';
      if (vditorInstance && state['paneVditorReady_' + paneId]) {
        vditorInstance.setValue(content);
      }
    }
    _saveSession();
  }
};

// ─── 会话持久化（刷新恢复） ───────────────────────────────

function _saveSession() {
  try {
    var panes = {};
    Object.keys(state).forEach(function(key) {
      if (key.startsWith('paneTabs_') && key !== 'paneTabs_0') {
        var pid = key.substring(9);
        var arr = state[key];
        if (Array.isArray(arr) && arr.length) {
          var normalTabs = arr.filter(function(t) { return !t._isSlides && !t._isBrowser; });
          if (normalTabs.length) {
            panes[pid] = {
              tabs: normalTabs.map(function(tab) {
                var obj = { path: tab.path, name: tab.name };
                if (tab._isPdf) {
                  var pp = state['panePdfPage_' + pid];
                  if (pp) {
                    obj.pdfState = {
                      pageNum: pp,
                      zoom: state['panePdfZoom_' + pid] || 1.0,
                      dualPage: state['panePdfDualPage_' + pid] || false
                    };
                  }
                }
                return obj;
              }),
              activeTab: state['paneActiveTab_' + pid] || null
            };
          }
        }
      }
    });
    localStorage.setItem('ts2_session', JSON.stringify({
      openTabs: state.openTabs.filter(function(t) { return !t._isSlides; }).map(function(t) {
        var obj = { path: t.path, name: t.name };
        if (t._isPdf && state.pdfViewState[t.path]) {
          obj.pdfState = state.pdfViewState[t.path];
        }
        return obj;
      }),
      activeTab: state.activeTab,
      panes: panes
    }));
  } catch(e) { console.warn('_saveSession error:', e); }
}

function _checkSessionRestore() {
  var saved;
  try { saved = JSON.parse(localStorage.getItem('ts2_session')); } catch(e) {}
  if (!saved) return;
  var hasTabs = saved.openTabs && saved.openTabs.length > 0;
  var hasPanes = saved.panes && Object.keys(saved.panes).length > 0;
  if (!hasTabs && !hasPanes) return;
  var fileItems = [];
  // 主编辑器标签页
  saved.openTabs.forEach(function(t) {
    var ext = t.path.includes('.') ? t.path.split('.').pop().toLowerCase() : '';
    var icon = ['pdf'].includes(ext) ? '📄' : ['py','js','ts','jsx','tsx','go','rs','java','cpp','c','h','rb','php','swift','kt','r','sh','bash','css','scss','less','vue','svelte','json','xml','yaml','yml','toml','sql','tex','md'].includes(ext) ? '📝' : '📄';
    fileItems.push('<div style="padding:3px 0;font-size:13px">📌 ' + icon + ' ' + escapeHtml(t.name) + '</div>');
  });
  // 分屏 pane 标签页
  if (hasPanes) {
    Object.keys(saved.panes).forEach(function(pid) {
      var p = saved.panes[pid];
      if (p && p.tabs) {
        p.tabs.forEach(function(t) {
          var ext = t.path.includes('.') ? t.path.split('.').pop().toLowerCase() : '';
          var icon = ['pdf'].includes(ext) ? '📄' : ['py','js','ts','jsx','tsx','go','rs','java','cpp','c','h','rb','php','swift','kt','r','sh','bash','css','scss','less','vue','svelte','json','xml','yaml','yml','toml','sql','tex','md'].includes(ext) ? '📝' : '📄';
          fileItems.push('<div style="padding:3px 0;font-size:13px;color:var(--fg-muted)">⬜ ' + icon + ' ' + escapeHtml(t.name) + '</div>');
        });
      }
    });
  }
  if (!fileItems.length) return;
  showHtmlModal('♻️ 恢复上次会话', '<div style="padding:12px"><p style="margin:0 0 12px;font-size:13px;color:var(--fg-muted)">检测到上次退出时打开的标签页：</p><div style="max-height:300px;overflow-y:auto;background:var(--bg);border-radius:6px;padding:8px 12px;border:1px solid var(--border);margin-bottom:12px">' + fileItems.join('') + '</div><div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn-action" onclick="restoreSession()" style="padding:8px 20px">恢复</button><button class="btn" onclick="closeHtmlModal();clearSavedSession()" style="padding:8px 20px">忽略</button></div></div>', '480px');
}

function restoreSession() {
  closeHtmlModal();
  var saved;
  try { saved = JSON.parse(localStorage.getItem('ts2_session')); } catch(e) {}
  if (!saved || !saved.openTabs) return;
  localStorage.removeItem('ts2_session');
  var tabs = saved.openTabs;
  var paneData = saved.panes || {};
  var paneKeys = Object.keys(paneData);
  var idx = 0;
  function openNext() {
    if (idx >= tabs.length) {
      if (saved.activeTab && state.openTabs.find(function(t) { return t.path === saved.activeTab; })) {
        switchToTab(saved.activeTab);
      }
      if (!paneKeys.length) return;
      // 恢复分屏 pane
      for (var pi = 0; pi < paneKeys.length; pi++) {
        splitPane('editor', 'h');
      }
      setTimeout(function() {
        var paneEls = document.querySelectorAll('#splitContainer > .pane[data-pane-id]:not([data-pane-id="0"])');
        paneEls.forEach(function(el, i) {
          if (i >= paneKeys.length) return;
          var newPid = el.getAttribute('data-pane-id');
          var data = paneData[paneKeys[i]];
          if (!data || !data.tabs || !data.tabs.length) return;
          var pIdx = 0;
          function openPaneTab() {
            if (pIdx >= data.tabs.length) {
              if (data.activeTab) {
                setActivePane(newPid);
                setTimeout(function() { editorService.switchInPane(data.activeTab, newPid); }, 100);
              }
              return;
            }
            var tabData = data.tabs[pIdx++];
            if (tabData.pdfState) {
              state['panePdfPage_' + newPid] = tabData.pdfState.pageNum;
              state['panePdfZoom_' + newPid] = tabData.pdfState.zoom;
              state['panePdfDualPage_' + newPid] = tabData.pdfState.dualPage;
            }
            editorService.openInPane(tabData.path, newPid).then(openPaneTab);
          }
          openPaneTab();
        });
      }, 200);
      return;
    }
    var tabData = tabs[idx++];
    if (tabData.pdfState) {
      state.pdfViewState[tabData.path] = tabData.pdfState;
    }
    openFile(tabData.path).then(openNext);
  }
  openNext();
}

function clearSavedSession() {
  try { localStorage.removeItem('ts2_session'); } catch(e) {}
}

// ─── Vditor Editor ──────────────────────────────────────────

function initVditor() {
  if (state.vditorReady) return;

  // If Vditor is not loaded yet, load the script dynamically
  if (typeof Vditor === 'undefined') {
    const existingScript = document.getElementById('vditorScriptTag');
    if (existingScript) {
      const newScript = document.createElement('script');
      newScript.id = 'vditorScriptTag';
      newScript.src = existingScript.src;
      newScript.onload = () => initVditor();
      newScript.onerror = () => {
        showToast('Vditor 加载失败，切换到原生编辑器', 'error');
        state.editorMode = 'plain';
        document.getElementById('vditor').style.display = 'none';
        document.getElementById('plainEditor').style.display = 'block';
      };
      existingScript.replaceWith(newScript);
      return;
    }
  }

  const acCfg = loadAcConfig();
  var currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
  state.vditor = new Vditor('vditor', {
    height: '100%',
    mode: 'wysiwyg',
    theme: currentTheme === 'light' ? 'classic' : 'dark',
    icon: 'material',
    cdn: '/static/vditor',
    placeholder: '开始输入...',
    cache: {
      enable: false,
    },
    hint: {
      delay: 200,
      parse: false,
      extend: buildHintExtends(acCfg),
    },
    toolbar: [
      'headings', 'bold', 'italic', 'strike', '|',
      'list', 'ordered-list', 'check', 'outdent', 'indent', '|',
      'quote', 'code', 'inline-code', 'table', '|',
      'link', 'upload', 'emoji', '|',
      'undo', 'redo', '|',
      'edit-mode', 'preview', 'fullscreen',
    ],
    tab: '\t',
    preview: {
      theme: {
        current: currentTheme === 'light' ? 'light' : 'dark',
      },
      hljs: {
        style: currentTheme === 'light' ? 'github' : 'tokyo-night-dark',
        lineNumber: true,
      },
    },
    upload: {
      url: `${API_BASE}/api/file/upload`,
      fieldName: 'files[]',
      extraData: () => ({ path: state.currentDir || '' }),
      handler: null,
      format: (files, responseText) => {
        try {
          const res = JSON.parse(responseText);
          if (res.code === 0 && res.data && res.data.uploaded) {
            return JSON.stringify({
              msg: '',
              code: 0,
              data: {
                errFiles: [],
                succMap: res.data.uploaded.reduce((m, f) => {
                  m[f.name] = f.url || f.path || f.name;
                  return m;
                }, {})
              }
            });
          }
        } catch (e) {}
        return responseText;
      },
    },
    value: '',
    after: () => {
      state.vditorReady = true;
    },
    input: () => {
      if (!state.activeTab) return;
      const content = state.vditor.getValue();
      state.fileContents[state.activeTab] = content;
      markTabModified(state.activeTab, content !== state.originalContents[state.activeTab]);
    },
  });
}

/* 为分屏 pane 初始化独立的 Vditor 实例 */
function initPaneVditor(paneId) {
  if (typeof Vditor === 'undefined') return;
  var vditorDiv = document.getElementById('paneVditor-' + paneId);
  if (!vditorDiv) return;
  // Vditor 容器和 PDF 容器已在 splitPane 中创建，这里只初始化 Vditor 实例
  if (state['paneVditorReady_' + paneId]) return;

  var currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
  state['paneVditor_' + paneId] = new Vditor('paneVditor-' + paneId, {
    height: '100%',
    mode: 'wysiwyg',
    theme: currentTheme === 'light' ? 'classic' : 'dark',
    icon: 'material',
    cdn: '/static/vditor',
    placeholder: '开始输入...',
    cache: { enable: false },
    toolbar: [
      'headings', 'bold', 'italic', 'strike', '|',
      'list', 'ordered-list', 'check', '|',
      'quote', 'code', 'inline-code', 'table', '|',
      'undo', 'redo',
    ],
    tab: '\t',
    preview: {
      theme: { current: currentTheme === 'light' ? 'light' : 'dark' },
      hljs: { style: currentTheme === 'light' ? 'github' : 'tokyo-night-dark', lineNumber: true },
    },
    value: '',
    after: function() {
      state['paneVditorReady_' + paneId] = true;
      // 如果当前活动 tab 是 PDF，初始化完成后隐藏 Vditor
      var activePath = state['paneActiveTab_' + paneId];
      var activeTab = (state['paneTabs_' + paneId] || []).find(function(t) { return t.path === activePath; });
      if (activeTab && activeTab._isPdf) {
        var vditorEl = document.getElementById('paneVditor-' + paneId);
        if (vditorEl) vditorEl.style.display = 'none';
      }
    },
    input: function() {
      var activePath = state['paneActiveTab_' + paneId];
      if (!activePath) return;
      var content = state['paneVditor_' + paneId].getValue();
      state['paneFileContents_' + paneId][activePath] = content;
      var tabs = state['paneTabs_' + paneId] || [];
      var tab = tabs.find(function(t) { return t.path === activePath; });
      if (tab) {
        var orig = (state['paneOriginalContents_' + paneId] || {})[activePath];
        tab.modified = content !== orig;
        // 更新 tab 修改标记点
        var tabsEl = document.getElementById('editorTabs-' + paneId);
        if (tabsEl) {
          var tabEl = tabsEl.querySelector('.tab[data-path="' + activePath + '"]');
          if (tabEl) {
            var modDot = tabEl.querySelector('.modified');
            if (modDot) modDot.style.display = tab.modified ? 'inline-block' : 'none';
          }
        }
      }
    },
  });
}

/* 分屏 pane 中加载 PDF */
async function loadPdfInPane(path, paneId) {
  var data = await client.downloadBinary(path);
  if (!data || data.code === -1) {
    showToast('打开 PDF 失败', 'error');
    return;
  }
  try {
    var pdf = await pdfjsLib.getDocument({ data: data }).promise;
    state['panePdfDoc_' + paneId] = pdf;
    if (!state['panePdfPage_' + paneId]) state['panePdfPage_' + paneId] = 1;
    if (!state['panePdfZoom_' + paneId]) state['panePdfZoom_' + paneId] = 1.0;
    await renderPanePdfPage(paneId);
  } catch (e) {
    showToast('PDF 渲染失败: ' + e.message, 'error');
  }
}

async function renderPanePdfPage(paneId) {
  var pdf = state['panePdfDoc_' + paneId];
  if (!pdf) return;
  var pageNum = state['panePdfPage_' + paneId] || 1;
  var zoom = state['panePdfZoom_' + paneId] || 1.0;
  var dual = state['panePdfDualPage_' + paneId] || false;
  var canvas = document.getElementById('panePdfCanvas-' + paneId);
  var canvas2 = document.getElementById('panePdfCanvas2-' + paneId);
  if (!canvas) return;

  var container = canvas.parentElement;
  var containerWidth = container ? container.clientWidth - 16 : 600;
  var availW = dual ? (containerWidth - 3) / 2 : containerWidth;
  var dpr = window.devicePixelRatio || 1;

  var page = await pdf.getPage(pageNum);
  var baseViewport = page.getViewport({ scale: 1.0 });
  var fitScale = availW / baseViewport.width;
  var baseScale = Math.min(fitScale * zoom, 3.0);
  var renderScale = baseScale * dpr * 1.5;
  var viewport = page.getViewport({ scale: renderScale });

  canvas.width = viewport.width;
  canvas.height = viewport.height;
  var cssWidth = baseScale * baseViewport.width;
  var cssHeight = baseScale * baseViewport.height;
  canvas.style.width = cssWidth + 'px';
  canvas.style.height = cssHeight + 'px';
  canvas.style.display = '';
  canvas.style.boxShadow = '0 2px 12px rgba(0,0,0,0.3)';
  var ctx = canvas.getContext('2d');

  // 双页：准备第二页
  var page2 = null, viewport2 = null, ctx2 = null;
  if (dual && pageNum < pdf.numPages) {
    page2 = await pdf.getPage(pageNum + 1);
    var baseViewport2 = page2.getViewport({ scale: 1.0 });
    var fitScale2 = availW / baseViewport2.width;
    var baseScale2 = Math.min(fitScale2 * zoom, 3.0);
    var renderScale2 = baseScale2 * dpr * 1.5;
    viewport2 = page2.getViewport({ scale: renderScale2 });
    canvas2.width = viewport2.width;
    canvas2.height = viewport2.height;
    canvas2.style.width = (baseScale2 * baseViewport2.width) + 'px';
    canvas2.style.height = (baseScale2 * baseViewport2.height) + 'px';
    canvas2.style.display = '';
    canvas2.style.boxShadow = '0 2px 12px rgba(0,0,0,0.3)';
    ctx2 = canvas2.getContext('2d');
  } else if (canvas2) {
    canvas2.style.display = 'none';
  }

  // 隐藏两个 canvas 一起渲染，避免闪烁
  canvas.style.visibility = 'hidden';
  if (dual && page2 && canvas2.style.display !== 'none') canvas2.style.visibility = 'hidden';

  var tasks = [page.render({ canvasContext: ctx, viewport }).promise];
  if (page2 && ctx2) tasks.push(page2.render({ canvasContext: ctx2, viewport: viewport2 }).promise);
  await Promise.all(tasks);

  canvas.style.visibility = '';
  if (dual && page2 && canvas2.style.display !== 'none') canvas2.style.visibility = '';

  // 容器排版
  if (container) {
    container.style.flexDirection = dual ? 'row' : 'column';
    container.style.alignItems = dual ? 'flex-start' : 'center';
    container.style.justifyContent = dual ? 'center' : 'flex-start';
    container.style.gap = dual ? '3px' : '';
  }

  var infoText = dual ?
    pageNum + '-' + Math.min(pageNum + 1, pdf.numPages) + '/' + pdf.numPages :
    pageNum + '/' + pdf.numPages;
  var infoEl = document.getElementById('panePdfInfo-' + paneId);
  if (infoEl) {
    infoEl.value = pageNum;
    infoEl.max = pdf.numPages;
  }
  var totalEl = document.getElementById('panePdfTotal-' + paneId);
  if (totalEl) totalEl.textContent = '/ ' + pdf.numPages;
  var zoomEl = document.getElementById('panePdfZoom-' + paneId);
  if (zoomEl) zoomEl.textContent = Math.round(zoom * 100) + '%';
}

function panePdfNav(paneId, delta) {
  var pdf = state['panePdfDoc_' + paneId];
  if (!pdf) return;
  var current = state['panePdfPage_' + paneId] || 1;
  var dual = state['panePdfDualPage_' + paneId] || false;
  var step = dual ? 2 : 1;
  var next = current + delta * step;
  if (next < 1 || next > pdf.numPages) return;
  state['panePdfPage_' + paneId] = next;
  renderPanePdfPage(paneId);
  _saveSession();
}

function panePdfGoToPage(paneId, page) {
  var pdf = state['panePdfDoc_' + paneId];
  if (!pdf) return;
  if (page < 1 || page > pdf.numPages || isNaN(page)) {
    var infoEl = document.getElementById('panePdfInfo-' + paneId);
    if (infoEl) infoEl.value = state['panePdfPage_' + paneId] || 1;
    return;
  }
  state['panePdfPage_' + paneId] = page;
  renderPanePdfPage(paneId);
  _saveSession();
}

function panePdfZoom(paneId, delta) {
  var current = state['panePdfZoom_' + paneId] || 1.0;
  var next = Math.max(0.3, Math.min(3.0, current + delta));
  state['panePdfZoom_' + paneId] = next;
  renderPanePdfPage(paneId);
  _saveSession();
}

function togglePanePdfDual(paneId) {
  var dual = !(state['panePdfDualPage_' + paneId] || false);
  state['panePdfDualPage_' + paneId] = dual;
  var pdf = state['panePdfDoc_' + paneId];
  if (pdf && dual) {
    var pageNum = state['panePdfPage_' + paneId] || 1;
    if (pageNum === pdf.numPages && pdf.numPages > 1) {
      state['panePdfPage_' + paneId] = pdf.numPages - 1;
    }
  }
  renderPanePdfPage(paneId);
  _saveSession();
}

// 分屏 PDF 目录
async function loadPanePdfOutline(paneId) {
  var pdf = state['panePdfDoc_' + paneId];
  if (!pdf) return;
  var container = document.getElementById('panePdfOutlineContent-' + paneId);
  if (!container) return;
  container.innerHTML = '';
  try {
    var outline = await pdf.getOutline();
    if (!outline || outline.length === 0) {
      container.innerHTML = '<div style="padding:6px 10px;color:var(--fg-muted);font-size:10px">此 PDF 无目录信息</div>';
      return;
    }
    await _renderPaneOutlineItems(outline, container, 0, paneId);
  } catch (e) {
    container.innerHTML = '<div style="padding:6px 10px;color:var(--fg-muted);font-size:10px">目录加载失败</div>';
  }
}

async function _renderPaneOutlineItems(items, container, depth, paneId) {
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var el = document.createElement('div');
    el.className = 'pdf-outline-item';
    el.style.paddingLeft = (10 + depth * 14) + 'px';
    el.textContent = item.title;
    el.title = item.title;
    (function(it, element, pid) {
      var _resolve = async function() {
        if (!it.dest) return;
        try {
          var dest = it.dest;
          if (typeof dest === 'string') dest = await state['panePdfDoc_' + pid].getDestination(dest);
          if (dest && dest[0]) {
            var pageIdx = await state['panePdfDoc_' + pid].getPageIndex(dest[0]);
            element.dataset.pageNum = pageIdx + 1;
          }
        } catch (e) {}
      };
      _resolve();
    })(item, el, paneId);
    el.addEventListener('click', function() {
      var pn = parseInt(this.dataset.pageNum);
      var pdf = state['panePdfDoc_' + paneId];
      if (pn && pdf && pn >= 1 && pn <= pdf.numPages) {
        state['panePdfPage_' + paneId] = pn;
        renderPanePdfPage(paneId);
        container.querySelectorAll('.pdf-outline-item').forEach(function(e) { e.classList.remove('active'); });
        this.classList.add('active');
      }
    });
    container.appendChild(el);
    if (item.items && item.items.length > 0) {
      await _renderPaneOutlineItems(item.items, container, depth + 1, paneId);
    }
  }
}

function togglePanePdfOutline(paneId) {
  var panel = document.getElementById('panePdfOutline-' + paneId);
  if (!panel) return;
  if (panel.style.display === 'none' || panel.style.display === '') {
    panel.style.display = 'flex';
    loadPanePdfOutline(paneId);
  } else {
    panel.style.display = 'none';
  }
}

function showEditor() {
  hidePdfViewer();
  // 确保 slides/mindmap/jupyter 编辑器隐藏
  var slidesView = document.getElementById('slidesEditorView');
  if (slidesView) slidesView.style.display = 'none';
  document.getElementById('kmindEditorView').style.display = 'none';
  document.getElementById('jupyterEditorView').style.display = 'none';
  document.getElementById('monacoEditorView').style.display = 'none';
  document.getElementById('browserView').style.display = 'none';
  document.getElementById('welcomeScreen').style.display = 'none';
  if (state.editorMode === 'vditor') {
    document.getElementById('vditor').style.display = '';
    document.getElementById('plainEditor').style.display = 'none';
    if (!state.vditorReady) {
      initVditor();
    }
  } else {
    document.getElementById('vditor').style.display = 'none';
    document.getElementById('plainEditor').style.display = '';
  }
}

function hideEditor() {
  hidePdfViewer();
  document.getElementById('welcomeScreen').style.display = '';
  renderWelcomeRecentFiles();
  renderWelcomeTaskSessions();
  document.getElementById('vditor').style.display = 'none';
  document.getElementById('plainEditor').style.display = 'none';
  document.getElementById('kmindEditorView').style.display = 'none';
  document.getElementById('jupyterEditorView').style.display = 'none';
  document.getElementById('monacoEditorView').style.display = 'none';
  document.getElementById('browserView').style.display = 'none';
}

function setEditorContent(content) {
  if (state.editorMode === 'vditor') {
    if (state.vditorReady && state.vditor) {
      state.vditor.setValue(content || '');
    }
  } else {
    document.getElementById('plainEditor').value = content || '';
  }
}

function getEditorContent() {
  if (state.editorMode === 'vditor') {
    if (state.vditorReady && state.vditor) {
      return state.vditor.getValue();
    }
    return '';
  } else {
    return document.getElementById('plainEditor').value;
  }
}

function toggleEditorMode() {
  const content = getEditorContent();

  if (state.editorMode === 'vditor') {
    state.editorMode = 'plain';
    document.getElementById('vditor').style.display = 'none';
    document.getElementById('plainEditor').style.display = '';
    document.getElementById('plainEditor').value = content;
    document.getElementById('btnEditorToggle').innerHTML = '✨<span class="btn-label"> Vditor</span>';
  } else {
    state.editorMode = 'vditor';
    document.getElementById('plainEditor').style.display = 'none';
    document.getElementById('vditor').style.display = '';
    if (!state.vditorReady) {
      initVditor();
    } else {
      state.vditor.setValue(content);
    }
    document.getElementById('btnEditorToggle').innerHTML = '📝<span class="btn-label"> 原生</span>';
  }
}

// ─── PDF Viewer ─────────────────────────────────────────────

function showPdfViewer() {
  state.viewingPdf = true;
  document.getElementById('welcomeScreen').style.display = 'none';
  document.getElementById('vditor').style.display = 'none';
  document.getElementById('plainEditor').style.display = 'none';
  document.getElementById('pdfViewer').style.display = 'flex';
}

function hidePdfViewer() {
  state.viewingPdf = false;
  document.getElementById('pdfViewer').style.display = 'none';
  document.getElementById('pdfAiPanel').style.display = 'none';
  document.getElementById('pdfOutlinePanel').style.display = 'none';
}

function destroyPdfSession() {
  _clearPdfCache();
  if (state.pdfPath) {
    state.pdfViewState[state.pdfPath] = { pageNum: state.pdfPageNum, zoom: state.pdfZoom, dualPage: state.pdfDualPage };
  }
  if (state.pdfDoc) {
    state.pdfDoc.destroy();
    state.pdfDoc = null;
  }
  state.pdfPageNum = 1;
  state.pdfZoom = 1.0;
  state.pdfPath = null;
  pdfAiMessages = [];
  document.getElementById('pdfAiMessages').innerHTML = '';
  document.getElementById('pdfIndexBtn').textContent = '建立索引';
}

// ─── PDF 目录/书签 ──────────────────────────────────────────

async function loadPdfOutline() {
  if (!state.pdfDoc) return;
  var container = document.getElementById('pdfOutlineContent');
  if (!container) return;
  container.innerHTML = '';
  try {
    var outline = await state.pdfDoc.getOutline();
    if (!outline || outline.length === 0) {
      container.innerHTML = '<div style="padding:8px 12px;color:var(--fg-muted);font-size:11px">此 PDF 无目录信息</div>';
      return;
    }
    await _renderOutlineItems(outline, container, 0);
  } catch (e) {
    container.innerHTML = '<div style="padding:8px 12px;color:var(--fg-muted);font-size:11px">目录加载失败</div>';
  }
}

async function _renderOutlineItems(items, container, depth) {
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var el = document.createElement('div');
    el.className = 'pdf-outline-item';
    el.style.paddingLeft = (12 + depth * 16) + 'px';
    el.textContent = item.title;
    el.title = item.title;
    // 获取目标页码
    (function(it, element) {
      var _resolvePage = async function() {
        if (!it.dest) return;
        try {
          var dest = it.dest;
          if (typeof dest === 'string') {
            dest = await state.pdfDoc.getDestination(dest);
          }
          if (dest && dest[0]) {
            var pageIdx = await state.pdfDoc.getPageIndex(dest[0]);
            element.dataset.pageNum = pageIdx + 1;
          }
        } catch (e) {}
      };
      _resolvePage();
    })(item, el);
    el.addEventListener('click', async function() {
      var pn = parseInt(this.dataset.pageNum);
      if (pn && pn >= 1 && pn <= state.pdfPageCount) {
        await _goToPdfPage(pn);
        container.querySelectorAll('.pdf-outline-item').forEach(function(e) { e.classList.remove('active'); });
        this.classList.add('active');
      }
    });
    container.appendChild(el);
    // 递归渲染子目录
    if (item.items && item.items.length > 0) {
      await _renderOutlineItems(item.items, container, depth + 1);
    }
  }
}

function togglePdfOutline() {
  var panel = document.getElementById('pdfOutlinePanel');
  if (!panel) return;
  if (panel.style.display === 'none' || panel.style.display === '') {
    panel.style.display = 'flex';
  } else {
    panel.style.display = 'none';
  }
}

async function renderPdfPage() {
  if (!state.pdfDoc) return;
  const canvas = document.getElementById('pdfCanvas');
  const ctx = canvas.getContext('2d');
  const textLayer = document.getElementById('pdfTextLayer');
  const canvas2 = document.getElementById('pdfCanvas2');
  const dual = state.pdfDualPage;
  const dpr = window.devicePixelRatio || 1;
  const container = document.getElementById('pdfCanvasContainer');
  const containerWidth = container ? container.clientWidth - 32 : 800;

  const zoom = state.pdfZoom;
  const page = await state.pdfDoc.getPage(state.pdfPageNum);
  const baseViewport = page.getViewport({ scale: 1.0 });
  var availW = dual ? (containerWidth - 3) / 2 : containerWidth;
  const fitScale = availW / baseViewport.width;
  const baseScale = Math.min(fitScale * zoom, 3.0);
  const renderScale = baseScale * dpr * 1.5;
  const viewport = page.getViewport({ scale: renderScale });
  const cssWidth = baseScale * baseViewport.width;
  const cssHeight = baseScale * baseViewport.height;

  canvas.width = viewport.width;
  canvas.height = viewport.height;
  canvas.style.width = cssWidth + 'px';
  canvas.style.height = cssHeight + 'px';
  canvas.style.display = '';

  // 双页：准备第二页 canvas 尺寸
  var page2 = null, viewport2 = null, cssWidth2 = 0, cssHeight2 = 0;
  if (dual && state.pdfPageNum < state.pdfPageCount) {
    page2 = await state.pdfDoc.getPage(state.pdfPageNum + 1);
    const baseViewport2 = page2.getViewport({ scale: 1.0 });
    const fitScale2 = availW / baseViewport2.width;
    const baseScale2 = Math.min(fitScale2 * zoom, 3.0);
    const renderScale2 = baseScale2 * dpr * 1.5;
    viewport2 = page2.getViewport({ scale: renderScale2 });
    cssWidth2 = baseScale2 * baseViewport2.width;
    cssHeight2 = baseScale2 * baseViewport2.height;
    canvas2.width = viewport2.width;
    canvas2.height = viewport2.height;
    canvas2.style.width = cssWidth2 + 'px';
    canvas2.style.height = cssHeight2 + 'px';
    canvas2.style.display = '';
  } else {
    canvas2.style.display = 'none';
  }

  // 隐藏两个 canvas，一起渲染完成后再显示，避免闪烁
  canvas.style.visibility = 'hidden';
  if (dual && canvas2.style.display !== 'none') canvas2.style.visibility = 'hidden';

  var renderTasks = [page.render({ canvasContext: ctx, viewport }).promise];
  if (page2 && viewport2) {
    const ctx2 = canvas2.getContext('2d');
    renderTasks.push(page2.render({ canvasContext: ctx2, viewport: viewport2 }).promise);
  }
  await Promise.all(renderTasks);

  canvas.style.visibility = '';
  if (dual && canvas2.style.display !== 'none') canvas2.style.visibility = '';

  if (textLayer) {
    textLayer.style.width = cssWidth + 'px';
    textLayer.style.height = cssHeight + 'px';
    textLayer.innerHTML = '';
    const textContent = await page.getTextContent();
    for (const item of textContent.items) {
      if (!item.str) continue;
      const tx = item.transform;
      const fontSize = Math.sqrt(tx[0] * tx[0] + tx[1] * tx[1]) * baseScale;
      const posX = tx[4] * baseScale;
      const posY = cssHeight - tx[5] * baseScale - fontSize * 0.85;
      const div = document.createElement('div');
      div.textContent = item.str;
      div.style.cssText = `
        position:absolute;
        left:${posX}px; top:${posY}px;
        font-size:${fontSize}px;
        line-height:${fontSize}px;
        font-family:sans-serif;
        color:transparent;
        white-space:pre;
        cursor:text;
        pointer-events:auto;
        user-select:text;
        -webkit-user-select:text;
      `;
      textLayer.appendChild(div);
    }
  }

  // 容器排版
  container.style.flexDirection = dual ? 'row' : 'column';
  container.style.alignItems = dual ? 'flex-start' : 'center';
  container.style.justifyContent = dual ? 'center' : 'flex-start';
  container.style.gap = dual ? '3px' : '0';

  var infoText = dual ?
    `第 ${state.pdfPageNum}-${Math.min(state.pdfPageNum + 1, state.pdfPageCount)} 页 / 共 ${state.pdfPageCount} 页` :
    `第 ${state.pdfPageNum} 页 / 共 ${state.pdfPageCount} 页`;
  document.getElementById('pdfPageInfo').textContent = infoText;
  document.getElementById('pdfPageInput').value = state.pdfPageNum;
  document.getElementById('pdfPageInput').max = state.pdfPageCount;
  document.getElementById('pdfPrevBtn').disabled = state.pdfPageNum <= 1;
  document.getElementById('pdfNextBtn').disabled = state.pdfPageNum >= state.pdfPageCount;
  document.getElementById('pdfZoomLevel').textContent = Math.round(state.pdfZoom * 100) + '%';
  _schedulePdfPreload();
}

// ─── PDF 页面预加载缓存 ──────────────────────────────

var _pdfPageCache = {};
var _pdfPreloadGen = 0;

function _clearPdfCache() {
  _pdfPageCache = {};
  _pdfPreloadGen++;
}

function _getCachedPdfPage(pageNum) {
  var c = _pdfPageCache[pageNum];
  if (!c || c.zoom !== state.pdfZoom) return null;
  return c;
}

function _swapFromCache(pageNum, canvasEl) {
  var c = _getCachedPdfPage(pageNum);
  if (!c) return false;
  canvasEl.width = c.canvas.width;
  canvasEl.height = c.canvas.height;
  canvasEl.style.width = c.cssWidth + 'px';
  canvasEl.style.height = c.cssHeight + 'px';
  canvasEl.style.boxShadow = '0 2px 12px rgba(0,0,0,0.3)';
  canvasEl.getContext('2d').drawImage(c.canvas, 0, 0);
  return true;
}

function _schedulePdfPreload() {
  if (!state.pdfDoc) return;
  var gen = ++_pdfPreloadGen;
  setTimeout(function() { _doPdfPreload(gen); }, 120);
}

async function _doPdfPreload(gen) {
  if (gen !== _pdfPreloadGen) return;
  if (!state.pdfDoc || !state.pdfPath) return;
  var zoom = state.pdfZoom;
  var container = document.getElementById('pdfCanvasContainer');
  if (!container) return;
  var containerWidth = container.clientWidth - 32;
  var dual = state.pdfDualPage;
  var step = dual ? 2 : 1;
  var cur = state.pdfPageNum;
  var max = state.pdfPageCount;

  // 计算下一组和上一组需要预加载的页码
  var pages = [];
  // 下一组
  var ns = cur + step;
  if (dual && ns <= max) { pages.push(ns); if (ns + 1 <= max) pages.push(ns + 1); }
  else if (!dual && ns <= max) pages.push(ns);
  // 上一组
  var ps = cur - step;
  if (dual && ps >= 1) { if (ps >= 1) pages.push(ps); if (ps + 1 <= max) pages.push(ps + 1); }
  else if (!dual && ps >= 1) pages.push(ps);

  // 去重、排除当前可见页、排除已缓存
  var seen = {};
  for (var i = 0; i < pages.length; i++) {
    var p = pages[i];
    if (p < 1 || p > max) continue;
    if (!dual && p === cur) continue;
    if (dual && (p === cur || p === cur + 1)) continue;
    if (_getCachedPdfPage(p)) continue;
    seen[p] = true;
  }
  var toPreload = Object.keys(seen).map(Number).sort(function(a,b) { return a - b; });
  if (toPreload.length === 0) return;

  var availW = dual ? (containerWidth - 3) / 2 : containerWidth;
  var dpr = window.devicePixelRatio || 1;

  for (var i = 0; i < toPreload.length; i++) {
    if (gen !== _pdfPreloadGen) return;
    var p = toPreload[i];
    if (_getCachedPdfPage(p)) continue;
    try {
      var page = await state.pdfDoc.getPage(p);
      var bv = page.getViewport({ scale: 1.0 });
      var fitS = availW / bv.width;
      var baseS = Math.min(fitS * zoom, 3.0);
      var renderS = baseS * dpr * 1.5;
      var vp = page.getViewport({ scale: renderS });
      var oc = document.createElement('canvas');
      oc.width = vp.width;
      oc.height = vp.height;
      await page.render({ canvasContext: oc.getContext('2d'), viewport: vp }).promise;
      _pdfPageCache[p] = { canvas: oc, cssWidth: baseS * bv.width, cssHeight: baseS * bv.height, zoom: zoom };
    } catch(e) { /* skip */ }
  }
}

async function _goToPdfPage(newPage) {
  if (newPage < 1 || newPage > state.pdfPageCount || newPage === state.pdfPageNum) return;
  var dual = state.pdfDualPage;
  var canvas = document.getElementById('pdfCanvas');
  var canvas2 = document.getElementById('pdfCanvas2');
  if (!canvas) return;

  var c1 = _getCachedPdfPage(newPage);
  var c2 = dual && newPage < state.pdfPageCount ? _getCachedPdfPage(newPage + 1) : null;

  if (c1 && (!dual || c2)) {
    // 两页都已缓存 → 瞬间切换
    state.pdfPageNum = newPage;
    if (state.pdfPath) state.pdfViewState[state.pdfPath] = { pageNum: state.pdfPageNum, zoom: state.pdfZoom, dualPage: dual };

    canvas.style.display = '';
    _swapFromCache(newPage, canvas);
    if (dual && newPage < state.pdfPageCount && canvas2) {
      canvas2.style.display = '';
      _swapFromCache(newPage + 1, canvas2);
    } else if (canvas2) {
      canvas2.style.display = 'none';
    }

    var container = document.getElementById('pdfCanvasContainer');
    if (dual) {
      container.style.flexDirection = 'row';
      container.style.alignItems = 'flex-start';
      container.style.justifyContent = 'center';
      container.style.gap = '3px';
    } else {
      container.style.flexDirection = 'column';
      container.style.alignItems = 'center';
      container.style.justifyContent = 'flex-start';
      container.style.gap = '0';
    }

    var infoText = dual ?
      '第 ' + newPage + '-' + Math.min(newPage + 1, state.pdfPageCount) + ' 页 / 共 ' + state.pdfPageCount + ' 页' :
      '第 ' + newPage + ' 页 / 共 ' + state.pdfPageCount + ' 页';
    document.getElementById('pdfPageInfo').textContent = infoText;
    document.getElementById('pdfPageInput').value = newPage;
    document.getElementById('pdfPageInput').max = state.pdfPageCount;
    document.getElementById('pdfPrevBtn').disabled = newPage <= 1;
    document.getElementById('pdfNextBtn').disabled = newPage >= state.pdfPageCount;
    document.getElementById('pdfZoomLevel').textContent = Math.round(state.pdfZoom * 100) + '%';

    _schedulePdfPreload();
    _saveSession();
    return;
  }

  // 缓存未命中 → 常规渲染
  state.pdfPageNum = newPage;
  if (state.pdfPath) state.pdfViewState[state.pdfPath] = { pageNum: state.pdfPageNum, zoom: state.pdfZoom, dualPage: dual };
  await renderPdfPage();
  _saveSession();
}

let _pdfLoadGen = 0;

async function _loadAndRenderPdf(path) {
  _clearPdfCache();
  const gen = ++_pdfLoadGen;
  if (state.pdfDoc && state.pdfPath && state.pdfPath !== path) {
    state.pdfViewState[state.pdfPath] = { pageNum: state.pdfPageNum, zoom: state.pdfZoom, dualPage: state.pdfDualPage };
    state.pdfDoc.destroy();
    state.pdfDoc = null;
  }
  let data = state.pdfCache[path];
  let fromCache = true;
  if (!data) {
    fromCache = false;
    const res = await client.downloadBinary(path);
    if (!res || res.code === -1) {
      showToast('打开 PDF 失败' + (res ? ': ' + res.msg : ''), 'error');
      return false;
    }
    if (gen !== _pdfLoadGen) return false;
    data = res;
    state.pdfCache[path] = data;
  }
      showPdfViewer();
      _clearPdfCache();
      try {
    const pdf = await pdfjsLib.getDocument({ data }).promise;
    if (gen !== _pdfLoadGen) { pdf.destroy(); return false; }
    state.pdfDoc = pdf;
    state.pdfPageCount = pdf.numPages;
    state.pdfPath = path;
    const vs = state.pdfViewState[path];
    state.pdfPageNum = vs ? vs.pageNum : 1;
    state.pdfZoom = vs ? vs.zoom : 1.0;
    state.pdfDualPage = vs ? (vs.dualPage || false) : false;
    await renderPdfPage();
    if (gen !== _pdfLoadGen) return false;
    loadPdfOutline();
    return true;
  } catch (e) {
    if (fromCache) {
      delete state.pdfCache[path];
    }
    showToast('PDF 渲染失败: ' + e.message, 'error');
    hidePdfViewer();
    return false;
  }
}

async function openPdf(path) {
  // 外部直接调用 openPdf 时，确保有编辑器 tab
  var existing = state.openTabs.find(t => t.path === path);
  if (existing) {
    switchToTab(path);
    return;
  }
  // 通过 editorService.open 走 tab 创建流程
  await editorService.open(path);
}

// ─── 思维导图 (.kmind) ───
var kmindState = { path: null, ready: false, queue: [] };

// 全局监听 iframe 消息
window.addEventListener('message', function(e) {
  if (!e.data || !e.data.action) return;
  if (e.data.action === 'mindmapReady') { kmindState.ready = true; }
  if (e.data.action === 'saveData') kmindHandleSaveData(e);
});

async function openKmind(path) {
  var existing = state.openTabs.find(t => t.path === path);
  if (existing) { editorService.switchTo(path); return; }
  await editorService.open(path);
}

async function kmindCreateNew() {
  var kmindName = await modalPrompt('思维导图名称', '新思维导图');
  if (!kmindName || !kmindName.trim()) return;
  kmindName = kmindName.trim();
  if (!kmindName.endsWith('.kmind')) kmindName += '.kmind';
  var defaultData = {
    root: { data: { text: '中心主题' }, children: [] },
    theme: { template: 'classic3', config: {} },
    layout: 'mindMap2',
    smmVersion: '0.13.1'
  };
  var kmindContent = JSON.stringify(defaultData, null, 2);
  var basePath = 'data/courses/思维导图';
  try { await client.api('/api/file/createDir', { path: basePath }); } catch(e) {}
  var filePath = basePath + '/' + kmindName;
  try {
    var kmindRes = await client.putFile(filePath, kmindContent);
    if (kmindRes && kmindRes.code === 0) {
      showToast('已创建: ' + kmindName, 'success');
      await refreshTree();
      await openKmind(filePath);
    } else {
      showToast('创建失败: ' + ((kmindRes && kmindRes.msg) || ''), 'error');
    }
  } catch(e) {
    showToast('创建失败', 'error');
  }
}

async function kmindWaitReady() {
  if (kmindState.ready) return;
  var iframe = document.getElementById('kmindIframe');
  if (!iframe || !iframe.contentWindow) return;
  return new Promise(function(resolve) {
    var check = function() {
      if (kmindState.ready) { resolve(); return; }
      try {
        iframe.contentWindow.postMessage({ action: 'ping' }, '*');
      } catch(e) {}
      setTimeout(check, 300);
    };
    setTimeout(function() { kmindState.ready = true; resolve(); }, 12000);
    check();
  });
}

async function kmindLoadData(path, content) {
  var data;
  try { data = JSON.parse(content); } catch(e) { data = null; }
  if (!data) { showToast('无效的思维导图文件', 'error'); return; }
  kmindState.path = path;
  kmindState.ready = false;
  // 记录最近打开
  _kmindAddRecent(path);
  // 动态创建 iframe（防止页面加载时预下载 mindmap 资源）
  var wrap = document.getElementById('kmindIframeWrap');
  if (!wrap) return;
  var oldIframe = document.getElementById('kmindIframe');
  if (oldIframe) oldIframe.remove();
  var iframe = document.createElement('iframe');
  iframe.id = 'kmindIframe';
  iframe.style.cssText = 'width:100%;height:100%;border:none;display:block';
  wrap.appendChild(iframe);
  iframe.src = '/static/mindmap/index.html';
  // 等待加载后发数据
  await kmindWaitReady();
  try { iframe.contentWindow.postMessage({ action: 'loadData', data: data }, '*'); } catch(e) {}
  showToast('已打开思维导图', 'info');
}

async function kmindSave() {
  if (!kmindState.path) { showToast('未打开任何思维导图', 'error'); return; }
  var iframe = document.getElementById('kmindIframe');
  if (!iframe || !iframe.contentWindow) { showToast('思维导图编辑器尚未加载', 'error'); return; }
  document.getElementById('kmindSaveStatus').textContent = '保存中...';
  showToast('正在保存...', 'info');
  iframe.contentWindow.postMessage({ action: 'getData' }, '*');
}

async function kmindHandleSaveData(e) {
  if (e.data && e.data.action === 'saveData' && e.data.data && kmindState.path) {
    var kmsContent = JSON.stringify(e.data.data, null, 2);
    try {
      var kmsRes = await client.putFile(kmindState.path, kmsContent);
      if (kmsRes && kmsRes.code === 0) {
        document.getElementById('kmindSaveStatus').textContent = '已保存';
        setTimeout(function() { document.getElementById('kmindSaveStatus').textContent = ''; }, 2000);
        showToast('已保存', 'success');
      } else {
        document.getElementById('kmindSaveStatus').textContent = '保存失败';
        showToast('保存失败: ' + ((kmsRes && kmsRes.msg) || 'write error'), 'error');
      }
    } catch(e) {
      document.getElementById('kmindSaveStatus').textContent = '保存失败';
      showToast('保存失败', 'error');
    }
  }
}

function _kmindAddRecent(path) {
  var list = JSON.parse(localStorage.getItem('kmindRecent') || '[]');
  list = list.filter(function(p) { return (typeof p === 'string' ? p : p.path) !== path; });
  list.unshift({ path: path, time: Date.now() });
  if (list.length > 10) list = list.slice(0, 10);
  localStorage.setItem('kmindRecent', JSON.stringify(list));
  _kmindRenderRecent();
}

function _kmindRenderRecent() {
  var el = document.getElementById('kmindRecentItems');
  if (!el) return;
  var list = JSON.parse(localStorage.getItem('kmindRecent') || '[]');
  if (!list.length) { el.innerHTML = '<span style="color:var(--fg-dim);font-size:11px">暂无</span>'; return; }
  el.innerHTML = list.map(function(item) {
    var name = item.path.split('/').pop();
    return '<div onclick="openKmind(\'' + escapeHtml(item.path).replace(/'/g, "\\'") + '\')" style="padding:4px 6px;border-radius:4px;cursor:pointer;font-size:11px;color:var(--fg-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis" onmouseover="this.style.background=\'var(--bg-tertiary)\'" onmouseout="this.style.background=\'transparent\'">' + escapeHtml(name) + '</div>';
  }).join('');
}

async function kmindExportPNG() {
  showToast('导出功能需要先保存思维导图', 'info');
}

async function openOfficeAsPdf(path) {
  showToast('正在转换文档为 PDF...');
  try {
    var resp = await fetch(API_BASE + '/api/file/convert-to-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: path })
    });
    if (resp.ok && resp.headers.get('content-type') && resp.headers.get('content-type').includes('pdf')) {
      var blob = await resp.blob();
      var arrayBuffer = await blob.arrayBuffer();
      showPdfViewer();
      try {
        var pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
        if (state.pdfDoc) state.pdfDoc.destroy();
        state.pdfDoc = pdf;
        state.pdfPageNum = 1;
        state.pdfPageCount = pdf.numPages;
        state.pdfPath = path;
        await renderPdfPage();
        document.getElementById('pdfPageInput').value = 1;
        document.getElementById('pdfPageInput').max = state.pdfPageCount;
        document.getElementById('pdfPageInfo').textContent = '第 1 页 / 共 ' + state.pdfPageCount + ' 页';
        if (state.pdfPageCount > 1) {
          document.getElementById('pdfNextBtn').disabled = false;
          document.getElementById('pdfPageInput').disabled = false;
        }
      } catch (e) {
        showToast('PDF 渲染失败: ' + e.message, 'error');
        hidePdfViewer();
      }
    } else {
      var res = await resp.json();
      showToast('转换失败: ' + (res.msg || '未知错误'), 'error');
      window.open(API_BASE + '/api/file/download/' + path.split('/').map(s => encodeURIComponent(s)).join('/'), '_blank');
    }
  } catch (e) {
    showToast('转换失败: ' + e.message, 'error');
    window.open(API_BASE + '/api/file/download/' + path.split('/').map(s => encodeURIComponent(s)).join('/'), '_blank');
  }
}

// ─── Nav Tabs ───────────────────────────────────────────────

document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const tabName = tab.dataset.tab;
    switchNavTab(tabName);
  });
});

function switchNavTab(tabName) {
  // 如果 Agent 面板在分屏中，点击 Agent tab 时聚焦分屏而非 sidebar
  if (tabName === 'agent' && _agentPaneId) {
    setActivePane(_agentPaneId);
    // 不切换 sidebar 面板，因为 panel-agent 已在分屏中
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
    return;
  }

  state.activeNavTab = tabName;

  document.querySelectorAll('.nav-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
  document.querySelectorAll('.nav-panel').forEach(p => p.classList.toggle('active', p.id === `panel-${tabName}`));

  // 离开 slides/mindmap 时隐藏其编辑器
  var slidesView = document.getElementById('slidesEditorView');
  if (slidesView) slidesView.style.display = 'none';
  document.getElementById('kmindEditorView').style.display = 'none';

  // 切回文件面板时，通过 editorService 恢复编辑器状态
  if (tabName === 'files') {
    if (state.activeTab) {
      editorService.switchTo(state.activeTab);
    } else {
      hideEditor();
    }
    loadPushDashboard();
  }

  if (tabName === 'tasks') loadTasks();
  if (tabName === 'bookmarks') loadBookmarks();
  if (tabName === 'projects') loadProjects();
  if (tabName === 'source') { /* source merged into projects */ }
  if (tabName === 'courses') { loadCourses(); initExecutionPanel(); }
  if (tabName === 'agent') initAgentPanel();
  if (tabName === 'slides') initSlidesPanel();
  if (tabName === 'stats') loadStatsPanel();
  if (tabName === 'dashboard') loadDashboardPanel();
}

// ─── File Tree ──────────────────────────────────────────────

async function loadFileTree(subdir = '') {
  const res = await client.readDir(subdir);
  if (res.code === 0) {
    state.dirCache[subdir] = res.data;
    renderFileTree();
  }
}

function renderFileTree() {
  const tree = document.getElementById('fileTree');
  tree.innerHTML = '';

  // 工作区模式：如果切换到了非 TS2 工作区，显示该工作区的根目录
  var rootKeys = EXPOSED_DIRS;
  if (state.currentWorkspaceRoot) {
    rootKeys = ['.'];
  }

  var rootEntries;
  if (state.currentWorkspaceRoot) {
    // 非默认工作区：从 dirCache 读取根目录列表
    var cached = state.dirCache['.'];
    if (cached) {
      rootEntries = cached;
    } else {
      rootEntries = [{ name: '(加载中...)', path: '', is_dir: false, ext: '', size: 0 }];
    }
  } else {
    rootEntries = EXPOSED_DIRS.map(d => ({
      name: d,
      path: d,
      is_dir: true,
      ext: '',
      size: 0,
    }));
  }

  rootEntries.forEach(function(entry) {
    renderTreeItem(tree, entry, 0);
    if (entry.is_dir && state.expandedDirs.has(entry.path)) {
      renderChildren(tree, entry.path, 1);
    }
  });
}

function renderChildren(container, parentPath, depth) {
  const children = state.dirCache[parentPath];
  if (!children) return;
  const sorted = sortEntries(children);
  sorted.forEach(child => {
    renderTreeItem(container, child, depth);
    if (child.is_dir && state.expandedDirs.has(child.path)) {
      renderChildren(container, child.path, depth + 1);
    }
  });
}

function renderTreeItem(container, entry, depth) {
  const isActive = entry.is_dir
    ? state.currentDir === entry.path
    : state.activeTab === entry.path;
  const item = document.createElement('div');
  item.className = 'tree-item' + (isActive ? ' active' : '');
  item.style.setProperty('--depth', depth);
  item.dataset.path = entry.path;
  item.dataset.isDir = entry.is_dir ? '1' : '0';

  const icon = entry.is_dir
    ? (state.expandedDirs.has(entry.path) ? '📂' : '📁')
    : getFileIcon(entry.ext);

  item.innerHTML = `
    <span class="icon">${icon}</span>
    <span class="name">${entry.name}</span>
    ${!entry.is_dir ? `<span class="size">${formatSize(entry.size)}</span>` : ''}
  `;

  item.addEventListener('click', () => onTreeItemClick(entry));
  item.addEventListener('contextmenu', (e) => onTreeItemContext(e, entry));

  container.appendChild(item);
}

function sortEntries(entries) {
  const dirs = entries.filter(e => e.is_dir).sort((a, b) => a.name.localeCompare(b.name));
  const files = entries.filter(e => !e.is_dir).sort((a, b) => a.name.localeCompare(b.name));
  return [...dirs, ...files];
}

function getFileIcon(ext) {
  const icons = {
    '.md':'📝','.rmd':'📝','.txt':'📄','.tex':'📐',
    '.py':'🐍','.js':'📜','.ts':'📘','.json':'📋',
    '.yaml':'📋','.yml':'📋','.r':'📊','.R':'📊',
    '.cpp':'⚙️','.c':'⚙️','.h':'⚙️','.java':'☕',
    '.go':'🔵','.rs':'🦀','.html':'🌐','.css':'🎨',
    '.bib':'📚','.sql':'🗃️','.pdf':'📕','.png':'🖼️',
    '.jpg':'🖼️','.svg':'🖼️','.gif':'🖼️',
  };
  return icons[ext] || '📄';
}

function formatSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + 'B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'K';
  return (bytes / 1024 / 1024).toFixed(1) + 'M';
}

async function onTreeItemClick(entry) {
  if (entry.is_dir) {
    state.currentDir = entry.path;
    updateFileBreadcrumb();
    if (state.expandedDirs.has(entry.path)) {
      state.expandedDirs.delete(entry.path);
    } else {
      state.expandedDirs.add(entry.path);
      if (!state.dirCache[entry.path]) {
        const res = await client.readDir(entry.path);
        if (res.code === 0) {
          state.dirCache[entry.path] = res.data;
        }
      }
    }
    renderFileTree();
  } else if (entry.ext === '.pdf') {
    await openPdf(entry.path);
  } else if (entry.ext === '.docx' || entry.ext === '.xlsx' || entry.ext === '.pptx') {
    await openOfficeAsPdf(entry.path);
  } else if (entry.ext === '.html' || entry.ext === '.htm') {
    const encodedPath = entry.path.split('/').map(s => encodeURIComponent(s)).join('/');
    window.open(API_BASE + '/api/file/download/' + encodedPath + '?preview=true', '_blank');
  } else if (entry.ext === '.kmind') {
    await editorService.open(entry.path);
  } else if (shouldShowIdePicker(entry)) {
    await editorService.open(entry.path);
  } else {
    await openFile(entry.path);
  }
}

function onTreeItemContext(e, entry) {
  e.preventDefault();
  state.contextTarget = entry;
  const menu = document.getElementById('contextMenu');
  menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
  menu.style.top = Math.min(e.clientY, window.innerHeight - 200) + 'px';
  menu.classList.add('show');
  // 显示"添加为课程资源"选项（当有挂起的课程时）
  const addResItem = document.getElementById('ctxAddResource');
  const addResSep = document.getElementById('ctxAddResourceSep');
  if (state._pendingResourceCourse && !entry.is_dir) {
    addResItem.style.display = '';
    addResSep.style.display = '';
    addResItem.dataset.courseId = state._pendingResourceCourse;
  } else {
    addResItem.style.display = 'none';
    addResSep.style.display = 'none';
  }
  // 显示"外部编辑器打开"和"用...打开"选项（仅文件）
  const extEditItem = document.getElementById('ctxExternalEdit');
  extEditItem.style.display = (!entry.is_dir) ? '' : 'none';
  const openWithItem = document.getElementById('ctxOpenWith');
  openWithItem.style.display = (!entry.is_dir && shouldShowIdePicker(entry)) ? '' : 'none';
}

async function refreshTree() {
  // 如果正在搜索，重新执行搜索而不是刷新文件树（避免搜索结果丢失）
  const searchInput = document.getElementById('searchInput');
  const query = searchInput ? searchInput.value.trim() : '';
  if (query) {
    const res = await client.search(query);
    if (res.code === 0 && res.data) {
      const tree = document.getElementById('fileTree');
      tree.innerHTML = '';
      const entries = Array.isArray(res.data) ? res.data : [];
      if (!entries.length) {
        tree.innerHTML = '<div class="tree-loading">未找到结果</div>';
        return;
      }
      const sorted = sortEntries(entries);
      sorted.forEach(entry => renderTreeItem(tree, entry, 0));
    }
    return;
  }
  for (const dirPath of state.expandedDirs) {
    const res = await client.readDir(dirPath);
    if (res.code === 0) {
      state.dirCache[dirPath] = res.data;
    }
  }
  for (const d of EXPOSED_DIRS) {
    if (state.expandedDirs.has(d)) {
      const res = await client.readDir(d);
      if (res.code === 0) state.dirCache[d] = res.data;
    }
  }
  renderFileTree();
}

// ─── File Editing ───────────────────────────────────────────

async function openFile(path) {
  await editorService.open(path);
}

function addTab(path, name) {
  const tabs = document.getElementById('editorTabs');
  const tab = document.createElement('div');
  tab.className = 'tab';
  tab.dataset.path = path;
  tab.title = name;
  tab.draggable = true;
  var tabData = state.openTabs.find(function(t) { return t.path === path; });
  var icon = (tabData && tabData._isSlides) ? '📔' : getFileIcon('.' + path.split('.').pop());
  tab.innerHTML = `
    <span>${icon}</span>
    <span class="tab-label">${name}</span>
    <span class="modified" style="display:none"></span>
    <span class="close">×</span>
  `;

  tab.addEventListener('click', (e) => {
    if (e.target.classList.contains('close')) {
      closeTab(path);
    } else {
      switchToTab(path);
    }
  });

  tab.addEventListener('dragstart', (e) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', path);
    e.dataTransfer.setData('application/x-pane-id', '0');
    tab.classList.add('dragging');
  });

  tab.addEventListener('dragend', () => {
    tab.classList.remove('dragging');
    tabs.querySelectorAll('.tab.drag-over').forEach(t => t.classList.remove('drag-over'));
  });

  tab.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  });

  tab.addEventListener('dragenter', (e) => {
    e.preventDefault();
    if (!tab.classList.contains('dragging')) {
      tab.classList.add('drag-over');
    }
  });

  tab.addEventListener('dragleave', () => {
    tab.classList.remove('drag-over');
  });

  tab.addEventListener('drop', (e) => {
    e.preventDefault();
    tab.classList.remove('drag-over');
    const srcPath = e.dataTransfer.getData('text/plain');
    if (!srcPath || srcPath === path) return;

    const allTabs = Array.from(tabs.children);
    const srcIdx = state.openTabs.findIndex(t => t.path === srcPath);
    const dstIdx = state.openTabs.findIndex(t => t.path === path);
    if (srcIdx === -1 || dstIdx === -1) return;

    const [moved] = state.openTabs.splice(srcIdx, 1);
    state.openTabs.splice(dstIdx, 0, moved);

    allTabs.forEach(t => t.remove());
    state.openTabs.forEach(t => addTab(t.path, t.name));
    switchToTab(state.activeTab);
  });

  tabs.appendChild(tab);
}

function switchToTab(path) {
  editorService.switchTo(path);
}

async function closeTab(path) {
  const idx = state.openTabs.findIndex(t => t.path === path);
  if (idx === -1) return;

  if (state.openTabs[idx].modified) {
    if (!await modalConfirm(`"${state.openTabs[idx].name}" 有未保存的更改，确定关闭？`)) return;
  }

  const tab = state.openTabs[idx];
  const isPdf = tab._isPdf;
  const isSlides = tab._isSlides;
  const isKmind = tab._isKmind;
  state.openTabs.splice(idx, 1);
  delete state.fileContents[path];
  delete state.originalContents[path];

  if (isPdf) {
    delete state.pdfCache[path];
    delete state.pdfViewState[path];
    if (state.activeTab === path || state.openTabs.filter(t => t._isPdf).length === 0) {
      destroyPdfSession();
      hidePdfViewer();
    }
  }
  if (isSlides) {
    slidesSaveCurrent();
    _slidesSaveToCache(path);
    delete _slidesNotebookCache[path];
    if (_slidesActivePath === path) _slidesActivePath = null;
    if (slidesState.nbSource === 'local') slidesSaveToLocalSilent();
    else slidesSaveToServerSilent();
    document.getElementById('slidesEditorView').style.display = 'none';
  }
  if (isKmind) {
    document.getElementById('kmindEditorView').style.display = 'none';
  }
  if (tab._isJupyter) {
    document.getElementById('jupyterEditorView').style.display = 'none';
    document.getElementById('jupyterIframeWrap').innerHTML = '';
  }
  if (tab._isMonaco) {
    if (_monacoCurrentFile && _monacoEditor) {
      _monacoFiles[_monacoCurrentFile] = _monacoEditor.getValue();
    }
    delete _monacoFiles[path];
    // dispose the model for this file
    try {
      var uri = _monacoApi.Uri.file(path);
      var model = _monacoApi.editor.getModel(uri);
      if (model) model.dispose();
    } catch(e) {}
    // if no more Monaco tabs, destroy the editor
    var remaining = state.openTabs.filter(function(t) { return t._isMonaco; });
    if (remaining.length === 0) {
      document.getElementById('monacoEditorView').style.display = 'none';
      document.getElementById('monacoEditorWrap').innerHTML = '';
      if (_monacoEditor) { _monacoEditor.dispose(); _monacoEditor = null; _monacoReady = false; _monacoCurrentFile = null; }
    }
  }
  if (tab._isBrowser) {
    document.getElementById('browserView').style.display = 'none';
    var frame = document.getElementById('browserFrame');
    if (frame) { frame.src = 'about:blank'; frame.removeAttribute('data-url'); }
  }

  const tabEl = document.querySelector(`.tab[data-path="${CSS.escape(path)}"]`);
  if (tabEl) tabEl.remove();

  if (state.activeTab === path) {
    if (state.openTabs.length > 0) {
      switchToTab(state.openTabs[state.openTabs.length - 1].path);
    } else {
      state.activeTab = null;
      hideEditor();
      document.getElementById('statusPath').textContent = '就绪';
    }
  }
  _saveSession();
}

function markTabModified(path, modified) {
  const tab = state.openTabs.find(t => t.path === path);
  if (tab) {
    tab.modified = modified;
    const tabEl = document.querySelector(`.tab[data-path="${CSS.escape(path)}"] .modified`);
    if (tabEl) tabEl.style.display = modified ? 'inline-block' : 'none';
  }
}

async function saveCurrentFile() {
  // 如果活动 pane 是分屏编辑器，走分屏保存
  if (_splitActive && _activePaneId !== '0' && _activePaneId !== _agentPaneId) {
    await savePaneFile(_activePaneId);
    return;
  }

  if (!state.activeTab) return;

  const path = state.activeTab;
  // Monaco 标签页：从实例取值
  if (_monacoEditor && _monacoCurrentFile && state.activeTab === path) {
    var monoTab = state.openTabs.find(function(t) { return t.path === path; });
    if (monoTab && monoTab._isMonaco) {
      const content = _monacoEditor.getValue();
      let res;
      if (_monacoSrcFile) {
        res = await client.api('/api/data/projects/writeFile', { path: _monacoCurrentFile, content });
      } else {
        res = await client.putFile(_monacoCurrentFile, content);
        if (res.code !== 0) {
          res = await client.api('/api/data/projects/writeFile', { path: _monacoCurrentFile, content });
        }
      }
      if (res.code === 0) {
        _monacoFiles[_monacoCurrentFile] = content;
        markTabModified(path, false);
        showToast('已保存: ' + _monacoCurrentFile.split('/').pop(), 'success');
        await refreshTree();
      } else {
        showToast('保存失败: ' + (res.msg || ''), 'error');
      }
      return;
    }
  }
  const content = getEditorContent();

  let res = await client.putFile(path, content);
  // 如果 FileSyncEngine 保存失败（路径不在 EXPOSED_DIRS 中），fallback 到项目源码 API
  if (res.code !== 0) {
    res = await client.api('/api/data/projects/writeFile', { path, content });
  }
  if (res.code === 0) {
    state.fileContents[path] = content;
    state.originalContents[path] = content;
    markTabModified(path, false);
    showToast('已保存: ' + path.split('/').pop(), 'success');
    await refreshTree();
  } else {
    showToast('保存失败: ' + (res.msg || ''), 'error');
  }
}

async function savePaneFile(paneId) {
  var activePath = state['paneActiveTab_' + paneId];
  if (!activePath) return;

  var tab = (state['paneTabs_' + paneId] || []).find(function(t) { return t.path === activePath; });
  if (tab && tab._isPdf) { showToast('PDF 文件无法编辑保存', 'error'); return; }

  var vditorInstance = state['paneVditor_' + paneId];
  var content = (tab && tab._isMonaco && state['paneMonaco_' + paneId])
    ? state['paneMonaco_' + paneId].getValue()
    : (vditorInstance && state['paneVditorReady_' + paneId])
    ? vditorInstance.getValue()
    : (state['paneFileContents_' + paneId][activePath] || '');

  var res = await client.putFile(activePath, content);
  if (res.code !== 0) {
    res = await client.api('/api/data/projects/writeFile', { path: activePath, content: content });
  }
  if (res.code === 0) {
    state['paneFileContents_' + paneId][activePath] = content;
    state['paneOriginalContents_' + paneId] = state['paneOriginalContents_' + paneId] || {};
    state['paneOriginalContents_' + paneId][activePath] = content;
    if (tab) tab.modified = false;
    // 更新 tab 修改标记
    var tabsEl = document.getElementById('editorTabs-' + paneId);
    if (tabsEl) {
      var tabEl = tabsEl.querySelector('.tab[data-path="' + activePath + '"]');
      if (tabEl) {
        var modDot = tabEl.querySelector('.modified');
        if (modDot) modDot.style.display = 'none';
      }
    }
    showToast('已保存: ' + activePath.split('/').pop(), 'success');
    await refreshTree();
  } else {
    showToast('保存失败: ' + (res.msg || ''), 'error');
  }
}

// ─── Path Bar ───────────────────────────────────────────────

function updatePathBar(path) {
  const bar = document.getElementById('pathBar');
  const parts = path.split('/');
  let html = '<span class="crumb" data-path="">~</span>';

  let accumulated = '';
  parts.forEach((part, i) => {
    accumulated += (i > 0 ? '/' : '') + part;
    html += '<span class="sep">/</span>';
    html += `<span class="crumb" data-path="${accumulated}">${part}</span>`;
  });

  bar.innerHTML = html;

  bar.querySelectorAll('.crumb').forEach(crumb => {
    crumb.addEventListener('click', async () => {
      const p = crumb.dataset.path;
      if (p) {
        state.currentDir = p;
        updateFileBreadcrumb();
        state.expandedDirs.add(p);
        if (!state.dirCache[p]) {
          const res = await client.readDir(p);
          if (res.code === 0) state.dirCache[p] = res.data;
        }
        renderFileTree();
      }
    });
  });
}

// ─── File Sidebar Breadcrumb ─────────────────────────────

function updateFileBreadcrumb() {
  const el = document.getElementById('fileBreadcrumb');
  const pathEl = document.getElementById('fileBreadcrumbPath');
  if (!state.currentDir) {
    el.style.display = 'none';
    return;
  }
  el.style.display = 'flex';
  pathEl.textContent = state.currentDir;
}

document.getElementById('fileNewBtn').addEventListener('click', () => {
  const dir = state.currentDir || '';
  if (!dir) { showToast('禁止在根目录创建文件，请先进入子目录', 'error'); return; }
  showModal('新建文件', 'filename.md', async (name) => {
    if (!name) return;
    const path = dir + '/' + name;
    const res = await client.putFile(path, '');
    if (res.code === 0) {
      showToast('已创建: ' + name, 'success');
      state.expandedDirs.add(dir);
      if (!state.dirCache[dir]) {
        const dirRes = await client.readDir(dir);
        if (dirRes.code === 0) state.dirCache[dir] = dirRes.data;
      }
      renderFileTree();
      await openFile(path);
    } else {
      showToast('创建失败', 'error');
    }
  });
});

// ─── Tasks (Kanban) ─────────────────────────────────────────

async function loadTasks() {
  const res = await client.getTasks();
  if (res.code === 0 && res.data) {
    state.tasks = Array.isArray(res.data) ? res.data : (res.data.tasks || []);
    renderKanban();
  } else {
    renderKanbanEmpty();
  }
}

function getTaskStatus(task) {
  return task.status || task.column || '待办';
}

function _todayStr() {
  return new Date().toISOString().split('T')[0];
}

function renderKanban() {
  let filtered = state.tasks;
  const dateFilter = document.getElementById('taskDateFilter').value;
  if (dateFilter) {
    filtered = filtered.filter(t => t.due_date === dateFilter);
  }

  const todo = filtered.filter(t => getTaskStatus(t) === '待办');
  const inProgress = filtered.filter(t => getTaskStatus(t) === '进行中');
  const done = filtered.filter(t => getTaskStatus(t) === '已完成');

  document.getElementById('countTodo').textContent = todo.length;
  document.getElementById('countProgress').textContent = inProgress.length;
  document.getElementById('countDone').textContent = done.length;

  // Stats
  document.getElementById('taskStatTotal').textContent = filtered.length;
  document.getElementById('taskStatDone').textContent = done.length;
  const todayStr = _todayStr();
  const todayDue = filtered.filter(t => getTaskStatus(t) !== '已完成' && t.due_date === todayStr);
  const overdue = filtered.filter(t => getTaskStatus(t) !== '已完成' && t.due_date && t.due_date < todayStr);
  document.getElementById('taskStatOverdue').textContent = overdue.length;
  document.getElementById('taskStatToday').textContent = todayDue.length;

  renderKanbanColumn('kanbanTodo', todo, '待办');
  renderKanbanColumn('kanbanProgress', inProgress, '进行中');
  renderKanbanColumn('kanbanDone', done, '已完成');

  setupKanbanDragDrop();
  setupKanbanAddButtons();
  var hId = sessionStorage.getItem('_hlTask');
  if (hId) { sessionStorage.removeItem('_hlTask'); highlightTask(hId); }
}

function highlightTask(taskId) {
  if (!taskId) return;
  var card = document.querySelector('.task-card[data-task-id="' + taskId + '"]');
  if (!card) { sessionStorage.setItem('_hlTask', taskId); return; }
  card.classList.add('task-highlight');
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(function() { card.classList.remove('task-highlight'); }, 2000);
}

function _sortTasks(tasks) {
  const order = { '高': 0, '中': 1, '低': 2 };
  const todayStr = _todayStr();
  return tasks.sort((a, b) => {
    const aOverdue = a.due_date && a.due_date < todayStr ? 0 : 1;
    const bOverdue = b.due_date && b.due_date < todayStr ? 0 : 1;
    if (aOverdue !== bOverdue) return aOverdue - bOverdue;
    const pa = order[a.priority] ?? 1;
    const pb = order[b.priority] ?? 1;
    if (pa !== pb) return pa - pb;
    if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
    if (a.due_date) return -1;
    if (b.due_date) return 1;
    return 0;
  });
}

function renderKanbanColumn(containerId, tasks, status) {
  const container = document.getElementById(containerId);
  if (!tasks.length) {
    container.innerHTML = '<div class="empty-state"><span class="empty-icon">📋</span><span>暂无任务</span></div>';
    return;
  }

  _sortTasks(tasks);

  container.innerHTML = tasks.map(task => {
    const taskId = task.id || task._id || '';
    const todayStr = _todayStr();
    const isOverdue = task.due_date && getTaskStatus(task) !== '已完成' && task.due_date < todayStr;
    const isRecurring = task.recurrence && task.recurrence !== '不循环';
    const desc = task.description ? escapeHtml(task.description.substring(0, 60)) : '';
    return `
    <div class="task-card${isOverdue ? ' task-overdue' : ''}" draggable="true" data-task-id="${taskId}">
      <div class="task-actions">
        <button class="edit-btn" data-task-id="${taskId}" title="编辑">✏️</button>
        <button class="del-btn" data-task-id="${taskId}" title="删除">🗑️</button>
      </div>
      <div class="task-title">${escapeHtml(task.title || task.name || '未命名')}${isRecurring ? ' <span style="font-size:10px;color:var(--accent)">🔄</span>' : ''}</div>
      ${desc ? '<div class="task-desc">' + desc + (task.description.length > 60 ? '...' : '') + '</div>' : ''}
      <div class="task-meta">
        ${task.priority ? `<span class="task-priority ${task.priority}">${task.priority}</span>` : ''}
        ${task.due_date ? `<span class="task-date${isOverdue ? ' task-date-overdue' : ''}">📅 ${task.due_date}</span>` : ''}
        ${isRecurring ? `<span class="task-recurrence">🔄${task.recurrence}</span>` : ''}
        ${task.duration ? `<span class="task-duration">⏱️${task.duration}分钟</span>` : ''}
      </div>
    </div>
  `;
  }).join('');

  // Bind edit/delete buttons
  container.querySelectorAll('.edit-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const taskId = btn.dataset.taskId;
      const task = state.tasks.find(t => (t.id || t._id) === taskId);
      if (task) showTaskEditModal(task);
    });
  });

  container.querySelectorAll('.del-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const taskId = btn.dataset.taskId;
      if (await modalConfirm('确定删除此任务？')) {
        const res = await client.deleteTask(taskId);
        if (res.code === 0) {
          showToast('任务已删除', 'success');
          await loadTasks();
        } else {
          showToast('删除失败: ' + (res.msg || ''), 'error');
        }
      }
    });
  });

  // Double-click to edit
  container.querySelectorAll('.task-card').forEach(card => {
    card.addEventListener('dblclick', (e) => {
      if (e.target.closest('.task-actions')) return;
      const taskId = card.dataset.taskId;
      const task = state.tasks.find(t => (t.id || t._id) === taskId);
      if (task) showTaskEditModal(task);
    });
  });
}

document.getElementById('taskDateFilter').addEventListener('change', () => renderKanban());
document.getElementById('taskClearFilter').addEventListener('click', () => {
  document.getElementById('taskDateFilter').value = '';
  renderKanban();
});

function renderKanbanEmpty() {
  ['kanbanTodo', 'kanbanProgress', 'kanbanDone'].forEach(id => {
    document.getElementById(id).innerHTML = '<div class="empty-state"><span class="empty-icon">📋</span><span>暂无任务</span></div>';
  });
  document.getElementById('countTodo').textContent = '0';
  document.getElementById('countProgress').textContent = '0';
  document.getElementById('countDone').textContent = '0';
}

function setupKanbanDragDrop() {
  const cards = document.querySelectorAll('.task-card');
  const columns = document.querySelectorAll('.kanban-column-body');

  cards.forEach(card => {
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', card.dataset.taskId);
      card.classList.add('dragging');
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      columns.forEach(c => c.classList.remove('drag-over'));
    });
  });

  columns.forEach(col => {
    col.addEventListener('dragover', (e) => {
      e.preventDefault();
      col.classList.add('drag-over');
    });
    col.addEventListener('dragleave', () => col.classList.remove('drag-over'));
    col.addEventListener('drop', async (e) => {
      e.preventDefault();
      col.classList.remove('drag-over');
      const taskId = e.dataTransfer.getData('text/plain');
      const newStatus = col.dataset.status;
      if (taskId && newStatus) {
        await client.updateTask(taskId, { status: newStatus });
        await loadTasks();
        loadPushDashboard();
        showToast('任务已移动', 'success');
      }
    });
  });
}

function setupKanbanAddButtons() {
  document.querySelectorAll('.kanban-column-header .add-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const status = btn.dataset.status;
      showTaskCreateModal(status);
    });
  });
}

// ─── Task Modal ─────────────────────────────────────────────

let taskModalMode = 'create'; // 'create' or 'edit'
let taskModalEditId = null;

function showTaskCreateModal(defaultStatus) {
  taskModalMode = 'create';
  taskModalEditId = null;
  document.getElementById('taskModalTitle').textContent = '新建任务';
  document.getElementById('taskModalTitleInput').value = '';
  document.getElementById('taskModalDesc').value = '';
  document.getElementById('taskModalPriority').value = '中';
  document.getElementById('taskModalRecurrence').value = '不循环';
  document.getElementById('taskModalDueDate').value = '';
  document.getElementById('taskModalStartTime').value = '';
  document.getElementById('taskModalDuration').value = '60';
  document.getElementById('taskModalOverlay').classList.add('show');
  document.getElementById('taskModalTitleInput').dataset.defaultStatus = defaultStatus || '待办';
  setTimeout(() => document.getElementById('taskModalTitleInput').focus(), 100);
}

function showTaskEditModal(task) {
  taskModalMode = 'edit';
  taskModalEditId = task.id || task._id;
  document.getElementById('taskModalTitle').textContent = '编辑任务';
  document.getElementById('taskModalTitleInput').value = task.title || task.name || '';
  document.getElementById('taskModalDesc').value = task.description || '';
  document.getElementById('taskModalPriority').value = task.priority || '中';
  document.getElementById('taskModalRecurrence').value = task.recurrence || '不循环';
  document.getElementById('taskModalDueDate').value = task.due_date || '';
  var st = task.start_time || '';
  if (st && st.length === 10) st += 'T00:00';
  document.getElementById('taskModalStartTime').value = st;
  document.getElementById('taskModalDuration').value = task.duration || '60';
  document.getElementById('taskModalOverlay').classList.add('show');
  setTimeout(() => document.getElementById('taskModalTitleInput').focus(), 100);
}

document.getElementById('taskModalCancel').addEventListener('click', () => {
  document.getElementById('taskModalOverlay').classList.remove('show');
});

document.getElementById('taskModalConfirm').addEventListener('click', async () => {
  const title = document.getElementById('taskModalTitleInput').value.trim();
  if (!title) return;

  const description = document.getElementById('taskModalDesc').value.trim();
  const priority = document.getElementById('taskModalPriority').value;
  const recurrence = document.getElementById('taskModalRecurrence').value;
  const dueDate = document.getElementById('taskModalDueDate').value;
  var startTime = document.getElementById('taskModalStartTime').value;
  if (startTime && startTime.includes('T')) startTime = startTime.split('T')[0];
  const duration = parseInt(document.getElementById('taskModalDuration').value) || 60;

  const payload = { title, priority, due_date: dueDate, description, recurrence, start_time: startTime, duration };

  if (taskModalMode === 'create') {
    const defaultStatus = document.getElementById('taskModalTitleInput').dataset.defaultStatus || '待办';
    payload.status = defaultStatus;
    const res = await client.createTask(payload);
    if (res.code === 0) {
      showToast('任务已创建', 'success');
      await loadTasks();
    } else {
      showToast('创建失败: ' + (res.msg || ''), 'error');
    }
  } else {
    const res = await client.updateTask(taskModalEditId, payload);
    if (res.code === 0) {
      showToast('任务已更新', 'success');
      await loadTasks();
    } else {
      showToast('更新失败: ' + (res.msg || ''), 'error');
    }
  }

  document.getElementById('taskModalOverlay').classList.remove('show');
});

document.getElementById('taskModalTitleInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    document.getElementById('taskModalConfirm').click();
  } else if (e.key === 'Escape') {
    document.getElementById('taskModalOverlay').classList.remove('show');
  }
});

// ─── Bookmarks ──────────────────────────────────────────────

async function loadBookmarks() {
  const res = await client.getBookmarks();
  if (res.code === 0 && res.data) {
    state.bookmarks = Array.isArray(res.data) ? res.data : (res.data.bookmarks || res.data.items || []);
    state.bookmarkCategories = [...new Set(state.bookmarks.map(b => b.category || b.group || '其他'))];
    renderBookmarkCategories();
    renderBookmarks();
  } else {
    document.getElementById('bookmarksGrid').innerHTML = '<div class="empty-state"><span class="empty-icon">🔖</span><span>暂无书签</span></div>';
  }
}

function renderBookmarkCategories() {
  const container = document.getElementById('bookmarkCategories');
  container.innerHTML = `<span class="bookmark-cat-btn ${state.bookmarkFilter === '' ? 'active' : ''}" data-cat="">全部</span>` +
    state.bookmarkCategories.map(cat =>
      `<span class="bookmark-cat-btn ${state.bookmarkFilter === cat ? 'active' : ''}" data-cat="${cat}">${cat}</span>`
    ).join('');

  container.querySelectorAll('.bookmark-cat-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.bookmarkFilter = btn.dataset.cat;
      renderBookmarkCategories();
      renderBookmarks();
    });
  });
}

function renderBookmarks() {
  const grid = document.getElementById('bookmarksGrid');
  let filtered = state.bookmarks;
  if (state.bookmarkFilter) {
    filtered = filtered.filter(b => (b.category || b.group || '其他') === state.bookmarkFilter);
  }

  const searchVal = document.getElementById('bookmarkSearch').value.trim().toLowerCase();
  if (searchVal) {
    filtered = filtered.filter(b =>
      (b.name || b.title || '').toLowerCase().includes(searchVal) ||
      (b.url || b.link || '').toLowerCase().includes(searchVal)
    );
  }

  if (!filtered.length) {
    grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><span class="empty-icon">🔖</span><span>暂无书签</span></div>';
    return;
  }

  grid.innerHTML = filtered.map(bm => {
    const name = bm.name || bm.title || '未命名';
    const url = bm.url || bm.link || '#';
    const icon = bm.icon || bm.favicon || getFaviconFromUrl(url);
    return `
      <a class="bookmark-card" href="${escapeHtml(url)}" target="_blank" rel="noopener" title="${escapeHtml(url)}">
        <div class="bm-icon">${icon}</div>
        <div class="bm-name">${escapeHtml(name)}</div>
        <div class="bm-url">${escapeHtml(extractDomain(url))}</div>
      </a>
    `;
  }).join('');
}

function getFaviconFromUrl(url) {
  try {
    const u = new URL(url);
    return u.hostname.charAt(0).toUpperCase();
  } catch { return '🔗'; }
}

function extractDomain(url) {
  try { return new URL(url).hostname; } catch { return url; }
}

document.getElementById('btnAddBookmark').addEventListener('click', showAddBookmarkDialog);

async function showAddBookmarkDialog() {
  const html = `
<div style="padding:4px">
  <div style="margin-bottom:12px">
    <label style="display:block;margin-bottom:4px;font-size:12px;color:var(--fg-muted)">名称</label>
    <input id="bmNameInput" type="text" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);box-sizing:border-box;font-size:13px">
  </div>
  <div style="margin-bottom:12px">
    <label style="display:block;margin-bottom:4px;font-size:12px;color:var(--fg-muted)">URL</label>
    <input id="bmUrlInput" type="text" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);box-sizing:border-box;font-size:13px" placeholder="https://...">
    <div style="margin-top:6px;display:flex;gap:4px">
      <button onclick="pasteClipboardToBookmark()" style="padding:4px 8px;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:4px;color:var(--fg);font-size:11px;cursor:pointer">📋 从剪贴板粘贴</button>
    </div>
  </div>
  <div style="margin-bottom:12px">
    <label style="display:block;margin-bottom:4px;font-size:12px;color:var(--fg-muted)">分类</label>
    <div style="display:flex;gap:8px;flex-wrap:wrap" id="bmCategoryRadios">
      <label style="display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer"><input type="radio" name="bmCat" value="preprint" checked> 预印本</label>
      <label style="display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer"><input type="radio" name="bmCat" value="search"> 学术搜索</label>
      <label style="display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer"><input type="radio" name="bmCat" value="journal"> 期刊</label>
      <label style="display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer"><input type="radio" name="bmCat" value="database"> 数据库</label>
      <label style="display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer"><input type="radio" name="bmCat" value="tool"> 工具</label>
      <label style="display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer"><input type="radio" name="bmCat" value="其他"> 其他</label>
    </div>
  </div>
  <div style="margin-bottom:16px">
    <label style="display:block;margin-bottom:4px;font-size:12px;color:var(--fg-muted)">图标 (emoji)</label>
    <input id="bmIconInput" type="text" value="🔖" style="width:60px;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);box-sizing:border-box;text-align:center;font-size:16px">
  </div>
  <div style="display:flex;gap:8px;justify-content:flex-end;border-top:1px solid var(--border);padding-top:12px">
    <button id="bmCancelBtn" onclick="closeHtmlModal()" style="padding:8px 16px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer;font-size:13px">取消</button>
    <button id="bmSaveBtn" onclick="doSaveBookmark()" style="padding:8px 16px;border:none;border-radius:6px;background:var(--accent);color:var(--bg);cursor:pointer;font-size:13px;font-weight:500">保存</button>
  </div>
</div>`;
  showHtmlModal('➕ 添加书签', html);
  setTimeout(() => document.getElementById('bmNameInput').focus(), 100);
}

async function doSaveBookmark() {
  const name = document.getElementById('bmNameInput').value.trim();
  const url = document.getElementById('bmUrlInput').value.trim();
  if (!name || !url) { showToast('请填写名称和URL', 'warning'); return; }
  const category = document.querySelector('input[name="bmCat"]:checked').value;
  const icon = document.getElementById('bmIconInput').value.trim() || '🔖';
  const btn = document.getElementById('bmSaveBtn');
  btn.disabled = true;
  btn.textContent = '保存中...';
  const res = await client.addBookmark({ name, url, category, icon });
  if (res.code === 0) {
    closeHtmlModal();
    loadBookmarks();
  } else {
    showToast(res.msg || '添加失败', 'error');
    btn.disabled = false;
    btn.textContent = '保存';
  }
}

function pasteClipboardToBookmark() {
  navigator.clipboard.readText().then(text => {
    const urlInput = document.getElementById('bmUrlInput');
    const nameInput = document.getElementById('bmNameInput');
    urlInput.value = text.trim();
    try { new URL(text.trim()); } catch { return; }
    // 尝试从URL推断名称
    const u = new URL(text.trim());
    let name = u.hostname.replace(/^www\./, '');
    if (u.pathname && u.pathname !== '/') {
      const parts = u.pathname.split('/').filter(Boolean);
      if (parts.length > 0) name = decodeURIComponent(parts[parts.length-1].replace(/\.\w+$/, ''));
    }
    nameInput.value = name;
    showToast('已从剪贴板粘贴', 'success');
  }).catch(() => showToast('无法读取剪贴板', 'warning'));
}

// ─── Projects ───────────────────────────────────────────────

async function loadProjects() {
  const res = await client.getProjects();
  if (res.code === 0 && res.data) {
    state.projects = Array.isArray(res.data) ? res.data : (res.data.projects || []);
    renderProjects();
  } else {
    document.getElementById('projectsPanel').innerHTML = '<div class="empty-state"><span class="empty-icon">🚀</span><span>暂无项目</span></div>';
  }
}

function renderProjects() {
  const panel = document.getElementById('projectsPanel');

  if (!state.projects.length) {
    panel.innerHTML = '<div class="empty-state"><span class="empty-icon">🚀</span><span>暂无项目</span></div>';
    return;
  }

  panel.innerHTML = state.projects.map(proj => {
    const name = proj.name || proj.title || '未命名';
    const created = proj.created || proj.created_at || '';
    const fileCount = proj.file_count || proj.files || 0;
    const progress = Math.min(100, Math.max(0, proj.progress || 0));
    const path = proj.path || proj.dir || '';

    return `
      <div class="project-card" data-path="${escapeHtml(path)}">
        <div class="proj-header">
          <span class="proj-name">${escapeHtml(name)}</span>
          <span class="proj-date">${created ? '📅 ' + created : ''}</span>
        </div>
        <div class="proj-progress">
          <div class="proj-progress-fill" style="width:${progress}%"></div>
        </div>
        <div class="proj-meta">
          <span>📄 ${fileCount} 文件</span>
          <span>📊 ${progress}%</span>
        </div>
      </div>
    `;
  }).join('');

  panel.querySelectorAll('.project-card').forEach(card => {
    card.addEventListener('click', async () => {
      const path = card.dataset.path;
      if (path) {
        // 跳转到源码浏览器并打开该目录
        state.srcCurrentPath = path;
        switchNavTab('projects');
        if (!_srcBrowserExpanded) toggleSrcBrowserInProjects();
        await srcLoadDir(path);
      }
    });
  });
}

// ─── 源码浏览器 ──────────────────────────────────────────

var _srcBrowserExpanded = false;

function toggleSrcBrowserInProjects() {
  var wrap = document.getElementById('srcBrowserWrap');
  var icon = document.getElementById('srcBrowserToggleIcon');
  if (!wrap) return;
  _srcBrowserExpanded = !_srcBrowserExpanded;
  wrap.style.display = _srcBrowserExpanded ? 'flex' : 'none';
  if (icon) icon.style.transform = _srcBrowserExpanded ? 'rotate(180deg)' : '';
  if (_srcBrowserExpanded) loadSource();
}

async function loadSource() {
  state.srcCurrentPath = '';
  await srcLoadDir('');
}

function showSourceAuthDialog() {
  showHtmlModal('🔒 源码浏览器授权', `
    <div style="padding:12px">
      <p style="margin:0 0 12px;font-size:13px;color:var(--fg-muted)">访问源码浏览器需要输入源码授权码</p>
      <input id="sourceAuthInput" type="password" placeholder="源码授权码" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:14px;box-sizing:border-box" autofocus>
      <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
        <button class="btn-action" onclick="doSourceAuth()" style="padding:8px 20px">确认</button>
      </div>
    </div>
  `, '400px');
}

async function doSourceAuth() {
  const code = document.getElementById('sourceAuthInput')?.value || '';
  if (!code) return;
  const res = await fetch(API_BASE + '/api/system/sourceAuth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  const data = await res.json();
  if (data.code === 0) {
    hideHtmlModal();
    await loadSource();
    showToast('源码浏览器已授权', 'success');
  } else {
    modalAlert('源码授权码错误');
  }
}

function hideHtmlModal() {
  const overlay = document.getElementById('modalOverlay');
  if (overlay) overlay.classList.remove('show');
}

function srcFileIcon(ext) {
  const icons = {'.py':'🐍','.js':'📜','.ts':'📜','.vue':'💚','.html':'🌐','.css':'🎨',
    '.json':'📋','.md':'📝','.txt':'📄','.rmd':'📄','.r':'📊','.tex':'📐','.bib':'📚',
    '.pdf':'📕','.xlsx':'📗','.csv':'📊','.db':'🗄️','.bat':'⚙️','.sh':'⚙️','.lua':'🌙',
    '.spec':'📦','.iss':'⚙️','.pyc':'🔧'};
  return icons[ext] || '📄';
}

function srcFormatSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + 'B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + 'KB';
  return (bytes/1048576).toFixed(1) + 'MB';
}

async function srcLoadDir(path) {
  state.srcCurrentPath = path;
  const listEl = document.getElementById('srcDirList');
  const pathEl = document.getElementById('srcPath');
  const upBtn = document.getElementById('srcUpBtn');

  pathEl.textContent = path || '/';
  upBtn.style.display = path ? 'inline-block' : 'none';

  listEl.innerHTML = '<div style="padding:12px;color:var(--fg-muted);font-size:12px">加载中...</div>';

  const res = await client.api('/api/data/projects/readDir', { path });
  if (res.code === 403 && res.msg && res.msg.includes('源码')) {
    // 源码鉴权失败，弹授权框
    showSourceAuthDialog();
    listEl.innerHTML = '<div style="padding:12px;color:var(--danger);font-size:12px">需要源码授权码</div>';
    return;
  }
  if (res.code !== 0) {
    listEl.innerHTML = '<div style="padding:12px;color:var(--danger);font-size:12px">加载失败</div>';
    return;
  }

  const entries = Array.isArray(res.data) ? res.data : [];
  if (!entries.length) {
    listEl.innerHTML = '<div class="empty-state"><span class="empty-icon">📂</span><span>空目录</span></div>';
    return;
  }

  listEl.innerHTML = entries.map(e => {
    const icon = e.is_dir ? '📁' : srcFileIcon(e.ext || '');
    const sizeStr = (!e.is_dir && e.size) ? srcFormatSize(e.size) : '';
    const dirClass = e.is_dir ? ' is-dir' : '';
    const activeClass = state.srcSelectedFile === e.path ? ' active' : '';
    return `<div class="src-entry${dirClass}${activeClass}" data-path="${escapeHtml(e.path)}" data-is-dir="${e.is_dir}" data-ext="${escapeHtml(e.ext||'')}">
      <span class="src-entry-icon">${icon}</span>
      <span class="src-entry-name">${escapeHtml(e.name)}</span>
      <span class="src-entry-size">${sizeStr}</span>
    </div>`;
  }).join('');

  // 绑定点击事件
  listEl.querySelectorAll('.src-entry').forEach(el => {
    el.addEventListener('click', async () => {
      const entryPath = el.dataset.path;
      const isDir = el.dataset.isDir === 'true';

      if (isDir) {
        await srcLoadDir(entryPath);
      } else {
        state.srcSelectedFile = entryPath;
        listEl.querySelectorAll('.src-entry').forEach(e => e.classList.remove('active'));
        el.classList.add('active');
        await srcLoadFile(entryPath);
      }
    });

    // 右键菜单
    el.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      e.stopPropagation();
      showSrcContextMenu(e, el);
    });
  });
}

function showSrcContextMenu(event, el) {
  // 移除已有菜单
  document.querySelectorAll('.src-context-menu').forEach(m => m.remove());

  const entryPath = el.dataset.path;
  const isDir = el.dataset.isDir === 'true';
  const ext = el.dataset.ext || '';
  const name = el.querySelector('.src-entry-name').textContent;

  const menu = document.createElement('div');
  menu.className = 'src-context-menu';

  const items = [];

  if (!isDir) {
    const entryExt = entryPath.includes('.') ? ('.' + entryPath.split('.').pop().toLowerCase()) : '';
    if (entryExt === '.html' || entryExt === '.htm') {
      items.push({ icon: '🌐', label: '在浏览器中打开', action: () => editorService.open(entryPath) });
      items.push({ icon: '✏️', label: '编辑源码', action: () => { srcOpenInEditor(entryPath); } });
    } else {
      items.push({ icon: '👁️', label: '查看', action: () => { srcLoadFile(entryPath); } });
      items.push({ icon: '✏️', label: '编辑', action: () => { srcOpenInEditor(entryPath); } });
    }
    items.push({ sep: true });
    items.push({ icon: '📥', label: '下载', action: () => { client.downloadFile(entryPath); showToast('下载中: ' + name, 'info'); } });
    items.push({ icon: '📋', label: '复制路径', action: () => { navigator.clipboard.writeText(entryPath); showToast('已复制路径', 'success'); } });
    items.push({ sep: true });
  } else {
    items.push({ icon: '📂', label: '打开目录', action: () => srcLoadDir(entryPath) });
    items.push({ icon: '📤', label: '上传到此目录', action: () => {
      const input = document.createElement('input');
      input.type = 'file'; input.multiple = true;
      input.addEventListener('change', async (e) => {
        if (!e.target.files.length) return;
        const res = await client.uploadFiles(e.target.files, entryPath);
        if (res.code === 0) { showToast('上传成功', 'success'); await srcLoadDir(entryPath); }
        else showToast('上传失败', 'error');
      });
      input.click();
    }});
    items.push({ icon: '📋', label: '复制路径', action: () => { navigator.clipboard.writeText(entryPath); showToast('已复制路径', 'success'); } });
    items.push({ sep: true });
  }

  items.push({ icon: '📝', label: '重命名', action: async () => {
    var newName = await modalPrompt('新名称:', name);
    if (newName && newName !== name) {
      const dir = entryPath.substring(0, entryPath.lastIndexOf('/'));
      const newPath = dir + '/' + newName;
      client.renameFile(entryPath, newPath).then(res => {
        if (res.code === 0) { showToast('已重命名', 'success'); srcLoadDir(state.srcCurrentPath || ''); }
        else showToast('重命名失败', 'error');
      });
    }
  }});

  items.push({ icon: '🗑️', label: '删除', action: async () => {
    if (await modalConfirm(`确定删除 "${name}"？此操作不可撤销。`)) {
      client.removeFile(entryPath).then(res => {
        if (res.code === 0) { showToast('已删除', 'success'); srcLoadDir(state.srcCurrentPath || ''); }
        else showToast('删除失败', 'error');
      });
    }
  }, danger: true });

  menu.innerHTML = items.map(item => {
    if (item.sep) return '<div class="ctx-sep"></div>';
    return `<div class="ctx-item${item.danger ? ' danger' : ''}" data-action="${item.label}">
      <span class="ctx-icon">${item.icon}</span><span>${item.label}</span>
    </div>`;
  }).join('');

  document.body.appendChild(menu);

  // 定位
  const x = Math.min(event.clientX, window.innerWidth - 200);
  const y = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 10);
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';

  // 绑定动作
  const actionItems = menu.querySelectorAll('.ctx-item');
  let actionIdx = 0;
  items.forEach(item => {
    if (item.sep) return;
    const el = actionItems[actionIdx++];
    if (el && item.action) {
      el.addEventListener('click', () => { menu.remove(); item.action(); });
    }
  });

  // 点击其他地方关闭
  const closeMenu = (e) => {
    if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', closeMenu); }
  };
  setTimeout(() => document.addEventListener('click', closeMenu), 0);
}

async function srcLoadFile(path) {
  const contentEl = document.getElementById('srcContent');

  contentEl.innerHTML = '<div style="padding:20px;color:var(--fg-muted)">加载中...</div>';

  const res = await client.api('/api/data/projects/readFile', { path });
  if (res.code !== 0) {
    contentEl.innerHTML = `<div style="padding:20px;color:var(--danger)">读取失败: ${escapeHtml(res.msg || '未知错误')}</div>`;
    return;
  }

  const data = res.data;
  const fileName = data.name || path.split('/').pop();
  const fileSize = srcFormatSize(data.size);

  if (data.is_binary) {
    contentEl.innerHTML = `
      <div class="src-file-header">
        <span class="src-file-name">${escapeHtml(fileName)}</span>
        <span class="src-file-size">${fileSize}</span>
        <span class="src-file-binary">二进制文件</span>
        <button class="src-download-btn" id="srcDownloadBtn" title="下载文件">📥 下载</button>
      </div>
      <div style="padding:40px;color:var(--fg-muted);text-align:center">此文件为二进制格式，无法以文本方式显示。</div>`;
    document.getElementById('srcDownloadBtn').addEventListener('click', () => {
      client.downloadFile(path);
      showToast('下载中: ' + fileName, 'info');
    });
    return;
  }

  contentEl.innerHTML = `
    <div class="src-file-header">
      <span class="src-file-name">${escapeHtml(fileName)}</span>
      <span class="src-file-size">${fileSize}</span>
      <button class="src-download-btn" id="srcDownloadBtn" title="下载文件">📥 下载</button>
      <button class="src-edit-btn" id="srcEditBtn" title="在编辑器中打开">✏️ 编辑</button>
    </div>
    <pre class="src-file-body">${escapeHtml(data.content || '')}</pre>`;

  // 绑定编辑按钮 - 用 srcOpenInEditor 打开
  document.getElementById('srcEditBtn').addEventListener('click', async () => {
    await srcOpenInEditor(path);
  });

  // 绑定下载按钮
  document.getElementById('srcDownloadBtn').addEventListener('click', () => {
    client.downloadFile(path);
    showToast('下载中: ' + fileName, 'info');
  });
}

async function srcOpenInEditor(path) {
  // 通过源码 API 读取文件内容，然后用 Monaco Editor 打开
  var monoName = path.split('/').pop();
  var res = await client.api('/api/data/projects/readFile', { path });
  if (res.code !== 0 || !res.data) { showToast('打开失败: ' + (res.msg || '读取错误'), 'error'); return; }
  if (res.data.is_binary) { showToast('二进制文件无法编辑', 'error'); return; }

  var content = res.data.content || '';
  // 保存当前 Monaco 内容
  if (_monacoCurrentFile && _monacoEditor) {
    _monacoFiles[_monacoCurrentFile] = _monacoEditor.getValue();
  }
  _monacoCurrentFile = path;
  _monacoFiles[path] = content;

  var existingTab = state.openTabs.find(function(t) { return t.path === path; });
  if (existingTab) {
    existingTab.modified = false;
    editorService.switchTo(path);
  } else {
    state.openTabs.push({ path: path, name: monoName, modified: false, _isMonaco: true });
    addTab(path, monoName);
    editorService.switchTo(path);
  }

  if (!_monacoEditor) {
    document.getElementById('monacoEditorWrap').innerHTML = '';
    _initMonaco(document.getElementById('monacoEditorWrap'), content, path);
  } else {
    _loadMonacoFile(path);
  }
  // 标记为源码文件，保存时使用源码 API
  _monacoSrcFile = path;
  showToast('已打开: ' + monoName, 'info');
}

// 上级目录按钮
document.getElementById('srcUpBtn').addEventListener('click', async () => {
  if (!state.srcCurrentPath) return;
  const parts = state.srcCurrentPath.split('/');
  parts.pop();
  await srcLoadDir(parts.join('/'));
});

document.getElementById('srcNewFileBtn').addEventListener('click', () => {
  const dir = state.srcCurrentPath || '';
  if (!dir) { showToast('禁止在根目录创建文件，请先进入子目录', 'error'); return; }
  showModal('新建文件', 'filename.md', async (name) => {
    if (!name) return;
    const path = dir + '/' + name;
    const res = await client.putFile(path, '');
    if (res.code === 0) {
      showToast('已创建: ' + name, 'success');
      await srcLoadDir(dir);
    } else {
      showToast('创建失败', 'error');
    }
  });
});

// 源码浏览器递归搜索
let srcSearchTimer = null;
document.getElementById('srcFilterInput').addEventListener('input', (e) => {
  clearTimeout(srcSearchTimer);
  const query = e.target.value.trim();

  if (!query) {
    // 清空搜索时恢复当前目录
    srcLoadDir(state.srcCurrentPath || '');
    return;
  }

  srcSearchTimer = setTimeout(async () => {
    const subdir = state.srcCurrentPath || '';
    const res = await client.search(query, subdir);
    if (res.code === 0 && res.data) {
      const listEl = document.getElementById('srcDirList');
      listEl.innerHTML = '';
      const entries = Array.isArray(res.data) ? res.data : [];
      if (!entries.length) {
        listEl.innerHTML = '<div style="padding:12px;color:var(--fg-muted);font-size:12px">未找到结果</div>';
        return;
      }
      const sorted = sortEntries(entries);
      listEl.innerHTML = sorted.map(e => {
        const icon = e.is_dir ? '📁' : srcFileIcon(e.ext || '');
        const sizeStr = (!e.is_dir && e.size) ? srcFormatSize(e.size) : '';
        const dirClass = e.is_dir ? ' is-dir' : '';
        const activeClass = state.srcSelectedFile === e.path ? ' active' : '';
        // 显示相对路径以便区分不同目录的同名文件
        const displayPath = e.path && !e.is_dir ? `<span style="color:var(--fg-dim);font-size:10px;margin-left:6px">${escapeHtml(e.path.replace(/[^/]*$/, ''))}</span>` : '';
        return `<div class="src-entry${dirClass}${activeClass}" data-path="${escapeHtml(e.path)}" data-is-dir="${e.is_dir}" data-ext="${escapeHtml(e.ext||'')}">
          <span class="src-entry-icon">${icon}</span>
          <span class="src-entry-name">${escapeHtml(e.name)}</span>${displayPath}
          <span class="src-entry-size">${sizeStr}</span>
        </div>`;
      }).join('');

      // 绑定点击事件
      listEl.querySelectorAll('.src-entry').forEach(el => {
        el.addEventListener('click', async () => {
          const entryPath = el.dataset.path;
          const isDir = el.dataset.isDir === 'true';
          if (isDir) {
            // 点击目录：清空搜索，导航到该目录
            document.getElementById('srcFilterInput').value = '';
            await srcLoadDir(entryPath);
          } else {
            state.srcSelectedFile = entryPath;
            listEl.querySelectorAll('.src-entry').forEach(e => e.classList.remove('active'));
            el.classList.add('active');
            await srcLoadFile(entryPath);
          }
        });
        el.addEventListener('contextmenu', (e) => {
          e.preventDefault();
          e.stopPropagation();
          showSrcContextMenu(e, el);
        });
      });
    }
  }, 300);
});

// 源码浏览器上传
document.getElementById('srcUploadBtn').addEventListener('click', () => {
  const dir = state.srcCurrentPath || '';
  if (!dir) { showToast('请先进入项目目录再上传', 'error'); return; }
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  input.addEventListener('change', async (e) => {
    const files = e.target.files;
    if (!files.length) return;
    showToast(`正在上传 ${files.length} 个文件...`, 'info');
    const res = await client.uploadFiles(files, dir);
    if (res.code === 0) {
      showToast(`已上传 ${files.length} 个文件`, 'success');
      await srcLoadDir(dir);
    } else {
      showToast('上传失败: ' + (res.msg || ''), 'error');
    }
  });
  input.click();
});

// ─── Recent Files Dropdown ──────────────────────────────────

document.getElementById('recentFilesBtn').addEventListener('click', (e) => {
  e.stopPropagation();
  const dd = document.getElementById('recentFilesDropdown');
  if (dd.style.display === 'none') {
    renderRecentFiles();
    dd.style.display = 'block';
  } else {
    dd.style.display = 'none';
  }
});

document.addEventListener('click', (e) => {
  const dd = document.getElementById('recentFilesDropdown');
  if (dd && !dd.contains(e.target) && e.target.id !== 'recentFilesBtn') {
    dd.style.display = 'none';
  }
});

function renderRecentFiles() {
  const dd = document.getElementById('recentFilesDropdown');
  if (!state.recentFiles.length) {
    dd.innerHTML = '<div style="padding:8px;color:var(--fg-dim);font-size:11px;text-align:center">暂无最近打开的文件</div>';
    return;
  }
  dd.innerHTML = state.recentFiles.map(f => {
    const ext = '.' + f.path.split('.').pop();
    const ago = timeAgo(f.time);
    const isOpen = state.openTabs.some(t => t.path === f.path);
    return `<div class="recent-file-item" data-path="${escapeHtml(f.path)}" style="display:flex;align-items:center;gap:6px;padding:5px 8px;cursor:pointer;border-radius:4px;font-size:11px;${isOpen ? 'background:var(--accent-bg)' : ''}" title="${escapeHtml(f.path)}">
      <span>${getFileIcon(ext)}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--fg)">${escapeHtml(f.name)}</span>
      <span style="font-size:9px;color:var(--fg-dim)">${ago}</span>
    </div>`;
  }).join('') + `<div style="border-top:1px solid var(--border);padding:4px 8px;text-align:center">
    <button id="clearRecentBtn" style="font-size:10px;color:var(--fg-dim);background:none;border:none;cursor:pointer">清除记录</button>
  </div>`;

  dd.querySelectorAll('.recent-file-item').forEach(item => {
    item.addEventListener('click', async () => {
      const path = item.dataset.path;
      await editorService.open(path);
      dd.style.display = 'none';
    });
  });

  const clearBtn = document.getElementById('clearRecentBtn');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      state.recentFiles = [];
      localStorage.removeItem('ts2_recent_files');
      renderRecentFiles();
    });
  }
}

function timeAgo(ts) {
  const diff = Date.now() - ts;
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
  return Math.floor(diff / 86400000) + '天前';
}

function renderWelcomeRecentFiles() {
  const list = document.getElementById('welcomeRecentList');
  if (!list) return;
  if (!state.recentFiles.length) {
    list.innerHTML = '<div style="color:var(--fg-dim);font-size:12px;padding:8px 4px">暂无最近打开的文件</div>';
    return;
  }
  const items = state.recentFiles.slice(0, 10);
  list.innerHTML = items.map(f => {
    const ext = '.' + f.path.split('.').pop();
    const ago = timeAgo(f.time);
    const pathDisplay = f.path.length > 50 ? '...' + f.path.slice(-47) : f.path;
    return `<div class="welcome-recent-item" data-path="${escapeHtml(f.path)}" style="display:flex;align-items:center;gap:8px;padding:6px 8px;cursor:pointer;border-radius:6px;font-size:12px;transition:background 0.15s" onmouseover="this.style.background='var(--bg-tertiary)'" onmouseout="this.style.background=''">
      <span style="font-size:14px">${getFileIcon(ext)}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--fg)">${escapeHtml(f.name)}</span>
      <span style="font-size:10px;color:var(--fg-dim);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(f.path)}">${escapeHtml(pathDisplay)}</span>
      <span style="font-size:9px;color:var(--fg-dim);white-space:nowrap">${ago}</span>
    </div>`;
  }).join('');

  list.querySelectorAll('.welcome-recent-item').forEach(item => {
    item.addEventListener('click', async () => {
      await editorService.open(item.dataset.path);
    });
  });
}

// ─── Task Sessions ──────────────────────────────────────────

/** 从 localStorage 加载已保存的任务会话列表 */
function _loadTaskSessions() {
  try {
    return JSON.parse(localStorage.getItem('ts2_task_sessions') || '{}');
  } catch(e) { return {}; }
}

function _saveTaskSessions(sessions) {
  try { localStorage.setItem('ts2_task_sessions', JSON.stringify(sessions)); } catch(e) {}
}

function renderWelcomeTaskSessions() {
  const list = document.getElementById('welcomeTaskSessionsList');
  if (!list) return;
  var sessions = _loadTaskSessions();
  var keys = Object.keys(sessions);
  if (!keys.length) {
    list.innerHTML = '<div id="welcomeTaskSessionsEmpty" style="color:var(--fg-dim);font-size:12px;padding:8px 4px">暂无保存的任务</div>';
    return;
  }
  list.innerHTML = keys.map(function(name) {
    var s = sessions[name];
    var count = (s.tabs ? s.tabs.length : 0) + (s.panes ? Object.keys(s.panes).reduce(function(a, k) { return a + (s.panes[k].tabs ? s.panes[k].tabs.length : 0); }, 0) : 0);
    var time = s.savedAt ? timeAgo(s.savedAt) : '';
    return '<div style="display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:6px;font-size:12px;transition:background 0.15s" onmouseover="this.style.background=\'var(--bg-tertiary)\'" onmouseout="this.style.background=\'\'">' +
      '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--fg);cursor:pointer" title="' + escapeHtml(name) + ' (' + count + ' 个标签页)" onclick="restoreTaskSession(\'' + escapeHtml(name) + '\')">📋 ' + escapeHtml(name) + '</span>' +
      '<span style="font-size:9px;color:var(--fg-dim);white-space:nowrap">' + count + ' 页</span>' +
      '<span style="font-size:9px;color:var(--fg-dim);white-space:nowrap">' + time + '</span>' +
      '<button onclick="deleteTaskSession(\'' + escapeHtml(name) + '\')" style="background:none;border:none;cursor:pointer;color:var(--fg-dim);font-size:12px;padding:0 2px;line-height:1" title="删除">✕</button>' +
      '</div>';
  }).join('');
}

async function promptSaveTaskSession() {
  var name = await modalPrompt('为当前任务状态命名：');
  if (!name || !name.trim()) return;
  name = name.trim();
  var hasMain = state.openTabs.some(function(t) { return !t._isSlides; });
  var panes = {};
  Object.keys(state).forEach(function(key) {
    if (key.startsWith('paneTabs_') && key !== 'paneTabs_0') {
      var pid = key.substring(9);
      var pidTabs = state[key];
      if (Array.isArray(pidTabs) && pidTabs.length) {
        var normalTabs = pidTabs.filter(function(t) { return !t._isSlides && !t._isBrowser; });
        if (normalTabs.length) {
          panes[pid] = {
            tabs: normalTabs.map(function(t) {
              var obj = { path: t.path, name: t.name };
              if (t._isPdf) {
                var pp = state['panePdfPage_' + pid];
                if (pp) {
                  obj.pdfState = {
                    pageNum: pp,
                    zoom: state['panePdfZoom_' + pid] || 1.0,
                    dualPage: state['panePdfDualPage_' + pid] || false
                  };
                }
              }
              return obj;
            }),
            activeTab: state['paneActiveTab_' + pid] || null
          };
        }
      }
    }
  });
  if (!hasMain && !Object.keys(panes).length) {
    showToast('没有打开的标签页，无法保存', 'error');
    return;
  }
  var sessions = _loadTaskSessions();
  sessions[name] = {
    tabs: state.openTabs.filter(function(t) { return !t._isSlides; }).map(function(t) {
      var obj = { path: t.path, name: t.name };
      if (t._isPdf && state.pdfViewState[t.path]) {
        obj.pdfState = state.pdfViewState[t.path];
      }
      return obj;
    }),
    activeTab: state.activeTab,
    panes: panes,
    savedAt: Date.now()
  };
  _saveTaskSessions(sessions);
  renderWelcomeTaskSessions();
  showToast('任务已保存: ' + name, 'info');
}

function restoreTaskSession(name) {
  var sessions = _loadTaskSessions();
  var session = sessions[name];
  if (!session || (!session.tabs || !session.tabs.length) && (!session.panes || !Object.keys(session.panes).length)) {
    showToast('任务数据为空', 'error');
    return;
  }
  // 先关闭所有当前分屏 pane（保留主编辑器）
  if (_splitActive) {
    var allPaneEls = document.querySelectorAll('#splitContainer > .pane[data-pane-id]:not([data-pane-id="0"])');
    allPaneEls.forEach(function(el) {
      var pid = el.getAttribute('data-pane-id');
      if (pid) closePane(pid, true);
    });
  }
  var tabs = session.tabs || [];
  var paneData = session.panes || {};
  var paneKeys = Object.keys(paneData);
  var idx = 0;
  function openNext() {
    if (idx < tabs.length) {
      var tabData = tabs[idx++];
      if (tabData.pdfState) {
        state.pdfViewState[tabData.path] = tabData.pdfState;
      }
      openFile(tabData.path).then(openNext);
      return;
    }
    // 主标签页都打开后，切换到 activeTab
    if (session.activeTab && state.openTabs.find(function(t) { return t.path === session.activeTab; })) {
      switchToTab(session.activeTab);
    }
    // 恢复分屏
    if (!paneKeys.length) {
      showToast('已恢复任务: ' + name, 'info');
      return;
    }
    // 创建所有分屏 pane
    for (var pi = 0; pi < paneKeys.length; pi++) {
      splitPane('editor', 'h');
    }
    // 等待 DOM 渲染，然后打开每个 pane 的标签
    setTimeout(function() {
      var paneEls = document.querySelectorAll('#splitContainer > .pane[data-pane-id]:not([data-pane-id="0"])');
      var totalPending = 0;
      var completedPanes = 0;
      paneEls.forEach(function(el, i) {
        if (i >= paneKeys.length) return;
        var newPid = el.getAttribute('data-pane-id');
        var data = paneData[paneKeys[i]];
        if (!data || !data.tabs || !data.tabs.length) {
          completedPanes++;
          if (completedPanes >= totalPending) showToast('已恢复任务: ' + name, 'info');
          return;
        }
        totalPending++;
        var pIdx = 0;
        function openPaneTab() {
          if (pIdx >= data.tabs.length) {
            if (data.activeTab) {
              // 切换到对应 pane 的 activeTab
              setActivePane(newPid);
              setTimeout(function() {
                editorService.switchInPane(data.activeTab, newPid);
              }, 100);
            }
            completedPanes++;
            if (completedPanes >= totalPending) showToast('已恢复任务: ' + name, 'info');
            return;
          }
          var tabData = data.tabs[pIdx++];
          if (tabData.pdfState) {
            state['panePdfPage_' + newPid] = tabData.pdfState.pageNum;
            state['panePdfZoom_' + newPid] = tabData.pdfState.zoom;
            state['panePdfDualPage_' + newPid] = tabData.pdfState.dualPage;
          }
          editorService.openInPane(tabData.path, newPid).then(openPaneTab);
        }
        openPaneTab();
      });
      if (!totalPending) showToast('已恢复任务: ' + name, 'info');
    }, 200);
  }
  openNext();
}

async function deleteTaskSession(name) {
  if (!await modalConfirm('确定删除任务 "' + name + '" ？')) return;
  var sessions = _loadTaskSessions();
  delete sessions[name];
  _saveTaskSessions(sessions);
  renderWelcomeTaskSessions();
  showToast('已删除: ' + name, 'info');
}

async function loadCourses() {
  const res = await client.getCourses();
  if (res.code === 0 && res.data) {
    state.courses = Array.isArray(res.data) ? res.data : (res.data.courses || []);
    renderCourses();
    renderWelcomeCourses();
  } else {
    document.getElementById('coursesPanel').innerHTML = '<div class="empty-state"><span class="empty-icon">📚</span><span>暂无课程</span></div>';
    renderWelcomeCourses();
  }
}

var _welcomeCoursesExpanded = false;
var _welcomePendingExpanded = false;

function toggleWelcomePending() {
  _welcomePendingExpanded = !_welcomePendingExpanded;
  renderPushDashboard();
}

function toggleWelcomeCourses() {
  _welcomeCoursesExpanded = !_welcomeCoursesExpanded;
  renderWelcomeCourses();
}

function renderWelcomeCourses() {
  const el = document.getElementById('welcomeCoursesList');
  if (!el) return;
  if (!state.courses.length) {
    el.innerHTML = '<div style="color:var(--fg-dim);font-size:12px">暂无课程，点击右上角「管理课程」创建</div>';
    return;
  }

  // 课表提供排序，所有课程都展示
  var allCourses = _getTimetableSortedAllCourses();
  // 默认显示 9 门
  var showCount = _welcomeCoursesExpanded ? allCourses.length : Math.min(9, allCourses.length);
  var displayCourses = allCourses.slice(0, showCount);
  var hasMore = allCourses.length > 9;

  el.innerHTML = displayCourses.map(c => {
    const id = c.note_id || c.id || c._id || c.filename || '';
    const title = c.course_title || c.title || c.name || '未命名';
    const progress = c.lessons ? c.lessons.filter(l => l.completed).length + '/' + c.lessons.length : '';
    return `<div onclick="welcomeJumpToCourse('${escapeHtml(id)}')" style="padding:8px 12px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;cursor:pointer;min-width:120px;max-width:200px;transition:border-color 0.15s" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">
      <div style="font-size:12px;font-weight:600;color:var(--fg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(title)}</div>
      ${progress ? `<div style="font-size:10px;color:var(--fg-dim);margin-top:2px">📖 ${progress}</div>` : ''}
    </div>`;
  }).join('') + (hasMore ? `<div onclick="toggleWelcomeCourses()" style="padding:6px 12px;background:var(--bg-tertiary);border:1px dashed var(--border);border-radius:8px;cursor:pointer;font-size:11px;color:var(--fg-muted);text-align:center;min-width:120px;transition:background 0.15s" onmouseover="this.style.background='var(--bg-secondary)'" onmouseout="this.style.background='var(--bg-tertiary)'">${_welcomeCoursesExpanded ? '▲ 收起' : '📋 展开更多 (' + (allCourses.length - 9) + ')'}</div>` : '');
}

function _getTimetableSortedAllCourses() {
  if (!state.courses.length) return [];
  // 从课表获取离当前时间最近的课程名排序
  var sortedNames = _getTimetableCourseNames();
  // 有排序时：按序排列，不在课表中的原样追加在后面
  if (sortedNames.length) {
    var seen = {};
    var ordered = [];
    // 先按课表顺序排
    for (var i = 0; i < sortedNames.length; i++) {
      for (var j = 0; j < state.courses.length; j++) {
        var c = state.courses[j];
        var cTitle = c.course_title || c.title || c.name || '';
        if (cTitle === sortedNames[i] || cTitle.indexOf(sortedNames[i]) !== -1 || sortedNames[i].indexOf(cTitle) !== -1) {
          var key = c.note_id || c.id || c._id || c.filename || cTitle;
          if (!seen[key]) { seen[key] = true; ordered.push(c); }
          break;
        }
      }
    }
    // 再追加不在课表中的其余课程
    for (var j = 0; j < state.courses.length; j++) {
      var c = state.courses[j];
      var cTitle = c.course_title || c.title || c.name || '';
      var key = c.note_id || c.id || c._id || c.filename || cTitle;
      if (!seen[key]) { seen[key] = true; ordered.push(c); }
    }
    return ordered;
  }
  // 无课表数据时按原有顺序
  return state.courses;
}

function _getTimetableCourseNames() {
  var tts = state.timetables;
  if (!tts) return [];
  var activeTT = null;
  for (var tid in tts) { if (tts[tid].enabled) { activeTT = tts[tid]; break; } }
  if (!activeTT || !activeTT.slots || !activeTT.slots.length) return [];

  var now = new Date();
  var todayDow = now.getDay() === 0 ? 7 : now.getDay();
  var curTime = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2);

  // 计算每个slot的优先级分：越接近当前时间的分数越低（排前面）
  var scored = activeTT.slots.map(function(s) {
    var dayDiff = s.day_of_week - todayDow;
    if (dayDiff < 0) dayDiff += 7;
    var timeScore = 0;
    if (dayDiff === 0) {
      var slotMinutes = parseInt(s.start_time.split(':')[0]) * 60 + parseInt(s.start_time.split(':')[1]);
      var curMinutes = now.getHours() * 60 + now.getMinutes();
      if (curTime >= s.start_time && curTime < s.end_time) {
        timeScore = -1;
      } else if (slotMinutes > curMinutes) {
        timeScore = slotMinutes - curMinutes;
      } else {
        timeScore = 10080 + (curMinutes - slotMinutes);
      }
    }
    var totalScore = dayDiff * 1440 + timeScore;
    return { slot: s, score: totalScore };
  });

  scored.sort(function(a, b) { return a.score - b.score; });

  // 去重返回课程名
  var seen = {};
  var result = [];
  for (var i = 0; i < scored.length; i++) {
    var name = scored[i].slot.course_name || '';
    if (!name || seen[name]) continue;
    seen[name] = true;
    result.push(name);
  }
  return result;
}

function welcomeJumpToCourse(courseId) {
  switchNavTab('courses');
  setTimeout(function() {
    // 展开课程详情
    if (state.expandedCourse !== courseId) {
      state.expandedCourse = courseId;
      loadCourseDetails(courseId);
      renderCourses();
    }
    // 选中执行模式的课程下拉
    var execSelect = document.getElementById('execCourseSelect');
    if (execSelect) {
      execSelect.value = courseId;
      if (execSelect.value === courseId) {
        state.execCourseId = courseId;
        populateExecLessonSelect(courseId);
      }
    }
    // 滚动到执行模式区域
    var execPanel = document.getElementById('executionPanel');
    if (execPanel) execPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 150);
}

// ─── 课程表实时检测 ──────────────────────────────────

var _timetableCheckTimer = null;
var _lastFlashedCourse = null;

async function _loadTimetables() {
  try {
    var res = await fetch(API_BASE + '/api/data/timetable');
    var data = await res.json();
    if (data.code !== 0 || !data.data) return null;
    state.timetables = data.data;
    renderTimetableUI();
    renderWelcomeCourses();
    return state.timetables;
  } catch(e) { return null; }
}

function renderTimetableUI() {
  var sel = document.getElementById('welcomeTtSelector');
  var status = document.getElementById('welcomeTtStatus');
  if (!sel || !status) return;
  var tts = state.timetables || {};
  var list = Object.values(tts);
  if (!list.length) {
    sel.style.display = 'none';
    status.style.display = 'none';
    return;
  }
  sel.innerHTML = list.map(function(tt) {
    return '<option value="' + tt.timetable_id + '"' + (tt.enabled ? ' selected' : '') + '>' + escapeHtml(tt.name || '未命名') + '</option>';
  }).join('');
  sel.style.display = 'inline-block';
  var activeTT = null;
  for (var tid in tts) { if (tts[tid].enabled) { activeTT = tts[tid]; break; } }
  if (activeTT) {
    status.textContent = '📅 ' + activeTT.name;
    status.style.display = 'inline';
  } else {
    status.textContent = '📅 未启用课表';
    status.style.display = 'inline';
  }
}

async function switchTimetable(timetableId) {
  if (!timetableId) return;
  await client.api('/api/data/timetable/setActive', { timetable_id: timetableId });
  await _loadTimetables();
  _lastFlashedCourse = null;
  _checkCurrentTimetableSlot();
}

async function _checkCurrentTimetableSlot() {
  var tts = state.timetables;
  if (!tts) { tts = await _loadTimetables(); }
  if (!tts) { console.log('TT debug: no timetables loaded'); return; }
  var activeTT = null;
  for (var tid in tts) {
    if (tts[tid].enabled) { activeTT = tts[tid]; break; }
  }
  if (!activeTT || !activeTT.slots || !activeTT.slots.length) {
    console.log('TT debug: no active timetable or empty slots');
    return;
  }
  console.log('TT debug: active timetable =', activeTT.name);

  var now = new Date();
  var dayOfWeek = now.getDay() === 0 ? 7 : now.getDay();
  var curTime = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2);
  console.log('TT debug: day=' + dayOfWeek + ' time=' + curTime);

  var matchingSlot = null;
  for (var i = 0; i < activeTT.slots.length; i++) {
    var s = activeTT.slots[i];
    if (s.day_of_week !== dayOfWeek) continue;
    if (curTime >= s.start_time && curTime < s.end_time) {
      matchingSlot = s;
      console.log('TT debug: matched slot', s.course_name, s.start_time, '-', s.end_time);
      break;
    }
  }
  if (!matchingSlot) {
    console.log('TT debug: no matching slot for current time');
    if (_lastFlashedCourse) {
      var oldEl = document.querySelector('#welcomeCoursesList [data-course-name]');
      if (oldEl) oldEl.classList.remove('course-flash');
      _lastFlashedCourse = null;
    }
    return;
  }

  var courseName = matchingSlot.course_name || '';
  if (!courseName) return;
  if (courseName === _lastFlashedCourse) return;

  if (_lastFlashedCourse) {
    var prevEl = document.querySelector('#welcomeCoursesList [data-course-name]');
    if (prevEl) prevEl.classList.remove('course-flash');
  }

  var cards = document.querySelectorAll('#welcomeCoursesList > div');
  var found = false;
  for (var j = 0; j < cards.length; j++) {
    var textEl = cards[j].querySelector('div:first-child');
    if (!textEl) continue;
    var cardTitle = textEl.textContent.trim();
    if (cardTitle === courseName || cardTitle.indexOf(courseName) !== -1 || courseName.indexOf(cardTitle) !== -1) {
      cards[j].setAttribute('data-course-name', courseName);
      cards[j].classList.remove('course-flash');
      void cards[j].offsetWidth;
      cards[j].classList.add('course-flash');
      _lastFlashedCourse = courseName;
      found = true;
      console.log('TT debug: flashing course', courseName);
      break;
    }
  }
  if (!found) console.log('TT debug: course "' + courseName + '" not found in welcome cards');
}

function _startTimetableCheck() {
  if (_timetableCheckTimer) clearInterval(_timetableCheckTimer);
  _loadTimetables().then(function() {
    setTimeout(_checkCurrentTimetableSlot, 3000);
  });
  _timetableCheckTimer = setInterval(_checkCurrentTimetableSlot, 60000);
}

// ─── 推送面板 ──────────────────────────────────────────

async function loadPushDashboard() {
  const res = await client.getPushDashboard();
  if (res.code === 0 && res.data) {
    state.pushDashboard = res.data;
    renderPushDashboard();
    refreshCalendarBoard();
  }
}

function renderPushDashboard() {
  const panel = document.getElementById('welcomePushContent');
  if (!panel || !state.pushDashboard) return;

  const data = state.pushDashboard;
  const overdue = data.overdue_tasks || [];
  const due = data.due_tasks || [];
  const inProgress = data.in_progress_tasks || [];
  const pending = data.pending_tasks || [];
  const reviews = data.due_reviews || [];
  const resources = data.recent_resources || [];

  if (overdue.length === 0 && due.length === 0 && inProgress.length === 0 && pending.length === 0 && reviews.length === 0 && resources.length === 0) {
    panel.innerHTML = '<div style="color:var(--fg-dim);font-size:12px;padding:8px 4px">暂无待办事项</div>';
    return;
  }
  let html = '';

  // 超期任务
  if (overdue.length > 0) {
    html += `<div class="push-section push-urgent">
      <div class="push-section-title">⚠️ 超期任务 (${overdue.length})</div>
      ${overdue.slice(0, 5).map(t => `
        <div class="push-item push-item-overdue" onclick="switchNavTab('tasks')">
          <span class="push-item-title">${escapeHtml(t.title)}</span>
          <span class="push-item-meta">超期${t.overdue_days}天</span>
        </div>
      `).join('')}
    </div>`;
  }

  // 近期截止（今日或3天内）
  if (due.length > 0) {
    html += `<div class="push-section push-warning">
      <div class="push-section-title">📅 近期截止 (${due.length})</div>
      ${due.slice(0, 10).map(t => `
        <div class="push-item" onclick="switchNavTab('tasks')">
          <span class="push-item-title">${escapeHtml(t.title)}</span>
          <span class="push-item-meta">${t.due_date}</span>
        </div>
      `).join('')}
    </div>`;
  }

  // 进行中任务
  if (inProgress.length > 0) {
    html += `<div class="push-section push-info">
      <div class="push-section-title">▶️ 进行中 (${inProgress.length})</div>
      ${inProgress.map(t => `
        <div class="push-item" onclick="switchNavTab('tasks')">
          <span class="push-item-title">${escapeHtml(t.title)}</span>
          <span class="push-item-meta">${t.due_date || '无截止日'}</span>
        </div>
      `).join('')}
    </div>`;
  }

  // 待复习
  if (reviews.length > 0) {
    html += `<div class="push-section push-info">
      <div class="push-section-title">🔄 待复习 (${reviews.length})</div>
      ${reviews.slice(0, 5).map(r => `
        <div class="push-item" onclick="switchNavTab('courses')">
          <span class="push-item-title">${escapeHtml(r.lesson_title)}</span>
          <span class="push-item-meta">${escapeHtml(r.course_title)}</span>
        </div>
      `).join('')}
    </div>`;
  }

  // 其他待办任务（默认收起）
  if (pending.length > 0) {
    var showPending = _welcomePendingExpanded ? pending : [];
    html += `<div class="push-section">
      <div class="push-section-title" onclick="toggleWelcomePending()" style="cursor:pointer;user-select:none">📋 待办任务 (${pending.length}) ${_welcomePendingExpanded ? '▲' : '▼'}</div>
      ${showPending.map(t => `
        <div class="push-item" onclick="switchNavTab('tasks')">
          <span class="push-item-title">${escapeHtml(t.title)}</span>
          <span class="push-item-meta">${t.due_date ? t.due_date : '无截止日'}</span>
        </div>
      `).join('')}
    </div>`;
  }

  // 最近资源
  if (resources.length > 0) {
    html += `<div class="push-section">
      <div class="push-section-title">📎 最近资源</div>
      ${resources.slice(0, 3).map(r => `
        <div class="push-item" onclick="switchNavTab('courses')">
          <span class="push-item-title">${escapeHtml(r.label || r.type || '资源')}</span>
        </div>
      `).join('')}
    </div>`;
  }

  panel.innerHTML = html;
}

function togglePushPanel() {
  state.pushVisible = !state.pushVisible;
  const wrapper = document.getElementById('welcomePushPanel');
  if (wrapper) wrapper.style.display = state.pushVisible ? '' : 'none';
  // 同时更新最近文件列的宽度
  const recentCol = document.getElementById('welcomeRecentFiles');
  if (recentCol) recentCol.style.flex = state.pushVisible ? '1' : '1';
}

function onCourseSearch(val) {
  state.courseSearchQuery = val.trim().toLowerCase();
  renderCourses();
}

function renderCourses() {
  const panel = document.getElementById('coursesList');

  if (!state.courses.length) {
    panel.innerHTML = '<div class="empty-state"><span class="empty-icon">📚</span><span>暂无课程</span></div>';
    return;
  }

  var filtered = state.courses;
  if (state.courseSearchQuery) {
    filtered = state.courses.filter(function(c) {
      var title = (c.course_title || c.title || c.name || '').toLowerCase();
      var domain = (c.domain || '').toLowerCase();
      return title.indexOf(state.courseSearchQuery) !== -1 || domain.indexOf(state.courseSearchQuery) !== -1;
    });
  }

  panel.innerHTML = filtered.map(course => {
    const courseId = course.note_id || course.id || course._id || course.filename || '';
    const title = course.course_title || course.title || course.name || '未命名课程';
    const totalHours = course.total_hours || 0;
    const domain = course.domain || '';
    const lessons = course.lessons || [];
    const isExpanded = state.expandedCourse === courseId;
    const progress = state.courseProgress[courseId];
    const completedCount = progress ? Object.values(progress.lessons || progress).filter(v => v === true || v === 'true').length : 0;
    const totalCount = lessons.length;
    const progressPct = totalCount > 0 ? Math.round(completedCount / totalCount * 100) : 0;
    const dueReviews = state.courseDueReviews[courseId] || [];
    const resources = state.courseResources[courseId] || [];

    return `
      <div class="course-card ${isExpanded ? 'expanded' : ''}" data-course-id="${courseId}" onclick="execJumpToCourse('${escapeHtml(courseId)}', event)">
        <div class="course-header">
          <span class="course-title">${escapeHtml(title)}</span>
          <span class="course-hours">⏱ ${totalHours}h</span>
          ${domain ? `<span class="course-domain-tag">${escapeHtml(domain)}</span>` : ''}
          ${dueReviews.length ? `<span class="course-review-badge" data-course-id="${courseId}" title="${dueReviews.length} 个待复习">🔄 ${dueReviews.length}</span>` : ''}
        </div>
        <div class="course-progress">
          <div class="course-progress-fill" style="width:${progressPct}%"></div>
        </div>
        <div class="course-progress-text">${completedCount}/${totalCount} 课时完成 (${progressPct}%)</div>
        <div class="course-actions">
          <button class="course-action-btn" onclick="toggleCourseExpand('${escapeHtml(courseId)}')">${isExpanded ? '收起' : '展开'}</button>
          <button class="course-action-btn note-btn" onclick="openCourseNote('${escapeHtml(courseId)}')">📓 笔记</button>
          <button class="course-action-btn resource-btn" onclick="showCourseResources('${escapeHtml(courseId)}')">📎 资源(${resources.length})</button>
          <button class="course-action-btn" onclick="openNotesFolder('${escapeHtml(courseId)}')">📂 文件夹</button>
          <button class="course-action-btn" onclick="editCourse('${escapeHtml(courseId)}')">✏️ 编辑</button>
          <button class="course-action-btn" onclick="addLessonToCourse('${escapeHtml(courseId)}')" style="font-size:10px">📖 +课时</button>
          <button class="course-action-btn" onclick="reorderLessons('${escapeHtml(courseId)}')" style="font-size:10px">↻ 重排</button>
          <button class="course-action-btn danger" onclick="deleteCourse('${escapeHtml(courseId)}')">删除</button>
        </div>
        <div class="lessons-timeline" id="lessons-${courseId}">
          ${dueReviews.length ? `
            <div style="padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:6px">
              <div style="font-size:11px;color:#f59e0b;font-weight:600">🔄 待复习 (${dueReviews.length})</div>
              ${dueReviews.slice(0, 5).map(r => {
                const lesson = lessons.find(l => (l.lesson_number || l.number) === r.lesson_number);
                const lTitle = lesson ? (lesson.lesson_title || lesson.title || '') : `课时 ${r.lesson_number}`;
                return `<div style="font-size:11px;color:var(--fg-muted);padding:2px 0">• ${escapeHtml(lTitle)} <span style="color:#f59e0b">超期${r.overdue_days}天</span>
                  <button class="course-action-btn" style="font-size:9px;padding:0 4px" onclick="markReviewDone('${escapeHtml(courseId)}', ${r.lesson_number})">已复习</button></div>`;
              }).join('')}
            </div>
          ` : ''}
          ${lessons.map((lesson, idx) => {
            const lNum = lesson.lesson_number || lesson.number || (idx + 1);
            const lTitle = lesson.lesson_title || lesson.title || '未命名课时';
            const lQuestion = lesson.central_question || '';
            const lHours = lesson.estimated_hours || 0;
            const isCompleted = progress && (progress.lessons || progress)[lNum];
            const lessonRes = resources.filter(r => r.lesson_number == lNum);
            return `
              <div class="lesson-item">
                <div class="lesson-number ${isCompleted ? 'completed' : ''}">${lNum}</div>
                <div class="lesson-info">
                  <div class="lesson-title">${escapeHtml(lTitle)}</div>
                  ${lQuestion ? `<div class="lesson-question">❓ ${escapeHtml(lQuestion)}</div>` : ''}
                  <div class="lesson-hours">⏱ ${lHours}h</div>
                  <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px">
                    <button class="course-action-btn note-btn" style="font-size:9px;padding:0 6px" onclick="openLessonNote('${escapeHtml(courseId)}', ${lNum})">📝 笔记</button>
                    <button class="course-action-btn resource-btn" style="font-size:9px;padding:0 6px" onclick="showCourseResources('${escapeHtml(courseId)}', ${lNum})">📎</button>
                    <button class="course-action-btn" style="font-size:9px;padding:0 4px" onclick="editLesson('${escapeHtml(courseId)}', ${lNum})">✏️</button>
                    <button class="course-action-btn" style="font-size:9px;padding:0 4px;color:var(--red)" onclick="deleteLessonConfirm('${escapeHtml(courseId)}', ${lNum}, '${lTitle.replace(/'/g, "\\'").replace(/\\/g, "\\\\")}')">🗑️</button>
                    ${lessonRes.length ? lessonRes.map(r =>
                      `<span class="lesson-resource-link" onclick="openResource('${escapeHtml(r.type)}', '${escapeHtml(r.path || r.url || '')}')">${escapeHtml(r.label || r.type)}</span>`
                    ).join('') : ''}
                  </div>
                </div>
                <div class="lesson-check">
                  <input type="checkbox" ${isCompleted ? 'checked' : ''} data-course-id="${courseId}" data-lesson-num="${lNum}" title="标记完成">
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }).join('');

  // Bind lesson checkboxes
  panel.querySelectorAll('.lesson-check input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', async (e) => {
      e.stopPropagation();
      const courseId = cb.dataset.courseId;
      const lessonNum = parseInt(cb.dataset.lessonNum);
      const completed = cb.checked;
      const res = await client.updateLessonStatus(courseId, lessonNum, completed ? 'completed' : 'not_started');
      if (res.code === 0) {
        if (!state.courseProgress[courseId]) state.courseProgress[courseId] = { lessons: {} };
        if (!state.courseProgress[courseId].lessons) state.courseProgress[courseId].lessons = {};
        state.courseProgress[courseId].lessons[lessonNum] = completed;
        showToast(completed ? '课时已完成' : '课时标记未完成', 'success');
        // 完成课时时触发复习调度
        if (completed) {
          await client.api('/api/data/courses/updateReview', { course_id: courseId, lesson_number: lessonNum, status: 5 });
        }
        renderCourses();
      } else {
        cb.checked = !completed;
        showToast('更新失败: ' + (res.msg || ''), 'error');
      }
    });
  });
}

function toggleCourseExpand(courseId) {
  if (state.expandedCourse === courseId) {
    state.expandedCourse = null;
  } else {
    state.expandedCourse = courseId;
    loadCourseDetails(courseId);
  }
  renderCourses();
}

function execJumpToCourse(courseId, event) {
  if (event && event.target.closest('button, a, input, select, .lesson-check, .course-action-btn, .lesson-number')) return;
  var select = document.getElementById('execCourseSelect');
  if (!select) return;
  select.value = courseId;
  state.execCourseId = courseId;
  select.dispatchEvent(new Event('change'));
  var execPanel = document.getElementById('executionPanel');
  if (execPanel) execPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadCourseDetails(courseId) {
  // 加载进度
  if (!state.courseProgress[courseId]) {
    const res = await client.getCourseProgress(courseId);
    if (res.code === 0 && res.data) {
      state.courseProgress[courseId] = res.data;
    }
  }
  // 加载复习
  const reviewRes = await client.api('/api/data/courses/review/due', { course_id: courseId });
  if (reviewRes.code === 0) {
    state.courseDueReviews[courseId] = reviewRes.data || [];
  }
  // 加载资源
  const resRes = await client.api_get(`/api/data/resources/${courseId}`);
  if (resRes.code === 0) {
    state.courseResources[courseId] = resRes.data || [];
  }
  renderCourses();
}

async function markReviewDone(courseId, lessonNumber) {
  await client.api('/api/data/courses/review/done', { course_id: courseId, lesson_number: lessonNumber });
  showToast('复习已标记完成', 'success');
  await loadCourseDetails(courseId);
}

async function deleteCourse(courseId) {
  if (!await modalConfirm('确定删除此课程？此操作不可撤销。')) return;
  const res = await client.api('/api/data/courses/delete', { course_id: courseId });
  if (res.code === 0) {
    showToast('课程已删除', 'success');
    await loadCourses();
  } else {
    showToast('删除失败: ' + (res.msg || ''), 'error');
  }
}

function openResource(type, path) {
  if (!path) { showToast('资源路径为空', 'error'); return; }
  if (type === 'pdf') {
    openPdf(path);
  } else if (type === 'url') {
    window.open(path, '_blank');
  } else if (type === 'video') {
    window.open(path, '_blank');
  } else {
    // 尝试作为文件打开
    editorService.open(path);
  }
}

// ─── 课程资源管理（仿 course_tracker.py ResourceMgr）──────────

async function getCourseResources(courseId) {
  const res = await client.api_get(`/api/data/resources/${courseId}`);
  return (res.code === 0 && res.data) ? res.data : [];
}

async function addCourseResource(courseId, entry) {
  const res = await client.api('/api/data/resources/add', { course_key: courseId, entry });
  return res.code === 0;
}

async function removeCourseResource(courseId, entry) {
  const res = await client.api('/api/data/resources/remove', { course_key: courseId, entry });
  return res.code === 0;
}

async function showCourseResources(courseId, filterLessonNumber) {
  _currentResourceFilterLesson = filterLessonNumber != null ? filterLessonNumber : null;
  const resources = await getCourseResources(courseId);
  const course = state.courses.find(c => (c.note_id || c.id || c._id || c.filename || '') === courseId);
  const lessons = (course && course.lessons) || [];
  const courseTitle = course ? (course.course_title || course.title || '') : '';

  // 按课时分组
  const courseLevel = resources.filter(r => !r.lesson_number);
  const lessonMap = {};
  lessons.forEach(l => { lessonMap[l.lesson_number || 0] = []; });
  resources.forEach(r => {
    const ln = r.lesson_number;
    if (ln != null) {
      if (!lessonMap[ln]) lessonMap[ln] = [];
      lessonMap[ln].push(r);
    }
  });

  const ICONS = { pdf: '📄', url: '🌐', video: '🎬', image: '🖼️', note: '📝', code: '💻' };

  let html = `<div style="display:flex;flex-direction:column;gap:6px;max-height:65vh;overflow-y:auto">`;

  // 操作栏
  html += `<div style="display:flex;gap:4px;flex-wrap:wrap;padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:6px">
    <button class="course-action-btn" onclick="addCourseFileResource('${courseId}'${filterLessonNumber ? ', ' + filterLessonNumber : ''})">📂 添加文件</button>
    <button class="course-action-btn" onclick="addCourseUrlResource('${courseId}'${filterLessonNumber ? ', ' + filterLessonNumber : ''})">🔖 添加URL</button>
    ${filterLessonNumber ? `<span style="font-size:10px;color:var(--accent);padding:0 4px">→ L${filterLessonNumber}</span>` : ''}
    <span style="flex:1"></span>
    <button class="course-action-btn" onclick="addCourseResourceFromTree('${courseId}')">📋 从文件树添加</button>
  </div>`;

  // 课程级资源（仅在不按课时过滤时显示）
  if (!filterLessonNumber && courseLevel.length) {
    html += `<div class="resource-modal-section"><div style="font-weight:600;padding:2px 0;color:var(--fg);font-size:12px">📁 课程级资源</div>`;
    courseLevel.forEach(r => {
      html += renderResourceModalRow(r, ICONS[r.type] || '📎', r.label || r.path || r.url || '', courseId);
    });
    html += `</div>`;
    html += `<hr style="border-color:var(--border-light);margin:2px 0">`;
  }

  // 课时级资源
  if (lessons.length) {
    lessons.forEach(lesson => {
      const lnum = lesson.lesson_number || 0;
      // 若指定了课时过滤，跳过其他课时
      if (filterLessonNumber && lnum !== filterLessonNumber) return;
      const lresources = lessonMap[lnum] || [];
      const ltitle = lesson.lesson_title || '';
      html += `<div class="resource-modal-section">`;
      html += `<div style="font-weight:600;padding:2px 0;color:var(--accent);font-size:12px">📖 课时 ${lnum}: ${escapeHtml(ltitle)}</div>`;
      if (lresources.length) {
        lresources.forEach(r => {
          html += renderResourceModalRow(r, ICONS[r.type] || '📎', r.label || r.path || r.url || '', courseId);
        });
      } else {
        html += `<div style="font-size:11px;color:var(--fg-muted);padding:2px 8px">暂无资源</div>`;
      }
      html += `<div style="display:flex;gap:4px;padding:4px 8px">
        <button class="course-action-btn" onclick="addCourseFileResource('${courseId}', ${lnum})" style="font-size:10px;padding:2px 6px">📂 添加文件</button>
        <button class="course-action-btn" onclick="addCourseUrlResource('${courseId}', ${lnum})" style="font-size:10px;padding:2px 6px">🔖 添加URL</button>
      </div>`;
      html += `</div>`;
    });
  }

  // 没有课时的空白课程
  if (!resources.length && !lessons.length) {
    html += `<div style="text-align:center;padding:30px;color:var(--fg-muted)">暂无资源，点击上方按钮添加</div>`;
  }

  html += `</div>`;

  showHtmlModal(`📎 课程资源 · ${escapeHtml(courseTitle)}`, html);
}

let _currentResourceFilterLesson = null;

function renderResourceModalRow(r, icon, label, courseId) {
  const rEnc = encodeURIComponent(JSON.stringify(r));
  let openBtn = '';
  if (r.type === 'pdf' && r.path) {
    openBtn = `<span class="resource-modal-action" onclick="event.stopPropagation();openPdf('${r.path.replace(/'/g, "\\'")}')" title="打开PDF">📂</span>`;
  } else if (r.type === 'url' && r.url) {
    openBtn = `<span class="resource-modal-action" onclick="event.stopPropagation();window.open('${r.url.replace(/'/g, "\\'")}','_blank')" title="打开链接">🌐</span>`;
  } else if (r.path) {
    openBtn = `<span class="resource-modal-action" onclick="event.stopPropagation();editorService.open('${r.path.replace(/'/g, "\\'")}')" title="打开">📂</span>`;
  }
  return `<div class="resource-modal-row">
    <span class="resource-modal-icon">${icon}</span>
    <span class="resource-modal-label">${escapeHtml(label)}</span>
    <span class="resource-modal-actions">
      ${openBtn}
      <span class="resource-modal-action" style="color:var(--red)" onclick="event.stopPropagation();removeCourseResourceConfirm('${courseId}','${rEnc}')" title="删除">🗑️</span>
    </span>
  </div>`;
}

async function removeCourseResourceConfirm(courseId, encodedResource) {
  if (!await modalConfirm('确定删除此资源？')) return;
  const resource = JSON.parse(decodeURIComponent(encodedResource));
  const ok = await removeCourseResource(courseId, resource);
  if (ok) {
    showToast('资源已删除', 'success');
    showCourseResources(courseId, _currentResourceFilterLesson);
    loadCourseDetails(courseId);
  } else {
    showToast('删除失败', 'error');
  }
}

async function addCourseFileResource(courseId, lessonNumber) {
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  input.onchange = async () => {
    if (!input.files.length) return;
    const res = await client.uploadFiles(input.files, 'Notes');
    if (res.code === 0) {
      const uploaded = res.data || [];
      let count = 0;
      for (const f of uploaded) {
        const path = f.path || f.name || '';
        const name = path.split('/').pop() || 'file';
        const entry = {
          type: 'pdf',
          label: `📄 ${name}`,
          path: 'Notes/' + path
        };
        if (lessonNumber != null) entry.lesson_number = lessonNumber;
        const ok = await addCourseResource(courseId, entry);
        if (ok) count++;
      }
      showToast(`已添加 ${count}/${uploaded.length} 个文件`, 'success');
      if (document.getElementById('modalOverlay').classList.contains('show')) showCourseResources(courseId, _currentResourceFilterLesson);
      loadCourseDetails(courseId);
    } else {
      showToast('上传失败: ' + (res.msg || ''), 'error');
    }
  };
  input.click();
}

async function addCourseUrlResource(courseId, lessonNumber) {
  const url = await modalPrompt('输入资源URL:');
  if (!url) return;
  const label = await modalPrompt('标签 (可选):') || url;
  const entry = {
    type: 'url',
    label: `🌐 ${label}`,
    url: url
  };
  if (lessonNumber != null) entry.lesson_number = lessonNumber;
  const ok = await addCourseResource(courseId, entry);
  if (ok) {
    showToast('URL已添加', 'success');
    if (document.getElementById('modalOverlay').classList.contains('show')) showCourseResources(courseId, _currentResourceFilterLesson);
    loadCourseDetails(courseId);
  } else {
    showToast('添加失败', 'error');
  }
}

async function addCourseResourceFromTree(courseId) {
  closeHtmlModal();
  showToast('请在文件树中选择文件，右键选择"添加为课程资源"', 'info');
  // 标记当前课程以便文件树右键菜单使用
  state._pendingResourceCourse = courseId;
}

// ─── 课程笔记打开跳转（仿 course_tracker.py get_or_create_note + _open_note）──

function getNotePath(course, lessonNumber) {
  const title = course.course_title || course.title || 'unknown';
  const safeTitle = title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 40);
  if (lessonNumber != null) {
    const lesson = (course.lessons || []).find(l => (l.lesson_number || l.number) === lessonNumber);
    const lTitle = lesson ? (lesson.lesson_title || lesson.title || '') : '';
    const safeLTitle = lTitle.replace(/[\\/:*?"<>|]/g, '_').slice(0, 30);
    const fn = lTitle
      ? `L${String(lessonNumber).padStart(2, '0')}_${safeLTitle}.Rmd`
      : `L${String(lessonNumber).padStart(2, '0')}.Rmd`;
    return `Notes/${safeTitle}/${fn}`;
  }
  return `Notes/${safeTitle}/course_notes.Rmd`;
}

function generateNoteYaml(course, lessonNumber) {
  const title = course.course_title || course.title || '课程';
  const domain = course.domain || '';
  const description = course.description || '';
  const safeTitle = title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 40);
  const now = new Date();
  const dateStr = now.toISOString().split('T')[0];
  const lesson = lessonNumber != null ? (course.lessons || []).find(l => (l.lesson_number || l.number) === lessonNumber) : null;
  const lTitle = lesson ? (lesson.lesson_title || '') : '';
  const lNum = lessonNumber != null ? lessonNumber : '';
  const lQuestion = lesson ? (lesson.central_question || '') : '';
  const esc = s => s ? s.replace(/"/g, '\\"') : '';
  const pad = n => String(n).padStart(4, '0');
  const sub = lessonNumber != null
    ? esc(domain + '/《' + title + '》课程 — 课时' + pad(lNum) + ' ' + lTitle)
    : esc(domain + '/《' + title + '》课程 — 综合笔记');
  const bs = '\\';
  const lb = '\n';
  const t = '`';

  var y = '';
  y += '---' + lb;
  y += 'title: "Lecture Notes"' + lb;
  y += 'subtitle: "' + sub + '"' + lb;
  y += 'author: "P.C."' + lb;
  y += 'date: "' + t + 'r Sys.Date()' + t + '"' + lb;
  y += 'always_allow_html: true' + lb;
  y += 'output:' + lb;
  y += '  pdf_document:' + lb;
  y += '    includes:' + lb;
  y += '      in_header: ..' + bs + '..' + bs + '..' + bs + '..' + bs + '..' + bs + '.ts2' + bs + 'template/preamble-book.tex' + lb;
  y += '    pandoc_args:' + lb;
  y += '      - --lua-filter=..' + bs + '..' + bs + '..' + bs + '..' + bs + '..' + bs + '.ts2' + bs + 'template/env_mapping.lua' + lb;
  y += '    latex_engine: xelatex' + lb;
  y += '    fig_caption: true' + lb;
  y += '    number_sections: true' + lb;
  y += '    toc: true' + lb;
  y += '    toc_depth: 3' + lb;
  y += '    md_extensions: +fenced_divs+bracketed_spans' + lb;
  y += '    keep_tex: false' + lb;
  y += '    keep_md: false' + lb;
  y += '    extra_dependencies:' + lb;
  y += '      ctex: []' + lb;
  y += '      fancyhdr: []' + lb;
  y += '      lastpage: []' + lb;
  y += '      booktabs: []' + lb;
  y += '      multirow: []' + lb;
  y += '      graphicx: []' + lb;
  y += '      amsmath: []' + lb;
  y += '      amssymb: []' + lb;
  y += '      amsthm: []' + lb;
  y += '      bm: []' + lb;
  y += '      listings: []' + lb;
  y += '      xcolor: [table]' + lb;
  y += '      hyperref: []' + lb;
  y += '      longtable: []' + lb;
  y += '      float: []' + lb;
  y += '      caption: []' + lb;
  y += '  html_document:' + lb;
  y += '    toc: true' + lb;
  y += '    toc_float: true' + lb;
  y += '    code_folding: show' + lb;
  y += '    theme: flatly' + lb;
  y += '    number_sections: true' + lb;
  y += '---' + lb + lb;

  // R setup chunk 1 — encoding + knitr options
  y += t + t + t + '{r include=FALSE}' + lb;
  y += '# Windows中文路径支持' + lb;
  y += 'if (.Platform$OS.type == "windows") {' + lb;
  y += '  options(encoding = "UTF-8")' + lb;
  y += '  Sys.setlocale("LC_ALL", "Chinese (Simplified)_China.UTF-8")' + lb;
  y += '}' + lb;
  y += 'knitr::opts_chunk$set(' + lb;
  y += '  echo       = TRUE,' + lb;
  y += '  message    = FALSE,' + lb;
  y += '  warning    = FALSE,' + lb;
  y += '  fig.width  = 8,' + lb;
  y += '  fig.height = 6,' + lb;
  y += '  fig.dpi    = 300,' + lb;
  y += '  fig.align  = "center",' + lb;
  y += '  cache      = TRUE,' + lb;
  y += '  autodep    = TRUE' + lb;
  y += ')' + lb;
  y += 'options(knitr.table.format = "latex")' + lb;
  y += 'set.seed(42)' + lb;
  y += t + t + t + lb + lb;

  // R setup chunk 2 — library loading
  y += t + t + t + '{r include=FALSE}' + lb;
  y += 'library(tidyverse)' + lb;
  y += 'library(knitr)' + lb;
  y += 'library(kableExtra)' + lb;
  y += 'library(ggplot2)' + lb;
  y += 'library(gridExtra)' + lb + lb;
  y += 'theme_set(theme_bw(base_size = 12) +' + lb;
  y += '  theme(plot.title = element_text(hjust = 0.5, face = "bold"),' + lb;
  y += '        legend.position = "bottom"))' + lb;
  y += t + t + t + lb + lb;

  if (lessonNumber != null) {
    // ─── 课时级笔记：按 KCTSW 递进组织 ───
    y += bs + 'newpage' + lb + lb;
    y += '# 课时 ' + lNum + '：' + esc(lTitle) + lb + lb;
    y += '## 中心问题' + lb + lb;
    y += '> ' + esc(lQuestion || '（待补充）') + lb + lb;
    y += '**所属章节：**' + lb + lb;
    y += '**课时简介：**' + lb + lb;
    y += bs + 'newpage' + lb + lb;

    // ─── 1. 知识（Knowledge） ───
    y += '## 1. 知识（Knowledge）' + lb + lb;
    y += '> 列出本节课所需的前置知识与基本事实。' + lb + lb;
    y += '---' + lb + lb;

    // ─── 2. 概念（Concept） ───
    y += '## 2. 概念（Concept）' + lb + lb;
    y += '> 引入核心概念，解释其内涵与边界。' + lb + lb;
    y += ':::definition' + lb;
    y += '**概念名称**' + lb + lb;
    y += '> 概念的严格表述...' + lb + lb;
    y += '*注：此定义的适用范围是...*' + lb;
    y += ':::' + lb + lb;
    y += '---' + lb + lb;

    // ─── 3. 理论（Theory） ───
    y += '## 3. 理论（Theory）' + lb + lb;
    y += '> 陈述定理、公式或理论框架。' + lb + lb;
    y += ':::theorem' + lb;
    y += '**定理名称**' + lb + lb;
    y += '> 定理的完整表述...' + lb + lb;
    y += '*证明思路：*' + lb;
    y += ':::' + lb + lb;
    y += '### 公式与推导' + lb + lb;
    y += '**基本公式：**' + lb + lb;
    y += '$$$$' + lb + lb;
    y += '**参数说明：**' + lb + lb;
    y += '| 符号  | 含义 | 单位 |' + lb;
    y += '| :---- | :--- | :--- |' + lb;
    y += '| $x$ | 变量 | -    |' + lb;
    y += '| $y$ | 结果 | -    |' + lb + lb;
    y += '**推导过程：**' + lb + lb;
    y += '$$' + lb;
    y += bs + 'begin{aligned}' + lb;
    y += '结果 &= ' + bs + 'text{起始式} ' + bs + bs + lb;
    y += '&= ' + bs + 'text{化简} ' + bs + bs + lb;
    y += '&= ' + bs + 'text{结论}' + lb;
    y += bs + 'end{aligned}' + lb;
    y += '$$' + lb + lb;
    y += ':::corollary' + lb + lb;
    y += '> 由上述定理直接推出的结论...' + lb;
    y += ':::' + lb + lb;
    y += ':::lemma' + lb + lb;
    y += '> 辅助性命题，通常用于证明主要定理...' + lb;
    y += ':::' + lb + lb;
    y += ':::remark' + lb + lb;
    y += '> 对上述内容的补充说明、注意事项或直观理解...' + lb;
    y += ':::' + lb + lb;
    y += '---' + lb + lb;

    // ─── 4. 技能（Skill） ───
    y += '## 4. 技能（Skill）' + lb + lb;
    y += '> 给出具体方法、算法或操作步骤。' + lb + lb;
    y += ':::example' + lb;
    y += '**R 演绎**' + lb + lb;
    y += t + t + t + 'sr' + lb;
    y += '# 计算有限集合的幂集大小' + lb;
    y += 'A <- c(1, 2, 3)' + lb;
    y += 'cat("|A| =", length(A), "\\n")' + lb;
    y += 'cat("|P(A)| =", 2^length(A), "\\n")' + lb;
    y += 'cat("2^|A| > |A| 对有限集成立:", 2^length(A) > length(A))' + lb;
    y += t + t + t + lb + lb;
    y += '**Python 演绎（可选）**' + lb + lb;
    y += t + t + t + 'python' + lb;
    y += '# 计算有限集合的幂集大小' + lb;
    y += 'from itertools import chain, combinations' + lb + lb;
    y += 'def powerset(iterable):' + lb;
    y += '    s = list(iterable)' + lb;
    y += '    return list(chain.from_iterable(combinations(s, r) for r in range(len(s)+1)))' + lb + lb;
    y += 'A = [1, 2, 3]' + lb;
    y += 'print(f"|A| = {len(A)}")' + lb;
    y += 'print(f"|P(A)| = {len(powerset(A))}")' + lb;
    y += 'print(f"2^|A| > |A| 对有限集成立: {2**len(A) > len(A)}")' + lb;
    y += t + t + t + lb + lb;
    y += ':::' + lb + lb;
    y += '---' + lb + lb;

    // ─── 5. 工作流（Workflow） ───
    y += '## 5. 工作流（Workflow）' + lb + lb;
    y += '> 将上述技能整合为完整的工作流，解决实际问题。' + lb + lb;
    y += ':::problem' + lb;
    y += '**题目：** 描述例题内容...' + lb + lb;
    y += ':::' + lb + lb;
    y += ':::solution' + lb + lb;
    y += '**解答：**' + lb + lb;
    y += '1. 理解题意：' + lb;
    y += '2. 确定方法：' + lb;
    y += '3. 详细计算：' + lb + lb;
    y += '   $$' + lb;
    y += '   ' + bs + 'text{关键步骤}' + lb;
    y += '   $$' + lb;
    y += '4. 验证结果：' + lb + lb;
    y += '**答案：**' + lb;
    y += ':::' + lb + lb;
    y += '---' + lb + lb;

    // ─── 深入练习题 ───
    y += '## 深入练习题' + lb + lb;
    y += ':::exercise' + lb;
    y += '**练习 1：**' + lb + lb;
    y += '> 题干描述...' + lb + lb;
    y += '*提示：*' + lb + lb;
    y += '**练习 2：**' + lb + lb;
    y += '> 题干描述...' + lb + lb;
    y += ':::' + lb + lb;
    y += '---' + lb + lb;
    y += '---' + lb + lb;

    // ─── 参考文献 ───
    y += '## 参考文献' + lb + lb;
    y += '1. [教材名称](URL)，作者，年份' + lb;
    y += '2. [论文/视频标题](URL)，作者，年份' + lb;
    y += '3. [在线资源](URL)' + lb;
  } else {
    // ─── 课程级笔记 ───
    y += '# ' + esc(title) + lb + lb;
    y += '## 课程概述' + lb + lb;
    y += esc(description) + lb + lb;
    y += '## 课时列表' + lb + lb;
    for (var i = 0; i < (course.lessons || []).length; i++) {
      var l = course.lessons[i];
      var ln = l.lesson_number || l.number || 0;
      var lt = l.lesson_title || '';
      var lq = l.central_question || '';
      y += '- **课时 ' + ln + '**: ' + esc(lt) + (lq ? ' — ' + esc(lq) : '') + lb;
    }
    // ─── KCTSW 知识图谱表格 ───
    y += lb + '## KCTSW 知识图谱' + lb + lb;
    y += '| 课时 | 知识 | 概念 | 理论 | 技能 | 工作流 |' + lb;
    y += '|:----:|:----:|:----:|:----:|:----:|:------:|' + lb;
    for (var i = 0; i < (course.lessons || []).length; i++) {
      var l = course.lessons[i];
      var ln = l.lesson_number || l.number || 0;
      y += '| ' + ln + ' | 待补充 | 待补充 | 待补充 | 待补充 | 待补充 |' + lb;
    }
    y += lb + '## 综合笔记' + lb + lb + lb + lb;
    y += '## 参考文献' + lb;
  }
  return y;
}

async function openCourseNote(courseId) {
  const course = state.courses.find(c => (c.note_id || c.id || c._id || c.filename || '') === courseId);
  if (!course) { showToast('课程未找到', 'error'); return; }
  const notePath = getNotePath(course, null);
  let res = await client.getFile(notePath);
  if (res.code !== 0 || !res.data || !res.data.content) {
    const template = generateNoteYaml(course, null);
    res = await client.putFile(notePath, template);
    if (res.code !== 0) { showToast('创建笔记失败', 'error'); return; }
    showToast('已创建课程笔记', 'success');
  }
  await editorService.open(notePath);
}

async function openLessonNote(courseId, lessonNumber) {
  const course = state.courses.find(c => (c.note_id || c.id || c._id || c.filename || '') === courseId);
  if (!course) { showToast('课程未找到', 'error'); return; }
  const notePath = getNotePath(course, lessonNumber);
  let res = await client.getFile(notePath);
  if (res.code !== 0 || !res.data || !res.data.content) {
    const template = generateNoteYaml(course, lessonNumber);
    res = await client.putFile(notePath, template);
    if (res.code !== 0) { showToast('创建笔记失败', 'error'); return; }
    showToast('已创建课时笔记', 'success');
  }
  await editorService.open(notePath);
}

async function openNotesFolder(courseId) {
  const course = state.courses.find(c => (c.note_id || c.id || c._id || c.filename || '') === courseId);
  if (!course) { showToast('课程未找到', 'error'); return; }
  const title = course.course_title || course.title || 'unknown';
  const safeTitle = title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 40);
  const folderPath = `Notes/${safeTitle}`;
  state.currentDir = folderPath;
  await refreshTree();
  if (state.activeNavTab !== 'files') switchNavTab('files');
}

// ─── 外部编辑器打开（仿 course_tracker.py _open_in_positron）──────

async function openInExternalEditor(filePath) {
  const res = await client.api('/api/system/openExternal', { path: filePath });
  if (res.code === 0) {
    showToast('已在外部编辑器中打开', 'info');
  } else {
    const url = client.getDownloadUrl(filePath);
    window.open(url, '_blank');
    showToast('文件已下载，请用本地编辑器打开', 'info');
  }
}

// ─── IDE 打开方式选择（JupyterLab / VS Code / Cursor / 内置 / 外部）────

let _pendingOpenPath = '';

function showOpenWithPicker(filePath) {
  _pendingOpenPath = filePath;
  document.getElementById('idePickerOverlay').style.display = 'flex';
}

async function openWith(ide) {
  document.getElementById('idePickerOverlay').style.display = 'none';
  document.getElementById('openWithDropdown').style.display = 'none';
  const filePath = _pendingOpenPath || state.activeTab;
  // JupyterLab 不需要特定文件路径
  if (ide !== 'jupyter' && !filePath) return;

  switch (ide) {
    case 'jupyter': {
      const jupyterPath = '__jupyter__';
      // 如果已打开 JupyterLab tab，直接切过去
      const existing = state.openTabs.find(t => t._isJupyter);
      if (existing) { editorService.switchTo(jupyterPath); break; }
      // 启动并等待就绪
      showToast('正在启动 JupyterLab...', 'info');
      let st = await client.api('/api/system/jupyterStart');
      if (st.code !== 0) { showToast(st.msg || '启动失败', 'error'); return; }
      const wait = await client.api('/api/system/jupyterWaitReady');
      if (wait.code !== 0) { showToast(wait.msg || 'JupyterLab 启动超时', 'error'); return; }
      // 创建 tab
      state.openTabs.push({ path: jupyterPath, name: 'JupyterLab', modified: false, _isJupyter: true });
      _saveSession();
      addTab(jupyterPath, 'JupyterLab');
      // 嵌入 iframe
      const wrap = document.getElementById('jupyterIframeWrap');
      wrap.innerHTML = '';
      const iframe = document.createElement('iframe');
      iframe.src = st.data.url || wait.data.url;
      iframe.style.cssText = 'width:100%;height:100%;border:none;background:var(--bg)';
      iframe.setAttribute('allow', 'clipboard-read; clipboard-write');
      wrap.appendChild(iframe);
      document.getElementById('jupyterStatus').textContent = '已就绪';
      editorService.switchTo(jupyterPath);
      showToast('JupyterLab 已就绪', 'success');
      break;
    }
    case 'monaco': {
      // 用单实例 Monaco 打开
      if (_monacoCurrentFile && _monacoEditor) {
        _monacoFiles[_monacoCurrentFile] = _monacoEditor.getValue();
      }
      const res = await client.getFile(filePath);
      if (res.code !== 0 || !res.data) { showToast('读取文件失败', 'error'); return; }
      _monacoCurrentFile = filePath;
      _monacoFiles[filePath] = res.data.content;
      const tab = state.openTabs.find(t => t.path === filePath);
      if (tab) {
        tab.modified = false;
        editorService.switchTo(filePath);
      } else {
        state.openTabs.push({ path: filePath, name: filePath.split('/').pop(), modified: false, _isMonaco: true });
        addTab(filePath, filePath.split('/').pop());
        editorService.switchTo(filePath);
      }
      if (!_monacoEditor) {
        document.getElementById('monacoEditorWrap').innerHTML = '';
        _initMonaco(document.getElementById('monacoEditorWrap'), res.data.content, filePath);
      } else {
        _loadMonacoFile(filePath);
      }
      break;
    }
    case 'builtin':
      await editorService.open(filePath);
      break;
    case 'external':
      await openInExternalEditor(filePath);
      break;
    case 'vscode': {
      const proto = 'vscode://file/' + encodeURI(filePath.replace(/\\/g, '/'));
      window.open(proto, '_blank');
      showToast('已在 VS Code 中打开', 'info');
      break;
    }
    case 'cursor': {
      const proto = 'cursor://file/' + encodeURI(filePath.replace(/\\/g, '/'));
      window.open(proto, '_blank');
      showToast('已在 Cursor 中打开', 'info');
      break;
    }
  }
}

// 点击文件树时：代码文件弹出 IDE 选择，其他按原逻辑
function shouldShowIdePicker(entry) {
  const codeExts = ['.py','.js','.ts','.jsx','.tsx','.ipynb','.r','.rmd','.cpp','.c','.h','.java','.go','.rs','.rb','.php','.swift','.kt','.scala','.sh','.bash','.zsh','.ps1','.bat','.sql','.css','.scss','.less','.vue','.svelte','.yaml','.yml','.toml','.ini','.cfg','.conf','.dockerfile','.makefile','.gradle','.sbt','.m','.mm','.pl','.pm','.lua','.hs','.clj','.cljs','.ex','.exs','.erl','.hrl'];
  if (!entry || entry.is_dir) return false;
  const ext = '.' + entry.name.split('.').pop().toLowerCase();
  return codeExts.includes(ext);
}

// 工具按钮下拉切换
document.addEventListener('click', function(e) {
  const dd = document.getElementById('openWithDropdown');
  if (dd && dd.style.display !== 'none' && !e.target.closest('.btn-group')) {
    dd.style.display = 'none';
  }
});

// ─── 课程编辑（仿 course_tracker.py _edit_course）────────────

async function editCourse(courseId) {
  const course = state.courses.find(c => (c.note_id || c.id || c._id || c.filename || '') === courseId);
  if (!course) { showToast('课程未找到', 'error'); return; }

  const title = course.course_title || '';
  const domain = course.domain || 'UNKNOWN';
  const totalHours = course.total_hours || '';
  const audience = course.target_audience || '';
  const assessment = course.assessment || '';
  const positioning = course.positioning || '';
  const prerequisites = Array.isArray(course.prerequisites) ? course.prerequisites.join(', ') : (course.prerequisites || '');
  const description = course.description || '';
  const sections = course.sections || [];
  const lessons = course.lessons || [];

  let html = `<div style="display:flex;flex-direction:column;gap:8px;max-height:70vh;overflow-y:auto;padding:4px">`;

  // ── 基本信息 ──
  html += `<div style="font-weight:600;color:var(--fg);font-size:13px;padding:4px 0">📋 基本信息</div>`;

  const fields = [
    { key: 'course_title', label: '课程名称', type: 'text', value: title, required: true },
    { key: 'domain', label: '学科域', type: 'text', value: domain },
    { key: 'total_hours', label: '总学时', type: 'text', value: totalHours },
    { key: 'target_audience', label: '授课对象', type: 'text', value: audience },
    { key: 'assessment', label: '考核方式', type: 'text', value: assessment },
    { key: 'positioning', label: '课程定位', type: 'text', value: positioning },
    { key: 'prerequisites', label: '先修课程（逗号分隔）', type: 'text', value: prerequisites },
  ];

  fields.forEach(f => {
    html += `<div style="display:flex;flex-direction:column;gap:2px">
      <label style="font-size:11px;color:var(--fg-muted)">${f.label}${f.required ? ' <span style="color:var(--red)">*</span>' : ''}</label>
      <input type="${f.type}" id="ef_${f.key}" value="${escapeHtml(String(f.value))}" style="padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:13px">
    </div>`;
  });

  html += `<div style="display:flex;flex-direction:column;gap:2px">
    <label style="font-size:11px;color:var(--fg-muted)">课程描述</label>
    <textarea id="ef_description" style="padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:13px;min-height:60px;resize:vertical">${escapeHtml(description)}</textarea>
  </div>`;

  // ── Section结构 ──
  html += `<hr style="border-color:var(--border-light);margin:8px 0">`;
  html += `<div style="font-weight:600;color:var(--fg);font-size:13px;padding:4px 0">📚 Section结构</div>`;
  html += `<div id="ef_sections_container">`;
  sections.forEach((sec, idx) => {
    const sn = sec.section_number || '';
    const st = sec.section_title || '';
    const sh = sec.section_hours || sec.hours || '';
    html += `<div style="display:flex;gap:4px;align-items:center;margin-bottom:4px">
      <input type="text" id="ef_sec_num_${idx}" value="${sn}" placeholder="编号" style="width:50px;padding:4px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:11px">
      <input type="text" id="ef_sec_title_${idx}" value="${escapeHtml(String(st))}" placeholder="标题" style="flex:1;padding:4px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:11px">
      <input type="text" id="ef_sec_hours_${idx}" value="${sh}" placeholder="学时" style="width:50px;padding:4px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:11px">
    </div>`;
  });
  html += `</div>`;
  html += `<button class="course-action-btn" onclick="addSectionField()" style="font-size:10px">+ 添加Section</button>`;
  html += `<input type="hidden" id="ef_section_count" value="${sections.length}">`;

  // ── 课时管理 ──
  html += `<hr style="border-color:var(--border-light);margin:8px 0">`;
  html += `<div style="font-weight:600;color:var(--fg);font-size:13px;padding:4px 0">📖 课时列表</div>`;
  html += `<div style="font-size:11px;color:var(--fg-muted);margin-bottom:4px">共 ${lessons.length} 个课时</div>`;
  html += `<div style="max-height:180px;overflow-y:auto">`;
  lessons.forEach(l => {
    const ln = l.lesson_number || 0;
    const lt = l.lesson_title || '';
    const eLt = escapeHtml(lt);
    html += `<div style="display:flex;align-items:center;gap:4px;padding:2px 0;font-size:11px">
      <span style="color:var(--accent);font-weight:600">L${ln}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${eLt}</span>
      <span class="course-action-btn" style="font-size:9px;padding:0 4px;cursor:pointer" onclick="insertLesson('${courseId}', ${ln})">📄</span>
      <span class="course-action-btn" style="font-size:9px;padding:0 4px;color:var(--red);cursor:pointer" onclick="deleteLessonConfirm('${courseId}', ${ln}, '${eLt.replace(/'/g, "\\'")}')">🗑️</span>
    </div>`;
  });
  html += `</div>`;
  html += `<div style="display:flex;gap:4px;flex-wrap:wrap;padding-top:4px">`;
  html += `<button class="course-action-btn" onclick="prependLesson('${courseId}')" style="font-size:10px">⤒ 开头插入</button>`;
  html += `<button class="course-action-btn" onclick="addLessonToCourse('${courseId}')" style="font-size:10px">+ 尾部追加</button>`;
  html += `<button class="course-action-btn" onclick="reorderLessons('${courseId}')" style="font-size:10px">↻ 重排编号</button>`;
  html += `</div>`;

  // ── 操作按钮 ──
  html += `<div style="display:flex;gap:8px;padding-top:8px;border-top:1px solid var(--border)">
    <button class="course-action-btn" onclick="saveCourse('${courseId}')" style="background:var(--accent);color:#fff;padding:6px 16px">💾 保存</button>
    <button class="course-action-btn" onclick="closeHtmlModal()" style="padding:6px 16px">取消</button>
  </div></div>`;

  showHtmlModal(`✏️ 编辑课程 · ${escapeHtml(title)}`, html);
}

let _sectionCounter = 0;

function addSectionField() {
  const container = document.getElementById('ef_sections_container');
  if (!container) return;
  const countEl = document.getElementById('ef_section_count');
  const idx = parseInt(countEl ? countEl.value : '0');
  const div = document.createElement('div');
  div.style.cssText = 'display:flex;gap:4px;align-items:center;margin-bottom:4px';
  div.innerHTML = `
    <input type="text" id="ef_sec_num_${idx}" placeholder="编号" style="width:50px;padding:4px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:11px">
    <input type="text" id="ef_sec_title_${idx}" placeholder="标题" style="flex:1;padding:4px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:11px">
    <input type="text" id="ef_sec_hours_${idx}" placeholder="学时" style="width:50px;padding:4px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:11px">
  `;
  container.appendChild(div);
  if (countEl) countEl.value = String(idx + 1);
}

async function addLessonToCourse(courseId) {
  const course = state.courses.find(c => (c.note_id || c.id || c._id || c.filename || '') === courseId);
  if (!course) return;
  const lessons = course.lessons || [];
  const nextNum = lessons.length > 0 ? Math.max(...lessons.map(l => l.lesson_number || 0)) + 1 : 1;
  const title = await modalPrompt(`新课时标题 (将排为 #${nextNum}):`, `课时 ${nextNum}`);
  if (!title) return;
  const res = await client.api('/api/data/courses/addLesson', {
    course_id: courseId,
    lesson_number: nextNum,
    lesson_data: { lesson_title: title, central_question: '', description: '', estimated_hours: 1 }
  });
  if (res.code === 0) {
    showToast('课时已添加', 'success');
    closeHtmlModal();
    await loadCourses();
  } else {
    showToast('添加失败: ' + (res.msg || ''), 'error');
  }
}

async function insertLesson(courseId, afterLessonNumber) {
  const course = state.courses.find(c => (c.note_id || c.id || c._id || c.filename || '') === courseId);
  if (!course) return;
  const lessons = course.lessons || [];
  const insertAt = afterLessonNumber + 1;
  const title = await modalPrompt(`插入课时标题 (插入到 #${afterLessonNumber} 之后, 将排为 #${insertAt}):`, `课时 ${insertAt}`);
  if (!title) return;
  const res = await client.api('/api/data/courses/addLesson', {
    course_id: courseId,
    lesson_number: insertAt,
    lesson_data: { lesson_title: title, central_question: '', description: '', estimated_hours: 1 }
  });
  if (res.code === 0) {
    showToast('课时已插入', 'success');
    closeHtmlModal();
    await loadCourses();
  } else {
    showToast('插入失败: ' + (res.msg || ''), 'error');
  }
}

async function prependLesson(courseId) {
  const title = await modalPrompt('新课时标题 (插入到开头, 将排为 #1):', '课时 1');
  if (!title) return;
  const res = await client.api('/api/data/courses/addLesson', {
    course_id: courseId,
    lesson_number: 1,
    lesson_data: { lesson_title: title, central_question: '', description: '', estimated_hours: 1 }
  });
  if (res.code === 0) {
    showToast('课时已插入', 'success');
    closeHtmlModal();
    await loadCourses();
  } else {
    showToast('插入失败: ' + (res.msg || ''), 'error');
  }
}

async function _doDeleteLesson(courseId, lessonNumber) {
  return await client.api('/api/data/courses/deleteLesson', {
    course_id: courseId,
    lesson_number: lessonNumber
  });
}

async function deleteLessonConfirm(courseId, lessonNumber, lessonTitle) {
  if (!await modalConfirm(`确定删除课时 #${lessonNumber}「${lessonTitle || ''}」？后续课时将自动重排。`)) return;
  const res = await _doDeleteLesson(courseId, lessonNumber);
  if (res.code === 0) {
    showToast('课时已删除并重排', 'success');
    closeHtmlModal();
    await loadCourses();
  } else {
    showToast('删除失败: ' + (res.msg || ''), 'error');
  }
}

async function deleteLessonFromEdit(courseId, lessonNumber) {
  if (!await modalConfirm(`确定删除课时 #${lessonNumber}？后续课时将自动重排。`)) return;
  const res = await _doDeleteLesson(courseId, lessonNumber);
  if (res.code === 0) {
    showToast('课时已删除并重排', 'success');
    closeHtmlModal();
    await loadCourses();
  } else {
    showToast('删除失败: ' + (res.msg || ''), 'error');
  }
}

async function reorderLessons(courseId) {
  if (!await modalConfirm('强制重新编号所有课时为 1,2,3…？')) return;
  const res = await client.api('/api/data/courses/reorderLessons', { course_id: courseId });
  if (res.code === 0) {
    showToast('课时已重新编号', 'success');
    closeHtmlModal();
    await loadCourses();
  } else {
    showToast('重排失败: ' + (res.msg || ''), 'error');
  }
}

async function saveCourse(courseId) {
  const getVal = (key) => {
    const el = document.getElementById(`ef_${key}`);
    return el ? el.value.trim() : '';
  };
  const title = getVal('course_title');
  if (!title) { showToast('课程名称不能为空', 'error'); return; }

  const updates = {
    course_title: title,
    domain: getVal('domain') || 'UNKNOWN',
    total_hours: getVal('total_hours'),
    target_audience: getVal('target_audience'),
    assessment: getVal('assessment'),
    positioning: getVal('positioning'),
    prerequisites: getVal('prerequisites'),
    description: getVal('description'),
  };

  // 收集 sections
  const countEl = document.getElementById('ef_section_count');
  if (countEl) {
    const count = parseInt(countEl.value) || 0;
    if (count > 0) {
      const sections = [];
      for (let i = 0; i < count; i++) {
        const sn = document.getElementById(`ef_sec_num_${i}`);
        const st = document.getElementById(`ef_sec_title_${i}`);
        const sh = document.getElementById(`ef_sec_hours_${i}`);
        if (sn && (sn.value.trim() || st?.value.trim())) {
          sections.push({
            section_number: parseInt(sn.value.trim()) || 0,
            section_title: st ? st.value.trim() : '',
            section_hours: sh ? sh.value.trim() : ''
          });
        }
      }
      if (sections.length > 0) {
        updates.sections = sections;
      }
    }
  }

  const res = await client.api('/api/data/courses/update', { course_id: courseId, updates });
  if (res.code === 0) {
    showToast('课程已更新', 'success');
    closeHtmlModal();
    await loadCourses();
  } else {
    showToast('保存失败: ' + (res.msg || ''), 'error');
  }
}

// ─── 课时编辑 ───────────────────────────────────────────

async function editLesson(courseId, lessonNumber) {
  const course = state.courses.find(c => (c.note_id || c.id || c._id || c.filename || '') === courseId);
  if (!course) { showToast('课程未找到', 'error'); return; }
  const lesson = (course.lessons || []).find(l => l.lesson_number == lessonNumber);
  if (!lesson) { showToast('课时未找到', 'error'); return; }

  const lTitle = lesson.lesson_title || '';
  const lQuestion = lesson.central_question || '';
  const lDesc = lesson.description || '';
  const lHours = lesson.estimated_hours || '';

  let html = `<div style="display:flex;flex-direction:column;gap:8px;max-height:65vh;overflow-y:auto;padding:4px">`;

  const fields = [
    { key: 'lesson_title', label: '课时标题', type: 'text', value: lTitle },
    { key: 'central_question', label: '中心问题', type: 'text', value: lQuestion },
    { key: 'estimated_hours', label: '预估学时', type: 'text', value: lHours },
  ];

  fields.forEach(f => {
    html += `<div style="display:flex;flex-direction:column;gap:2px">
      <label style="font-size:11px;color:var(--fg-muted)">${f.label}</label>
      <input type="${f.type}" id="el_${f.key}" value="${escapeHtml(String(f.value))}" style="padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:13px">
    </div>`;
  });

  html += `<div style="display:flex;flex-direction:column;gap:2px">
    <label style="font-size:11px;color:var(--fg-muted)">描述</label>
    <textarea id="el_description" style="padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--fg);font-size:13px;min-height:80px;resize:vertical">${escapeHtml(lDesc)}</textarea>
  </div>`;

  html += `<div style="display:flex;flex-wrap:wrap;gap:4px;padding-top:8px;border-top:1px solid var(--border);align-items:center">
    <button class="course-action-btn" onclick="saveLesson('${courseId}', ${lessonNumber})" style="background:var(--accent);color:#fff;padding:6px 16px">💾 保存</button>
    <span style="font-size:10px;color:var(--fg-muted);padding:0 4px">│</span>
    <button class="course-action-btn" onclick="insertLesson('${courseId}', ${lessonNumber - 1})" style="font-size:10px;padding:4px 8px">⤒ 前插入</button>
    <button class="course-action-btn" onclick="insertLesson('${courseId}', ${lessonNumber})" style="font-size:10px;padding:4px 8px">⤓ 后插入</button>
    <button class="course-action-btn" onclick="deleteLessonFromEdit('${courseId}', ${lessonNumber})" style="font-size:10px;padding:4px 8px;color:var(--red)">🗑️ 删除本课时</button>
    <button class="course-action-btn" onclick="closeHtmlModal()" style="padding:6px 16px">取消</button>
  </div></div>`;

  showHtmlModal(`✏️ 编辑课时 ${lessonNumber} · ${escapeHtml(lTitle)}`, html);
}

async function saveLesson(courseId, lessonNumber) {
  const getVal = (key) => {
    const el = document.getElementById(`el_${key}`);
    return el ? el.value.trim() : '';
  };
  const title = getVal('lesson_title');
  if (!title) { showToast('课时标题不能为空', 'error'); return; }

  const updates = {
    lesson_title: title,
    central_question: getVal('central_question'),
    estimated_hours: parseFloat(getVal('estimated_hours')) || 1,
    description: getVal('description'),
  };

  const res = await client.api('/api/data/courses/updateLesson', {
    course_id: courseId,
    lesson_number: lessonNumber,
    updates: updates
  });
  if (res.code === 0) {
    showToast('课时已更新', 'success');
    closeHtmlModal();
    await loadCourses();
  } else {
    showToast('保存失败: ' + (res.msg || ''), 'error');
  }
}

// ─── 文件树右键菜单：添加为课程资源 ──────────────────────────

// 在原有的文件树右键菜单中增加"添加为课程资源"选项
// 挂载到现有的 context menu 处理逻辑

document.getElementById('courseCreateBtn').addEventListener('click', () => {
  showModal('新建课程', '课程名称', async (title) => {
    if (!title) return;
    const domain = await modalPrompt('学科领域 (如 PHYSICS, MATH):', 'UNKNOWN') || 'UNKNOWN';
    const res = await client.api('/api/data/courses/create', { title, domain });
    if (res.code === 0) {
      showToast('课程已创建', 'success');
      await loadCourses();
    } else {
      showToast('创建失败: ' + (res.msg || ''), 'error');
    }
  });
});

document.getElementById('courseRefreshBtn').addEventListener('click', () => {
  loadCourses();
});

// ─── Execution Panel ────────────────────────────────────────

function initExecutionPanel() {
  populateExecCourseSelect();
  loadWorkflowStats();
}

async function populateExecCourseSelect() {
  const select = document.getElementById('execCourseSelect');
  if (!state.courses.length) {
    const res = await client.getCourses();
    if (res.code === 0 && res.data) {
      state.courses = Array.isArray(res.data) ? res.data : (res.data.courses || []);
    }
  }

  select.innerHTML = '<option value="">-- 请选择课程 --</option>';
  state.courses.forEach(course => {
    const id = course.note_id || course.id || course._id || course.filename || '';
    const title = course.course_title || course.title || course.name || '未命名课程';
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = title;
    select.appendChild(opt);
  });

  // Restore selection if any
  if (state.execCourseId) {
    select.value = state.execCourseId;
    await populateExecLessonSelect(state.execCourseId);
  }
}

async function populateExecLessonSelect(courseId) {
  const select = document.getElementById('execLessonSelect');
  select.innerHTML = '<option value="">-- 请选择课时 --</option>';

  if (!courseId) return;

  const course = state.courses.find(c => (c.note_id || c.id || c._id) === courseId);
  if (!course) return;

  // Load progress
  if (!state.courseProgress[courseId]) {
    const res = await client.getCourseProgress(courseId);
    if (res.code === 0 && res.data) {
      state.courseProgress[courseId] = res.data.progress || res.data || {};
    }
  }

  const lessons = course.lessons || [];
  const progress = state.courseProgress[courseId] || {};

  lessons.forEach((lesson, idx) => {
    const lNum = lesson.lesson_number || lesson.number || (idx + 1);
    const lTitle = lesson.lesson_title || lesson.title || '未命名课时';
    const isCompleted = progress[lNum];
    const opt = document.createElement('option');
    opt.value = idx;
    opt.textContent = `${lNum}. ${lTitle}${isCompleted ? ' ✅' : ''}`;
    select.appendChild(opt);
  });

  // Auto-select first uncompleted lesson
  const firstUncompleted = lessons.findIndex((lesson, idx) => {
    const lNum = lesson.lesson_number || lesson.number || (idx + 1);
    return !progress[lNum];
  });
  if (firstUncompleted >= 0) {
    select.value = firstUncompleted;
    showExecLessonInfo(courseId, firstUncompleted);
  }
}

document.getElementById('execCourseSelect').addEventListener('change', async (e) => {
  const courseId = e.target.value;
  state.execCourseId = courseId;
  resetTimer();
  await populateExecLessonSelect(courseId);
  document.getElementById('execLessonInfo').style.display = 'none';
  document.getElementById('execLessonActions').style.display = 'none';
  document.getElementById('execTimer').style.display = 'none';
  document.getElementById('execCompleteBtn').style.display = 'none';
});

document.getElementById('execLessonSelect').addEventListener('change', (e) => {
  const idx = e.target.value;
  if (idx === '') {
    document.getElementById('execLessonInfo').style.display = 'none';
    document.getElementById('execLessonActions').style.display = 'none';
    document.getElementById('execTimer').style.display = 'none';
    document.getElementById('execCompleteBtn').style.display = 'none';
    resetTimer();
    return;
  }
  resetTimer();
  showExecLessonInfo(state.execCourseId, parseInt(idx));
});

document.getElementById('execLessonActions').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const { action, course, lesson, title } = btn.dataset;
  if (action === 'course-resource') showCourseResources(course);
  else if (action === 'note') openLessonNote(course, parseInt(lesson));
  else if (action === 'resource') showCourseResources(course, parseInt(lesson));
  else if (action === 'edit') editLesson(course, parseInt(lesson));
  else if (action === 'delete') deleteLessonConfirm(course, parseInt(lesson), title);
});

function showExecLessonInfo(courseId, lessonIdx) {
  const course = state.courses.find(c => (c.note_id || c.id || c._id) === courseId);
  if (!course || !course.lessons || !course.lessons[lessonIdx]) return;

  const lesson = course.lessons[lessonIdx];
  const lNum = lesson.lesson_number || lesson.number || (lessonIdx + 1);
  const title = lesson.lesson_title || lesson.title || '未命名课时';
  const question = lesson.central_question || '';
  const desc = lesson.description || '';
  const hours = lesson.estimated_hours || 0;
  const refs = lesson.references || [];

  const infoEl = document.getElementById('execLessonInfo');
  infoEl.innerHTML = `
    <div class="exec-lesson-info">
      <div class="eli-title">${escapeHtml(title)}</div>
      ${question ? `<div class="eli-question">❓ ${escapeHtml(question)}</div>` : ''}
      ${desc ? `<div class="eli-desc">${escapeHtml(desc)}</div>` : ''}
      ${refs.length ? `<div class="eli-refs">📖 参考资料: ${refs.map(r => `<span>${escapeHtml(r)}</span>`).join(', ')}</div>` : ''}
      <div style="font-size:11px;color:var(--fg-dim);margin-top:6px">⏱ 预计时长: ${hours}h</div>
    </div>
  `;
  infoEl.style.display = 'block';

  const actionsEl = document.getElementById('execLessonActions');
  const safeTitle = title.replace(/'/g, "\\'").replace(/\\/g, "\\\\");
  actionsEl.innerHTML = `
    <div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
      <button class="course-action-btn resource-btn" style="font-size:10px;padding:2px 8px" data-action="course-resource" data-course="${escapeHtml(courseId)}">📎 课程资源</button>
      <span style="width:1px;height:16px;background:var(--border);margin:0 2px"></span>
      <button class="course-action-btn note-btn" style="font-size:10px;padding:2px 8px" data-action="note" data-course="${escapeHtml(courseId)}" data-lesson="${lNum}">📝 笔记</button>
      <button class="course-action-btn resource-btn" style="font-size:10px;padding:2px 8px" data-action="resource" data-course="${escapeHtml(courseId)}" data-lesson="${lNum}">📎 本课资源</button>
      <button class="course-action-btn" style="font-size:10px;padding:2px 6px" data-action="edit" data-course="${escapeHtml(courseId)}" data-lesson="${lNum}">✏️ 编辑</button>
      <button class="course-action-btn" style="font-size:10px;padding:2px 6px;color:var(--red)" data-action="delete" data-course="${escapeHtml(courseId)}" data-lesson="${lNum}" data-title="${safeTitle}">🗑️ 删除</button>
    </div>
  `;
  actionsEl.style.display = 'block';

  // Setup timer
  state.timerSeconds = hours * 3600;
  updateTimerDisplay();
  document.getElementById('execTimer').style.display = 'block';
  document.getElementById('execCompleteBtn').style.display = 'block';

  state.execLessonIdx = lessonIdx;
}

// ─── Timer ──────────────────────────────────────────────────

function updateTimerDisplay() {
  const h = Math.floor(state.timerSeconds / 3600);
  const m = Math.floor((state.timerSeconds % 3600) / 60);
  const s = state.timerSeconds % 60;
  document.getElementById('timerDisplay').textContent =
    `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function resetTimer() {
  if (state.timerInterval) clearInterval(state.timerInterval);
  state.timerInterval = null;
  state.timerRunning = false;
  state.timerPaused = false;
  state.timerSeconds = 0;
  updateTimerDisplay();
  document.getElementById('timerStart').style.display = '';
  document.getElementById('timerStart').textContent = '▶ 开始';
  document.getElementById('timerStart').classList.remove('running');
  document.getElementById('timerPause').style.display = 'none';
  document.getElementById('timerStop').style.display = 'none';
}

document.getElementById('timerStart').addEventListener('click', () => {
  if (state.timerRunning) return;
  if (state.timerPaused) {
    state.timerPaused = false;
  }
  state.timerRunning = true;
  state._timerStartTime = Date.now();
  document.getElementById('timerStart').style.display = 'none';
  document.getElementById('timerPause').style.display = '';
  document.getElementById('timerStop').style.display = '';

  // 记录开始计时到工作流日志
  if (state.execCourseId) {
    const course = state.courses.find(c => (c.note_id || c.id || c._id) === state.execCourseId);
    const lNum = course && course.lessons[state.execLessonIdx] ?
      (course.lessons[state.execLessonIdx].lesson_number || state.execLessonIdx + 1) : null;
    client.api('/api/data/workflow/log', {
      type: 'timer_start', course_id: state.execCourseId, lesson_number: lNum,
    });
  }

  state.timerInterval = setInterval(() => {
    if (state.timerSeconds > 0) {
      state.timerSeconds--;
      updateTimerDisplay();
    } else {
      clearInterval(state.timerInterval);
      state.timerInterval = null;
      state.timerRunning = false;
      showToast('⏰ 计时结束！', 'info');
      document.getElementById('timerStart').style.display = '';
      document.getElementById('timerPause').style.display = 'none';
      document.getElementById('timerStop').style.display = 'none';
    }
  }, 1000);
});

document.getElementById('timerPause').addEventListener('click', () => {
  if (!state.timerRunning) return;
  state.timerPaused = true;
  state.timerRunning = false;
  if (state.timerInterval) clearInterval(state.timerInterval);
  state.timerInterval = null;
  document.getElementById('timerStart').style.display = '';
  document.getElementById('timerStart').textContent = '▶ 继续';
  document.getElementById('timerPause').style.display = 'none';
});

document.getElementById('timerStop').addEventListener('click', () => {
  // 记录停止计时到工作流日志
  if (state._timerStartTime && state.execCourseId) {
    const elapsed = Math.round((Date.now() - state._timerStartTime) / 1000);
    const h = Math.floor(elapsed / 3600);
    const m = Math.floor((elapsed % 3600) / 60);
    const s = elapsed % 60;
    const durStr = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    const course = state.courses.find(c => (c.note_id || c.id || c._id) === state.execCourseId);
    const lNum = course && course.lessons[state.execLessonIdx] ?
      (course.lessons[state.execLessonIdx].lesson_number || state.execLessonIdx + 1) : null;
    client.api('/api/data/workflow/log', {
      type: 'timer_stop', course_id: state.execCourseId, lesson_number: lNum,
      detail: `耗时 ${durStr}`,
    });
    loadWorkflowStats();
  }
  resetTimer();
  if (state.execCourseId && state.execLessonIdx !== null) {
    const course = state.courses.find(c => (c.note_id || c.id || c._id) === state.execCourseId);
    if (course && course.lessons && course.lessons[state.execLessonIdx]) {
      state.timerSeconds = (course.lessons[state.execLessonIdx].estimated_hours || 0) * 3600;
      updateTimerDisplay();
    }
  }
});

document.getElementById('execCompleteBtn').addEventListener('click', async () => {
  if (!state.execCourseId || state.execLessonIdx === null) return;
  const course = state.courses.find(c => (c.note_id || c.id || c._id) === state.execCourseId);
  if (!course || !course.lessons[state.execLessonIdx]) return;

  const lesson = course.lessons[state.execLessonIdx];
  const lNum = lesson.lesson_number || lesson.number || (state.execLessonIdx + 1);

  const res = await client.updateLessonStatus(state.execCourseId, lNum, 'completed');
  if (res.code === 0) {
    if (!state.courseProgress[state.execCourseId]) state.courseProgress[state.execCourseId] = {};
    state.courseProgress[state.execCourseId][lNum] = true;
    showToast('✅ 课时已完成！', 'success');
    resetTimer();

    // 记录完成到工作流日志
    await client.api('/api/data/workflow/log', {
      type: 'lesson_complete', course_id: state.execCourseId, lesson_number: lNum,
      detail: `完成: ${lesson.lesson_title || lesson.title || ''}`,
    });
    // 触发复习调度
    await client.api('/api/data/courses/updateReview', { course_id: state.execCourseId, lesson_number: lNum, status: 5 });
    loadWorkflowStats();

    // Advance to next lesson
    const nextIdx = state.execLessonIdx + 1;
    if (nextIdx < course.lessons.length) {
      state.execLessonIdx = nextIdx;
      document.getElementById('execLessonSelect').value = nextIdx;
      showExecLessonInfo(state.execCourseId, nextIdx);
    } else {
      showToast('🎉 课程全部完成！', 'success');
      document.getElementById('execLessonInfo').style.display = 'none';
      document.getElementById('execLessonActions').style.display = 'none';
      document.getElementById('execTimer').style.display = 'none';
      document.getElementById('execCompleteBtn').style.display = 'none';
    }
    await populateExecLessonSelect(state.execCourseId);
  } else {
    showToast('完成失败: ' + (res.msg || ''), 'error');
  }
});

// ─── Workflow Stats ──────────────────────────────────────

async function loadWorkflowStats() {
  const res = await client.api_get('/api/data/workflow/stats');
  if (res.code === 0 && res.data) {
    const d = res.data;
    document.getElementById('statFocusHours').textContent = d.total_focus_hours || 0;
    document.getElementById('statCompleted').textContent = d.complete_count || 0;
    document.getElementById('statNotes').textContent = d.note_count || 0;
    document.getElementById('statEntries').textContent = d.total_entries || 0;
  }
  // 加载最近日志
  const logRes = await client.api_get('/api/data/workflow/log');
  if (logRes.code === 0 && logRes.data) {
    const entries = logRes.data.slice(-10).reverse();
    const icons = { timer_start: '▶️', timer_stop: '⏹', lesson_complete: '✅', note: '📝', action: '⚡', blur: '👁️', focus_return: '👁️‍🗨️' };
    document.getElementById('workflowLogContent').innerHTML = entries.map(e =>
      `<div style="font-size:10px;color:var(--fg-muted);padding:2px 0;border-bottom:1px solid var(--border)">
        <span>${icons[e.type] || '📌'}</span>
        <span style="color:var(--fg-dim)">${e.timestamp ? e.timestamp.substring(5, 16) : ''}</span>
        ${e.detail ? `<span> ${escapeHtml(e.detail)}</span>` : ''}
      </div>`
    ).join('') || '<div style="font-size:10px;color:var(--fg-dim)">暂无记录</div>';
  }
}

// ─── Stats Panel ──────────────────────────────────────────

async function loadStatsPanel() {
  // 课程统计
  const csRes = await client.api_get('/api/data/courses/stats');
  if (csRes.code === 0 && csRes.data) {
    const d = csRes.data;
    document.getElementById('statTotalCourses').textContent = d.total_courses || 0;
    document.getElementById('statTotalHours').textContent = d.total_hours || 0;
    document.getElementById('statTotalLessons').textContent = d.total_lessons || 0;
    document.getElementById('statCompletionRate').textContent = (d.completion_rate || 0) + '%';

    // 域名分布
    const dist = d.domain_distribution || {};
    const maxCount = Math.max(...Object.values(dist), 1);
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
    document.getElementById('domainDistribution').innerHTML = Object.entries(dist).map(([domain, count], i) =>
      `<div style="margin-bottom:4px">
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--fg-muted)">
          <span>${escapeHtml(domain)}</span><span>${count} 门</span>
        </div>
        <div style="background:var(--bg);border-radius:3px;height:6px;margin-top:2px">
          <div class="domain-bar" style="width:${Math.round(count/maxCount*100)}%;background:${colors[i % colors.length]}"></div>
        </div>
      </div>`
    ).join('') || '<div style="font-size:10px;color:var(--fg-dim)">暂无数据</div>';
  }

  // 工作流统计 + 热力图
  const wfRes = await client.api_get('/api/data/workflow/stats');
  if (wfRes.code === 0 && wfRes.data) {
    const d = wfRes.data;
    document.getElementById('statWFFocusHours').textContent = d.total_focus_hours || 0;
    document.getElementById('statWFCompleted').textContent = d.complete_count || 0;

    // 热力图
    const daily = d.daily || {};
    const today = new Date();
    const cells = [];
    for (let i = 29; i >= 0; i--) {
      const d2 = new Date(today);
      d2.setDate(d2.getDate() - i);
      const key = d2.toISOString().substring(0, 10);
      const count = daily[key] || 0;
      let level = '';
      if (count >= 10) level = 'l4';
      else if (count >= 5) level = 'l3';
      else if (count >= 2) level = 'l2';
      else if (count >= 1) level = 'l1';
      cells.push(`<div class="heatmap-cell ${level}" title="${key}: ${count} 条记录"></div>`);
    }
    document.getElementById('activityHeatmap').innerHTML = cells.join('');
  }
}

// ─── Dashboard Panel (Pilot 仪表盘，明晃晃默认首页) ──
// 严格对齐 docs/sabersystem_plan_05_frontend_dashboard.md 的 11 条修正清单

let _dashLoadTreePending = false;

async function loadDashboardPanel() {
  await Promise.all([
    _dashLoadLife(),
    _dashLoadTree(),
  ]);
  if (state.dashboard.selectedPlanId) {
    _dashLoadIntensity(state.dashboard.selectedPlanId);
  } else {
    _renderHudIntensity(null);
  }
  _renderHud();
  _renderCopilotLog();
}

async function _dashLoadLife() {
  const [lifeRes, attRes] = await Promise.all([
    client.saberGetLife('default'),
    client.saberGetAttention('default'),
  ]);
  if (lifeRes.code === 0) state.dashboard.life = lifeRes.data;
  if (attRes.code === 0) state.dashboard.attention = attRes.data;
  _renderHud();
}

async function _dashLoadTree() {
  // 防重入：防止快速点击创建按钮导致并发加载
  if (_dashLoadTreePending) return;
  _dashLoadTreePending = true;
  const container = document.getElementById('dashTreeList');
  if (container && !container.innerHTML.trim()) {
    container.innerHTML = '<div class="dash-empty" style="opacity:0.6;">⏳ 加载中...</div>';
  }
  try {
    const idealsRes = await client.saberListIdeals();
    if (idealsRes.code !== 0) return;
    state.dashboard.ideals = idealsRes.data || [];

    // 批量加载所有 Goal（并行）
    const goalReqs = state.dashboard.ideals.map(ideal =>
      client.saberListGoals(ideal.id).then(r => ({ ideal, goals: r.code === 0 ? (r.data || []) : [] }))
    );
    const goalResults = await Promise.all(goalReqs);
    for (const gr of goalResults) {
      gr.ideal._goals = gr.goals;
    }

    // 批量加载所有 Plan（并行）
    const allGoals = goalResults.flatMap(gr => gr.goals);
    const planReqs = allGoals.map(goal =>
      client.saberListPlans(goal.id).then(r => ({ goal, plans: r.code === 0 ? (r.data || []) : [] }))
    );
    const planResults = await Promise.all(planReqs);
    for (const pr of planResults) {
      pr.goal._plans = pr.plans;
    }

    // 批量加载所有 Task（并行）
    const allPlans = planResults.flatMap(pr => pr.plans);
    const taskReqs = allPlans.map(plan =>
      client.saberListTasks(plan.id).then(r => ({ plan, tasks: r.code === 0 ? (r.data || []) : [] }))
    );
    const taskResults = await Promise.all(taskReqs);
    for (const tr of taskResults) {
      tr.plan._tasks = tr.tasks;
    }

    // 并行加载偏航警告 + 拓扑 + 违规
    const extraReqs = [client.saberCheckImbalance()];
    if (state.dashboard.selectedPlanId) {
      extraReqs.push(
        client.api_get(`/api/saber/plans/${state.dashboard.selectedPlanId}/topology`),
        client.api_get(`/api/saber/plans/${state.dashboard.selectedPlanId}/violations`),
      );
    }
    const [imbRes, topoRes, violRes] = await Promise.all(extraReqs);
    state.dashboard.imbalanceWarning = imbRes.code === 0 ? imbRes.data : null;
    if (topoRes && topoRes.code === 0) state.dashboard.topology = topoRes.data;
    if (violRes && violRes.code === 0) state.dashboard.violations = violRes.data;

    _renderDashTree();
  } finally {
    _dashLoadTreePending = false;
  }
}

// ─── 认知层级中文化 ───
const _COG_LAYERS = ['K','C','T','S','W'];
const _COG_MAP = {K:'知识', C:'概念', T:'理论', S:'技能', W:'工作流'};

function _layerLabel(layer) {
  const ch = _COG_MAP[layer] || layer || '—';
  return layer ? `${layer} ${ch}` : '—';
}

function _layerBadge(layer) {
  const ch = _COG_MAP[layer] || layer || '—';
  return layer ? `<span class="cl-badge cl-${layer}">${layer} ${ch}</span>` : '—';
}

function _cogOptions(selected) {
  return _COG_LAYERS.map(l => `<option value="${l}" ${selected===l?'selected':''}>${l} ${_COG_MAP[l]}</option>`).join('');
}

// ─── HUD 6 分区渲染 ───

function _renderHud() {
  const life = state.dashboard.life;
  const att = state.dashboard.attention;
  // ⏳ 生命资源
  if (life) {
    const used = life.waking_hours_used ?? 0;
    const total = life.waking_hours_total ?? 16;
    const surplus = life.waking_hours_surplus ?? Math.max(0, total - used);
    document.getElementById('hudLifeValue').textContent = `${used.toFixed(1)} / ${surplus.toFixed(1)}h`;
    const attBal = att ? (att.balance ?? 0).toFixed(2) : '—';
    const energy = (life.energy_level ?? 0).toFixed(2);
    document.getElementById('hudLifeSub').textContent = `注意力 ${attBal} · 体能 ${energy}`;
    // 经济显示：自由时间盈余回报 + trust_score
    const surplusTotal = life.free_time_surplus_total ?? 0;
    const trustScore = state.dashboard.trustScore ?? (life.trust_score ?? 1.0);
    const metaEl = document.getElementById('hudLifeMeta');
    if (metaEl) {
      metaEl.textContent = `盈余回报 +${surplusTotal.toFixed(1)}h · 信任 ${(trustScore * 100).toFixed(0)}%`;
      metaEl.title = `累计自由时间盈余回报: ${surplusTotal.toFixed(1)}h · Trust Score: ${trustScore.toFixed(2)}`;
    }
    // 透支/耗尽视觉
    const lifeCell = document.getElementById('hudLife');
    lifeCell.classList.toggle('hud-warn', att && att.is_depleted);
    lifeCell.classList.toggle('hud-danger', att && att.is_overdrawn || (life.health && life.health.is_burned_out));

    // 健康警告横幅
    const burnedOut = life.health && (typeof life.health.is_burned_out === 'function' ? life.health.is_burned_out() : life.health.is_burned_out);
    const banner = document.getElementById('healthBanner');
    if (banner) {
      if (burnedOut) {
        banner.classList.add('active');
        const energyLevel = (life.energy_level ?? 0).toFixed(2);
        const attBalVal = att ? (att.balance ?? 0).toFixed(2) : '—';
        document.getElementById('healthBannerText').textContent = `⚠️ 生命硬约束触发：体能 ${energyLevel} / 注意力 ${attBalVal}，已强制冻结新任务启动。请先休息。`;
      } else {
        banner.classList.remove('active');
      }
    }
  }
  // 🧠 认知层级
  const plan = state.dashboard.selectedPlan;
  if (plan) {
    document.getElementById('hudCogValue').textContent = _layerLabel(plan.cognitive_focus);
    const progress = ((plan.aggregated_progress ?? 0) * 100).toFixed(0);
    document.getElementById('hudCogSub').textContent = `进度 ${progress}%`;
  } else {
    document.getElementById('hudCogValue').textContent = '—';
    document.getElementById('hudCogSub').textContent = '无活动 Plan';
  }
  // ✅ 核验率（悬停显示最近 10 次记录）
  const verifyHistory = state.dashboard.verifyHistory || [];
  const verifyPassed = verifyHistory.filter(v => v.passed).length;
  const verifyTotal = verifyHistory.length;
  const verifyRate = verifyTotal > 0 ? (verifyPassed / verifyTotal * 100).toFixed(0) : '—';
  document.getElementById('hudVerifyValue').textContent = verifyTotal > 0 ? `${verifyRate}%` : '—';
  document.getElementById('hudVerifySub').textContent = verifyTotal > 0 ? `${verifyPassed}/${verifyTotal} 通过` : '无记录';
  const verifyCell = document.getElementById('hudVerify');
  verifyCell.classList.toggle('hud-warn', verifyTotal > 0 && verifyPassed / verifyTotal < 0.7);
  verifyCell.classList.toggle('hud-danger', verifyTotal > 0 && verifyPassed / verifyTotal < 0.4);
  // 悬停 tooltip：最近 10 次
  if (verifyHistory.length > 0) {
    const last10 = verifyHistory.slice(-10).reverse();
    const tipHtml = last10.map(v => `<div class="verify-tip-item ${v.passed ? 'pass' : 'fail'}">${v.passed ? '✅' : '❌'} ${escapeHtml(v.constraint || v.name || '')} <span class="verify-tip-time">${escapeHtml(v.time || '')}</span></div>`).join('');
    verifyCell.setAttribute('title', '');
    let tip = document.getElementById('verifyTooltip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'verifyTooltip';
      tip.className = 'verify-tooltip';
      document.body.appendChild(tip);
    }
    tip.innerHTML = tipHtml;
    verifyCell.onmouseenter = (e) => {
      tip.style.display = 'block';
      const rect = verifyCell.getBoundingClientRect();
      tip.style.left = rect.left + 'px';
      tip.style.top = (rect.bottom + 4) + 'px';
    };
    verifyCell.onmouseleave = () => { tip.style.display = 'none'; };
  } else {
    verifyCell.onmouseenter = verifyCell.onmouseleave = null;
  }
  // 🌌 机遇（暂用 state.dashboard.opportunities，后端 API 待接入）
  const opps = state.dashboard.opportunities || [];
  document.getElementById('hudOppValue').textContent = opps.length;
  document.getElementById('hudOppSub').textContent = opps.length > 0 ? '点击查看' : '无活动窗口';
  // 📡 消息（暂用 state.dashboard.messages，后端 API 待接入）
  const msgs = state.dashboard.messages || [];
  document.getElementById('hudMsgValue').textContent = msgs.length;
  document.getElementById('hudMsgSub').textContent = msgs.length > 0 ? `${msgs.filter(m => !m.read).length} 新` : '无新消息';
}

function _pushVerifyHistory(item) {
  if (!state.dashboard.verifyHistory) state.dashboard.verifyHistory = [];
  state.dashboard.verifyHistory.push(item);
  if (state.dashboard.verifyHistory.length > 50) {
    state.dashboard.verifyHistory = state.dashboard.verifyHistory.slice(-50);
  }
  _renderHud();
}

function _renderHudIntensity(data) {
  const fill = document.getElementById('hudIntFill');
  const value = document.getElementById('hudIntValue');
  const cell = document.getElementById('hudIntensity');
  if (!data) {
    fill.style.width = '0%';
    value.textContent = '—';
    cell.classList.remove('hud-warn', 'hud-danger');
    state.dashboard.intensity = null;
    _applyIntensityToAgentPanel(0);
    return;
  }
  const intensity = data.intensity ?? 0;
  const retired = data.retired ?? false;
  state.dashboard.intensity = data;
  fill.style.width = (intensity * 100).toFixed(0) + '%';
  value.textContent = intensity.toFixed(2);
  cell.classList.toggle('hud-warn', !retired && intensity < 0.5);
  cell.classList.toggle('hud-danger', retired);
  // 应用 I(P) 调控：panel-agent 入口可见度
  _applyIntensityToAgentPanel(intensity);
  // 应用 I(P) 调控：建议气泡显隐（>30% 主动弹，≤30% 静默）
  _applyIntensityToDecisionBubble(intensity);
}

function _applyIntensityToDecisionBubble(intensity) {
  const section = document.getElementById('focusDecisionSection');
  const bubble = document.getElementById('focusDecision');
  if (!section || !bubble) return;
  // 移除旧提示
  const oldHint = section.querySelector('.ip-silent-hint');
  if (oldHint) oldHint.remove();
  if (intensity > 0.3) {
    // >30%：建议气泡正常显示，若已有决策则闪烁提示
    section.classList.remove('ip-silent');
    bubble.style.display = '';
    if (state.dashboard.currentDecision) {
      _flashDecisionCard();
    }
  } else {
    // ≤30%：静默折叠为单行提示
    section.classList.add('ip-silent');
    bubble.style.display = 'none';
    const hint = document.createElement('div');
    hint.className = 'ip-silent-hint';
    hint.innerHTML = `💡 I(P)=${intensity.toFixed(2)}≤0.30，Agent 静默中 <button class="dash-btn-mini" onclick="_expandDecisionBubble()">查看建议</button>`;
    section.appendChild(hint);
  }
}

function _expandDecisionBubble() {
  const section = document.getElementById('focusDecisionSection');
  const bubble = document.getElementById('focusDecision');
  if (!section || !bubble) return;
  section.classList.remove('ip-silent');
  bubble.style.display = '';
  const hint = section.querySelector('.ip-silent-hint');
  if (hint) hint.remove();
}

function _applyIntensityToAgentPanel(intensity) {
  const agentTab = document.querySelector('.nav-tab[data-tab="agent"]');
  if (!agentTab) return;
  if (intensity > 0.3) {
    agentTab.style.opacity = '1';
    agentTab.classList.remove('tab-dimmed');
  } else {
    agentTab.style.opacity = '0.4';
    agentTab.classList.add('tab-dimmed');
  }
}

// ─── Plan 树渲染（6 种状态指示器） ───

function _planStatusIndicator(plan, life) {
  // 返回 {icon, cls}
  const progress = plan.aggregated_progress ?? 0;
  const burnedOut = life && life.health && (typeof life.health.is_burned_out === 'function' ? life.health.is_burned_out() : life.health.is_burned_out);
  if (burnedOut) return { icon: '⚫', cls: 'stat-burned' };
  if (progress >= 1.0) return { icon: '✅', cls: 'stat-done' };
  // 简化判定（无 expected_progress 字段时用 0.7/0.9 阈值）
  if (progress >= 0.9) return { icon: '🟢', cls: 'stat-good' };
  if (progress >= 0.7) return { icon: '🟡', cls: 'stat-warn' };
  if (progress < 0.7 && progress > 0) return { icon: '🔴', cls: 'stat-danger' };
  return { icon: '⚪', cls: 'stat-blocked' };
}

function _renderDashTree() {
  const container = document.getElementById('dashTreeList');
  const ideals = state.dashboard.ideals || [];
  if (ideals.length === 0) {
    container.innerHTML = '<div class="dash-empty">暂无 Ideal，点击右上角 ➕ Ideal 创建第一个</div>';
    return;
  }
  const life = state.dashboard.life;
  const burnedOut = life && life.health && (typeof life.health.is_burned_out === 'function' ? life.health.is_burned_out() : life.health.is_burned_out);
  // 理想偏航警告
  const imb = state.dashboard.imbalanceWarning;
  const imbHtml = imb ? `<div class="dash-imbalance-warning" title="${escapeHtml(imb.recommended_action || '')}">⚠️ ${escapeHtml(imb.message || '')}</div>` : '';
  container.innerHTML = imbHtml + ideals.map(ideal => {
    // 健康硬约束：burnedOut 时按钮禁用（提升到外层，供 Ideal/Goal/Plan 三级使用）
    const disabledAttr = burnedOut ? 'disabled' : '';
    const disabledCls = burnedOut ? 'dash-disabled' : '';
    const goals = ideal._goals || [];
    const goalsHtml = goals.map(goal => {
      const plans = goal._plans || [];
      const plansHtml = plans.map(plan => {
        const selected = plan.id === state.dashboard.selectedPlanId ? 'dash-selected' : '';
        return _renderPlanNode(plan, plans, disabledCls, disabledAttr, selected);
      }).join('');
      function _renderPlanNode(p, allPlans, dCls, dAttr, selId) {
        const isSelected = p.id === selId;
        const st = _planStatusIndicator(p, life);
        const prog = ((p.aggregated_progress ?? 0) * 100).toFixed(0);
        const tCnt = (p._tasks || []).length || (p.task_count || 0);
        const dCnt = (p._tasks || []).filter(t => t.status === 'done').length;
        const tProg = tCnt > 0 ? (dCnt / tCnt * 100).toFixed(0) : 0;
        const sur = p.estimated_surplus_yield;
        const surLbl = sur != null ? ` <span class="dash-plan-surplus" title="预计自由时间盈余">${sur >= 0 ? '⏫' : '⏬'} ${sur >= 0 ? '+' : ''}${sur.toFixed(1)}h</span>` : '';
        // 偏序链标签
        const preds = p.predecessors || [];
        const succs = p.successors || [];
        const partialOrderLbl = [];
        if (preds.length) partialOrderLbl.push(`⬅ ${preds.length}`);
        if (succs.length) partialOrderLbl.push(`➡ ${succs.length}`);
        const poHtml = partialOrderLbl.length ? ` <span class="dash-plan-partial-order" title="偏序：${preds.length} 前驱, ${succs.length} 后继">${partialOrderLbl.join(' ')}</span>` : '';
        // 合规状态标签（三色灯+黑灯）
        const cs = p.compliance_status || 'on_track';
        const csHtml = ` <span class="dash-compliance-dot dot-${cs}" title="合规状态: ${cs}"></span>`;
        // 聚合状态标签
        const aggr = p.aggregated_status || '';
        const aggrHtml = aggr && aggr !== 'active' ? ` <span class="dash-plan-aggr-status" title="聚合状态">${aggr === 'completed' ? '✅' : aggr === 'blocked' ? '⛔' : ''}</span>` : '';
        // Angel 介入指示器（训练轮图标，I(P) 越高越亮）
        const globalIp = state.dashboard.intensity;
        const planIp = globalIp ? globalIp.intensity : 0.8;
        const angelOpacity = Math.max(0.15, Math.min(1.0, planIp * 1.5));
        const angelHtml = `<span class="dash-angel-indicator" title="Angel 介入度 I(P)=${planIp.toFixed(2)}"><span class="angel-wheel" style="opacity:${angelOpacity}">🔧</span><span class="angel-pct">${(planIp * 100).toFixed(0)}%</span></span>`;

        const children = allPlans.filter(c => c.parent_plan_id === p.id);
        const isExpanded = state.dashboard.expandedPlans && state.dashboard.expandedPlans[p.id] !== false;
        const toggleBtn = children.length ? `<span class="dash-plan-toggle ${isExpanded ? 'expanded' : ''}" onclick="event.stopPropagation();toggleExpandPlan('${p.id}')">▶</span>` : '';
        const chHtml = children.length ? `<div class="dash-plan-children ${isExpanded ? '' : 'collapsed'}" data-parent="${p.id}">${children.map(c => _renderPlanNode(c, allPlans, dCls, dAttr, selId)).join('')}</div>` : '';
        const tasks = p._tasks || [];
        const tasksHtml = tasks.map(task => {
          const tw = (Number(task.priority_weight) || 0).toFixed(2);
          const th = (Number(task.estimated_hours) || 0).toFixed(1);
          const tIcon = task.status === 'done' ? '✅' : task.status === 'doing' ? '🔄' : task.status === 'blocked' ? '⛔' : '⬜';
          const tDesc = task.description ? `<div class="dash-desc">${escapeHtml(task.description)}</div>` : '';
          return `<div class="dash-task ${dCls}" onclick="event.stopPropagation();toggleTaskStatus({id:'${task.id}', title:'${escapeHtml(task.title).replace(/'/g, "\\'")}', status:'${task.status}'})" title="点击切换状态 (${task.status}→${({todo:'doing', doing:'done', done:'todo', blocked:'todo'})[task.status] || 'todo'})">
            <span class="dash-task-icon">${tIcon}</span>
            <span class="dash-task-title">${escapeHtml(task.title)}</span>
            <span class="dash-task-weight">↘ ${tw}</span>
            <span class="dash-task-hours">${th}h</span>
            <span class="dash-node-edit" onclick="event.stopPropagation();showEditTaskForm('${task.id}','${escapeHtml(task.title).replace(/'/g, "\\'")}','${escapeHtml(task.description||'').replace(/'/g, "\\'")}','${task.cognitive_layer||'K'}','${task.estimated_hours||1}','${task.priority_weight||0.5}')" title="编辑 Task">✎</span>
            <span class="dash-node-del" onclick="event.stopPropagation();deleteEntity('task','${task.id}')" title="删除 Task">✕</span>
            ${tDesc}
          </div>`;
        }).join('');
        return `<div class="dash-plan-wrapper">
          <div class="dash-plan ${isSelected ? 'dash-selected' : ''} ${st.cls} ${dCls}" data-plan-id="${escapeHtml(p.id)}" onclick="selectDashPlan('${p.id}')" title="${escapeHtml(p.description || '')}">
          <div class="dash-plan-row">
            ${toggleBtn}
            <span class="dash-plan-icon">${st.icon}</span>
            <span class="dash-plan-title">${escapeHtml(p.title)}</span>${angelHtml}
            <span class="dash-plan-layer">${_layerBadge(p.cognitive_focus)}</span>${surLbl}${poHtml}${csHtml}${aggrHtml}
            <button class="dash-plan-task-add" onclick="event.stopPropagation();showCreateTaskForm('${p.id}')" title="新建 Task">➕ Task</button>
            <button class="dash-plan-quick ${dCls}" onclick="event.stopPropagation();quickGenDecision('${p.id}')" title="一键调用 Generator" ${dAttr}>⚡</button>
            <span class="dash-node-edit" onclick="event.stopPropagation();showEditPlanForm('${p.id}','${escapeHtml(p.title).replace(/'/g, "\\'")}','${escapeHtml(p.description||'').replace(/'/g, "\\'")}','${p.cognitive_focus||'W'}','${p.priority_weight||0.5}')" title="编辑 Plan">✎</span>
            <span class="dash-node-del" onclick="event.stopPropagation();deleteEntity('plan','${p.id}')" title="删除 Plan">✕</span>
          </div>
          <div class="dash-plan-progress-block">
            <div class="dash-plan-dual-bar">
              <div class="dual-bar-pct" style="width:${prog}%"></div>
              <div class="dual-bar-tasks" style="width:${tProg}%"></div>
            </div>
            <div class="dash-plan-progress-text">${prog}% · ${dCnt}/${tCnt}任务</div>
          </div>
        </div>
        ${tasksHtml ? `<div class="dash-tasks">${tasksHtml}</div>` : '<div class="dash-empty-mini">无 Task</div>'}
        ${chHtml}
        </div>`;
      }
      const goalDesc = goal.description ? `<div class="dash-desc">${escapeHtml(goal.description)}</div>` : '';
      return `<details class="dash-goal" open>
        <summary><span class="dash-goal-icon">●</span>${escapeHtml(goal.title)} <span class="dash-goal-weight" title="权重传播：Goal 权重（用户设定，同 Ideal 下和为 1）→ Plan 继承并重分配 → Task 继承">⚖ ${(goal.priority_weight ?? 0).toFixed(2)}</span><button class="dash-node-add ${disabledCls}" onclick="event.preventDefault();event.stopPropagation();showCreatePlanForm('${goal.id}')" title="新建 Plan" ${disabledAttr}>➕ Plan</button><button class="dash-node-add ${disabledCls}" onclick="event.preventDefault();event.stopPropagation();generatePlansForGoal('${goal.id}')" title="LLM 生成 Plan 方案" ${disabledAttr}>🤖 生成</button><span class="dash-node-edit" onclick="event.stopPropagation();showEditGoalForm('${goal.id}','${escapeHtml(goal.title).replace(/'/g, "\\'")}','${escapeHtml(goal.description||'').replace(/'/g, "\\'")}','${goal.priority_weight||0.33}','${goal.target_layer?.value||'W'}')" title="编辑 Goal">✎</span><span class="dash-node-del" onclick="event.stopPropagation();deleteEntity('goal','${goal.id}')" title="删除 Goal">✕</span></summary>
        ${goalDesc}
        <div class="dash-plans">${plansHtml || '<div class="dash-empty-mini">无 Plan</div>'}</div>
      </details>`;
    }).join('');
    const idealDesc = ideal.description ? `<div class="dash-desc">${escapeHtml(ideal.description)}</div>` : '';
    return `<details class="dash-ideal" open>
      <summary><span class="dash-ideal-icon">★</span>${escapeHtml(ideal.title)}<button class="dash-node-add ${disabledCls}" onclick="event.preventDefault();event.stopPropagation();showCreateGoalForm('${ideal.id}')" title="新建 Goal" ${disabledAttr}>➕ Goal</button><span class="dash-node-edit" onclick="event.stopPropagation();showEditIdealForm('${ideal.id}','${escapeHtml(ideal.title).replace(/'/g, "\\'")}','${escapeHtml(ideal.description||'').replace(/'/g, "\\'")}')" title="编辑 Ideal">✎</span><span class="dash-node-del" onclick="event.stopPropagation();deleteEntity('ideal','${ideal.id}')" title="删除 Ideal">✕</span></summary>
      ${idealDesc}
      <div class="dash-goals">${goalsHtml || '<div class="dash-empty-mini">无 Goal</div>'}</div>
    </details>`;
  }).join('');
}

// ─── 子 Plan 展开/折叠 ───

function toggleExpandPlan(planId) {
  if (!state.dashboard.expandedPlans) state.dashboard.expandedPlans = {};
  state.dashboard.expandedPlans[planId] = !state.dashboard.expandedPlans[planId];
  const children = document.querySelector(`.dash-plan-children[data-parent="${planId}"]`);
  if (children) {
    children.classList.toggle('collapsed');
  }
  const toggle = document.querySelector(`.dash-plan[data-plan-id="${planId}"] .dash-plan-toggle`);
  if (toggle) {
    toggle.classList.toggle('expanded');
  }
}

// ─── Modal 创建表单（Ideal / Goal / Plan） ───

function _showCreateModal(title, html, onSubmit) {
  const overlay = document.getElementById('modalOverlay');
  const modalBody = document.getElementById('modalBody');
  const confirmBtn = document.getElementById('modalConfirm');
  const cancelBtn = document.getElementById('modalCancel');
  const titleEl = document.getElementById('modalTitle');
  const input = document.getElementById('modalInput');
  const dirSelect = document.getElementById('modalDirSelect');
  input.style.display = 'none';
  dirSelect.style.display = 'none';
  const old = modalBody.querySelector('.modal-html-content');
  if (old) old.remove();
  const wrapper = document.createElement('div');
  wrapper.className = 'modal-html-content';
  wrapper.innerHTML = html;
  modalBody.appendChild(wrapper);
  titleEl.textContent = title;
  overlay.classList.add('show');
  setTimeout(() => { const first = wrapper.querySelector('input,select'); if (first) first.focus(); }, 100);
  const newConfirm = confirmBtn.cloneNode(true);
  const newCancel = cancelBtn.cloneNode(true);
  confirmBtn.replaceWith(newConfirm);
  cancelBtn.replaceWith(newCancel);
  newConfirm.textContent = '✓ 创建';
  newCancel.textContent = '✕ 取消';
  function close() { overlay.classList.remove('show'); }
  newCancel.addEventListener('click', close);
  newConfirm.addEventListener('click', async () => {
    newConfirm.disabled = true;
    newConfirm.textContent = '⏳ ...';
    await onSubmit(close);
    newConfirm.disabled = false;
  });
  wrapper.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); newConfirm.click(); }
    if (e.key === 'Escape') { close(); }
  });
}

function showCreateIdealForm() {
  _showCreateModal('新建 Ideal', `
    <input type="text" id="modalFI" placeholder="Ideal 标题" autofocus style="width:100%;box-sizing:border-box">
    <input type="text" id="modalFId" placeholder="描述（可选）" style="width:100%;box-sizing:border-box;margin-top:6px">
  `, async (close) => {
    const title = document.getElementById('modalFI').value.trim();
    if (!title) return;
    const desc = document.getElementById('modalFId').value.trim();
    const res = await client.saberCreateIdeal(title, desc);
    if (res.code !== 0) { _pushCopilotLog('system', `Ideal 创建失败: ${res.msg||''}`); return; }
    _pushCopilotLog('system', `新建 Ideal: ${title}`);
    close();
    await _dashLoadTree();
  });
}

function showCreateGoalForm(idealId) {
  _showCreateModal('新建 Goal', `
    <input type="text" id="modalFG" placeholder="Goal 标题" autofocus style="width:100%;box-sizing:border-box">
    <textarea id="modalFGd" placeholder="描述（可选）" style="width:100%;box-sizing:border-box;margin-top:6px;min-height:50px"></textarea>
    <input type="number" id="modalFGw" placeholder="权重 (0~1)" min="0" max="1" step="0.1" value="0.33" style="width:100%;box-sizing:border-box;margin-top:6px">
  `, async (close) => {
    const title = document.getElementById('modalFG').value.trim();
    if (!title) return;
    const desc = document.getElementById('modalFGd').value.trim();
    const w = parseFloat(document.getElementById('modalFGw').value) || 0.33;
    const res = await client.saberCreateGoal({ideal_id:idealId, title, description:desc, priority_weight:w, target_layer:'W'});
    if (res.code !== 0) { _pushCopilotLog('system', `Goal 创建失败: ${res.msg||''}`); return; }
    _pushCopilotLog('system', `新建 Goal: ${title}`);
    close();
    await _dashLoadTree();
  });
}

function showCreatePlanForm(goalId) {
  _showCreateModal('新建 Plan', `
    <input type="text" id="modalFP" placeholder="Plan 标题" autofocus style="width:100%;box-sizing:border-box">
    <textarea id="modalFPd" placeholder="描述（可选）" style="width:100%;box-sizing:border-box;margin-top:6px;min-height:50px"></textarea>
    <div style="display:flex;gap:6px;margin-top:6px">
      <select id="modalFPl" style="flex:1">${_cogOptions()}</select>
      <input type="number" id="modalFPw" placeholder="权重" min="0" max="1" step="0.1" value="0.5" style="width:80px">
    </div>
  `, async (close) => {
    const title = document.getElementById('modalFP').value.trim();
    if (!title) return;
    const desc = document.getElementById('modalFPd').value.trim();
    const layer = document.getElementById('modalFPl').value;
    const w = parseFloat(document.getElementById('modalFPw').value) || 0.5;
    const res = await client.saberCreatePlan({goal_id:goalId, title, description:desc, cognitive_focus:layer, priority_weight:w});
    if (res.code !== 0) { _pushCopilotLog('system', `Plan 创建失败: ${res.msg||''}`); return; }
    _pushCopilotLog('system', `新建 Plan: ${title} (层级 ${layer})`);
    close();
    await _dashLoadTree();
  });
}

function showCreateTaskForm(planId) {
  _showCreateModal('新建 Task', `
    <input type="text" id="modalFT" placeholder="Task 标题" autofocus style="width:100%;box-sizing:border-box">
    <textarea id="modalFTd" placeholder="描述（可选）" style="width:100%;box-sizing:border-box;margin-top:6px;min-height:50px"></textarea>
    <div style="display:flex;gap:6px;margin-top:6px">
      <select id="modalFTl" style="flex:1">${_cogOptions()}</select>
      <input type="number" id="modalFTh" placeholder="预计小时" min="0" step="0.5" value="1" style="width:80px">
      <input type="number" id="modalFTw" placeholder="权重" min="0" max="1" step="0.1" value="0.5" style="width:70px">
    </div>
  `, async (close) => {
    const title = document.getElementById('modalFT').value.trim();
    if (!title) return;
    const desc = document.getElementById('modalFTd').value.trim();
    const layer = document.getElementById('modalFTl').value;
    const hours = parseFloat(document.getElementById('modalFTh').value) || 1;
    const w = parseFloat(document.getElementById('modalFTw').value) || 0.5;
    const res = await client.saberAddTask(planId, {title, description:desc, goal_id:'', cognitive_layer:layer, estimated_hours:hours, priority_weight:w});
    if (res.code !== 0) { _pushCopilotLog('system', `Task 创建失败: ${res.msg||''}`); return; }
    _pushCopilotLog('system', `新建 Task: ${title}`);
    close();
    await _dashLoadTree();
  });
}

async function deleteEntity(type, id) {
  const labels = {ideal:'Ideal', goal:'Goal', plan:'Plan', task:'Task'};
  if (!await modalConfirm(`确定删除此 ${labels[type]||type}？`)) return;
  const fn = {ideal:client.saberDeleteIdeal, goal:client.saberDeleteGoal, plan:client.saberDeletePlan, task:client.saberDeleteTask}[type];
  if (!fn) return;
  const res = await fn.call(client, id);
  if (res.code !== 0) { _pushCopilotLog('system', `删除失败: ${res.msg||''}`); return; }
  _pushCopilotLog('system', `已删除 ${labels[type]||type}`);
  if (type === 'plan') {
    _archivePlanFadeOut(id);
  } else {
    await _dashLoadTree();
  }
}

// 归档淡出动画：给节点加 archiving class，0.5s 后刷新
function _archivePlanFadeOut(planId) {
  const node = document.querySelector(`.dash-plan[data-plan-id="${planId}"]`);
  if (node) {
    node.classList.add('archiving');
    setTimeout(() => _dashLoadTree(), 500);
  } else {
    _dashLoadTree();
  }
}

function showEditIdealForm(id, title, desc) {
  _showCreateModal('编辑 Ideal', `
    <input type="text" id="modalEI" value="${escapeHtml(title)}" autofocus style="width:100%;box-sizing:border-box">
    <input type="text" id="modalEId" value="${escapeHtml(desc||'')}" style="width:100%;box-sizing:border-box;margin-top:6px">
  `, async (close) => {
    const t = document.getElementById('modalEI').value.trim();
    if (!t) return;
    const d = document.getElementById('modalEId').value.trim();
    const res = await client.saberUpdateIdeal(id, {title:t, description:d});
    if (res.code !== 0) { _pushCopilotLog('system', `编辑失败: ${res.msg||''}`); return; }
    _pushCopilotLog('system', `已更新 Ideal: ${t}`);
    close();
    await _dashLoadTree();
  });
}

function showEditGoalForm(id, title, desc, weight, layer) {
  _showCreateModal('编辑 Goal', `
    <input type="text" id="modalEG" value="${escapeHtml(title)}" autofocus style="width:100%;box-sizing:border-box">
    <textarea id="modalEGd" placeholder="描述（可选）" style="width:100%;box-sizing:border-box;margin-top:6px;min-height:50px">${escapeHtml(desc||'')}</textarea>
    <input type="number" id="modalEGw" value="${weight||0.33}" min="0" max="1" step="0.1" style="width:100%;box-sizing:border-box;margin-top:6px">
    <select id="modalEGl" style="width:100%;box-sizing:border-box;margin-top:6px">${_cogOptions(layer)}</select>
  `, async (close) => {
    const t = document.getElementById('modalEG').value.trim();
    if (!t) return;
    const d = document.getElementById('modalEGd').value.trim();
    const w = parseFloat(document.getElementById('modalEGw').value) || 0.33;
    const l = document.getElementById('modalEGl').value;
    const res = await client.saberUpdateGoal(id, {title:t, description:d, priority_weight:w, target_layer:l});
    if (res.code !== 0) { _pushCopilotLog('system', `编辑失败: ${res.msg||''}`); return; }
    _pushCopilotLog('system', `已更新 Goal: ${t}`);
    close();
    await _dashLoadTree();
  });
}

function showEditPlanForm(id, title, desc, layer, weight) {
  _showCreateModal('编辑 Plan', `
    <input type="text" id="modalEP" value="${escapeHtml(title)}" autofocus style="width:100%;box-sizing:border-box">
    <textarea id="modalEPd" placeholder="描述（可选）" style="width:100%;box-sizing:border-box;margin-top:6px;min-height:50px">${escapeHtml(desc||'')}</textarea>
    <div style="display:flex;gap:6px;margin-top:6px">
      <select id="modalEPl" style="flex:1">${_cogOptions(layer)}</select>
      <input type="number" id="modalEPw" value="${weight||0.5}" min="0" max="1" step="0.1" style="width:80px">
    </div>
  `, async (close) => {
    const t = document.getElementById('modalEP').value.trim();
    if (!t) return;
    const d = document.getElementById('modalEPd').value.trim();
    const l = document.getElementById('modalEPl').value;
    const w = parseFloat(document.getElementById('modalEPw').value) || 0.5;
    const res = await client.saberUpdatePlan(id, {title:t, description:d, cognitive_focus:l, priority_weight:w});
    if (res.code !== 0) { _pushCopilotLog('system', `编辑失败: ${res.msg||''}`); return; }
    _pushCopilotLog('system', `已更新 Plan: ${t}`);
    close();
    await _dashLoadTree();
  });
}

function showEditTaskForm(id, title, desc, layer, hours, weight) {
  _showCreateModal('编辑 Task', `
    <input type="text" id="modalET" value="${escapeHtml(title)}" autofocus style="width:100%;box-sizing:border-box">
    <textarea id="modalETd" placeholder="描述（可选）" style="width:100%;box-sizing:border-box;margin-top:6px;min-height:50px">${escapeHtml(desc||'')}</textarea>
    <div style="display:flex;gap:6px;margin-top:6px">
      <select id="modalETl" style="flex:1">${_cogOptions(layer)}</select>
      <input type="number" id="modalETh" value="${hours||1}" min="0" step="0.5" style="width:80px">
      <input type="number" id="modalETw" value="${weight||0.5}" min="0" max="1" step="0.1" style="width:70px">
    </div>
  `, async (close) => {
    const t = document.getElementById('modalET').value.trim();
    if (!t) return;
    const d = document.getElementById('modalETd').value.trim();
    const l = document.getElementById('modalETl').value;
    const h = parseFloat(document.getElementById('modalETh').value) || 1;
    const w = parseFloat(document.getElementById('modalETw').value) || 0.5;
    const res = await client.saberUpdateTask(id, {title:t, description:d, cognitive_layer:l, estimated_hours:h, priority_weight:w});
    if (res.code !== 0) { _pushCopilotLog('system', `编辑失败: ${res.msg||''}`); return; }
    _pushCopilotLog('system', `已更新 Task: ${t}`);
    close();
    await _dashLoadTree();
  });
}

async function toggleTaskStatus(task) {
  const cycle = {todo:'doing', doing:'done', done:'todo', blocked:'todo'};
  const next = cycle[task.status] || 'todo';
  const res = await client.saberUpdateTask(task.id, {status: next});
  if (res.code !== 0) { _pushCopilotLog('system', `Task 状态更新失败: ${res.msg||''}`); return; }
  _pushCopilotLog('system', `Task "${task.title}" → ${next}`);
  await _dashLoadTree();
  loadPushDashboard();
  loadTasks();
}

// ─── quickGenDecision：不依赖选中，可传 planId；未传则用 selectedPlanId 或第一个 Plan ───

async function quickGenDecision(planId) {
  // 1. 优先使用传入的 planId
  let targetPlanId = planId;
  // 2. 否则使用 selectedPlanId
  if (!targetPlanId) targetPlanId = state.dashboard.selectedPlanId;
  // 3. 否则自动选第一个 Plan
  if (!targetPlanId) {
    const firstPlan = _findFirstPlan();
    if (firstPlan) {
      targetPlanId = firstPlan.id;
      selectDashPlan(firstPlan.id);
      _pushCopilotLog('agent', `自动选中第一个 Plan: ${firstPlan.title}`);
    } else {
      _pushCopilotLog('agent', '⚠️ 没有 Plan，请先点击 ➕ Ideal 创建');
      _renderDecisionCard('没有 Plan，请先在左侧点击 ➕ Ideal 创建');
      return;
    }
  } else if (targetPlanId !== state.dashboard.selectedPlanId) {
    selectDashPlan(targetPlanId);
  }
  // 调用 Generator
  const btn = document.getElementById('hudAgentBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⚡ 调用中...'; }
  const focusBtn = document.getElementById('dashGenDecision');
  if (focusBtn) { focusBtn.disabled = true; focusBtn.textContent = '调用中...'; }
  try {
    const res = await client.saberGenerateDecision(targetPlanId);
    if (res.code === 0) {
      state.dashboard.currentDecision = res.data;
      _pushCopilotLog('agent', `⚡ Generator 生成决策点 (plan=${targetPlanId.slice(0,8)})`);
      _renderDecisionCard();
      _dashLoadIntensity(targetPlanId);
      // 高亮 + 滚动到决策卡
      _flashDecisionCard();
    } else {
      state.dashboard.currentDecision = null;
      _renderDecisionCard(res.msg || '生成失败');
    }
  } catch (e) {
    state.dashboard.currentDecision = null;
    _renderDecisionCard(e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '⚡ Agent'; }
    if (focusBtn) { focusBtn.disabled = false; focusBtn.textContent = '⚡ 调用 Generator'; }
  }
}

function _findFirstPlan() {
  for (const ideal of state.dashboard.ideals) {
    for (const goal of (ideal._goals || [])) {
      for (const plan of (goal._plans || [])) {
        return plan;
      }
    }
  }
  return null;
}

function _flashDecisionCard() {
  const container = document.getElementById('focusDecision');
  if (!container) return;
  container.classList.add('focus-decision-active');
  container.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => container.classList.remove('focus-decision-active'), 4000);
}

function selectDashPlan(planId) {
  // 在已加载的 ideals 中查找 plan
  let foundPlan = null;
  for (const ideal of state.dashboard.ideals) {
    for (const goal of (ideal._goals || [])) {
      for (const plan of (goal._plans || [])) {
        if (plan.id === planId) { foundPlan = plan; break; }
      }
    }
  }
  state.dashboard.selectedPlanId = planId;
  state.dashboard.selectedPlan = foundPlan;
  state.dashboard.currentDecision = null;
  // 选中 Plan 时自动展开焦点浮层
  const focusEl = document.getElementById('dashFocusOverlay');
  if (focusEl && focusEl.classList.contains('overlay-hidden')) {
    focusEl._hoverPinned = true;
    _toggleOverlay('dashFocusOverlay');
  }
  // 仅更新选中高亮（增量），不重绘整棵树
  const tree = document.getElementById('dashTreeList');
  if (tree) {
    tree.querySelectorAll('.dash-selected').forEach(el => el.classList.remove('dash-selected'));
    const sel = tree.querySelector(`[data-plan-id="${planId}"]`);
    if (sel) sel.classList.add('dash-selected');
  }
  _renderHud();
  _renderFocusPanel();
  _dashLoadIntensity(planId);
}

// ─── 右侧焦点面板渲染 ───

function _renderFocusPanel() {
  const plan = state.dashboard.selectedPlan;
  const titleEl = document.getElementById('focusTitle');
  const metaEl = document.getElementById('focusMeta');
  const tasksEl = document.getElementById('focusTasks');
  const constraintsEl = document.getElementById('focusConstraints');
  const ragEl = document.getElementById('focusRag');
  const decisionEl = document.getElementById('focusDecision');

  if (!plan) {
    titleEl.textContent = '未选择 Plan';
    metaEl.textContent = '点击左侧 Plan 节点查看详情';
    tasksEl.innerHTML = '<div class="dash-empty">选择 Plan 后显示任务</div>';
    constraintsEl.innerHTML = '<div class="dash-empty">无约束</div>';
    ragEl.innerHTML = '<div class="dash-empty">选择 Plan 后显示 RAG 检索片段</div>';
    decisionEl.innerHTML = '<div class="dash-empty">选择一个 Plan 后点击"生成决策"</div>';
    return;
  }
  titleEl.textContent = plan.title;
  const descEl = document.getElementById('focusPlanDesc');
  if (descEl) descEl.textContent = plan.description || '';
  const progress = ((plan.aggregated_progress ?? 0) * 100).toFixed(0);
  const life = state.dashboard.life;
  const lifeInfo = life ? ` · 已用 ${life.waking_hours_used?.toFixed(1) ?? 0}h` : '';
  // 偏序信息
  const preds = plan.predecessors || [];
  const succs = plan.successors || [];
  const poInfo = [];
  if (preds.length) poInfo.push(`⬅ ${preds.length} 前驱`);
  if (succs.length) poInfo.push(`➡ ${succs.length} 后继`);
  const poStr = poInfo.length ? ` · ${poInfo.join(' ')}` : '';
  metaEl.textContent = `层级 ${_layerLabel(plan.cognitive_focus)} · 进度 ${progress}%${lifeInfo}${poStr}`;
  // 创建任务按钮（独立于看板，避免拉伸变形）
  const toolbarEl = document.getElementById('focusTasksToolbar');
  if (toolbarEl) {
    toolbarEl.innerHTML = `<button class="dash-plan-task-add" onclick="createTaskForPlan()" title="新建任务">➕ 新建任务</button>`;
  }

  // 任务看板
  const tasks = plan._tasks || plan.tasks || [];
  if (tasks.length === 0) {
    tasksEl.innerHTML = `<div class="dash-empty">暂无任务</div>`;
  } else {
    const todo = tasks.filter(t => t.status === 'todo');
    const doing = tasks.filter(t => t.status === 'doing');
    const done = tasks.filter(t => t.status === 'done');
    tasksEl.innerHTML = `
      <div class="kanban-col"><div class="kanban-col-title">待办 (${todo.length})</div>${todo.map(_taskCard).join('')}</div>
      <div class="kanban-col"><div class="kanban-col-title">进行 (${doing.length})</div>${doing.map(_taskCard).join('')}</div>
      <div class="kanban-col"><div class="kanban-col-title">完成 (${done.length})</div>${done.map(_taskCard).join('')}</div>
    `;
  }
  // 约束 + 拓扑
  _renderTopologyInfo(plan);
  // RAG 注入预览：尝试检索，无 API 时显示占位
  _renderRagPreview(plan);
  // 决策点
  _renderDecisionCard();
}

function _renderTopologyInfo(plan) {
  const el = document.getElementById('focusConstraints');
  if (!el) return;
  const topo = state.dashboard.topology;
  const viol = state.dashboard.violations;
  let html = '';
  // 偏序
  const preds = plan.predecessors || [];
  const succs = plan.successors || [];
  if (preds.length) {
    html += `<div class="topo-section"><span class="topo-label">⬅ 前驱</span> ${preds.join(', ')}</div>`;
  }
  if (succs.length) {
    html += `<div class="topo-section"><span class="topo-label">➡ 后继</span> ${succs.join(', ')}</div>`;
  }
  // 拓扑排序
  if (topo && topo.topological_order && topo.topological_order.length) {
    html += `<div class="topo-section"><span class="topo-label">拓扑序</span> ${topo.topological_order.slice(0, 6).join(' → ')}${topo.topological_order.length > 6 ? '...' : ''}</div>`;
  }
  // 关键路径
  if (topo && topo.critical_path && topo.critical_path.length) {
    html += `<div class="topo-section"><span class="topo-label">关键路径</span> <span class="topo-critical">${topo.critical_path.join(' → ')}</span></div>`;
  }
  // 循环依赖
  if (topo && topo.has_cycle) {
    html += `<div class="topo-section topo-violation"><span class="topo-label">🔴 循环依赖</span> ${(topo.cycle_path || []).join(' → ')}</div>`;
  }
  // 违规
  if (viol && viol.violations && viol.violations.length) {
    html += `<div class="topo-section topo-violation"><span class="topo-label">🔴 违规</span></div>`;
    for (const v of viol.violations) {
      html += `<div class="topo-violation-item">${escapeHtml(v.message)}</div>`;
    }
  }
  if (!html) {
    html = '<div class="dash-empty">无偏序关系</div>';
    // 尝试异步加载拓扑
    _fetchTopologyAsync(plan.id);
  }
  el.innerHTML = html;
}

async function _fetchTopologyAsync(planId) {
  try {
    const [topoRes, violRes] = await Promise.all([
      client.api_get(`/api/saber/plans/${planId}/topology`),
      client.api_get(`/api/saber/plans/${planId}/violations`),
    ]);
    if (topoRes.code === 0) state.dashboard.topology = topoRes.data;
    if (violRes.code === 0) state.dashboard.violations = violRes.data;
    // 重新渲染拓扑
    if (state.dashboard.selectedPlan && state.dashboard.selectedPlan.id === planId) {
      _renderTopologyInfo(state.dashboard.selectedPlan);
    }
  } catch (e) {
    // 忽略
  }
}

async function _renderRagPreview(plan) {
  const ragEl = document.getElementById('focusRag');
  if (!ragEl) return;
  // 后端 RAG API 未就绪，先显示占位+计划对接
  const query = plan.title + ' ' + (plan.description || '');
  ragEl.innerHTML = `<div class="dash-empty">🔄 检索中... <code>${escapeHtml(query.slice(0, 40))}</code></div>`;
  try {
    // 尝试调用 RAG 检索 API（后端未实现时 404）
    const res = await fetch(`${API_BASE}/api/saber/rag/search?q=${encodeURIComponent(query)}&limit=3`);
    if (!res.ok) throw new Error('RAG API 未就绪');
    const data = await res.json();
    const hits = (data.data || data.hits || []).slice(0, 3);
    if (hits.length === 0) {
      ragEl.innerHTML = '<div class="dash-empty">无命中片段</div>';
      return;
    }
    ragEl.innerHTML = hits.map(h => `
      <div class="rag-hit">
        <div class="rag-hit-source">${escapeHtml(h.source || h.title || '未知来源')}</div>
        <div class="rag-hit-snippet">${escapeHtml((h.snippet || h.content || '').slice(0, 120))}...</div>
        <div class="rag-hit-score">相关度 ${((h.score ?? 0) * 100).toFixed(0)}%</div>
      </div>
    `).join('');
    _pushCopilotLog('rag', `检索 "${query.slice(0, 20)}..." 命中 ${hits.length} 片段`);
  } catch (e) {
    ragEl.innerHTML = `<div class="dash-empty">🌌 万有 RAG 系统待接入（工期4）<br><span style="font-size:10px;color:var(--fg-muted)">查询：<code>${escapeHtml(query.slice(0, 50))}</code></span></div>`;
  }
}

function _taskCard(t) {
  const statusIcon = t.status === 'done' ? '✅' : t.status === 'doing' ? '🔄' : '⏳';
  const deliveryBadge = t.delivered_at ? ' 📦' : '';
  const gitBadge = t.git_diff_summary ? ' 🔗' : '';
  const verifiedBadge = t.verified_at ? ' ✓' : '';
  const tDesc = t.description ? `<div class="task-card-desc">${escapeHtml(t.description)}</div>` : '';
  return `<div class="task-card" data-task-id="${t.id}">
    <div class="task-card-title">${statusIcon} ${escapeHtml(t.title)}${deliveryBadge}${gitBadge}${verifiedBadge}</div>
    ${tDesc}
    <div class="task-card-meta">${Number(t.estimated_hours) || 0}h · ${_layerBadge(t.cognitive_layer)} · ${t.status}</div>
    <div class="task-card-actions">
      ${t.status === 'doing' ? `<button class="tcb-btn" onclick="deliverTask('${t.id}')" title="交付任务">📦 交付</button>` : ''}
      ${t.status === 'todo' ? `<button class="tcb-btn" onclick="updateTaskStatus('${t.id}','doing')" title="开始">▶️ 开始</button>` : ''}
      ${t.status === 'todo' ? `<button class="tcb-btn" onclick="updateTaskStatus('${t.id}','blocked')" title="阻塞">⛔ 阻塞</button>` : ''}
      ${t.status === 'doing' ? `<button class="tcb-btn" onclick="updateTaskStatus('${t.id}','todo')" title="放回待办">↩️ 放回</button>` : ''}
      ${(Number(t.estimated_hours) || 0) > 0 ? `<button class="tcb-btn" onclick="startTaskTimer(${Number(t.estimated_hours) * 60})" title="计时 ${t.estimated_hours}h">⏱</button>` : (t.duration ? `<button class="tcb-btn" onclick="startTaskTimer(${t.duration})" title="计时 ${t.duration}min">⏱</button>` : '')}
      <button class="tcb-btn" onclick="startGitTracking('${t.id}')" title="开始 Git 追踪">🔗 Git</button>
      <button class="tcb-btn" onclick="captureGitDiff('${t.id}')" title="捕获 Diff">📝 Diff</button>
      <button class="tcb-btn-edit" onclick="showEditTaskForm('${t.id}','${escapeHtml(t.title).replace(/'/g, "\\'")}','${escapeHtml(t.description||'').replace(/'/g, "\\'")}','${t.cognitive_layer||'K'}','${t.estimated_hours||1}','${t.priority_weight||0.5}')" title="编辑">✏️</button>
      <button class="tcb-btn-del" onclick="deleteTask('${t.id}')" title="删除">🗑️</button>
    </div>
  </div>`;
}

// ─── 任务 CRUD 操作 ───

async function updateTaskStatus(taskId, status) {
  const res = await client.saberUpdateTask(taskId, { status });
  if (res.code === 0) {
    await loadDashboard();
  } else {
    await modalAlert(`状态更新失败: ${res.msg}`);
  }
}

async function deliverTask(taskId) {
  const artifacts = await modalPrompt('交付物路径（逗号分隔，可选）:');
  const notes = await modalPrompt('交付备注（可选）:');
  const artifactsList = artifacts ? artifacts.split(',').map(s => s.trim()).filter(Boolean) : [];
  const res = await client.saberDeliverTask(taskId, artifactsList, notes || '');
  if (res.code === 0) {
    await loadDashboard();
  } else {
    await modalAlert(`交付失败: ${res.msg}`);
  }
}

async function startGitTracking(taskId) {
  const res = await client.saberStartGitTracking(taskId);
  if (res && res.code === 0) {
    await modalAlert(`Git 追踪已启动` + (res.data.commit_sha ? `，起点: ${res.data.commit_sha}` : ''));
    await loadDashboard();
  } else {
    await modalAlert(`Git 追踪失败: ${(res && res.msg) || '请求失败'}`);
  }
}

async function captureGitDiff(taskId) {
  const res = await client.saberCaptureGitDiff(taskId);
  if (res && res.code === 0) {
    await modalAlert(`已捕获 Diff (${res.data.diff_length} 行)`);
    await loadDashboard();
  } else {
    await modalAlert(`Diff 捕获失败: ${(res && res.msg) || '请求失败'}`);
  }
}

async function editTask(taskId) {
  const plan = state.dashboard.selectedPlan;
  if (!plan) return;
  const task = (plan._tasks || plan.tasks || []).find(t => t.id === taskId);
  if (!task) return;
  const title = await modalPrompt('任务标题:', task.title);
  if (!title) return;
  const hours = await modalPrompt('预计小时:', task.estimated_hours || '1');
  const res = await client.saberUpdateTask(taskId, { title, estimated_hours: parseFloat(hours) || 1 });
  if (res.code === 0) {
    await loadDashboard();
  } else {
    await modalAlert(`编辑失败: ${res.msg}`);
  }
}

async function deleteTask(taskId) {
  if (!await modalConfirm('确定删除此任务？')) return;
  const res = await client.saberDeleteTask(taskId);
  if (res.code === 0) {
    await loadDashboard();
  } else {
    await modalAlert(`删除失败: ${res.msg}`);
  }
}

async function createTaskForPlan() {
  const plan = state.dashboard.selectedPlan;
  if (!plan) { await modalAlert('请先选择 Plan'); return; }
  const title = await modalPrompt('新任务标题:');
  if (!title) return;
  const hours = await modalPrompt('预计小时:', '1');
  const layer = await modalPrompt('认知层级 (K=知识 C=概念 T=理论 S=技能 W=工作流):', plan.cognitive_focus || 'T');
  const res = await client.saberCreateTask(plan.id, {
    title, estimated_hours: parseFloat(hours) || 1,
    cognitive_layer: layer || 'T',
    description: '', goal_id: plan.goal_id || '',
    status: 'todo', priority_weight: 1.0,
  });
  if (res.code === 0) {
    await loadDashboard();
  } else {
    await modalAlert(`创建失败: ${res.msg}`);
  }
}

// ─── 决策点渲染（按钮式 + 置信度分级 + 天使提醒） ───

async function _dashLoadIntensity(planId) {
  const res = await client.saberGetIntensity(planId);
  if (res.code === 0) {
    state.dashboard.intensity = res.data;
    _renderHudIntensity(res.data);
  } else {
    _renderHudIntensity(null);
  }
}

async function generatePlansForGoal(goalId) {
  const res = await client.saberGeneratePlans(goalId);
  if (res.code !== 0) {
    await modalAlert(`生成失败: ${res.msg}`);
    return;
  }
  const suggestions = res.data?.suggestions || [];
  if (suggestions.length === 0) {
    await modalAlert('LLM 未返回任何 Plan 建议');
    return;
  }
  const lines = suggestions.map((s, i) =>
    `${i+1}. ${escapeHtml(s.title)} [${s.cognitive_focus || 'T'}] · ⚖ ${(s.priority_weight ?? 0.5).toFixed(2)}\n   ${escapeHtml(s.description || '')}`
  );
  const msg = `LLM 生成了 ${suggestions.length} 个 Plan 方案：\n\n${lines.join('\n\n')}\n\n输入编号创建对应 Plan（逗号分隔，如 1,2,3），或留空取消：`;
  const input = await modalPrompt(msg);
  if (!input) return;
  const indices = input.split(',').map(s => parseInt(s.trim()) - 1).filter(i => i >= 0 && i < suggestions.length);
  for (const idx of indices) {
    const s = suggestions[idx];
    const createRes = await client.saberCreatePlan({
      title: s.title, description: s.description || '',
      goal_id: goalId,
      cognitive_focus: s.cognitive_focus || 'T',
      priority_weight: s.priority_weight ?? 0.5,
    });
    if (createRes.code !== 0) {
      await modalAlert(`创建 Plan「${s.title}」失败: ${createRes.msg}`);
    }
  }
  await loadDashboard();
}

async function generateDashDecision() {
  // 焦点面板按钮 → 转发到 quickGenDecision（统一入口）
  await quickGenDecision();
}

function _renderDecisionCard(errorMsg) {
  const container = document.getElementById('focusDecision');
  const dp = state.dashboard.currentDecision;
  if (errorMsg) {
    container.innerHTML = `<div class="dash-empty dash-error">⚠️ ${escapeHtml(errorMsg)}</div>`;
    return;
  }
  if (dp === null) {
    const intensity = state.dashboard.intensity;
    if (intensity && intensity.retired) {
      container.innerHTML = '<div class="dash-empty dash-retired-msg">Agent 已退役（熟练度过高），请自主决策</div>';
    } else {
      container.innerHTML = '<div class="dash-empty dash-burned-msg">⚠️ 生命资本透支，请先 [🛌 休息]</div>';
    }
    return;
  }
  if (!dp) {
    container.innerHTML = '<div class="dash-empty">选择一个 Plan 后点击"生成决策"</div>';
    return;
  }
  // 健康硬约束：burned_out 时非休息类选项置灰
  const life = state.dashboard.life;
  const burnedOut = life && life.health && (typeof life.health.is_burned_out === 'function' ? life.health.is_burned_out() : life.health.is_burned_out);
  const isRestOption = (opt) => {
    const desc = (opt.description || '').toLowerCase();
    return desc.includes('休息') || desc.includes('sleep') || desc.includes('recover') || (opt.tags || []).includes('rest');
  };
  // 按置信度分级：推荐(≥0.7) / 可选(0.4~0.69) / 折叠(<0.4)
  const options = dp.options || [];
  const recommended = options.filter(o => (o.confidence ?? 0) >= 0.7);
  const optional = options.filter(o => ((o.confidence ?? 0) >= 0.4 && (o.confidence ?? 0) < 0.7));
  const lowConf = options.filter(o => (o.confidence ?? 0) < 0.4);

  // 检测天使提醒触发条件
  const angelHint = _detectAngelHint(options);

  const optsHtml = (opts, label, cls) => opts.map(opt => {
    // 三行机会成本分明：消耗 / 错过 / 盈余影响
    const consumeParts = [];
    if (opt.attention_cost) consumeParts.push(`注意力 -${opt.attention_cost.toFixed(2)}`);
    if (opt.energy_cost) consumeParts.push(`体能 -${opt.energy_cost.toFixed(2)}`);
    const consumeLine = consumeParts.length ? consumeParts.join(' ｜ ') : '无消耗';
    const missedList = opt.missed_opportunities || [];
    const missedLine = missedList.length ? missedList.slice(0, 2).map(m => escapeHtml(typeof m === 'string' ? m : (m.title || JSON.stringify(m)))).join('、') : '无错失';
    const surplusLine = opt.surplus_delta != null ? `盈余 ${opt.surplus_delta > 0 ? '+' : ''}${opt.surplus_delta.toFixed(1)}h` : '盈余不变';
    const confPct = ((opt.confidence ?? 0) * 100).toFixed(0);
    // 健康硬约束：burned_out 时非休息类置灰
    const disabled = burnedOut && !isRestOption(opt);
    const disabledCls = disabled ? 'opt-disabled' : '';
    const disabledAttr = disabled ? 'disabled' : '';
    const disabledTip = disabled ? ' title="⚠️ 生命透支中，仅休息类选项可用，请先 [🛌 休息]"' : '';
    return `<div class="dash-option ${cls} ${disabledCls}">
      <div class="dash-option-header">
        <span class="dash-option-label">${label}</span>
        <span class="dash-option-confidence">置信度 ${confPct}%</span>
      </div>
      <div class="dash-option-desc">${escapeHtml(opt.description)}</div>
      ${opt.rationale ? `<div class="dash-option-rationale">${escapeHtml(opt.rationale)}</div>` : ''}
      ${opt.estimated_impact ? `<div class="dash-option-impact">→ ${escapeHtml(opt.estimated_impact)}</div>` : ''}
      <div class="dash-option-cost-lines">
        <div class="cost-line cost-consume">⏳ 消耗：${consumeLine}</div>
        <div class="cost-line cost-missed">🌌 错过：${missedLine}</div>
        <div class="cost-line cost-surplus">💰 ${surplusLine}</div>
      </div>
      <div class="dash-option-actions">
        <button class="dash-btn-primary" onclick="adoptDashDecision('${opt.id}', true, 0.1)" ${disabledAttr}${disabledTip}>📌 选这个</button>
        <button class="dash-btn-mini" onclick="showCustomizeBox('${opt.id}')" ${disabledAttr}>📝 自定义修改</button>
      </div>
      <div class="dash-customize-box" id="customize-${opt.id}" style="display:none">
        <input type="number" id="modRatio-${opt.id}" placeholder="修改比例 0~1" min="0" max="1" step="0.1" value="0.3">
        <button class="dash-btn-mini" onclick="adoptDashDecision('${opt.id}', true, parseFloat(document.getElementById('modRatio-${opt.id}').value || 0.3))">提交修改</button>
        <button class="dash-btn-mini" onclick="adoptDashDecision('${opt.id}', false, 0.8)">不采纳</button>
      </div>
    </div>`;
  }).join('');

  container.innerHTML = `
    <div class="dash-dp-context">${escapeHtml(dp.context_snapshot || '')}</div>
    <div class="dash-dp-intensity">介入度 I(P)=${(dp.agent_intensity ?? 0).toFixed(2)}${burnedOut ? ' · ⚠️ 生命透支' : ''}</div>
    ${burnedOut ? '<div class="dash-burned-warning">⚠️ 健康硬约束生效：仅休息类选项可点击，请先 [🛌 休息]</div>' : ''}
    ${angelHint ? `<div class="dash-angel-hint">💡 ${escapeHtml(angelHint)}</div>` : ''}
    ${recommended.length ? `<div class="dash-options-group"><div class="dash-options-group-title">推荐</div>${optsHtml(recommended, '推荐', 'opt-recommended')}</div>` : ''}
    ${optional.length ? `<div class="dash-options-group"><div class="dash-options-group-title">可选</div>${optsHtml(optional, '可选', 'opt-optional')}</div>` : ''}
    ${lowConf.length ? `<details class="dash-options-group"><summary>其他选项 (${lowConf.length})</summary>${optsHtml(lowConf, '参考', 'opt-low')}</details>` : ''}
    <div style="margin-top:6px;text-align:center"><button class="dash-btn" onclick="openAgentChat()">💬 自由对话</button></div>
  `;
}

function _detectAngelHint(options) {
  // 检测负盈余 / 健康损害
  for (const opt of options) {
    if (opt.surplus_delta && opt.surplus_delta < 0) {
      return `选项 "${opt.description}" 会让今天的自由盈余降为 ${opt.surplus_delta.toFixed(1)}h`;
    }
    if (opt.energy_cost && opt.energy_cost > 0.3) {
      return `选项 "${opt.description}" 体能消耗 ${opt.energy_cost.toFixed(2)} 较大`;
    }
  }
  return null;
}

function showCustomizeBox(optId) {
  const box = document.getElementById(`customize-${optId}`);
  if (box) {
    box.style.display = box.style.display === 'none' ? 'block' : 'none';
  }
}

async function adoptDashDecision(optionId, wasAdopted, modificationRatio) {
  const dp = state.dashboard.currentDecision;
  if (!dp) return;
  // 健康硬约束检测：burned_out 时强行采纳非休息类选项 → 记录 self_destructive_choices
  const life = state.dashboard.life;
  const burnedOut = life && life.health && (typeof life.health.is_burned_out === 'function' ? life.health.is_burned_out() : life.health.is_burned_out);
  const opt = (dp.options || []).find(o => o.id === optionId);
  const isRestOption = opt && (
    (opt.description || '').toLowerCase().includes('休息') ||
    (opt.tags || []).includes('rest')
  );
  if (burnedOut && wasAdopted && !isRestOption) {
    // 强行绕过：留痕（不阻塞用户行为，但记 system 日志）
    state.dashboard.selfDestructiveChoices = (state.dashboard.selfDestructiveChoices || 0) + 1;
    state.dashboard.trustScore = Math.max(0, (state.dashboard.trustScore ?? 1.0) - 0.1);
    _pushCopilotLog('system', `⚠️ 强行绕过健康硬约束！self_destructive_choices=${state.dashboard.selfDestructiveChoices}，trust_score 降至 ${state.dashboard.trustScore.toFixed(2)}`);
  }
  const res = await client.saberSelectDecision(dp.id, optionId, wasAdopted, modificationRatio);
  if (res.code === 0) {
    const newP = res.data?.proficiency_new;
    const action = res.data?.action || {};
    const actionMsg = action.created_tasks ? ` ✅ 创建 ${action.created_tasks} 个 Task` : action.rest_hours ? ` ☕ 休息 ${(action.rest_hours * 60).toFixed(0)}min` : action.switched_to_task ? ` 🔄 切换到 ${action.switched_to_task}` : '';
    _pushCopilotLog('agent', `采纳决策 (adopted=${wasAdopted}, mod=${modificationRatio.toFixed(2)}) → P=${newP?.toFixed(2) ?? '?'}${actionMsg}`);
    state.dashboard.currentDecision = null;
    _renderDecisionCard();
    if (state.dashboard.selectedPlanId) _dashLoadIntensity(state.dashboard.selectedPlanId);
    if (action.created_tasks || action.progress_boost) await _dashLoadTree();
  } else {
    _pushCopilotLog('system', `决策选择失败: ${res.msg || '未知'}`);
  }
}

async function recoverDashAttention() {
  const hours = parseFloat(document.getElementById('dashRecoverHours').value) || 1;
  const quality = parseFloat(document.getElementById('dashRecoverQuality').value) || 1;
  const res = await client.saberRecoverAttention('default', hours, quality);
  if (res.code === 0) {
    _pushCopilotLog('life', `休息恢复 ${hours}h (质量 ${quality})`);
    await _dashLoadLife();
  } else {
    _pushCopilotLog('system', `恢复失败: ${res.msg || '未知'}`);
  }
}

// ─── Agent 自由对话 ───

async function openAgentChat() {
  const plan = state.dashboard.selectedPlan;
  if (!plan) { await modalAlert('请先选择 Plan'); return; }
  const msg = await modalPrompt('💬 自由对话: 你想和 Agent 讨论什么？');
  if (!msg) return;
  const res = await client.saberAgentChat(plan.id, msg);
  if (res && res.code === 0) {
    const replyEl = document.createElement('div');
    replyEl.className = 'dash-agent-reply';
    replyEl.innerHTML = `<div class="dash-agent-msg">🤖 ${escapeHtml(res.data.reply)}</div>`;
    const focusDecision = document.getElementById('focusDecision');
    if (focusDecision) focusDecision.appendChild(replyEl);
    _pushCopilotLog('agent', res.data.reply.substring(0, 100));
  } else {
    await modalAlert(`对话失败: ${(res && res.msg) || '请求错误'}`);
  }
}

// ─── 副驾驶日志 ───

function _pushCopilotLog(tag, content) {
  state.dashboard.copilotLogs.unshift({ tag, content, time: new Date() });
  if (state.dashboard.copilotLogs.length > 100) state.dashboard.copilotLogs.pop();
  _renderCopilotLog();
}

function _renderCopilotLog() {
  const logs = state.dashboard.copilotLogs;
  const counts = { system: 0, agent: 0, rag: 0, life: 0, opportunity: 0 };
  logs.forEach(l => { counts[l.tag] = (counts[l.tag] || 0) + 1; });
  document.getElementById('copilotCountSystem').textContent = counts.system;
  document.getElementById('copilotCountAgent').textContent = counts.agent;
  document.getElementById('copilotCountRag').textContent = counts.rag;
  document.getElementById('copilotCountLife').textContent = counts.life;
  document.getElementById('copilotCountOpp').textContent = counts.opportunity;
  // 最新一条摘要
  const summary = document.getElementById('copilotLogSummary');
  if (logs.length > 0) {
    const latest = logs[0];
    const tagIcons = { system: '⚖️', agent: '🤝', rag: '🌌', life: '⏳', opportunity: '🌌' };
    summary.textContent = `${tagIcons[latest.tag] || '📡'} ${latest.content}`;
  } else {
    summary.textContent = '📡 副驾驶日志（点击展开）';
  }
  // 展开时渲染列表
  const list = document.getElementById('copilotLogList');
  if (!state.dashboard.copilotCollapsed) {
    const tagIcons = { system: '⚖️', agent: '🤝', rag: '🌌', life: '⏳', opportunity: '🌌' };
    list.innerHTML = logs.slice(0, 30).map(l => {
      const t = l.time instanceof Date ? l.time.toLocaleTimeString() : '';
      return `<div class="copilot-log-item tag-${l.tag}">
        <span class="copilot-log-time">${t}</span>
        <span class="copilot-log-tag">${tagIcons[l.tag] || '📡'}</span>
        <span class="copilot-log-content">${escapeHtml(l.content)}</span>
      </div>`;
    }).join('');
  }
}

function _toggleCopilotLog() {
  const list = document.getElementById('copilotLogList');
  const showing = list.style.display !== 'none';
  list.style.display = showing ? 'none' : 'block';
  if (!showing) _renderCopilotLog();
}

function _toggleOverlay(id, byHover) {
  const el = document.getElementById(id);
  if (!el) return;
  const wasHidden = el.classList.contains('overlay-hidden');
  el.classList.toggle('overlay-hidden');
  if (!wasHidden) {
    // 收起：保存内联宽度，清除后让 CSS class（width: 50px）生效
    el._prevWidth = el.style.width || '';
    el.style.width = '';
    el._hoverPinned = false;
  } else if (el._prevWidth) {
    // 展开：恢复之前拖拽调整的宽度
    el.style.width = el._prevWidth;
    delete el._prevWidth;
  }
  if (byHover && wasHidden) {
    el._hoverPinned = false;  // hover 展开，尚未 pin
  }
  const btn = el.querySelector('.overlay-collapse-btn');
  if (btn) btn.textContent = wasHidden ? '➖' : '➕';
  // 临时启用过渡动画
  el.classList.add('overlay-transitioning');
  setTimeout(() => el.classList.remove('overlay-transitioning'), 550);
}

// 移入微缩浮层 → 自动展开；移出 → 自动收缩
document.addEventListener('mouseenter', (e) => {
  const overlay = e.target.closest('.hud-overlay, .dash-tree-overlay, .dash-focus-overlay, .copilot-overlay');
  if (!overlay || !overlay.classList.contains('overlay-hidden')) return;
  clearTimeout(overlay._hoverTimer);
  _toggleOverlay(overlay.id, true);
}, true);

document.addEventListener('mouseleave', (e) => {
  const overlay = e.target.closest('.hud-overlay, .dash-tree-overlay, .dash-focus-overlay, .copilot-overlay');
  if (!overlay || overlay.classList.contains('overlay-hidden') || overlay._hoverPinned) return;
  // 如果鼠标移到内部元素（按钮等），不收缩
  const related = e.relatedTarget;
  if (related && overlay.contains(related)) return;
  overlay._hoverTimer = setTimeout(() => {
    if (!overlay.classList.contains('overlay-hidden') && !overlay._hoverPinned) {
      _toggleOverlay(overlay.id);
    }
  }, 300);
}, true);

// 点击浮层内部 → pin 住（取消自动收缩）；点击外部 → 统一收起
document.addEventListener('click', (e) => {
  const overlay = e.target.closest('.hud-overlay, .dash-tree-overlay, .dash-focus-overlay, .copilot-overlay');
  if (overlay) {
    clearTimeout(overlay._hoverTimer);
    overlay._hoverPinned = true;
    return;
  }
  // 点击浮层外部 → 统一收起所有展开的浮层
  document.querySelectorAll('.hud-overlay, .dash-tree-overlay, .dash-focus-overlay, .copilot-overlay').forEach(el => {
    if (!el.classList.contains('overlay-hidden')) {
      el._hoverPinned = false;
      _toggleOverlay(el.id);
    }
  });
});

// ─── 浮层自由拖动（HUD + 副驾驶日志） ───
// 拖动把手带 data-drag-target 属性，指向被拖动浮层的 id
// 拖动后浮层从 transform: translateX(-50%) 居中模式切换为 left/top 绝对定位

function _initOverlayDrag() {
  const startDrag = (e, target) => {
    e.preventDefault();
    e.stopPropagation();
    // 如果浮层是收起的，先清除隐藏状态保证拖动可见
    if (target.classList.contains('overlay-hidden')) {
      target._hoverPinned = true;
      target.classList.remove('overlay-hidden');
      target.classList.remove('overlay-transitioning');
      target.style.width = '200px';
      clearTimeout(target._hoverTimer);
    }
    const rect = target.getBoundingClientRect();
    const offsetX = e.clientX - rect.left;
    const offsetY = e.clientY - rect.top;
    target.style.transform = 'none';
    target.style.left = rect.left + 'px';
    target.style.top = rect.top + 'px';
    target.style.right = 'auto';
    target.style.bottom = 'auto';
    target.classList.add('dragging');
    const onMove = (ev) => {
      const newLeft = Math.max(0, Math.min(window.innerWidth - rect.width, ev.clientX - offsetX));
      const newTop = Math.max(0, Math.min(window.innerHeight - 40, ev.clientY - offsetY));
      target.style.left = newLeft + 'px';
      target.style.top = newTop + 'px';
    };
    const onUp = () => {
      target.classList.remove('dragging');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  // 拖动把手
  document.querySelectorAll('.overlay-drag-handle[data-drag-target]').forEach(handle => {
    const targetId = handle.getAttribute('data-drag-target');
    const target = document.getElementById(targetId);
    if (!target) return;
    handle.addEventListener('mousedown', (e) => startDrag(e, target));
  });

  // 收起状态下的微缩标签也可拖动
  document.querySelectorAll('.dash-tree-overlay, .dash-focus-overlay, .hud-overlay, .copilot-overlay').forEach(overlay => {
    overlay.addEventListener('mousedown', (e) => {
      if (!overlay.classList.contains('overlay-hidden')) return;
      if (e.target.closest('.overlay-collapse-btn')) return;
      startDrag(e, overlay);
    });
  });
}

// ─── Dashboard 事件绑定 ───

document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    const genBtn = document.getElementById('dashGenDecision');
    if (genBtn) genBtn.addEventListener('click', generateDashDecision);
    const refreshBtn = document.getElementById('dashRefreshTree');
    if (refreshBtn) refreshBtn.addEventListener('click', _dashLoadTree);
    const recoverBtn = document.getElementById('dashRecoverBtn');
    if (recoverBtn) recoverBtn.addEventListener('click', recoverDashAttention);
    const logHeader = document.getElementById('copilotLogHeader');
    if (logHeader) logHeader.addEventListener('click', _toggleCopilotLog);
    const markOpp = document.getElementById('dashMarkOpp');
    if (markOpp) markOpp.addEventListener('click', () => _pushCopilotLog('opportunity', '用户标记一个机遇'));
    const viewSurplus = document.getElementById('dashViewSurplus');
    if (viewSurplus) viewSurplus.addEventListener('click', () => {
      const life = state.dashboard.life;
      if (life) _pushCopilotLog('life', `当前盈余 ${life.waking_hours_surplus?.toFixed(1) ?? 0}h`);
    });
    // HUD Agent 主按钮（常驻、一键调用）
    const hudAgentBtn = document.getElementById('hudAgentBtn');
    if (hudAgentBtn) hudAgentBtn.addEventListener('click', () => quickGenDecision());
    // Plan 树 ➕ Ideal 主按钮
    const addIdealBtn = document.getElementById('dashAddIdeal');
    if (addIdealBtn) addIdealBtn.addEventListener('click', showCreateIdealForm);
    // RAG 刷新按钮
    const refreshRag = document.getElementById('dashRefreshRag');
    if (refreshRag) refreshRag.addEventListener('click', () => {
      if (state.dashboard.selectedPlan) _renderRagPreview(state.dashboard.selectedPlan);
    });
    // 浮层自由拖动初始化
    _initOverlayDrag();
  }, 100);
});

// ─── Agent Panel ────────────────────────────────────────────

window.__lastCpHash = '';  // 全局 fallback 检查点哈希

function initAgentPanel() {
  if (state.agentMessages.length === 0) {
    addAgentMessage('assistant', '你好！我是 TS2 学习助手，支持流式响应和工具调用。');
  }
  loadModelCapabilities();
  // 初始化嵌入式 Swarm 子面板
  initSwarmPanel();
  document.getElementById('swarmEmbeddedPanel').style.display = '';
}

async function loadModelCapabilities() {
  try {
    const res = await fetch(`${API_BASE}/api/agent/model-info`);
    const data = await res.json();
    if (data.code !== 0 || !data.data) return;
    const info = data.data;
    const caps = info.capabilities || {};
    const badge = document.getElementById('modelCapabilityBadge');
    if (!badge) return;

    const tags = [];
    if (caps.supports_image_input) tags.push('🖼️');
    if (caps.supports_video_input) tags.push('🎬');
    if (info.is_reasoning_model) tags.push('🧠');
    if (caps.supports_tools) tags.push('🔧');

    if (tags.length > 0) {
      badge.style.display = 'inline';
      badge.textContent = `${info.model} ${tags.join('')}`;
      badge.title = `模型: ${info.model}\n上下文: ${info.context_window}\n图片输入: ${caps.supports_image_input ? '✓' : '✗'}\n视频输入: ${caps.supports_video_input ? '✓' : '✗'}\n推理: ${info.is_reasoning_model ? '✓' : '✗'}\n工具: ${caps.supports_tools ? '✓' : '✗'}`;
    } else {
      badge.style.display = 'inline';
      badge.textContent = info.model || 'unknown';
      badge.title = `模型: ${info.model}\n上下文: ${info.context_window || '?'}`;
    }

    // 更新输入框 placeholder
    const input = document.getElementById('agentInput');
    if (input) {
      if (caps.supports_image_input && caps.supports_video_input) {
        input.placeholder = '输入消息... (支持图片和视频)';
      } else if (caps.supports_image_input) {
        input.placeholder = '输入消息... (支持图片)';
      } else {
        input.placeholder = '输入消息...';
      }
    }
  } catch (e) {
    // 静默失败
  }
}

function addAgentMessage(role, content, extra) {
  state.agentMessages.push({ role, content, ...extra });
  renderAgentMessages();
}

function renderToolCallsInline(toolCalls) {
  if (!toolCalls || !toolCalls.length) return '';
  var toolsHtml = '';
  for (var tci = 0; tci < toolCalls.length; tci++) {
    var tc = toolCalls[tci];
    // 子Agent特殊渲染
    if (tc.name === 'sub_agent' && tc.result) {
      toolsHtml += renderSubAgentResult(tc.result, tci);
      continue;
    }
    var statusIcon = tc.status === 'running' ? '⏳' : '✅';
    var cpTag = tc.checkpointHash ? '<span class="checkpoint-tag" title="点击查看检查点差异" onclick="viewCheckpointDiff(\'' + tc.checkpointHash + '\')">cp: ' + tc.checkpointHash.substring(0,8) + '</span>' : '';
    var resultHtml = tc.result ? '<div class="agent-tool-result"><span class="agent-tool-result-label">结果:</span> ' + escapeHtml(tc.result.substring(0, 500)) + '</div>' : '';
    toolsHtml += '<div class="agent-tool-call"><span class="agent-tool-name">' + statusIcon + ' ' + escapeHtml(tc.name) + '</span>' + cpTag + '</div>' + resultHtml;
  }
  return '<div class="agent-tool-calls">' + toolsHtml + '</div>';
}

/* 子Agent结果折叠面板渲染 */
var _subAgentPanelId = 0;
function renderSubAgentResult(resultStr, idx) {
  var data = null;
  try { data = JSON.parse(resultStr); } catch(e) {}
  if (!data || !data.__sub_agent__) {
    // 非结构化结果，回退到普通渲染
    return '<div class="agent-tool-call"><span class="agent-tool-name">🐝 sub_agent</span></div>' +
      '<div class="agent-tool-result"><span class="agent-tool-result-label">结果:</span> ' + escapeHtml(resultStr.substring(0, 500)) + '</div>';
  }
  var pid = 'sap_' + (++_subAgentPanelId);
  var roleIcons = { coder: '💻', task: '📋', research: '🔍', review: '🔎' };
  var icon = roleIcons[data.role] || '🐝';
  var statusClass = data.status || 'completed';
  var statusText = { completed: '完成', failed: '失败', cancelled: '已取消' }[data.status] || data.status;
  var header = '<div class="subagent-header" onclick="toggleSubAgentPanel(\'' + pid + '\')">' +
    '<span class="subagent-icon">' + icon + '</span>' +
    '<span class="subagent-name">' + escapeHtml(data.agent_name || 'sub_agent') + '</span>' +
    '<span class="subagent-toggle">▶ 展开</span>' +
    '<span class="subagent-status ' + statusClass + '">' + statusText + '</span>' +
    '</div>';
  var metaHtml = '<div class="subagent-meta">' +
    '<span>轮次: ' + (data.tool_calls_count || 0) + '</span>' +
    '<span>tokens: ' + (data.prompt_tokens || 0) + '+' + (data.completion_tokens || 0) + '</span>' +
    '<span>耗时: ' + (data.duration_ms || 0) + 'ms</span>' +
    '</div>';
  var bodyHtml = '<div class="subagent-body" id="' + pid + '">' +
    renderSimpleMarkdown(data.content || '') +
    '</div>';
  var reasoningHtml = '';
  if (data.reasoning_content) {
    var rid = pid + '_r';
    reasoningHtml = '<div class="subagent-reasoning" id="' + rid + '">' +
      '<div class="subagent-reasoning-label">💭 推理过程</div>' +
      escapeHtml(data.reasoning_content.substring(0, 1000)) +
      '</div>';
  }
  var errorHtml = data.error ? '<div class="subagent-error">❌ ' + escapeHtml(data.error) + '</div>' : '';
  return '<div class="subagent-panel">' + header + metaHtml + bodyHtml + reasoningHtml + errorHtml + '</div>';
}

function toggleSubAgentPanel(pid) {
  var el = document.getElementById(pid);
  if (!el) return;
  el.classList.toggle('open');
  // 更新toggle文字
  var header = el.parentElement.querySelector('.subagent-header');
  var toggle = header ? header.querySelector('.subagent-toggle') : null;
  if (toggle) toggle.textContent = el.classList.contains('open') ? '▼ 收起' : '▶ 展开';
  // 同时切换推理面板
  var rEl = document.getElementById(pid + '_r');
  if (rEl && el.classList.contains('open')) rEl.classList.add('open');
}

function getLastCheckpointHash(msg) {
  if (msg.role === 'assistant' && msg.toolCalls && msg.toolCalls.length) {
    for (var ti = msg.toolCalls.length - 1; ti >= 0; ti--) {
      if (msg.toolCalls[ti].checkpointHash) return msg.toolCalls[ti].checkpointHash;
    }
  }
  return '';
}

function renderAgentMessages() {
  const container = document.getElementById('agentMessages');
  container.innerHTML = state.agentMessages.map(msg => {
    let rendered = '';
    if (msg.role === 'user') {
      rendered = escapeHtml(msg.content);
    } else if (msg.role === 'tool' || msg.role === 'tool_call') {
      // 兼容旧消息
      var toolName = msg.toolName || msg.name || '工具';
      var toolResult = msg.result || msg.content || '';
      // 子Agent特殊渲染
      if (toolName === 'sub_agent' && toolResult) {
        rendered = renderSubAgentResult(toolResult, 0);
      } else {
        var truncated = toolResult.length > 300 ? toolResult.substring(0, 300) + '...' : toolResult;
        rendered = '<div class="agent-tool-call"><span class="agent-tool-name">🔧 ' + escapeHtml(toolName) + '</span>' + (msg.checkpointHash ? '<span class="checkpoint-tag" title="点击查看检查点差异" onclick="viewCheckpointDiff(\'' + msg.checkpointHash + '\')">cp: ' + msg.checkpointHash.substring(0,8) + '</span>' : '') + '</div>';
        if (toolResult) rendered += '<div class="agent-tool-result"><span class="agent-tool-result-label">结果:</span> ' + escapeHtml(truncated) + '</div>';
      }
      return '<div class="agent-msg assistant">' + rendered + '</div>';
    } else if (msg.role === 'assistant') {
      rendered = renderSimpleMarkdown(msg.content);
      // 内联 toolCalls（流式 + 恢复后）
      if (msg.toolCalls && msg.toolCalls.length) {
        rendered += renderToolCallsInline(msg.toolCalls);
      }
    } else {
      rendered = escapeHtml(msg.content);
    }
      var cpHash = msg.checkpointHash || getLastCheckpointHash(msg);
      // 没有内联 cpHash，尝试全局 fallback
      if (!cpHash && (msg.role === 'assistant' || msg.role === 'tool_call')) {
        cpHash = window.__lastCpHash || '';
      }
      var mi = state.agentMessages.indexOf(msg);
      var btnDisplay = cpHash ? '' : 'style="display:none"';
      return `
        <div class="agent-msg ${msg.role}">
          <div class="msg-role">${msg.role === 'user' ? '👤 你' : msg.role === 'tool_call' ? '🔧 工具' : '🤖 助手'}</div>
          <div class="msg-content">${rendered}</div>
          <div class="agent-actions">
            <span class="agent-msg-time">${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span>
            <button class="agent-action-btn" onclick="copyAgentMessage(${mi})" title="复制消息">📋</button>
            <button class="agent-action-btn" onclick="restoreAgentCheckpointModal('${cpHash}','')" title="恢复到此处" ${btnDisplay}>↩️</button>
          </div>
        </div>
      `;
  }).join('');
  container.scrollTop = container.scrollHeight;
}

function updateLastAssistantMessage(content) {
  // 找到最后一条 assistant 消息并更新内容
  for (let i = state.agentMessages.length - 1; i >= 0; i--) {
    if (state.agentMessages[i].role === 'assistant') {
      state.agentMessages[i].content = content;
      renderAgentMessages();
      return;
    }
  }
  // 如果没有找到，创建一条新的
  addAgentMessage('assistant', content);
}

function copyAgentMessage(index) {
  var msg = state.agentMessages[index];
  if (!msg) return;
  var text = msg.content || '';
  if (msg.role === 'tool_call') text = '[工具: ' + (msg.name || '工具') + ']\n' + (msg.result || text);
  navigator.clipboard.writeText(text).then(function() {
    var el = document.querySelector('.agent-msg .agent-action-btn');
    if (el && el.textContent === '📋') { el.textContent = '✓'; setTimeout(function() { el.textContent = '📋'; }, 2000); }
  }).catch(function() {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });
}

function renderSimpleMarkdown(text) {
  if (!text) return '';
  let html = escapeHtml(text);
  // Bold: **text** or __text__
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
  // Inline code: `text`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Code blocks: ```...```
  html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  // Unordered lists: lines starting with - or *
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/^\* (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // Ordered lists: lines starting with 1.
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  return html;
}

async function sendAgentMessage() {
  const input = document.getElementById('agentInput');
  const text = input.value.trim();
  if (!text || state.agentStreaming) return;

  input.value = '';
  addAgentMessage('user', text);

  // 捕获并清除附件
  const attachments = _buildAttachmentsPayload();
  _clearMediaAttachments();

  // 尝试流式请求
  state.agentStreaming = true;
  updateAgentSendButton();

  try {
    await sendAgentStream(text, attachments);
  } catch (e) {
    // 流式失败，回退到普通请求
    console.warn('Stream failed, falling back to sync:', e);
    try {
      await sendAgentSync(text, attachments);
    } catch (e2) {
      addAgentMessage('assistant', '抱歉，发生了错误: ' + e2.message);
    }
  } finally {
    state.agentStreaming = false;
    document.getElementById('agentTyping').classList.remove('show');
    updateAgentSendButton();
  }
}

async function sendAgentStream(text, attachments) {
  // 添加空的 assistant 消息用于流式更新
  addAgentMessage('assistant', '');
  let fullContent = '';
  let toolCallHappened = false;
  const toolMsgMap = {};  // tool name → message index

  // 使用 XMLHttpRequest 实现更可靠的 SSE 读取
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    state.agentXHR = xhr;  // 保存引用，用于外部 abort
    xhr.open('POST', `${API_BASE}/api/agent/chat/stream`, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = '';  // 文本模式

    let lastIndex = 0;
    let sseBuffer = '';  // SSE 行缓冲区，处理 TCP 分包

    function processSSEData(newData) {
      sseBuffer += newData;
      // 按双换行分割 SSE 事件
      while (true) {
        const eventEnd = sseBuffer.indexOf('\n\n');
        if (eventEnd === -1) break;
        const eventBlock = sseBuffer.substring(0, eventEnd);
        sseBuffer = sseBuffer.substring(eventEnd + 2);

        // 解析事件块中的 data: 行
        const lines = eventBlock.split('\n');
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') {
            // 流结束 — 更新最后一个 assistant 气泡（而非创建新的，避免拖尾）
            state.streamingToolCalls = [];
            if (fullContent) {
              updateLastAssistantMessage(fullContent);
            } else if (!toolCallHappened) {
              // 无 tool call 且无文本，移除空 assistant 消息
              for (let i = state.agentMessages.length - 1; i >= 0; i--) {
                if (state.agentMessages[i].role === 'assistant' && !state.agentMessages[i].content) {
                  state.agentMessages.splice(i, 1);
                  break;
                }
              }
              renderAgentMessages();
            }
            // 标记未返回结果的工具
            for (var tName in toolMsgMap) {
              var tidx = toolMsgMap[tName];
              if (state.agentMessages[tidx] && state.agentMessages[tidx].role === 'tool_call') {
                state.agentMessages[tidx].content = '⚠️ 工具未返回结果';
                state.agentMessages[tidx].status = 'done';
              }
            }
            fullContent = '';
            resolve();
            return;
          }

          try {
            const msg = JSON.parse(data);
            switch (msg.type) {
              case 'token':
                // tool_call 之后的首个 token：先创建新空气泡
                if (toolCallHappened && !fullContent) {
                  addAgentMessage('assistant', '');
                }
                fullContent += msg.content;
                updateLastAssistantMessage(fullContent);
                break;
              case 'tool_call':
                // 分段模式：将已有文本固化为独立 assistant 消息，再创建独立 tool 消息
                if (fullContent) {
                  updateLastAssistantMessage(fullContent);
    } else if (tab && tab._isMonaco) {
      var vditorEl = document.getElementById('paneVditor-' + paneId);
      if (vditorEl) vditorEl.style.display = 'none';
      var monacoEl = document.getElementById('paneMonaco-' + paneId);
      if (monacoEl) monacoEl.style.display = '';
      var pdfContainer = document.getElementById('panePdfContainer-' + paneId);
      if (pdfContainer) pdfContainer.style.display = 'none';
      var content = state['paneFileContents_' + paneId][path] || '';
      _ensurePaneMonaco(paneId, content, path);
    } else {
                  // 无文本，移除空的 assistant 消息
                  for (let j = state.agentMessages.length - 1; j >= 0; j--) {
                    if (state.agentMessages[j].role === 'assistant' && !state.agentMessages[j].content) {
                      state.agentMessages.splice(j, 1);
                      break;
                    }
                  }
                }
                toolCallHappened = true;
                fullContent = '';
                addAgentMessage('tool_call', '⏳ 调用中...', { name: msg.name, args: msg.args, result: '', status: 'running' });
                toolMsgMap[msg.name] = state.agentMessages.length - 1;
                document.getElementById('agentTyping').classList.add('show');
                break;
              case 'tool_result':
                if (msg.checkpoint_hash) window.__lastCpHash = msg.checkpoint_hash;
                // 更新独立的 tool 消息
                var toolIdx = toolMsgMap[msg.name];
                if (toolIdx !== undefined) {
                  var tm = state.agentMessages[toolIdx];
                  if (tm && tm.role === 'tool_call') {
                    var truncated = (msg.result || '').length > 500 ? (msg.result || '').substring(0, 500) + '...' : (msg.result || '');
                    tm.content = truncated;
                    tm.result = msg.result || '';
                    tm.status = 'done';
                    if (msg.checkpoint_hash) tm.checkpointHash = msg.checkpoint_hash;
                    renderAgentMessages();
                  }
                  delete toolMsgMap[msg.name];
                }
                break;
              case 'done':
                state.streamingToolCalls = [];
                if (msg.content) fullContent = msg.content;
                if (fullContent) {
                  updateLastAssistantMessage(fullContent);
                } else if (!toolCallHappened) {
                  // 无内容且无 tool call，移除空 assistant 消息
                  for (let i = state.agentMessages.length - 1; i >= 0; i--) {
                    if (state.agentMessages[i].role === 'assistant' && !state.agentMessages[i].content) {
                      state.agentMessages.splice(i, 1);
                      break;
                    }
                  }
                  renderAgentMessages();
                }
                // 标记未返回结果的工具
                for (var tName in toolMsgMap) {
                  var tidx = toolMsgMap[tName];
                  if (state.agentMessages[tidx] && state.agentMessages[tidx].role === 'tool_call') {
                    state.agentMessages[tidx].content = '⚠️ 工具未返回结果';
                    state.agentMessages[tidx].status = 'done';
                  }
                }
                fullContent = '';
                break;
              case 'error':
                if (!fullContent) {
                  updateLastAssistantMessage('错误: ' + msg.content);
                }
                break;
            }
          } catch (e) {
            console.warn('SSE parse error:', e, data);
          }
        }
      }
    }

    xhr.onprogress = function() {
      const newData = xhr.responseText.substring(lastIndex);
      lastIndex = xhr.responseText.length;
      processSSEData(newData);
    };

    xhr.onload = function() {
      state.agentXHR = null;
      state.streamingToolCalls = [];
      // 处理缓冲区中剩余数据
      const remaining = xhr.responseText.substring(lastIndex);
      if (remaining.trim()) {
        sseBuffer += remaining;
        if (sseBuffer.trim()) {
          const lines = sseBuffer.split('\n');
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const data = line.slice(6).trim();
            if (data === '[DONE]') continue;
            try {
              const msg = JSON.parse(data);
              if (msg.type === 'done' && msg.content) {
                fullContent = msg.content;
              }
            } catch (e) {}
          }
        }
      }
      if (fullContent) {
        updateLastAssistantMessage(fullContent);
      } else if (!toolCallHappened) {
        for (let i = state.agentMessages.length - 1; i >= 0; i--) {
          if (state.agentMessages[i].role === 'assistant' && !state.agentMessages[i].content) {
            state.agentMessages.splice(i, 1);
            break;
          }
        }
        renderAgentMessages();
      }
      // 标记未返回结果的工具
      for (var tName in toolMsgMap) {
        var tidx = toolMsgMap[tName];
        if (state.agentMessages[tidx] && state.agentMessages[tidx].role === 'tool_call') {
          state.agentMessages[tidx].content = '⚠️ 工具未返回结果';
          state.agentMessages[tidx].status = 'done';
        }
      }
      fullContent = '';
      resolve();
    };

    xhr.onerror = function() {
      state.agentXHR = null;  // 清除引用
      state.streamingToolCalls = [];
      reject(new Error('Network error'));
    };

    xhr.send(JSON.stringify({ message: text, session_id: _getAgentSessionId(), attachments: attachments || undefined }));
  });
}

async function sendAgentSync(text, attachments) {
  document.getElementById('agentTyping').classList.add('show');

  const res = await client.agentChat(text, [], _getAgentSessionId(), attachments);
  document.getElementById('agentTyping').classList.remove('show');

  if (res.code === 0 && res.data) {
    const reply = res.data.content || res.data.message || res.data.reply || res.msg || '（无回复）';
    addAgentMessage('assistant', reply);
  } else {
    addAgentMessage('assistant', '抱歉，请求失败: ' + (res.msg || '未知错误'));
  }
}

function updateAgentSendButton() {
  const btn = document.getElementById('agentSend');
  if (state.agentStreaming) {
    btn.textContent = '停止';
    btn.style.background = 'var(--red)';
  } else {
    btn.textContent = '发送';
    btn.style.background = '';
  }
}

async function cancelAgentChat() {
  // 先中断 XHR 流式请求
  if (state.agentXHR) {
    try { state.agentXHR.abort(); } catch (e) {}
    state.agentXHR = null;
  }
  try {
    await fetch(`${API_BASE}/api/agent/cancel`, { method: 'POST' });
  } catch (e) {}
  state.agentStreaming = false;
  state.streamingToolCalls = [];
  document.getElementById('agentTyping').classList.remove('show');
  updateAgentSendButton();
}

document.getElementById('agentSend').addEventListener('click', () => {
  if (state.agentStreaming) {
    cancelAgentChat();
  } else {
    sendAgentMessage();
  }
});
document.getElementById('agentInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (state.agentStreaming) return;
    sendAgentMessage();
  }
});

// ─── 多模态附件：粘贴 / 拖拽 ──────────────────────────

let _mediaAttachId = 0;

function _addMediaAttachment(kind, dataUrl, mime, filename) {
  const id = ++_mediaAttachId;
  const placeholder = kind === 'image'
    ? `[image #${id}]`
    : `[video #${id} ${filename || mime}]`;
  state.mediaAttachments.push({ id, kind, dataUrl, mime, filename, placeholder });
  _renderMediaPreview();
  // 在输入框中插入占位符
  const input = document.getElementById('agentInput');
  const pos = input.selectionStart;
  const before = input.value.slice(0, pos);
  const after = input.value.slice(pos);
  input.value = before + placeholder + ' ' + after;
  input.focus();
}

function _removeMediaAttachment(id) {
  state.mediaAttachments = state.mediaAttachments.filter(a => a.id !== id);
  _renderMediaPreview();
}

function _renderMediaPreview() {
  const bar = document.getElementById('mediaPreviewBar');
  if (state.mediaAttachments.length === 0) {
    bar.style.display = 'none';
    bar.innerHTML = '';
    return;
  }
  bar.style.display = 'flex';
  bar.innerHTML = state.mediaAttachments.map(a => {
    if (a.kind === 'image') {
      return `<div style="position:relative;display:inline-block">
        <img src="${a.dataUrl}" style="height:48px;border-radius:4px;border:1px solid var(--border)" />
        <span onclick="_removeMediaAttachment(${a.id})" style="position:absolute;top:-4px;right:-4px;background:var(--danger);color:#fff;border-radius:50%;width:16px;height:16px;font-size:10px;cursor:pointer;display:flex;align-items:center;justify-content:center">&times;</span>
      </div>`;
    } else {
      return `<div style="position:relative;display:inline-flex;align-items:center;gap:4px;padding:4px 8px;background:var(--bg-secondary);border-radius:4px;border:1px solid var(--border);font-size:11px">
        🎬 ${a.filename || 'video'}
        <span onclick="_removeMediaAttachment(${a.id})" style="cursor:pointer;color:var(--danger);font-weight:bold">&times;</span>
      </div>`;
    }
  }).join('');
}

function _fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function _handleDroppedFiles(files) {
  for (const file of files) {
    const mime = file.type || '';
    if (mime.startsWith('image/')) {
      const dataUrl = await _fileToDataUrl(file);
      _addMediaAttachment('image', dataUrl, mime, file.name);
    } else if (mime.startsWith('video/')) {
      const dataUrl = await _fileToDataUrl(file);
      _addMediaAttachment('video', dataUrl, mime, file.name);
    }
  }
}

// 粘贴事件
document.getElementById('agentInput').addEventListener('paste', async (e) => {
  const items = e.clipboardData?.items;
  if (!items) return;
  let hasMedia = false;
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault();
      hasMedia = true;
      const file = item.getAsFile();
      if (file) {
        const dataUrl = await _fileToDataUrl(file);
        _addMediaAttachment('image', dataUrl, item.type, file.name || 'pasted.png');
      }
    }
  }
});

// 拖拽事件
const _agentInput = document.getElementById('agentInput');
_agentInput.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); });
_agentInput.addEventListener('drop', async (e) => {
  e.preventDefault();
  e.stopPropagation();
  const files = e.dataTransfer?.files;
  if (files && files.length > 0) {
    await _handleDroppedFiles(files);
  }
});

function _buildAttachmentsPayload() {
  // 从 state.mediaAttachments 构建 API 请求的 attachments 数组
  if (!state.mediaAttachments.length) return null;
  return state.mediaAttachments.map(a => ({
    kind: a.kind,
    data_url: a.dataUrl,
    path: a.filename || '',
  }));
}

function _clearMediaAttachments() {
  state.mediaAttachments = [];
  _mediaAttachId = 0;
  _renderMediaPreview();
}

// ─── Agent 会话管理 ──────────────────────────────────

async function showAgentSessions() {
  const res = await client.getAgentSessions();
  if (res.code !== 0 || !res.data) return;
  
  const sessions = res.data;
  if (!sessions.length) {
    showToast('暂无历史会话');
    return;
  }
  
  // 创建模态框
  let modal = document.getElementById('sessionModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'sessionModal';
    modal.className = 'modal-overlay';
    document.body.appendChild(modal);
  }
  
  const items = sessions.map(s => {
    const ts = s.timestamp;
    const time = ts > 1e12 ? new Date(ts) : new Date(ts * 1000);
    const timeStr = `${time.getMonth()+1}/${time.getDate()} ${time.getHours()}:${String(time.getMinutes()).padStart(2,'0')}`;
    const preview = s.summary || s.preview || '(无预览)';
    return `<div class="session-item" data-id="${s.id}">
      <div class="session-item-info">
        <span class="session-preview">${escapeHtml(preview.substring(0, 60))}</span>
        <span class="session-meta">${timeStr} · ${s.message_count}条消息</span>
      </div>
      <div class="session-item-actions">
        <button class="session-load-btn" data-id="${s.id}">载入</button>
        <button class="session-del-btn" data-id="${s.id}">✕</button>
      </div>
    </div>`;
  }).join('');
  
  modal.innerHTML = `<div class="modal-content session-modal">
    <div class="modal-header">
      <h3>历史会话</h3>
      <button class="modal-close" onclick="closeSessionModal()">✕</button>
    </div>
    <div class="session-list">${items}</div>
  </div>`;
  modal.classList.add('show');
  
  // 绑定事件
  modal.querySelectorAll('.session-load-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      await switchToSession(id);
      closeSessionModal();
    });
  });
  modal.querySelectorAll('.session-del-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      await client.deleteAgentSession(id);
      btn.closest('.session-item').remove();
    });
  });
}

function closeSessionModal() {
  const modal = document.getElementById('sessionModal');
  if (modal) modal.classList.remove('show');
}

async function createNewSession() {
  // 先中断流式请求 + 取消当前对话
  if (state.agentXHR) {
    try { state.agentXHR.abort(); } catch (e) {}
    state.agentXHR = null;
  }
  state.agentStreaming = false;
  try { await client.cancelAgent(); } catch { /* ignore */ }
  const res = await client.createAgentSession();
  if (res.code === 0 && res.data?.created) {
    showToast('新会话已创建');
    updateSessionInfo('新对话');
    // 重置 session_id
    _resetAgentSessionId();
    // 清空聊天显示
    state.agentMessages = [];
    const chatBox = document.getElementById('agentMessages');
    if (chatBox) chatBox.innerHTML = '';
  }
}

async function switchToSession(sessionId) {
  // 先中断流式请求
  if (state.agentXHR) {
    try { state.agentXHR.abort(); } catch (e) {}
    state.agentXHR = null;
  }
  state.agentStreaming = false;
  const res = await client.switchAgentSession(sessionId);
  if (res.code === 0 && res.data?.switched) {
    showToast('已切换会话');
    // 从服务端返回的消息列表还原聊天 UI（包含 tool 消息细节）
    const restoredMessages = res.data.messages || [];
    state.agentMessages = [];
    if (restoredMessages.length > 0) {
      for (const msg of restoredMessages) {
        if (msg.role === 'tool') {
          addAgentMessage('tool', msg.content, { toolName: msg.tool_name || '' });
        } else if (msg.role === 'assistant' && msg.tool_calls && msg.tool_calls.length) {
          // 先添加 assistant 文本内容
          if (msg.content) addAgentMessage('assistant', msg.content);
          // 再添加每个 tool_call 作为 tool_call 消息
          for (const tc of msg.tool_calls) {
            const tcDict = typeof tc === 'object' ? tc : {};
            const func = tcDict.function || {};
            let args = {};
            try { args = typeof func.arguments === 'string' ? JSON.parse(func.arguments) : (func.arguments || {}); } catch {}
            addAgentMessage('tool_call', '', { name: func.name || '', args, result: '' });
          }
        } else if (msg.role === 'assistant') {
          addAgentMessage('assistant', msg.content);
        } else if (msg.role === 'user') {
          addAgentMessage('user', msg.content);
        }
      }
      updateSessionInfo(`${restoredMessages.length}条消息`);
    } else {
      updateSessionInfo('历史会话');
    }
  }
}

function updateSessionInfo(text) {
  const info = document.getElementById('agentSessionInfo');
  if (info) info.textContent = text;
}

// ─── Agent Session ID 管理（参考 Crush Session.ID）────────────

function _getAgentSessionId() {
  const KEY = 'ts2_agent_session_id';
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8);
    localStorage.setItem(KEY, id);
  }
  return id;
}

function _resetAgentSessionId() {
  const KEY = 'ts2_agent_session_id';
  const id = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8);
  localStorage.setItem(KEY, id);
  return id;
}

// ─── Agent Checkpoint Management ────────────────────────────

async function showAgentCheckpoints() {
  // 清除红点
  const btn = document.querySelector('[onclick="showAgentCheckpoints()"]');
  if (btn) {
    const dot = btn.querySelector('.badge-dot');
    if (dot) dot.remove();
  }
  try {
    const res = await client.getAgentCheckpoints(_getAgentSessionId());
    const cps = (res && res.data && res.data.checkpoints) ? res.data.checkpoints : [];
    const instanceId = (res && res.data && res.data.instance_id) || '';
    if (cps.length === 0) {
      showToast('暂无检查点 — 发送消息后系统会自动创建', 'info');
      return;
    }
    let html = '<div style="overflow-y:auto;text-align:left"><div style="font-size:13px;font-weight:700;padding:4px 8px 8px;border-bottom:1px solid var(--border);margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap">';
    html += '<span>📋 检查点列表</span>';
    if (instanceId) html += '<span style="font-size:10px;color:var(--fg-muted);font-weight:400;font-family:monospace">实例: ' + escapeHtml(instanceId.substring(0, 12)) + '</span>';
    html += '</div>';
    cps.forEach(function(cp) {
      // 优先使用结构化元数据
      var meta = cp.meta || {};
      var seqLabel = meta.step ? '#' + meta.step : '';
      var toolLabel = meta.tool || '';
      var instanceLabel = meta.instance || '';
      var sourceLabel = meta.source === 'baseline' ? 'baseline' : '';
      // 兼容旧格式
      if (!seqLabel && !toolLabel) {
        var raw = (cp.message || '').replace('TS2 checkpoint: ', '');
        var m = raw.match(/^\[([^\]]+)\]\[(\d+)\]\s*(.*)/);
        if (m) { instanceLabel = m[1]; seqLabel = '#' + parseInt(m[2], 10); toolLabel = m[3]; }
        else { toolLabel = raw; }
      }
      var diffCount = cp.diff_count || 0;
      var time = cp.timestamp > 1e12 ? new Date(cp.timestamp) : new Date(cp.timestamp * 1000);
      var timeStr = time.getFullYear() + '-' + String(time.getMonth()+1).padStart(2,'0') + '-' + String(time.getDate()).padStart(2,'0') + ' ' + String(time.getHours()).padStart(2,'0') + ':' + String(time.getMinutes()).padStart(2,'0');
      html += '<div style="border:1px solid var(--border);border-radius:8px;padding:8px 10px;margin:0 4px 8px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;background:var(--bg-secondary)">';
      html += '<div style="flex:1;min-width:160px">';
      html += '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">';
      if (seqLabel) html += '<span style="font-size:10px;color:#fff;background:var(--accent);padding:0 5px;border-radius:4px;font-weight:600">' + seqLabel + '</span>';
      html += '<code style="font-size:10px;color:var(--accent);background:rgba(122,162,247,0.1);padding:1px 5px;border-radius:4px">' + cp.hash.substring(0, 8) + '</code>';
      html += ' <span style="font-size:12px;font-weight:500">' + escapeHtml(toolLabel) + '</span>';
      if (sourceLabel) html += '<span style="font-size:10px;color:var(--accent);background:var(--accent-dim, rgba(122,162,247,0.08));padding:1px 5px;border-radius:4px">' + sourceLabel + '</span>';
      else if (instanceLabel) html += '<span style="font-size:10px;color:var(--fg-muted);font-family:monospace">[' + escapeHtml(instanceLabel) + ']</span>';
      if (diffCount) html += '<span style="font-size:10px;color:var(--accent);background:var(--accent-dim, rgba(122,162,247,0.08));padding:1px 5px;border-radius:4px">' + diffCount + ' files</span>';
      html += '</div>';
      html += '<div style="font-size:10px;color:var(--fg-muted);margin-top:2px">' + timeStr;
      html += '</div></div>';
      html += '<div style="display:flex;gap:4px;flex-wrap:wrap">';
      html += '<button onclick="viewCheckpointDiff(\'' + cp.hash + '\')" title="查看此检查点与当前的文件差异" style="background:transparent;border:1px solid var(--border);font-size:11px;padding:3px 7px;border-radius:5px;cursor:pointer">📊 差异</button>';
      html += '<button onclick="restoreAgentCheckpointModal(\'' + cp.hash + '\',\'' + encodeURIComponent(toolLabel || cp.message) + '\')" title="选择恢复模式" style="background:var(--accent);color:#fff;border:none;font-size:11px;padding:3px 10px;border-radius:5px;cursor:pointer;font-weight:600">↩️ 回退</button>';
      html += '</div></div>';
    });
    html += '</div>';
    showHtmlModal('🔖 检查点', html);
  } catch (e) {
    showToast('加载检查点失败: ' + e.message, 'error');
  }
}

async function restoreAgentCheckpointModal(commitHash, summary) {
  summary = decodeURIComponent(summary);
  const modes = [
    { id: 'taskAndFiles', icon: '🔃', label: '对话 + 文件', desc: '同时恢复对话历史和工作区文件（推荐）' },
    { id: 'task', icon: '💬', label: '仅对话', desc: '只恢复对话历史，保留当前文件' },
    { id: 'files', icon: '📁', label: '仅文件', desc: '只恢复工作区文件，保留当前对话' },
  ];
  let html = '<div style="text-align:left;padding:4px 8px">';
  html += '<div style="margin-bottom:8px"><button onclick="showAgentCheckpoints()" style="background:transparent;border:1px solid var(--border);color:var(--accent);font-size:12px;padding:4px 10px;border-radius:6px;cursor:pointer">← 返回检查点列表</button></div>';
  html += '<div style="font-size:14px;font-weight:700;margin-bottom:4px">↩️ 回退到检查点</div>';
  html += '<div style="font-size:12px;color:var(--fg-muted);margin-bottom:12px">摘要: ' + escapeHtml(summary) + '</div>';
  modes.forEach(m => {
    html += '<div onclick="doRestoreCheckpoint(\'' + commitHash + '\',\'' + m.id + '\')" style="border:1px solid var(--border);border-radius:8px;padding:8px 10px;margin-bottom:6px;cursor:pointer;transition:background 0.15s;background:var(--bg-secondary)" onmouseover="this.style.background=\'var(--accent-dim, rgba(122,162,247,0.08))\'" onmouseout="this.style.background=\'var(--bg-secondary)\'">';
    html += '<div style="font-size:13px;font-weight:600">' + m.icon + ' ' + m.label + '</div>';
    html += '<div style="font-size:11px;color:var(--fg-muted);margin-top:2px">' + m.desc + '</div>';
    html += '</div>';
  });
  html += '<div style="font-size:11px;color:var(--fg-dim);margin-top:8px;padding:4px 0">⚠️ 恢复后当前工作区将被替换，不可撤销</div>';
  html += '</div>';
  showHtmlModal('恢复模式', html);
}

function convertApiToolCalls(apiToolCalls) {
  if (!apiToolCalls || !Array.isArray(apiToolCalls)) return [];
  return apiToolCalls.map(function(tc) {
    var fn = tc.function || {};
    var name = fn.name || '';
    var args = {};
    try { args = JSON.parse(fn.arguments || '{}'); } catch(e) {}
    return { name: name, args: args, status: 'done' };
  });
}

async function doRestoreCheckpoint(commitHash, restoreType) {
  closeHtmlModal();
  showToast('正在恢复…', 'info');
  try {
    const res = await client.restoreAgentCheckpoint(commitHash, restoreType);
    if (res && res.data && res.data.restored) {
      showToast('✅ 已恢复检查点');
      // 重建前端消息列表
      state.agentMessages = [];
      const container = document.getElementById('agentMessages');
      container.innerHTML = '';
      const msgs = res.data.ui_messages || [];
      msgs.forEach(m => {
        if (m.role === 'tool') {
          addAgentMessage('tool', m.content || '', { toolName: m.tool_name || '', checkpointHash: m.checkpoint_hash || '' });
        } else if (m.role === 'assistant') {
          var extra = {};
          if (m.tool_calls) {
            extra.toolCalls = convertApiToolCalls(m.tool_calls);
            // 从 API tool_calls 恢复 checkpoint_hash（服务器按序分配）
            m.tool_calls.forEach(function(apiTc, i) {
              if (apiTc.checkpoint_hash && i < extra.toolCalls.length) {
                extra.toolCalls[i].checkpointHash = apiTc.checkpoint_hash;
              }
            });
          }
          addAgentMessage('assistant', m.content || '', extra);
        } else {
          addAgentMessage(m.role, m.content || '');
        }
      });
      window.__lastCpHash = commitHash;
    } else {
      showToast('恢复失败: ' + ((res && res.data && res.data.error) || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('恢复失败: ' + e.message, 'error');
  }
}

async function viewCheckpointDiff(commitHash) {
  try {
    const res = await client.getAgentCheckpointDiff(commitHash);
    if (!res || !res.data) {
      showToast('获取差异失败', 'error');
      return;
    }
    const diffs = res.data.diff || [];
    const summary = res.data.summary || null;
    if (diffs.length === 0) {
      showToast('该检查点无差异数据', 'info');
      return;
    }
    let html = '<div style="overflow-y:auto;text-align:left">';
    html += '<div style="padding:6px 8px;border-bottom:1px solid var(--border);margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px">';
    html += '<button onclick="showAgentCheckpoints()" style="background:transparent;border:1px solid var(--border);color:var(--accent);font-size:12px;padding:4px 10px;border-radius:6px;cursor:pointer">← 返回检查点列表</button>';
    if (summary) {
      html += '<span style="font-size:11px;color:var(--fg-muted)">+' + summary.additions + ' -' + summary.deletions + ' (' + summary.files_changed + ' files)</span>';
    }
    html += '</div>';
    diffs.forEach(function(f) {
      const statusIcon = f.status === 'A' ? '🟢' : f.status === 'D' ? '🔴' : '🟡';
      const statusLabel = f.status === 'A' ? '新增' : f.status === 'D' ? '删除' : '修改';
      const adds = f.additions || 0;
      const dels = f.deletions || 0;
      html += '<div style="border-bottom:1px solid var(--border);padding:6px 8px">';
      html += '<div style="font-size:11px;font-weight:600;margin-bottom:4px">' + statusIcon + ' ' + escapeHtml(f.path) + ' <span style="color:var(--fg-muted);font-weight:400">(' + statusLabel + ', +' + adds + ' -' + dels + ')</span></div>';
      if (f.diff) {
        html += '<pre style="font-size:11px;background:#1e1e1e;color:#d4d4d4;padding:6px 8px;border-radius:4px;overflow-x:auto;margin:0;line-height:1.4">' + escapeHtml(f.diff) + '</pre>';
      }
      html += '</div>';
    });
    html += '</div>';
    showHtmlModal('📊 检查点差异', html);
  } catch (e) {
    showToast('加载差异失败: ' + e.message, 'error');
  }
}

// ─── Swarm 子 Agent 面板 ──────────────────────────────────────

let _swarmInited = false;
let _swarmPollTimers = {};
let _swarmEmbeddedOpen = false;

function toggleSwarmEmbedded() {
  var body = document.getElementById('swarmEmbeddedBody');
  var toggle = document.getElementById('swarmEmbeddedToggle');
  _swarmEmbeddedOpen = !_swarmEmbeddedOpen;
  body.style.display = _swarmEmbeddedOpen ? '' : 'none';
  toggle.textContent = _swarmEmbeddedOpen ? '▼' : '▶';
}

function initSwarmPanel() {
  if (!_swarmInited) {
    _swarmInited = true;
    swarmRefresh();
  }
}

async function swarmRefresh() {
  try {
    const res = await fetch(`${API_BASE}/api/swarm/agents`);
    const data = await res.json();
    if (data.code !== 0 || !data.data.available) {
      document.getElementById('swarmAgentList').innerHTML =
        '<div style="color:var(--fg-muted);font-size:11px;text-align:center;padding:20px">Swarm 系统未初始化</div>';
      return;
    }
    const agents = data.data.agents || [];
    const swarmEnabled = data.data.swarm_enabled || false;
    state.swarmAgents = agents;

    // 更新集群模式状态显示
    const badge = document.getElementById('swarmModeBadge');
    const enableBtn = document.getElementById('swarmEnableBtn');
    const disableBtn = document.getElementById('swarmDisableBtn');
    if (swarmEnabled) {
      badge.textContent = '集群模式';
      badge.style.background = '#10b981';
      badge.style.color = '#fff';
      enableBtn.style.display = 'none';
      disableBtn.style.display = '';
    } else {
      badge.textContent = '单次模式';
      badge.style.background = 'var(--bg-tertiary)';
      badge.style.color = 'var(--fg-muted)';
      enableBtn.style.display = '';
      disableBtn.style.display = 'none';
    }

    // 更新下拉选择（如果存在）
    const sel = document.getElementById('swarmAgentSelect');
    if (sel) {
      const curVal = sel.value;
      sel.innerHTML = '<option value="">选择 Agent</option>';
      agents.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.name;
        opt.textContent = `${a.name} (${a.role})`;
        sel.appendChild(opt);
      });
      if (curVal) sel.value = curVal;
    }

    // 渲染 Agent 卡片
    const container = document.getElementById('swarmAgentList');
    if (agents.length === 0) {
      container.innerHTML = '<div style="color:var(--fg-muted);font-size:11px;text-align:center;padding:20px">无已注册子 Agent</div>';
      return;
    }
    container.innerHTML = agents.map(a => {
      const statusColors = { idle: '#6b7280', pending: '#f59e0b', running: '#3b82f6', completed: '#10b981', failed: '#ef4444', cancelled: '#9ca3af' };
      const statusLabels = { idle: '空闲', pending: '等待', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' };
      const color = statusColors[a.status] || '#6b7280';
      const label = statusLabels[a.status] || a.status;
      const busy = a.is_busy;
      return `
        <div style="border:1px solid var(--border);border-radius:8px;padding:8px 10px;background:var(--bg-secondary)">
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div style="display:flex;align-items:center;gap:6px">
              <span style="width:8px;height:8px;border-radius:50%;background:${color};${busy ? 'animation:swarmPulse 1.5s infinite' : ''}"></span>
              <span style="font-size:12px;font-weight:600;color:var(--fg)">${a.name}</span>
              <span style="font-size:10px;color:var(--fg-muted);background:var(--bg-tertiary);padding:1px 6px;border-radius:4px">${a.role}</span>
            </div>
            <div style="display:flex;gap:4px">
              ${busy ? `<button onclick="swarmCancelAgent('${a.name}')" style="background:#ef4444;color:#fff;border:none;border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer">取消</button>` : ''}
              <button onclick="swarmShowDetail('${a.name}')" style="background:var(--bg-tertiary);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer">详情</button>
            </div>
          </div>
          <div style="margin-top:4px;font-size:10px;color:var(--fg-muted)">
            ${a.system_prompt ? `<div style="margin-bottom:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${a.system_prompt}</div>` : ''}
            <div>状态: <span style="color:${color}">${label}</span> | 最大轮次: ${a.max_turns}${a.model ? ' | 模型: ' + a.model : ''}</div>
            ${a.running_tasks && a.running_tasks.length > 0 ? `<div style="margin-top:2px">后台任务: ${a.running_tasks.map(t => t.task_id.slice(0,8)).join(', ')}</div>` : ''}
          </div>
        </div>`;
    }).join('');

    // 添加 pulse 动画（如果还没有）
    if (!document.getElementById('swarmPulseStyle')) {
      const style = document.createElement('style');
      style.id = 'swarmPulseStyle';
      style.textContent = '@keyframes swarmPulse{0%,100%{opacity:1}50%{opacity:0.4}}';
      document.head.appendChild(style);
    }
  } catch (e) {
    document.getElementById('swarmAgentList').innerHTML =
      `<div style="color:var(--fg-muted);font-size:11px;text-align:center;padding:20px">加载失败: ${e.message}</div>`;
  }
}

async function swarmRefreshTasks() {
  try {
    const res = await fetch(`${API_BASE}/api/swarm/tasks`);
    const data = await res.json();
    const tasks = (data.data && data.data.tasks) || [];
    const container = document.getElementById('swarmTaskList');

    if (tasks.length === 0) {
      container.innerHTML = '<div style="color:var(--fg-muted);font-size:11px;text-align:center;padding:8px">暂无后台任务</div>';
      return;
    }

    container.innerHTML = tasks.map(t => {
      const statusColors = { pending: '#f59e0b', running: '#3b82f6', completed: '#10b981', failed: '#ef4444', cancelled: '#9ca3af' };
      const color = statusColors[t.status] || '#6b7280';
      const completed = t.completed;
      return `
        <div style="border:1px solid var(--border);border-radius:6px;padding:6px 8px;background:var(--bg-secondary);font-size:10px">
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div style="display:flex;align-items:center;gap:4px">
              <span style="width:6px;height:6px;border-radius:50%;background:${color};${!completed ? 'animation:swarmPulse 1.5s infinite' : ''}"></span>
              <span style="color:var(--fg)">${t.agent_name || '未知'}</span>
              <span style="color:var(--fg-muted)">${t.task_id.slice(0,8)}</span>
            </div>
            <span style="color:${color}">${t.status || 'running'}</span>
          </div>
          ${t.content ? `<div style="margin-top:3px;color:var(--fg-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.content.slice(0,80)}</div>` : ''}
          ${t.error ? `<div style="margin-top:2px;color:#ef4444">${t.error.slice(0,60)}</div>` : ''}
          ${!completed ? `<button onclick="swarmPollTask('${t.task_id}')" style="margin-top:3px;background:var(--bg-tertiary);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:1px 6px;font-size:9px;cursor:pointer">轮询结果</button>` : ''}
        </div>`;
    }).join('');

    // 自动轮询未完成任务
    tasks.filter(t => !t.completed).forEach(t => {
      if (!_swarmPollTimers[t.task_id]) {
        _swarmPollTimers[t.task_id] = setInterval(() => {
          swarmPollTask(t.task_id);
        }, 5000);
      }
    });
    // 清除已完成任务的定时器
    Object.keys(_swarmPollTimers).forEach(tid => {
      if (!tasks.find(t => t.task_id === tid && !t.completed)) {
        clearInterval(_swarmPollTimers[tid]);
        delete _swarmPollTimers[tid];
      }
    });
  } catch (e) {
    // 静默失败
  }
}

async function swarmRunAgent() {
  const selEl = document.getElementById('swarmAgentSelect');
  const promptEl = document.getElementById('swarmPromptInput');
  const bgEl = document.getElementById('swarmBgCheck');
  const resultDiv = document.getElementById('swarmRunResult');

  const agentName = selEl ? selEl.value : '';
  const prompt = promptEl ? promptEl.value.trim() : '';
  const background = bgEl ? bgEl.checked : false;

  if (!agentName) { showToast('请选择 Agent', 'error'); return; }
  if (!prompt) { showToast('请输入任务描述', 'error'); return; }

  if (resultDiv) {
    resultDiv.style.display = 'block';
    resultDiv.textContent = '执行中...';
  }

  try {
    const res = await fetch(`${API_BASE}/api/swarm/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_name: agentName, prompt, background }),
    });
    const data = await res.json();

    if (data.code !== 0) {
      if (resultDiv) resultDiv.textContent = '错误: ' + (data.msg || '未知错误');
      return;
    }

    if (background) {
      const taskId = data.data.task_id;
      if (resultDiv) resultDiv.textContent = `后台任务已启动: ${taskId}`;
      if (promptEl) promptEl.value = '';
      swarmRefreshTasks();
      _swarmPollTimers[taskId] = setInterval(async () => {
        const pollRes = await swarmPollTask(taskId);
        if (pollRes) clearInterval(_swarmPollTimers[taskId]);
      }, 3000);
    } else {
      const d = data.data;
      if (resultDiv) {
        resultDiv.textContent = d.content || d.error || '(无输出)';
        if (d.reasoning_content) {
          resultDiv.textContent = `💭 ${d.reasoning_content.slice(0,200)}\n\n${resultDiv.textContent}`;
        }
        resultDiv.textContent += `\n\n---\n状态: ${d.status} | 耗时: ${d.duration_ms}ms | tokens: ${d.prompt_tokens}+${d.completion_tokens}`;
      }
      if (promptEl) promptEl.value = '';
      swarmRefresh();
    }
  } catch (e) {
    if (resultDiv) resultDiv.textContent = '执行失败: ' + e.message;
  }
}

async function swarmEnableCluster() {
  const reason = await modalPrompt('请输入启用 Swarm 集群模式的原因（如：大规模并行研究任务）：');
  if (!reason || !reason.trim()) {
    if (reason !== null) showToast('启用集群模式需要提供原因说明', 'error');
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/swarm/enable`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason.trim() }),
    });
    const data = await res.json();
    if (data.code === 0) {
      showToast('Swarm 集群模式已启用', 'info');
      swarmRefresh();
    } else {
      showToast(data.msg || '启用失败', 'error');
    }
  } catch (e) {
    showToast('启用失败: ' + e.message, 'error');
  }
}

async function swarmDisableCluster() {
  if (!await modalConfirm('确认禁用 Swarm 集群模式？正在运行的大规模并行任务将被取消。')) return;
  try {
    const res = await fetch(`${API_BASE}/api/swarm/disable`, { method: 'POST' });
    const data = await res.json();
    if (data.code === 0) {
      showToast('Swarm 集群模式已禁用', 'info');
      swarmRefresh();
    } else {
      showToast(data.msg || '禁用失败', 'error');
    }
  } catch (e) {
    showToast('禁用失败: ' + e.message, 'error');
  }
}

async function swarmCancelAgent(agentName) {
  try {
    await fetch(`${API_BASE}/api/swarm/cancel/${agentName}`, { method: 'POST' });
    showToast(`已取消 ${agentName}`, 'info');
    swarmRefresh();
  } catch (e) {
    showToast('取消失败: ' + e.message, 'error');
  }
}

async function swarmShowDetail(agentName) {
  try {
    const res = await fetch(`${API_BASE}/api/swarm/agents/${agentName}`);
    const data = await res.json();
    if (data.code !== 0) { showToast(data.msg || '获取失败', 'error'); return; }
    const a = data.data;
    const resultDiv = document.getElementById('swarmRunResult');
    resultDiv.style.display = 'block';

    let text = `=== ${a.name} (${a.role}) ===\n`;
    text += `状态: ${a.status} | 忙碌: ${a.is_busy}\n`;
    text += `模型: ${a.model || '继承主Agent'} | 最大轮次: ${a.max_turns}\n`;
    if (a.allowed_tools) text += `允许工具: ${a.allowed_tools.join(', ')}\n`;
    if (a.denied_tools) text += `禁止工具: ${a.denied_tools.join(', ')}\n`;
    text += `\n--- System Prompt ---\n${a.system_prompt || '(无)'}`;

    if (a.last_result) {
      const lr = a.last_result;
      text += `\n\n--- 最近结果 ---\n`;
      text += `耗时: ${lr.duration_ms}ms | 工具调用: ${lr.tool_calls_count}\n`;
      text += `tokens: ${lr.prompt_tokens}+${lr.completion_tokens}\n`;
      if (lr.error) text += `错误: ${lr.error}\n`;
      if (lr.content) text += `\n${lr.content}`;
    }
    resultDiv.textContent = text;
  } catch (e) {
    showToast('获取详情失败: ' + e.message, 'error');
  }
}

async function swarmPollTask(taskId) {
  try {
    const res = await fetch(`${API_BASE}/api/swarm/poll/${taskId}`, { method: 'POST' });
    const data = await res.json();
    if (data.code !== 0) return false;
    const d = data.data;
    if (d.completed) {
      // 清除定时器
      if (_swarmPollTimers[taskId]) {
        clearInterval(_swarmPollTimers[taskId]);
        delete _swarmPollTimers[taskId];
      }
      const resultDiv = document.getElementById('swarmRunResult');
      resultDiv.style.display = 'block';
      resultDiv.textContent = `[${d.agent_name}] ${d.status}\n${d.content || d.error || '(无输出)'}`;
      if (d.duration_ms) resultDiv.textContent += `\n\n耗时: ${d.duration_ms}ms | tokens: ${d.prompt_tokens}+${d.completion_tokens}`;
      swarmRefresh();
      swarmRefreshTasks();
      return true;
    }
    return false;
  } catch (e) {
    return false;
  }
}

// ─── WebSocket Message Handler ──────────────────────────────

function handleWSMessage(msg) {
  switch (msg.cmd) {
    case 'connected':
      console.log('WS connected:', msg.data);
      loadPushDashboard();
      break;
    case 'filechange':
      const change = msg.data;
      showToast(`文件 ${change.type}: ${change.path}`, 'info');
      // 防抖刷新，避免短时间内多次刷新导致搜索状态丢失
      if (window._refreshTreeTimer) clearTimeout(window._refreshTreeTimer);
      window._refreshTreeTimer = setTimeout(() => { refreshTree(); }, 500);
      break;
    case 'reloadFiletree':
      if (window._refreshTreeTimer) clearTimeout(window._refreshTreeTimer);
      window._refreshTreeTimer = setTimeout(() => { refreshTree(); }, 500);
      break;
    case 'msg':
      showToast(msg.msg, msg.code === 0 ? 'info' : 'error');
      break;
    case 'pong':
      break;
    case 'openInEditor':
      // Agent 请求在编辑器中打开文件
      if (msg.data && msg.data.path) {
        editorService.open(msg.data.path);
        switchNavTab('files');
      }
      break;
    case 'switchPanel':
      // Agent 请求切换面板
      if (msg.data && msg.data.panel) {
        switchNavTab(msg.data.panel);
      }
      break;
    case 'navigateSource':
      // Agent 请求在源码浏览器中导航
      if (msg.data) {
        switchNavTab('projects');
        if (!_srcBrowserExpanded) toggleSrcBrowserInProjects();
        srcLoadDir(msg.data.path || '');
      }
      break;
    case 'pushDashboard':
      if (msg.data) {
        state.pushDashboard = msg.data;
        renderPushDashboard();
        refreshCalendarBoard();
      }
      break;
    case 'checkpoint_created':
      // 检查点事件（参考 Crush PubSub + VersionedMap）
      if (msg.data) {
        const newVersion = msg.data.version || 0;
        if (newVersion > (state._checkpointVersion || 0)) {
          state._checkpointVersion = newVersion;
          // 在检查点按钮上显示红点
          const btn = document.querySelector('[onclick="showAgentCheckpoints()"]');
          if (btn && !btn.querySelector('.badge-dot')) {
            btn.style.position = 'relative';
            const dot = document.createElement('span');
            dot.className = 'badge-dot';
            dot.style.cssText = 'position:absolute;top:-2px;right:-2px;width:8px;height:8px;background:#ef4444;border-radius:50%;';
            btn.appendChild(dot);
          }
        }
      }
      break;
    case 'swarm_task_started':
      if (msg.data) {
        showToast(`子 Agent ${msg.data.agent_name} 已启动任务`, 'info');
        swarmRefresh();
        swarmRefreshTasks();
      }
      break;
    case 'swarm_task_completed':
      if (msg.data) {
        const statusIcon = msg.data.status === 'completed' ? '✅' : '❌';
        showToast(`${statusIcon} 子 Agent ${msg.data.agent_name} 任务${msg.data.status === 'completed' ? '完成' : '失败'} (${msg.data.duration_ms}ms)`, msg.data.status === 'completed' ? 'info' : 'error');
        swarmRefresh();
        swarmRefreshTasks();
      }
      break;
  }
}

// ─── UI Helpers ─────────────────────────────────────────────

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function updateWsStatus(connected) {
  const indicator = document.getElementById('wsIndicator');
  if (indicator) {
    indicator.className = 'indicator ' + (connected ? 'connected' : 'disconnected');
    document.getElementById('statusWs').innerHTML = `
      <span class="indicator ${connected ? 'connected' : 'disconnected'}" id="wsIndicator"></span>
      WebSocket ${connected ? '已连接' : '断开'}
    `;
  }
  const settingsWs = document.getElementById('settingsWsStatus');
  if (settingsWs) {
    settingsWs.textContent = connected ? '已连接' : '断开';
    settingsWs.style.background = connected ? '#4ade80' : '#ef4444';
  }
}

// ─── IndexedDB 储存自定义服务器 URL ─────────────────

const SETTINGS_DB = 'ts2_settings';
const SETTINGS_VER = 1;
const SETTINGS_STORE = 'settings';

function settingsDBOpen() {
  return new Promise(function(resolve, reject) {
    var req = indexedDB.open(SETTINGS_DB, SETTINGS_VER);
    req.onupgradeneeded = function() {
      var db = req.result;
      if (!db.objectStoreNames.contains(SETTINGS_STORE)) {
        db.createObjectStore(SETTINGS_STORE, { keyPath: 'key' });
      }
    };
    req.onsuccess = function() { resolve(req.result); };
    req.onerror = function() { reject(req.error); };
  });
}

function settingsDBGet(key) {
  return settingsDBOpen().then(function(db) {
    return new Promise(function(resolve, reject) {
      var tx = db.transaction(SETTINGS_STORE, 'readonly');
      var req = tx.objectStore(SETTINGS_STORE).get(key);
      req.onsuccess = function() { db.close(); resolve(req.result ? req.result.value : null); };
      req.onerror = function() { db.close(); reject(req.error); };
    });
  }).catch(function() { return null; });
}

function settingsDBSet(key, value) {
  return settingsDBOpen().then(function(db) {
    return new Promise(function(resolve, reject) {
      var tx = db.transaction(SETTINGS_STORE, 'readwrite');
      var req = tx.objectStore(SETTINGS_STORE).put({ key: key, value: value });
      req.onsuccess = function() { db.close(); resolve(); };
      req.onerror = function() { db.close(); reject(req.error); };
    });
  }).catch(function() {});
}

// ─── 服务器 URL 管理 ────────────────────────────────

const SERVER_URL_KEY = 'server_url';

async function loadServerUrl() {
  var saved = await settingsDBGet(SERVER_URL_KEY);
  if (saved) {
    API_BASE = saved;
    document.getElementById('serverUrlInput').value = saved;
    document.getElementById('serverUrlDisplay').textContent = saved;
  } else {
    API_BASE = location.origin;
    document.getElementById('serverUrlInput').value = location.origin;
    document.getElementById('serverUrlDisplay').textContent = location.origin;
  }
  return API_BASE;
}

async function saveServerUrl() {
  var input = document.getElementById('serverUrlInput');
  var url = input.value.trim().replace(/\/+$/, '');
  if (!url) {
    showToast('请输入服务器地址', 'error');
    return;
  }
  // 测试连接
  try {
    var res = await fetch(url + '/api/system/stats');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    var data = await res.json();
    if (data.code !== 0 && !data.data) throw new Error('非预期响应');
  } catch (e) {
    showToast('无法连接到 ' + url + '：' + e.message, 'error');
    return;
  }
  API_BASE = url;
  await settingsDBSet(SERVER_URL_KEY, url);
  document.getElementById('serverUrlDisplay').textContent = url;
  // 重连 WebSocket
  if (client.ws) { client.ws.close(); client.ws = null; }
  client.connectWS();
  refreshServerInfo();
  showToast('已切换至 ' + url, 'success');
}

function onServerUrlChange() {
  // 输入变化时不做操作，用户需点击"应用"按钮
}

async function refreshServerInfo() {
  document.getElementById('serverUrlDisplay').textContent = API_BASE;
  var settingsWs = document.getElementById('settingsWsStatus');
  settingsWs.textContent = '检查中...';
  settingsWs.style.background = '#888';
  try {
    var res = await fetch(API_BASE + '/api/system/stats');
    var data = await res.json();
    var info = data.data || data;
    if (info) {
      document.getElementById('serverVersionDisplay').textContent = info.version || '—';
      var extraRow = document.getElementById('serverExtraRow');
      if (info.local_ip) {
        extraRow.style.display = '';
        document.getElementById('serverLanIpDisplay').textContent = info.local_ip;
      } else {
        extraRow.style.display = 'none';
      }
    }
  } catch {
    document.getElementById('serverVersionDisplay').textContent = '无法连接';
  }
  updateWsStatus(client.wsConnected);
}

function reconnectWebSocket() {
  if (client.reconnectTimer) {
    clearTimeout(client.reconnectTimer);
    client.reconnectTimer = null;
  }
  if (client.ws) {
    client.ws.close();
    client.ws = null;
  }
  client.connectWS();
  refreshServerInfo();
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ─── Modal ──────────────────────────────────────────────────

let modalCallback = null;

function showHtmlModal(title, html) {
  const overlay = document.getElementById('modalOverlay');
  const titleEl = document.getElementById('modalTitle');
  const input = document.getElementById('modalInput');
  const dirSelect = document.getElementById('modalDirSelect');
  const modalBody = document.getElementById('modalBody');
  const modalBox = document.getElementById('modalBox');

  titleEl.textContent = title;
  input.style.display = 'none';
  dirSelect.style.display = 'none';

  // HTML 内容弹窗加宽
  modalBox.classList.add('modal-wide');

  // 清除旧的自定义内容
  const existing = modalBody.querySelector('.modal-html-content');
  if (existing) existing.remove();
  const htmlDiv = document.createElement('div');
  htmlDiv.className = 'modal-html-content';
  htmlDiv.innerHTML = html;
  modalBody.appendChild(htmlDiv);

  overlay.classList.add('show');

  const confirm = document.getElementById('modalConfirm');
  const cancel = document.getElementById('modalCancel');
  confirm.style.display = 'none';
  cancel.style.display = 'none';
  // 点击 overlay 外部区域关闭
  overlay.onclick = function(e) {
    if (e.target === overlay) {
      overlay.classList.remove('show');
      modalBox.classList.remove('modal-wide');
      overlay.onclick = null;
    }
  };
}

function closeHtmlModal() {
  const overlay = document.getElementById('modalOverlay');
  const modalBox = document.getElementById('modalBox');
  overlay.classList.remove('show');
  modalBox.classList.remove('modal-wide');
}

// ─── Modal Prompt / Confirm（替代浏览器原生弹窗，兼容 Electron） ──

var _modalResolve = null;

function resolveModal(val) {
  closeHtmlModal();
  var r = _modalResolve;
  _modalResolve = null;
  if (r) r(val);
}

function modalConfirm(msg) {
  return new Promise(function(resolve) {
    _modalResolve = resolve;
    showHtmlModal('确认', '<div style="padding:12px"><p style="margin:0 0 12px;font-size:13px;color:var(--fg-muted)">' + escapeHtml(msg) + '</p><div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn-action" onclick="resolveModal(true)" style="padding:8px 20px" autofocus>确定</button><button class="btn" onclick="resolveModal(false)" style="padding:8px 20px">取消</button></div></div>');
  });
}

function modalAlert(msg) {
  return new Promise(function(resolve) {
    _modalResolve = resolve;
    showHtmlModal('提示', '<div style="padding:12px"><p style="margin:0 0 12px;font-size:13px;color:var(--fg-muted)">' + escapeHtml(msg) + '</p><div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn-action" onclick="resolveModal(true)" style="padding:8px 20px" autofocus>确定</button></div></div>');
  });
}

function modalPrompt(msg, defaultValue) {
  return new Promise(function(resolve) {
    _modalResolve = resolve;
    var defVal = defaultValue || '';
    showHtmlModal(msg, '<div style="padding:12px"><input id="modalPromptInput" type="text" value="' + escapeHtml(defVal) + '" placeholder="' + escapeHtml(msg) + '" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:14px;font-family:monospace;box-sizing:border-box" autofocus><div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end"><button class="btn-action" onclick="resolveModal(document.getElementById(\'modalPromptInput\').value)" style="padding:8px 20px">确定</button><button class="btn" onclick="resolveModal(null)" style="padding:8px 20px">取消</button></div></div>');
    setTimeout(function() {
      var inp = document.getElementById('modalPromptInput');
      if (inp) inp.focus();
    }, 100);
  });
}

function showModal(title, placeholder, callback, options = {}) {
  const overlay = document.getElementById('modalOverlay');
  const input = document.getElementById('modalInput');
  const titleEl = document.getElementById('modalTitle');
  const dirSelect = document.getElementById('modalDirSelect');
  const modalBody = document.getElementById('modalBody');
  const modalBox = document.getElementById('modalBox');

  // 恢复普通弹窗宽度
  modalBox.classList.remove('modal-wide');

  // 清除之前的 html 内容，恢复输入框
  const existingHtml = modalBody.querySelector('.modal-html-content');
  if (existingHtml) existingHtml.remove();
  input.style.display = '';
  const confirmBtn = document.getElementById('modalConfirm');
  const cancelBtn = document.getElementById('modalCancel');
  confirmBtn.style.display = '';
  cancelBtn.style.display = '';

  titleEl.textContent = title;
  input.placeholder = placeholder;
  input.value = options.defaultValue || '';
  input.style.display = '';

  if (options.showDirSelect) {
    dirSelect.style.display = '';
    dirSelect.innerHTML = EXPOSED_DIRS.map(d =>
      `<option value="${d}" ${d === state.currentDir ? 'selected' : ''}>${d}</option>`
    ).join('');
    if (state.currentDir) {
      const matchDir = EXPOSED_DIRS.find(d => state.currentDir.startsWith(d));
      if (matchDir) dirSelect.value = matchDir;
    }
  } else {
    dirSelect.style.display = 'none';
  }

  modalCallback = callback;
  overlay.classList.add('show');

  setTimeout(() => input.focus(), 100);

  const confirm = document.getElementById('modalConfirm');
  const cancel = document.getElementById('modalCancel');

  const newConfirm = confirm.cloneNode(true);
  const newCancel = cancel.cloneNode(true);
  confirm.replaceWith(newConfirm);
  cancel.replaceWith(newCancel);

  newConfirm.addEventListener('click', () => {
    const val = input.value.trim();
    const dir = options.showDirSelect ? dirSelect.value : null;
    if (val || options.showDirSelect) {
      if (modalCallback) modalCallback(val, dir);
      overlay.classList.remove('show');
      modalCallback = null;
    }
  });

  newCancel.addEventListener('click', () => {
    overlay.classList.remove('show');
    modalCallback = null;
  });

  input.onkeydown = (e) => {
    if (e.key === 'Enter') {
      const val = input.value.trim();
      const dir = options.showDirSelect ? dirSelect.value : null;
      if (val || options.showDirSelect) {
        if (modalCallback) modalCallback(val, dir);
        overlay.classList.remove('show');
        modalCallback = null;
      }
    } else if (e.key === 'Escape') {
      overlay.classList.remove('show');
      modalCallback = null;
    }
  };
}

// ─── Context Menu Actions ───────────────────────────────────

document.addEventListener('click', () => {
  document.getElementById('contextMenu').classList.remove('show');
});

document.querySelectorAll('.context-menu-item').forEach(item => {
  item.addEventListener('click', async () => {
    const action = item.dataset.action;
    const target = state.contextTarget;
    if (!target) return;

    switch (action) {
      case 'open':
        if (target.is_dir) {
          state.expandedDirs.add(target.path);
          if (!state.dirCache[target.path]) {
            const res = await client.readDir(target.path);
            if (res.code === 0) state.dirCache[target.path] = res.data;
          }
          renderFileTree();
        } else {
          await openFile(target.path);
        }
        break;

      case 'rename':
        showModal('重命名', target.name, async (newName) => {
          const lastSlash = target.path.lastIndexOf('/');
          const dir = lastSlash >= 0 ? target.path.substring(0, lastSlash + 1) : '';
          const newPath = dir + newName;
          const res = await client.renameFile(target.path, newPath);
          if (res.code === 0) {
            showToast('重命名成功', 'success');
            await refreshTree();
          } else {
            showToast('重命名失败: ' + (res.msg || ''), 'error');
          }
        });
        break;

      case 'duplicate':
        if (state.fileContents[target.path] !== undefined) {
          const ext = target.ext || '';
          const baseName = target.name.replace(ext, '');
          const newPath = target.path.replace(target.name, baseName + '-copy' + ext);
          const res = await client.putFile(newPath, state.fileContents[target.path]);
          if (res.code === 0) {
            showToast('已复制', 'success');
            await refreshTree();
          }
        } else {
          const fileRes = await client.getFile(target.path);
          if (fileRes.code === 0) {
            const ext = target.ext || '';
            const baseName = target.name.replace(ext, '');
            const newPath = target.path.replace(target.name, baseName + '-copy' + ext);
            const res = await client.putFile(newPath, fileRes.data.content);
            if (res.code === 0) {
              showToast('已复制', 'success');
              await refreshTree();
            }
          }
        }
        break;

      case 'delete':
        if (await modalConfirm(`确定删除 "${target.name}"？`)) {
          const res = await client.removeFile(target.path);
          if (res.code === 0) {
            showToast('已删除', 'success');
            closeTab(target.path);
            await refreshTree();
          } else {
            showToast('删除失败: ' + (res.msg || ''), 'error');
          }
        }
        break;

      case 'download':
        client.downloadFile(target.path);
        showToast('下载中: ' + target.name, 'info');
        break;

      case 'addResource': {
        const courseId = item.dataset.courseId;
        if (courseId) {
          const label = target.name || target.path.split('/').pop() || 'file';
          const ext = (target.ext || '').toLowerCase();
          const type = (ext === '.pdf') ? 'pdf' : (ext.match(/\.(png|jpg|jpeg|gif|svg|webp)$/i) ? 'image' : 'pdf');
          const ok = await addCourseResource(courseId, {
            type: type,
            label: `📄 ${label}`,
            path: target.path
          });
          if (ok) {
            showToast(`已添加 ${label} 到课程资源`, 'success');
            loadCourseDetails(courseId);
          } else {
            showToast('资源已存在或添加失败', 'error');
          }
          state._pendingResourceCourse = null;
        }
        break;
      }

      case 'externalEdit':
        await openInExternalEditor(target.path);
        break;

      case 'openWith':
        showOpenWithPicker(target.path);
        break;
    }
  });
});

// ─── Toolbar Actions ────────────────────────────────────────

document.getElementById('btnNewFile').addEventListener('click', () => {
  const dir = state.currentDir || '';
  if (!dir) { showToast('禁止在根目录创建文件，请先进入子目录（如 Notes/）', 'error'); return; }
  showModal('新建文件', 'filename.md', async (name) => {
    if (!name) return;
    const path = dir + '/' + name;
    const res = await client.putFile(path, '');
    if (res.code === 0) {
      showToast('已创建: ' + name, 'success');
      await refreshTree();
      await openFile(path);
    } else {
      showToast('创建失败', 'error');
    }
  });
});

document.getElementById('btnNewDir').addEventListener('click', () => {
  const dir = state.currentDir || '';
  if (!dir) { showToast('禁止在根目录创建目录，请先进入子目录', 'error'); return; }
  showModal('新建目录', 'directory-name', async (name) => {
    if (!name) return;
    const path = dir + '/' + name;
    const res = await client.api('/api/file/createDir', { path });
    if (res.code === 0) {
      showToast('已创建目录: ' + name, 'success');
      await refreshTree();
    } else {
      showToast('创建失败', 'error');
    }
  });
});

document.getElementById('btnSave').addEventListener('click', saveCurrentFile);

// RMD 三格式编译按钮（参考 course_tracker 辅助工具方法）
async function knitRmd(outputFormat, btnId, btnIcon) {
  if (!state.activeTab) { showToast('未选择文件', 'info'); return; }
  // 先保存当前文件
  await saveCurrentFile();
  var btn = document.getElementById(btnId);
  btn.disabled = true;
  var origHtml = btn.innerHTML;
  btn.innerHTML = '⏳<span class="btn-label"> 编译中</span>';
  try {
    var res = await fetch(API_BASE + '/api/tools/knit-rmd', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: state.activeTab, output_format: outputFormat }),
    });
    var data = await res.json();
    if (data.code === 0 && data.data && data.data.success) {
      showToast('编译成功: ' + (data.data.output_file || ''), 'info');
      await refreshTree();
      // 编译成功后自动打开输出文件
      if (data.data.output_file) {
        editorService.open(data.data.output_file);
      }
    } else {
      var errMsg = data.data ? data.data.error : (data.msg || '未知错误');
      showToast('编译失败: ' + (errMsg || '').slice(0, 100), 'error');
    }
  } catch (e) {
    showToast('编译失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

document.getElementById('btnKnitPdf').addEventListener('click', function() { knitRmd('pdf_document', 'btnKnitPdf', '📄'); });
document.getElementById('btnKnitHtml').addEventListener('click', function() { knitRmd('html_document', 'btnKnitHtml', '🌐'); });
document.getElementById('btnKnitDocx').addEventListener('click', function() { knitRmd('word_document', 'btnKnitDocx', '📝'); });

function updateKnitButtonVisibility(filePath) {
  var isRmd = filePath && (filePath.toLowerCase().endsWith('.rmd') || filePath.toLowerCase().endsWith('.rmarkdown') || filePath.toLowerCase().endsWith('.md'));
  document.getElementById('btnKnitPdf').style.display = isRmd ? '' : 'none';
  document.getElementById('btnKnitHtml').style.display = isRmd ? '' : 'none';
  document.getElementById('btnKnitDocx').style.display = isRmd ? '' : 'none';
}

const _btnOpenWith = document.getElementById('btnOpenWith');
if (_btnOpenWith) {
  _btnOpenWith.addEventListener('click', function(e) {
    e.stopPropagation();
    const dd = document.getElementById('openWithDropdown');
    dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
  });
}

document.getElementById('btnUpload').addEventListener('click', () => {
  if (!state.currentDir) { showToast('禁止在根目录上传，请先进入子目录', 'error'); return; }
  document.getElementById('fileInput').click();
});

document.getElementById('fileInput').addEventListener('change', async (e) => {
  const files = e.target.files;
  if (!files.length) return;
  await handleFileUpload(files);
  e.target.value = '';
});

document.getElementById('btnDownload').addEventListener('click', () => {
  if (!state.activeTab) {
    showToast('未选择文件', 'info');
    return;
  }
  client.downloadFile(state.activeTab);
  showToast('下载中: ' + state.activeTab.split('/').pop(), 'info');
});

document.getElementById('btnSync').addEventListener('click', async () => {
  const res = await client.api('/api/sync/performSync', { direction: 'both' });
  if (res.code === 0) {
    showToast(`已同步 ${res.data?.synced || 0} 个文件`, 'success');
    await refreshTree();
  } else {
    showToast('同步失败', 'error');
  }
});

document.getElementById('btnEditorToggle').addEventListener('click', toggleEditorMode);

document.getElementById('plainEditor').addEventListener('input', () => {
  if (!state.activeTab) return;
  const content = document.getElementById('plainEditor').value;
  state.fileContents[state.activeTab] = content;
  markTabModified(state.activeTab, content !== state.originalContents[state.activeTab]);
});

// ─── PDF 翻页/缩放事件绑定 ──────────────────────────────

document.getElementById('pdfCloseBtn').addEventListener('click', () => {
  if (state.activeTab && state.activeTab.endsWith('.pdf')) {
    closeTab(state.activeTab);
  } else {
    destroyPdfSession();
    hidePdfViewer();
    document.getElementById('welcomeScreen').style.display = '';
    document.getElementById('statusPath').textContent = '就绪';
  }
});

document.getElementById('pdfPrevBtn').addEventListener('click', async () => {
  const step = state.pdfDualPage ? 2 : 1;
  await _goToPdfPage(state.pdfPageNum - step);
});

document.getElementById('pdfNextBtn').addEventListener('click', async () => {
  const step = state.pdfDualPage ? 2 : 1;
  await _goToPdfPage(state.pdfPageNum + step);
});

document.getElementById('pdfPageInput').addEventListener('change', async function() {
  const p = parseInt(this.value, 10);
  if (p >= 1 && p <= state.pdfPageCount) {
    await _goToPdfPage(p);
  } else {
    this.value = state.pdfPageNum;
  }
});

document.getElementById('pdfZoomIn').addEventListener('click', async () => {
  state.pdfZoom = Math.min(state.pdfZoom + 0.25, 3.0);
  if (state.pdfPath) state.pdfViewState[state.pdfPath] = { pageNum: state.pdfPageNum, zoom: state.pdfZoom, dualPage: state.pdfDualPage };
  _clearPdfCache();
  await renderPdfPage();
  _saveSession();
});

document.getElementById('pdfZoomOut').addEventListener('click', async () => {
  state.pdfZoom = Math.max(state.pdfZoom - 0.25, 0.25);
  if (state.pdfPath) state.pdfViewState[state.pdfPath] = { pageNum: state.pdfPageNum, zoom: state.pdfZoom, dualPage: state.pdfDualPage };
  _clearPdfCache();
  await renderPdfPage();
  _saveSession();
});

document.getElementById('pdfDualBtn').addEventListener('click', async () => {
  state.pdfDualPage = !state.pdfDualPage;
  if (state.pdfPath) state.pdfViewState[state.pdfPath] = { pageNum: state.pdfPageNum, zoom: state.pdfZoom, dualPage: state.pdfDualPage };
  if (state.pdfDualPage && state.pdfPageNum === state.pdfPageCount && state.pdfPageCount > 1) {
    state.pdfPageNum = state.pdfPageCount - 1;
  }
  document.getElementById('pdfCanvasContainer').style.flexDirection = state.pdfDualPage ? 'row' : 'column';
  document.getElementById('pdfCanvasContainer').style.alignItems = state.pdfDualPage ? 'flex-start' : 'center';
  _clearPdfCache();
  await renderPdfPage();
  _saveSession();
});

// 键盘翻页（主编辑器 PDF 和分屏 PDF）
document.addEventListener('keydown', async (e) => {
  // 分屏 PDF 翻页
  if (_splitActive && _activePaneId !== '0' && _activePaneId !== _agentPaneId) {
    var panePdf = state['panePdfDoc_' + _activePaneId];
    if (!panePdf) return;
    var paneTab = (state['paneTabs_' + _activePaneId] || []).find(function(t) { return t.path === state['paneActiveTab_' + _activePaneId]; });
    if (!paneTab || !paneTab._isPdf) return;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      panePdfNav(_activePaneId, -1); e.preventDefault();
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      panePdfNav(_activePaneId, 1); e.preventDefault();
    }
    return;
  }
  // 主编辑器 PDF 翻页
  if (!state.viewingPdf || !state.pdfDoc) return;
  var step = state.pdfDualPage ? 2 : 1;
  if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    await _goToPdfPage(state.pdfPageNum - step); e.preventDefault();
  } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    await _goToPdfPage(state.pdfPageNum + step); e.preventDefault();
  }
});

// ─── PDF AI 问答 ──────────────────────────────────────────

var pdfAiMessages = [];
var pdfAiStreaming = false;

document.getElementById('pdfOutlineBtn').addEventListener('click', togglePdfOutline);
document.getElementById('pdfOutlineCloseBtn').addEventListener('click', function() {
  document.getElementById('pdfOutlinePanel').style.display = 'none';
});
document.getElementById('pdfAiBtn').addEventListener('click', function() {
  var panel = document.getElementById('pdfAiPanel');
  if (panel.style.display === 'none') {
    panel.style.display = 'flex';
    if (pdfAiMessages.length === 0) {
      pdfAiAddMsg('assistant', '你好！我可以帮你回答关于这份 PDF 的问题。请输入你的问题。');
    }
  } else {
    panel.style.display = 'none';
  }
});

document.getElementById('pdfAiCloseBtn').addEventListener('click', function() {
  document.getElementById('pdfAiPanel').style.display = 'none';
});

document.getElementById('pdfIndexBtn').addEventListener('click', async function() {
  if (!state.pdfPath) { showToast('请先打开 PDF 文件', 'error'); return; }
  var btn = document.getElementById('pdfIndexBtn');
  btn.textContent = '索引中...';
  btn.disabled = true;
  try {
    var res = await client.api('/api/pdf/index', { file_path: state.pdfPath });
    if (res.code === 0) {
      showToast('索引建立完成，共 ' + (res.data.chunk_count || 0) + ' 个片段');
      btn.textContent = '已索引';
      btn.style.color = '';
      btn.style.borderColor = '';
    } else {
      showToast('索引失败: ' + (res.msg || '未知错误'), 'error');
      btn.textContent = '建立索引';
    }
  } catch (e) {
    showToast('索引失败: ' + e.message, 'error');
    btn.textContent = '建立索引';
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('pdfAiInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); pdfAiSend(); }
});
document.getElementById('pdfAiSendBtn').addEventListener('click', pdfAiSend);

function pdfAiAddMsg(role, content, sources) {
  pdfAiMessages.push({ role: role, content: content, sources: sources || [] });
  pdfAiRenderMessages();
}

function pdfAiRenderMessages() {
  var container = document.getElementById('pdfAiMessages');
  var html = '';
  for (var i = 0; i < pdfAiMessages.length; i++) {
    var msg = pdfAiMessages[i];
    var isUser = msg.role === 'user';
    if (isUser) {
      html += '<div style="display:flex;justify-content:flex-end">';
      html += '<div style="max-width:88%;padding:8px 12px;border-radius:12px 12px 3px 12px;font-size:13px;line-height:1.6;word-break:break-word;background:var(--accent);color:#fff">';
      html += msg.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
      html += '</div></div>';
    } else {
      html += '<div style="display:flex;gap:8px;align-items:flex-start">';
      html += '<div style="width:28px;height:28px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;margin-top:2px">AI</div>';
      html += '<div style="max-width:88%;min-width:0">';
      html += '<div style="padding:8px 12px;border-radius:3px 12px 12px 12px;font-size:13px;line-height:1.7;word-break:break-word;background:var(--bg);color:var(--fg);border:1px solid var(--border)">';
      // 简单 Markdown 渲染
      var text = msg.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      text = text.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
      text = text.replace(/`([^`]+?)`/g,'<code style="background:rgba(127,127,127,0.15);padding:1px 5px;border-radius:3px;font-size:12px;font-family:Consolas,monospace">$1</code>');
      text = text.replace(/^[-•] (.+)$/gm,'<div style="padding-left:12px;position:relative">• $1</div>');
      text = text.replace(/\n/g,'<br>');
      html += text;
      html += '</div>';
      if (msg.sources && msg.sources.length) {
        html += '<div style="margin-top:6px;font-size:11px;color:var(--fg-muted);padding-left:4px">';
        html += '<span style="font-weight:600">来源：</span>';
        for (var j = 0; j < msg.sources.length; j++) {
          html += '<span style="margin-right:8px">📄 ' + msg.sources[j].file_name + ' 第' + msg.sources[j].page + '页</span>';
        }
        html += '</div>';
      }
      html += '</div></div>';
    }
  }
  container.innerHTML = html;
  container.scrollTop = container.scrollHeight;
}

async function pdfAiSend() {
  var input = document.getElementById('pdfAiInput');
  var text = input.value.trim();
  if (!text || pdfAiStreaming) return;
  input.value = '';
  pdfAiAddMsg('user', text);
  pdfAiStreaming = true;
  document.getElementById('pdfAiSendBtn').disabled = true;

  try {
    var res = await client.api('/api/pdf/chat', { message: text });
    if (res.code === 0 && res.data) {
      pdfAiAddMsg('assistant', res.data.reply || '无回复', res.data.contexts || []);
    } else {
      pdfAiAddMsg('assistant', '错误: ' + (res.msg || '未知错误'));
    }
  } catch (e) {
    pdfAiAddMsg('assistant', '请求失败: ' + e.message);
  } finally {
    pdfAiStreaming = false;
    document.getElementById('pdfAiSendBtn').disabled = false;
  }
}

// ─── Upload ─────────────────────────────────────────────────

const uploadArea = document.getElementById('uploadArea');
const sidebarEl = document.getElementById('sidebar');

sidebarEl.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadArea.style.display = 'block';
  uploadArea.classList.add('dragover');
});

sidebarEl.addEventListener('dragleave', (e) => {
  if (!sidebarEl.contains(e.relatedTarget)) {
    uploadArea.classList.remove('dragover');
    setTimeout(() => { if (!uploadArea.classList.contains('dragover')) uploadArea.style.display = 'none'; }, 300);
  }
});

sidebarEl.addEventListener('drop', async (e) => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  uploadArea.style.display = 'none';
  if (!state.currentDir) { showToast('禁止在根目录上传，请先进入子目录', 'error'); return; }
  const files = e.dataTransfer.files;
  if (files.length) await handleFileUpload(files);
});

uploadArea.addEventListener('click', () => {
  document.getElementById('fileInput').click();
});

document.body.addEventListener('dragover', (e) => e.preventDefault());
document.body.addEventListener('drop', async (e) => {
  e.preventDefault();
  if (!state.currentDir) { showToast('禁止在根目录上传，请先进入子目录', 'error'); return; }
  const files = e.dataTransfer.files;
  if (files.length) await handleFileUpload(files);
});

async function handleFileUpload(files) {
  const panel = document.getElementById('transferPanel');
  const list = document.getElementById('transferList');
  list.innerHTML = '';
  panel.classList.add('show');

  showToast(`正在上传 ${files.length} 个文件...`, 'info');

  try {
    const res = await client.uploadFiles(files, state.currentDir);
    if (res.code === 0) {
      const uploaded = res.data.uploaded || res.data || [];
      (Array.isArray(uploaded) ? uploaded : []).forEach(f => {
        const item = document.createElement('div');
        item.className = 'transfer-item';
        item.innerHTML = `
          <span>✅</span>
          <span class="name">${f.name || f}</span>
          <span class="status">${f.size ? formatSize(f.size) : '完成'}</span>
        `;
        list.appendChild(item);
      });
      showToast(`已上传 ${files.length} 个文件`, 'success');
      await refreshTree();
    } else {
      showToast('上传失败: ' + (res.msg || ''), 'error');
    }
  } catch (e) {
    showToast('上传错误: ' + e.message, 'error');
  }

  setTimeout(() => panel.classList.remove('show'), 5000);
}

document.getElementById('closeTransferPanel').addEventListener('click', () => {
  document.getElementById('transferPanel').classList.remove('show');
});

// ─── LAN Info ───────────────────────────────────────────────

async function loadLanInfo() {
  try {
    const res = await client.getStats();
    if (res.code === 0 && res.data) {
      const stats = res.data;
      if (stats.file_stats) {
        document.getElementById('statusInfo').textContent =
          `${stats.file_stats.total_files || 0} 文件 · ${stats.file_stats.total_size_human || ''}`;
      }
      if (stats.local_ip) {
        const banner = document.getElementById('lanBanner');
        const ipEl = document.getElementById('lanIp');
        const addr = `http://${stats.local_ip}:${location.port}`;
        ipEl.textContent = addr;
        banner.style.display = 'flex';
        showToast('局域网访问: ' + addr, 'info');
      }
    }
  } catch (e) {}
}

document.getElementById('copyLanIp').addEventListener('click', () => {
  const ip = document.getElementById('lanIp').textContent;
  navigator.clipboard.writeText(ip).then(() => showToast('已复制: ' + ip, 'success'));
});

// ─── Resource Index ──────────────────────────────────────────

let resourceData = [];
let resourceSearchTimer = null;
let resourceFilterTimer = null;

function getResourceFilters() {
  const q = document.getElementById('resourceSearchInput')?.value.trim() || '';
  const courseFilter = document.getElementById('resourceCourseFilter')?.value || '';
  const lessonFilter = document.getElementById('resourceLessonFilter')?.value || '';
  return { query: q, course_id: courseFilter, lesson_number: lessonFilter };
}

async function loadResources(query) {
  const list = document.getElementById('resourceList');
  if (!list) return;
  list.innerHTML = '<div class="tree-loading">加载中...</div>';
  try {
    const params = new URLSearchParams();
    if (query) params.set('query', query);
    const filters = getResourceFilters();
    if (filters.course_id) params.set('course_id', filters.course_id);
    if (filters.lesson_number) params.set('lesson_number', filters.lesson_number);
    const qs = params.toString();
    const url = qs ? `/api/data/resources?${qs}` : '/api/data/resources';
    const res = await fetch(url);
    const json = await res.json();
    resourceData = json.data || [];
    renderResources(resourceData);
  } catch (e) {
    list.innerHTML = '<div class="tree-loading">加载失败</div>';
  }
}

function renderResources(items) {
  const list = document.getElementById('resourceList');
  if (!list) return;
  if (!items.length) {
    list.innerHTML = '<div class="tree-loading">暂无资源</div>';
    return;
  }
  let html = '';
  for (const r of items) {
    const type = r.type || 'url';
    const label = r.label || r.url || r.path || '';
    const course = r.course_id || '';
    const icon = type === 'pdf' ? '📄' : type === 'url' ? '🌐' : type === 'video' ? '🎬' : type === 'image' ? '🖼️' : type === 'note' ? '📝' : type === 'code' ? '💻' : '📄';
    const path = r.path || '';
    const url = r.url || '';
    const lesson = r.lesson_number ? `L${r.lesson_number}` : '';
    html += `<div class="resource-item" data-type="${type}" data-path="${encodeURIComponent(path)}" data-url="${encodeURIComponent(url)}" style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--border);cursor:pointer" onmouseover="this.style.background='var(--bg-tertiary)'" onmouseout="this.style.background=''">
      <span style="font-size:16px;flex-shrink:0">${icon}</span>
      <div style="flex:1;min-width:0">
        <div style="font-size:13px;color:var(--fg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${label.replace(/</g,'&lt;')}</div>
        <div style="font-size:11px;color:var(--fg-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${course}${lesson ? ' · ' + lesson : ''}</div>
      </div>
    </div>`;
  }
  list.innerHTML = html;
  list.querySelectorAll('.resource-item').forEach(el => {
    el.addEventListener('click', () => {
      const type = el.dataset.type;
      const path = decodeURIComponent(el.dataset.path);
      const url = decodeURIComponent(el.dataset.url);
      if (type === 'pdf' && path) {
        openPdf(path);
      } else if (type === 'url' && url) {
        window.open(url, '_blank');
      } else if (type === 'video') {
        if (url) window.open(url, '_blank');
        else if (path) openPdf(path);
      } else if (path) {
        openPdf(path);
      } else if (url) {
        window.open(url, '_blank');
      }
    });
  });
}

// 填充课程过滤下拉框
function populateResourceFilters() {
  const courseSel = document.getElementById('resourceCourseFilter');
  const lessonSel = document.getElementById('resourceLessonFilter');
  if (!courseSel || !lessonSel) return;
  const currentCourse = courseSel.value;
  const currentLesson = lessonSel.value;
  // 课程
  const courses = state.courses || [];
  let opts = '<option value="">全部课程</option>';
  const seenCourses = new Set();
  for (const c of courses) {
    const cid = c.note_id || c.course_title || '';
    if (cid && !seenCourses.has(cid)) {
      seenCourses.add(cid);
      opts += `<option value="${escapeHtml(cid)}">${escapeHtml(c.course_title || c.title || cid)}</option>`;
    }
  }
  // 从已有资源中补充未知的课程ID
  for (const r of resourceData) {
    const cid = r.course_id || '';
    if (cid && !seenCourses.has(cid)) {
      seenCourses.add(cid);
      opts += `<option value="${escapeHtml(cid)}">${escapeHtml(cid)}</option>`;
    }
  }
  courseSel.innerHTML = opts;
  if (currentCourse) courseSel.value = currentCourse;
  // 课时
  const selectedCourse = courseSel.value;
  opts = '<option value="">全部课时</option>';
  if (selectedCourse) {
    const course = courses.find(c => (c.note_id || c.course_title || '') === selectedCourse);
    if (course && course.lessons) {
      course.lessons.forEach(l => {
        const ln = l.lesson_number || 0;
        opts += `<option value="${ln}">L${ln} ${escapeHtml(l.lesson_title || '')}</option>`;
      });
    }
  }
  lessonSel.innerHTML = opts;
  if (currentLesson && selectedCourse === currentCourse) lessonSel.value = currentLesson;
}

function refreshResourceList() {
  const q = document.getElementById('resourceSearchInput')?.value.trim() || '';
  loadResources(q);
}

document.getElementById('resourceSearchInput')?.addEventListener('input', (e) => {
  clearTimeout(resourceSearchTimer);
  const q = e.target.value.trim();
  resourceSearchTimer = setTimeout(() => { populateResourceFilters(); loadResources(q); }, 300);
});

document.getElementById('resourceRefreshBtn')?.addEventListener('click', () => {
  populateResourceFilters();
  refreshResourceList();
});

document.getElementById('resourceCourseFilter')?.addEventListener('change', () => {
  populateResourceFilters();
  refreshResourceList();
});

document.getElementById('resourceLessonFilter')?.addEventListener('change', () => {
  refreshResourceList();
});

const origSwitchNavTabResources = switchNavTab;
switchNavTab = function(tabName) {
  origSwitchNavTabResources(tabName);
  if (tabName === 'resources') {
    populateResourceFilters();
    if (resourceData.length === 0) loadResources('');
  }
};

// ─── Search ─────────────────────────────────────────────────

let searchTimer = null;
document.getElementById('searchInput').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  const query = e.target.value.trim();

  if (!query) {
    renderFileTree();
    return;
  }

  searchTimer = setTimeout(async () => {
    const res = await client.search(query);
    if (res.code === 0 && res.data) {
      const tree = document.getElementById('fileTree');
      tree.innerHTML = '';
      const entries = Array.isArray(res.data) ? res.data : [];
      if (!entries.length) {
        tree.innerHTML = '<div class="tree-loading">未找到结果</div>';
        return;
      }
      const sorted = sortEntries(entries);
      sorted.forEach(entry => renderTreeItem(tree, entry, 0));
    }
  }, 300);
});

// ─── Split Pane 分屏管理 ─────────────────────────────────────────
// 核心思路：默认不包裹，分屏时动态将 editorContainer 包裹进 split-container

let _paneCounter = 1;
let _activePaneId = '0';
var _splitActive = false;  // 是否处于分屏状态
var _splitDirection = 'h'; // 分屏方向: 'h' 水平, 'v' 垂直
let _agentPaneId = null;   // Agent 分屏所在的 paneId（复用 sidebar DOM）

function _onPaneMousedown(paneId, e) {
  var el = e.target;
  while (el && el !== e.currentTarget) {
    if (el.classList && el.classList.contains('pane')) return;
    el = el.parentElement;
  }
  setActivePane(paneId);
}

function _addPaneToContainer(container, type) {
  var paneCount = container.querySelectorAll(':scope > .pane').length;
  if (paneCount >= 4) { showToast('同方向最多4个分屏', 'error'); return null; }
  var newPaneId = '' + (_paneCounter++);
  var divider = document.createElement('div');
  divider.className = 'split-divider divider-anim-in';
  var pane = document.createElement('div');
  pane.className = 'pane pane-anim-in';
  pane.id = 'pane-' + newPaneId;
  pane.setAttribute('data-pane-id', newPaneId);
  pane.addEventListener('mousedown', function(e) { _onPaneMousedown(newPaneId, e); });
  container.appendChild(divider);
  container.appendChild(pane);
  _initNewPane(pane, newPaneId, type);
  var tabsEl = document.getElementById('editorTabs-' + newPaneId);
  if (tabsEl) _setupPaneTabsDrop(tabsEl, newPaneId);
  initDividerDrag(divider);
  setActivePane(newPaneId);
  requestAnimationFrame(function() {
    pane.classList.remove('pane-anim-in');
    divider.classList.remove('divider-anim-in');
  });
  setTimeout(_relayoutEditors, 280);
  return newPaneId;
}

function _relayoutEditors() {
  if (_monacoEditor && typeof _monacoEditor.layout === 'function') _monacoEditor.layout();
  for (var key in state) {
    if (key.startsWith('paneMonaco_') && state[key] && typeof state[key].layout === 'function') state[key].layout();
  }
}

function splitPane(type, direction) {
  direction = direction || 'h';
  var editorArea = document.getElementById('editorArea');

  if (!_splitActive) {
    var editorContainer = document.getElementById('editorContainer');
    var splitContainer = document.createElement('div');
    splitContainer.className = 'split-container';
    splitContainer.id = 'splitContainer';
    splitContainer.dataset.direction = direction;
    splitContainer.style.flexDirection = direction === 'v' ? 'column' : 'row';

    var mainPane = document.createElement('div');
    mainPane.className = 'pane active-pane';
    mainPane.id = 'pane-0';
    mainPane.setAttribute('data-pane-id', '0');
    mainPane.addEventListener('mousedown', function(e) { _onPaneMousedown('0', e); });

    // 给 pane-0 也建立标准 pane-header + pane-body 结构
    mainPane.innerHTML =
      '<div class="pane-header">' +
        '<span class="pane-title" id="paneTitle-0">📄 编辑器</span>' +
      '</div>' +
      '<div class="pane-body" id="editorPaneBody-0"></div>';

    editorArea.insertBefore(splitContainer, editorContainer);
    splitContainer.appendChild(mainPane);
    document.getElementById('editorPaneBody-0').appendChild(editorContainer);
    _splitActive = true;
    _splitDirection = direction;
    _relayoutEditors();

    _addPaneToContainer(document.getElementById('splitContainer'), type);
    return;
  }

  var targetId = _activePaneId || '0';
  var targetEl = document.getElementById('pane-' + targetId);
  if (!targetEl) { showToast('找不到目标分屏', 'error'); return; }

  var container = _findSplitContainer(targetEl);
  if (!container) { showToast('无法分割此分屏', 'error'); return; }
  var containerDir = container.style.flexDirection === 'column' ? 'v' : 'h';

  if (direction === containerDir) {
    // 同方向：在同层追加（上限4个）
    _addPaneToContainer(container, type);
  } else {
    // 反方向：检查是否已嵌套
    if (container !== document.getElementById('splitContainer')) {
      showToast('已达最大嵌套深度', 'error'); return;
    }
    if (targetEl.querySelector('.split-container')) {
      showToast('该分屏已嵌套，不可继续分割', 'error'); return;
    }
    var oldBody = targetEl.querySelector('.pane-body');
    if (!oldBody) { showToast('无法分割此分屏', 'error'); return; }

    var outer = document.createElement('div');
    outer.className = 'split-container';
    outer.dataset.direction = direction;
    outer.style.cssText = 'flex:1;display:flex;flex-direction:' + (direction === 'v' ? 'column' : 'row') + ';overflow:hidden;min-height:0';
    var leftPane = document.createElement('div');
    leftPane.className = 'pane-nested';
    leftPane.style.cssText = 'flex:1;display:flex;flex-direction:column;overflow:hidden;min-height:0';
    leftPane.appendChild(oldBody);
    var divider = document.createElement('div');
    divider.className = 'split-divider divider-anim-in';
    var newPaneId = '' + (_paneCounter++);
    var newPane = document.createElement('div');
    newPane.className = 'pane pane-anim-in';
    newPane.id = 'pane-' + newPaneId;
    newPane.setAttribute('data-pane-id', newPaneId);
    newPane.addEventListener('mousedown', function(e) { _onPaneMousedown(newPaneId, e); });

    _initNewPane(newPane, newPaneId, type);
    outer.appendChild(leftPane);
    outer.appendChild(divider);
    outer.appendChild(newPane);
    targetEl.appendChild(outer);
    initDividerDrag(divider);
    setActivePane(newPaneId);
    requestAnimationFrame(function() {
      requestAnimationFrame(function() {
        newPane.classList.remove('pane-anim-in');
        divider.classList.remove('divider-anim-in');
      });
    });
  }
}

function _initNewPane(pane, newPaneId, type) {
  if (type === 'agent') {
    _agentPaneId = newPaneId;
    var panelAgent = document.getElementById('panel-agent');
    pane.innerHTML =
      '<div class="pane-header">' +
        '<span class="pane-title">🤖 Agent</span>' +
        '<button class="pane-close" onclick="closePane(\'' + newPaneId + '\')" title="关闭">✕</button>' +
      '</div>' +
      '<div class="pane-body" id="agentPaneBody-' + newPaneId + '"></div>';
    pane.style.flex = '1';
    pane.style.overflow = 'hidden';
    var newPaneBody = pane.querySelector('.pane-body');
    newPaneBody.appendChild(panelAgent);
    panelAgent.classList.add('split-pane-content');
    panelAgent.style.flexDirection = 'column';
    panelAgent.style.height = '100%';
    initAgentPanel();
  } else {
    pane.innerHTML =
      '<div class="pane-header">' +
        '<span class="pane-title" id="paneTitle-' + newPaneId + '">📄 编辑器</span>' +
        '<button class="pane-close" onclick="closePane(\'' + newPaneId + '\')" title="关闭">✕</button>' +
        '<button class="split-btn" onclick="savePaneFile(\'' + newPaneId + '\')" title="保存 (Ctrl+S)" style="font-size:11px">💾</button>' +
      '</div>' +
      '<div class="pane-body" id="editorPaneBody-' + newPaneId + '">' +
        '<div class="editor-tabs" id="editorTabs-' + newPaneId + '">' +
          '<button class="add-browser-tab-btn" onclick="openBrowserInPane(\'' + newPaneId + '\')" title="新建浏览器标签" style="background:transparent;border:none;font-size:13px;color:var(--fg-muted);cursor:pointer;padding:2px 6px;line-height:1;flex-shrink:0;white-space:nowrap">+🌐</button>' +
        '</div>' +
        '<div id="editorWrapper-' + newPaneId + '" style="flex:1;overflow:hidden;display:flex;flex-direction:column">' +
          '<div id="paneVditor-' + newPaneId + '" style="width:100%;height:100%"></div>' +
          '<div id="paneMonaco-' + newPaneId + '" style="width:100%;height:100%;display:none"></div>' +
          '<div id="panePdfContainer-' + newPaneId + '" style="width:100%;height:100%;display:none;flex-direction:column;overflow:auto">' +
            '<div class="pdf-toolbar" style="padding:4px 10px;gap:6px">' +
              '<button class="pdf-nav-btn" onclick="panePdfNav(\'' + newPaneId + '\',-1)">◀</button>' +
              '<input id="panePdfInfo-' + newPaneId + '" type="number" min="1" value="1" style="width:52px;padding:1px 4px;font-size:11px;background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:3px;text-align:center" onchange="panePdfGoToPage(\'' + newPaneId + '\',+this.value)">' +
              '<span style="font-size:11px;color:var(--fg-muted)" id="panePdfTotal-' + newPaneId + '">/ 1</span>' +
              '<button class="pdf-nav-btn" onclick="panePdfNav(\'' + newPaneId + '\',1)">▶</button>' +
              '<button class="pdf-nav-btn" onclick="panePdfZoom(\'' + newPaneId + '\',-0.2)">🔍-</button>' +
              '<span id="panePdfZoom-' + newPaneId + '" style="font-size:12px;color:var(--fg-muted)">100%</span>' +
              '<button class="pdf-nav-btn" onclick="panePdfZoom(\'' + newPaneId + '\',0.2)">🔍+</button>' +
              '<button class="pdf-nav-btn" onclick="togglePanePdfDual(\'' + newPaneId + '\')" title="双页视图">📖</button>' +
              '<button class="pdf-nav-btn" onclick="togglePanePdfOutline(\'' + newPaneId + '\')">📑</button>' +
            '</div>' +
            '<div style="display:flex;flex:1;overflow:hidden">' +
              '<div id="panePdfOutline-' + newPaneId + '" style="display:none;flex-direction:column;width:220px;min-width:140px;max-width:30vw;border-right:1px solid var(--border);background:var(--bg-secondary);flex-shrink:0;overflow-y:auto">' +
                '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 10px;border-bottom:1px solid var(--border);background:var(--bg)">' +
                  '<span style="font-size:11px;font-weight:600;color:var(--fg)">目录</span>' +
                  '<button onclick="document.getElementById(\'panePdfOutline-' + newPaneId + '\').style.display=\'none\'" style="background:transparent;border:none;color:var(--fg-muted);font-size:12px;cursor:pointer;padding:1px 4px">✕</button>' +
                '</div>' +
                '<div id="panePdfOutlineContent-' + newPaneId + '" style="padding:4px 0;font-size:11px"></div>' +
              '</div>' +
              '<div class="pdf-canvas-container" id="panePdfCanvasContainer-' + newPaneId + '" style="padding:8px">' +
                '<canvas id="panePdfCanvas-' + newPaneId + '"></canvas>' +
                '<canvas id="panePdfCanvas2-' + newPaneId + '" style="display:none"></canvas>' +
              '</div>' +
            '</div>' +
          '</div>' +
          '<div id="paneBrowserContainer-' + newPaneId + '" style="width:100%;height:100%;display:none;flex-direction:column;overflow:hidden">' +
            '<div style="display:flex;padding:4px 8px;gap:4px;align-items:center;border-bottom:1px solid var(--border);flex-shrink:0">' +
              '<input id="paneBrowserUrl-' + newPaneId + '" style="flex:1;padding:3px 6px;font-size:11px;background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:4px" placeholder="输入URL..." onkeydown="if(event.key===\'Enter\') navigatePaneBrowser(\'' + newPaneId + '\')">' +
              '<button class="tcb-btn" onclick="navigatePaneBrowser(\'' + newPaneId + '\')" style="font-size:11px">↵</button>' +
            '</div>' +
            '<iframe id="paneBrowserFrame-' + newPaneId + '" style="flex:1;border:none;width:100%" src="about:blank"></iframe>' +
          '</div>' +
        '</div>' +
      '</div>';
    state['paneTabs_' + newPaneId] = [];
    state['paneActiveTab_' + newPaneId] = null;
    state['paneFileContents_' + newPaneId] = {};
    state['paneVditorReady_' + newPaneId] = false;
    setTimeout(function() { initPaneVditor(newPaneId); }, 50);
    var newTabsEl = document.getElementById('editorTabs-' + newPaneId);
    if (newTabsEl) _setupPaneTabsDrop(newTabsEl, newPaneId);
  }
}

function navigatePaneBrowser(paneId) {
  var inp = document.getElementById('paneBrowserUrl-' + paneId);
  var frame = document.getElementById('paneBrowserFrame-' + paneId);
  if (!inp || !frame) return;
  var url = inp.value.trim();
  if (!url) return;
  if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;
  inp.value = url;
  frame.removeAttribute('srcdoc');
  _setFrameSandbox(frame, true);
  frame.src = '/api/browser/proxy?url=' + encodeURIComponent(url);
  var tabs = state['paneTabs_' + paneId] || [];
  for (var i = 0; i < tabs.length; i++) { if (tabs[i]._isBrowser) { tabs[i]._browserUrl = url; break; } }
}

function closePane(paneId, noAnim) {
  var pane = document.getElementById('pane-' + paneId);
  if (!pane) return;
  var container = _findSplitContainer(pane) || document.getElementById('splitContainer');

  // 如果关闭的是 Agent 分屏，把 panel-agent 移回 sidebar
  var isAgent = paneId === _agentPaneId;
  var panelAgent;
  if (isAgent) {
    panelAgent = document.getElementById('panel-agent');
    var sidebar = document.getElementById('sidebar');
    if (panelAgent && sidebar) {
      panelAgent.classList.remove('split-pane-content');
      panelAgent.style.flexDirection = '';
      panelAgent.style.height = '';
      var navPanels = sidebar.querySelector('.nav-tabs');
      if (navPanels) {
        sidebar.insertBefore(panelAgent, navPanels.nextSibling);
      } else {
        sidebar.appendChild(panelAgent);
      }
    }
    _agentPaneId = null;
  }

  // 找到关联的 divider
  var prev = pane.previousElementSibling;
  var next = pane.nextElementSibling;
  var divider;
  if (prev && prev.classList.contains('split-divider')) {
    divider = prev;
  } else if (next && next.classList.contains('split-divider')) {
    divider = next;
  }

  if (noAnim) {
    if (divider) divider.remove();
    pane.remove();
  } else {
    pane.classList.add('pane-anim-out');
    if (divider) divider.classList.add('divider-anim-out');
    setTimeout(function() {
      if (divider && divider.parentNode) divider.remove();
      if (pane.parentNode) pane.remove();
    }, 260);
  }

  // 如果只剩 pane-0 且是顶层容器，恢复原始结构
  var isTopContainer = container && container.id === 'splitContainer';
  if (isTopContainer) {
    var remaining = container.querySelectorAll(':scope > .pane');
    if (remaining.length <= 1 && remaining[0] && remaining[0].id === 'pane-0') {
      var editorContainer = document.getElementById('editorContainer');
      var editorArea = document.getElementById('editorArea');
      setTimeout(function() {
        if (container.parentNode) {
          editorArea.appendChild(editorContainer);
          container.remove();
          _splitActive = false;
          _relayoutEditors();
        }
      }, noAnim ? 0 : 260);
      _cleanupPaneState(paneId);
      return;
    }
  }

  // 激活第一个 pane（只在单层）
  if (container) {
    var firstPane = container.querySelector(':scope > .pane');
    if (firstPane) {
      setActivePane(firstPane.getAttribute('data-pane-id'));
    }
  }

  // 清理 pane 状态
  _cleanupPaneState(paneId);
  setTimeout(_relayoutEditors, 280);
}

function _cleanupPaneState(paneId) {
  // 若 pane 有 slides 标签页，先保存
  var paneTabs = state['paneTabs_' + paneId] || [];
  paneTabs.forEach(function(t) {
    if (t._isSlides) {
      slidesSaveCurrent();
      _slidesSaveToCache(t.path);
      delete _slidesNotebookCache[t.path];
    }
  });
  // 如果 slidesEditorView 在这个 pane 中，移回主容器
  if (_slidesEditorInPane === paneId) {
    _moveSlidesEditorToMain();
    document.getElementById('slidesEditorView').style.display = 'none';
  }
  delete state['paneTabs_' + paneId];
  delete state['paneActiveTab_' + paneId];
  delete state['paneFileContents_' + paneId];
  delete state['paneOriginalContents_' + paneId];
  delete state['paneVditorReady_' + paneId];
  var vditor = state['paneVditor_' + paneId];
  if (vditor && typeof vditor.destroy === 'function') {
    try { vditor.destroy(); } catch(e) {}
  }
  delete state['paneVditor_' + paneId];
  var paneMonaco = state['paneMonaco_' + paneId];
  if (paneMonaco && typeof paneMonaco.dispose === 'function') {
    try { paneMonaco.dispose(); } catch(e) {}
  }
  delete state['paneMonaco_' + paneId];
  // dispose all models created for this pane
  try {
    var api = window.monaco;
    if (api && api.editor) {
      paneTabs.forEach(function(t) {
        if (t._isMonaco) {
          var uri = api.Uri.file(paneId + '/' + t.path);
          var m = api.editor.getModel(uri);
          if (m) m.dispose();
        }
      });
    }
  } catch(e) {}
}

function _setFrameSandbox(frame, enable) {
  if (enable) {
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms');
  } else {
    frame.removeAttribute('sandbox');
  }
}

/* 关闭分屏编辑器 pane 中的 tab */
function closePaneTab(paneId, path) {
  var tabs = state['paneTabs_' + paneId] || [];
  var idx = tabs.findIndex(function(t) { return t.path === path; });
  if (idx < 0) return;
  var tab = tabs[idx];

  // 若为 slides 标签页，关闭前保存当前幻灯片内容到缓存
  if (tab._isSlides) {
    slidesSaveCurrent();
    _slidesSaveToCache(path);
    delete _slidesNotebookCache[path];
    if (_slidesActivePath === path) _slidesActivePath = null;
  }

  tabs.splice(idx, 1);
  state['paneTabs_' + paneId] = tabs;

  // 移除 tab DOM
  var tabsEl = document.getElementById('editorTabs-' + paneId);
  if (tabsEl) {
    var tabEl = tabsEl.querySelector('.tab[data-path="' + path + '"]');
    if (tabEl) tabEl.remove();
  }

  // 如果关闭的是当前活动 tab，切换到前一个
  if (state['paneActiveTab_' + paneId] === path) {
    if (tabs.length > 0) {
      var newActive = tabs[Math.max(0, idx - 1)] || tabs[0];
      editorService.switchInPane(newActive.path, paneId);
    } else {
      state['paneActiveTab_' + paneId] = null;
      // 如果 slidesEditorView 在这个 pane 中，移回主容器
      if (_slidesEditorInPane === paneId) {
        _moveSlidesEditorToMain();
        document.getElementById('slidesEditorView').style.display = 'none';
      }
      // 隐藏编辑器和 PDF 容器，显示空提示，但不销毁 DOM
      var vditorEl = document.getElementById('paneVditor-' + paneId);
      if (vditorEl) vditorEl.style.display = 'none';
      var pdfEl = document.getElementById('panePdfContainer-' + paneId);
      if (pdfEl) pdfEl.style.display = 'none';
      // 如果没有空提示 div 则创建
      var wrapper = document.getElementById('editorWrapper-' + paneId);
      if (wrapper && !wrapper.querySelector('.pane-empty-hint')) {
        var hint = document.createElement('div');
        hint.className = 'pane-empty-hint';
        hint.style.cssText = 'display:flex;align-items:center;justify-content:center;height:100%;color:var(--fg-muted);font-size:12px';
        hint.textContent = '在文件树中点击文件以在此打开';
        wrapper.appendChild(hint);
      } else if (wrapper) {
        var hintEl = wrapper.querySelector('.pane-empty-hint');
        if (hintEl) hintEl.style.display = 'flex';
      }
      var titleEl = document.getElementById('paneTitle-' + paneId);
      if (titleEl) titleEl.textContent = '📄 编辑器';
    }
  }
  _saveSession();
}

// ─── 跨分屏 Tab 拖拽传递 ──────────────────────────────────

function _getPaneIdForTabEl(tabEl) {
  // 从 tab 自身或父级 editor-tabs 推断 paneId
  if (tabEl.dataset.paneId) return tabEl.dataset.paneId;
  var tabsContainer = tabEl.closest('.editor-tabs');
  if (tabsContainer && tabsContainer.id === 'editorTabs') return '0';
  if (tabsContainer) {
    var m = tabsContainer.id.match(/^editorTabs-(.+)$/);
    if (m) return m[1];
  }
  return '0';
}

async function _moveTabBetweenPanes(srcPath, srcPaneId, dstPaneId) {
  if (srcPaneId === dstPaneId) return;
  // 从源 pane 移除
  var srcTabs = srcPaneId === '0' ? state.openTabs : (state['paneTabs_' + srcPaneId] || []);
  var idx = srcTabs.findIndex(function(t) { return t.path === srcPath; });
  if (idx < 0) return;
  var tabData = srcTabs[idx];
  srcTabs.splice(idx, 1);
  if (srcPaneId === '0') { state.openTabs = srcTabs; } else { state['paneTabs_' + srcPaneId] = srcTabs; }

  // 移除源 tab DOM
  var srcTabsEl = srcPaneId === '0' ? document.getElementById('editorTabs') : document.getElementById('editorTabs-' + srcPaneId);
  if (srcTabsEl) {
    var srcTabEl = srcTabsEl.querySelector('.tab[data-path="' + CSS.escape(srcPath) + '"]');
    if (srcTabEl) srcTabEl.remove();
  }

  // 先保存 slides 编辑器的内容到内存
  if (tabData._isSlides) {
    slidesSaveCurrent();
  }

  // 从源实例读取最新内容（Vditor 可能还有未同步的编辑）
  var latestContent = '';
  if (tabData._isPdf) {
    latestContent = '';
  } else if (tabData._isSlides) {
    // slides：DOM 整体迁移，无需内容复制；slidesSaveCurrent 已保存 Vditor 到 slidesState
    _slidesSaveToCache(srcPath);
  } else if (srcPaneId === '0') {
    // 主编辑器：从 state.fileContents 或 Vditor 获取
    if (state.vditor && state.vditorReady && state.activeTab === srcPath) {
      latestContent = state.vditor.getValue();
    } else {
      latestContent = state.fileContents[srcPath] || '';
    }
  } else {
    // 分屏：从 pane Vditor 或 paneFileContents 获取
    var srcVditor = state['paneVditor_' + srcPaneId];
    if (srcVditor && state['paneVditorReady_' + srcPaneId] && state['paneActiveTab_' + srcPaneId] === srcPath) {
      latestContent = srcVditor.getValue();
    } else {
      latestContent = (state['paneFileContents_' + srcPaneId] || {})[srcPath] || '';
    }
  }
  // 同步回源 state
  if (tabData._isSlides) {
    // slides：不做内容同步（DOM 整体迁移，cache 已更新）
    // 提前将 slidesEditorView 从源 pane 的 wrapper 移到主区，
    // 防止后续 innerHTML 清空时被销毁
    var sev = document.getElementById('slidesEditorView');
    var mainEw = document.getElementById('editorWrapper');
    if (sev && sev.parentNode !== mainEw) {
      mainEw.appendChild(sev);
    }
  } else if (srcPaneId === '0') {
    state.fileContents[srcPath] = latestContent;
  } else {
    state['paneFileContents_' + srcPaneId] = state['paneFileContents_' + srcPaneId] || {};
    state['paneFileContents_' + srcPaneId][srcPath] = latestContent;
  }

  // 如果源 pane 当前活动的是这个 tab，切换
  var srcActiveKey = srcPaneId === '0' ? 'activeTab' : ('paneActiveTab_' + srcPaneId);
  if (state[srcActiveKey] === srcPath) {
    if (srcTabs.length > 0) {
      var next = srcTabs[Math.max(0, idx - 1)] || srcTabs[0];
      if (srcPaneId === '0') {
        editorService.switchTo(next.path);
      } else {
        editorService.switchInPane(next.path, srcPaneId);
      }
    } else {
      state[srcActiveKey] = null;
      if (srcPaneId !== '0') {
        var w = document.getElementById('editorWrapper-' + srcPaneId);
        if (w) {
          // 隐藏编辑器和 PDF 容器，显示空提示，但不销毁 DOM
          var ve = document.getElementById('paneVditor-' + srcPaneId);
          if (ve) ve.style.display = 'none';
          var pe = document.getElementById('panePdfContainer-' + srcPaneId);
          if (pe) pe.style.display = 'none';
          if (!w.querySelector('.pane-empty-hint')) {
            var hint = document.createElement('div');
            hint.className = 'pane-empty-hint';
            hint.style.cssText = 'display:flex;align-items:center;justify-content:center;height:100%;color:var(--fg-muted);font-size:12px';
            hint.textContent = '在文件树中点击文件以在此打开';
            w.appendChild(hint);
          } else {
            var he = w.querySelector('.pane-empty-hint');
            he.style.display = 'flex';
          }
          // 清理 pane 的 PDF 会话（如果有）
          if (state['panePdfDoc_' + srcPaneId]) {
            try { state['panePdfDoc_' + srcPaneId].destroy(); } catch(e) {}
            delete state['panePdfDoc_' + srcPaneId];
          }
          delete state['panePdfPage_' + srcPaneId];
          delete state['panePdfZoom_' + srcPaneId];
          delete state['panePdfDualPage_' + srcPaneId];
        }
        var t = document.getElementById('paneTitle-' + srcPaneId);
        if (t) t.textContent = '📄 编辑器';
      }
    }
  }

  // 添加到目标 pane
  if (dstPaneId === '0') {
    // 移到主编辑器
    if (state.openTabs.find(function(t) { return t.path === srcPath; })) return;
    state.openTabs.push(tabData);
    state.fileContents[srcPath] = latestContent;
    // 转移 originalContents
    if (srcPaneId !== '0') {
      var srcOrig = (state['paneOriginalContents_' + srcPaneId] || {})[srcPath];
      state.originalContents[srcPath] = srcOrig !== undefined ? srcOrig : latestContent;
    } else {
      state.originalContents[srcPath] = state.originalContents[srcPath] || latestContent;
    }
    addTab(srcPath, tabData.name);
    editorService.switchTo(srcPath);
  } else {
    // 移到分屏 pane
    var dstTabs = state['paneTabs_' + dstPaneId] || [];
    if (dstTabs.find(function(t) { return t.path === srcPath; })) return;
    // 转移文件内容
    if (!tabData._isPdf) {
      state['paneFileContents_' + dstPaneId] = state['paneFileContents_' + dstPaneId] || {};
      state['paneFileContents_' + dstPaneId][srcPath] = latestContent;
      state['paneOriginalContents_' + dstPaneId] = state['paneOriginalContents_' + dstPaneId] || {};
      // 转移 originalContents
      if (srcPaneId === '0') {
        state['paneOriginalContents_' + dstPaneId][srcPath] = state.originalContents[srcPath] || latestContent;
      } else {
        var srcOrig = (state['paneOriginalContents_' + srcPaneId] || {})[srcPath];
        state['paneOriginalContents_' + dstPaneId][srcPath] = srcOrig !== undefined ? srcOrig : latestContent;
      }
    }
    dstTabs.push(tabData);
    state['paneTabs_' + dstPaneId] = dstTabs;
    // 添加 tab DOM
    var dstTabsEl = document.getElementById('editorTabs-' + dstPaneId);
    if (dstTabsEl) {
      var newTab = _createPaneTabEl(tabData.path, tabData.name, dstPaneId, tabData._isPdf, tabData._isSlides);
      dstTabsEl.appendChild(newTab);
    }
    editorService.switchInPane(srcPath, dstPaneId);
    // 如果是 PDF，需要重新加载
    if (tabData._isPdf) {
      await loadPdfInPane(srcPath, dstPaneId);
    } else if (!tabData._isSlides) {
      // 设置 Vditor 内容（slides 已通过 DOM 整体迁移）
      var vditorInstance = state['paneVditor_' + dstPaneId];
      if (vditorInstance && state['paneVditorReady_' + dstPaneId]) {
        vditorInstance.setValue(latestContent);
      }
    }
  }
}

function _createPaneTabEl(path, name, paneId, isPdf, isSlides) {
  var tabBtn = document.createElement('div');
  tabBtn.className = 'tab';
  tabBtn.dataset.path = path;
  tabBtn.dataset.paneId = paneId;
  tabBtn.draggable = true;
  var ext = path.includes('.') ? ('.' + path.split('.').pop().toLowerCase()) : '';
  var icon = isPdf ? '📄' : (isSlides ? '📔' : (ext === '.md' ? '📝' : '📄'));
  tabBtn.innerHTML = '<span style="font-size:11px">' + icon + '</span><span class="tab-label">' + escapeHtml(name) + '</span><span class="modified" style="display:none"></span><span class="close" onclick="event.stopPropagation();closePaneTab(\'' + paneId + '\',\'' + path + '\')">✕</span>';
  tabBtn.onclick = function() { editorService.switchInPane(path, paneId); };

  // 拖拽事件
  tabBtn.addEventListener('dragstart', function(e) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', path);
    e.dataTransfer.setData('application/x-pane-id', paneId);
    tabBtn.classList.add('dragging');
  });
  tabBtn.addEventListener('dragend', function() {
    tabBtn.classList.remove('dragging');
    document.querySelectorAll('.tab.drag-over').forEach(function(t) { t.classList.remove('drag-over'); });
    document.querySelectorAll('.editor-tabs.drag-target').forEach(function(t) { t.classList.remove('drag-target'); });
  });

  return tabBtn;
}

// 为分屏 editor-tabs 容器注册 drop 监听
function _setupPaneTabsDrop(tabsEl, paneId) {
  tabsEl.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    tabsEl.classList.add('drag-target');
  });
  tabsEl.addEventListener('dragleave', function(e) {
    if (!tabsEl.contains(e.relatedTarget)) {
      tabsEl.classList.remove('drag-target');
    }
  });
  tabsEl.addEventListener('drop', function(e) {
    e.preventDefault();
    tabsEl.classList.remove('drag-target');
    var srcPath = e.dataTransfer.getData('text/plain');
    var srcPaneId = e.dataTransfer.getData('application/x-pane-id') || '0';
    if (!srcPath || srcPaneId === paneId) return;
    // 检查目标 pane 是否已有此 tab
    var dstTabs = paneId === '0' ? state.openTabs : (state['paneTabs_' + paneId] || []);
    if (dstTabs.find(function(t) { return t.path === srcPath; })) return;
    _moveTabBetweenPanes(srcPath, srcPaneId, paneId);
  });
}

function setActivePane(paneId) {
  _activePaneId = paneId;
  var container = document.getElementById('splitContainer');
  if (!container) return;
  container.querySelectorAll('.pane').forEach(function(p) {
    p.classList.toggle('active-pane', p.getAttribute('data-pane-id') === paneId);
  });
}

function _findSplitContainer(el) {
  var p = el.parentElement;
  while (p) {
    if (p.classList && p.classList.contains('split-container')) return p;
    p = p.parentElement;
  }
  return document.getElementById('splitContainer') || null;
}

function initDividerDrag(divider) {
  divider.addEventListener('mousedown', function(e) {
    e.preventDefault();
    divider.classList.add('dragging');
    var container = _findSplitContainer(divider);
    var isVertical = container ? container.style.flexDirection === 'column' : (_splitDirection === 'v');
    var startPos = isVertical ? e.clientY : e.clientX;
    var panes = container.querySelectorAll('.pane');
    var startSizes = [];
    panes.forEach(function(p) { startSizes.push(isVertical ? p.offsetHeight : p.offsetWidth); });

    // 拖拽时禁用过渡以获得即时反馈
    panes.forEach(function(p) { p.classList.add('pane-no-transition'); });
    divider.classList.add('divider-no-transition');

    function onMove(e2) {
      var d = (isVertical ? e2.clientY : e2.clientX) - startPos;
      var panes = container.querySelectorAll('.pane');
      if (panes.length < 2 || !startSizes.length) return;

      var idx = -1;
      var children = Array.from(container.children);
      for (var i = 0; i < children.length; i++) {
        if (children[i] === divider) {
          var paneCount = 0;
          for (var j = 0; j < i; j++) {
            if (children[j].classList.contains('pane')) paneCount++;
          }
          idx = paneCount - 1;
          break;
        }
      }
      if (idx < 0 || idx >= startSizes.length - 1) return;

      var newA = startSizes[idx] + d;
      var newB = startSizes[idx + 1] - d;
      if (newA < 200 || newB < 200) return;

      panes[idx].style.flex = 'none';
      panes[idx + 1].style.flex = 'none';
      if (isVertical) {
        panes[idx].style.height = newA + 'px';
        panes[idx + 1].style.height = newB + 'px';
      } else {
        panes[idx].style.width = newA + 'px';
        panes[idx + 1].style.width = newB + 'px';
      }
    }

    function onUp() {
      divider.classList.remove('dragging');
      // 重新启用过渡 → 平滑归位
      panes.forEach(function(p) { p.classList.remove('pane-no-transition'); });
      divider.classList.remove('divider-no-transition');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}

// ─── Sidebar Resize ─────────────────────────────────────────

const resizeHandle = document.getElementById('resizeHandle');
const sidebar = document.getElementById('sidebar');
let isResizing = false;

resizeHandle.addEventListener('mousedown', (e) => {
  isResizing = true;
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
});

document.addEventListener('mousemove', (e) => {
  if (!isResizing) return;
  const newWidth = Math.max(180, Math.min(500, e.clientX));
  sidebar.style.width = newWidth + 'px';
});

document.addEventListener('mouseup', () => {
  isResizing = false;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
});

// ─── Mobile ─────────────────────────────────────────────────

document.getElementById('mobileMenu').addEventListener('click', () => {
  sidebar.classList.add('mobile-open');
});

document.getElementById('mobileClose').addEventListener('click', () => {
  sidebar.classList.remove('mobile-open');
});

document.addEventListener('click', (e) => {
  if (window.innerWidth <= 768 && sidebar.classList.contains('mobile-open')) {
    if (!sidebar.contains(e.target) && e.target.id !== 'mobileMenu') {
      sidebar.classList.remove('mobile-open');
    }
  }
});

// ─── Keyboard Shortcuts ─────────────────────────────────────

function closeShortcutHelp() {
  document.getElementById('shortcutHelpOverlay').classList.remove('active');
}

document.addEventListener('keydown', async (e) => {
  // Ctrl/Meta shortcuts
  if (e.ctrlKey || e.metaKey) {
    switch (e.key.toLowerCase()) {
      case 's':
        e.preventDefault();
        saveCurrentFile();
        break;
      case 'n':
        e.preventDefault();
        document.getElementById('btnNewFile').click();
        break;
    }
    return;
  }
  // 不处理输入框/文本域中的快捷键（除 R/? 外）
  const tag = e.target.tagName;
  const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable;
  // SaberSystem Dashboard 快捷键（仅在 dashboard 激活时生效）
  if (!state.activeNavTab || state.activeNavTab === 'dashboard') {
    switch (e.key) {
      case 'J': case 'j': case 'ArrowDown':
        e.preventDefault();
        _navTreeNextItem(1);
        break;
      case 'K': case 'k': case 'ArrowUp':
        e.preventDefault();
        _navTreeNextItem(-1);
        break;
      case 'Enter':
        if (!isInput) {
          e.preventDefault();
          const selPlanId = state.dashboard.selectedPlanId;
          if (selPlanId) selectDashPlan(selPlanId);
        }
        break;
      case ' ':
        if (!isInput) {
          e.preventDefault();
          const details = document.querySelector('.dash-tree-overlay details[open]');
          if (details) details.open = !details.open;
        }
        break;
      case 'Escape':
        if (document.getElementById('shortcutHelpOverlay').classList.contains('active')) {
          closeShortcutHelp();
        }
        break;
      case 'R': case 'r':
        if (!isInput) {
          e.preventDefault();
          const recoverBtn = document.getElementById('dashRecoverBtn');
          if (recoverBtn) recoverBtn.click();
        }
        break;
      case '1': case '2': case '3': case '4':
        if (!isInput) {
          e.preventDefault();
          const idx = parseInt(e.key) - 1;
          const optBtns = document.querySelectorAll('.dash-option-actions .dash-btn-primary:not(:disabled)');
          if (optBtns[idx]) optBtns[idx].click();
        }
        break;
      case '?':
        e.preventDefault();
        document.getElementById('shortcutHelpOverlay').classList.toggle('active');
        break;
      case 'N': case 'n':
        if (!isInput) {
          e.preventDefault();
          const addIdealBtn = document.getElementById('dashAddIdeal');
          if (addIdealBtn) addIdealBtn.click();
        }
        break;
      case 'D': case 'd':
        if (!isInput && state.dashboard.selectedPlanId) {
          e.preventDefault();
          if (await modalConfirm('确定归档当前选中的 Plan？')) {
            deleteEntity('plan', state.dashboard.selectedPlanId);
          }
        }
        break;
      case 'G': case 'g':
        if (!isInput) {
          e.preventDefault();
          generateDashDecision();
        }
        break;
      case 'F': case 'f':
        if (!isInput) {
          e.preventDefault();
          const markBtn = document.getElementById('dashMarkOpp');
          if (markBtn) markBtn.click();
        }
        break;
      case 'M': case 'm':
        if (!isInput) {
          e.preventDefault();
          const customize = document.querySelector('.dash-customize-box[style*="display: block"]');
          if (!customize) {
            const firstOpt = document.querySelector('.dash-customize-box');
            if (firstOpt) firstOpt.style.display = 'block';
          }
        }
        break;
    }
  }
});

// 树视图上下导航
function _navTreeNextItem(dir) {
  const items = document.querySelectorAll('.dash-plan[data-plan-id]');
  if (!items.length) return;
  let idx = -1;
  const selId = state.dashboard.selectedPlanId;
  for (let i = 0; i < items.length; i++) {
    if (items[i].dataset.planId === selId) { idx = i; break; }
  }
  const next = Math.max(0, Math.min(items.length - 1, idx + dir));
  const planId = items[next].dataset.planId;
  if (planId) selectDashPlan(planId);
  items[next].scrollIntoView({ block: 'nearest' });
}

// ─── Init ───────────────────────────────────────────────────

async function init() {
  try {
    var savedUrl = await Promise.race([
      loadServerUrl(),
      new Promise(function(r) { setTimeout(function() { r(null); }, 3000); })
    ]);
  } catch(e) {
    savedUrl = null;
  }

  // 无已存 URL 且非后端同源环境（如 Electron 纯前端）→ 弹窗引导配置
  var isBackendOrigin = !location.origin.startsWith('http://127.0.0.1:') && !location.origin.startsWith('http://localhost:');
  try {
    var testRes = await fetch(location.origin + '/api/system/stats');
    if (testRes.ok) isBackendOrigin = true;
  } catch {}
  // 鉴权检查 — 需要登录时停止后续加载
  var authed = await checkAuth();
  if (!authed) {
    console.log('Auth required, waiting for login...');
    return;
  }

  // 加载工作区列表
  await loadWorkspaces();

  if (!savedUrl && !isBackendOrigin) {
    showHtmlModal('🔗 配置服务器连接', `
      <div style="padding:12px">
        <p style="margin:0 0 12px;font-size:13px;color:var(--fg-muted)">请指定 TS2 后端服务器地址：</p>
        <input id="firstUrlInput" type="url" placeholder="http://192.168.x.x:6906" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:14px;font-family:monospace;box-sizing:border-box" autofocus>
        <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
          <button class="btn-action" onclick="saveFirstUrl()" style="padding:8px 20px">确定</button>
        </div>
      </div>
    `, '500px');
  }

  try {
    for (const d of EXPOSED_DIRS) {
      const res = await client.readDir(d);
      if (res.code === 0) {
        state.dirCache[d] = res.data;
        state.expandedDirs.add(d);
      }
    }
    // 如果有工作区根目录，也加载根目录列表
    if (!state.currentWorkspaceRoot) {
      var rootRes = await client.readDir('');
      if (rootRes.code === 0) {
        state.dirCache['.'] = rootRes.data;
      }
    }
    renderFileTree();
    renderWelcomeRecentFiles();
    renderWelcomeTaskSessions();
    // 检查是否有上次未关闭的标签页，弹窗询问是否恢复
    _checkSessionRestore();
  } catch(e) { console.warn('init: load dirs failed', e); }

  client.connectWS();

  await loadLanInfo();
  refreshServerInfo();

  // 立即加载课程和待办，不延迟到标签切换
  loadCourses();
  loadPushDashboard();

  var mainTabsEl = document.getElementById('editorTabs');
  if (mainTabsEl) _setupPaneTabsDrop(mainTabsEl, '0');

  console.log('TS2 Client v2.0 initialized');
  _startTimetableCheck();

  // 同步默认激活的 tab 状态（HTML 中第一个 nav-tab 已带 active 类，但 JS 状态需同步）
  const activeTabEl = document.querySelector('.nav-tab.active');
  if (activeTabEl) {
    state.activeNavTab = activeTabEl.dataset.tab;
  }
  // 初始化加载 Dashboard 数据
  loadDashboardPanel();
}

// ─── Workspace ──────────────────────────────────────────────

var _workspaces = [];

async function loadWorkspaces() {
  try {
    var res = await fetch(API_BASE + '/api/system/workspaces');
    var data = await res.json();
    if (data.code !== 0) return;
    _workspaces = data.data || [];
    var sel = document.getElementById('workspaceSelect');
    if (!sel) return;
    sel.innerHTML = '';
    // 默认选项：TS2 工作区（使用 EXPOSED_DIRS 硬编码路由）
    var defOpt = document.createElement('option');
    defOpt.value = '';
    defOpt.textContent = '📁 TS2 (默认)';
    sel.appendChild(defOpt);
    _workspaces.forEach(function(ws, i) {
      var opt = document.createElement('option');
      opt.value = ws.path;
      opt.textContent = ws.name + (ws.relaxed ? ' ★' : '');
      sel.appendChild(opt);
    });
    if (sel.options.length <= 1) {
      sel.innerHTML = '<option value="">无工作区</option>';
    }
    state.currentWorkspaceRoot = '';
  } catch(e) { console.warn('loadWorkspaces failed', e); }
}

async function switchWorkspace(path, code) {
  if (!path) {
    // 切回默认（TS2）模式
    state.currentWorkspaceRoot = '';
    state.dirCache = {};
    state.expandedDirs.clear();
    try {
      for (const d of EXPOSED_DIRS) {
        var r = await client.readDir(d);
        if (r.code === 0) {
          state.dirCache[d] = r.data;
          state.expandedDirs.add(d);
        }
      }
    } catch(e) {}
    renderFileTree();
    showToast('已切换到 TS2 默认模式', 'success');
    return;
  }
  _pendingSwitchPath = path;
  var body = { path: path };
  if (code) body.code = code;
  var res = await client.api('/api/system/switchWorkspace', body);
  if (res.code === 0) {
    _pendingSwitchPath = '';
    hideAuthDialog();
    showToast('已切换到工作区', 'success');
    state.currentWorkspaceRoot = path;
    state.dirCache = {};
    state.expandedDirs.clear();
    var r = await client.readDir('');
    if (r.code === 0) {
      state.dirCache['.'] = r.data;
    }
    renderFileTree();
  } else if (res.code === 403 || res.code === 401) {
    showToast(res.msg || '无权访问此工作区', 'error');
    showAuthDialog();
  } else {
    _pendingSwitchPath = '';
    showToast(res.msg || '切换失败', 'error');
  }
}

function saveFirstUrl() {
  var input = document.getElementById('firstUrlInput');
  if (!input) return;
  var url = input.value.trim().replace(/\/+$/, '');
  if (!url) { showToast('请输入服务器地址', 'error'); return; }
  API_BASE = url;
  settingsDBSet(SERVER_URL_KEY, url);
  document.getElementById('serverUrlInput').value = url;
  document.getElementById('serverUrlDisplay').textContent = url;
  closeHtmlModal();
  showToast('已设置服务器地址', 'success');
  if (client.ws) { client.ws.close(); client.ws = null; }
  client.connectWS();
  refreshServerInfo();
}

// ─── 多实例集群导入 ──────────────────────────────────────
(function() {
  // 动态创建弹窗 DOM
  const overlay = document.createElement('div');
  overlay.id = 'clusterModalOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:10000;display:none;align-items:center;justify-content:center;';
  overlay.innerHTML = `
    <div id="clusterModal" style="background:var(--bg,#1e1e2e);border-radius:12px;width:90%;max-width:520px;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.4);">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:16px;border-bottom:1px solid var(--border,#333);">
        <h3 style="margin:0;font-size:16px;">从其他实例导入</h3>
        <button id="clusterCloseBtn" style="background:none;border:none;color:var(--fg-muted);font-size:18px;cursor:pointer;">✕</button>
      </div>
      <div id="clusterContent" style="padding:16px;overflow-y:auto;flex:1;"></div>
    </div>
  `;
  document.body.appendChild(overlay);

  let _clusterUrl = '';
  let _clusterPath = '';
  let _selectedFiles = new Set();

  function closeClusterModal() {
    overlay.style.display = 'none';
    _clusterUrl = '';
    _clusterPath = '';
    _selectedFiles.clear();
  }

  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeClusterModal(); });
  document.getElementById('clusterCloseBtn').addEventListener('click', closeClusterModal);

  document.getElementById('srcClusterImportBtn').addEventListener('click', async () => {
    overlay.style.display = 'flex';
    _clusterUrl = '';
    _clusterPath = '';
    _selectedFiles.clear();
    const content = document.getElementById('clusterContent');
    content.innerHTML = '<div style="text-align:center;color:var(--fg-muted);padding:32px 0;">扫描实例中...</div>';
    try {
      const res = await client.api('/api/cluster/instances');
      const data = res.data ?? res;
      const self = data?.self;
      const peers = data?.peers ?? [];
      if (!peers.length) {
        content.innerHTML = '<div style="text-align:center;color:var(--fg-muted);padding:32px 0;">未发现其他 TS2 实例<br><small>确保其他实例正在运行</small></div>';
        return;
      }
      content.innerHTML = peers.map(p => `
        <div class="cluster-instance-card" data-url="${p.url}" style="display:flex;align-items:center;gap:12px;padding:12px;border-radius:8px;border:1px solid var(--border,#333);margin-bottom:8px;cursor:pointer;transition:background 0.15s;">
          <span style="font-size:24px;">🖥️</span>
          <div style="flex:1;">
            <div style="font-weight:600;font-size:14px;">${p.url}</div>
            <div style="font-size:11px;color:var(--fg-muted);">端口 ${p.port} · v${p.version}</div>
          </div>
          <span style="color:var(--accent);font-size:18px;">→</span>
        </div>
      `).join('');
      content.querySelectorAll('.cluster-instance-card').forEach(card => {
        card.addEventListener('click', () => selectClusterInstance(card.dataset.url));
        card.addEventListener('mouseenter', () => card.style.background = 'rgba(59,130,246,0.1)');
        card.addEventListener('mouseleave', () => card.style.background = '');
      });
    } catch {
      content.innerHTML = '<div style="text-align:center;color:var(--danger);padding:32px 0;">扫描失败</div>';
    }
  });

  async function selectClusterInstance(url) {
    _clusterUrl = url;
    _clusterPath = '';
    _selectedFiles.clear();
    await loadClusterDir('');
  }

  async function loadClusterDir(path) {
    _clusterPath = path;
    const content = document.getElementById('clusterContent');
    content.innerHTML = '<div style="text-align:center;color:var(--fg-muted);padding:16px;">加载中...</div>';
    try {
      const res = await client.api('/api/cluster/remote/readDir', { remote_url: _clusterUrl, path });
      const entries = Array.isArray(res.data) ? res.data : [];
      renderClusterBrowser(entries);
    } catch {
      content.innerHTML = '<div style="text-align:center;color:var(--danger);padding:16px;">加载失败</div>';
    }
  }

  function renderClusterBrowser(entries) {
    const content = document.getElementById('clusterContent');
    const pathParts = _clusterPath.split('/').filter(Boolean);
    const breadcrumb = `<span style="cursor:pointer;color:var(--accent);" onclick="loadClusterDir('')">根目录</span>` +
      pathParts.map((seg, i) => ` / <span style="cursor:pointer;color:var(--accent);" onclick="loadClusterDir('${pathParts.slice(0,i+1).join('/')}')">${seg}</span>`).join('');

    const entriesHtml = entries.map(e => {
      const icon = e.is_dir ? '📁' : srcFileIcon(e.ext || '');
      const selected = _selectedFiles.has(e.path);
      return `<div class="cluster-entry" data-path="${escapeHtml(e.path)}" data-is-dir="${e.is_dir}" style="display:flex;align-items:center;gap:8px;padding:8px 4px;border-radius:4px;cursor:pointer;${selected ? 'background:rgba(59,130,246,0.12);' : ''}">
        <span>${icon}</span>
        <span style="flex:1;${e.is_dir ? 'font-weight:600;' : ''}">${escapeHtml(e.name)}</span>
        ${!e.is_dir ? `<span style="color:${selected ? 'var(--accent)' : 'var(--fg-dim)'};font-size:14px;">${selected ? '✓' : '○'}</span>` : ''}
      </div>`;
    }).join('');

    const upBtn = _clusterPath ? `<div style="display:flex;align-items:center;gap:8px;padding:8px 4px;cursor:pointer;border-radius:4px;" onclick="loadClusterDir('${_clusterPath.split('/').slice(0,-1).join('/')}')"><span>📁</span><span>..</span></div>` : '';

    content.innerHTML = `
      <div style="margin-bottom:8px;">
        <button onclick="_clusterUrl='';_clusterPath='';document.getElementById('srcClusterImportBtn').click();" style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:13px;">← 返回实例列表</button>
        <span style="font-size:11px;color:var(--fg-muted);font-family:monospace;margin-left:8px;">${_clusterUrl}</span>
      </div>
      <div style="font-size:12px;margin-bottom:8px;color:var(--fg-muted);">${breadcrumb}</div>
      <div style="max-height:300px;overflow-y:auto;">${upBtn}${entriesHtml || '<div style="text-align:center;color:var(--fg-muted);padding:16px;">空目录</div>'}</div>
      ${_selectedFiles.size > 0 ? `<div style="display:flex;align-items:center;gap:8px;padding-top:12px;border-top:1px solid var(--border,#333);margin-top:12px;font-size:13px;">
        <span>已选 ${_selectedFiles.size} 个文件</span>
        <button id="clusterDoTransfer" style="background:var(--accent);color:#fff;border:none;border-radius:6px;padding:6px 16px;font-size:13px;cursor:pointer;">导入到当前目录</button>
        <button id="clusterClearSel" style="background:none;border:1px solid var(--border);color:var(--fg-muted);border-radius:6px;padding:6px 12px;font-size:12px;cursor:pointer;">清空</button>
      </div>` : ''}
    `;

    // 绑定事件
    content.querySelectorAll('.cluster-entry').forEach(el => {
      el.addEventListener('click', () => {
        const path = el.dataset.path;
        const isDir = el.dataset.isDir === 'true';
        if (isDir) {
          loadClusterDir(path);
        } else {
          if (_selectedFiles.has(path)) _selectedFiles.delete(path);
          else _selectedFiles.add(path);
          renderClusterBrowser(entries);
        }
      });
    });

    const doBtn = document.getElementById('clusterDoTransfer');
    if (doBtn) {
      doBtn.addEventListener('click', async () => {
        doBtn.disabled = true;
        doBtn.textContent = '传输中...';
        const prefix = state.srcCurrentPath ? state.srcCurrentPath + '/' : '';
        const files = Array.from(_selectedFiles).map(rp => ({ remote_path: rp, local_path: prefix + rp.split('/').pop() }));
        try {
          const res = await client.api('/api/cluster/transfer/batch', { remote_url: _clusterUrl, files });
          const data = res.data ?? res;
          const ok = data?.ok ?? 0;
          const fail = data?.fail ?? 0;
          _selectedFiles.clear();
          await srcLoadDir(state.srcCurrentPath || '');
          showToast(`导入完成：${ok} 个成功${fail > 0 ? '，' + fail + ' 个失败' : ''}`, 'success');
          closeClusterModal();
        } catch (e) {
          showToast('导入失败: ' + e.message, 'error');
          doBtn.disabled = false;
          doBtn.textContent = '导入到当前目录';
        }
      });
    }

    const clearBtn = document.getElementById('clusterClearSel');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => { _selectedFiles.clear(); renderClusterBrowser(entries); });
    }
  }

  // 暴露给 inline onclick
  window.loadClusterDir = loadClusterDir;
})();

// ─── Theme Toggle ──────────────────────────────────────

function lerpColor(a, b, t) {
  return '#' + [0,1,2].map(i => {
    var ca = parseInt(a.slice(1+i*2,3+i*2), 16);
    var cb = parseInt(b.slice(1+i*2,3+i*2), 16);
    return Math.round(ca + (cb - ca) * t).toString(16).padStart(2, '0');
  }).join('');
}

function getTimeColors() {
  var d = new Date();
  var h = d.getHours() + d.getMinutes() / 60;
  var phases = [
    { t: 0,  bg: '#0d1117', bg2: '#161b22', accent: '#58a6ff', fg: '#c9d1d9' },
    { t: 5,  bg: '#1a1b26', bg2: '#24283b', accent: '#7aa2f7', fg: '#c0caf5' },
    { t: 7,  bg: '#2d1b2e', bg2: '#3d2438', accent: '#f0a070', fg: '#e8d5c0' },
    { t: 10, bg: '#f5e6d0', bg2: '#fff5e6', accent: '#d97706', fg: '#3d2e1e' },
    { t: 12, bg: '#f5f5f0', bg2: '#ffffff', accent: '#4f73d1', fg: '#2c2c2c' },
    { t: 15, bg: '#e8f0fe', bg2: '#ffffff', accent: '#2563eb', fg: '#1e293b' },
    { t: 17, bg: '#f5e6d0', bg2: '#fff5e6', accent: '#d97706', fg: '#3d2e1e' },
    { t: 19, bg: '#2d1b2e', bg2: '#3d2438', accent: '#e8799b', fg: '#e8d5c0' },
    { t: 21, bg: '#16162a', bg2: '#1e1e3a', accent: '#a78bfa', fg: '#c4b5fd' },
    { t: 24, bg: '#0d1117', bg2: '#161b22', accent: '#58a6ff', fg: '#c9d1d9' },
  ];
  for (var i = 0; i < phases.length - 1; i++) {
    if (h >= phases[i].t && h < phases[i+1].t) {
      var t = (h - phases[i].t) / (phases[i+1].t - phases[i].t);
      return {
        bg: lerpColor(phases[i].bg, phases[i+1].bg, t),
        bg2: lerpColor(phases[i].bg2, phases[i+1].bg2, t),
        accent: lerpColor(phases[i].accent, phases[i+1].accent, t),
        fg: lerpColor(phases[i].fg, phases[i+1].fg, t),
      };
    }
  }
  return phases[phases.length-1];
}

var _gradientTimer = null;
var _gradientStyleEl = null;

function buildGradientCSS(c, isDark) {
  return 'html[data-theme="gradient"]{'
    + '--bg:' + c.bg + ';'
    + '--bg-secondary:' + c.bg2 + ';'
    + '--bg-tertiary:' + (isDark ? '#2f3349' : '#e8e8e4') + ';'
    + '--bg-hover:' + (isDark ? '#353a54' : '#e0e0dc') + ';'
    + '--fg:' + c.fg + ';'
    + '--fg-muted:' + (isDark ? '#565f89' : '#737373') + ';'
    + '--fg-dim:' + (isDark ? '#3b4261' : '#b0b0ac') + ';'
    + '--accent:' + c.accent + ';'
    + '--accent-hover:' + c.accent + ';'
    + '--accent-bg:' + c.accent.slice(0,7) + '1f' + ';'
    + '--green:#9ece6a;--green-bg:rgba(158,206,106,0.12);'
    + '--red:#f7768e;--red-bg:rgba(247,118,142,0.12);'
    + '--yellow:#e0af68;--yellow-bg:rgba(224,175,104,0.12);'
    + '--cyan:#7dcfff;--cyan-bg:rgba(125,207,255,0.12);'
    + '--purple:#bb9af7;--purple-bg:rgba(187,154,247,0.12);'
    + '--orange:#ff9e64;--orange-bg:rgba(255,158,100,0.12);'
    + '--border:' + (isDark ? '#3b4261' : '#d4d4d0') + ';'
    + '--border-light:' + (isDark ? '#414868' : '#e0e0dc') + ';'
    + '--radius:8px;--radius-lg:12px;'
    + '--shadow:' + (isDark ? '0 8px 24px rgba(0,0,0,0.4)' : '0 8px 24px rgba(0,0,0,0.12)') + ';'
    + '--font-mono:\'JetBrains Mono\',\'Fira Code\',\'Cascadia Code\',Consolas,monospace;'
    + '--font-sans:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;'
    + '--sidebar-w:280px;--toolbar-h:44px;--statusbar-h:28px;--tab-h:36px;--transition:0.2s ease;'
    + '}';
}

function applyGradientTheme() {
  var c = getTimeColors();
  var isDark = ['#0d1117','#1a1b26','#16162a','#2d1b2e'].some(function(x) { return c.bg.startsWith(x); });
  var css = buildGradientCSS(c, isDark);
  if (_gradientStyleEl) {
    _gradientStyleEl.textContent = css;
  } else {
    _gradientStyleEl = document.createElement('style');
    _gradientStyleEl.textContent = css;
    document.head.appendChild(_gradientStyleEl);
  }
}

function startGradientTheme() {
  stopGradientTheme();
  applyGradientTheme();
  _gradientTimer = setInterval(applyGradientTheme, 60000);
}

function stopGradientTheme() {
  if (_gradientTimer) { clearInterval(_gradientTimer); _gradientTimer = null; }
}

function clearGradientInlineStyles() {
  if (_gradientStyleEl) { _gradientStyleEl.remove(); _gradientStyleEl = null; }
}

function applyBaseTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document.getElementById('vditorContentTheme').href = theme === 'light'
    ? '/static/vditor/css/content-theme/light.css'
    : '/static/vditor/css/content-theme/dark.css';
}

function toggleTheme() {
  var gradOn = document.getElementById('gradientToggleInput').checked;
  var isLight = document.getElementById('themeToggleInput').checked;
  if (gradOn) {
    localStorage.setItem('ts2_light_mode', isLight);
    return;
  }
  var theme = isLight ? 'light' : 'dark';
  applyBaseTheme(theme);
  localStorage.setItem('ts2_static_theme', theme);
}

function toggleGradientTheme() {
  var isOn = document.getElementById('gradientToggleInput').checked;
  var isLight = document.getElementById('themeToggleInput').checked;
  localStorage.setItem('ts2_gradient_on', isOn);
  if (isOn) {
    stopGradientTheme();
    document.documentElement.setAttribute('data-theme', 'gradient');
    startGradientTheme();
    document.getElementById('vditorContentTheme').href = '/static/vditor/css/content-theme/dark.css';
  } else {
    stopGradientTheme();
    clearGradientInlineStyles();
    var theme = isLight ? 'light' : 'dark';
    applyBaseTheme(theme);
    localStorage.setItem('ts2_static_theme', theme);
  }
}

// 时钟更新
function setElColor(el, h, m) {
  var t = h + m / 60;
  var stops = [
    [0, '#7aa2f7'], [5, '#9ece6a'], [6, '#8b5cf6'],
    [7, '#f97316'], [8, '#facc15'], [12, '#22d3ee'],
    [16, '#06b6d4'], [17, '#f97316'], [19, '#a855f7'],
    [20, '#6366f1'], [23, '#7aa2f7'], [24, '#7aa2f7']
  ];
  for (var i = 0; i < stops.length - 1; i++) {
    var t0 = stops[i][0], c0 = stops[i][1];
    var t1 = stops[i+1][0], c1 = stops[i+1][1];
    if (t >= t0 && t < t1) {
      var f = (t - t0) / (t1 - t0);
      var r = function(a, b) { return Math.round(parseInt(a,16) + (parseInt(b,16) - parseInt(a,16)) * f); };
      el.style.color = 'rgb(' + r(c0.slice(1,3), c1.slice(1,3)) + ',' + r(c0.slice(3,5), c1.slice(3,5)) + ',' + r(c0.slice(5,7), c1.slice(5,7)) + ')';
      return;
    }
  }
  el.style.color = '';
}
function updateHeaderClock() {
  var el = document.getElementById('headerClock');
  var ap = document.getElementById('headerAmPm');
  if (!el) return;
  var d = new Date();
  var h = d.getHours(), m = d.getMinutes();
  el.textContent = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  if (ap) ap.textContent = h < 12 ? 'AM' : 'PM';
  setElColor(el, h, m);
}
setInterval(updateHeaderClock, 1000);
updateHeaderClock();

// ─── 快捷倒计时(持久化) ───
var _timerRemaining = 0;
var _timerTotal = 0;
var _timerRunning = false;
var _timerInterval = null;
var _timerPresets = [0, 5*60, 10*60, 25*60, 60*60];
var _timerIdx = 0;
var _activeTimerTaskId = '';

function _playTimerAlert() {
  try {
    var ctx = new (window.AudioContext || window.webkitAudioContext)();
    var g = ctx.createGain();
    g.connect(ctx.destination);
    g.gain.value = 0.3;
    var o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.value = 880;
    o.connect(g);
    o.start();
    o.stop(ctx.currentTime + 0.15);
    setTimeout(function() {
      var o2 = ctx.createOscillator();
      o2.type = 'sine';
      o2.frequency.value = 1100;
      o2.connect(ctx.createGain());
      o2.connect(g);
      o2.start();
      o2.stop(ctx.currentTime + 0.15);
    }, 200);
    setTimeout(function() { ctx.close(); }, 1000);
  } catch(e) {}
}

function _playTimerTick(ratio) {
  try {
    var ctx = new (window.AudioContext || window.webkitAudioContext)();
    var now = ctx.currentTime;
    var g = ctx.createGain();
    g.connect(ctx.destination);
    g.gain.setValueAtTime((0.003 / (1 - ratio + 0.05)) * 0.5, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
    var o = ctx.createOscillator();
    o.type = 'square';
    o.frequency.value = 1800;
    o.connect(g);
    o.start(now);
    o.stop(now + 0.04);
    setTimeout(function() { ctx.close(); }, 200);
  } catch(e) {}
}

function _onTimerExpired() {
  _timerRemaining = 0;
  _timerRunning = false;
  _activeTimerTaskId = '';
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  _playTimerAlert();
  showToast('⏰ 倒计时结束！', 'warning', 0);
  updateTimerDisplay();
  saveTimerState();
}

function saveTimerState() {
  localStorage.setItem('ts2_timer_total', _timerTotal);
  localStorage.setItem('ts2_timer_remaining', _timerRemaining);
  localStorage.setItem('ts2_timer_running', _timerRunning);
  localStorage.setItem('ts2_timer_idx', _timerIdx);
  localStorage.setItem('ts2_timer_saved_at', Date.now());
}

function restoreTimerState() {
  var total = parseInt(localStorage.getItem('ts2_timer_total')) || 0;
  var remaining = parseInt(localStorage.getItem('ts2_timer_remaining')) || 0;
  var running = localStorage.getItem('ts2_timer_running') === 'true';
  var idx = parseInt(localStorage.getItem('ts2_timer_idx')) || 0;
  var savedAt = parseInt(localStorage.getItem('ts2_timer_saved_at')) || 0;
  if (total === 0) return;
  _timerTotal = total;
  _timerIdx = idx;
  if (running && savedAt > 0) {
    var elapsed = Math.floor((Date.now() - savedAt) / 1000);
    _timerRemaining = Math.max(0, remaining - elapsed);
    _timerRunning = _timerRemaining > 0;
  } else {
    _timerRemaining = remaining;
    _timerRunning = false;
  }
  if (_timerRunning) {
    _timerInterval = setInterval(function() {
      _playTimerTick(1 - _timerRemaining / _timerTotal);
      _timerRemaining--;
      if (_timerRemaining <= 0) { _onTimerExpired(); }
      updateTimerDisplay(); saveTimerState();
    }, 1000);
  }
  updateTimerDisplay();
}

function updateTimerDisplay() {
  var el = document.getElementById('headerTimer');
  var navEl = document.getElementById('navTimer');
  if (!el) return;
  var text, cls;
  if (_timerTotal === 0) {
    text = '―:―'; cls = 'nav-timer';
  } else {
    var m = Math.floor(_timerRemaining / 60);
    var s = _timerRemaining % 60;
    text = (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
    cls = 'nav-timer';
    if (_timerRunning) cls += ' running';
    if (_timerRemaining <= 0) cls += ' alert';
  }
  el.textContent = text; el.className = 'header-timer' + cls.slice(9);
  if (navEl) { navEl.textContent = text; navEl.className = cls; }
}

function cycleTimer() {
  _activeTimerTaskId = "";
  _timerIdx = (_timerIdx + 1) % _timerPresets.length;
  _timerTotal = _timerPresets[_timerIdx];
  _timerRemaining = _timerTotal;
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  _timerRunning = false;
  if (_timerTotal > 0) {
    _timerRunning = true;
    _timerInterval = setInterval(function() {
      _playTimerTick(1 - _timerRemaining / _timerTotal);
      _timerRemaining--;
      if (_timerRemaining <= 0) { _onTimerExpired(); }
      updateTimerDisplay(); saveTimerState();
    }, 1000);
  }
  saveTimerState();
  updateTimerDisplay();
}

function resetTimer() {
  _activeTimerTaskId = "";
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  _timerRemaining = _timerTotal;
  _timerRunning = _timerTotal > 0;
  if (_timerRunning) {
    _timerInterval = setInterval(function() {
      _playTimerTick(1 - _timerRemaining / _timerTotal);
      _timerRemaining--;
      if (_timerRemaining <= 0) { _onTimerExpired(); }
      updateTimerDisplay(); saveTimerState();
    }, 1000);
  }
  saveTimerState();
  updateTimerDisplay();
}

function startTaskTimer(minutes, taskId) {
  if (!minutes || minutes <= 0) return;
  if (taskId && taskId === _activeTimerTaskId) return;
  _activeTimerTaskId = taskId || '';
  _timerTotal = Math.round(minutes * 60);
  _timerRemaining = _timerTotal;
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  _timerRunning = true;
  _timerInterval = setInterval(function() {
    _playTimerTick(1 - _timerRemaining / _timerTotal);
    _timerRemaining--;
    if (_timerRemaining <= 0) { _onTimerExpired(); }
    updateTimerDisplay(); saveTimerState();
  }, 1000);
  saveTimerState();
  updateTimerDisplay();
}

// 页面加载时恢复倒计时状态
restoreTimerState();

// ─── 指针时钟 ───
function drawAnalogClock() {
  var canvas = document.getElementById('welcomeClock');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var d = new Date();
  var cx = 90, cy = 90, r = 78;
  ctx.clearRect(0, 0, 180, 180);
  
  // 读取当前主题色
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim() || '#7aa2f7';
  var fg = style.getPropertyValue('--fg').trim() || '#c0caf5';
  var fgDim = style.getPropertyValue('--fg-dim').trim() || '#3b4261';
  var bg = style.getPropertyValue('--bg').trim() || '#1a1b26';
  
  // 外圈
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.strokeStyle = fgDim;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  
  // 内圈
  ctx.beginPath();
  ctx.arc(cx, cy, r - 6, 0, Math.PI * 2);
  ctx.strokeStyle = fgDim;
  ctx.lineWidth = 0.5;
  ctx.stroke();
  
  // 刻度
  for (var i = 0; i < 60; i++) {
    var a = i * 6 * Math.PI / 180 - Math.PI / 2;
    var isHour = i % 5 === 0;
    var len = isHour ? 8 : 4;
    var w = isHour ? 2.5 : 1;
    ctx.beginPath();
    ctx.moveTo(cx + (r - 14) * Math.cos(a), cy + (r - 14) * Math.sin(a));
    ctx.lineTo(cx + (r - 14 - len) * Math.cos(a), cy + (r - 14 - len) * Math.sin(a));
    ctx.strokeStyle = isHour ? accent : fgDim;
    ctx.lineWidth = w;
    ctx.stroke();
  }
  
  // 数字 (12, 3, 6, 9)
  var numR = r - 24;
  ctx.fillStyle = accent;
  ctx.font = 'bold 14px var(--font-sans, sans-serif)';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (var i = 0; i < 4; i++) {
    var angle = i * Math.PI / 2 - Math.PI / 2;
    ctx.fillText([12, 3, 6, 9][i], cx + numR * Math.cos(angle), cy + numR * Math.sin(angle));
  }
  
  var h = d.getHours() % 12;
  var m = d.getMinutes();
  var s = d.getSeconds();
  
  // 时针
  var ha = (h + m / 60) * 30 * Math.PI / 180 - Math.PI / 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + 32 * Math.cos(ha), cy + 32 * Math.sin(ha));
  ctx.strokeStyle = accent;
  ctx.lineWidth = 4;
  ctx.lineCap = 'round';
  ctx.stroke();
  
  // 分针
  var ma = (m + s / 60) * 6 * Math.PI / 180 - Math.PI / 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + 46 * Math.cos(ma), cy + 46 * Math.sin(ma));
  ctx.strokeStyle = fg;
  ctx.lineWidth = 2.5;
  ctx.lineCap = 'round';
  ctx.stroke();
  
  // 秒针
  var sa = s * 6 * Math.PI / 180 - Math.PI / 2;
  ctx.beginPath();
  ctx.moveTo(cx - 10 * Math.cos(sa), cy - 10 * Math.sin(sa));
  ctx.lineTo(cx + 54 * Math.cos(sa), cy + 54 * Math.sin(sa));
  ctx.strokeStyle = '#ff2d2d';
  ctx.lineWidth = 1.5;
  ctx.lineCap = 'round';
  ctx.stroke();
  
  // 中心点
  ctx.beginPath();
  ctx.arc(cx, cy, 3.5, 0, Math.PI * 2);
  ctx.fillStyle = accent;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(cx, cy, 1.5, 0, Math.PI * 2);
  ctx.fillStyle = bg;
  ctx.fill();
}

var _calViewYear, _calViewMonth;

function getTaskDateMap() {
  var map = {};
  if (!state.pushDashboard) return map;
  var cats = [
    { list: state.pushDashboard.overdue_tasks || [], cls: 'overdue' },
    { list: state.pushDashboard.due_tasks || [], cls: 'due' },
    { list: state.pushDashboard.in_progress_tasks || [], cls: 'progress' },
    { list: state.pushDashboard.pending_tasks || [], cls: 'pending' },
  ];
  cats.forEach(function(c) {
    c.list.forEach(function(t) {
      var key = t.due_date || t.start_time;
      if (!key) return;
      key = key.slice(0, 10);
      if (!map[key]) map[key] = [];
      map[key].push({ id: t.id, title: t.title, cls: c.cls, due_date: t.due_date, start_time: t.start_time, duration: t.duration });
    });
  });
  return map;
}

var _calCollapsed = localStorage.getItem('ts2_cal_collapsed') !== 'false';
var _calViewMode = localStorage.getItem('ts2_cal_view_mode') || 'calendar';

function toggleCalendar() {
  _calCollapsed = !_calCollapsed;
  localStorage.setItem('ts2_cal_collapsed', _calCollapsed);
  var grid = document.getElementById('calBoardGrid');
  if (grid) grid.style.display = _calCollapsed ? 'none' : '';
  var sched = document.getElementById('calScheduleView');
  if (sched) sched.style.display = _calCollapsed ? 'none' : '';
  var btn = document.getElementById('calToggleBtn');
  if (btn) btn.textContent = _calCollapsed ? '▶' : '▼';
}

function setCalViewMode(mode) {
  _calViewMode = mode;
  localStorage.setItem('ts2_cal_view_mode', mode);
  renderCalendarBoard();
}

function renderTodaySchedule() {
  var taskMap = getTaskDateMap();
  var now = new Date();
  var todayKey = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0');
  var tasks = taskMap[todayKey] || [];
  var overdue = (state.pushDashboard && state.pushDashboard.overdue_tasks) || [];
  var inProgress = (state.pushDashboard && state.pushDashboard.in_progress_tasks) || [];

  var html = '<div id="calScheduleView"' + (_calCollapsed ? ' style="display:none"' : '') + '>';

  html += '<div class="cal-sched-addbar">'
    + '<input id="schedQuickInput" class="cal-sched-input" placeholder="快速添加今日任务..."'
    + ' onkeydown="if(event.key===\'Enter\') quickAddTask(this.value)"'
    + ' spellcheck="false" autocomplete="off">'
    + '<button class="cal-sched-addbtn" onclick="quickAddTask(document.getElementById(\'schedQuickInput\').value)" title="添加">+</button>'
    + '</div>';

  if (overdue.length === 0 && tasks.length === 0 && inProgress.length === 0) {
    html += '<div style="padding:24px 16px;text-align:center;color:var(--fg-dim);font-size:12px">✓ 今日暂无任务</div>';
    html += '</div>';
    return html;
  }

  function formatDateLabel(dateStr) {
    if (!dateStr) return '';
    var parts = dateStr.split('T');
    var dateParts = parts[0].split('-');
    var label = parts[0].slice(5); // "MM-DD"
    if (parts.length > 1 && parts[1]) label += ' ' + parts[1].slice(0, 5);
    return label;
  }

  function renderGroup(items, cls, icon) {
    if (items.length === 0) return '';
    var h = '';
    items.slice(0, 8).forEach(function(t) {
      var title = t.title || t;
      if (typeof title === 'object') title = title.title;
      var timeParts = [];
      var st = t.start_time;
      var dd = t.due_date;
      if (st && st.length >= 10) timeParts.push('🕐 ' + formatDateLabel(st));
      if (dd && dd.length >= 10) timeParts.push('📅 ' + formatDateLabel(dd));
      if (t.duration) timeParts.push(t.duration + 'min');
      var timeStr = timeParts.length ? '<span class="cal-sched-time">' + timeParts.join(' ') + '</span>' : '';
      h += '<div class="cal-sched-item" onclick="sessionStorage.setItem(\'_hlTask\',\'' + (t.id || '') + '\');switchNavTab(\'tasks\');startTaskTimer(' + (t.duration || 0) + ',\'' + (t.id || '') + '\')">'
        + '<span class="cal-sched-line"></span>'
        + '<span class="cal-sched-dot ' + cls + '"></span>'
        + '<span class="cal-sched-title">' + escapeHtml(title) + '</span>'
        + (t.id ? '<span class="cal-sched-revert" onclick="event.stopPropagation();quickRevertTask(\'' + t.id + '\')" title="放回待办">↩</span><span class="cal-sched-check" onclick="event.stopPropagation();quickCompleteTask(\'' + t.id + '\')" title="标记完成">✓</span>' : '')
        + timeStr
        + '</div>';
    });
    if (items.length > 8) {
      h += '<div class="cal-sched-item" onclick="switchNavTab(\'tasks\')" style="color:var(--fg-dim);font-size:11px">'
        + '<span class="cal-sched-line"></span><span style="flex-shrink:0;width:12px;height:12px;margin-top:1px"></span>'
        + '<span>+' + (items.length - 8) + ' 更多</span></div>';
    }
    return h;
  }

  html += '<div style="padding:0 0 4px 0">';
  html += renderGroup(overdue, 'overdue', '');
  html += renderGroup(inProgress, 'progress', '');
  html += renderGroup(tasks, 'due', '');
  html += '</div>';
  html += '</div>';
  return html;
}

function quickCompleteTask(taskId) {
  if (!taskId) return;
  client.updateTask(taskId, { status: '已完成' }).then(function(res) {
    if (res.code === 0) {
      loadPushDashboard();
      loadTasks();
    }
  });
}

function quickRevertTask(taskId) {
  if (!taskId) return;
  client.updateTask(taskId, { status: '待办' }).then(function(res) {
    if (res.code === 0) {
      loadPushDashboard();
      loadTasks();
    }
  });
}

function quickAddTask(title) {
  title = title.trim();
  if (!title) return;
  var now = new Date();
  var todayKey = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0');
  client.createTask({ title: title, due_date: todayKey, status: '待办' }).then(function(res) {
    if (res.code === 0) {
      var inp = document.getElementById('schedQuickInput');
      if (inp) inp.value = '';
      loadPushDashboard();
    }
  });
}

function renderCalendarBoard(y, m) {
  var el = document.getElementById('welcomeCalendar');
  if (!el) return;
  var now = new Date();
  if (y === undefined) y = now.getFullYear();
  if (m === undefined) m = now.getMonth();
  _calViewYear = y; _calViewMonth = m;
  var first = (new Date(y, m, 1).getDay() + 6) % 7;
  var daysInMonth = new Date(y, m + 1, 0).getDate();
  var prevDays = new Date(y, m, 0).getDate();
  var moName = ['一','二','三','四','五','六','七','八','九','十','十一','十二'][m];
  var wd = ['一','二','三','四','五','六','日'];
  var today = now.getDate(), thisMonth = (now.getMonth() === m && now.getFullYear() === y);
  var taskMap = getTaskDateMap();

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  var isCal = _calViewMode === 'calendar';

  var html = '<div class="cal-board-tabs">'
    + '<span class="cal-tab' + (isCal ? ' active' : '') + '" onclick="setCalViewMode(\'calendar\')">📅 日历</span>'
    + '<span class="cal-tab' + (!isCal ? ' active' : '') + '" onclick="setCalViewMode(\'schedule\')">📋 日程</span>'
    + '</div>';

  if (isCal) {
    html += '<div class="cal-board-header">'
      + '<div class="cal-board-title">'
      + '<span id="calToggleBtn" onclick="toggleCalendar()" style="cursor:pointer;margin-right:6px;font-size:10px;color:var(--fg-dim)">' + (_calCollapsed ? '▶' : '▼') + '</span>'
      + y + '年 ' + moName + '月</div>'
      + '<div class="cal-board-nav">'
      + '<button onclick="renderCalendarBoard(_calViewYear,_calViewMonth-1)">◀</button>'
      + '<button onclick="renderCalendarBoard(_calViewYear,_calViewMonth+1)">▶</button>'
      + '</div></div>'
      + '<div id="calBoardGrid" class="cal-board-grid" style="' + (_calCollapsed ? 'display:none' : '') + '">';

    for (var i = 0; i < 7; i++) html += '<div class="cal-board-weekday">' + wd[i] + '</div>';

    var total = first + daysInMonth;
    var rows = Math.ceil(total / 7);
    for (var r = 0; r < rows * 7; r++) {
      var day, dateKey, cls = 'cal-board-day';
      if (r < first) {
        day = prevDays - first + r + 1;
        dateKey = (m === 0 ? y - 1 : y) + '-' + pad(m === 0 ? 12 : m) + '-' + pad(day);
        cls += ' other-month';
      } else if (r >= first + daysInMonth) {
        day = r - first - daysInMonth + 1;
        dateKey = (m === 11 ? y + 1 : y) + '-' + pad(m === 11 ? 1 : m + 2) + '-' + pad(day);
        cls += ' other-month';
      } else {
        day = r - first + 1;
        dateKey = y + '-' + pad(m + 1) + '-' + pad(day);
        if (thisMonth && day === today) cls += ' today';
      }

      var tasks = taskMap[dateKey];
      html += '<div class="' + cls + '" onclick="switchNavTab(\'tasks\')">';
      html += '<div class="cal-day-num">' + day + '</div>';
      if (tasks && tasks.length > 0) {
        html += '<div class="cal-day-tasks">';
        tasks.slice(0, 2).forEach(function(t) {
          html += '<div class="cal-day-task ' + t.cls + '" title="' + t.title + '">' + escapeHtml(t.title) + '</div>';
        });
        if (tasks.length > 2) html += '<div class="cal-day-task pending" style="font-size:9px;background:transparent">+' + (tasks.length - 2) + '</div>';
        html += '</div>';
      }
      html += '</div>';
    }
    html += '</div>';
  } else {
    html += renderTodaySchedule();
  }

  el.innerHTML = html;
}

function refreshCalendarBoard() {
  if (_calViewYear !== undefined) renderCalendarBoard(_calViewYear, _calViewMonth);
  else renderCalendarBoard();
}

function updateWelcomeDate() {
  var d = new Date();
  var mo = ['一','二','三','四','五','六','七','八','九','十','十一','十二'][d.getMonth()];
  document.getElementById('calMonth').textContent = mo + '月';
  document.getElementById('calDay').textContent = String(d.getDate()).padStart(2, '0');
  document.getElementById('calWeekday').textContent = '周' + ['日','一','二','三','四','五','六'][d.getDay()];
}

function startAnalogClock() {
  renderCalendarBoard();
  drawAnalogClock();
  updateWelcomeDate();
  setInterval(function() { drawAnalogClock(); updateWelcomeDate(); }, 1000);
}

// 页面加载后启动指针时钟
if (document.getElementById('welcomeClock')) {
  startAnalogClock();
} else if (document.getElementById('welcomeCalendar')) {
  renderCalendarBoard();
}

// 初始化主题开关状态
function initThemeToggle() {
  var savedTheme = localStorage.getItem('ts2_static_theme') || 'dark';
  var lightMode = localStorage.getItem('ts2_light_mode');
  var gradOn = localStorage.getItem('ts2_gradient_on');
  var dayInput = document.getElementById('themeToggleInput');
  var gradInput = document.getElementById('gradientToggleInput');
  if (dayInput) dayInput.checked = lightMode === 'true' ? true : (savedTheme === 'light');
  if (gradOn === 'true') {
    if (gradInput) gradInput.checked = true;
    document.documentElement.setAttribute('data-theme', 'gradient');
    startGradientTheme();
  } else {
    if (gradInput) gradInput.checked = false;
    if (savedTheme === 'gradient') savedTheme = 'dark';
    applyBaseTheme(savedTheme);
  }
}

// ─── 护眼休息 ──────────────────────────────────────

var _eyeRestTimer = null;
var _eyeRestActive = false;

function toggleEyeRest() {
  var on = document.getElementById('eyeRestToggle').checked;
  localStorage.setItem('ts2_eye_rest_enabled', on);
  if (on) {
    startEyeRest();
  } else {
    stopEyeRest();
    hideEyeRestOverlay();
  }
}

function restartEyeRest() {
  localStorage.setItem('ts2_eye_rest_interval', document.getElementById('eyeRestInterval').value);
  localStorage.setItem('ts2_eye_rest_duration', document.getElementById('eyeRestDuration').value);
  if (document.getElementById('eyeRestToggle').checked) {
    stopEyeRest();
    startEyeRest();
  }
}

function startEyeRest() {
  stopEyeRest();
  var interval = parseInt(document.getElementById('eyeRestInterval').value) * 60000;
  var now = Date.now();
  localStorage.setItem('ts2_eye_rest_session_start', now);
  _eyeRestTimer = setTimeout(showEyeRestOverlay, interval);
}

function stopEyeRest() {
  if (_eyeRestTimer) { clearTimeout(_eyeRestTimer); _eyeRestTimer = null; }
  localStorage.removeItem('ts2_eye_rest_session_start');
}

function showEyeRestOverlay() {
  if (_eyeRestActive) return;
  _eyeRestActive = true;
  localStorage.removeItem('ts2_eye_rest_session_start');
  var overlay = document.getElementById('eyeRestOverlay');
  var cd = document.getElementById('eyeRestCountdown');
  if (!overlay || !cd) return;
  var duration = parseInt(document.getElementById('eyeRestDuration').value);
  overlay.style.display = 'flex';
  overlay.style.opacity = 0;
  var fadeIn = 0;
  function fadeStep() { fadeIn += 0.05; overlay.style.opacity = fadeIn; if (fadeIn < 1) requestAnimationFrame(fadeStep); }
  requestAnimationFrame(fadeStep);
  cd.textContent = duration;
  var t = duration;
  var ticker = setInterval(function() { t--; cd.textContent = t >= 0 ? t : '0'; if (t < 0) { clearInterval(ticker); hideEyeRestOverlay(); } }, 1000);
  overlay._ticker = ticker;
  overlay.onclick = function() { clearInterval(ticker); hideEyeRestOverlay(); };
  setTimeout(function() { if (_eyeRestActive) { clearInterval(ticker); hideEyeRestOverlay(); } }, duration * 1000);
}

function hideEyeRestOverlay() {
  _eyeRestActive = false;
  var overlay = document.getElementById('eyeRestOverlay');
  if (overlay) { overlay.style.display = 'none'; if (overlay._ticker) clearInterval(overlay._ticker); }
  if (document.getElementById('eyeRestToggle').checked) startEyeRest();
}

// 初始化护眼休息(持久化)
function initEyeRest() {
  var saved = localStorage.getItem('ts2_eye_rest_enabled');
  var interval = localStorage.getItem('ts2_eye_rest_interval');
  var duration = localStorage.getItem('ts2_eye_rest_duration');
  if (interval) document.getElementById('eyeRestInterval').value = interval;
  if (duration) document.getElementById('eyeRestDuration').value = duration;
  if (saved === 'true') {
    document.getElementById('eyeRestToggle').checked = true;
    var sessionStart = localStorage.getItem('ts2_eye_rest_session_start');
    var intervalMs = parseInt(document.getElementById('eyeRestInterval').value) * 60000;
    if (sessionStart) {
      var elapsed = Date.now() - parseInt(sessionStart);
      var remaining = intervalMs - elapsed;
      if (remaining <= 0) {
        showEyeRestOverlay();
      } else {
        _eyeRestTimer = setTimeout(showEyeRestOverlay, remaining);
      }
    } else {
      startEyeRest();
    }
  }
}

// ─── Tunnel Settings ──────────────────────────────────────
let currentTunnelType = 'localtunnel';
let localInstances = [];

// 设置隧道类型
function setTunnelType(type) {
  currentTunnelType = type;
  document.querySelectorAll('.tunnel-type-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.type === type);
  });
  
  // 显示对应的配置面板
  document.querySelectorAll('.tunnel-config').forEach(el => el.style.display = 'none');
  document.getElementById('tunnelConfig' + type.charAt(0).toUpperCase() + type.slice(1)).style.display = 'block';
  
  // 更新提示文字
  const hints = {
    localtunnel: '使用 npx localtunnel，访问 https://xxx.loca.lt（推荐，最稳定）',
    serveo: '用 SSH 连接到 serveo.net，可能被校园网封锁',
    bore: '需要下载 bore 可执行文件，无需 VPS',
    frp: '需要自建 VPS，配置最灵活',
    cloudflare: '需要 Cloudflare 账号和 cloudflared，稳定可靠，支持自定义域名'
  };
  document.getElementById('tunnelTypeHint').textContent = hints[type];
}

// 扫描本地实例
async function scanLocalInstances() {
  try {
    const res = await fetch('/api/cluster/instances');
    const data = await res.json();
    if (data.code === 0 && data.data) {
      localInstances = [];
      if (data.data.self) localInstances.push(data.data.self);
      if (data.data.peers) localInstances.push(...data.data.peers);
      
      const select = document.getElementById('tunnelLocalPort');
      select.innerHTML = localInstances.map(inst => 
        `<option value="${inst.port}">端口 ${inst.port}${inst.self ? ' (当前实例)' : ''}</option>`
      ).join('');
    }
  } catch (e) {
    console.error('扫描实例失败:', e);
  }
}

// 加载隧道状态
async function loadTunnelStatus() {
  try {
    const res = await fetch('/api/tunnel/status');
    const data = await res.json();
    if (data.code === 0 && data.data) {
      const status = data.data;
      const statusEl = document.getElementById('tunnelStatus');
      const urlRow = document.getElementById('tunnelUrlRow');
      const urlEl = document.getElementById('tunnelUrl');
      const errorRow = document.getElementById('tunnelErrorRow');
      const errorEl = document.getElementById('tunnelError');
      const startBtn = document.getElementById('btnTunnelStart');
      const stopBtn = document.getElementById('btnTunnelStop');
      
      // 更新状态显示
      if (status.status === 'running') {
        statusEl.textContent = '已连接';
        statusEl.style.background = 'var(--green)';
        startBtn.disabled = true;
        stopBtn.disabled = false;
      } else if (status.status === 'starting') {
        statusEl.textContent = '启动中...';
        statusEl.style.background = '#f59e0b';
        startBtn.disabled = true;
        stopBtn.disabled = false;
      } else if (status.status === 'error') {
        statusEl.textContent = '错误';
        statusEl.style.background = 'var(--red)';
        startBtn.disabled = false;
        stopBtn.disabled = true;
      } else {
        statusEl.textContent = '未启动';
        statusEl.style.background = 'var(--fg-dim)';
        startBtn.disabled = false;
        stopBtn.disabled = true;
      }

      // 公网地址：只要有 URL 就显示（running 和 starting 都可能已有 URL）
      if (status.public_url) {
        urlRow.style.display = 'block';
        urlEl.textContent = status.public_url;
        urlEl.href = status.public_url;
      } else {
        urlRow.style.display = 'none';
      }

      // 错误信息
      if (status.error) {
        errorRow.style.display = 'block';
        errorEl.textContent = status.error;
      } else {
        errorRow.style.display = 'none';
      }
    }
  } catch (e) {
    console.error('加载隧道状态失败:', e);
  }
}

// 启动隧道
async function startTunnel() {
  const startBtn = document.getElementById('btnTunnelStart');
  startBtn.disabled = true;
  startBtn.textContent = '启动中...';
  
  try {
    // 先保存设置
    const settings = { tunnel_type: currentTunnelType };
    
    if (currentTunnelType === 'localtunnel') {
      settings.local_port = parseInt(document.getElementById('tunnelLocalPort').value);
    } else if (currentTunnelType === 'serveo') {
      settings.local_port = parseInt(document.getElementById('serveoLocalPort').value);
      settings.subdomain = document.getElementById('serveoSubdomain').value;
    } else if (currentTunnelType === 'bore') {
      settings.local_port = parseInt(document.getElementById('boreLocalPort').value);
    } else if (currentTunnelType === 'frp') {
      settings.server_addr = document.getElementById('frpServerAddr').value;
      settings.server_port = parseInt(document.getElementById('frpServerPort').value);
      settings.token = document.getElementById('frpToken').value;
      settings.local_port = parseInt(document.getElementById('frpLocalPort').value);
      settings.remote_port = parseInt(document.getElementById('frpRemotePort').value);
    } else if (currentTunnelType === 'cloudflare') {
      settings.cf_tunnel_token = document.getElementById('cfToken').value;
      settings.cf_domain = document.getElementById('cfDomain').value;
      settings.local_port = parseInt(document.getElementById('cfLocalPort').value);
    }
    
    await fetch('/api/tunnel/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings)
    });
    
    // 启动隧道
    const res = await fetch('/api/tunnel/start', { method: 'POST' });
    const data = await res.json();
    const result = data.data || {};
    
    if (data.code === 0) {
      if (result.status === 'starting') {
        showToast('隧道正在启动，请稍候...');
      } else {
        showToast('隧道启动成功');
      }
    } else {
      showToast(data.msg || '隧道启动失败', 'error');
    }
  } catch (e) {
    showToast('启动失败: ' + e.message, 'error');
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = '启动隧道';
    // 立即刷新一次，再延迟刷新等待隧道完全启动
    loadTunnelStatus();
    setTimeout(loadTunnelStatus, 3000);
    setTimeout(loadTunnelStatus, 8000);
  }
}

// 停止隧道
async function stopTunnel() {
  const stopBtn = document.getElementById('btnTunnelStop');
  stopBtn.disabled = true;
  
  try {
    const res = await fetch('/api/tunnel/stop', { method: 'POST' });
    const data = await res.json();
    
    if (data.code === 0) {
      showToast('隧道已停止');
    } else {
      showToast(data.msg || '停止失败', 'error');
    }
  } catch (e) {
    showToast('停止失败: ' + e.message, 'error');
  } finally {
    loadTunnelStatus();
  }
}

// 暴露给全局
window.setTunnelType = setTunnelType;
window.scanLocalInstances = scanLocalInstances;
window.loadTunnelStatus = loadTunnelStatus;
window.startTunnel = startTunnel;
window.stopTunnel = stopTunnel;

// 初始化
function initTunnel() {
  scanLocalInstances();
  loadTunnelStatus();
  // 不自动刷新，用户手动点"刷新状态"按钮时才查询
}

// 页面加载时初始化主题 & 护眼
(function initOnLoad() {
  initThemeToggle();
  initEyeRest();
})();

// 在切换到设置面板时初始化
document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    if (tab.dataset.tab === 'settings') {
      initTunnel();
      initThemeToggle();
      initEyeRest();
      initAcSettings();
    }
  });
});

// ─── 编辑器自动补全 ──────────────────────────────────────────
const LATEX_COMMANDS = {
  'alpha':'α','beta':'β','gamma':'γ','delta':'δ','epsilon':'ε','varepsilon':'ε','zeta':'ζ','eta':'η','theta':'θ','vartheta':'ϑ',
  'iota':'ι','kappa':'κ','lambda':'λ','mu':'μ','nu':'ν','xi':'ξ','pi':'π','rho':'ρ','sigma':'σ','tau':'τ','upsilon':'υ','phi':'φ','varphi':'ϕ','chi':'χ','psi':'ψ','omega':'ω',
  'Gamma':'Γ','Delta':'Δ','Theta':'Θ','Lambda':'Λ','Xi':'Ξ','Pi':'Π','Sigma':'Σ','Upsilon':'Υ','Phi':'Φ','Psi':'Ψ','Omega':'Ω',
  'frac':'\\frac{a}{b}','dfrac':'\\dfrac{a}{b}','sqrt':'\\sqrt{x}','sum':'\\sum_{i=1}^{n}','prod':'\\prod_{i=1}^{n}','int':'\\int_{a}^{b}',
  'iint':'\\iint','iiint':'\\iiint','oint':'\\oint','lim':'\\lim_{x \\to }',
  'leq':'≤','geq':'≥','neq':'≠','approx':'≈','equiv':'≡','sim':'∼','propto':'∝','perp':'⊥','parallel':'∥',
  'in':'∈','notin':'∉','subset':'⊂','supset':'⊃','subseteq':'⊆','supseteq':'⊇','cup':'∪','cap':'∩','emptyset':'∅',
  'rightarrow':'→','leftarrow':'←','leftrightarrow':'↔','Rightarrow':'⇒','Leftarrow':'⇐','mapsto':'↦',
  'sin':'\\sin','cos':'\\cos','tan':'\\tan','ln':'\\ln','log':'\\log','exp':'\\exp','det':'\\det',
  'hat':'\\hat{x}','bar':'\\bar{x}','vec':'\\vec{x}','dot':'\\dot{x}','ddot':'\\ddot{x}','tilde':'\\tilde{x}',
  'mathbf':'\\mathbf{x}','mathbb':'\\mathbb{R}','mathcal':'\\mathcal{L}','mathrm':'\\mathrm{x}',
  'begin':'\\begin{aligned}\n\n\\end{aligned}','pmatrix':'\\begin{pmatrix}\na & b \\\\\nc & d\n\\end{pmatrix}',
  'bmatrix':'\\begin{bmatrix}\na & b \\\\\nc & d\n\\end{bmatrix}','cases':'\\begin{cases}\na, & x > 0 \\\\\nb, & \\text{otherwise}\n\\end{cases}',
  'nabla':'∇','partial':'∂','infty':'∞','hbar':'ℏ','forall':'∀','exists':'∃',
  'text':'\\text{}','quad':'\\quad','cdots':'⋯','ldots':'…','boxed':'\\boxed{x}',
};

const SNIPPETS = {
  'table':'| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n|  |  |  |',
  'math':'$$\n\n$$','mathinline':'$ $',
  'code':'```\n\n```','codepython':'```python\n\n```','codejs':'```javascript\n\n```',
  'quote':'> ','task':'- [ ] ','h1':'# ','h2':'## ','h3':'### ',
  'hr':'---','img':'![描述](url)','link':'[文本](url)',
  'bold':'**粗体**','italic':'*斜体*',
  'mermaid':'```mermaid\ngraph TD\n    A --> B\n```',
};

const DEFAULT_DICTS = [
  { name:'数学名词（中文）', enabled:true, entries:[
    {keyword:'极限',value:'极限',desc:'lim'},{keyword:'导数',value:'导数',desc:"f'(x)"},
    {keyword:'偏导',value:'偏导数',desc:'∂f/∂x'},{keyword:'积分',value:'积分',desc:'∫'},
    {keyword:'矩阵',value:'矩阵',desc:'A ∈ ℝᵐˣⁿ'},{keyword:'行列式',value:'行列式',desc:'det(A)'},
    {keyword:'特征值',value:'特征值',desc:'λ'},{keyword:'概率',value:'概率',desc:'P(A)'},
    {keyword:'期望',value:'期望',desc:'E[X]'},{keyword:'方差',value:'方差',desc:'Var(X)'},
    {keyword:'正态分布',value:'正态分布',desc:'N(μ,σ²)'},{keyword:'傅里叶变换',value:'傅里叶变换',desc:'F(ω)'},
    {keyword:'微分方程',value:'微分方程'},{keyword:'泰勒展开',value:'泰勒展开'},
  ]},
  { name:'物理名词（中文）', enabled:true, entries:[
    {keyword:'动量',value:'动量',desc:'p = mv'},{keyword:'角动量',value:'角动量',desc:'L = r × p'},
    {keyword:'动能',value:'动能',desc:'Eₖ = ½mv²'},{keyword:'势能',value:'势能',desc:'Eₚ'},
    {keyword:'引力',value:'万有引力',desc:'F = GMm/r²'},{keyword:'电场',value:'电场',desc:'E'},
    {keyword:'磁场',value:'磁场',desc:'B'},{keyword:'麦克斯韦方程',value:'麦克斯韦方程组'},
    {keyword:'熵',value:'熵',desc:'S'},{keyword:'波函数',value:'波函数',desc:'ψ'},
    {keyword:'薛定谔方程',value:'薛定谔方程',desc:'iℏ∂ψ/∂t = Ĥψ'},
    {keyword:'不确定性原理',value:'不确定性原理',desc:'ΔxΔp ≥ ℏ/2'},
    {keyword:'质能方程',value:'质能方程',desc:'E = mc²'},
    {keyword:'哈密顿量',value:'哈密顿量',desc:'Ĥ'},{keyword:'拉格朗日量',value:'拉格朗日量',desc:'L'},
  ]},
  { name:'生物名词（中文）', enabled:false, entries:[
    {keyword:'细胞',value:'细胞'},{keyword:'蛋白质',value:'蛋白质'},{keyword:'基因',value:'基因'},
    {keyword:'转录',value:'转录'},{keyword:'翻译',value:'翻译'},{keyword:'突变',value:'突变'},
    {keyword:'光合作用',value:'光合作用'},{keyword:'免疫',value:'免疫'},
  ]},
  { name:'化学名词（中文）', enabled:false, entries:[
    {keyword:'原子',value:'原子'},{keyword:'分子',value:'分子'},{keyword:'离子',value:'离子'},
    {keyword:'共价键',value:'共价键'},{keyword:'氧化',value:'氧化'},{keyword:'还原',value:'还原'},
    {keyword:'催化剂',value:'催化剂'},{keyword:'同位素',value:'同位素'},
  ]},
  { name:'数学名词（English）', enabled:true, entries:[
    {keyword:'limit',value:'limit',desc:'lim'},{keyword:'derivative',value:'derivative',desc:"f'(x)"},
    {keyword:'integral',value:'integral',desc:'∫'},{keyword:'matrix',value:'matrix',desc:'A ∈ ℝᵐˣⁿ'},
    {keyword:'eigenvalue',value:'eigenvalue',desc:'λ'},{keyword:'probability',value:'probability',desc:'P(A)'},
    {keyword:'variance',value:'variance',desc:'Var(X)'},{keyword:'Fourier transform',value:'Fourier transform',desc:'F(ω)'},
    {keyword:'differential equation',value:'differential equation'},{keyword:'PDE',value:'partial differential equation'},
  ]},
  { name:'物理名词（English）', enabled:true, entries:[
    {keyword:'momentum',value:'momentum',desc:'p = mv'},{keyword:'energy',value:'energy',desc:'E'},
    {keyword:'force',value:'force',desc:'F = ma'},{keyword:'electric field',value:'electric field',desc:'E'},
    {keyword:'magnetic field',value:'magnetic field',desc:'B'},{keyword:'entropy',value:'entropy',desc:'S'},
    {keyword:'wave function',value:'wave function',desc:'ψ'},{keyword:'Schrödinger equation',value:'Schrödinger equation',desc:'iℏ∂ψ/∂t = Ĥψ'},
    {keyword:'Hamiltonian',value:'Hamiltonian',desc:'Ĥ'},{keyword:'Lagrangian',value:'Lagrangian',desc:'L'},
  ]},
  { name:'生物名词（English）', enabled:false, entries:[
    {keyword:'cell',value:'cell'},{keyword:'protein',value:'protein'},{keyword:'gene',value:'gene'},
    {keyword:'transcription',value:'transcription'},{keyword:'mutation',value:'mutation'},{keyword:'evolution',value:'evolution'},
  ]},
  { name:'化学名词（English）', enabled:false, entries:[
    {keyword:'atom',value:'atom'},{keyword:'molecule',value:'molecule'},{keyword:'ion',value:'ion'},
    {keyword:'covalent bond',value:'covalent bond'},{keyword:'oxidation',value:'oxidation'},{keyword:'catalyst',value:'catalyst'},
  ]},
];

function loadAcConfig() {
  try { const r = localStorage.getItem('ts2_autocomplete_config'); if(r) return JSON.parse(r); } catch{}
  return { latex:true, snippets:true, dicts:true, dictGroups: DEFAULT_DICTS };
}
function saveAcConfig(c) { localStorage.setItem('ts2_autocomplete_config', JSON.stringify(c)); }

function buildHintExtends(cfg) {
  const ext = [];
  if (cfg.latex) {
    ext.push({ key:'\\', hint: async function(key) {
      if (!key) { const c=['frac','sqrt','sum','int','lim','begin','alpha','beta']; return c.map(n=>({html:'<span style="color:#c678dd">\\'+n+'</span> <span style="color:#888;font-size:11px">'+(LATEX_COMMANDS[n]||'')+'</span>',value:LATEX_COMMANDS[n]||('\\'+n)})); }
      const lk=key.toLowerCase(); return Object.entries(LATEX_COMMANDS).filter(([n])=>n.toLowerCase().startsWith(lk)).slice(0,8).map(([n,v])=>({html:'<span style="color:#c678dd">\\'+n+'</span> <span style="color:#888;font-size:11px">'+(v.length>30?v.substring(0,30)+'…':v)+'</span>',value:v}));
    }});
  }
  if (cfg.snippets) {
    ext.push({ key:'!', hint: async function(key) {
      const lk=key.toLowerCase(); const m=Object.entries(SNIPPETS).filter(([n])=>n.toLowerCase().startsWith(lk)).slice(0,8);
      return m.map(([n,v])=>({html:'<span style="color:#e5c07b">!'+n+'</span> <span style="color:#888;font-size:11px">'+v.split('\n')[0]+'</span>',value:v}));
    }});
  }
  if (cfg.dicts) {
    var zhE=[], enE=[];
    cfg.dictGroups.forEach(function(g){ if(g.enabled){ if(g.name.indexOf('中文')>=0) zhE.push(...g.entries); else if(g.name.indexOf('English')>=0) enE.push(...g.entries); else zhE.push(...g.entries); }});
    if(zhE.length>0) ext.push({ key:'@', hint: async function(key) {
      if(!key) return zhE.slice(0,8).map(e=>({html:'<span style="color:#61afef">@'+e.keyword+'</span>'+(e.desc?' <span style="color:#888;font-size:11px">'+e.desc+'</span>':''),value:e.value}));
      var lk=key.toLowerCase(); return zhE.filter(e=>e.keyword.toLowerCase().includes(lk)||e.value.toLowerCase().includes(lk)).slice(0,8).map(e=>({html:'<span style="color:#61afef">@'+e.keyword+'</span>'+(e.desc?' <span style="color:#888;font-size:11px">'+e.desc+'</span>':''),value:e.value}));
    }});
    if(enE.length>0) ext.push({ key:'&', hint: async function(key) {
      if(!key) return enE.slice(0,8).map(e=>({html:'<span style="color:#56b6c2">&'+e.keyword+'</span>'+(e.desc?' <span style="color:#888;font-size:11px">'+e.desc+'</span>':''),value:e.value}));
      var lk=key.toLowerCase(); return enE.filter(e=>e.keyword.toLowerCase().includes(lk)||e.value.toLowerCase().includes(lk)).slice(0,8).map(e=>({html:'<span style="color:#56b6c2">&'+e.keyword+'</span>'+(e.desc?' <span style="color:#888;font-size:11px">'+e.desc+'</span>':''),value:e.value}));
    }});
  }
  return ext;
}

function saveAcToggle() {
  const cfg = loadAcConfig();
  cfg.latex = document.getElementById('acLatex').checked;
  cfg.snippets = document.getElementById('acSnippets').checked;
  cfg.dicts = document.getElementById('acDicts').checked;
  saveAcConfig(cfg);
  renderAcDicts();
}

function renderAcDicts() {
  const cfg = loadAcConfig();
  const panel = document.getElementById('acDictPanel');
  const list = document.getElementById('acDictList');
  if (!panel || !list) return;
  panel.style.display = cfg.dicts ? '' : 'none';
  let html = '';
  cfg.dictGroups.forEach((g, gi) => {
    html += '<div style="margin-bottom:6px;border:1px solid var(--border);border-radius:4px;overflow:hidden">';
    html += '<div style="display:flex;align-items:center;gap:6px;padding:6px 8px;background:var(--bg)">';
    html += '<label class="sync-toggle" style="transform:scale(0.75)"><input type="checkbox" '+(g.enabled?'checked':'')+' onchange="toggleAcDict('+gi+',this.checked)"><span class="sync-toggle-slider"></span></label>';
    html += '<span style="flex:1;font-size:12px;font-weight:500;'+(g.enabled?'':'opacity:0.5')+'">'+g.name+'</span>';
    html += '<span style="font-size:10px;color:var(--fg-dim)">'+g.entries.length+'条</span>';
    html += '<button style="background:none;border:none;color:var(--fg-dim);cursor:pointer;font-size:11px" onclick="removeAcDict('+gi+')">✕</button>';
    html += '</div></div>';
  });
  list.innerHTML = html;
}

function toggleAcDict(idx, checked) {
  const cfg = loadAcConfig();
  cfg.dictGroups[idx].enabled = checked;
  saveAcConfig(cfg);
  renderAcDicts();
}

function addAcDict() {
  const inp = document.getElementById('acNewDictName');
  const name = (inp.value||'').trim();
  if (!name) return;
  const cfg = loadAcConfig();
  cfg.dictGroups.push({name:name,enabled:true,entries:[]});
  saveAcConfig(cfg);
  inp.value = '';
  renderAcDicts();
}

function removeAcDict(idx) {
  const cfg = loadAcConfig();
  cfg.dictGroups.splice(idx,1);
  saveAcConfig(cfg);
  renderAcDicts();
}

function resetAcDicts() {
  const cfg = loadAcConfig();
  cfg.dictGroups = JSON.parse(JSON.stringify(DEFAULT_DICTS));
  saveAcConfig(cfg);
  renderAcDicts();
}

function initAcSettings() {
  const cfg = loadAcConfig();
  const el = document.getElementById('acLatex'); if(el) el.checked = cfg.latex;
  const es = document.getElementById('acSnippets'); if(es) es.checked = cfg.snippets;
  const ed = document.getElementById('acDicts'); if(ed) ed.checked = cfg.dicts;
  renderAcDicts();
}

// ─── 数据同步 ──────────────────────────────────────────────

let autoSyncTimer = null;

async function syncData() {
  const btn = document.getElementById('btnSyncNow');
  btn.disabled = true;
  btn.textContent = '同步中...';

  try {
    const res = await client.syncFull(state.tasks, state.bookmarks, state.projects || []);
    if (res.code === 0 && res.data) {
      const d = res.data;

      // 用 server_data 更新本地 state
      if (d.tasks && d.tasks.server_data) {
        state.tasks = d.tasks.server_data;
        renderKanban();
      }
      if (d.bookmarks && d.bookmarks.server_data) {
        state.bookmarks = d.bookmarks.server_data;
        state.bookmarkCategories = [...new Set(state.bookmarks.map(b => b.category || b.group || '其他'))];
        renderBookmarkCategories();
        renderBookmarks();
      }
      if (d.projects && d.projects.server_data) {
        state.projects = d.projects.server_data;
      }

      // 显示同步结果
      const resultRow = document.getElementById('syncResultRow');
      const resultDetail = document.getElementById('syncResultDetail');
      resultRow.style.display = 'block';

      const taskPull = d.tasks ? d.tasks.pull : [];
      const taskPush = d.tasks ? d.tasks.pushed : 0;
      const taskConflicts = d.tasks ? d.tasks.conflicts : [];
      const bmPull = d.bookmarks ? d.bookmarks.pull : [];
      const bmPush = d.bookmarks ? d.bookmarks.pushed : 0;
      const bmConflicts = d.bookmarks ? d.bookmarks.conflicts : [];
      const projPull = d.projects ? d.projects.pull : [];
      const projPush = d.projects ? d.projects.pushed : 0;

      let html = '';
      html += `<div>📋 任务：拉取 ${taskPull.length} 条，推送 ${taskPush} 条` +
        (taskConflicts.length > 0 ? `，<span style="color:var(--red)">冲突 ${taskConflicts.length} 条</span>` : '') + '</div>';
      html += `<div>🔖 书签：拉取 ${bmPull.length} 条，推送 ${bmPush} 条` +
        (bmConflicts.length > 0 ? `，<span style="color:var(--red)">冲突 ${bmConflicts.length} 条</span>` : '') + '</div>';
      html += `<div>📁 项目：拉取 ${projPull.length} 条，推送 ${projPush} 条</div>`;
      resultDetail.innerHTML = html;

      // 更新上次同步时间
      const now = new Date();
      document.getElementById('syncLastTime').textContent =
        now.getHours().toString().padStart(2, '0') + ':' +
        now.getMinutes().toString().padStart(2, '0') + ':' +
        now.getSeconds().toString().padStart(2, '0');
      localStorage.setItem('ts2_last_sync_time', document.getElementById('syncLastTime').textContent);

      showToast('同步完成');
    } else {
      showToast('同步失败: ' + (res.msg || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('同步失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '立即同步';
  }
}

function toggleAutoSync(enabled) {
  if (enabled) {
    if (autoSyncTimer) clearInterval(autoSyncTimer);
    autoSyncTimer = setInterval(syncData, 5 * 60 * 1000);
    localStorage.setItem('ts2_auto_sync', '1');
    showToast('已开启自动同步');
  } else {
    if (autoSyncTimer) { clearInterval(autoSyncTimer); autoSyncTimer = null; }
    localStorage.setItem('ts2_auto_sync', '0');
    showToast('已关闭自动同步');
  }
}

// 恢复自动同步状态
function initAutoSync() {
  const saved = localStorage.getItem('ts2_auto_sync');
  const savedTime = localStorage.getItem('ts2_last_sync_time');
  if (savedTime) {
    document.getElementById('syncLastTime').textContent = savedTime;
  }
  if (saved === '1') {
    document.getElementById('autoSyncToggle').checked = true;
    autoSyncTimer = setInterval(syncData, 5 * 60 * 1000);
  }
}

initAutoSync();

// ─── IndexedDB 本地文件系统 ──────────────────────────────────────────

var LOCAL_FS_DB = 'ts2_local_fs';
var LOCAL_FS_VER = 1;
var LOCAL_FS_FILES = 'files';
var LOCAL_FS_DIRS = 'dirs';

function localFSOpenDB() {
  return new Promise(function(resolve, reject) {
    var req = indexedDB.open(LOCAL_FS_DB, LOCAL_FS_VER);
    req.onupgradeneeded = function() {
      var db = req.result;
      if (!db.objectStoreNames.contains(LOCAL_FS_FILES)) {
        var store = db.createObjectStore(LOCAL_FS_FILES, { keyPath: 'path' });
        store.createIndex('dir', 'dir', { unique: false });
      }
      if (!db.objectStoreNames.contains(LOCAL_FS_DIRS)) {
        var store2 = db.createObjectStore(LOCAL_FS_DIRS, { keyPath: 'path' });
        store2.createIndex('parent', 'parent', { unique: false });
      }
    };
    req.onsuccess = function() { resolve(req.result); };
    req.onerror = function() { reject(req.error); };
  });
}

function localReadFile(path) {
  return localFSOpenDB().then(function(db) {
    return new Promise(function(resolve, reject) {
      var tx = db.transaction(LOCAL_FS_FILES, 'readonly');
      var req = tx.objectStore(LOCAL_FS_FILES).get(path);
      req.onsuccess = function() { db.close(); resolve(req.result || null); };
      req.onerror = function() { db.close(); reject(req.error); };
    });
  }).catch(function() { return null; });
}

function localWriteFile(path, content) {
  var now = Date.now();
  var name = path.split('/').pop() || path;
  var dir = path.substring(0, path.lastIndexOf('/')) || '/';
  var file = { path: path, name: name, content: content, dir: dir, updatedAt: now, createdAt: now, size: new Blob([content]).size };
  return localReadFile(path).then(function(existing) {
    if (existing) file.createdAt = existing.createdAt;
    return localFSOpenDB();
  }).then(function(db) {
    return new Promise(function(resolve, reject) {
      var tx = db.transaction(LOCAL_FS_FILES, 'readwrite');
      tx.objectStore(LOCAL_FS_FILES).put(file);
      tx.oncomplete = function() { db.close(); resolve(); };
      tx.onerror = function() { reject(tx.error); };
    });
  });
}

function localDeleteFile(path) {
  return localFSOpenDB().then(function(db) {
    return new Promise(function(resolve, reject) {
      var tx = db.transaction(LOCAL_FS_FILES, 'readwrite');
      tx.objectStore(LOCAL_FS_FILES).delete(path);
      tx.oncomplete = function() { db.close(); resolve(); };
      tx.onerror = function() { reject(tx.error); };
    });
  });
}

function localMkdir(path) {
  var now = Date.now();
  var name = path.split('/').pop() || path;
  var parent = path.substring(0, path.lastIndexOf('/')) || '/';
  var dir = { path: path, name: name, parent: parent, updatedAt: now, createdAt: now };
  return localFSOpenDB().then(function(db) {
    return new Promise(function(resolve, reject) {
      var tx = db.transaction(LOCAL_FS_DIRS, 'readwrite');
      tx.objectStore(LOCAL_FS_DIRS).put(dir);
      tx.oncomplete = function() { db.close(); resolve(); };
      tx.onerror = function() { reject(tx.error); };
    });
  });
}

function localReadDir(dirPath) {
  dirPath = dirPath || '/';
  return localFSOpenDB().then(function(db) {
    var entries = [];
    // 获取子目录
    var dirsPromise = new Promise(function(resolve, reject) {
      var tx = db.transaction(LOCAL_FS_DIRS, 'readonly');
      var idx = tx.objectStore(LOCAL_FS_DIRS).index('parent');
      var req = idx.getAll(dirPath);
      req.onsuccess = function() { resolve(req.result || []); };
      req.onerror = function() { reject(req.error); };
    });
    // 获取文件
    var filesPromise = new Promise(function(resolve, reject) {
      var tx = db.transaction(LOCAL_FS_FILES, 'readonly');
      var idx = tx.objectStore(LOCAL_FS_FILES).index('dir');
      var req = idx.getAll(dirPath);
      req.onsuccess = function() { resolve(req.result || []); };
      req.onerror = function() { reject(req.error); };
    });
    return Promise.all([dirsPromise, filesPromise]).then(function(results) {
      db.close();
      (results[0] || []).forEach(function(d) {
        entries.push({ name: d.name, type: 'dir', path: d.path, updatedAt: d.updatedAt });
      });
      (results[1] || []).forEach(function(f) {
        entries.push({ name: f.name, type: 'file', path: f.path, updatedAt: f.updatedAt, size: f.size });
      });
      entries.sort(function(a, b) {
        if (a.type !== b.type) return a.type === 'dir' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      return entries;
    });
  }).catch(function() { return []; });
}

function localFSStats() {
  return localFSOpenDB().then(function(db) {
    var filesP = new Promise(function(resolve, reject) {
      var tx = db.transaction(LOCAL_FS_FILES, 'readonly');
      var req = tx.objectStore(LOCAL_FS_FILES).getAll();
      req.onsuccess = function() { resolve(req.result || []); };
      req.onerror = function() { reject(req.error); };
    });
    var dirsP = new Promise(function(resolve, reject) {
      var tx = db.transaction(LOCAL_FS_DIRS, 'readonly');
      var req = tx.objectStore(LOCAL_FS_DIRS).getAll();
      req.onsuccess = function() { resolve(req.result || []); };
      req.onerror = function() { reject(req.error); };
    });
    return Promise.all([filesP, dirsP]).then(function(results) {
      db.close();
      var files = results[0] || [];
      var dirs = results[1] || [];
      return { files: files.length, dirs: dirs.length, totalSize: files.reduce(function(s, f) { return s + (f.size || 0); }, 0) };
    });
  }).catch(function() { return { files: 0, dirs: 0, totalSize: 0 }; });
}

// 导入目录从服务端到本地
async function localImportDirFromServer(serverDir, localDir) {
  var count = 0;
  try {
    var res = await client.readDir(serverDir);
    var entries = (res.code === 0 && res.data) ? res.data : [];
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      var serverPath = serverDir ? serverDir + '/' + entry.name : entry.name;
      var localPath = localDir ? localDir + '/' + entry.name : entry.name;
      if (entry.is_dir) {
        await localMkdir(localPath);
        count += await localImportDirFromServer(serverPath, localPath);
      } else {
        try {
          var fileRes = await client.getFile(serverPath);
          var content = fileRes.data && fileRes.data.content ? fileRes.data.content : (typeof fileRes.data === 'string' ? fileRes.data : '');
          if (content) {
            await localWriteFile(localPath, content);
            count++;
          }
        } catch (e) { /* skip failed files */ }
      }
    }
  } catch (e) { /* ignore */ }
  return count;
}

// 导出本地目录到服务端
async function localExportDirToServer(localDir, serverDir) {
  var count = 0;
  var entries = await localReadDir(localDir);
  for (var i = 0; i < entries.length; i++) {
    var entry = entries[i];
    var serverPath = serverDir ? serverDir + '/' + entry.name : entry.name;
    var localPath = localDir ? localDir + '/' + entry.name : entry.name;
    if (entry.type === 'dir') {
      count += await localExportDirToServer(localPath, serverPath);
    } else {
      try {
        var file = await localReadFile(localPath);
        if (file && file.content) {
          await client.putFile(serverPath, file.content);
          count++;
        }
      } catch (e) { /* skip failed files */ }
    }
  }
  return count;
}

// ─── 分页笔记 ──────────────────────────────────────────

var slidesState = {
  id: '',
  title: '',
  slides: [],
  currentIndex: 0,
  vditor: null,
  vditorReady: false,
  isSwitching: false,
  saveTimer: null,
  notebookList: [],  // 服务器上的笔记列表
  nbSource: 'server',  // 'server' | 'local'
  localNbList: [],  // 本地笔记列表
  localNbDirs: [],  // 本地笔记子目录列表
  localNbDir: '',  // 本地笔记当前所在子目录
  noteExt: '.md',  // 当前打开的服务端笔记的原始扩展名
  importExportBusy: false,
  autoSaveTimer: null,  // 周期性自动保存定时器
  nbCurrentDir: '',  // 服务端笔记当前所在子目录（相对 Notes）
  searchQuery: '',  // 笔记搜索过滤关键词
};

var SLIDES_STORAGE_KEY = 'ts2_slides_notebook';
var SLIDES_LOCAL_DIR = 'notebooks';  // 本地笔记存储目录
// 所有 markdown 变体扩展名
var SLIDES_MD_EXTS = ['.md', '.markdown', '.rmd', '.rmarkdown', '.mdx'];
var SLIDES_MD_EXT_PAT = SLIDES_MD_EXTS.map(function(e) { return e.replace('.', '\\.'); }).join('|');
// 文件 I/O 用：含常见大小写变体
var SLIDES_MD_EXTS_IO = SLIDES_MD_EXTS.concat(['.Rmd', '.RMD', '.RMARKDOWN', '.Mdx', '.MDX', '.MD', '.MARKDOWN']);

function slidesIsMdFile(name) {
  var lower = name.toLowerCase();
  return SLIDES_MD_EXTS.some(function(e) { return lower.endsWith(e); });
}
function slidesStripMdExt(name) {
  return name.replace(new RegExp('\\.(' + SLIDES_MD_EXT_PAT + ')$', 'i'), '');
}
function slidesIsLocalNbFile(name) {
  return name.toLowerCase().endsWith('.json') || slidesIsMdFile(name);
}

var AUTO_SAVE_INTERVAL = 30000;  // 30秒周期性自动保存

function slidesGenId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 6);
}

function slidesCreateSlide(title, markdown) {
  var now = Date.now();
  return { id: slidesGenId(), title: title || '', markdown: markdown || '', createdAt: now, updatedAt: now };
}

function slidesLoadLocal() {
  try {
    var raw = localStorage.getItem(SLIDES_STORAGE_KEY);
    if (raw) {
      var nb = JSON.parse(raw);
      if (nb.slides && nb.slides.length > 0) return nb;
    }
  } catch (e) {}
  return {
    id: slidesGenId(),
    title: '我的笔记',
    slides: [slidesCreateSlide('欢迎', '# 欢迎\n\n这是第一页笔记。\n\n按 **→** 翻到下一页，按 **←** 返回上一页。\n\n点击 **+ 新页** 插入空白页。')],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}

function slidesSaveLocal() {
  var nb = {
    id: slidesState.id,
    title: slidesState.title,
    slides: slidesState.slides.map(function(s) { return Object.assign({}, s); }),
    createdAt: 0,
    updatedAt: Date.now(),
  };
  var existing = localStorage.getItem(SLIDES_STORAGE_KEY);
  if (existing) { try { nb.createdAt = JSON.parse(existing).createdAt; } catch (e) {} }
  if (!nb.createdAt) nb.createdAt = Date.now();
  localStorage.setItem(SLIDES_STORAGE_KEY, JSON.stringify(nb));
  slidesShowStatus('已保存');
}

function slidesDebounceSave() {
  if (slidesState.saveTimer) clearTimeout(slidesState.saveTimer);
  slidesState.saveTimer = setTimeout(slidesSaveLocal, 500);
}

// 静默防抖保存（仅保存到 localStorage，无用户反馈）
function slidesDebounceSaveSilent() {
  if (slidesState.saveTimer) clearTimeout(slidesState.saveTimer);
  slidesState.saveTimer = setTimeout(function() {
    slidesSaveCurrent();
    try {
      var nb = {
        id: slidesState.id,
        title: slidesState.title,
        slides: slidesState.slides.map(function(s) { return Object.assign({}, s); }),
        createdAt: 0,
        updatedAt: Date.now(),
      };
      var existing = localStorage.getItem(SLIDES_STORAGE_KEY);
      if (existing) { try { nb.createdAt = JSON.parse(existing).createdAt; } catch (e) {} }
      if (!nb.createdAt) nb.createdAt = Date.now();
      localStorage.setItem(SLIDES_STORAGE_KEY, JSON.stringify(nb));
    } catch (e) {}
  }, 500);
}

// 周期性自动保存
function slidesStartAutoSave() {
  slidesStopAutoSave();
  slidesState.autoSaveTimer = setInterval(function() {
    if (slidesState.slides.length === 0) return;
    slidesSaveCurrent();
    if (slidesState.nbSource === 'local') {
      slidesSaveToLocalSilent();
    } else {
      slidesSaveToServerSilent();
    }
  }, AUTO_SAVE_INTERVAL);
}

function slidesStopAutoSave() {
  if (slidesState.autoSaveTimer) {
    clearInterval(slidesState.autoSaveTimer);
    slidesState.autoSaveTimer = null;
  }
}

// 静默保存到服务器（无用户反馈）
async function slidesSaveToServerSilent() {
  slidesSaveCurrent();
  try {
    var nb = {
      id: slidesState.id,
      title: slidesState.title,
      slides: slidesState.slides.map(function(s) { return Object.assign({}, s); }),
      createdAt: 0,
      updatedAt: Date.now(),
    };
    var existing = localStorage.getItem(SLIDES_STORAGE_KEY);
    if (existing) { try { nb.createdAt = JSON.parse(existing).createdAt; } catch (e) {} }
    var serverUrl = localStorage.getItem('ts2_server_url') || '';
    if (!serverUrl) return;
    var base = serverUrl.replace(/\/+$/, '');
    var resp = await fetch(base + '/api/notebook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nb),
    });
    if (!resp.ok) throw new Error('save failed');
  } catch (e) { /* silent fail */ }
}

function slidesShowStatus(msg) {
  var el = document.getElementById('slidesSaveStatus');
  if (el) { el.textContent = msg; setTimeout(function() { el.textContent = ''; }, 2000); }
}

function slidesGetTitle(slide, idx) {
  if (slide.title) return slide.title;
  var firstLine = (slide.markdown || '').split('\n')[0] || '';
  var heading = firstLine.replace(/^#+\s*/, '').trim();
  return heading || ('第 ' + (idx + 1) + ' 页');
}

function slidesRenderOutline() {
  var container = document.getElementById('slidesOutline');
  if (!container) return;
  var html = '';
  for (var i = 0; i < slidesState.slides.length; i++) {
    var s = slidesState.slides[i];
    var active = i === slidesState.currentIndex ? ' style="background:rgba(59,130,246,0.1);color:var(--accent)"' : '';
    html += '<div class="outline-item" onclick="slidesGoTo(' + i + ')"' + active + ' style="display:flex;align-items:center;gap:6px;padding:6px 8px;cursor:pointer;font-size:11px;border-bottom:1px solid var(--border);border-radius:4px;margin-bottom:2px">';
    html += '<span style="color:var(--fg-muted);min-width:16px;text-align:right;font-size:10px">' + (i + 1) + '</span>';
    html += '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + slidesGetTitle(s, i) + '</span>';
    if (slidesState.slides.length > 1) {
      html += '<button onclick="event.stopPropagation();slidesDelete(' + i + ')" style="background:none;border:none;color:var(--fg-muted);font-size:10px;cursor:pointer;padding:2px 4px;opacity:0.5" onmouseover="this.style.color=\'#ef4444\'" onmouseout="this.style.color=\'var(--fg-muted)\'">✕</button>';
    }
    html += '</div>';
  }
  container.innerHTML = html;
}

function slidesUpdateNav() {
  var cur = document.getElementById('slidesCurrentNum');
  var tot = document.getElementById('slidesTotalNum');
  var prev = document.getElementById('slidesPrevBtn');
  var next = document.getElementById('slidesNextBtn');
  if (cur) cur.textContent = slidesState.currentIndex + 1;
  if (tot) tot.textContent = slidesState.slides.length;
  if (prev) prev.disabled = slidesState.currentIndex === 0;
  if (next) next.disabled = slidesState.currentIndex === slidesState.slides.length - 1;
}

function slidesSaveCurrent() {
  if (slidesState.vditor && slidesState.slides[slidesState.currentIndex] && !slidesState.isSwitching) {
    try {
      var val = slidesState.vditor.getValue();
      if (val !== undefined) {
        slidesState.slides[slidesState.currentIndex].markdown = val;
        slidesState.slides[slidesState.currentIndex].updatedAt = Date.now();
      }
    } catch (e) {}
  }
  // 同步页面标题
  var titleInput = document.getElementById('slidesPageTitle');
  if (titleInput && slidesState.slides[slidesState.currentIndex]) {
    slidesState.slides[slidesState.currentIndex].title = titleInput.value;
  }
}

function slidesLoadPage(index) {
  if (!slidesState.vditor) return;
  slidesState.isSwitching = true;
  try {
    var md = slidesState.slides[index] ? slidesState.slides[index].markdown : '';
    slidesState.vditor.setValue(md || '');
  } finally {
    setTimeout(function() { slidesState.isSwitching = false; }, 100);
  }
  // 更新页面标题
  var titleInput = document.getElementById('slidesPageTitle');
  if (titleInput) {
    titleInput.value = slidesState.slides[index] ? slidesState.slides[index].title : '';
  }
}

/* 刷新主 Slides Vditor 内容（切换标签页或从分屏回到主编辑器时调用） */
function slidesUpdateSlideEditor() {
  if (slidesState.vditor && slidesState.slides[slidesState.currentIndex]) {
    slidesLoadPage(slidesState.currentIndex);
  }
}

function slidesGoTo(index) {
  if (index === slidesState.currentIndex) return;
  slidesSaveCurrent();
  if (slidesState.nbSource === 'local') slidesSaveToLocalSilent();
  else slidesSaveToServerSilent();
  slidesState.currentIndex = index;
  slidesLoadPage(index);
  slidesRenderOutline();
  slidesUpdateNav();
  slidesStartAutoSave();  // 重启自动保存定时器
  // 刷新分屏中 slides 标签页的 Vditor 内容
  _slidesUpdatePaneVditor();
}

function slidesPrev() {
  if (slidesState.currentIndex > 0) slidesGoTo(slidesState.currentIndex - 1);
}

function slidesNext() {
  if (slidesState.currentIndex < slidesState.slides.length - 1) {
    slidesGoTo(slidesState.currentIndex + 1);
  } else {
    slidesAddPage(slidesState.currentIndex + 1);
  }
}

function slidesAddPage(insertAt) {
  slidesSaveCurrent();
  var newSlide = slidesCreateSlide('', '');
  slidesState.slides.splice(insertAt, 0, newSlide);
  slidesState.currentIndex = insertAt;
  slidesLoadPage(slidesState.currentIndex);
  slidesRenderOutline();
  slidesUpdateNav();
  slidesSaveLocal();
  _slidesUpdatePaneVditor();
}

function slidesAddPageBefore() {
  slidesAddPage(slidesState.currentIndex);
}

function slidesAddPageAfter() {
  slidesAddPage(slidesState.currentIndex + 1);
}

function slidesDelete(index) {
  if (slidesState.slides.length <= 1) return;
  slidesState.slides.splice(index, 1);
  if (slidesState.currentIndex >= slidesState.slides.length) {
    slidesState.currentIndex = slidesState.slides.length - 1;
  } else if (slidesState.currentIndex > index) {
    slidesState.currentIndex--;
  } else if (slidesState.currentIndex === index) {
    slidesState.currentIndex = Math.min(index, slidesState.slides.length - 1);
  }
  slidesLoadPage(slidesState.currentIndex);
  slidesRenderOutline();
  slidesUpdateNav();
  slidesSaveLocal();
  _slidesUpdatePaneVditor();
}

/* 刷新分屏中 slides 标签页的 Vditor 内容 */
function _slidesUpdatePaneVditor() {
  var allPanes = document.querySelectorAll('#splitContainer .pane');
  for (var pi = 0; pi < allPanes.length; pi++) {
    var pid = allPanes[pi].getAttribute('data-pane-id');
    if (!pid || pid === '0') continue;
    if ((state['paneTabs_' + pid] || []).find(function(t) { return t._isSlides; })) {
      var v = state['paneVditor_' + pid];
      if (v && state['paneVditorReady_' + pid]) {
        v.setValue((slidesState.slides[slidesState.currentIndex] || {}).markdown || '');
      }
    }
  }
}

var _slidesNotebookCache = {};
var _slidesActivePath = null;
var _slidesEditorInPane = null;  // paneId 或 null（在主区）

/* 将 slidesEditorView 移入分屏 pane */
function _moveSlidesEditorToPane(paneId) {
  var wrapper = document.getElementById('editorWrapper-' + paneId);
  var view = document.getElementById('slidesEditorView');
  if (!wrapper || !view) return;
  if (view.parentNode === wrapper) return;
  // 移除 pane 空状态占位提示（避免积累挤压）
  var toRemove = [];
  for (var ci = 0; ci < wrapper.children.length; ci++) {
    var c = wrapper.children[ci];
    if (c.tagName === 'DIV' && !c.id && c.textContent.indexOf('在文件树中点击') >= 0) {
      toRemove.push(c);
    }
  }
  toRemove.forEach(function(el) { el.remove(); });
  var pv = document.getElementById('paneVditor-' + paneId);
  if (pv) pv.style.display = 'none';
  var pp = document.getElementById('panePdfContainer-' + paneId);
  if (pp) pp.style.display = 'none';
  wrapper.appendChild(view);
  view.style.display = 'flex';
  _slidesEditorInPane = paneId;
}

/* 将 slidesEditorView 从分屏移回主编辑器容器 */
function _moveSlidesEditorToMain() {
  var editorWrapper = document.getElementById('editorWrapper');
  var view = document.getElementById('slidesEditorView');
  if (!editorWrapper || !view) return;
  if (view.parentNode === editorWrapper) { _slidesEditorInPane = null; return; }
  var fromPane = _slidesEditorInPane;
  editorWrapper.appendChild(view);
  view.style.display = 'flex';
  _slidesEditorInPane = null;
  if (fromPane) {
    var vditorEl = document.getElementById('paneVditor-' + fromPane);
    if (vditorEl) vditorEl.style.display = 'none';
    var pdfEl = document.getElementById('panePdfContainer-' + fromPane);
    if (pdfEl) pdfEl.style.display = 'none';
    var wrapper = document.getElementById('editorWrapper-' + fromPane);
    if (wrapper) {
      var hintEl = wrapper.querySelector('.pane-empty-hint');
      if (hintEl) hintEl.style.display = 'flex';
    }
  }
}

/* 将当前 slidesState 保存到缓存 */
function _slidesSaveToCache(path) {
  _slidesNotebookCache[path] = {
    title: slidesState.title,
    slides: slidesState.slides.map(function(s) { return JSON.parse(JSON.stringify(s)); }),
    currentIndex: slidesState.currentIndex,
    nbSource: slidesState.nbSource,
    nbCurrentDir: slidesState.nbCurrentDir,
    localNbDir: slidesState.localNbDir,
    noteExt: slidesState.noteExt,
    id: slidesState.id,
  };
}

/* 从缓存恢复 slidesState */
function _slidesLoadFromCache(path) {
  var data = _slidesNotebookCache[path];
  if (!data) return false;
  slidesState.title = data.title;
  slidesState.slides = data.slides;
  slidesState.currentIndex = data.currentIndex;
  slidesState.nbSource = data.nbSource;
  slidesState.nbCurrentDir = data.nbCurrentDir;
  slidesState.localNbDir = data.localNbDir;
  slidesState.noteExt = data.noteExt;
  slidesState.id = data.id;
  return true;
}

/* 切离当前笔记：保存 Vditor 到 slidesState 再写入缓存和磁盘 */
function _slidesSaveCurrentAndCache() {
  if (!_slidesActivePath) return;
  slidesSaveCurrent();
  // 持久化到磁盘
  if (slidesState.nbSource === 'local') slidesSaveToLocalSilent();
  else slidesSaveToServerSilent();
  _slidesSaveToCache(_slidesActivePath);
}

/* 切换到指定笔记标签页：缓存当前，加载目标 */
function _slidesSwitchToNotebook(path) {
  if (_slidesActivePath === path) return;
  if (_slidesActivePath) _slidesSaveCurrentAndCache();
  if (_slidesNotebookCache[path]) {
    _slidesLoadFromCache(path);
    _slidesActivePath = path;
    // 刷新 UI
    var titleInput = document.getElementById('slidesNotebookTitle');
    if (titleInput) titleInput.value = slidesState.title;
    slidesLoadPage(slidesState.currentIndex);
    slidesRenderOutline();
    slidesUpdateNav();
    slidesShowCurrentNB(slidesState.slides.length > 0);
  } else {
    _slidesActivePath = path;
  }
}

async function slidesNewNotebook() {
  var name = await modalPrompt('新笔记标题：');
  if (!name || !name.trim()) return;
  slidesSaveCurrent();
  slidesState.id = slidesGenId();
  slidesState.title = name.trim();
  slidesState.slides = [slidesCreateSlide('', '# ' + name.trim() + '\n\n')];
  slidesState.currentIndex = 0;
  var titleInput = document.getElementById('slidesNotebookTitle');
  if (titleInput) titleInput.value = slidesState.title;
  slidesLoadPage(0);
  slidesRenderOutline();
  slidesUpdateNav();
  slidesSaveLocal();
  slidesShowCurrentNB(true);
  if (slidesState.nbSource === 'local') {
    slidesSaveToLocal();
  } else {
    slidesSaveToServer();
  }
  // 为新笔记创建独立标签页
  var nbPath = _getCurrentSlidesPath() || '__notes__';
  var ts = Date.now();
  // 如果路径冲突，加时间戳
  if (state.openTabs.find(function(t) { return t.path === nbPath; }) || _slidesNotebookCache[nbPath]) {
    nbPath = nbPath.replace(/(\.\w+)?$/, '_' + ts + '$1');
  }
  slidesState.slides[0].markdown = '# ' + name.trim() + '\n\n';
  _slidesSaveToCache(nbPath);
  _ensureSlidesTab(nbPath, slidesState.title);
}

// ─── 源切换 ──────────────────────────────────────────

function slidesSwitchSource(source) {
  slidesSaveCurrent();
  if (slidesState.nbSource === 'local') slidesSaveToLocalSilent();
  else slidesSaveToServerSilent();
  slidesState.nbSource = source;
  slidesState.nbCurrentDir = '';
  slidesState.localNbDir = '';
  slidesState.localNbDirs = [];
  slidesState.noteExt = '.md';
  var btnServer = document.getElementById('slidesSrcServer');
  var btnLocal = document.getElementById('slidesSrcLocal');
  var localActions = document.getElementById('slidesLocalActions');
  var btnSave = document.getElementById('slidesBtnSave');
  var btnLoad = document.getElementById('slidesBtnLoad');
  if (btnServer) { btnServer.style.background = source === 'server' ? 'var(--accent)' : 'transparent'; btnServer.style.color = source === 'server' ? '#fff' : 'var(--fg-muted)'; }
  if (btnLocal) { btnLocal.style.background = source === 'local' ? 'var(--accent)' : 'transparent'; btnLocal.style.color = source === 'local' ? '#fff' : 'var(--fg-muted)'; }
  if (localActions) localActions.style.display = source === 'local' ? 'block' : 'none';
  if (btnSave) btnSave.innerHTML = source === 'local' ? '💾 保存本地' : '💾 保存';
  if (btnLoad) btnLoad.style.display = source === 'server' ? '' : 'none';
  // 刷新笔记列表
  slidesLoadNotebookList();
  if (source === 'local') slidesRefreshLocalStats();
}

function slidesDoSave() {
  if (slidesState.nbSource === 'local') {
    slidesSaveToLocal();
  } else {
    slidesSaveToServer();
  }
}

function slidesDoLoad() {
  if (slidesState.nbSource === 'local') {
    // 本地模式不需要单独加载按钮
    slidesShowStatus('本地模式自动保存');
  } else {
    slidesLoadFromServer();
  }
}

// ─── 本地笔记操作 ──────────────────────────────────────────

async function slidesSaveToLocal() {
  slidesSaveCurrent();
  try {
    var nb = {
      id: slidesState.id,
      title: slidesState.title,
      slides: slidesState.slides.map(function(s) { return Object.assign({}, s); }),
      createdAt: 0,
      updatedAt: Date.now(),
    };
    var existing = localStorage.getItem(SLIDES_STORAGE_KEY);
    if (existing) { try { nb.createdAt = JSON.parse(existing).createdAt; } catch (e) {} }
    var safeName = (slidesState.title || 'note').replace(/[\\/:*?"<>|]/g, '_');
    var dirPrefix = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
    await localMkdir(dirPrefix);
    await localWriteFile(dirPrefix + '/' + safeName + '.json', JSON.stringify(nb, null, 2));
    slidesShowStatus('已保存到本地');
    slidesLoadLocalNbList();
    slidesRefreshLocalStats();
  } catch (e) {
    slidesShowStatus('本地保存失败');
  }
}

// 静默保存到本地（无用户反馈）
async function slidesSaveToLocalSilent() {
  slidesSaveCurrent();
  try {
    var nb = {
      id: slidesState.id,
      title: slidesState.title,
      slides: slidesState.slides.map(function(s) { return Object.assign({}, s); }),
      createdAt: 0,
      updatedAt: Date.now(),
    };
    var existing = localStorage.getItem(SLIDES_STORAGE_KEY);
    if (existing) { try { nb.createdAt = JSON.parse(existing).createdAt; } catch (e) {} }
    var safeName = (slidesState.title || 'note').replace(/[\\/:*?"<>|]/g, '_');
    var dirPrefix = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
    await localMkdir(dirPrefix);
    await localWriteFile(dirPrefix + '/' + safeName + '.json', JSON.stringify(nb, null, 2));
  } catch (e) { /* silent fail */ }
}

async function slidesLoadLocalNbList() {
  try {
    await localMkdir(SLIDES_LOCAL_DIR);
    var subDir = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
    var entries = await localReadDir(subDir);
    slidesState.localNbDirs = entries
      .filter(function(e) { return e.type === 'dir'; })
      .map(function(e) { return { name: e.name, relPath: slidesState.localNbDir ? slidesState.localNbDir + '/' + e.name : e.name }; });
    // 文件去重：同名基只显示一次，优先 .json，否则取第一个 MD 变体
    var seen = {};
    for (var ei = 0; ei < entries.length; ei++) {
      var e = entries[ei];
      if (e.type !== 'file' || !slidesIsLocalNbFile(e.name)) continue;
      var base = e.name.replace(/\.\w+$/, '');
      var isJson = e.name.endsWith('.json');
      if (!seen[base] || (isJson && !seen[base].name.endsWith('.json'))) {
        seen[base] = { name: e.name, path: e.path, updatedAt: e.updatedAt };
      }
    }
    var list = [];
    for (var key in seen) {
      if (seen.hasOwnProperty(key)) list.push(seen[key]);
    }
    slidesState.localNbList = list;
  } catch (e) { /* ignore */ }
}

function slidesLocalNavigateTo(dirPath) {
  slidesState.localNbDir = dirPath;
  slidesLoadNotebookList();
}

async function slidesRefreshLocalStats() {
  try {
    var stats = await localFSStats();
    var el = document.getElementById('slidesLocalStats');
    if (el && stats.files > 0) el.textContent = stats.files + '文件';
    else if (el) el.textContent = '';
  } catch (e) { /* ignore */ }
}

async function slidesOpenLocalNotebook(name) {
  try {
    slidesSaveCurrent();
    if (slidesState.nbSource === 'local') slidesSaveToLocalSilent();
    else slidesSaveToServerSilent();
    var dirPrefix = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
    var baseName = name.replace(/\.\w+$/, '');
    var filePrefix = dirPrefix + '/' + baseName;
    // 先尝试 JSON 格式
    var jsonFile = await localReadFile(filePrefix + '.json');
    if (jsonFile && jsonFile.content) {
      var nb = JSON.parse(jsonFile.content);
      if (nb.slides && Array.isArray(nb.slides)) {
        slidesSaveCurrent();
        slidesState.title = nb.title || baseName;
        slidesState.id = nb.id || slidesGenId();
        slidesState.slides = nb.slides.map(function(s) {
          return { id: s.id || slidesGenId(), title: s.title || '', markdown: s.markdown || '', createdAt: s.createdAt || Date.now(), updatedAt: s.updatedAt || Date.now() };
        });
        slidesState.currentIndex = 0;
        var titleInput = document.getElementById('slidesNotebookTitle');
        if (titleInput) titleInput.value = slidesState.title;
        slidesLoadPage(0);
        slidesRenderOutline();
        slidesUpdateNav();
        slidesSaveLocal();
        slidesStartAutoSave();
        slidesShowCurrentNB(true);
        slidesShowStatus('已打开本地笔记');
        _slidesSaveToCache('_local:' + name);
        _ensureSlidesTab('_local:' + name, slidesState.title);
        return;
      }
    }
    // 回退到所有 MD 变体
    for (var ei = 0; ei < SLIDES_MD_EXTS_IO.length; ei++) {
      var ext = SLIDES_MD_EXTS_IO[ei];
      var mdFile = await localReadFile(filePrefix + ext);
      if (mdFile && mdFile.content) {
        slidesSaveCurrent();
        var parsed = slidesImportMDParse(mdFile.content);
        slidesState.title = parsed.title || baseName;
        slidesState.id = slidesGenId();
        slidesState.slides = parsed.slides;
        slidesState.currentIndex = 0;
        var titleInput2 = document.getElementById('slidesNotebookTitle');
        if (titleInput2) titleInput2.value = slidesState.title;
        slidesLoadPage(0);
        slidesRenderOutline();
        slidesUpdateNav();
        slidesSaveLocal();
        slidesStartAutoSave();
        slidesShowCurrentNB(true);
        slidesShowStatus('已打开本地笔记');
        _slidesSaveToCache('_local:' + name);
        _ensureSlidesTab('_local:' + name, slidesState.title);
        return;
      }
    }
    slidesShowStatus('笔记为空');
  } catch (e) {
    slidesShowStatus('打开失败');
  }
}

async function slidesDeleteLocalNotebook(name) {
  if (!await modalConfirm('确定删除本地笔记 "' + name + '"？')) return;
  try {
    var dirPrefix = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
    var baseName = name.replace(/\.\w+$/, '');
    try { await localDeleteFile(dirPrefix + '/' + baseName + '.json'); } catch (e) {}
    for (var ei = 0; ei < SLIDES_MD_EXTS_IO.length; ei++) {
      try { await localDeleteFile(dirPrefix + '/' + baseName + SLIDES_MD_EXTS_IO[ei]); } catch (e) {}
    }
    slidesShowStatus('已删除');
    slidesLoadNotebookList();
    slidesRefreshLocalStats();
  } catch (e) {
    slidesShowStatus('删除失败');
  }
}

async function slidesImportFromServer() {
  if (slidesState.importExportBusy) return;
  slidesState.importExportBusy = true;
  var msgEl = document.getElementById('slidesImportExportMsg');
  if (msgEl) msgEl.textContent = '正在从服务端导入...';
  try {
    var serverDir = slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir : 'Notes';
    var localDir = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
    await localMkdir(localDir);
    var count = await localImportDirFromServer(serverDir, localDir);
    if (msgEl) msgEl.textContent = '导入完成：' + count + ' 个文件';
    slidesLoadNotebookList();
    slidesRefreshLocalStats();
  } catch (e) {
    if (msgEl) msgEl.textContent = '导入失败';
  } finally {
    slidesState.importExportBusy = false;
    setTimeout(function() { if (msgEl) msgEl.textContent = ''; }, 3000);
  }
}

async function slidesExportToServer() {
  if (slidesState.importExportBusy) return;
  slidesState.importExportBusy = true;
  var msgEl = document.getElementById('slidesImportExportMsg');
  if (msgEl) msgEl.textContent = '正在导出到服务端...';
  try {
    var localDir = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
    var serverDir = slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir : 'Notes';
    var count = await localExportDirToServer(localDir, serverDir);
    if (msgEl) msgEl.textContent = '导出完成：' + count + ' 个文件';
    if (slidesState.nbSource === 'server') slidesLoadNotebookList();
  } catch (e) {
    if (msgEl) msgEl.textContent = '导出失败';
  } finally {
    slidesState.importExportBusy = false;
    setTimeout(function() { if (msgEl) msgEl.textContent = ''; }, 3000);
  }
}

// 单个笔记从服务端导入到本地
async function slidesImportSingleFromServer(fileName) {
  try {
    var path = slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir + '/' + fileName : 'Notes/' + fileName;
    var res = await client.getFile(path);
    var content = res.data && res.data.content ? res.data.content : (typeof res.data === 'string' ? res.data : '');
    if (content) {
      var safeName = slidesStripMdExt(fileName).replace(/[\\/:*?"<>|]/g, '_');
      var originalExt = '.' + (fileName.split('.').pop() || 'md');
      var dirPrefix = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
      await localMkdir(dirPrefix);
      var parsed = slidesImportMDParse(content);
      var nb = {
        id: slidesGenId(),
        title: parsed.title || safeName,
        slides: parsed.slides,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };
      await localWriteFile(dirPrefix + '/' + safeName + '.json', JSON.stringify(nb, null, 2));
      await localWriteFile(dirPrefix + '/' + safeName + originalExt, content);
      slidesShowStatus('已导入: ' + safeName);
      await slidesLoadLocalNbList();
    }
  } catch (e) {
    slidesShowStatus('导入失败');
  }
}

// 单个笔记从本地导出到服务端
async function slidesExportSingleToServer(name) {
  try {
    var dirPrefix = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
    var baseName = name.replace(/\.\w+$/, '');
    var content = '';
    var foundExt = '.md';
    var jsonFile = await localReadFile(dirPrefix + '/' + baseName + '.json');
    if (jsonFile && jsonFile.content) {
      try {
        var nb = JSON.parse(jsonFile.content);
        var parts2 = [];
        if (nb.title) parts2.push('# ' + nb.title + '\n');
        for (var si = 0; si < (nb.slides || []).length; si++) {
          var s = nb.slides[si];
          if (s.title) parts2.push('## ' + s.title + '\n');
          parts2.push(s.markdown || '');
          if (si < nb.slides.length - 1) parts2.push('\n---\n');
        }
        content = parts2.join('\n');
      } catch (e) {}
    }
    if (!content) {
      for (var ei = 0; ei < SLIDES_MD_EXTS_IO.length; ei++) {
        var mdFile = await localReadFile(dirPrefix + '/' + baseName + SLIDES_MD_EXTS_IO[ei]);
        if (mdFile && mdFile.content) { content = mdFile.content; foundExt = SLIDES_MD_EXTS_IO[ei]; break; }
      }
    }
    if (content) {
      var serverDir = slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir : 'Notes';
      await client.putFile(serverDir + '/' + baseName + foundExt, content);
      slidesShowStatus('已导出: ' + baseName);
    }
  } catch (e) {
    slidesShowStatus('导出失败');
  }
}

// 服务器保存/加载（notes 目录 MD 文件）
function slidesNotePath() {
  var name = (slidesState.title || 'note').replace(/[\\/:*?"<>|]/g, '_');
  var dir = slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir : 'Notes';
  return dir + '/' + name + (slidesState.noteExt || '.md');
}

function slidesNotebookToMD() {
  var parts = [];
  if (slidesState.title) parts.push('# ' + slidesState.title + '\n');
  for (var i = 0; i < slidesState.slides.length; i++) {
    var slide = slidesState.slides[i];
    if (slide.title) parts.push('## ' + slide.title + '\n');
    parts.push(slide.markdown || '');
    if (i < slidesState.slides.length - 1) parts.push('\n---\n');
  }
  return parts.join('\n');
}

async function slidesSaveToServer() {
  slidesSaveCurrent();
  try {
    // 保存 MD 到 notes 目录
    var md = slidesNotebookToMD();
    await client.putFile(slidesNotePath(), md);
    // 同时保存 JSON 元数据
    var data = {
      id: slidesState.id,
      title: slidesState.title,
      slides: slidesState.slides.map(function(s) { return Object.assign({}, s); }),
      createdAt: 0,
      updatedAt: Date.now(),
    };
    var existing = localStorage.getItem(SLIDES_STORAGE_KEY);
    if (existing) { try { data.createdAt = JSON.parse(existing).createdAt; } catch (e) {} }
    await client.api('/api/notebooks/' + slidesState.id, data);
    slidesShowStatus('已保存');
  } catch (e) {
    slidesShowStatus('保存失败');
  }
}

async function slidesLoadFromServer() {
  try {
    // 先尝试从 notes 目录读取 MD
    var res = await client.getFile(slidesNotePath());
    var content = res.data && res.data.content ? res.data.content : (typeof res.data === 'string' ? res.data : '');
    if (content && content.trim()) {
      var parsed = slidesImportMDParse(content);
      slidesSaveCurrent();
      if (parsed.title) slidesState.title = parsed.title;
      slidesState.slides = parsed.slides;
      slidesState.currentIndex = 0;
      var titleInput = document.getElementById('slidesNotebookTitle');
      if (titleInput) titleInput.value = slidesState.title;
      slidesLoadPage(0);
      slidesRenderOutline();
      slidesUpdateNav();
      slidesSaveLocal();
      slidesShowStatus('已加载');
    } else {
      // 回退到 JSON API
      var nbRes = await fetch(API_BASE + '/api/notebooks/' + slidesState.id);
      var nbJson = await nbRes.json();
      var nbData = nbJson.data;
      if (nbData && nbData.slides) {
        slidesSaveCurrent();
        slidesState.title = nbData.title || '';
        if (nbData.id) slidesState.id = nbData.id;
        slidesState.slides = (nbData.slides || []).map(function(s) {
          return { id: s.id || slidesGenId(), title: s.title || '', markdown: s.markdown || '', createdAt: s.createdAt || Date.now(), updatedAt: s.updatedAt || Date.now() };
        });
        slidesState.currentIndex = 0;
        var titleInput2 = document.getElementById('slidesNotebookTitle');
        if (titleInput2) titleInput2.value = slidesState.title;
        slidesLoadPage(0);
        slidesRenderOutline();
        slidesUpdateNav();
        slidesSaveLocal();
        slidesShowStatus('已加载');
      } else {
        slidesShowStatus('无数据');
      }
    }
  } catch (e) {
    slidesShowStatus('加载失败');
  }
}

// 解析 MD 为 slides（不修改 state，只返回数据）
function slidesImportMDParse(content) {
  var sections = content.split(/\n---\n/);
  var imported = [];
  var nbTitle = '';
  for (var i = 0; i < sections.length; i++) {
    var md = sections[i].trim();
    if (!md) continue;
    var title = '';
    var firstLine = md.split('\n')[0];
    if (i === 0 && firstLine.startsWith('# ')) {
      nbTitle = firstLine.replace(/^# +/, '').trim();
      md = md.split('\n').slice(1).join('\n').trim();
      if (!md) continue;
    }
    if (firstLine.startsWith('## ')) {
      title = firstLine.replace(/^## +/, '').trim();
      md = md.split('\n').slice(1).join('\n').trim();
    }
    imported.push(slidesCreateSlide(title, md));
  }
  if (imported.length === 0) imported.push(slidesCreateSlide('', content));
  return { title: nbTitle, slides: imported };
}

// 导出 Markdown
function slidesExportMD() {
  slidesSaveCurrent();
  var parts = [];
  if (slidesState.title) parts.push('# ' + slidesState.title + '\n');
  for (var i = 0; i < slidesState.slides.length; i++) {
    var slide = slidesState.slides[i];
    if (slide.title) parts.push('## ' + slide.title + '\n');
    parts.push(slide.markdown || '');
    if (i < slidesState.slides.length - 1) parts.push('\n---\n');
  }
  var md = parts.join('\n');
  var blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = (slidesState.title || 'note') + '.md';
  a.click();
  URL.revokeObjectURL(url);
  slidesShowStatus('已导出 MD');
}

// 导出 JSON
function slidesExportJSON() {
  slidesSaveCurrent();
  slidesSaveLocal();
  var existing = localStorage.getItem(SLIDES_STORAGE_KEY);
  var nb = existing ? JSON.parse(existing) : {};
  var blob = new Blob([JSON.stringify(nb, null, 2)], { type: 'application/json' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = (slidesState.title || 'note') + '.json';
  a.click();
  URL.revokeObjectURL(url);
  slidesShowStatus('已导出 JSON');
}

// 导入
function slidesImportFile(e) {
  var file = e.target.files[0];
  if (!file) return;
  var reader = new FileReader();
  reader.onload = async function() {
    var content = reader.result;
    var ext = file.name.split('.').pop().toLowerCase();
    if (ext === 'md' || ext === 'markdown' || ext === 'rmd' || ext === 'rmarkdown' || ext === 'mdx' || ext === 'txt') {
      slidesImportMD(content, file.name.replace(/\.\w+$/, ''));
    } else {
      try {
        var nb = JSON.parse(content);
        if (!nb.slides || !Array.isArray(nb.slides)) { await modalAlert('无效的笔记文件'); return; }
        slidesSaveCurrent();
        slidesState.title = nb.title || '导入的笔记';
        if (nb.id) slidesState.id = nb.id;
        slidesState.slides = nb.slides.map(function(s) {
          return { id: s.id || slidesGenId(), title: s.title || '', markdown: s.markdown || '', createdAt: s.createdAt || Date.now(), updatedAt: s.updatedAt || Date.now() };
        });
        slidesState.currentIndex = 0;
        var titleInput = document.getElementById('slidesNotebookTitle');
        if (titleInput) titleInput.value = slidesState.title;
        slidesLoadPage(0);
        slidesRenderOutline();
        slidesUpdateNav();
        slidesSaveLocal();
        slidesShowCurrentNB(true);
        slidesShowStatus('已导入 JSON');
        // 多笔记标签页
        var nbPath = _getCurrentSlidesPath() || '__imported__';
        if (state.openTabs.find(function(t) { return t.path === nbPath; }) || _slidesNotebookCache[nbPath]) {
          nbPath = nbPath.replace(/(\.\w+)?$/, '_' + Date.now() + '$1');
        }
        _slidesSaveToCache(nbPath);
        _ensureSlidesTab(nbPath, slidesState.title);
      } catch (err) { await modalAlert('文件解析失败'); }
    }
  };
  reader.readAsText(file);
  e.target.value = '';
}

function slidesImportMD(content, filename) {
  slidesSaveCurrent();
  var sections = content.split(/\n---\n/);
  var imported = [];
  for (var i = 0; i < sections.length; i++) {
    var md = sections[i].trim();
    if (!md) continue;
    var title = '';
    var firstLine = md.split('\n')[0];
    if (firstLine.startsWith('# ')) {
      title = firstLine.replace(/^# +/, '').trim();
      md = md.split('\n').slice(1).join('\n').trim();
    } else if (firstLine.startsWith('## ')) {
      title = firstLine.replace(/^## +/, '').trim();
      md = md.split('\n').slice(1).join('\n').trim();
    }
    imported.push(slidesCreateSlide(title, md));
  }
  if (imported.length === 0) imported.push(slidesCreateSlide('', content));
  slidesState.title = filename || '导入的笔记';
  slidesState.slides = imported;
  slidesState.currentIndex = 0;
  var titleInput = document.getElementById('slidesNotebookTitle');
  if (titleInput) titleInput.value = slidesState.title;
  slidesLoadPage(0);
  slidesRenderOutline();
  slidesUpdateNav();
  slidesSaveLocal();
  slidesShowCurrentNB(true);
  slidesShowStatus('已导入 ' + imported.length + ' 页');
  // 多笔记标签页
  var nbPath = _getCurrentSlidesPath() || '__imported__';
  if (state.openTabs.find(function(t) { return t.path === nbPath; }) || _slidesNotebookCache[nbPath]) {
    nbPath = nbPath.replace(/(\.\w+)?$/, '_' + Date.now() + '$1');
  }
  _slidesSaveToCache(nbPath);
  _ensureSlidesTab(nbPath, slidesState.title);
}

// 初始化面板
function initSlidesPanel() {
  _kmindRenderRecent();
  var editorView = document.getElementById('slidesEditorView');
  if (!editorView) return;

  // 保存当前文件编辑器内容
  if (typeof saveCurrentFile === 'function') saveCurrentFile();

  // 隐藏文件编辑器相关区域
  var welcomeScreen = document.getElementById('welcomeScreen');
  var vditorEl = document.getElementById('vditor');
  var plainEditor = document.getElementById('plainEditor');
  var pdfViewer = document.getElementById('pdfViewer');
  if (welcomeScreen) welcomeScreen.style.display = 'none';
  if (vditorEl) vditorEl.style.display = 'none';
  if (plainEditor) plainEditor.style.display = 'none';
  if (pdfViewer) pdfViewer.style.display = 'none';
  editorView.style.display = 'flex';
  // 如果 slides 编辑器当前在分屏中，移回主容器
  _moveSlidesEditorToMain();

  // 加载数据
  if (!slidesState.slides.length) {
    var nb = slidesLoadLocal();
    slidesState.id = nb.id || slidesGenId();
    slidesState.title = nb.title;
    slidesState.slides = nb.slides;
    slidesState.currentIndex = 0;
  }

  var titleInput = document.getElementById('slidesNotebookTitle');
  if (titleInput) {
    titleInput.value = slidesState.title;
    titleInput.onchange = function() {
      slidesState.title = titleInput.value;
      slidesSaveLocal();
    };
  }

  var pageTitleInput = document.getElementById('slidesPageTitle');
  if (pageTitleInput) {
    pageTitleInput.onchange = function() {
      if (slidesState.slides[slidesState.currentIndex]) {
        slidesState.slides[slidesState.currentIndex].title = pageTitleInput.value;
        slidesSaveLocal();
        slidesRenderOutline();
      }
    };
  }

  // 显示/隐藏当前笔记区域
  slidesShowCurrentNB(slidesState.slides.length > 0);

  // 初始化 Vditor（只初始化一次）
  if (!slidesState.vditorReady) {
    slidesState.vditorReady = true;
    setTimeout(function() {
      if (typeof Vditor !== 'undefined') {
        var acCfg = loadAcConfig();
        var currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        slidesState.vditor = new Vditor('slidesVditor', {
          height: '100%',
          mode: 'wysiwyg',
          theme: currentTheme === 'light' ? 'classic' : 'dark',
          placeholder: '开始书写...',
          cache: { enable: false },
          cdn: '/static/vditor',
          _lutePath: '/static/vditor/dist/js/lute/lute.min.js',
          input: function(val) {
            if (!slidesState.isSwitching && slidesState.slides[slidesState.currentIndex]) {
              slidesState.slides[slidesState.currentIndex].markdown = val;
              slidesState.slides[slidesState.currentIndex].updatedAt = Date.now();
              slidesDebounceSaveSilent();  // 静默保存到 localStorage，不弹提示
            }
          },
          toolbar: ['headings','bold','italic','strike','|','quote','inline-code','code','|','list','ordered-list','check','|','link','table','|','undo','redo','|','edit-mode','preview','fullscreen'],
          toolbarConfig: { pin: true },
          counter: { enable: true },
          preview: { mode: 'editor' },
          tab: '\t',
          hint: {
            delay: 200,
            parse: false,
            extend: buildHintExtends(acCfg),
          },
        });
        setTimeout(function() {
          // 等待 Vditor 完全就绪后再加载内容
          var checkReady = function() {
            if (slidesState.vditor && slidesState.vditor.vditor && slidesState.slides[slidesState.currentIndex]) {
              try {
                slidesState.vditor.setValue(slidesState.slides[slidesState.currentIndex].markdown || '');
              } catch(e) {
                setTimeout(checkReady, 200);
              }
            } else {
              setTimeout(checkReady, 200);
            }
          };
          checkReady();
        }, 500);
      }
    }, 200);
  } else {
    // 已初始化，重新加载当前页
    setTimeout(function() {
      if (slidesState.vditor && slidesState.slides[slidesState.currentIndex]) {
        slidesState.vditor.setValue(slidesState.slides[slidesState.currentIndex].markdown || '');
      }
    }, 100);
  }

  slidesRenderOutline();
  slidesUpdateNav();
  slidesLoadNotebookList();
  slidesStartAutoSave();  // 启动周期性自动保存

  // 注册笔记标签到编辑器 tab 栏（如果还没有则创建）
  _ensureSlidesTabForCurrent();
}

function slidesShowCurrentNB(show) {
  var el = document.getElementById('slidesCurrentNB');
  if (el) el.style.display = show ? 'block' : 'none';
}

function slidesHideCurrentNB() {
  slidesStopAutoSave();
  slidesSaveCurrent();
  if (slidesState.nbSource === 'local') slidesSaveToLocalSilent();
  else slidesSaveToServerSilent();
  var el = document.getElementById('slidesCurrentNB');
  if (el) el.style.display = 'none';
  var titleInput = document.getElementById('slidesNotebookTitle');
  if (titleInput) titleInput.value = '';
  // 关闭对应的编辑器 tab（当前激活的笔记标签页）
  var pathToClose = _slidesActivePath;
  var slidesTab = pathToClose ? state.openTabs.find(t => t.path === pathToClose) : state.openTabs.find(t => t._isSlides);
  if (slidesTab) closeTab(slidesTab.path);
  // 如果还有其它笔记标签页，切换到最后一个
  var remaining = state.openTabs.filter(t => t._isSlides);
  if (remaining.length > 0) {
    switchToTab(remaining[remaining.length - 1].path);
  }
}

function toggleMindmapFullscreen() {
  var container = document.getElementById('mindmapContainer');
  if (!container) return;
  if (!document.fullscreenElement) {
    container.requestFullscreen().catch(function(e) {});
  } else {
    document.exitFullscreen();
  }
}

function slidesToggleOutline() {
  var wrap = document.getElementById('slidesOutlineWrap');
  var toggle = document.getElementById('slidesOutlineToggle');
  if (!wrap) return;
  var isOpen = wrap.style.display !== 'none';
  wrap.style.display = isOpen ? 'none' : 'block';
  if (toggle) toggle.textContent = isOpen ? '▶' : '▼';
}

function toggleSlidesNbList() {
  var wrap = document.getElementById('slidesNbListWrap');
  var icon = document.getElementById('slidesNbToggleIcon');
  if (!wrap) return;
  var open = wrap.style.display !== 'none';
  wrap.style.display = open ? 'none' : 'block';
  if (icon) icon.style.transform = open ? '' : 'rotate(180deg)';
}

// 进入子目录
function slidesNbNavigateTo(dirPath) {
  slidesState.nbCurrentDir = dirPath;
  slidesLoadNotebookList();
}

function slidesEscapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;');
}

// 搜索过滤
function slidesSearchNotes() {
  var el = document.getElementById('slidesSearchInput');
  slidesState.searchQuery = el ? el.value.trim().toLowerCase() : '';
  slidesLoadNotebookList();
}

// 递归搜索整个 Notes 目录树，返回匹配的文件列表（含相对路径）
async function slidesSearchTree(dirPath, prefix, query, results) {
  results = results || [];
  try {
    var res = await client.readDir(dirPath);
    if (res.code === 0 && res.data) {
      var dirs = [];
      var files = [];
      res.data.forEach(function(f) {
        if (f.is_dir) {
          dirs.push(f);
        } else if (slidesIsMdFile(f.name)) {
          files.push(f);
        }
      });
      for (var f of files) {
        var relPath = prefix ? prefix + '/' + f.name : f.name;
        var displayName = slidesStripMdExt(f.name).toLowerCase();
        if (displayName.indexOf(query) !== -1) {
          results.push({ name: f.name, relPath: relPath });
        }
      }
      for (var d of dirs) {
        var subPrefix = prefix ? prefix + '/' + d.name : d.name;
        await slidesSearchTree(d.path, subPrefix, query, results);
      }
    }
  } catch (e) { /* ignore */ }
  return results;
}

// 加载笔记列表（根据源切换）
async function slidesLoadNotebookList() {
  var container = document.getElementById('slidesNotebookList');
  if (!container) return;

  if (slidesState.nbSource === 'local') {
    await slidesLoadLocalNbList();
    var html = '';
    // 本地面包屑
    html += '<div style="display:flex;align-items:center;gap:2px;padding:4px 6px;font-size:11px;color:var(--fg-muted);border-bottom:1px solid var(--border);margin-bottom:4px;flex-wrap:wrap">';
    if (slidesState.localNbDir) {
      html += '<span class="nb-crumb" onclick="slidesLocalNavigateTo(\'\')" style="cursor:pointer;color:var(--accent)">notebooks</span>';
      var dirParts = slidesState.localNbDir.split('/');
      for (var di = 0; di < dirParts.length; di++) {
        html += '<span style="margin:0 2px">/</span>';
        var subPath = dirParts.slice(0, di + 1).join('/');
        html += '<span class="nb-crumb" onclick="slidesLocalNavigateTo(\'' + subPath + '\')" style="cursor:pointer;color:var(--accent)">' + dirParts[di] + '</span>';
      }
    } else {
      html += '<span>notebooks</span>';
    }
    html += '</div>';
    // 子目录
    slidesState.localNbDirs.forEach(function(d) {
      html += '<div style="display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:6px;cursor:pointer;margin-bottom:2px;color:var(--fg-muted)" onclick="slidesLocalNavigateTo(\'' + d.relPath.replace(/'/g, "\\'") + '\')" onmouseover="this.style.background=\'var(--bg-tertiary)\'" onmouseout="this.style.background=\'transparent\'">';
      html += '<span style="font-size:12px">📁</span>';
      html += '<span style="flex:1;font-size:11px">' + d.name + '</span>';
      html += '</div>';
    });
    if (slidesState.localNbDir) {
      // 返回上级
      html += '<div style="display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:6px;cursor:pointer;margin-bottom:2px;color:var(--fg-muted)" onclick="slidesLocalNavigateTo(\'' + (slidesState.localNbDir.split('/').slice(0, -1).join('/')) + '\')" onmouseover="this.style.background=\'var(--bg-tertiary)\'" onmouseout="this.style.background=\'transparent\'">';
      html += '<span style="font-size:12px">📁</span>';
      html += '<span style="flex:1;font-size:11px">..</span>';
      html += '</div>';
    }
    // 笔记文件
    if (slidesState.localNbList.length === 0 && slidesState.localNbDirs.length === 0) {
      html += '<div style="font-size:11px;color:var(--fg-muted);padding:4px">暂无笔记</div>';
    }
    slidesState.localNbList.forEach(function(nb) {
      var displayName = slidesStripMdExt(nb.name);
      var isActive = displayName === slidesState.title;
      onclick = 'slidesOpenLocalNotebook(\'' + nb.name.replace(/'/g, "\\'") + '\')';
      html += '<div style="display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:6px;cursor:pointer;margin-bottom:2px;' +
        (isActive ? 'background:rgba(59,130,246,0.12);color:var(--accent)' : 'color:var(--fg-muted)') +
        '" onclick="' + onclick + '" onmouseover="if(!this.style.background.includes(\'0.12\'))this.style.background=\'var(--bg-tertiary)\'" onmouseout="if(!this.style.background.includes(\'0.12\'))this.style.background=\'transparent\'">';
      html += '<span style="font-size:12px">📝</span>';
      html += '<span style="flex:1;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + displayName + '</span>';
      html += '<button onclick="event.stopPropagation();slidesExportSingleToServer(\'' + nb.name.replace(/'/g, "\\'") + '\')" title="导出到服务端" style="background:none;border:none;color:var(--accent);font-size:10px;cursor:pointer;padding:2px 4px;border-radius:3px;opacity:0.5" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.5">↑</button>';
      html += '<button onclick="event.stopPropagation();slidesDeleteLocalNotebook(\'' + nb.name.replace(/'/g, "\\'") + '\')" title="删除" style="background:none;border:none;color:var(--fg-muted);font-size:10px;cursor:pointer;padding:2px 4px;border-radius:3px;opacity:0.5" onmouseover="this.style.opacity=1;this.style.color=\'#ef4444\'" onmouseout="this.style.opacity=0.5;this.style.color=\'var(--fg-muted)\'">✕</button>';
      html += '</div>';
    });
    container.innerHTML = html;
    return;
  }

  // 服务端模式 - 搜索时递归整个目录树，否则逐层浏览
  container.innerHTML = '<div style="font-size:11px;color:var(--fg-muted);padding:4px">加载中...</div>';
  try {
    // 有搜索关键词：递归搜索整个 Notes 目录树
    if (slidesState.searchQuery) {
      var searchResults = await slidesSearchTree('Notes', '', slidesState.searchQuery);
      var html = '';
      // 搜索结果面包屑
      html += '<div style="display:flex;align-items:center;gap:4px;padding:4px 6px;font-size:11px;color:var(--fg-muted);border-bottom:1px solid var(--border);margin-bottom:4px;flex-wrap:wrap">';
      html += '<span>🔍 搜索: "' + slidesEscapeHtml(slidesState.searchQuery) + '" (' + searchResults.length + ' 结果)</span>';
      html += '<span style="cursor:pointer;color:var(--accent);padding:2px 4px;border-radius:4px" onclick="slidesClearSearch()" onmouseover="this.style.background=\'var(--bg-tertiary)\'" onmouseout="this.style.background=\'transparent\'">✕ 清除</span>';
      html += '</div>';
      if (searchResults.length === 0) {
        html += '<div style="font-size:11px;color:var(--fg-muted);padding:4px">未找到匹配笔记</div>';
        container.innerHTML = html;
        return;
      }
      var currentTitle = (slidesState.title || '').replace(/[\/\\:*?"<>|]/g, '_');
      var itemStyle = 'display:flex;align-items:center;gap:4px;padding:5px 8px;border-radius:6px;cursor:pointer;margin-bottom:1px;font-size:11px';
      for (var r of searchResults) {
        var displayName = slidesStripMdExt(r.name);
        var isActive = displayName === currentTitle;
        var bgStyle = isActive ? 'background:rgba(59,130,246,0.12);color:var(--accent)' : 'color:var(--fg-muted)';
        var escRel = slidesEscapeHtml(r.relPath);
        var escDisplay = slidesEscapeHtml(displayName);
        var escDir = slidesEscapeHtml(r.relPath.indexOf('/') !== -1 ? r.relPath.substring(0, r.relPath.lastIndexOf('/')) : '');
        var onclick = 'slidesOpenNotebookByPath(\'' + escRel.replace(/'/g, "\\'") + '\')';
        var line = '<div style="' + itemStyle + ';' + bgStyle + '" onclick="' + onclick + '" onmouseover="if(!this.style.background.includes(\'0.12\'))this.style.background=\'var(--bg-tertiary)\'" onmouseout="if(!this.style.background.includes(\'0.12\'))this.style.background=\'transparent\'">';
        line += '<span style="font-size:12px">📝</span>';
        line += '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escDisplay;
        if (r.relPath.indexOf('/') !== -1) {
          line += ' <span style="font-size:9px;opacity:0.5">(' + escDir + ')</span>';
        }
        line += '</span>';
        line += '<button onclick="event.stopPropagation();slidesImportSingleFromServerByPath(\'' + escRel.replace(/'/g, "\\'") + '\')" title="导入到本地" style="background:none;border:none;color:var(--accent);font-size:10px;cursor:pointer;padding:2px 4px;border-radius:3px;opacity:0.5" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.5">↓</button>';
        line += '<button onclick="event.stopPropagation();slidesDeleteNotebookByPath(\'' + escRel.replace(/'/g, "\\'") + '\')" title="删除" style="background:none;border:none;color:var(--fg-muted);font-size:10px;cursor:pointer;padding:2px 4px;border-radius:3px;opacity:0.5" onmouseover="this.style.opacity=1;this.style.color=\'#ef4444\'" onmouseout="this.style.opacity=0.5;this.style.color=\'var(--fg-muted)\'">✕</button>';
        line += '</div>';
        html += line;
      }
      container.innerHTML = html;
      return;
    }

    // 无搜索：逐层浏览
    var dirPath = slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir : 'Notes';
    var res = await client.readDir(dirPath);
    var dirs = [];
    var files = [];
    if (res.code === 0 && res.data) {
      res.data.forEach(function(f) {
        if (f.is_dir) {
          dirs.push(f);
        } else if (slidesIsMdFile(f.name)) {
          files.push(f);
        }
      });
      dirs.sort(function(a, b) { return a.name.localeCompare(b.name); });
      files.sort(function(a, b) { return a.name.localeCompare(b.name); });
    }

    var html = '';
    // 面包屑导航
    html += '<div style="display:flex;align-items:center;gap:2px;padding:4px 6px;font-size:11px;color:var(--fg-muted);border-bottom:1px solid var(--border);margin-bottom:4px;flex-wrap:wrap">';
    html += '<span style="cursor:pointer;padding:2px 4px;border-radius:4px" onclick="slidesNbNavigateTo(\'\')" onmouseover="this.style.background=\'var(--bg-tertiary)\'" onmouseout="this.style.background=\'transparent\'">📁 Notes</span>';
    if (slidesState.nbCurrentDir) {
      var parts = slidesState.nbCurrentDir.split('/');
      var acc = '';
      for (var i = 0; i < parts.length; i++) {
        acc = acc ? acc + '/' + parts[i] : parts[i];
        html += '<span style="opacity:0.5">/</span>';
        var escPart = slidesEscapeHtml(parts[i]);
        var escAcc = slidesEscapeHtml(acc);
        if (i < parts.length - 1) {
          html += '<span style="cursor:pointer;padding:2px 4px;border-radius:4px" onclick="slidesNbNavigateTo(\'' + escAcc.replace(/'/g, "\\'") + '\')" onmouseover="this.style.background=\'var(--bg-tertiary)\'" onmouseout="this.style.background=\'transparent\'">' + escPart + '</span>';
        } else {
          html += '<span style="padding:2px 4px;color:var(--fg)">' + escPart + '</span>';
        }
      }
    }
    html += '</div>';

    if (dirs.length === 0 && files.length === 0) {
      html += '<div style="font-size:11px;color:var(--fg-muted);padding:4px">暂无笔记，点击"新建"创建</div>';
      container.innerHTML = html;
      return;
    }

    var currentTitle = (slidesState.title || '').replace(/[\/\\:*?"<>|]/g, '_');
    var itemStyle = 'display:flex;align-items:center;gap:4px;padding:5px 8px;border-radius:6px;cursor:pointer;margin-bottom:1px;font-size:11px';

    // 先显示子文件夹（点击进入下一层）
    for (var d of dirs) {
      var newDir = slidesState.nbCurrentDir ? slidesState.nbCurrentDir + '/' + d.name : d.name;
      var escDirName = slidesEscapeHtml(d.name);
      var escNewDir = slidesEscapeHtml(newDir);
      var line = '<div style="' + itemStyle + ';color:var(--fg-muted)" onclick="slidesNbNavigateTo(\'' + escNewDir.replace(/'/g, "\\'") + '\')" onmouseover="this.style.background=\'var(--bg-tertiary)\'" onmouseout="this.style.background=\'transparent\'">';
      line += '<span style="font-size:13px">📁</span>';
      line += '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escDirName + '</span>';
      line += '</div>';
      html += line;
    }

    // 再显示 .md 文件（点击打开）
    for (var f of files) {
      var fileName = f.name;
      var displayName = slidesStripMdExt(fileName);
      var isActive = displayName === currentTitle;
      var bgStyle = isActive ? 'background:rgba(59,130,246,0.12);color:var(--accent)' : 'color:var(--fg-muted)';
      var escFileName = slidesEscapeHtml(fileName);
      var onclick = 'slidesOpenNotebook(\'' + escFileName.replace(/'/g, "\\'") + '\')';
      var line = '<div style="' + itemStyle + ';' + bgStyle + '" onclick="' + onclick + '" onmouseover="if(!this.style.background.includes(\'0.12\'))this.style.background=\'var(--bg-tertiary)\'" onmouseout="if(!this.style.background.includes(\'0.12\'))this.style.background=\'transparent\'">';
      line += '<span style="font-size:12px">📝</span>';
      line += '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + slidesEscapeHtml(displayName) + '</span>';
      line += '<button onclick="event.stopPropagation();slidesImportSingleFromServer(\'' + escFileName.replace(/'/g, "\\'") + '\')" title="导入到本地" style="background:none;border:none;color:var(--accent);font-size:10px;cursor:pointer;padding:2px 4px;border-radius:3px;opacity:0.5" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.5">↓</button>';
      line += '<button onclick="event.stopPropagation();slidesDeleteNotebook(\'' + escFileName.replace(/'/g, "\\'") + '\')" title="删除" style="background:none;border:none;color:var(--fg-muted);font-size:10px;cursor:pointer;padding:2px 4px;border-radius:3px;opacity:0.5" onmouseover="this.style.opacity=1;this.style.color=\'#ef4444\'" onmouseout="this.style.opacity=0.5;this.style.color=\'var(--fg-muted)\'">✕</button>';
      line += '</div>';
      html += line;
    }
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div style="font-size:11px;color:var(--fg-muted);padding:4px">加载失败</div>';
  }
}

// 清除搜索
function slidesClearSearch() {
  slidesState.searchQuery = '';
  var el = document.getElementById('slidesSearchInput');
  if (el) el.value = '';
  slidesLoadNotebookList();
}

// 通过完整相对路径打开笔记（搜索结果用）
async function slidesOpenNotebookByPath(relPath) {
  try {
    slidesSaveCurrent();
    if (slidesState.nbSource === 'local') slidesSaveToLocalSilent();
    else slidesSaveToServerSilent();
    var path = 'Notes/' + relPath;
    var res = await client.getFile(path);
    var content = res.data && res.data.content ? res.data.content : (typeof res.data === 'string' ? res.data : '');
    if (content && content.trim()) {
      var parsed = slidesImportMDParse(content);
      var fileName = relPath.split('/').pop();
      slidesState.title = parsed.title || slidesStripMdExt(fileName);
      slidesState.noteExt = '.' + (fileName.split('.').pop() || 'md');
      slidesState.id = slidesGenId();
      slidesState.slides = parsed.slides;
      slidesState.currentIndex = 0;
      var titleInput = document.getElementById('slidesNotebookTitle');
      if (titleInput) titleInput.value = slidesState.title;
      slidesLoadPage(0);
      slidesRenderOutline();
      slidesUpdateNav();
      slidesSaveLocal();
      slidesStartAutoSave();
      slidesShowCurrentNB(true);
      slidesShowStatus('已打开: ' + slidesState.title);
      _slidesSaveToCache(path);
      _ensureSlidesTab(path, slidesState.title);
      slidesLoadNotebookList();
    }
  } catch (e) {
    slidesShowStatus('打开失败');
  }
}

// 通过完整相对路径导入笔记（搜索结果用）
async function slidesImportSingleFromServerByPath(relPath) {
  try {
    var path = 'Notes/' + relPath;
    var res = await client.getFile(path);
    var content = res.data && res.data.content ? res.data.content : (typeof res.data === 'string' ? res.data : '');
    if (content && typeof content === 'string') {
      var fileName = relPath.split('/').pop();
      var safeName = slidesStripMdExt(fileName).replace(/[\\/:*?"<>|]/g, '_');
      var originalExt = '.' + (fileName.split('.').pop() || 'md');
      var dirPrefix = slidesState.localNbDir ? SLIDES_LOCAL_DIR + '/' + slidesState.localNbDir : SLIDES_LOCAL_DIR;
      await localMkdir(dirPrefix);
      await localWriteFile(dirPrefix + '/' + safeName + originalExt, content);
      slidesShowStatus('已导入: ' + safeName);
      setTimeout(function() { slidesShowStatus(''); }, 2000);
    }
  } catch (e) {
    slidesShowStatus('导入失败');
  }
}

// 通过完整相对路径删除笔记（搜索结果用）
async function slidesDeleteNotebookByPath(relPath) {
  if (!await modalConfirm('确定删除笔记 "' + relPath + '"？此操作不可恢复。')) return;
  try {
    var path = 'Notes/' + relPath;
    var res = await client.api('/api/file/removeFile', { path: path });
    if (res.code === 0) {
      slidesShowStatus('已删除');
      slidesLoadNotebookList();
    } else {
      slidesShowStatus('删除失败');
    }
  } catch (e) {
    slidesShowStatus('删除失败');
  }
}

// 打开指定笔记
function _ensureSlidesTab(filePath, title) {
  var existing = state.openTabs.find(t => t._isSlides && t.path === filePath);
  if (existing) { switchToTab(filePath); return; }
  // 允许同时打开多个笔记标签页
  if (!_slidesNotebookCache[filePath]) {
    _slidesSaveToCache(filePath);
  }
  state.openTabs.push({ path: filePath, name: title || filePath.split('/').pop(), modified: false, _isSlides: true });
  _saveSession();
  addTab(filePath, title || filePath.split('/').pop());
  switchToTab(filePath);
}

/* 根据 slidesState 当前笔记路径创建/切换到笔记标签页 */
function _ensureSlidesTabForCurrent() {
  // 检查分屏中是否有 slides 标签页，若有则移回主编辑器
  var allPanes = document.querySelectorAll('#splitContainer .pane');
  for (var pi = 0; pi < allPanes.length; pi++) {
    var pid = allPanes[pi].getAttribute('data-pane-id');
    if (!pid || pid === '0') continue;
    var paneTab = (state['paneTabs_' + pid] || []).find(function(t) { return t._isSlides; });
    if (paneTab) {
      _moveTabBetweenPanes(paneTab.path, pid, '0');
      return;
    }
  }
  // 如果已有笔记标签页，直接切换到第一个
  var anySlidesTab = state.openTabs.find(function(t) { return t._isSlides; });
  if (anySlidesTab) {
    switchToTab(anySlidesTab.path);
    return;
  }
  // 无标签页，新建
  var nbPath = _getCurrentSlidesPath() || '__notes__';
  var nbTitle = slidesState.title || '笔记';
  _slidesSaveToCache(nbPath);
  _ensureSlidesTab(nbPath, nbTitle);
}

/* 获取当前笔记的路径标识 */
function _getCurrentSlidesPath() {
  if (slidesState.nbSource === 'local' && slidesState.title) {
    var safeName = slidesState.title.replace(/[\\/:*?"<>|]/g, '_');
    return '_local:' + safeName + '.json';
  }
  if (slidesState.nbSource === 'server' && slidesState.title && slidesState.title !== '笔记') {
    var safeName = slidesState.title.replace(/[\\/:*?"<>|]/g, '_');
    return slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir + '/' + safeName + '.md' : 'Notes/' + safeName + '.md';
  }
  return '__notes__';
}

async function slidesOpenNotebook(fileName) {
  try {
    slidesSaveCurrent();
    if (slidesState.nbSource === 'local') slidesSaveToLocalSilent();
    else slidesSaveToServerSilent();
    var path = slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir + '/' + fileName : 'Notes/' + fileName;
    var res = await client.getFile(path);
    var content = res.data && res.data.content ? res.data.content : (typeof res.data === 'string' ? res.data : '');
    if (content && content.trim()) {
      var parsed = slidesImportMDParse(content);
      var title = parsed.title || slidesStripMdExt(fileName);
      slidesState.title = title;
      slidesState.noteExt = '.' + (fileName.split('.').pop() || 'md');
      slidesState.id = slidesGenId();
      slidesState.slides = parsed.slides;
      slidesState.currentIndex = 0;
      var titleInput = document.getElementById('slidesNotebookTitle');
      if (titleInput) titleInput.value = slidesState.title;
      slidesLoadPage(0);
      slidesRenderOutline();
      slidesUpdateNav();
      slidesSaveLocal();
      slidesStartAutoSave();
      slidesShowCurrentNB(true);
      slidesShowStatus('已打开: ' + slidesState.title);
      slidesLoadNotebookList();
      // 保存到多笔记缓存并注册到编辑器 tab
      _slidesSaveToCache(path);
      _ensureSlidesTab(path, title);
    }
  } catch (e) {
    slidesShowStatus('打开失败');
  }
}

// 删除笔记
async function slidesDeleteNotebook(fileName) {
  if (!await modalConfirm('确定删除笔记 "' + fileName + '"？此操作不可恢复。')) return;
  try {
    var filePath = slidesState.nbCurrentDir ? 'Notes/' + slidesState.nbCurrentDir + '/' + fileName : 'Notes/' + fileName;
    var res = await client.api('/api/file/removeFile', { path: filePath });
    if (res.code === 0) {
      slidesShowStatus('已删除');
      slidesLoadNotebookList();
      // 如果删除的是当前笔记，清空
      var currentFile = (slidesState.title || 'note').replace(/[\\/:*?"<>|]/g, '_') + '.md';
      if (fileName === currentFile) {
        slidesState.id = slidesGenId();
        slidesState.title = '';
        slidesState.slides = [slidesCreateSlide('', '')];
        slidesState.currentIndex = 0;
        var titleInput = document.getElementById('slidesNotebookTitle');
        if (titleInput) titleInput.value = '';
        slidesLoadPage(0);
        slidesRenderOutline();
        slidesUpdateNav();
        slidesSaveLocal();
        slidesShowCurrentNB(false);
      }
    } else {
      slidesShowStatus('删除失败: ' + (res.msg || ''));
    }
  } catch (e) {
    slidesShowStatus('删除失败');
  }
}

// 键盘翻页 & 保存（全局监听）
document.addEventListener('keydown', function(e) {
  if (state.activeNavTab === 'slides') {
    var tag = e.target.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    if ((e.ctrlKey || e.metaKey) && e.key === 'ArrowLeft') { e.preventDefault(); slidesPrev(); }
    if ((e.ctrlKey || e.metaKey) && e.key === 'ArrowRight') { e.preventDefault(); slidesNext(); }
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); slidesDoSave(); }
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    // kmind 保存
    var kmindTab = state.openTabs.find(function(t) { return t._isKmind && t.path === state.activeTab; });
    if (kmindTab) { e.preventDefault(); kmindSave(); }
  }
});

// ─── 关键路径检测 ──────────────────────────────────────────

function formatDuration(minutes) {
  if (!minutes) return '0分钟';
  if (minutes < 60) return minutes + '分钟';
  var h = Math.floor(minutes / 60);
  var m = minutes % 60;
  if (h < 24) return m > 0 ? h + '小时' + m + '分钟' : h + '小时';
  var d = Math.floor(h / 24);
  var rh = h % 24;
  return rh > 0 ? d + '天' + rh + '小时' : d + '天';
}

async function doCriticalPath() {
  var btn = document.getElementById('btnCriticalPath');
  btn.disabled = true;
  btn.textContent = '分析中...';
  try {
    var res = await fetch(API_BASE + '/api/tasks/critical-path');
    var json = await res.json();
    var data = json.data || json;
    if (data) {
      var box = document.getElementById('cpResultBox');
      var detail = document.getElementById('cpResultDetail');
      var taskList = document.getElementById('cpTaskList');
      box.style.display = 'block';

      var html = '<div>项目总工期：<span style="color:var(--accent)">' + formatDuration(data.project_duration) + '</span></div>';
      html += '<div>总任务数：' + data.total_tasks + '，关键任务数：<span style="color:#f59e0b">' + data.critical_tasks + '</span></div>';
      detail.innerHTML = html;

      if (data.critical_path && data.critical_path.length > 0) {
        taskList.style.display = 'block';
        var tHtml = '<div style="font-size:11px;color:var(--fg-muted);margin-bottom:4px">关键路径任务</div>';
        data.critical_path.forEach(function(t) {
          tHtml += '<div style="display:flex;align-items:center;gap:6px;padding:4px 8px;background:var(--bg-secondary);border-radius:4px;margin-bottom:3px;font-size:11px">';
          tHtml += '<span style="flex:1;color:var(--fg);font-weight:500">' + t.title + '</span>';
          tHtml += '<span style="color:var(--accent);font-size:10px">' + formatDuration(t.duration) + '</span>';
          tHtml += '<span style="color:#f59e0b;font-size:10px">裕度:' + t.total_float + '分钟</span>';
          tHtml += '</div>';
        });
        taskList.innerHTML = tHtml;
      } else {
        taskList.style.display = 'none';
      }
      showToast('关键路径分析完成');
    }
  } catch (e) {
    showToast('关键路径分析失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '分析关键路径';
  }
}

// ─── Terminal (xterm.js) ──────────────────────────────────

// ─── Monaco Editor ──────────────────────────────────────

var _monacoEditor = null;
var _monacoReady = false;
var _monacoLoading = false;
var _monacoCurrentFile = null;
var _monacoFiles = {};
var _monacoApi = null;  // 持有 monaco 模块引用，供 _loadMonacoFile 使用
var _monacoSrcFile = null;  // 源码浏览器打开的文件路径，保存时使用源码 API

function _initMonaco(wrap, content, filePath) {
  if (_monacoApi) {
    // API already loaded (e.g. by pane), create editor directly
    var ext = filePath.includes('.') ? filePath.split('.').pop().toLowerCase() : '';
    var langMap = { py:'python', js:'javascript', ts:'typescript', jsx:'javascript', tsx:'typescript',
      r:'r', rmd:'markdown', cpp:'cpp', c:'c', h:'c', java:'java', go:'go', rs:'rust',
      rb:'ruby', php:'php', swift:'swift', kt:'kotlin', scala:'scala', sh:'shell',
      bash:'shell', ps1:'powershell', sql:'sql', css:'css', scss:'scss', less:'less',
      vue:'html', svelte:'html', yaml:'yaml', yml:'yaml', toml:'ini', json:'json',
      xml:'xml', md:'markdown', html:'html', htm:'html', tex:'latex' };
    var lang = langMap[ext] || 'plaintext';
    _monacoEditor = monaco.editor.create(wrap, {
      value: content,
      language: lang,
      theme: 'vs-dark',
      fontSize: 13,
      fontFamily: "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,monospace",
      minimap: { enabled: true, size: 'fit' },
      scrollBeyondLastLine: false,
      wordWrap: 'on',
      automaticLayout: true,
      tabSize: 2,
      cursorBlinking: 'smooth',
      smoothScrolling: true,
      bracketPairColorization: { enabled: true },
      guides: { bracketPairs: true, indentation: true },
      renderLineHighlight: 'all',
      lineNumbersMinChars: 3,
      padding: { top: 6 },
    });
    _monacoReady = true;
    _updateMonacoStatus(filePath.split('/').pop());
    _updateMonacoCursor();
    _monacoEditor.onDidChangeModelContent(function() {
      var tab = state.openTabs.find(function(t) { return t.path === state.activeTab; });
      if (tab && tab._isMonaco) tab.modified = true;
    });
    _monacoEditor.onDidChangeCursorPosition(function(e) {
      _updateMonacoCursor();
    });
    return;
  }
  if (_monacoLoading) {
    setTimeout(function() { _initMonaco(wrap, content, filePath); }, 200);
    return;
  }
  _monacoLoading = true;
  var _vsBaseLocal = location.origin + '/static/monaco-editor/vs';
  var _vsBaseCDN = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs';
  function tryLoadMonaco(vsBase) {
    // 动态加载 Monaco CSS
    var cssHref = vsBase + '/editor/editor.main.min.css';
    if (!document.querySelector('link[href*="editor.main.min.css"]')) {
      var cssLink = document.createElement('link');
      cssLink.rel = 'stylesheet';
      cssLink.href = cssHref;
      document.head.appendChild(cssLink);
    }
    self.MonacoEnvironment = {
      getWorkerUrl: function(moduleId, label) {
        if (label === 'json') return vsBase + '/language/json/json.worker.js';
        if (label === 'css' || label === 'scss' || label === 'less') return vsBase + '/language/css/css.worker.js';
        if (label === 'html' || label === 'handlebars' || label === 'razor') return vsBase + '/language/html/html.worker.js';
        if (label === 'typescript' || label === 'javascript') return vsBase + '/language/typescript/ts.worker.js';
        return vsBase + '/editor/editor.worker.js';
      }
    };
    var _vditorDefine = typeof define !== 'undefined' ? define : null;
    var loaderEl = document.createElement('script');
    loaderEl.src = vsBase + '/loader.js';
    loaderEl.onload = function() {
      var _monacoRequire = window.require;
      if (_vditorDefine) { define = _vditorDefine; }
      _monacoRequire.config({ paths: { vs: vsBase } });
      _monacoRequire(['vs/editor/editor.main'], function() {
        _monacoApi = window.monaco;
        var ext = filePath.includes('.') ? filePath.split('.').pop().toLowerCase() : '';
        var langMap = { py:'python', js:'javascript', ts:'typescript', jsx:'javascript', tsx:'typescript',
          r:'r', rmd:'markdown', cpp:'cpp', c:'c', h:'c', java:'java', go:'go', rs:'rust',
          rb:'ruby', php:'php', swift:'swift', kt:'kotlin', scala:'scala', sh:'shell',
          bash:'shell', ps1:'powershell', sql:'sql', css:'css', scss:'scss', less:'less',
          vue:'html', svelte:'html', yaml:'yaml', yml:'yaml', toml:'ini', json:'json',
          xml:'xml', md:'markdown', html:'html', htm:'html', tex:'latex' };
        var lang = langMap[ext] || 'plaintext';
        _monacoEditor = monaco.editor.create(wrap, {
          value: content,
          language: lang,
          theme: 'vs-dark',
          fontSize: 13,
          fontFamily: "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,monospace",
          minimap: { enabled: true, size: 'fit' },
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          automaticLayout: true,
          tabSize: 2,
          cursorBlinking: 'smooth',
          smoothScrolling: true,
          bracketPairColorization: { enabled: true },
          guides: { bracketPairs: true, indentation: true },
          renderLineHighlight: 'all',
          lineNumbersMinChars: 3,
          padding: { top: 6 },
        });
        _monacoReady = true;
        _updateMonacoStatus(filePath.split('/').pop());
        _updateMonacoCursor();
        _monacoEditor.onDidChangeModelContent(function() {
          var tab = state.openTabs.find(function(t) { return t.path === state.activeTab; });
          if (tab && tab._isMonaco) tab.modified = true;
        });
        _monacoEditor.onDidChangeCursorPosition(function(e) {
          _updateMonacoCursor();
        });
        _monacoLoading = false;
      });
    };
    loaderEl.onerror = function() {
      if (vsBase === _vsBaseLocal) {
        console.warn('Local Monaco load failed, falling back to CDN');
        tryLoadMonaco(_vsBaseCDN);
      } else {
        _monacoLoading = false;
        wrap.innerHTML = '<div style="padding:20px;color:var(--red)">Monaco Editor 加载失败</div>';
      }
    };
    document.head.appendChild(loaderEl);
  }
  tryLoadMonaco(_vsBaseLocal);
}

function _getMonacoContent() {
  return _monacoEditor ? _monacoEditor.getValue() : '';
}

var _codeLangMap = { py:'python', js:'javascript', ts:'typescript', jsx:'javascript', tsx:'typescript',
  r:'r', cpp:'cpp', c:'c', h:'c', java:'java', go:'go', rs:'rust',
  rb:'ruby', php:'php', swift:'swift', kt:'kotlin', scala:'scala', sh:'shell',
  bash:'shell', ps1:'powershell', sql:'sql', css:'css', scss:'scss', less:'less',
  vue:'html', svelte:'html', yaml:'yaml', yml:'yaml', toml:'ini', json:'json',
  xml:'xml', html:'html', htm:'html', tex:'latex' };

function _isCodeFile(path) {
  var ext = path.includes('.') ? path.split('.').pop().toLowerCase() : '';
  return !!_codeLangMap[ext];
}

function _loadMonacoApi() {
  if (_monacoLoading) return;
  _monacoLoading = true;
  var vsBase = location.origin + '/static/monaco-editor/vs';
  if (!document.querySelector('link[href*="editor.main.min.css"]')) {
    var cssLink = document.createElement('link');
    cssLink.rel = 'stylesheet';
    cssLink.href = vsBase + '/editor/editor.main.min.css';
    document.head.appendChild(cssLink);
  }
  self.MonacoEnvironment = {
    getWorkerUrl: function(moduleId, label) {
      if (label === 'json') return vsBase + '/language/json/json.worker.js';
      if (label === 'css' || label === 'scss' || label === 'less') return vsBase + '/language/css/css.worker.js';
      if (label === 'html' || label === 'handlebars' || label === 'razor') return vsBase + '/language/html/html.worker.js';
      if (label === 'typescript' || label === 'javascript') return vsBase + '/language/typescript/ts.worker.js';
      return vsBase + '/editor/editor.worker.js';
    }
  };
  var _vditorDefine = typeof define !== 'undefined' ? define : null;
  var loaderEl = document.createElement('script');
  loaderEl.src = vsBase + '/loader.js';
  loaderEl.onload = function() {
    var _monacoRequire = window.require;
    if (_vditorDefine) { define = _vditorDefine; }
    _monacoRequire.config({ paths: { vs: vsBase } });
    _monacoRequire(['vs/editor/editor.main'], function() {
      _monacoApi = window.monaco;
      _monacoLoading = false;
    });
  };
  loaderEl.onerror = function() {
    console.warn('Local Monaco load failed, falling back to CDN');
    _monacoLoading = false;
    _loadMonacoApiCdn();
  };
  document.head.appendChild(loaderEl);
}

function _loadMonacoApiCdn() {
  if (_monacoLoading) return;
  _monacoLoading = true;
  var vsBase = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs';
  if (!document.querySelector('link[href*="editor.main.min.css"]')) {
    var cssLink = document.createElement('link');
    cssLink.rel = 'stylesheet';
    cssLink.href = vsBase + '/editor/editor.main.min.css';
    document.head.appendChild(cssLink);
  }
  self.MonacoEnvironment = {
    getWorkerUrl: function(moduleId, label) {
      if (label === 'json') return vsBase + '/language/json/json.worker.js';
      if (label === 'css' || label === 'scss' || label === 'less') return vsBase + '/language/css/css.worker.js';
      if (label === 'html' || label === 'handlebars' || label === 'razor') return vsBase + '/language/html/html.worker.js';
      if (label === 'typescript' || label === 'javascript') return vsBase + '/language/typescript/ts.worker.js';
      return vsBase + '/editor/editor.worker.js';
    }
  };
  var _vditorDefine = typeof define !== 'undefined' ? define : null;
  var loaderEl = document.createElement('script');
  loaderEl.src = vsBase + '/loader.js';
  loaderEl.onload = function() {
    var _monacoRequire = window.require;
    if (_vditorDefine) { define = _vditorDefine; }
    _monacoRequire.config({ paths: { vs: vsBase } });
    _monacoRequire(['vs/editor/editor.main'], function() {
      _monacoApi = window.monaco;
      _monacoLoading = false;
    });
  };
  document.head.appendChild(loaderEl);
}

function _ensurePaneMonaco(paneId, content, filePath) {
  var container = document.getElementById('paneMonaco-' + paneId);
  if (!container) return;
  var ext = filePath.includes('.') ? filePath.split('.').pop().toLowerCase() : '';
  var lang = _codeLangMap[ext] || 'plaintext';
  if (!window.monaco) {
    if (!_monacoLoading) _loadMonacoApi();
    setTimeout(function() { _ensurePaneMonaco(paneId, content, filePath); }, 200);
    return;
  }
  var api = window.monaco;
  var uri = api.Uri.file(paneId + '/' + filePath);
  var model = api.editor.getModel(uri);
  if (!model) {
    model = api.editor.createModel(content, lang, uri);
  } else {
    model.setValue(content);
  }
  var editor = state['paneMonaco_' + paneId];
  if (!editor) {
    state['paneMonaco_' + paneId] = api.editor.create(container, {
      model: model,
      theme: 'vs-dark',
      fontSize: 13,
      fontFamily: "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,monospace",
      minimap: { enabled: true, size: 'fit' },
      scrollBeyondLastLine: false,
      wordWrap: 'on',
      automaticLayout: true,
      tabSize: 2,
      cursorBlinking: 'smooth',
      smoothScrolling: true,
      bracketPairColorization: { enabled: true },
      guides: { bracketPairs: true, indentation: true },
      renderLineHighlight: 'all',
      lineNumbersMinChars: 3,
      padding: { top: 6 },
    });
    state['paneMonaco_' + paneId].onDidChangeModelContent(function() {
      var activePath = state['paneActiveTab_' + paneId];
      if (activePath) {
        var tabs = state['paneTabs_' + paneId] || [];
        var tab = tabs.find(function(t) { return t.path === activePath; });
        if (tab) tab.modified = true;
      }
    });
  } else {
    editor.setModel(model);
  }
}

function _loadMonacoFile(filePath) {
  if (!_monacoEditor || !filePath || !_monacoFiles[filePath]) return;
  var ext = filePath.includes('.') ? filePath.split('.').pop().toLowerCase() : '';
  var langMap = { py:'python', js:'javascript', ts:'typescript', jsx:'javascript', tsx:'typescript',
    r:'r', rmd:'markdown', cpp:'cpp', c:'c', h:'c', java:'java', go:'go', rs:'rust',
    rb:'ruby', php:'php', swift:'swift', kt:'kotlin', scala:'scala', sh:'shell',
    bash:'shell', ps1:'powershell', sql:'sql', css:'css', scss:'scss', less:'less',
    vue:'html', svelte:'html', yaml:'yaml', yml:'yaml', toml:'ini', json:'json',
    xml:'xml', md:'markdown', html:'html', htm:'html', tex:'latex' };
  var lang = langMap[ext] || 'plaintext';
  var uri = _monacoApi.Uri.file(filePath);
  var oldModel = _monacoEditor.getModel();
  // 检查同名 model 是否已存在，避免 "Cannot add model because it already exists"
  var model = _monacoApi.editor.getModel(uri);
  if (model) {
    model.setValue(_monacoFiles[filePath]);
  } else {
    model = _monacoApi.editor.createModel(_monacoFiles[filePath], lang, uri);
  }
  _monacoEditor.setModel(model);
  if (oldModel && oldModel !== model) oldModel.dispose();
  _monacoCurrentFile = filePath;
  _updateMonacoStatus(filePath.split('/').pop());
  // 切换文件时清空执行输出
  var output = document.getElementById('monacoOutput');
  if (output) { output.style.display = 'none'; output.textContent = ''; }
  var st = document.getElementById('monacoExecStatus');
  if (st) { st.textContent = ''; }
  _updateMonacoCursor();
}

// ─── Monaco 辅助函数 ─────────────────────────────────────

function _updateMonacoStatus(fileName) {
  var el = document.getElementById('monacoFilePath');
  if (el) el.textContent = fileName || '';
  var langEl = document.getElementById('monacoLangStatus');
  if (langEl && _monacoCurrentFile) {
    var ext = _monacoCurrentFile.includes('.') ? _monacoCurrentFile.split('.').pop().toLowerCase() : '';
    var langNames = { py:'Python', js:'JavaScript', ts:'TypeScript', jsx:'JavaScript', tsx:'TypeScript',
      r:'R', rmd:'R Markdown', cpp:'C++', c:'C', h:'C', java:'Java', go:'Go', rs:'Rust',
      rb:'Ruby', php:'PHP', swift:'Swift', kt:'Kotlin', scala:'Scala', sh:'Shell Script',
      bash:'Bash', ps1:'PowerShell', sql:'SQL', css:'CSS', scss:'SCSS', less:'LESS',
      vue:'Vue', svelte:'Svelte', yaml:'YAML', yml:'YAML', toml:'TOML',
      json:'JSON', xml:'XML', md:'Markdown', html:'HTML', tex:'LaTeX' };
    langEl.textContent = langNames[ext] || ext.toUpperCase() || 'Plain Text';
  }
}

function _updateMonacoCursor() {
  if (!_monacoEditor) return;
  var pos = _monacoEditor.getPosition();
  if (!pos) return;
  var el = document.getElementById('monacoCursorPos');
  if (el) el.textContent = 'Ln ' + pos.lineNumber + ', Col ' + pos.column;
}

// ─── Monaco 代码执行 ─────────────────────────────────────

var _execOutput = document.getElementById('monacoOutput');
var _execStatus = document.getElementById('monacoExecStatus');
var _execRunning = false;
var _execAbortController = null;

function _showStopBtn(show) {
  var btn = document.getElementById('monacoStopBtn');
  if (btn) btn.style.display = show ? 'flex' : 'none';
}

function getMonacoLanguage() {
  if (!_monacoCurrentFile) return 'python';
  var ext = _monacoCurrentFile.includes('.') ? _monacoCurrentFile.split('.').pop().toLowerCase() : '';
  var langMap = { py:'python', js:'javascript', ts:'typescript', jsx:'javascript', tsx:'typescript',
    r:'r', rmd:'r', cpp:'cpp', c:'c', h:'c', java:'java', go:'go', rs:'rust',
    rb:'ruby', php:'php', swift:'swift', kt:'kotlin', scala:'scala', sh:'bash',
    bash:'bash', ps1:'powershell', sql:'sql', css:'css', scss:'scss', less:'less',
    vue:'javascript', svelte:'javascript', yaml:'yaml', yml:'yaml', toml:'ini',
    json:'json', xml:'xml', md:'markdown', html:'html', htm:'html', tex:'latex' };
  return langMap[ext] || 'python';
}

async function execMonacoCode() {
  if (!_monacoEditor) { showToast('Monaco 编辑器未加载', 'error'); return; }
  var code = _monacoEditor.getValue();
  if (!code || !code.trim()) { showToast('没有代码可执行', 'error'); return; }

  var language = getMonacoLanguage();
  var filePath = _monacoCurrentFile || '';
  var runBtn = document.getElementById('monacoRunBtn');
  var stopBtn = document.getElementById('monacoStopBtn');
  runBtn.disabled = true;
  runBtn.style.display = 'none';
  _showStopBtn(true);
  if (_execStatus) _execStatus.textContent = '';
  _execRunning = true;

  // 显示 output 面板，滚动到可见位置
  var output = _execOutput;
  output.style.display = 'block';
  output.textContent = '$ ' + (filePath || language) + '\n';
  output.scrollTop = output.scrollHeight;
  setTimeout(function() { output.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, 100);

  // 支持停止：用 AbortController 超时
  _execAbortController = new AbortController();
  var signal = _execAbortController.signal;
  var timedOut = false;
  var timer = setTimeout(function() { timedOut = true; }, 60000);

  try {
    var body = { language: language, code: code };
    if (filePath) body.file_path = filePath;
    var res = await fetch(API_BASE + '/api/exec/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: signal,
    });
    var json = await res.json();
    if (timedOut) {
      output.textContent += '\n✗ 客户端超时 (>60s)\n';
      if (_execStatus) { _execStatus.textContent = '✗ 超时'; _execStatus.style.color = '#ff7b72'; }
    } else if (json.code === 0 && json.data) {
      var d = json.data;
      if (d.exit_code === -2) {
        output.textContent += '\n■ 已停止\n';
        if (_execStatus) { _execStatus.textContent = '■ 已停止'; _execStatus.style.color = '#ff7b72'; }
      } else {
        output.textContent += d.stdout;
        if (d.stderr) output.textContent += '\n' + d.stderr;
        if (d.exit_code === 0) {
          output.textContent += '\n✓ 完成 (退出码 0)\n';
          if (_execStatus) { _execStatus.textContent = '✓ 完成'; _execStatus.style.color = '#3fb950'; }
        } else {
          output.textContent += '\n✗ 退出码: ' + d.exit_code + '\n';
          if (_execStatus) { _execStatus.textContent = '✗ 退出码 ' + d.exit_code; _execStatus.style.color = '#ff7b72'; }
        }
      }
    } else {
      output.textContent += '\n[错误] ' + (json.msg || '执行失败');
    }
  } catch (e) {
    output.textContent += '\n[错误] ' + e.message;
    if (_execStatus) { _execStatus.textContent = '✗ 错误'; _execStatus.style.color = '#f7768e'; }
  } finally {
    clearTimeout(timer);
    _execRunning = false;
    _execAbortController = null;
    runBtn.disabled = false;
    runBtn.style.display = '';
    _showStopBtn(false);
    output.scrollTop = output.scrollHeight;
  }
}

function stopMonacoCode() {
  if (!_execRunning) return;
  // 发请求终止后端进程
  fetch(API_BASE + '/api/exec/stop', { method: 'POST' }).catch(function(){});
  // 同时取消前端 fetch
  if (_execAbortController) {
    _execAbortController.abort();
    _execAbortController = null;
  }
  var output = _execOutput;
  output.textContent += '\n■ 正在停止...\n';
  if (_execStatus) { _execStatus.textContent = '■ 停止中'; _execStatus.style.color = '#ff7b72'; }
}

async function runInTerminal() {
  if (!_monacoEditor) { showToast('Monaco 编辑器未加载', 'error'); return; }
  var code = _monacoEditor.getValue();
  if (!code || !code.trim()) { showToast('没有代码可执行', 'error'); return; }

  var language = getMonacoLanguage();
  var filePath = _monacoCurrentFile || '';
  var termBtn = document.getElementById('monacoRunTerminalBtn');
  var runBtn = document.getElementById('monacoRunBtn');
  termBtn.disabled = true;
  termBtn.textContent = '⏳';
  runBtn.disabled = true;
  runBtn.style.display = 'none';
  _showStopBtn(true);

  try {
    var body = { language: language, code: code };
    if (filePath) body.file_path = filePath;
    var res = await fetch(API_BASE + '/api/exec/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    var json = await res.json();
    if (json.code !== 0 || !json.data) {
      showToast('执行失败', 'error');
      return;
    }
    var d = json.data;
    var output = _execOutput;
    output.style.display = 'block';
    output.textContent = '$ ' + d.command + '\n' + d.stdout;
    if (d.stderr) output.textContent += '\n' + d.stderr;
    if (d.exit_code === 0) {
      output.textContent += '\n✓ 完成 (退出码 0)\n';
      if (_execStatus) { _execStatus.textContent = '✓ 完成'; _execStatus.style.color = '#3fb950'; }
    } else {
      output.textContent += '\n✗ 退出码: ' + d.exit_code + '\n';
      if (_execStatus) { _execStatus.textContent = '✗ 退出码 ' + d.exit_code; _execStatus.style.color = '#ff7b72'; }
    }
    output.scrollTop = output.scrollHeight;
    if (!document.getElementById('terminalPanel').classList.contains('open')) {
      toggleTerminal();
    }
  } catch (e) {
    showToast('执行出错: ' + e.message, 'error');
  } finally {
    termBtn.disabled = false;
    termBtn.innerHTML = '⬇ <span style="font-weight:400;font-size:10px">终端</span>';
    runBtn.disabled = false;
    runBtn.style.display = '';
    _showStopBtn(false);
  }
}

// Ctrl+Enter 快速运行 / Ctrl+Shift+Enter 终端中运行
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    var monacoView = document.getElementById('monacoEditorView');
    if (monacoView && monacoView.style.display !== 'none' && _monacoEditor) {
      e.preventDefault();
      if (e.shiftKey) {
        runInTerminal();
      } else {
        execMonacoCode();
      }
    }
  }
});

// ─── Terminal (xterm.js) ──────────────────────────────────

var _term = null;
var _termFit = null;
var _termWs = null;

function toggleTerminal() {
  var panel = document.getElementById('terminalPanel');
  if (panel.classList.contains('open')) {
    panel.classList.remove('open');
    if (_term) _term.blur();
  } else {
    panel.classList.add('open');
    if (!_term) initTerminal();
    else _term.focus();
  }
}

function initTerminal() {
  var body = document.getElementById('terminalBody');
  var panel = document.getElementById('terminalPanel');
  body.innerHTML = '';
  if (_term) { _term.dispose(); _term = null; }
  if (_termWs) { _termWs.close(); _termWs = null; }

  _term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block',
    fontSize: 13,
    fontFamily: "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,monospace",
    theme: {
      background: '#0d1117',
      foreground: '#e6edf3',
      cursor: '#e6edf3',
      selectionBackground: '#3b4261',
      black: '#484f58', red: '#ff7b72', green: '#3fb950', yellow: '#d29922',
      blue: '#58a6ff', magenta: '#bc8cff', cyan: '#39c5cf', white: '#b1bac4',
      brightBlack: '#6e7681', brightRed: '#ff7b72', brightGreen: '#3fb950',
      brightYellow: '#d29922', brightBlue: '#58a6ff', brightMagenta: '#bc8cff',
      brightCyan: '#39c5cf', brightWhite: '#f0f6fc',
    },
  });
  _termFit = new FitAddon.FitAddon();
  _term.loadAddon(_termFit);
  _term.open(body);
  _termFit.fit();

  // WebSocket 连接
  var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var wsUrl = proto + '//' + location.host + '/api/terminal';
  _termWs = new WebSocket(wsUrl);
  _termWs.binaryType = 'arraybuffer';

  _termWs.onopen = function() {
    _term.focus();
    setTimeout(function() { _termFit.fit(); }, 100);
  };
  _termWs.onmessage = function(ev) {
    _term.write(new Uint8Array(ev.data));
  };
  _termWs.onclose = function() {
    if (_term) _term.write('\r\n\x1b[31m[终端连接已断开]\x1b[0m\r\n');
    _termWs = null;
  };
  _termWs.onerror = function() {
    if (_term) _term.write('\r\n\x1b[31m[终端连接错误]\x1b[0m\r\n');
  };

  _term.onData(function(data) {
    if (_termWs && _termWs.readyState === WebSocket.OPEN) {
      _termWs.send(data);
    }
  });

  // 窗口 resize → 终端 fit
  window.addEventListener('resize', function() {
    if (_termFit) _termFit.fit();
  });
  // 面板可拖动变化 → 终端 fit（MutationObserver 监听）
  var observer = new MutationObserver(function() {
    if (_termFit && panel.classList.contains('open')) _termFit.fit();
  });
  observer.observe(panel, { attributes: true, attributeFilter: ['class', 'style'] });
}

function killTerminal() {
  if (_termWs) { _termWs.close(); _termWs = null; }
  if (_term) { _term.dispose(); _term = null; }
  document.getElementById('terminalBody').innerHTML = '';
  document.getElementById('terminalPanel').classList.remove('open');
}

// 终端面板拖拽调整高度
(function initTerminalResize() {
  var handle = document.getElementById('terminalResizeHandle');
  var panel = document.getElementById('terminalPanel');
  if (!handle || !panel) return;
  var isDragging = false, startY, startH;
  handle.addEventListener('mousedown', function(e) {
    isDragging = true;
    startY = e.clientY;
    startH = panel.offsetHeight;
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    var delta = startY - e.clientY;
    var newH = Math.max(80, Math.min(600, startH + delta));
    panel.style.height = newH + 'px';
    if (_termFit) setTimeout(function() { _termFit.fit(); }, 50);
  });
  document.addEventListener('mouseup', function() {
    if (!isDragging) return;
    isDragging = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
})();

// Ctrl+` 切换终端
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === '`') {
    e.preventDefault();
    toggleTerminal();
  }
});

// ─── 内置浏览器 ──────────────────────────────────────────

var _searchEngines = [
  { name: 'Google', url: 'https://www.google.com/search?q=' },
  { name: 'Bing',   url: 'https://www.bing.com/search?q=' },
  { name: 'DuckDuckGo', url: 'https://duckduckgo.com/?q=' },
  { name: '百度',   url: 'https://www.baidu.com/s?wd=' },
  { name: '搜狗',   url: 'https://www.sogou.com/web?query=' },
];
var _curSearchEngine = localStorage.getItem('ts2_search_engine') || 0;

function _browserTabState(tab) {
  if (!tab._browserUrl) tab._browserUrl = 'about:blank';
  if (!tab._browserHistory) tab._browserHistory = [];
  if (tab._browserHistoryIdx === undefined) tab._browserHistoryIdx = -1;
  return tab;
}

function _saveBrowserFrame(tab) {
  var frame = document.getElementById('browserFrame');
  var input = document.getElementById('browserUrlInput');
  if (!frame || !tab) return;
  tab._browserUrl = frame.getAttribute('data-url') || input.value || 'about:blank';
}

function _browserFallback(url) {
  var tab = state.openTabs.find(function(t) { return t.path === state.activeTab; });
  if (tab) tab._browserFallback = true;
  var frame = document.getElementById('browserFrame');
  if (frame) {
    frame.removeAttribute('srcdoc');
    _setFrameSandbox(frame, true);
    frame.src = url;
  }
}

function _browserLoadUrl(url) {
  var frame = document.getElementById('browserFrame');
  var input = document.getElementById('browserUrlInput');
  if (!frame || !input) return;
  var tab = state.openTabs.find(function(t) { return t.path === state.activeTab; });
  if (tab) delete tab._browserFallback;
  input.value = url;
  frame.setAttribute('data-url', url);
  frame.removeAttribute('srcdoc');
  _setFrameSandbox(frame, true);
  frame.src = _browserProxyUrl(url);
}

// 监听 iframe 加载完成，检测代理错误后自动降级和同步 URL
(function() {
  var frame = document.getElementById('browserFrame');
  var input = document.getElementById('browserUrlInput');
  if (!frame) return;
  frame.addEventListener('load', function() {
    var tab = state.openTabs.find(function(t) { return t.path === state.activeTab; });
    if (!tab || !tab._isBrowser || tab._browserFallback) return;
    try {
      // 同步 URL 地址栏（代理页面同源，可读取 iframe URL）
      if (input && frame.contentWindow) {
        var iframeUrl = frame.contentWindow.location.href;
        if (iframeUrl && iframeUrl.indexOf('/api/browser/proxy?url=') >= 0) {
          var actualUrl = decodeURIComponent(iframeUrl.split('?url=')[1] || '');
          if (actualUrl && actualUrl !== input.value) {
            input.value = actualUrl;
            frame.setAttribute('data-url', actualUrl);
            tab._browserUrl = actualUrl;
            // 避免重复压入历史
            if (tab._browserHistory[tab._browserHistoryIdx] !== actualUrl) {
              if (tab._browserHistoryIdx < tab._browserHistory.length - 1) {
                tab._browserHistory = tab._browserHistory.slice(0, tab._browserHistoryIdx + 1);
              }
              tab._browserHistory.push(actualUrl);
              tab._browserHistoryIdx = tab._browserHistory.length - 1;
            }
          }
        }
      }
      // 检测代理错误后自动降级
      var doc = frame.contentDocument || frame.contentWindow.document;
      if (doc && doc.body) {
        var text = doc.body.textContent || '';
        if (text.indexOf('代理错误') >= 0 || text.indexOf('错误：') >= 0) {
          var url = tab._browserUrl;
          if (url && !_isStartPage(url)) {
            tab._browserFallback = true;
            frame.removeAttribute('srcdoc');
            frame.src = url;
            return;
          }
        }
      }
      // 同源页面：拦截所有链接点击走代理
      if (doc && doc.addEventListener) {
        doc.addEventListener('click', function(e) {
          var a = e.target.closest('a');
          if (!a) return;
          var h = a.getAttribute('href');
          if (!h || h === '#' || h.indexOf('javascript:') === 0) return;
          try {
            var absUrl = new URL(h, doc.baseURI).href;
            if (absUrl.indexOf(location.origin + '/api/browser/proxy') >= 0) return;
            e.preventDefault();
            // 中键 / Ctrl+click / Cmd+click / target=_blank → 新标签打开
            if (e.button === 1 || e.ctrlKey || e.metaKey || a.target === '_blank') {
              openBrowser(absUrl);
              return;
            }
            var proxyUrl = '/api/browser/proxy?url=' + encodeURIComponent(absUrl);
            frame.src = proxyUrl;
            // 同步地址栏
            if (input) { input.value = absUrl; frame.setAttribute('data-url', absUrl); }
            tab._browserUrl = absUrl;
            if (tab._browserHistory[tab._browserHistoryIdx] !== absUrl) {
              if (tab._browserHistoryIdx < tab._browserHistory.length - 1)
                tab._browserHistory = tab._browserHistory.slice(0, tab._browserHistoryIdx + 1);
              tab._browserHistory.push(absUrl);
              tab._browserHistoryIdx = tab._browserHistory.length - 1;
            }
          } catch(ex) {}
        }, true);
        // 阻止中键默认行为（自动滚动）
        doc.addEventListener('mousedown', function(e) {
          if (e.button === 1) e.preventDefault();
        }, true);
      }
      // 根据页面标题重命名标签
      try {
        var pageTitle = doc && doc.title;
        if (pageTitle && pageTitle.trim()) {
          tab.name = pageTitle.trim();
          var label = document.querySelector('[data-path="' + tab.path.replace(/"/g,'\\"') + '"] .tab-label');
          if (label) label.textContent = '🌐 ' + pageTitle.trim();
        }
      } catch(e) {}
    } catch(e) {}
  });
})();

function _restoreBrowserFrame(tab) {
  var frame = document.getElementById('browserFrame');
  var input = document.getElementById('browserUrlInput');
  if (!frame || !tab) return;
  var url = tab._browserUrl || 'about:blank';
  if (_isStartPage(url)) {
    input.value = '';
    frame.removeAttribute('src');
    _setFrameSandbox(frame, false);_renderStartPage().then(function(html) { frame.srcdoc = html; });
  } else {
    _browserLoadUrl(url);
  }
}

function _renderStartPageInPane(paneId) {
  _renderStartPage(paneId).then(function(html) {
    var frame = document.getElementById('paneBrowserFrame-' + paneId);
    if (frame) { _setFrameSandbox(frame, false); frame.srcdoc = html; }
  });
}

function openBrowser(url) {
  var tab = { path: '__browser__' + Date.now(), name: '浏览器', modified: false, _isBrowser: true };
  _browserTabState(tab);
  state.openTabs.push(tab);
  addTab(tab.path, '🌐 浏览器');
  if (url) {
    if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;
    tab._browserUrl = url;
  }
  if (_splitActive && _activePaneId !== '0' && _activePaneId !== _agentPaneId) {
    editorService.openInPane(tab.path, _activePaneId);
  } else {
    editorService.switchTo(tab.path);
  }
}

function openBrowserInPane(paneId, url) {
  if (url) {
    if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;
    var frame = document.getElementById('paneBrowserFrame-' + paneId);
    var inp = document.getElementById('paneBrowserUrl-' + paneId);
    if (frame && inp) {
      inp.value = url;
      frame.removeAttribute('srcdoc');
      _setFrameSandbox(frame, true);
      frame.src = '/api/browser/proxy?url=' + encodeURIComponent(url);
      var tabs = state['paneTabs_' + paneId] || [];
      for (var i = 0; i < tabs.length; i++) {
        if (tabs[i]._isBrowser) { tabs[i]._browserUrl = url; break; }
      }
      return;
    }
  }
  var path = '__browser__' + Date.now();
  var tabs = state['paneTabs_' + paneId] || [];
  tabs.push({ path: path, name: '浏览器', modified: false, _isBrowser: true, _browserUrl: url || '' });
  state['paneTabs_' + paneId] = tabs;
  var tabsEl = document.getElementById('editorTabs-' + paneId);
  if (tabsEl) tabsEl.appendChild(_createPaneTabEl(path, '浏览器', paneId, false));
  editorService.switchInPane(path, paneId);
}

var _browserBookmarksCache = null;

async function _loadBrowserBookmarks() {
  // 加载 bookmarks.json（静态书签，通过 API 获取）
  try {
    if (!_browserBookmarksCache) {
      var resp = await fetch('/api/data/bookmarks', { method: 'POST' });
      var result = await resp.json();
      _browserBookmarksCache = result.data || result || [];
    }
    return _browserBookmarksCache;
  } catch(e) {
    return [];
  }
}

function _loadCustomBookmarks() {
  try {
    return JSON.parse(localStorage.getItem('ts2_browser_bookmarks_custom')) || [];
  } catch { return []; }
}

function _saveCustomBookmarks(bms) {
  try {
    localStorage.setItem('ts2_browser_bookmarks_custom', JSON.stringify(bms));
  } catch(e) {}
}

function _isStartPage(url) {
  return !url || url === 'about:blank' || url === 'about:start';
}

function _browserProxyUrl(url) {
  if (!url || _isStartPage(url) || url.indexOf('/api/browser/proxy') >= 0) return url;
  return '/api/browser/proxy?url=' + encodeURIComponent(url);
}

async function _renderStartPage(paneId) {
  var _obPfx = paneId ? 'openBrowserInPane(\'' + paneId + '\',' : 'openBrowser(';
  var staticBms = await _loadBrowserBookmarks();
  var customBms = _loadCustomBookmarks();
  var engIdx = parseInt(_curSearchEngine);
  var eng = _searchEngines[engIdx] || _searchEngines[0];
  var engOptions = _searchEngines.map(function(e, i) {
    return '<span class="eng-opt' + (i === engIdx ? ' active' : '') + '" data-idx="' + i + '">' + e.name + '</span>';
  }).join('');

  var allCats = ['全部'];
  var catSet = {};
  staticBms.forEach(function(b) {
    var c = b.category || '其他';
    if (!catSet[c]) { catSet[c] = true; allCats.push(c); }
  });

  var makeBmItem = function(b, isCustom, idx) {
    var safeUrl = encodeURI(b.url);
    var cat = (b.category || '其他').replace(/"/g,'&quot;');
    var name = (b.name || '未命名').replace(/</g,'&lt;');
    var delHtml = isCustom
      ? '<span class="bm-del" onclick="event.stopPropagation();parent._delCustomBm(' + idx + ')">&times;</span>'
      : '';
    return '<div class="bm-item bm-sys" data-cat="' + cat + '" data-name="' + name.toLowerCase() + '" data-url="' + (b.url||'').toLowerCase() + '" onclick="parent.' + _obPfx + 'decodeURIComponent(\'' + safeUrl.replace(/'/g,"%27") + '\'))">'
      + '<span class="bm-icon">' + (b.icon || '🔖') + '</span>'
      + '<span class="bm-name">' + name + '</span>'
      + delHtml
      + '</div>';
  };

  var makeCustomBmItem = function(b, i) {
    var cat = (b.category || '其他').replace(/"/g,'&quot;');
    var name = (b.name || '未命名').replace(/</g,'&lt;');
    return '<div class="bm-item bm-custom" data-cat="' + cat + '" data-name="' + name.toLowerCase() + '" data-url="' + (b.url||'').toLowerCase() + '" onclick="parent.' + _obPfx + 'decodeURIComponent(\'' + encodeURI(b.url).replace(/'/g,"%27") + '\'))">'
      + '<span class="bm-icon">' + (b.icon || '🔖') + '</span>'
      + '<span class="bm-name">' + name + '</span>'
      + '<span class="bm-del" onclick="event.stopPropagation();parent._delCustomBm(' + i + ')">&times;</span>'
      + '</div>';
  };

  var catBtns = allCats.map(function(c) {
    return '<span class="cat-btn active" data-cat="' + c + '">' + c + '</span>';
  }).join('');
  var staticItems = staticBms.map(function(b) { return makeBmItem(b, false, 0); }).join('');
  var customItems = customBms.map(function(b, i) { return makeCustomBmItem(b, i); }).join('');
  var addBmHtml = '<div class="bm-item bm-add" onclick="parent._promptAddBm()"><span class="bm-icon">+</span><span class="bm-name" style="color:#7aa2f7">添加书签</span></div>';

  return '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    + '<style>'
    + '*{margin:0;padding:0;box-sizing:border-box}'
    + 'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#1a1b26;color:#c0caf5;display:flex;flex-direction:column;align-items:center;padding:60px 20px 40px;min-height:100vh}'
    + '.logo{font-size:32px;font-weight:800;color:#7aa2f7;margin-bottom:24px;letter-spacing:-0.5px}'
    + '.search-wrap{width:100%;max-width:580px;background:#24253a;border:1px solid #3b3d5c;border-radius:12px;padding:6px 6px 6px 16px;display:flex;align-items:center;gap:6px;position:relative}'
    + '.search-wrap .eng{font-size:12px;font-weight:600;color:#7aa2f7;cursor:pointer;white-space:nowrap;padding:4px 6px;border-radius:4px;user-select:none}'
    + '.search-wrap .eng:hover{background:#2f314a}'
    + '.search-wrap input{flex:1;border:none;background:transparent;outline:none;font-size:14px;color:#c0caf5;padding:8px 4px;min-width:0}'
    + '.search-wrap input::placeholder{color:#565a7a}'
    + '.search-wrap button{background:#7aa2f7;color:#1a1b26;border:none;border-radius:8px;padding:8px 18px;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap}'
    + '.search-wrap button:hover{background:#89b4fa}'
    + '.eng-popup{display:none;position:absolute;top:calc(100% + 4px);left:0;background:#24253a;border:1px solid #3b3d5c;border-radius:8px;padding:4px 0;z-index:10;min-width:120px}'
    + '.eng-popup.show{display:block}'
    + '.eng-popup .eng-opt{padding:6px 14px;font-size:12px;cursor:pointer;white-space:nowrap;color:#a9b1d6}'
    + '.eng-popup .eng-opt:hover{background:#2f314a;color:#c0caf5}'
    + '.eng-popup .eng-opt.active{color:#7aa2f7;font-weight:600}'
    + '.section-title{width:100%;max-width:580px;font-size:13px;font-weight:600;color:#565a7a;margin:32px 0 12px;text-align:left}'
    + '.bm-filter{width:100%;max-width:580px;display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 6px}'
    + '.bm-filter input{flex:1;min-width:120px;padding:6px 10px;background:#24253a;border:1px solid #3b3d5c;border-radius:6px;outline:none;font-size:12px;color:#c0caf5}'
    + '.bm-filter input:focus{border-color:#7aa2f7}'
    + '.bm-filter input::placeholder{color:#565a7a}'
    + '.cat-btn{font-size:11px;padding:3px 9px;background:#24253a;border:1px solid #3b3d5c;border-radius:12px;cursor:pointer;color:#a9b1d6;user-select:none}'
    + '.cat-btn:hover{border-color:#7aa2f7;color:#c0caf5}'
    + '.cat-btn.active{background:#7aa2f7;color:#1a1b26;border-color:#7aa2f7;font-weight:600}'
    + '.bookmarks{width:100%;max-width:580px;display:flex;flex-wrap:wrap;gap:8px}'
    + '.bm-item{display:flex;align-items:center;gap:6px;padding:8px 12px;background:#24253a;border:1px solid #3b3d5c;border-radius:8px;text-decoration:none;color:#c0caf5;font-size:12px;transition:0.1s;cursor:pointer}'
    + '.bm-item:hover{background:#2f314a;border-color:#7aa2f7}'
    + '.bm-item .bm-icon{font-size:16px;flex-shrink:0}'
    + '.bm-item .bm-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px}'
    + '.bm-item .bm-del{margin-left:auto;font-size:14px;color:#565a7a;padding:0 2px;display:none}'
    + '.bm-item:hover .bm-del{display:block}'
    + '.bm-item .bm-del:hover{color:#f7768e}'
    + '.bm-item.hidden{display:none}'
    + '.bm-add{border:1px dashed #3b3d5c;background:transparent}'
    + '.bm-add:hover{border-color:#7aa2f7;background:rgba(122,162,247,0.05)}'
    + '.section-sep{width:100%;font-size:11px;color:#565a7a;margin:8px 0 4px;padding:0 4px;font-weight:600}'
    + '</style></head><body>'
    + '<div class="logo">TS2 Browser</div>'
    + '<div class="search-wrap">'
    + '<span class="eng" onclick="toggleEng(event)" id="engLabel">' + eng.name + '</span>'
    + '<div class="eng-popup" id="engPopup">' + engOptions + '</div>'
    + '<input id="searchInput" type="text" placeholder="搜索或输入网址..." autofocus spellcheck="false"'
    + ' onkeydown="if(event.key===\'Enter\') doSearch()">'
    + '<button onclick="doSearch()">搜索</button>'
    + '</div>'
    + '<div class="section-title" style="margin-top:40px">🔖 浏览器书签</div>'
    + '<div class="bm-filter"><input id="bmSearchInput" type="text" placeholder="搜索书签..." oninput="filterBms()">'
    + '<span style="font-size:11px;color:#565a7a;padding:4px 2px">分类:</span>'
    + catBtns + '</div>'
    + '<div class="bookmarks">' + addBmHtml + '</div>'
    + (staticItems ? '<div class="section-sep">── 系统书签 ──</div><div class="bookmarks" id="sysBms">' + staticItems + '</div>' : '')
    + (customItems ? '<div class="section-sep">── 自定义书签 ──</div><div class="bookmarks" id="customBms">' + customItems + '</div>' : '')
    + '<script>'
    + 'var engData = ' + JSON.stringify(_searchEngines) + ';'
    + 'var curEng = ' + JSON.stringify(engIdx + '') + ';'
    + 'var _paneId = ' + (paneId ? ('\'' + paneId + '\'') : 'null') + ';'
    + 'function doSearch(){'
    + 'var q=document.getElementById("searchInput").value.trim();if(!q)return;'
    + 'var isUrl=q.match(/^https?:\\/\\//)||q.match(/^[\\w.-]+\\.[a-z]{2,}(\\/|$)/i);'
    + 'var url;if(isUrl){url=q;}'
    + 'else{var idx=parseInt(curEng)||0;var e=engData[idx]||engData[0];url=e.url+encodeURIComponent(q);}'
    + 'if(_paneId)parent.openBrowserInPane(_paneId,url);else parent.openBrowser(url);}'
    + 'function toggleEng(e){e.stopPropagation();'
    + 'var p=document.getElementById("engPopup");p.classList.toggle("show");}'
    + 'document.addEventListener("click",function(){document.getElementById("engPopup").classList.remove("show");});'
    + 'document.querySelectorAll(".eng-opt").forEach(function(el){'
    + 'el.addEventListener("click",function(e){e.stopPropagation();'
    + 'curEng=this.dataset.idx;'
    + 'document.getElementById("engLabel").textContent=this.textContent;'
    + 'document.getElementById("engPopup").classList.remove("show");'
    + 'document.querySelectorAll(".eng-opt").forEach(function(o){o.classList.remove("active");});'
    + 'this.classList.add("active");'
    + 'parent._setSearchEngine(curEng);});});'
    + 'var _curCat="全部";'
    + 'document.querySelectorAll(".cat-btn").forEach(function(btn){'
    + 'btn.addEventListener("click",function(){'
    + '_curCat=this.dataset.cat;'
    + 'document.querySelectorAll(".cat-btn").forEach(function(b){b.classList.remove("active");});'
    + 'this.classList.add("active");filterBms();});});'
    + 'function filterBms(){'
    + 'var q=document.getElementById("bmSearchInput").value.trim().toLowerCase();'
    + 'document.querySelectorAll(".bm-item.bm-sys,.bm-item.bm-custom").forEach(function(el){'
    + 'var show=true;'
    + 'if(_curCat!=="全部"&&el.dataset.cat!==_curCat)show=false;'
    + 'if(q&&el.dataset.name.indexOf(q)<0&&el.dataset.url.indexOf(q)<0)show=false;'
    + 'el.classList.toggle("hidden",!show);});}'
    + 'document.getElementById("searchInput").focus();'
    + '</script></body></html>';
}

function _setSearchEngine(idx) {
  _curSearchEngine = idx;
  localStorage.setItem('ts2_search_engine', idx);
}

function _browserNavigate(url) {
  var frame = document.getElementById('browserFrame');
  var input = document.getElementById('browserUrlInput');
  if (!frame || !input) return;
  var curPath = state.activeTab;
  var tab = state.openTabs.find(function(t) { return t.path === curPath; });
  if (!tab || !tab._isBrowser) return;
  _browserTabState(tab);
  if (_isStartPage(url)) {
    frame.removeAttribute('src');
    input.value = '';
    _setFrameSandbox(frame, false);_renderStartPage().then(function(html) { frame.srcdoc = html; });
    tab._browserUrl = 'about:blank';
    tab._browserHistory = [];
    tab._browserHistoryIdx = -1;
    frame.setAttribute('data-url', 'about:blank');
    return;
  }
  frame.removeAttribute('srcdoc');
  if (tab._browserHistoryIdx < tab._browserHistory.length - 1) {
    tab._browserHistory = tab._browserHistory.slice(0, tab._browserHistoryIdx + 1);
  }
  tab._browserHistory.push(url);
  tab._browserHistoryIdx = tab._browserHistory.length - 1;
  tab._browserUrl = url;
  _browserLoadUrl(url);
}

function navigateBrowser(url) {
  url = url.trim();
  if (!url) return;
  if (!url.startsWith('http://') && !url.startsWith('https://') && url !== 'about:blank' && url !== 'about:start') url = 'https://' + url;
  _browserNavigate(url);
}

function browserGoBack() {
  var curPath = state.activeTab;
  var tab = state.openTabs.find(function(t) { return t.path === curPath; });
  if (!tab || !tab._isBrowser) return;
  _browserTabState(tab);
  if (tab._browserHistoryIdx > 0) {
    tab._browserHistoryIdx--;
    var url = tab._browserHistory[tab._browserHistoryIdx];
    tab._browserUrl = url;
    if (_isStartPage(url)) {
      var frame = document.getElementById('browserFrame');
      var input = document.getElementById('browserUrlInput');
      input.value = url;
      frame.setAttribute('data-url', url);
      frame.removeAttribute('src');
      _setFrameSandbox(frame, false);_renderStartPage().then(function(html) { frame.srcdoc = html; });
    } else {
      _browserLoadUrl(url);
    }
  }
}

function browserGoForward() {
  var curPath = state.activeTab;
  var tab = state.openTabs.find(function(t) { return t.path === curPath; });
  if (!tab || !tab._isBrowser) return;
  _browserTabState(tab);
  if (tab._browserHistoryIdx < tab._browserHistory.length - 1) {
    tab._browserHistoryIdx++;
    var url = tab._browserHistory[tab._browserHistoryIdx];
    tab._browserUrl = url;
    if (_isStartPage(url)) {
      var frame = document.getElementById('browserFrame');
      var input = document.getElementById('browserUrlInput');
      input.value = url;
      frame.setAttribute('data-url', url);
      frame.removeAttribute('src');
      _setFrameSandbox(frame, false);_renderStartPage().then(function(html) { frame.srcdoc = html; });
    } else {
      _browserLoadUrl(url);
    }
  }
}

async function _promptAddBm() {
  var name = await modalPrompt('书签名称:');
  if (!name) return;
  var url = await modalPrompt('书签 URL:');
  if (!url) return;
  var bms = _loadCustomBookmarks();
  bms.push({ name: name, url: url, icon: '🔖' });
  _saveCustomBookmarks(bms);
  var frame = document.getElementById('browserFrame');
  if (frame) _setFrameSandbox(frame, false);_renderStartPage().then(function(html) { frame.srcdoc = html; });
}

function _delCustomBm(idx) {
  var bms = _loadCustomBookmarks();
  bms.splice(idx, 1);
  _saveCustomBookmarks(bms);
  var frame = document.getElementById('browserFrame');
  if (frame) _setFrameSandbox(frame, false);_renderStartPage().then(function(html) { frame.srcdoc = html; });
}

function browserRefresh() {
  var curPath = state.activeTab;
  var tab = state.openTabs.find(function(t) { return t.path === curPath; });
  if (!tab || !tab._isBrowser) return;
  _browserTabState(tab);
  var url = tab._browserUrl;
  if (_isStartPage(url)) {
    var frame = document.getElementById('browserFrame');
    frame.removeAttribute('src');
    _setFrameSandbox(frame, false);_renderStartPage().then(function(html) { frame.srcdoc = html; });
  } else {
    _browserLoadUrl(url);
  }
}

init().catch(function(e) { showToast('初始化失败: ' + (e.message || '未知错误'), 'error'); });
