<template>
  <v-app>
    <v-main>
      <form class="api-access" @submit.prevent="applyToken">
        <label for="api-token">API 存取 Token</label>

        <input
          id="api-token"
          v-model="token"
          autocomplete="off"
          placeholder="本機模式可留空"
          type="password"
        >

        <button type="submit">套用並重新載入</button>
      </form>

      <nav><RouterLink to="/knowledge">院所文件與審核</RouterLink></nav>

      <router-view />
    </v-main>
  </v-app>
</template>

<script lang="ts" setup>
  import { ref } from 'vue'

  const token = ref(sessionStorage.getItem('apiToken') || '')
  function applyToken () {
    sessionStorage.setItem('apiToken', token.value.trim())
    localStorage.removeItem('conversationId')
    window.location.reload()
  }
</script>

<style scoped>
.api-access { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 8px 16px; }
.api-access input { border: 1px solid #aaa; border-radius: 4px; padding: 4px 8px; }
.api-access button { padding: 4px 8px; text-decoration: underline; }
</style>
