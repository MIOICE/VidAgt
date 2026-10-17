<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Task } from '../api/client'

const props = defineProps<{ task: Task }>()
const emit = defineEmits<{ done: [task: Task] }>()
const current = ref<Task>(props.task)
let events: EventSource | null = null

const stageNames: Record<string, string> = {
  QUEUED: '等待调度',
  IMPORTING: '下载视频',
  PROBING: '读取媒体信息',
  HASHING: '内容去重',
  TRANSCODING: '生成预览',
  AUDIO: '提取音频',
  ASR: '语音转写',
  KEYFRAMES: '抽取关键帧',
  VISION: '画面理解',
  FUSION: '融合时间轴',
  INDEXING: '构建语义索引',
  COMPLETED: '处理完成',
}
const label = computed(() => stageNames[current.value.stage] || current.value.stage)

onMounted(() => {
  events = new EventSource(`/api/v1/tasks/${props.task.id}/events`)
  events.addEventListener('progress', (event) => {
    current.value = JSON.parse((event as MessageEvent).data)
  })
  events.addEventListener('done', (event) => {
    current.value = JSON.parse((event as MessageEvent).data)
    events?.close()
    emit('done', current.value)
  })
  events.onerror = () => events?.close()
})

onBeforeUnmount(() => events?.close())
</script>

<template>
  <div class="task-progress">
    <div class="task-progress__row">
      <span>{{ label }}</span>
      <strong>{{ Math.round(current.progress * 100) }}%</strong>
    </div>
    <el-progress
      :percentage="Math.round(current.progress * 100)"
      :status="current.status === 'FAILED' ? 'exception' : current.status === 'COMPLETED' ? 'success' : undefined"
      :show-text="false"
    />
    <p v-if="current.error" class="error-text">{{ current.error }}</p>
  </div>
</template>

