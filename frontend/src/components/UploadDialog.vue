<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadApi, videoApi, type Task } from '../api/client'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; submitted: [task: Task] }>()

const mode = ref<'file' | 'url'>('file')
const file = ref<File | null>(null)
const url = ref('')
const title = ref('')
const busy = ref(false)
const progress = ref(0)
const message = ref('')
const dragging = ref(false)

const fileSize = computed(() => {
  if (!file.value) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let value = file.value.size
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`
})

function pickFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] || null
}

function dropFile(event: DragEvent) {
  dragging.value = false
  file.value = event.dataTransfer?.files?.[0] || null
}

async function fingerprint(input: File): Promise<string> {
  const block = 1024 * 1024
  const head = await input.slice(0, block).arrayBuffer()
  const tail = await input.slice(Math.max(0, input.size - block)).arrayBuffer()
  const metadata = new TextEncoder().encode(`${input.name}:${input.size}:${input.lastModified}:`)
  const merged = new Uint8Array(metadata.length + head.byteLength + tail.byteLength)
  merged.set(metadata)
  merged.set(new Uint8Array(head), metadata.length)
  merged.set(new Uint8Array(tail), metadata.length + head.byteLength)
  const digest = await crypto.subtle.digest('SHA-256', merged)
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

async function uploadFile(input: File): Promise<Task> {
  message.value = '正在初始化分片上传…'
  const session = await uploadApi.create({
    filename: input.name,
    size_bytes: input.size,
    mime_type: input.type || 'application/octet-stream',
    fingerprint: await fingerprint(input),
  })
  const state = await uploadApi.status(session.upload_id)
  const completed = new Map(state.completed_parts.map((part) => [part.part_number, part.etag]))
  const queue = [...state.missing_parts]
  const totalParts = session.part_count
  progress.value = Math.round((completed.size / totalParts) * 100)
  message.value = completed.size ? '已恢复历史进度，继续上传…' : '正在上传视频分片…'

  async function worker() {
    while (queue.length) {
      const partNumber = queue.shift()
      if (!partNumber) return
      const signed = await uploadApi.sign(session.upload_id, [partNumber])
      const start = (partNumber - 1) * session.part_size
      const body = input.slice(start, Math.min(input.size, start + session.part_size))
      const response = await fetch(signed.parts[0].url, { method: 'PUT', body })
      if (!response.ok) throw new Error(`第 ${partNumber} 个分片上传失败`)
      const etag = response.headers.get('etag')?.replaceAll('"', '')
      if (!etag) throw new Error('对象存储未暴露 ETag 响应头，请检查 MinIO CORS 配置')
      completed.set(partNumber, etag)
      progress.value = Math.round((completed.size / totalParts) * 100)
    }
  }
  await Promise.all(Array.from({ length: session.parallelism }, () => worker()))
  message.value = '正在合并分片并创建解析任务…'
  return uploadApi.complete(
    session.upload_id,
    Array.from(completed, ([part_number, etag]) => ({ part_number, etag })).sort(
      (left, right) => left.part_number - right.part_number,
    ),
  )
}

async function submit() {
  busy.value = true
  progress.value = 0
  try {
    let task: Task
    if (mode.value === 'file') {
      if (!file.value) throw new Error('请先选择视频文件')
      task = await uploadFile(file.value)
    } else {
      if (!url.value.trim()) throw new Error('请输入视频链接')
      message.value = '正在创建链接导入任务…'
      task = await videoApi.importUrl(url.value.trim(), title.value.trim() || undefined)
    }
    emit('submitted', task)
    emit('update:modelValue', false)
    ElMessage.success('任务已提交，后台开始解析')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || error.message || '提交失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="添加视频"
    width="min(620px, 92vw)"
    :close-on-click-modal="!busy"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="mode-switch">
      <button :class="{ active: mode === 'file' }" @click="mode = 'file'">本地文件</button>
      <button :class="{ active: mode === 'url' }" @click="mode = 'url'">视频链接</button>
    </div>
    <div v-if="mode === 'file'">
      <label
        class="drop-zone"
        :class="{ dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="dropFile"
      >
        <input type="file" accept="video/*,.mkv,.mov,.webm" @change="pickFile" />
        <span class="drop-icon">↥</span>
        <strong>{{ file ? file.name : '点击或拖入视频文件' }}</strong>
        <small>{{ file ? fileSize : '支持 MP4、MOV、MKV、WebM，最大 2GB' }}</small>
      </label>
    </div>
    <div v-else class="url-form">
      <label>视频地址</label>
      <el-input v-model="url" size="large" placeholder="https://…" />
      <label>显示标题（可选）</label>
      <el-input v-model="title" size="large" placeholder="留空则自动获取" />
    </div>
    <div v-if="busy" class="upload-progress">
      <div><span>{{ message }}</span><strong v-if="mode === 'file'">{{ progress }}%</strong></div>
      <el-progress v-if="mode === 'file'" :percentage="progress" :show-text="false" />
    </div>
    <template #footer>
      <el-button :disabled="busy" @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="busy" @click="submit">开始解析</el-button>
    </template>
  </el-dialog>
</template>

