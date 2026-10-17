import { defineStore } from 'pinia'
import { ref } from 'vue'
import { videoApi, type Video } from '../api/client'

export const useVideoStore = defineStore('videos', () => {
  const videos = ref<Video[]>([])
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    try {
      videos.value = (await videoApi.list()).items
    } finally {
      loading.value = false
    }
  }

  return { videos, loading, refresh }
})

