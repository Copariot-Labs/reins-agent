<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import PresentationEditWorkspace from '@/components/presentation/PresentationEditWorkspace.vue'

const { locale } = useI18n()
const title = computed(() => (
  locale.value.toLowerCase().startsWith('zh') ? '演示文稿' : 'Presentations'
))
</script>

<template>
  <div class="presentation-view">
    <header class="page-header">
      <h1>{{ title }}</h1>
    </header>
    <main class="page-content">
      <PresentationEditWorkspace />
    </main>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.presentation-view {
  min-height: 100%;
  color: $text-primary;
  background: $bg-primary;
}

.page-header {
  height: 68px;
  display: flex;
  align-items: center;
  padding: 0 32px;
  border-bottom: 1px solid $border-color;
  background: $bg-card;
}

.page-header h1 {
  margin: 0;
  font-size: 21px;
  line-height: 1.2;
  letter-spacing: 0;
}

.page-content {
  width: min(1320px, 100%);
  margin: 0 auto;
  padding: 24px 28px 32px;
}

@media (max-width: $breakpoint-mobile) {
  .page-header {
    height: 58px;
    padding: 0 18px 0 58px;
  }

  .page-content {
    padding: 0 0 24px;
  }
}
</style>
