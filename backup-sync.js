#!/usr/bin/env node
// TS2 双向同步脚本：把工作区 /data 做成 git 仓库，定时与远程备份仓库双向同步。
//  - push：本地改动提交备份（防 Render 免费版丢数据）
//  - pull：远程改动拉回工作区（换设备/恢复用）
//  冲突策略：优先保留本地版本（-X ours），远程独有文件仍会合并进来。
//
// 环境变量：
//   BACKUP_GIT_URL        git 仓库地址（可内嵌 token，如 https://TOKEN@github.com/user/repo.git）
//   BACKUP_SOURCE         工作区目录（默认取 TS2_WORKSPACE，缺省 /data）
//   BACKUP_INTERVAL_MIN   间隔分钟（默认 10）
//   BACKUP_BRANCH         分支（默认 main）
//   GIT_NAME / GIT_EMAIL  commit 身份（默认 ts2-sync / sync@ts2.local）
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const REPO = process.env.BACKUP_GIT_URL || '';
const SOURCE = process.env.BACKUP_SOURCE || process.env.TS2_WORKSPACE || '/data';
const INTERVAL_MS = (parseInt(process.env.BACKUP_INTERVAL_MIN || '10', 10)) * 60 * 1000;
const BRANCH = process.env.BACKUP_BRANCH || 'main';
const GIT_NAME = process.env.GIT_NAME || 'ts2-sync';
const GIT_EMAIL = process.env.GIT_EMAIL || 'sync@ts2.local';

function run(cmd, cwd) {
  const r = spawnSync(cmd, { shell: true, cwd, encoding: 'utf8', timeout: 60000 });
  return { ok: r.status === 0, out: (r.stdout || '').trim(), err: (r.stderr || '').trim() };
}
function log(...a) { console.log(`[sync ${new Date().toISOString()}]`, ...a); }
function git(cwd, ...args) {
  return run(`git -c user.name="${GIT_NAME}" -c user.email="${GIT_EMAIL}" ${args.join(' ')}`, cwd);
}

function ensureRepo() {
  if (!REPO) { log('BACKUP_GIT_URL 未设置，仅本地记录，不推送'); return; }
  if (fs.existsSync(path.join(SOURCE, '.git'))) return;

  log(`初始化 ${SOURCE} 为 git 仓库 -> ${REPO}`);
  git(SOURCE, 'init', `-b "${BRANCH}"`);
  git(SOURCE, 'remote', 'add', 'origin', `"${REPO}"`);
  const ignorePath = path.join(SOURCE, '.gitignore');
  if (!fs.existsSync(ignorePath)) {
    fs.writeFileSync(ignorePath,
      '# TS2 sync auto-ignore\n__pycache__/\n*.pyc\n*.pyo\n.DS_Store\n*.log\nnode_modules/\n');
  }
  git(SOURCE, 'add', '-A');
  git(SOURCE, 'commit', '-m', '"init snapshot"');
  const p = run(`git push -u origin "${BRANCH}"`, SOURCE);
  if (!p.ok) log('首次推送失败（远程可能为空，已初始化）：', p.err);
}

function syncOnce() {
  ensureRepo();
  if (!fs.existsSync(path.join(SOURCE, '.git'))) {
    // 无远程，只做本地快照（对持久卷有意义）
    git(SOURCE, 'add', '-A');
    const st = run('git status --porcelain', SOURCE);
    if (st.out) { git(SOURCE, 'commit', '-m', `"snapshot ${new Date().toISOString()}"`); log('本地快照已提交'); }
    else log('无变更');
    return;
  }

  // 1) pull：把远程改动合并回来（冲突优先本地）
  const pull = run(`git pull -s recursive -X ours origin "${BRANCH}"`, SOURCE);
  if (!pull.ok) log('pull 警告（保留本地）：', pull.err);
  else if (pull.out) log('pull 完成：', pull.out.split('\n')[0]);

  // 2) commit + push：把本地改动备份上去
  git(SOURCE, 'add', '-A');
  const st = run('git status --porcelain', SOURCE);
  if (!st.out) { log('无变更'); return; }
  const ts = new Date().toISOString().replace(/[T:]/g, '-').slice(0, 19);
  git(SOURCE, 'commit', '-m', `"sync ${ts}"`);
  const push = run(`git push origin "${BRANCH}"`, SOURCE);
  if (push.ok) log(`已同步 ${st.out.split('\n').length} 个文件变更`);
  else log('push 失败：', push.err);
}

log(`双向同步：${SOURCE} <-> ${REPO || '(无远程)'}，每 ${INTERVAL_MS / 60000} 分钟`);
syncOnce();
setInterval(syncOnce, INTERVAL_MS);
