export interface SystemVoiceInfo {
  id: string;
  name: string;
}

export const DEFAULT_SYSTEM_VOICE = "zh-CN";

const DEFAULT_VOICES: SystemVoiceInfo[] = [
  { id: "zh-CN", name: "Mandarin Chinese - System default" },
  { id: "zh-TW", name: "Taiwan Mandarin - System default" },
  { id: "zh-HK", name: "Cantonese - System default" },
];

const isChineseVoice = (voice: SpeechSynthesisVoice) =>
  /^zh(?:-|_)/i.test(voice.lang);

const voiceId = (voice: SpeechSynthesisVoice) =>
  voice.voiceURI || `${voice.name} (${voice.lang})`;

function availableChineseVoices(): SystemVoiceInfo[] {
  if (typeof window === "undefined" || !window.speechSynthesis) {
    return [];
  }

  return window.speechSynthesis
    .getVoices()
    .filter(isChineseVoice)
    .sort((a, b) => {
      const aMandarin = /^zh-CN$/i.test(a.lang) ? 0 : 1;
      const bMandarin = /^zh-CN$/i.test(b.lang) ? 0 : 1;
      return aMandarin - bMandarin || a.name.localeCompare(b.name);
    })
    .map((voice) => ({
      id: voiceId(voice),
      name: `${voice.name} - ${voice.lang}`,
    }));
}

export async function listSystemChineseVoices(): Promise<SystemVoiceInfo[]> {
  const initial = availableChineseVoices();
  if (initial.length > 0) {
    return [...DEFAULT_VOICES, ...initial];
  }

  const synth =
    typeof window === "undefined" ? undefined : window.speechSynthesis;
  if (!synth) return DEFAULT_VOICES;
  const speechSynthesis = synth;

  await new Promise<void>((resolve) => {
    const timeout = window.setTimeout(finish, 300);

    function finish() {
      window.clearTimeout(timeout);
      speechSynthesis.removeEventListener("voiceschanged", finish);
      resolve();
    }

    speechSynthesis.addEventListener("voiceschanged", finish, { once: true });
  });

  return [...DEFAULT_VOICES, ...availableChineseVoices()];
}

export function configureSystemChineseVoice(
  utterance: SpeechSynthesisUtterance,
  requestedVoice = DEFAULT_SYSTEM_VOICE,
) {
  const synth =
    typeof window === "undefined" ? undefined : window.speechSynthesis;
  const voices = synth?.getVoices() ?? [];
  const exactVoice = voices.find(
    (voice) =>
      voiceId(voice) === requestedVoice || voice.name === requestedVoice,
  );
  const requestedLocale = /^zh(?:-(?:CN|TW|HK))?$/i.test(requestedVoice)
    ? requestedVoice
    : DEFAULT_SYSTEM_VOICE;
  const localeVoice =
    voices.find(
      (voice) =>
        voice.lang.toLowerCase() === requestedLocale.toLowerCase(),
    ) ?? voices.find(isChineseVoice);
  const selectedVoice = exactVoice ?? localeVoice;

  utterance.lang = selectedVoice?.lang || requestedLocale;
  if (selectedVoice) utterance.voice = selectedVoice;
}

export function previewSystemChineseVoice(
  voice: string,
  text = "你好，我是你的 Reins 伙伴。很高兴认识你。",
): Promise<void> {
  return new Promise((resolve, reject) => {
    const synth =
      typeof window === "undefined" ? undefined : window.speechSynthesis;
    if (!synth || typeof SpeechSynthesisUtterance === "undefined") {
      reject(new Error("System speech is not available on this device."));
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    configureSystemChineseVoice(utterance, voice);
    utterance.onend = () => resolve();
    utterance.onerror = () =>
      reject(new Error("The selected system Chinese voice could not play."));

    synth.cancel();
    synth.speak(utterance);
  });
}
