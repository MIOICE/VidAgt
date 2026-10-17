<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import UploadDialog from '../components/UploadDialog.vue'
import TaskProgress from '../components/TaskProgress.vue'
import { videoApi, type Task, type Video } from '../api/client'
import { useVideoStore } from '../stores/videos'

const store = useVideoStore()
const router = useRouter()
const uploadOpen = ref(false)
const tasks = ref<Task[]>([])
const query = ref('')
let refreshTimer: number | undefined

const filtered = computed(() =>
  store.videos.filter((video) => video.title.toLowerCase().includes(query.value.toLowerCase())),
)
const readyCount = computed(() => store.videos.filter((video) => video.status === 'READY').length)
const durationTotal = computed(() =>
  store.videos.reduce((sum, video) => sum + (video.duration_ms || 0), 0),
)

function duration(ms?: number) {
  const seconds = Math.floor((ms || 0) / 1000)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

function size(bytes?: number) {
  if (!bytes) return '—'
  return bytes > 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(0)} MB`
}

function statusLabel(video: Video) {
  return { QUEUED: '等待中', PROCESSING: '解析中', READY: '已完成', FAILED: '失败' }[video.status]
}

async function remove(video: Video) {
  await ElMessageBox.confirm(`确定删除「${video.title}」及其全部分析结果吗？`, '删除视频', {
    type: 'warning',
    confirmButtonText: '删除',
  })
  await videoApi.remove(video.id)
  ElMessage.success('已删除')
  await store.refresh()
}

function submitted(task: Task) {
  tasks.value.unshift(task)
  store.refresh()
}

onMounted(async () => {
  await store.refresh()
  refreshTimer = window.setInterval(() => {
    if (store.videos.some((video) => ['QUEUED', 'PROCESSING'].includes(video.status))) {
      store.refresh()
    }
  }, 3000)
})
onBeforeUnmount(() => window.clearInterval(refreshTimer))
</script>

<template>
  <section class="page home-page">
    <div class="hero-row">
      <div>
        <p class="eyebrow">VIDEO KNOWLEDGE WORKSPACE</p>
        <h1>让长视频变成<br /><em>可检索的知识。</em></h1>
        <p class="hero-copy">上传视频，自动生成带时间戳证据的报告，并围绕内容连续追问。</p>
      </div>
      <button class="primary-action" @click="uploadOpen = true"><span>＋</span> 添加视频</button>
    </div>

    <div class="stats-grid">
      <article><small>视频总数</small><strong>{{ store.videos.length }}</strong><span>VIDEOS</span></article>
      <article><small>已解析</small><strong>{{ readyCount }}</strong><span>READY</span></article>
      <article><small>内容时长</small><strong>{{ duration(durationTotal) }}</strong><span>CONTEXT</span></article>
    </div>

    <div v-if="tasks.length" class="active-tasks panel">
      <div class="section-title"><div><small>PROCESSING</small><h2>进行中的任务</h2></div></div>
      <TaskProgress
        v-for="task in tasks"
        :key="task.id"
        :task="task"
        @done="store.refresh()"
      />
    </div>

    <div class="library-head">
      <div class="section-title"><small>LIBRARY</small><h2>视频资料库</h2></div>
      <el-input v-model="query" clearable placeholder="搜索视频…" class="search-input" />
    </div>

    <div v-if="filtered.length" class="video-grid" v-loading="store.loading">
      <article v-for="video in filtered" :key="video.id" class="video-card" @click="router.push(`/videos/${video.id}`)">
        <div class="video-card__cover">
          <span class="source-badge">{{ video.source_type === 'URL' ? 'LINK' : 'UPLOAD' }}</span>
          <div class="play-mark">▶</div>
          <span class="duration-badge">{{ duration(video.duration_ms) }}</span>
        </div>
        <div class="video-card__body">
          <div class="status-line" :data-status="video.status"><i /> {{ statusLabel(video) }}</div>
          <h3>{{ video.title }}</h3>
          <div class="video-meta"><span>{{ size(video.size_bytes) }}</span><span>{{ new Date(video.created_at).toLocaleDateString() }}</span></div>
          <p v-if="video.error" class="error-text">{{ video.error }}</p>
        </div>
        <button class="card-delete" title="删除" @click.stop="remove(video)">×</button>
      </article>
    </div>
    <div v-else class="empty-state">
      <div>◫</div><h3>还没有视频</h3><p>添加第一个视频，建立你的可检索内容库。</p>
    </div>
    <UploadDialog v-model="uploadOpen" @submitted="submitted" />
  </section>
</template>
