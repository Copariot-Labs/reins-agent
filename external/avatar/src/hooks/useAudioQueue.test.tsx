import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeAudio, installFakeAudio } from "../test/fakeAudio";
import { useAudioQueue } from "./useAudioQueue";

vi.mock("./useAudioAnalyser", () => ({
  useAudioAnalyser: () => ({
    connectAudio: vi.fn(),
    disconnect: vi.fn(),
    getAudioLevels: vi.fn(() => ({
      volume: 0,
      mouthOpen: 0,
      mouthForm: 0,
    })),
  }),
}));

const sentence = (index: number) => ({
  index,
  expression: `expr-${index}`,
  text: `sentence-${index}`,
});

class FakeSpeechSynthesisUtterance {
  text: string;
  lang = "";
  voice: SpeechSynthesisVoice | null = null;
  onstart: (() => void) | null = null;
  onboundary: ((event: { charIndex: number }) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(text: string) {
    this.text = text;
  }
}

describe("useAudioQueue", () => {
  let speechSpeak: ReturnType<typeof vi.fn>;
  let mandarinVoice: SpeechSynthesisVoice;

  beforeEach(() => {
    FakeAudio.reset();
    installFakeAudio();
    speechSpeak = vi.fn((utterance: FakeSpeechSynthesisUtterance) => {
      utterance.onend?.();
    });
    mandarinVoice = {
      default: false,
      lang: "zh-CN",
      localService: true,
      name: "Tingting",
      voiceURI: "zh-CN-Tingting",
    };
    vi.stubGlobal("SpeechSynthesisUtterance", FakeSpeechSynthesisUtterance);
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: {
        addEventListener: vi.fn(),
        cancel: vi.fn(),
        getVoices: vi.fn(() => [mandarinVoice]),
        removeEventListener: vi.fn(),
        speak: speechSpeak,
      },
    });
  });

  it("speaks a failed middle sentence with Web Speech and then plays index 2", async () => {
    const { result } = renderHook(() => useAudioQueue());

    act(() => {
      result.current.beginRequest("r1");
      [0, 1, 2].forEach((index) => result.current.addSentence("r1", sentence(index)));
      result.current.addAudio("r1", 0, "a0");
      result.current.failAudio("r1", 1);
      result.current.addAudio("r1", 2, "a2");
    });

    await act(async () => {
      FakeAudio.instances[0].finish();
    });

    expect(speechSpeak).toHaveBeenCalledOnce();
    expect(speechSpeak.mock.calls[0][0].text).toBe("sentence-1");
    expect(speechSpeak.mock.calls[0][0].lang).toBe("zh-CN");
    expect(speechSpeak.mock.calls[0][0].voice).toBe(mandarinVoice);
    expect(FakeAudio.instances[1].src).toContain("a2");
  });

  it("uses the Chinese system voice selected in settings", () => {
    const { result } = renderHook(() => useAudioQueue());

    act(() => {
      result.current.beginRequest("r1");
      result.current.addSentence("r1", {
        index: 0,
        expression: "happy",
        text: "你好，很高兴认识你。",
      });
      result.current.useSystemSpeech("r1", 0, "zh-CN-Tingting");
    });

    expect(speechSpeak).toHaveBeenCalledOnce();
    expect(speechSpeak.mock.calls[0][0].lang).toBe("zh-CN");
    expect(speechSpeak.mock.calls[0][0].voice).toBe(mandarinVoice);
  });

  it("drives mouth levels while system Chinese speech is active", async () => {
    speechSpeak.mockImplementation(() => {});
    const { result } = renderHook(() => useAudioQueue());

    act(() => {
      result.current.beginRequest("r1");
      result.current.addSentence("r1", {
        index: 0,
        expression: "happy",
        text: "你好，很高兴认识你。",
      });
      result.current.useSystemSpeech("r1", 0, "zh-CN-Tingting");
    });

    const activeLevels = result.current.getAudioLevels();
    expect(activeLevels.mouthOpen).toBeGreaterThan(0);
    expect(Math.abs(activeLevels.mouthForm)).toBeLessThanOrEqual(0.65);

    await act(async () => {
      speechSpeak.mock.calls[0][0].onend?.();
    });

    expect(result.current.getAudioLevels()).toEqual({
      volume: 0,
      mouthOpen: 0,
      mouthForm: 0,
    });
  });

  it("ignores old audio and pauses active playback on begin", () => {
    const { result } = renderHook(() => useAudioQueue());

    act(() => {
      result.current.beginRequest("old");
      result.current.addSentence("old", sentence(0));
      result.current.addAudio("old", 0, "old-audio");
    });
    act(() => result.current.beginRequest("new"));

    expect(FakeAudio.instances[0].pause).toHaveBeenCalledOnce();
    act(() => result.current.addAudio("old", 0, "late-old-audio"));
    expect(FakeAudio.instances).toHaveLength(1);
  });

  it("advances after browser audio playback errors", async () => {
    const { result } = renderHook(() => useAudioQueue());

    act(() => {
      result.current.beginRequest("r1");
      result.current.addSentence("r1", sentence(0));
      result.current.addSentence("r1", sentence(1));
      result.current.addAudio("r1", 0, "a0");
      result.current.addAudio("r1", 1, "a1");
    });
    await act(async () => {
      FakeAudio.instances[0].fail();
    });

    expect(FakeAudio.instances[1].src).toContain("a1");
  });

  it("emits audio done once after text and all audio finish", async () => {
    const onAudioDone = vi.fn();
    const { result } = renderHook(() => useAudioQueue());

    act(() => {
      result.current.setOnAudioDone(onAudioDone);
      result.current.beginRequest("r1");
      result.current.addSentence("r1", sentence(0));
      result.current.addAudio("r1", 0, "a0");
      result.current.markTextDone("r1");
    });
    await act(async () => {
      FakeAudio.instances[0].finish();
    });

    expect(onAudioDone).toHaveBeenCalledOnce();
    expect(onAudioDone).toHaveBeenCalledWith("r1");
    act(() => result.current.markTextDone("r1"));
    expect(onAudioDone).toHaveBeenCalledOnce();
  });

  it("fails pending audio and completes after a chat error", () => {
    const onAudioDone = vi.fn();
    const { result } = renderHook(() => useAudioQueue());

    act(() => {
      result.current.setOnAudioDone(onAudioDone);
      result.current.beginRequest("r1");
      result.current.addSentence("r1", sentence(0));
      result.current.failRequest("r1");
    });

    expect(onAudioDone).toHaveBeenCalledWith("r1");
    expect(FakeAudio.instances).toHaveLength(0);
  });
});
