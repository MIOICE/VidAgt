<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  analysisApi,
  videoApi,
  type Analysis,
  type ChatMessage,
  type Segment,
  type Video,
} from '../api/client'

const route = useRoute()
const router = useRouter()
const videoId = String(route.params.id)
const video = ref<Video | null>(null)
const playbackUrl = ref('')
const segments = ref<Segment[]>([])
const analyses = ref<Analysis[]>([])
const activeAnalysisId = ref('')
const activeTab = ref('report')
const player = ref<HTMLVideoElement | null>(null)
const loading = ref(true)
const retryBusy = ref(false)
const customGoal = ref('')
const analysisBusy = ref(false)
const question = ref('')
const conversationStorageKey = `vidagt:conversation:${videoId}`
const conversationId = ref<string | undefined>(
  window.localStorage.getItem(conversationStorageKey) || undefined,
)
const chatBusy = ref(false)
const chatMessages = ref<ChatMessage[]>([])
const chatHistoryLoaded = ref(false)
let pollTimer: number | undefined

const activeAnalysis = computed(() =>
  analyses.value.find((item) => item.id === activeAnalysisId.value) || analyses.value[0],
)
const report = computed(() => activeAnalysis.value?.report || {})

function time(ms: number) {
  const total = Math.floor(ms / 1000)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':')
}

function jump(ms: number) {
  if (player.value) {
    player.value.currentTime = ms / 1000
    player.value.play().catch(() => undefined)
  }
}

async function load() {
  try {
    video.value = await videoApi.get(videoId)
    if (video.value.status === 'READY') {
      if (!playbackUrl.value) playbackUrl.value = (await videoApi.playback(videoId)).url
      segments.value = await videoApi.segments(videoId)
      analyses.value = await analysisApi.list(videoId)
      if (!activeAnalysisId.value && analyses.value.length) activeAnalysisId.value = analyses.value[0].id
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载视频失败')
  } finally {
    loading.value = false
  }
}

async function createAnalysis() {
  if (!customGoal.value.trim()) return
  analysisBusy.value = true
  try {
    const analysis = await analysisApi.create(videoId, customGoal.value.trim())
    analyses.value.unshift(analysis)
    activeAnalysisId.value = analysis.id
    customGoal.value = ''
    ElMessage.success('分析任务已提交')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '创建分析失败')
  } finally {
    analysisBusy.value = false
  }
}

async function retryProcessing() {
  retryBusy.value = true
  try {
    await videoApi.retry(videoId)
    ElMessage.success('已重新提交解析任务')
    await load()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '重新解析失败')
  } finally {
    retryBusy.value = false
  }
}

async function loadChatHistory() {
  if (chatHistoryLoaded.value) return
  try {
    const history = await analysisApi.chatHistory(videoId, conversationId.value)
    conversationId.value = history.conversation_id || undefined
    chatMessages.value = history.messages
    if (history.conversation_id) {
      window.localStorage.setItem(conversationStorageKey, history.conversation_id)
    }
  } catch (error: any) {
    if (error.response?.status === 404 && conversationId.value) {
      window.localStorage.removeItem(conversationStorageKey)
      conversationId.value = undefined
      const history = await analysisApi.chatHistory(videoId)
      conversationId.value = history.conversation_id || undefined
      chatMessages.value = history.messages
    } else {
      ElMessage.error(error.response?.data?.detail || '加载对话历史失败')
    }
  } finally {
    chatHistoryLoaded.value = true
  }
}

async function sendQuestion() {
  const content = question.value.trim()
  if (!content || chatBusy.value) return
  chatMessages.value.push({ role: 'user', content })
  question.value = ''
  chatBusy.value = true
  await nextTick()
  try {
    const response = await analysisApi.chat(videoId, content, conversationId.value)
    conversationId.value = response.conversation_id
    window.localStorage.setItem(conversationStorageKey, response.conversation_id)
    chatMessages.value.push({ role: 'assistant', content: response.answer, evidence: response.evidence })
  } catch (error: any) {
    chatMessages.value.push({
      role: 'assistant',
      content: `请求失败：${error.response?.data?.detail || error.message}`,
    })
  } finally {
    chatBusy.value = false
  }
}

onMounted(async () => {
  await load()
  if (video.value?.status === 'READY') await loadChatHistory()
  pollTimer = window.setInterval(() => {
    const unfinishedVideo = video.value && ['QUEUED', 'PROCESSING'].includes(video.value.status)
    const unfinishedAnalysis = analyses.value.some((item) => ['PENDING', 'RUNNING'].includes(item.status))
    if (unfinishedVideo || unfinishedAnalysis) {
      load().then(() => {
        if (video.value?.status === 'READY') loadChatHistory()
      })
    }
  }, 3000)
})
onBeforeUnmount(() => window.clearInterval(pollTimer))
</script>

<template>
  <section class="workspace" v-loading="loading">
    <div class="workspace-head">
      <button class="back-link" @click="router.push('/')">← 视频库</button>
      <div v-if="video">
        <h1>{{ video.title }}</h1>
        <p><span :data-status="video.status" class="status-line"><i /> {{ video.status }}</span></p>
      </div>
    </div>

    <div v-if="video" class="workspace-grid">
      <aside class="media-column">
        <div class="player-shell">
          <video v-if="playbackUrl" ref="player" :src="playbackUrl" controls preload="metadata" />
          <div v-else class="player-placeholder">
            <span>{{ video.status === 'FAILED' ? '!' : '◌' }}</span>
            <strong>{{ video.status === 'FAILED' ? '解析失败' : '视频正在解析' }}</strong>
            <small>{{ video.error || '完成后将在这里显示预览' }}</small>
            <el-button
              v-if="video.status === 'FAILED'"
              type="primary"
              :loading="retryBusy"
              @click="retryProcessing"
            >
              重新解析
            </el-button>
          </div>
        </div>
        <div class="media-facts panel">
          <div><small>时长</small><strong>{{ video.duration_ms ? time(video.duration_ms) : '—' }}</strong></div>
          <div><small>分段</small><strong>{{ segments.length }}</strong></div>
          <div><small>来源</small><strong>{{ video.source_type }}</strong></div>
        </div>
        <div class="custom-analysis panel">
          <p class="eyebrow">CUSTOM ANALYSIS</p>
          <h3>提出一个分析目标</h3>
          <el-input
            v-model="customGoal"
            type="textarea"
            :rows="4"
            placeholder="例如：提取课程中的所有行动项，并按优先级排序"
          />
          <el-button type="primary" :loading="analysisBusy" :disabled="video.status !== 'READY'" @click="createAnalysis">
            开始分析
          </el-button>
        </div>
      </aside>

      <div class="content-column panel">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="分析报告" name="report">
            <div v-if="analyses.length" class="analysis-picker">
              <el-select v-model="activeAnalysisId" placeholder="选择分析任务">
                <el-option
                  v-for="item in analyses"
                  :key="item.id"
                  :label="`${item.mode === 'AUTO_REPORT' ? '自动报告' : item.goal.slice(0, 30)} · ${item.status}`"
                  :value="item.id"
                />
              </el-select>
            </div>
            <div v-if="activeAnalysis?.status === 'COMPLETED'" class="report">
              <p class="eyebrow">EVIDENCE-GROUNDED REPORT</p>
              <h2>{{ report.title }}</h2>
              <p class="lead">{{ report.executive_summary }}</p>

              <div v-if="report.chapters?.length" class="report-section">
                <h3>章节脉络</h3>
                <button v-for="chapter in report.chapters" :key="chapter.start_ms" class="chapter" @click="jump(chapter.start_ms)">
                  <time>{{ time(chapter.start_ms) }}</time>
                  <span><strong>{{ chapter.title }}</strong><small>{{ chapter.summary }}</small></span>
                </button>
              </div>
              <div v-if="report.conclusions?.length" class="report-section">
                <h3>关键结论</h3>
                <article v-for="(item, index) in report.conclusions" :key="index" class="conclusion">
                  <span>{{ String(index + 1).padStart(2, '0') }}</span>
                  <div><p>{{ item.text }}</p><small>置信度 {{ Math.round(item.confidence * 100) }}% · {{ item.evidence_ids.length }} 条证据</small></div>
                </article>
              </div>
              <div class="two-columns">
                <div v-if="report.action_items?.length" class="report-section"><h3>行动项</h3><ul><li v-for="item in report.action_items" :key="item">{{ item }}</li></ul></div>
                <div v-if="report.suggestions?.length" class="report-section"><h3>建议</h3><ul><li v-for="item in report.suggestions" :key="item">{{ item }}</li></ul></div>
              </div>
            </div>
            <div v-else class="analysis-wait">
              <div class="pulse" />
              <h3>{{ activeAnalysis ? 'Agent 正在分析视频' : '尚无分析报告' }}</h3>
              <p>{{ activeAnalysis?.error || '视频解析完成后会自动生成第一份报告，也可以在左侧输入自定义目标。' }}</p>
            </div>
          </el-tab-pane>

          <el-tab-pane label="证据时间轴" name="timeline">
            <div class="timeline">
              <button v-for="segment in segments" :key="segment.id" class="timeline-item" @click="jump(segment.start_ms)">
                <time>{{ time(segment.start_ms) }}</time>
                <div>
                  <p v-if="segment.transcript"><b>ASR</b>{{ segment.transcript }}</p>
                  <p v-if="segment.visual_text"><b>VISION</b>{{ segment.visual_text }}</p>
                </div>
              </button>
              <div v-if="!segments.length" class="analysis-wait"><h3>等待生成时间轴</h3></div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="追问视频" name="chat">
            <div class="chat-panel">
              <div class="chat-stream">
                <div v-if="!chatMessages.length" class="chat-welcome">
                  <span>✦</span><h3>围绕视频继续追问</h3><p>回答会引用已有时间轴证据，不会重新处理视频。</p>
                </div>
                <article v-for="(message, index) in chatMessages" :key="index" :class="['chat-message', message.role]">
                  <small>{{ message.role === 'user' ? 'YOU' : 'VIDAGT' }}</small>
                  <p>{{ message.content }}</p>
                  <div v-if="message.evidence?.length" class="evidence-chips">
                    <button v-for="item in message.evidence" :key="item.id" @click="jump(item.start_ms)">
                      {{ item.source }} · {{ time(item.start_ms) }}
                    </button>
                  </div>
                </article>
                <article v-if="chatBusy" class="chat-message assistant"><small>VIDAGT</small><p class="typing">正在检索证据并生成回答…</p></article>
              </div>
              <div class="chat-input">
                <el-input v-model="question" size="large" placeholder="输入关于视频的问题…" @keyup.enter="sendQuestion" />
                <el-button type="primary" :loading="chatBusy" @click="sendQuestion">发送</el-button>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </section>
</template>
