<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <button class="brand" @click="router.push('/')">
        <span class="brand-mark">V</span>
        <span>
          <strong>VidAgt</strong>
          <small>VIDEO INTELLIGENCE</small>
        </span>
      </button>
      <nav>
        <button :class="{ active: route.name === 'home' }" @click="router.push('/')">
          视频库
        </button>
        <span class="system-pill"><i /> 本地工作台</span>
      </nav>
    </header>
    <main><router-view /></main>
  </div>
</template>

