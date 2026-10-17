import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 120_000,
})

export interface Video {
  id: string
  title: string
  source_type: 'UPLOAD' | 'URL'
  source_url?: string
  mime_type?: string
  size_bytes?: number
  duration_ms?: number
  status: 'QUEUED' | 'PROCESSING' | 'READY' | 'FAILED'
  error?: string
  media_metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  video_id: string
  kind: string
  status: string
  stage: string
  progress: number
  error?: string
  task_metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface Segment {
  id: string
  start_ms: number
  end_ms: number
  transcript: string
  visual_text: string
  frame_keys: string[]
}

export interface Evidence {
  id: string
  source: 'ASR' | 'VISION'
  start_ms: number
  end_ms: number
  content: string
  frame_key?: string
  confidence: number
}

export interface ChatMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
  evidence?: Evidence[]
  created_at?: string
}

export interface Analysis {
  id: string
  video_id: string
  goal: string
  mode: string
  language: string
  status: string
  progress: number
  plan: Record<string, unknown>
  report: Record<string, any>
  error?: string
  created_at: string
  updated_at: string
}

export const videoApi = {
  async list() {
    return (await api.get<{ items: Video[]; total: number }>('/videos')).data
  },
  async get(id: string) {
    return (await api.get<Video>(`/videos/${id}`)).data
  },
  async remove(id: string) {
    await api.delete(`/videos/${id}`)
  },
  async playback(id: string) {
    return (await api.get<{ url: string }>(`/videos/${id}/playback`)).data
  },
  async segments(id: string) {
    return (await api.get<Segment[]>(`/videos/${id}/segments`)).data
  },
  async importUrl(url: string, title?: string) {
    return (await api.post<Task>('/videos/import', { url, title })).data
  },
  async retry(id: string) {
    return (await api.post<Task>(`/videos/${id}/process`)).data
  },
}

export const uploadApi = {
  async create(payload: { filename: string; size_bytes: number; mime_type: string; fingerprint: string }) {
    return (
      await api.post<{ upload_id: string; part_size: number; part_count: number; parallelism: number }>(
        '/uploads',
        payload,
      )
    ).data
  },
  async status(uploadId: string) {
    return (
      await api.get<{
        upload_id: string
        status: string
        completed_parts: { part_number: number; etag: string }[]
        missing_parts: number[]
      }>(`/uploads/${uploadId}`)
    ).data
  },
  async sign(uploadId: string, partNumbers: number[]) {
    return (
      await api.post<{ parts: { part_number: number; url: string }[] }>(
        `/uploads/${uploadId}/parts/sign`,
        { part_numbers: partNumbers },
      )
    ).data
  },
  async complete(uploadId: string, parts: { part_number: number; etag: string }[]) {
    return (await api.post<Task>(`/uploads/${uploadId}/complete`, { parts })).data
  },
}

export const analysisApi = {
  async list(videoId: string) {
    return (await api.get<Analysis[]>(`/videos/${videoId}/analyses`)).data
  },
  async create(videoId: string, goal: string, mode: 'AUTO_REPORT' | 'CUSTOM' = 'CUSTOM') {
    return (await api.post<Analysis>(`/videos/${videoId}/analyses`, { goal, mode, language: 'auto' })).data
  },
  async get(id: string) {
    return (await api.get<Analysis>(`/analyses/${id}`)).data
  },
  async chat(videoId: string, question: string, conversationId?: string) {
    return (
      await api.post<{ conversation_id: string; message_id: string; answer: string; evidence: Evidence[] }>(
        `/videos/${videoId}/chat`,
        { question, conversation_id: conversationId },
      )
    ).data
  },
  async chatHistory(videoId: string, conversationId?: string) {
    return (
      await api.get<{ conversation_id: string | null; messages: ChatMessage[] }>(
        `/videos/${videoId}/chat/history`,
        { params: conversationId ? { conversation_id: conversationId } : undefined },
      )
    ).data
  },
}
