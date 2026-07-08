<template>
  <div class="view">
    <header class="view-header">
      <h1>设置</h1>
    </header>
    <div class="view-body">
      <!-- 外观设置 (unified with video settings) -->
      <div class="settings-section">
        <h2 class="section-title">🎨 外观</h2>
        <div class="setting-row">
          <label class="setting-label">主题</label>
          <select class="setting-select" :value="themeMode" @change="onThemeChange">
            <option value="dark">深色</option>
            <option value="light">浅色</option>
            <option value="black">纯黑（AMOLED）</option>
            <option value="auto">跟随系统</option>
          </select>
        </div>
      </div>

      <!-- 网络访问控制（仅浏览器端/服务器端显示，参考思源笔记） -->
      <div class="settings-section" v-if="!isNative">
        <h2 class="section-title">网络访问控制</h2>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">允许局域网访问</label>
              <span class="setting-desc">允许同一局域网内的设备访问服务器</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="netSettings.allow_lan" @change="saveNetSettings" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">允许公用网络访问</label>
              <span class="setting-desc">允许公用网络（如校园网、公共WiFi）的设备访问</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="netSettings.allow_public_network" @change="saveNetSettings" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">允许 USB 连接</label>
              <span class="setting-desc">允许通过 adb reverse 的 USB 连接访问</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="netSettings.allow_usb" @change="saveNetSettings" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <label class="setting-label">监听地址</label>
          <span class="setting-value mono">{{ netSettings.effective_host }}:{{ netSettings.port }}</span>
          <span class="setting-hint" v-if="!netSettings.allow_lan && !netSettings.allow_public_network">
            仅本机可访问（127.0.0.1）
          </span>
        </div>

        <div class="btn-group">
          <button class="btn-action" @click="doConfigureFirewall" :disabled="firewallLoading">
            {{ firewallLoading ? '配置中...' : '配置防火墙' }}
          </button>
          <button class="btn-action btn-secondary" @click="doSetNetworkPrivate" :disabled="privateLoading" v-if="netSettings.platform === 'Windows'">
            {{ privateLoading ? '设置中...' : '设为专用网络' }}
          </button>
          <button class="btn-action btn-outline" @click="doCheckNetworkAccess" :disabled="checkLoading">
            {{ checkLoading ? '检测中...' : '检测网络状态' }}
          </button>
        </div>

        <div v-if="firewallMsg" class="msg-box" :class="firewallOk ? 'msg-ok' : 'msg-err'">
          {{ firewallMsg }}
        </div>
        <div v-if="privateMsg" class="msg-box" :class="privateOk ? 'msg-ok' : 'msg-err'">
          {{ privateMsg }}
        </div>

        <!-- 网络检测结果 -->
        <div v-if="networkCheck" class="check-result">
          <div class="check-item">
            <span>本机访问</span>
            <span :class="networkCheck.localhost_accessible ? 'tag-ok' : 'tag-fail'">
              {{ networkCheck.localhost_accessible ? '正常' : '不可用' }}
            </span>
          </div>
          <div class="check-item">
            <span>局域网访问</span>
            <span :class="networkCheck.lan_accessible ? 'tag-ok' : 'tag-fail'">
              {{ networkCheck.lan_accessible ? '正常' : '不可用' }}
            </span>
          </div>
          <div class="check-item">
            <span>防火墙规则</span>
            <span :class="networkCheck.firewall_rule_exists ? 'tag-ok' : 'tag-fail'">
              {{ networkCheck.firewall_rule_exists ? '已配置' : '未配置' }}
            </span>
          </div>
          <div v-for="(iface, idx) in networkCheck.interfaces" :key="idx" class="check-item">
            <span>{{ iface.ip }}</span>
            <span :class="iface.accessible ? 'tag-ok' : 'tag-fail'">
              {{ iface.accessible ? '可达' : '不可达' }}
            </span>
          </div>
          <div v-for="profile in networkCheck.profiles" :key="profile.name" class="check-item">
            <span>{{ profile.name }}</span>
            <span :class="profile.category === 'Private' ? 'tag-ok' : 'tag-warn'">
              {{ profile.category === 'Private' ? '专用网络' : '公用网络' }}
            </span>
          </div>
          <div v-if="networkCheck.recommendations.length > 0" class="recommendations">
            <div v-for="(rec, idx) in networkCheck.recommendations" :key="idx" class="rec-item">
              {{ rec }}
            </div>
          </div>
        </div>
      </div>

      <!-- 公网穿透（frp） -->
      <div class="settings-section">
        <h2 class="section-title">🌐 公网穿透</h2>
        <p class="section-desc" style="font-size:12px;color:#888;margin:-8px 0 8px">
          通过隧道将本服务暴露到公网，适用于与手机不在同一局域网时访问
        </p>

        <!-- 隧道类型 -->
        <div class="setting-row">
          <label class="setting-label">隧道类型</label>
          <div class="tunnel-type-tabs">
            <button
              v-for="t in [{v:'localtunnel',l:'localtunnel (推荐)'},{v:'serveo',l:'serveo.net'},{v:'bore',l:'bore.pub'},{v:'frp',l:'frp (需VPS)'},{v:'cloudflare',l:'Cloudflare'}]"
              :key="t.v"
              :class="['tab-btn', tunnelSettings.tunnel_type === t.v ? 'active' : '']"
              @click="setTunnelType(t.v)"
            >{{ t.l }}</button>
          </div>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'localtunnel'">
            使用 npx localtunnel，访问 https://xxx.loca.lt（推荐，最稳定）
          </span>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'serveo'">
            用 SSH 连接到 serveo.net，可能被校园网封锁
          </span>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'bore'">
            需要下载 bore 可执行文件，无需 VPS
          </span>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'frp'">
            需要自建 VPS，配置最灵活
          </span>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'cloudflare'">
            使用 cloudflared，需 Cloudflare 账号，稳定且支持自定义域名
          </span>
        </div>

        <!-- 隧道状态 -->
        <div class="setting-row" v-if="tunnelStatus">
          <span class="setting-label">状态</span>
          <span class="setting-value" :class="tunnelStatus.status === 'running' ? 'tag-ok' : tunnelStatus.status === 'error' ? 'tag-fail' : ''">
            {{ tunnelStatus.status === 'running' ? '已连接' : tunnelStatus.status === 'error' ? '错误' : tunnelStatus.status === 'starting' ? '启动中...' : '未启动' }}
          </span>
        </div>
        <div class="setting-row" v-if="tunnelStatus?.public_url">
          <span class="setting-label">公网地址</span>
          <a :href="tunnelStatus.public_url" target="_blank" class="setting-link mono">
            {{ tunnelStatus.public_url }}
          </a>
        </div>
        <div class="setting-row" v-if="tunnelStatus?.error">
          <span class="setting-label">错误</span>
          <span class="setting-value tag-fail" style="font-size:11px">{{ tunnelStatus.error }}</span>
        </div>

        <div class="btn-group">
          <button class="btn-action" @click="doTunnelStart" :disabled="tunnelLoading || tunnelStatus?.status === 'running'">
            {{ tunnelLoading ? '启动中...' : '启动隧道' }}
          </button>
          <button class="btn-action btn-secondary" @click="doTunnelStop" :disabled="tunnelLoading || tunnelStatus?.status === 'stopped'">
            停止隧道
          </button>
          <button class="btn-action btn-outline" @click="loadTunnelStatus">
            刷新状态
          </button>
        </div>

        <!-- frp 配置（仅 frp 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'frp'">
          <h3 class="config-title">frps 服务器配置</h3>
          <div class="setting-row">
            <label class="setting-label">服务器地址</label>
            <input v-model="tunnelSettings.server_addr" class="setting-input" placeholder="VPS 公网 IP" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">服务器端口</label>
            <input v-model.number="tunnelSettings.server_port" class="setting-input" type="number" placeholder="7000" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">认证令牌</label>
            <input v-model="tunnelSettings.token" class="setting-input" type="password" placeholder="frps token" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">本地端口</label>
            <input v-model.number="tunnelSettings.local_port" class="setting-input" type="number" placeholder="6906" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">远程端口</label>
            <input v-model.number="tunnelSettings.remote_port" class="setting-input" type="number" placeholder="6906" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">frpc 路径</label>
            <input v-model="tunnelSettings.frpc_path" class="setting-input" placeholder="留空自动查找" @change="saveTunnelSettings" />
          </div>
          <div v-if="tunnelSettings.token_preview" class="setting-row">
            <span class="setting-label">令牌预览</span>
            <span class="setting-value mono" style="font-size:11px;color:#888">{{ tunnelSettings.token_preview }}</span>
          </div>
        </div>

        <!-- bore 配置（仅 bore 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'bore'">
          <h3 class="config-title">bore 配置</h3>
          <div class="setting-row">
            <label class="setting-label">本地端口</label>
            <input v-model.number="tunnelSettings.local_port" class="setting-input" type="number" placeholder="6906" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">bore 路径</label>
            <input v-model="tunnelSettings.bore_path" class="setting-input" placeholder="留空自动查找" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <a href="https://github.com/ekzhang/bore/releases" target="_blank" class="setting-link">
              下载 bore (Windows: bore.exe)
            </a>
          </div>
        </div>

        <!-- serveo 配置（仅 serveo 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'serveo'">
          <h3 class="config-title">serveo 配置</h3>
          <div class="setting-row">
            <label class="setting-label">本地端口</label>
            <input v-model.number="tunnelSettings.local_port" class="setting-input" type="number" placeholder="6906" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">子域名（可选）</label>
            <input v-model="tunnelSettings.subdomain" class="setting-input" placeholder="留空则随机分配" @change="saveTunnelSettings" />
          </div>
        </div>

        <!-- localtunnel 配置（仅 localtunnel 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'localtunnel'">
          <h3 class="config-title">localtunnel 配置</h3>
          <div class="setting-row">
            <label class="setting-label">选择本地实例</label>
            <div class="setting-input-row">
              <select v-model.number="tunnelSettings.local_port" class="setting-select" @change="saveTunnelSettings">
                <option v-for="inst in localInstances" :key="inst.port" :value="inst.port">
                  端口 {{ inst.port }}{{ inst.self ? ' (当前实例)' : '' }}{{ inst.workspace ? ' - ' + (inst.workspace.split(/[/\\]/).pop() || '') : '' }}
                </option>
              </select>
              <button class="btn-refresh" @click="scanLocalInstances" :disabled="scanningInstances" title="刷新实例列表">
                {{ scanningInstances ? '...' : '↻' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Cloudflare 配置（仅 cloudflare 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'cloudflare'">
          <h3 class="config-title">Cloudflare Tunnel 配置</h3>
          <div class="setting-row">
            <label class="setting-label">Tunnel Token</label>
            <input v-model="tunnelSettings.cf_token" class="setting-input" type="password" placeholder="eyJh..." @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">域名（可选）</label>
            <input v-model="tunnelSettings.cf_domain" class="setting-input" placeholder="ts2.your-domain.com" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">本地端口</label>
            <div class="setting-input-row">
              <select v-model.number="tunnelSettings.local_port" class="setting-select" @change="saveTunnelSettings">
                <option v-for="inst in localInstances" :key="inst.port" :value="inst.port">
                  端口 {{ inst.port }}{{ inst.self ? ' (当前实例)' : '' }}{{ inst.workspace ? ' - ' + (inst.workspace.split(/[/\\]/).pop() || '') : '' }}
                </option>
              </select>
              <button class="btn-refresh" @click="scanLocalInstances" :disabled="scanningInstances" title="刷新实例列表">
                {{ scanningInstances ? '...' : '↻' }}
              </button>
            </div>
          </div>
          <div class="setting-row">
            <a href="https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/" target="_blank" class="setting-link">
              查看 Cloudflare Tunnel 配置指南
            </a>
          </div>
          <div class="setting-hint" style="margin-top:4px">
            安装 cloudflared: Windows: winget install Cloudflare.cloudflared
          </div>
        </div>

        <div v-if="tunnelMsg" class="msg-box" :class="tunnelMsgType === 'ok' ? 'msg-ok' : 'msg-err'">
          {{ tunnelMsg }}
        </div>
      </div>

      <!-- 数据同步 -->
      <div class="settings-section">
        <h2 class="section-title">🔄 数据同步</h2>
        <p class="section-desc" style="font-size:12px;color:#888;margin:-8px 0 8px">
          将本地任务与书签数据同步到服务器
        </p>

        <div class="setting-row">
          <span class="setting-label">上次同步</span>
          <span class="setting-value">{{ lastSyncTimeText }}</span>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">自动同步</label>
              <span class="setting-desc">每 5 分钟自动同步一次</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="autoSync" @change="toggleAutoSync" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="btn-group">
          <button class="btn-action" @click="doSync" :disabled="syncing">
            {{ syncing ? '同步中...' : '立即同步' }}
          </button>
        </div>

        <div v-if="syncResult" class="sync-result">
          <div class="check-item">
            <span>拉取任务</span>
            <span class="tag-ok">{{ syncResult.pull }} 条</span>
          </div>
          <div class="check-item">
            <span>推送任务</span>
            <span class="tag-ok">{{ syncResult.pushed }} 条</span>
          </div>
          <div class="check-item">
            <span>冲突</span>
            <span :class="syncResult.conflicts > 0 ? 'tag-warn' : 'tag-ok'">{{ syncResult.conflicts }} 条</span>
          </div>
          <div class="check-item">
            <span>拉取书签</span>
            <span class="tag-ok">{{ syncResult.bookmarksPull }} 条</span>
          </div>
          <div class="check-item">
            <span>推送书签</span>
            <span class="tag-ok">{{ syncResult.bookmarksPushed }} 条</span>
          </div>
          <div class="check-item">
            <span>拉取项目</span>
            <span class="tag-ok">{{ syncResult.projectsPull }} 条</span>
          </div>
          <div class="check-item">
            <span>推送项目</span>
            <span class="tag-ok">{{ syncResult.projectsPushed }} 条</span>
          </div>
        </div>

        <div v-if="syncMsg" class="msg-box" :class="syncOk ? 'msg-ok' : 'msg-err'">
          {{ syncMsg }}
        </div>
      </div>

      <!-- 关键路径检测 -->
      <div class="settings-section">
        <h2 class="section-title">📊 关键路径检测</h2>
        <p class="section-desc" style="font-size:12px;color:#888;margin:-8px 0 8px">
          基于任务依赖关系和持续时间，计算项目关键路径（CPM）
        </p>

        <div class="btn-group">
          <button class="btn-action" @click="doCriticalPath" :disabled="cpLoading">
            {{ cpLoading ? '分析中...' : '分析关键路径' }}
          </button>
        </div>

        <div v-if="cpResult" class="sync-result" style="margin-top:12px">
          <div class="check-item">
            <span>项目总工期</span>
            <span class="tag-ok">{{ formatDuration(cpResult.project_duration) }}</span>
          </div>
          <div class="check-item">
            <span>总任务数</span>
            <span class="setting-value">{{ cpResult.total_tasks }}</span>
          </div>
          <div class="check-item">
            <span>关键任务数</span>
            <span :class="cpResult.critical_tasks > 0 ? 'tag-warn' : 'tag-ok'">{{ cpResult.critical_tasks }}</span>
          </div>
        </div>

        <div v-if="cpResult?.critical_path?.length" style="margin-top:8px">
          <div style="font-size:12px;color:var(--fg-muted);margin-bottom:6px">关键路径任务</div>
          <div v-for="task in cpResult.critical_path" :key="task.id" class="cp-task-item">
            <span class="cp-task-title">{{ task.title }}</span>
            <span class="cp-task-duration">{{ formatDuration(task.duration) }}</span>
            <span class="cp-task-float">裕度: {{ task.total_float }}分钟</span>
          </div>
        </div>

        <div v-if="cpMsg" class="msg-box" :class="cpOk ? 'msg-ok' : 'msg-err'">
          {{ cpMsg }}
        </div>
      </div>

      <!-- 自动补全 -->
      <div class="settings-section">
        <h2 class="section-title">✏️ 编辑器自动补全</h2>
        <p class="section-desc" style="font-size:12px;color:#888;margin:-8px 0 8px">
          在 Vditor 编辑器中输入触发字符弹出补全列表（需重新打开文件生效）
        </p>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">LaTeX 公式补全</label>
              <span class="setting-desc">输入 \ 触发，补全 LaTeX 命令</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="acConfig.latex" @change="saveAcConfig" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">代码片段补全</label>
              <span class="setting-desc">输入 ! 触发，补全表格、代码块等模板</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="acConfig.snippets" @change="saveAcConfig" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">关键词字典补全</label>
              <span class="setting-desc">输入 @ 触发中文，& 触发英文</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="acConfig.dicts" @change="saveAcConfig" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <!-- 字典管理 -->
        <div v-if="acConfig.dicts" class="config-block" style="margin-top:12px">
          <h3 class="config-title">关键词字典</h3>

          <div v-for="(group, gIdx) in acConfig.dictGroups" :key="gIdx" class="dict-group">
            <div class="dict-group-header">
              <label class="toggle" style="transform:scale(0.8)">
                <input type="checkbox" :checked="group.enabled" @change="toggleDictGroup(gIdx)" />
                <span class="toggle-slider"></span>
              </label>
              <span class="dict-group-name" :class="{ disabled: !group.enabled }">{{ group.name }}</span>
              <span class="dict-group-count">{{ group.entries.length }} 条</span>
              <button class="btn-dict-toggle" @click="acEditingDict = acEditingDict === gIdx ? null : gIdx">
                {{ acEditingDict === gIdx ? '收起' : '编辑' }}
              </button>
              <button class="btn-dict-del" @click="removeDict(gIdx)" title="删除字典">✕</button>
            </div>

            <!-- 展开编辑词条 -->
            <div v-if="acEditingDict === gIdx" class="dict-entries">
              <div v-for="(entry, eIdx) in group.entries" :key="eIdx" class="dict-entry-row">
                <span class="dict-entry-key">{{ entry.keyword }}</span>
                <span class="dict-entry-val">{{ entry.value }}</span>
                <span v-if="entry.desc" class="dict-entry-desc">{{ entry.desc }}</span>
                <button class="btn-dict-entry-del" @click="removeDictEntry(gIdx, eIdx)">✕</button>
              </div>
              <div class="dict-add-entry">
                <input v-model="acNewEntryKeyword" class="setting-input dict-input" placeholder="关键词" />
                <input v-model="acNewEntryValue" class="setting-input dict-input" placeholder="补全值" />
                <input v-model="acNewEntryDesc" class="setting-input dict-input dict-input-desc" placeholder="说明(可选)" />
                <button class="btn-action" style="padding:6px 10px;font-size:11px" @click="addDictEntry(gIdx)">添加</button>
              </div>
            </div>
          </div>

          <!-- 添加自定义字典 -->
          <div class="dict-add-group">
            <input v-model="acNewDictName" class="setting-input dict-input" placeholder="新字典名称（如：计算机名词）" @keyup.enter="addCustomDict" />
            <button class="btn-action" style="padding:6px 10px;font-size:11px" @click="addCustomDict">添加字典</button>
          </div>

          <button class="btn-action btn-outline" style="margin-top:8px;font-size:11px;padding:4px 10px" @click="resetDictsToDefault">
            恢复默认字典
          </button>
        </div>
      </div>

      <!-- 服务器连接 -->
      <div class="settings-section">
        <h2 class="section-title">服务器连接</h2>
        <div class="setting-row">
          <span class="setting-label">状态</span>
          <span class="setting-value">
            <span v-if="appMode === 'local'" style="color:var(--fg-muted)">未连接（本地模式）</span>
            <span v-else-if="appMode === 'server_connected'" style="color:#4ade80">已连接</span>
            <span v-else style="color:#ef4444">已断开</span>
          </span>
        </div>
        <div class="setting-row" v-if="appMode !== 'server_connected'">
          <span class="setting-label">服务器地址</span>
          <input v-model="srvUrl" class="setting-input" placeholder="http://192.168.x.x:6906" />
        </div>
        <div class="setting-row" v-if="showAuthFields">
          <span class="setting-label">{{ srvNeedToken ? 'Token' : '' }} {{ srvNeedCode ? '授权码' : '' }}</span>
          <input v-if="srvNeedToken" v-model="srvToken" class="setting-input" type="password" placeholder="API Token" />
          <input v-if="srvNeedCode" v-model="srvCode" class="setting-input" type="password" placeholder="授权码" />
        </div>
        <div class="btn-group">
          <button v-if="appMode !== 'server_connected'" class="btn-action" @click="doConnectServer" :disabled="srvConnecting">
            {{ srvConnecting ? '连接中...' : '连接服务器' }}
          </button>
          <button v-if="appMode === 'server_connected'" class="btn-action btn-danger" @click="doDisconnectServer">
            断开连接
          </button>
          <pre v-if="srvError" class="srv-error-box">{{ srvError }}</pre>
        </div>

        <!-- 地址历史 -->
        <div v-if="addressHistory.length > 0" class="address-list">
          <div class="list-header">
            <span>历史地址</span>
            <button class="btn-clear" @click="clearAllHistory">清空</button>
          </div>
          <div
            v-for="(item, idx) in addressHistory"
            :key="idx"
            class="address-item"
            :class="{ current: item.url === currentURL }"
            @click="switchTo(item.url)"
          >
            <div class="address-info">
              <span class="address-url">{{ item.url }}</span>
              <span class="address-meta">
                {{ formatTime(item.lastUsed) }}
                <span v-if="item.success" class="tag-ok">成功</span>
                <span v-else class="tag-fail">失败</span>
              </span>
            </div>
            <div class="address-actions">
              <span v-if="item.url === currentURL" class="tag-current">当前</span>
              <button class="btn-del" @click.stop="removeHistory(idx)">✕</button>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <h2 class="section-title">连接状态</h2>
        <div class="setting-row">
          <span class="setting-label">WebSocket</span>
          <span class="setting-value" :class="{ connected: wsConnected }">
            {{ wsConnected ? '已连接' : '未连接' }}
          </span>
        </div>
        <div class="setting-row">
          <span class="setting-label">同步状态</span>
          <span class="setting-value">{{ syncStatusText }}</span>
        </div>
        <div class="setting-row">
          <span class="setting-label">运行环境</span>
          <span class="setting-value">{{ isNative ? '原生 App' : '浏览器' }}</span>
        </div>
      </div>

      <!-- 调试日志区域（内嵌） -->
      <div class="settings-section debug-log-section">
        <div class="section-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>🐞 调试日志</span>
          <button class="btn-clear-log" @click="clearDebugLogs">清空</button>
        </div>
        <div class="debug-log-box" ref="debugBody">
          <div v-for="(log, idx) in debugLogs" :key="idx" class="debug-log-line">{{ log }}</div>
          <div v-if="debugLogs.length === 0" class="debug-log-empty">暂无日志</div>
        </div>
      </div>

      <div class="settings-section">
        <h2 class="section-title">🎬 视频设置</h2>
        <div class="video-settings-tabs">
          <button
            v-for="tab in videoSettingTabs"
            :key="tab.key"
            class="vs-tab"
            :class="{ active: activeVideoTab === tab.key }"
            @click="activeVideoTab = tab.key"
          >{{ tab.label }}</button>
        </div>
        <VideoSettingsSection :active-section="activeVideoTab" />
      </div>

      <div class="settings-section" v-if="serverInfo">
        <h2 class="section-title">服务器信息</h2>
        <div class="setting-row">
          <span class="setting-label">版本</span>
          <span class="setting-value">{{ serverInfo.version }}</span>
        </div>
        <div class="setting-row">
          <span class="setting-label">局域网 IP</span>
          <span class="setting-value">{{ serverInfo.local_ip }}</span>
        </div>
      </div>
    </div>
  </div>

</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useVideoSettingsStore } from '../stores/videoSettings'
import VideoSettingsSection from '../components/VideoSettingsSection.vue'
import {
  getServerURL, setServerURL, testServerConnection, isNativeApp,
  getNetworkSettings, setNetworkSettings, configureFirewall, setNetworkPrivate, checkNetworkAccess,
  getStats, getProjects, criticalPath,
  tunnelStatus as getTunnelStatusApi, tunnelStart, tunnelStop, tunnelSettingsGet, tunnelSettingsUpdate,
  clusterInstances,
  getAuthInfo, loginAuth, getAuthCode, getApiToken, setCredentials, diagnoseLogin,
} from '../api'
import { useWebSocket } from '../composables/useWebSocket'
import { useAppMode } from '../composables/useAppMode'
import { useTasksStore } from '../stores/tasks'
import { useTimetableStore } from '../stores/timetable'
import { loadAutocompleteConfig, saveAutocompleteConfig, DEFAULT_DICT_GROUPS } from '../autocomplete'
import type { AutocompleteConfig } from '../autocomplete'
import { debugLogs } from '../api'

const { appMode, setAppMode } = useAppMode()
const showDebug = ref(false)
const debugBody = ref<HTMLElement | null>(null)
const HISTORY_KEY = 'ts2_address_history'
const videoSettingsStore = useVideoSettingsStore()
const themeMode = computed(() => videoSettingsStore.settings.themeMode)

function clearDebugLogs() {
  debugLogs.length = 0
}

function onThemeChange(e: Event) {
  videoSettingsStore.update({ themeMode: (e.target as HTMLSelectElement).value as any })
}

interface HistoryEntry {
  url: string
  lastUsed: number
  success: boolean
}

const serverInfo = ref<any>(null)
const syncStatusText = ref('未知')
const isNative = ref(false)
const addressHistory = ref<HistoryEntry[]>([])
const activeVideoTab = ref('appearance')

// 服务器连接状态
const currentURL = ref(getServerURL())
const srvUrl = ref(getServerURL())
const srvToken = ref('')
const srvCode = ref('')
const srvConnecting = ref(false)
const srvError = ref('')
const srvNeedToken = ref(false)
const srvNeedCode = ref(false)

const showAuthFields = computed(() => {
  return appMode.value !== 'server_connected' && (srvNeedToken.value || srvNeedCode.value)
})
const videoSettingTabs = [
  { key: 'appearance', label: '外观' },
  { key: 'playback', label: '播放' },
  { key: 'content', label: '内容' },
  { key: 'history', label: '历史' },
  { key: 'about', label: '关于' },
]

// 网络设置状态
const netSettings = ref({
  allow_lan: true,
  allow_public_network: true,
  allow_usb: true,
  effective_host: '0.0.0.0',
  port: 6906,
  platform: '',
  firewall_configured: false,
})
const firewallLoading = ref(false)
const firewallMsg = ref('')
const firewallOk = ref(false)
const privateLoading = ref(false)
const privateMsg = ref('')
const privateOk = ref(false)
const checkLoading = ref(false)
const networkCheck = ref<any>(null)

// 隧道状态
const tunnelStatus = ref<any>(null)
const tunnelSettings = ref({
  tunnel_type: 'localtunnel',
  server_addr: '',
  server_port: 7000,
  token: '',
  local_port: 6906,
  remote_port: 6906,
  subdomain: '',
  frpc_path: '',
  bore_path: '',
  cf_token: '',
  cf_domain: '',
  token_preview: '',
})
const tunnelLoading = ref(false)
const tunnelMsg = ref('')
const tunnelMsgType = ref<'ok' | 'err'>('ok')

// 本地实例（用于端口选择）
interface LocalInstance {
  port: number
  url: string
  version: string
  local_ip: string
  self?: boolean
  workspace?: string
}
const localInstances = ref<LocalInstance[]>([])
const scanningInstances = ref(false)

const { wsConnected } = useWebSocket()
const timetableStore = useTimetableStore()

// ─── 数据同步 ────────────────────────────────────────
const tasksStore = useTasksStore()
const syncing = ref(false)
const syncResult = ref<{ pull: number; pushed: number; conflicts: number; bookmarksPull: number; bookmarksPushed: number; projectsPull: number; projectsPushed: number } | null>(null)
const syncMsg = ref('')
const syncOk = ref(false)
const lastSyncTime = ref<number | null>(null)
const autoSync = ref(false)
let autoSyncTimer: ReturnType<typeof setInterval> | null = null

// ─── 自动补全 ────────────────────────────────────────
const acConfig = ref<AutocompleteConfig>(loadAutocompleteConfig())
const acNewDictName = ref('')
const acNewEntryKeyword = ref('')
const acNewEntryValue = ref('')
const acNewEntryDesc = ref('')
const acEditingDict = ref<number | null>(null)  // 正在编辑的字典索引

// ─── 关键路径检测 ────────────────────────────────────────
const cpLoading = ref(false)
const cpResult = ref<any>(null)
const cpMsg = ref('')
const cpOk = ref(false)

function formatDuration(minutes: number): string {
  if (!minutes) return '0分钟'
  if (minutes < 60) return `${minutes}分钟`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h < 24) return m > 0 ? `${h}小时${m}分钟` : `${h}小时`
  const d = Math.floor(h / 24)
  const rh = h % 24
  return rh > 0 ? `${d}天${rh}小时` : `${d}天`
}

async function doCriticalPath() {
  cpLoading.value = true
  cpMsg.value = ''
  cpResult.value = null
  try {
    const res = await criticalPath()
    const data = res.data?.data ?? res.data
    if (data) {
      cpResult.value = data
      cpOk.value = true
      cpMsg.value = data.critical_tasks > 0
        ? `检测到 ${data.critical_tasks} 个关键任务，总工期 ${formatDuration(data.project_duration)}`
        : '未检测到关键路径（可能所有任务已完成或无依赖关系）'
    }
  } catch (e: any) {
    cpOk.value = false
    cpMsg.value = e?.message || '关键路径分析失败'
  } finally {
    cpLoading.value = false
  }
}

function saveAcConfig() {
  saveAutocompleteConfig(acConfig.value)
}

function toggleDictGroup(idx: number) {
  acConfig.value.dictGroups[idx].enabled = !acConfig.value.dictGroups[idx].enabled
  saveAcConfig()
}

function addCustomDict() {
  const name = acNewDictName.value.trim()
  if (!name) return
  acConfig.value.dictGroups.push({ name, enabled: true, entries: [] })
  acNewDictName.value = ''
  saveAcConfig()
}

function removeDict(idx: number) {
  acConfig.value.dictGroups.splice(idx, 1)
  saveAcConfig()
}

function addDictEntry(dictIdx: number) {
  const keyword = acNewEntryKeyword.value.trim()
  const value = acNewEntryValue.value.trim()
  if (!keyword || !value) return
  acConfig.value.dictGroups[dictIdx].entries.push({
    keyword,
    value,
    desc: acNewEntryDesc.value.trim() || undefined,
  })
  acNewEntryKeyword.value = ''
  acNewEntryValue.value = ''
  acNewEntryDesc.value = ''
  saveAcConfig()
}

function removeDictEntry(dictIdx: number, entryIdx: number) {
  acConfig.value.dictGroups[dictIdx].entries.splice(entryIdx, 1)
  saveAcConfig()
}

function resetDictsToDefault() {
  acConfig.value.dictGroups = JSON.parse(JSON.stringify(DEFAULT_DICT_GROUPS))
  saveAcConfig()
}

const LAST_SYNC_KEY = 'ts2_last_sync_time'
const AUTO_SYNC_KEY = 'ts2_auto_sync'

const lastSyncTimeText = computed(() => {
  if (!lastSyncTime.value) return '从未同步'
  const d = new Date(lastSyncTime.value)
  const now = new Date()
  const diffMin = Math.floor((now.getTime() - d.getTime()) / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}小时前`
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
})

async function doSync() {
  syncing.value = true
  syncMsg.value = ''
  syncResult.value = null
  try {
    // 获取当前 projects 数据
    let projects: any[] = []
    try {
      const projRes = await getProjects()
      const projData = projRes.data?.data ?? projRes.data
      projects = Array.isArray(projData) ? projData : []
    } catch { /* ignore */ }
    const result = await tasksStore.syncWithServer([], projects)
    syncResult.value = result
    lastSyncTime.value = Date.now()
    localStorage.setItem(LAST_SYNC_KEY, String(lastSyncTime.value))
    syncOk.value = true
    syncMsg.value = '同步完成'
  } catch (e: any) {
    syncOk.value = false
    syncMsg.value = e?.message || '同步失败'
  } finally {
    syncing.value = false
  }
}

function toggleAutoSync() {
  if (autoSync.value) {
    autoSyncTimer = setInterval(() => {
      doSync()
    }, 5 * 60 * 1000)
    localStorage.setItem(AUTO_SYNC_KEY, '1')
  } else {
    if (autoSyncTimer) {
      clearInterval(autoSyncTimer)
      autoSyncTimer = null
    }
    localStorage.removeItem(AUTO_SYNC_KEY)
  }
}

function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveHistory(list: HistoryEntry[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, 10)))
}

function addHistory(url: string, success: boolean) {
  const list = loadHistory().filter(h => h.url !== url)
  list.unshift({ url, lastUsed: Date.now(), success })
  saveHistory(list)
  addressHistory.value = list
}

function removeHistory(idx: number) {
  const list = loadHistory()
  list.splice(idx, 1)
  saveHistory(list)
  addressHistory.value = list
}

function clearAllHistory() {
  localStorage.removeItem(HISTORY_KEY)
  addressHistory.value = []
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const diffMin = Math.floor((now.getTime() - d.getTime()) / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}小时前`
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function switchTo(url: string) {
  srvUrl.value = url
  await doConnectServer()
}

async function doConnectServer() {
  const url = srvUrl.value?.trim() || ''
  if (!url) { srvError.value = '请输入服务器地址'; return }
  srvConnecting.value = true
  srvError.value = ''
  try {
    const ok = await testServerConnection(url)
    if (!ok) { srvError.value = '无法连接服务器'; return }
    const info = await getAuthInfo(url)
    if (!info.needAuth) {
	setCredentials(srvCode.value.trim() || getAuthCode(), srvToken.value.trim() || getApiToken())
        setServerURL(url)
    	currentURL.value = url
    	addHistory(url, true)
    	setAppMode('server_connected')
    	await Promise.all([tasksStore.switchToServer(), timetableStore.switchToServer()])
    	return
    }
    srvNeedToken.value = info.hasToken
    srvNeedCode.value = info.hasAuthCode
    const code = srvCode.value.trim() || getAuthCode()
    const token = srvToken.value.trim() || getApiToken()
    if ((!info.hasAuthCode || code) && (!info.hasToken || token)) {
      const loginResult = await loginAuth(code, token, url)
      if (loginResult.ok) {
	setCredentials(srvCode.value.trim() || getAuthCode(), srvToken.value.trim() || getApiToken())
        setServerURL(url)
	currentURL.value = url
	addHistory(url, true)
	setAppMode('server_connected')
	await Promise.all([tasksStore.switchToServer(), timetableStore.switchToServer()])
	return
      }
      // 登录失败，构造详细错误信息
      let errorMsg = loginResult.detail || '登录失败'
      // 根据错误类型附加建议
      if (loginResult.errorType === 'network' || loginResult.errorType === 'cors') {
        errorMsg += '\n\n💡 建议：\n- 检查服务器是否在运行\n- 确认IP地址和端口正确\n- 如果是Capacitor环境，请确保服务器与设备在同一网络'
      } else if (loginResult.errorType === 'auth_failed') {
        errorMsg += '\n\n💡 请确认授权码和Token是否正确'
      } else if (loginResult.errorType === 'timeout') {
        errorMsg += '\n\n💡 请检查网络连接，或尝试增加超时时间'
      }
      srvError.value = errorMsg
      // 自动运行诊断附加信息（可选）
      try {
        const diag = await diagnoseLogin(code, token, url)
        srvError.value += '\n\n📋 诊断:\n' + diag.join('\n')
      } catch {}
      return
    }
  } catch (e: any) {
    srvError.value = `连接失败: ${e?.message || e}`
  } finally {
    srvConnecting.value = false
  }
}

// 网络设置操作
async function loadNetSettings() {
  try {
    const res = await getNetworkSettings()
    const data = res.data?.data ?? res.data
    if (data) {
      netSettings.value = {
        allow_lan: data.allow_lan ?? true,
        allow_public_network: data.allow_public_network ?? true,
        allow_usb: data.allow_usb ?? true,
        effective_host: data.host ?? '0.0.0.0',
        port: data.port ?? 6906,
        platform: data.platform ?? '',
        firewall_configured: data.firewall_configured ?? false,
      }
    }
  } catch { /* ignore */ }
}

async function scanLocalInstances() {
  scanningInstances.value = true
  try {
    const res = await clusterInstances()
    const data = res.data?.data ?? res.data
    if (data) {
      // 合并 self 和 peers
      const instances: LocalInstance[] = []
      if (data.self) {
        instances.push(data.self)
      }
      if (data.peers) {
        instances.push(...data.peers)
      }
      localInstances.value = instances.sort((a, b) => a.port - b.port)
      // 如果当前设置的端口不在列表中，添加它
      const currentPort = tunnelSettings.value.local_port
      if (currentPort && !instances.find(i => i.port === currentPort)) {
        localInstances.value.push({
          port: currentPort,
          url: `http://127.0.0.1:${currentPort}`,
          version: 'unknown',
          local_ip: '',
        })
        localInstances.value.sort((a, b) => a.port - b.port)
      }
    }
  } catch {
    localInstances.value = []
  } finally {
    scanningInstances.value = false
  }
}

async function saveNetSettings() {
  try {
    await setNetworkSettings({
      allow_lan: netSettings.value.allow_lan,
      allow_public_network: netSettings.value.allow_public_network,
      allow_usb: netSettings.value.allow_usb,
    })
    // 重新加载以获取更新后的 effective_host
    await loadNetSettings()
  } catch { /* ignore */ }
}

async function doConfigureFirewall() {
  firewallLoading.value = true
  firewallMsg.value = ''
  try {
    const res = await configureFirewall(true)
    const data = res.data?.data ?? res.data
    firewallOk.value = data?.success ?? res.data?.code === 0
    firewallMsg.value = data?.message || data?.msg || (firewallOk.value ? '防火墙配置成功' : '防火墙配置失败')
  } catch (e: any) {
    firewallOk.value = false
    firewallMsg.value = e?.response?.data?.message || '防火墙配置请求失败'
  } finally {
    firewallLoading.value = false
  }
}

async function doSetNetworkPrivate() {
  privateLoading.value = true
  privateMsg.value = ''
  try {
    const res = await setNetworkPrivate()
    const data = res.data?.data ?? res.data
    privateOk.value = data?.success ?? res.data?.code === 0
    privateMsg.value = data?.message || data?.msg || (privateOk.value ? '已设为专用网络' : '设置失败')
  } catch (e: any) {
    privateOk.value = false
    privateMsg.value = e?.response?.data?.message || '设置请求失败'
  } finally {
    privateLoading.value = false
  }
}

async function doCheckNetworkAccess() {
  checkLoading.value = true
  try {
    const res = await checkNetworkAccess()
    const data = res.data?.data ?? res.data
    networkCheck.value = data
  } catch {
    networkCheck.value = null
  } finally {
    checkLoading.value = false
  }
}

// ─── 隧道操作 ────────────────────────────────────────

async function loadTunnelStatus() {
  try {
    const res = await getTunnelStatusApi()
    tunnelStatus.value = res.data?.data ?? res.data
  } catch {
    tunnelStatus.value = null
  }
}

async function loadTunnelSettings() {
  try {
    const res = await tunnelSettingsGet()
    const data = res.data?.data ?? res.data
    if (data) {
      tunnelSettings.value = {
        tunnel_type: data.tunnel_type || 'localtunnel',
        server_addr: data.server_addr || '',
        server_port: data.server_port || 7000,
        token: data.token || '',
        local_port: data.local_port || 6906,
        remote_port: data.remote_port || 6906,
        subdomain: data.subdomain || '',
        frpc_path: data.frpc_path || '',
        bore_path: data.bore_path || '',
        cf_token: data.cf_token || '',
        cf_domain: data.cf_domain || '',
        token_preview: data.token_preview || '',
      }
    }
  } catch { /* ignore */ }
}

async function setTunnelType(type: string) {
  tunnelSettings.value.tunnel_type = type
  await saveTunnelSettings()
}

async function saveTunnelSettings() {
  try {
    const res = await tunnelSettingsUpdate({
      tunnel_type: tunnelSettings.value.tunnel_type,
      server_addr: tunnelSettings.value.server_addr,
      server_port: tunnelSettings.value.server_port,
      token: tunnelSettings.value.token,
      local_port: tunnelSettings.value.local_port,
      remote_port: tunnelSettings.value.remote_port,
      subdomain: tunnelSettings.value.subdomain,
      frpc_path: tunnelSettings.value.frpc_path,
      bore_path: tunnelSettings.value.bore_path,
    })
    const data = res.data?.data ?? res.data
    if (data?.token) {
      tunnelSettings.value.token_preview = data.token_preview || ''
      tunnelSettings.value.token = ''
    }
    tunnelMsg.value = '配置已保存'
    tunnelMsgType.value = 'ok'
  } catch (e: any) {
    tunnelMsg.value = e?.response?.data?.msg || '保存失败'
    tunnelMsgType.value = 'err'
  }
}

async function doTunnelStart() {
  tunnelLoading.value = true
  tunnelMsg.value = ''
  try {
    const res = await tunnelStart()
    const data = res.data?.data ?? res.data
    if (res.data?.code === 0 || data?.success) {
      tunnelMsg.value = data?.message || '隧道启动成功'
      tunnelMsgType.value = 'ok'
    } else {
      tunnelMsg.value = data?.message || '隧道启动失败'
      tunnelMsgType.value = 'err'
    }
    await loadTunnelStatus()
  } catch (e: any) {
    tunnelMsg.value = e?.response?.data?.msg || '启动失败'
    tunnelMsgType.value = 'err'
  } finally {
    tunnelLoading.value = false
  }
}

async function doTunnelStop() {
  tunnelLoading.value = true
  tunnelMsg.value = ''
  try {
    const res = await tunnelStop()
    const data = res.data?.data ?? res.data
    tunnelMsg.value = data?.message || '隧道已停止'
    tunnelMsgType.value = 'ok'
    await loadTunnelStatus()
  } catch (e: any) {
    tunnelMsg.value = e?.response?.data?.msg || '停止失败'
    tunnelMsgType.value = 'err'
  } finally {
    tunnelLoading.value = false
  }
}

onMounted(async () => {
  isNative.value = isNativeApp()
  addressHistory.value = loadHistory()
  // 恢复上次同步时间
  const savedSyncTime = localStorage.getItem(LAST_SYNC_KEY)
  if (savedSyncTime) lastSyncTime.value = Number(savedSyncTime)
  // 恢复自动同步状态
  if (localStorage.getItem(AUTO_SYNC_KEY) === '1') {
    autoSync.value = true
    toggleAutoSync()
  }
  // 浏览器端加载网络设置
  if (!isNative.value) {
    await loadNetSettings()
  }
  // 加载隧道状态、配置和本地实例
  await Promise.all([loadTunnelStatus(), loadTunnelSettings(), scanLocalInstances()])
  try {
    const res = await getStats()
    const data = res.data?.data ?? res.data
    if (data) {
      syncStatusText.value = '在线'
      serverInfo.value = data
    }
  } catch { /* ignore */ }
  // 调试面板自动滚动到最新
  window.addEventListener('ts2-debug-update', () => {
    nextTick(() => {
      if (debugBody.value) {
        debugBody.value.scrollTop = 0
      }
    })
  })
})

onUnmounted(() => {
  if (autoSyncTimer) {
    clearInterval(autoSyncTimer)
    autoSyncTimer = null
  }
})
</script>

<style scoped>
.settings-section {
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg-muted);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.setting-row {
  margin-bottom: 12px;
}

.setting-label {
  display: block;
  font-size: 13px;
  color: var(--fg);
  margin-bottom: 4px;
}

.setting-desc {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
}

.setting-hint {
  display: block;
  font-size: 11px;
  color: var(--danger);
  margin-top: 2px;
}

.setting-input-row {
  display: flex;
  gap: 8px;
}

.setting-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  font-family: monospace;
}

.setting-input:focus {
  outline: none;
  border-color: var(--accent);
}

.btn-test {
  padding: 8px 16px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.btn-test:disabled {
  opacity: 0.5;
}

.setting-select {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  font-family: monospace;
  cursor: pointer;
}

.setting-select:focus {
  outline: none;
  border-color: var(--accent);
}

.btn-refresh {
  padding: 8px 12px;
  background: var(--bg-secondary);
  color: var(--fg-muted);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  min-width: 36px;
}

.btn-refresh:hover {
  background: var(--bg);
  color: var(--fg);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.setting-status {
  font-size: 12px;
  margin-top: 4px;
  display: block;
}

.setting-status.success {
  color: #4ade80;
}

.srv-error-box {
  font-size: 12px;
  color: #ef4444;
  background: rgba(239,68,68,0.08);
  border: 1px solid rgba(239,68,68,0.2);
  border-radius: 6px;
  padding: 8px 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  margin-top: 8px;
  line-height: 1.5;
}

.setting-status.error {
  color: var(--danger);
}

.setting-input[type="password"] {
  font-family: monospace;
}

.setting-error {
  color: #ef4444;
  font-size: 12px;
}

.btn-danger {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 6px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.setting-value {
  font-size: 13px;
  color: var(--fg-muted);
}

.setting-value.connected {
  color: #4ade80;
}

.setting-value.mono {
  font-family: monospace;
}

/* Toggle 开关 */
.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.toggle {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--border);
  border-radius: 24px;
  transition: 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: 0.2s;
}

.toggle input:checked + .toggle-slider {
  background: var(--accent);
}

.toggle input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

/* 按钮组 */
.btn-group {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.btn-action {
  padding: 8px 14px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.btn-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: #6366f1;
}

.btn-outline {
  background: transparent;
  color: var(--accent);
  border: 1px solid var(--accent);
}

.btn-outline:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

/* 消息框 */
.msg-box {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.msg-ok {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

.msg-err {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

/* 网络检测结果 */
.check-result {
  margin-top: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
}

.check-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}

.check-item:last-child {
  border-bottom: none;
}

.tag-ok {
  color: #4ade80;
  font-size: 12px;
}

.tag-fail {
  color: #ef4444;
  font-size: 12px;
}

.tag-warn {
  color: #f59e0b;
  font-size: 12px;
}

.recommendations {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.rec-item {
  font-size: 12px;
  color: #f59e0b;
  padding: 3px 0;
  padding-left: 12px;
  position: relative;
}

.rec-item::before {
  content: '!';
  position: absolute;
  left: 0;
  font-weight: bold;
}

/* 地址历史列表 */
.address-list {
  margin-top: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  overflow: hidden;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--border);
}

.btn-clear {
  background: none;
  border: none;
  color: var(--danger);
  font-size: 12px;
  cursor: pointer;
}

.address-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.address-item:hover {
  background: var(--border);
}

.address-item.current {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

.address-info {
  flex: 1;
  min-width: 0;
}

.address-url {
  display: block;
  font-size: 13px;
  font-family: monospace;
  color: var(--fg);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.address-meta {
  display: flex;
  gap: 6px;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
  align-items: center;
}

.address-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tag-current {
  font-size: 10px;
  color: var(--accent);
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.15);
  padding: 2px 6px;
  border-radius: 4px;
}

.btn-del {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
}

.btn-del:hover {
  background: var(--danger);
  color: white;
}

/* 公网穿透设置 */
.setting-link {
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
}

.setting-link:hover {
  text-decoration: underline;
}

.config-block {
  margin-top: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
}

.config-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-muted);
  margin-bottom: 10px;
}

/* 隧道类型标签 */
.tunnel-type-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.tab-btn {
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--bg);
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.tab-btn:hover:not(.active) {
  border-color: var(--accent);
  color: var(--accent);
}

/* 数据同步结果 */
.sync-result {
  margin-top: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
}

/* 字典管理 */
.dict-group {
  margin-bottom: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.dict-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: var(--bg);
}

.dict-group-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.dict-group-name.disabled {
  color: var(--fg-muted);
  opacity: 0.6;
}

.dict-group-count {
  font-size: 11px;
  color: var(--fg-muted);
}

.btn-dict-toggle {
  background: none;
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-dict-toggle:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

.btn-dict-del {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
}

.btn-dict-del:hover {
  color: var(--danger);
}

.dict-entries {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
}

.dict-entry-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}

.dict-entry-row:last-child {
  border-bottom: none;
}

.dict-entry-key {
  color: var(--accent);
  min-width: 60px;
  font-weight: 500;
}

.dict-entry-val {
  flex: 1;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dict-entry-desc {
  color: var(--fg-muted);
  font-size: 11px;
}

.btn-dict-entry-del {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 11px;
  cursor: pointer;
  padding: 2px;
}

.btn-dict-entry-del:hover {
  color: var(--danger);
}

.dict-add-entry {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.dict-input {
  font-size: 12px !important;
  padding: 5px 8px !important;
  min-width: 80px;
}

.dict-input-desc {
  max-width: 120px;
}

.dict-add-group {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

/* 关键路径任务 */
.cp-task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-radius: 6px;
  margin-bottom: 4px;
  font-size: 12px;
}

.cp-task-title {
  flex: 1;
  color: var(--fg);
  font-weight: 500;
}

.cp-task-duration {
  color: var(--accent);
  font-size: 11px;
}

.cp-task-float {
  color: #f59e0b;
  font-size: 11px;
}

/* 视频设置 tabs */
.video-settings-tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
.vs-tab { padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; cursor: pointer; }
.vs-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }

/* 调试日志区域（内嵌） */
.debug-log-section {
  border-top: 1px solid var(--border);
  padding-top: 16px;
  margin-top: 8px;
}

.debug-log-box {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  max-height: 200px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 11px;
  color: var(--fg-muted);
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}

.debug-log-line {
  padding: 2px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.debug-log-empty {
  color: var(--fg-muted);
  text-align: center;
  padding: 12px 0;
  font-style: italic;
}

.btn-clear-log {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--fg-muted);
  padding: 2px 10px;
  font-size: 11px;
  cursor: pointer;
}

.btn-clear-log:hover {
  background: var(--bg-secondary);
  color: var(--fg);
}
</style>








