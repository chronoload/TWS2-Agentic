import { createRouter, createWebHistory, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/files',
  },
  {
    path: '/files',
    name: 'files',
    component: () => import('./views/FilesView.vue'),
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('./views/TasksView.vue'),
  },
  {
    path: '/bookmarks',
    name: 'bookmarks',
    component: () => import('./views/BookmarksView.vue'),
  },
  {
    path: '/projects',
    name: 'projects',
    component: () => import('./views/ProjectsView.vue'),
  },
  {
    path: '/courses',
    name: 'courses',
    component: () => import('./views/CoursesView.vue'),
  },
  {
    path: '/timetable',
    name: 'timetable',
    component: () => import('./views/TimetableView.vue'),
  },
  {
    path: '/execution',
    name: 'execution',
    component: () => import('./views/ExecutionView.vue'),
  },
  {
    path: '/slides',
    name: 'slides',
    component: () => import('./views/SlidesView.vue'),
  },
  {
    path: '/agent',
    name: 'agent',
    component: () => import('./views/AgentView.vue'),
  },
  {
    path: '/stats',
    name: 'stats',
    component: () => import('./views/StatsView.vue'),
  },
  {
    path: '/resources',
    name: 'resources',
    component: () => import('./views/ResourcesView.vue'),
  },
  {
    path: '/pdf/:path(.*)',
    name: 'pdf-reader',
    component: () => import('./views/PdfReaderView.vue'),
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('./views/SettingsView.vue'),
  },
  {
    path: '/ecosystem',
    name: 'ecosystem',
    component: () => import('./views/EcosystemView.vue'),
  },
  {
    path: '/game',
    name: 'game',
    component: () => import('./views/GameView.vue'),
  },
  {
    path: '/videos',
    name: 'videos',
    component: () => import('./views/VideoView.vue'),
  },
  {
    path: '/videos/channel',
    name: 'channel',
    component: () => import('./views/ChannelView.vue'),
  },
  {
    path: '/video-player',
    name: 'video-player',
    component: () => import('./views/VideoPlayerView.vue'),
  },
  {
    path: '/videos/playlists',
    name: 'playlists',
    component: () => import('./views/FavoritesView.vue'),
  },
  {
    path: '/editor/:path(.*)',
    name: 'editor',
    component: () => import('./views/EditorView.vue'),
  },
]

// Capacitor 原生环境必须用 hash 模式（file:// 协议或 window.Capacitor 存在）
const isNative = typeof window !== 'undefined' && (window.location.protocol === 'file:' || !!(window as any).Capacitor)

const router = createRouter({
  history: isNative ? createWebHashHistory() : createWebHistory('/app/'),
  routes,
})

// 鉴权由 App.vue 的连接流程统一处理，路由层不做拦截
// 后端 check_auth middleware 会在无凭证时返回 401，
// 由 api.ts 的响应拦截器触发 setAuthErrorCallback 处理

export default router
