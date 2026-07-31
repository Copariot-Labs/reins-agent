/** User-facing TTS provider labels keyed by their internal config ids. */

export interface TtsPresetUi {
  name: string;
  needs_key: boolean;
  hint?: string;
}

export const TTS_PRESETS_UI: Record<string, TtsPresetUi> = {
  system: {
    name: 'System Chinese',
    needs_key: false,
    hint: 'Mandarin voices on this device — no key needed',
  },
  tiktok: {
    name: 'Reins TTS',
    needs_key: false,
    hint: 'Built into Reins — no key needed',
  },
  elevenlabs: {
    name: 'ElevenLabs',
    needs_key: true,
    hint: 'Studio voices (API key)',
  },
  openai_tts: {
    name: 'OpenAI',
    needs_key: true,
    hint: 'OpenAI speech (API key)',
  },
};

export const DEFAULT_TTS_PROVIDER = 'system';
export const DEFAULT_TTS_VOICE = 'zh-CN';
