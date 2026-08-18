<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NModal } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchWeComSetup } from '@/api/reins/wecom'
import { isStoredSuperAdmin } from '@/api/client'
import WeComSettings from './WeComSettings.vue'

const route = useRoute()
const router = useRouter()
const { locale } = useI18n()
const show = ref(false)
const dismissed = ref(false)
const checking = ref(false)
const canConfigure = computed(() => isStoredSuperAdmin())
const isChinese = computed(() => locale.value.toLowerCase().startsWith('zh'))
const title = computed(() => isChinese.value ? '完成 Reins 企业微信设置' : 'Finish setting up Reins WeCom')
const later = computed(() => isChinese.value ? '稍后设置' : 'Set up later')

async function check() {
  if (!canConfigure.value || checking.value || dismissed.value || route.name === 'login') return
  checking.value = true
  try {
    const status = await fetchWeComSetup()
    show.value = !status.configured
  } catch {
    show.value = false
  } finally {
    checking.value = false
  }
}

function dismiss() {
  dismissed.value = true
  show.value = false
}

function openSettings() {
  show.value = false
  void router.push({ name: 'hermes.settings', query: { tab: 'wecom' } })
}

watch(() => route.name, check, { immediate: true })
</script>

<template>
  <NModal v-model:show="show" preset="card" :title="title" class="wecom-setup-modal" :mask-closable="false">
    <WeComSettings @saved="show = false" />
    <template #footer>
      <div class="prompt-actions">
        <NButton quaternary @click="dismiss">{{ later }}</NButton>
        <NButton secondary @click="openSettings">Settings</NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.prompt-actions { display: flex; justify-content: flex-end; gap: 8px; }
:global(.wecom-setup-modal) { width: min(920px, calc(100vw - 32px)); max-height: calc(100vh - 40px); overflow-y: auto; }
</style>
