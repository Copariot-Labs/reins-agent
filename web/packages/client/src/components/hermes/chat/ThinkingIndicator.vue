<template>
  <div class="thinking-container">
    <div class="thinking-dots">
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
    </div>
    <span v-if="text" class="thinking-text">{{ text }}</span>
  </div>
</template>

<script setup>
defineProps({
  text: {
    type: String,
    default: ''
  }
})
</script>

<style scoped>
.thinking-container {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.thinking-dots {
  display: flex;
  align-items: center;
  gap: 4px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: currentColor;
  animation: bounce 1.4s ease-in-out infinite;
}

.dot:nth-child(1) {
  animation-delay: 0s;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}

.thinking-text {
  font-size: 13px;
  color: var(--text-secondary);
}

@keyframes bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.3;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}
</style>