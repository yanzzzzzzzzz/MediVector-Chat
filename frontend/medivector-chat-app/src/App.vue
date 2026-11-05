<template>
  <v-app>
    <v-main>
      <header v-if="route.path !== '/knowledge'" class="utility-header">
        <RouterLink class="utility-brand" to="/knowledge"><span>＋</span> MediVector</RouterLink>

        <div class="utility-actions">
          <RouterLink to="/knowledge">院所文件與審核</RouterLink>
          <button type="button" @click="openApiAccess"><i aria-hidden="true" class="mdi mdi-key-outline" />連線設定</button>
        </div>
      </header>

      <router-view />

      <dialog ref="accessDialog" aria-labelledby="access-title" class="access-dialog">
        <form @submit.prevent="applyToken">
          <div class="access-heading">
            <span class="access-symbol"><i aria-hidden="true" class="mdi mdi-key-outline" /></span>
            <button aria-label="關閉連線設定" class="access-close" type="button" @click="accessDialog?.close()"><i aria-hidden="true" class="mdi mdi-close" /></button>
          </div>

          <h2 id="access-title">連線到院所工作空間</h2>
          <p>輸入院所提供的存取憑證，載入你有權限查看的文件與審核工作。</p>
          <label for="api-token">存取憑證</label>

          <input
            id="api-token"
            v-model="token"
            autocomplete="off"
            placeholder="貼上你的存取憑證"
            type="password"
          >

          <small><i aria-hidden="true" class="mdi mdi-shield-lock-outline" />憑證僅保留於目前的瀏覽器分頁。</small>
          <button class="access-submit" type="submit">連線並重新載入<i aria-hidden="true" class="mdi mdi-arrow-right" /></button>
        </form>
      </dialog>
    </v-main>
  </v-app>
</template>

<script lang="ts" setup>
  import { provide, ref } from 'vue'
  import { useRoute } from 'vue-router'

  const route = useRoute()
  const accessDialog = ref<HTMLDialogElement | null>(null)
  const token = ref(sessionStorage.getItem('apiToken') || '')
  function openApiAccess () {
    accessDialog.value?.showModal()
  }
  provide('openApiAccess', openApiAccess)
  function applyToken () {
    sessionStorage.setItem('apiToken', token.value.trim())
    localStorage.removeItem('conversationId')
    window.location.reload()
  }
</script>

<style scoped>
:where(.access-dialog, .utility-header) button { appearance: none; border: 0; background: transparent; }

.utility-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding: 14px 24px; background: #fff; color: #273a35; border-bottom: 1px solid #e7ece9; font-size: 13px; }
.utility-brand { display: flex; align-items: center; gap: 9px; color: #203b32; text-decoration: none; font-weight: 750; font-size: 18px; }
.utility-brand span { display: grid; place-items: center; height: 29px; width: 29px; border-radius: 8px; background: #22795b; color: #fff; font-size: 24px; }
.utility-actions { display: flex; gap: 22px; align-items: center; }
.utility-actions a { color: #53655e; text-decoration: none; }
.utility-actions button { display: flex; gap: 7px; align-items: center; }
.access-dialog { margin: auto; padding: 32px; width: min(460px, calc(100vw - 32px)); border: 1px solid #e2e9e5; border-radius: 20px; background: #fff; color: #263e33; box-shadow: 0 24px 100px #10291d26; color-scheme: light; }
.access-dialog::backdrop { background: #152f2766; backdrop-filter: blur(3px); }
.access-heading { display: flex; justify-content: space-between; align-items: flex-start; }
.access-symbol { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 14px; background: #edf5ef; color: #28775b; font-size: 24px; }
.access-close { color: #819188; font-size: 21px; }
.access-dialog h2 { font-size: 23px; margin: 22px 0 10px; letter-spacing: -.6px; }
.access-dialog p { color: #748279; font-size: 13px; line-height: 1.8; margin-bottom: 24px; }
.access-dialog label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.access-dialog input { width: 100%; border: 1px solid #dce5df; border-radius: 9px; padding: 12px; outline: none; background: #fafcfb; }
.access-dialog input:focus { border-color: #40896a; box-shadow: 0 0 0 3px #3e906a14; }
.access-dialog small { display: flex; gap: 6px; margin: 12px 0 28px; color: #87928a; font-size: 11px; }
.access-submit { width: 100%; display: flex; justify-content: center; gap: 12px; padding: 12px; border-radius: 9px; background: #23795b; color: #fff; font-size: 13px; font-weight: 600; }
@media (max-width: 600px) { .utility-header { padding: 12px 16px; } .utility-actions { gap: 12px; } .utility-actions > a { display: none; } }
</style>
