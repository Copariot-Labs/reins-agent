import { useRef, useCallback, useState, useEffect } from "react";
import { OrderedAudioQueue } from "../audio/orderedAudioQueue";
import type { SentenceTask } from "../audio/orderedAudioQueue";
import { configureSystemChineseVoice } from "../audio/systemSpeech";
import { useAudioAnalyser } from "./useAudioAnalyser";
import type { AudioLevels } from "./useAudioAnalyser";

export type { SentenceTask } from "../audio/orderedAudioQueue";

interface CurrentPlayback {
  stop: () => void;
  finish: () => void;
}

interface SystemSpeechLipSyncState {
  active: boolean;
  text: string;
  startedAt: number;
  boundaryAt: number;
  boundaryIndex: number;
}

const PAUSE_CHARACTER = /[\s,.!?;:，。！？；：、]/;

export function useAudioQueue() {
  const [speaking, setSpeaking] = useState(false);
  const [speakingSentence, setSpeakingSentence] = useState<string | null>(null);
  const [speechSessionActive, setSpeechSessionActive] = useState(false);
  const queueRef = useRef(new OrderedAudioQueue());
  const playingRef = useRef(false);
  const currentPlaybackRef = useRef<CurrentPlayback | null>(null);
  const onExpressionChangeRef = useRef<((expr: string) => void) | null>(null);
  const onAudioDoneRef = useRef<((requestId: string) => void) | null>(null);
  const neutralExpressionRef = useRef("neutral");
  const systemSpeechLipSyncRef = useRef<SystemSpeechLipSyncState>({
    active: false,
    text: "",
    startedAt: 0,
    boundaryAt: 0,
    boundaryIndex: 0,
  });
  const {
    connectAudio,
    getAudioLevels: getAnalysedAudioLevels,
    disconnect,
  } = useAudioAnalyser();

  const connectRef = useRef(connectAudio);
  const disconnectRef = useRef(disconnect);
  useEffect(() => {
    connectRef.current = connectAudio;
  }, [connectAudio]);
  useEffect(() => {
    disconnectRef.current = disconnect;
  }, [disconnect]);

  const playAudioChunk = useCallback((audioData: string): Promise<void> => {
    return new Promise((resolve) => {
      disconnectRef.current();

      const blobUrl = `data:audio/mp3;base64,${audioData}`;
      const audio = new Audio(blobUrl);
      audio.crossOrigin = "anonymous";
      let resumeListenersAttached = false;
      let settled = false;

      const removeResumeListeners = () => {
        if (!resumeListenersAttached) return;
        document.removeEventListener("pointerdown", resumePlay);
        document.removeEventListener("keydown", resumePlay);
        resumeListenersAttached = false;
      };

      const finish = () => {
        if (settled) return;
        settled = true;
        removeResumeListeners();
        disconnectRef.current();
        audio.oncanplay = null;
        audio.onended = null;
        audio.onerror = null;
        audio.src = "";
        audio.load();
        if (currentPlaybackRef.current?.finish === finish) {
          currentPlaybackRef.current = null;
        }
        resolve();
      };

      currentPlaybackRef.current = {
        finish,
        stop: () => {
          audio.pause();
          finish();
        },
      };

      audio.oncanplay = () => {
        connectRef.current(audio);
      };
      audio.onended = finish;
      audio.onerror = finish;

      const resumePlay = () => {
        removeResumeListeners();
        audio.play().catch((error) => {
          console.warn("[AudioQueue] Resume play failed:", error);
          finish();
        });
      };

      const waitForInteraction = () => {
        if (resumeListenersAttached) return;
        resumeListenersAttached = true;
        document.addEventListener("pointerdown", resumePlay, { once: true });
        document.addEventListener("keydown", resumePlay, { once: true });
      };

      audio.play().catch((error) => {
        console.warn("[AudioQueue] Autoplay blocked, trying muted fallback:", error);
        audio.muted = true;
        audio.play().then(() => {
          audio.currentTime = 0;
          audio.muted = false;
        }).catch((fallbackError) => {
          console.warn("[AudioQueue] Muted autoplay fallback failed:", fallbackError);
          audio.muted = false;
          waitForInteraction();
        });
      });
    });
  }, []);

  const playSpeechFallback = useCallback((text: string, voice?: string): Promise<void> => {
    return new Promise((resolve) => {
      const synth = window.speechSynthesis;
      if (!text.trim() || !synth || typeof SpeechSynthesisUtterance === "undefined") {
        resolve();
        return;
      }

      disconnectRef.current();

      const utterance = new SpeechSynthesisUtterance(text);
      configureSystemChineseVoice(utterance, voice);
      const lipSyncState = systemSpeechLipSyncRef.current;
      lipSyncState.active = true;
      lipSyncState.text = text;
      lipSyncState.startedAt = performance.now();
      lipSyncState.boundaryAt = lipSyncState.startedAt;
      lipSyncState.boundaryIndex = 0;
      let settled = false;

      const finish = () => {
        if (settled) return;
        settled = true;
        lipSyncState.active = false;
        lipSyncState.text = "";
        utterance.onstart = null;
        utterance.onboundary = null;
        utterance.onend = null;
        utterance.onerror = null;
        if (currentPlaybackRef.current?.finish === finish) {
          currentPlaybackRef.current = null;
        }
        resolve();
      };

      currentPlaybackRef.current = {
        finish,
        stop: () => {
          synth.cancel();
          finish();
        },
      };

      utterance.onstart = () => {
        lipSyncState.startedAt = performance.now();
        lipSyncState.boundaryAt = lipSyncState.startedAt;
      };
      utterance.onboundary = (event) => {
        lipSyncState.boundaryAt = performance.now();
        lipSyncState.boundaryIndex = event.charIndex;
      };
      utterance.onend = finish;
      utterance.onerror = finish;

      try {
        synth.cancel();
        synth.speak(utterance);
      } catch (error) {
        console.warn("[AudioQueue] Web Speech fallback failed:", error);
        finish();
      }
    });
  }, []);

  const getAudioLevels = useCallback((): AudioLevels => {
    const state = systemSpeechLipSyncRef.current;
    if (!state.active) {
      return getAnalysedAudioLevels();
    }

    const now = performance.now();
    const elapsed = Math.max(0, (now - state.startedAt) / 1000);
    const boundaryAge = Math.max(0, (now - state.boundaryAt) / 1000);
    const estimatedIndex = Math.min(
      Math.max(0, state.text.length - 1),
      state.boundaryIndex + Math.floor(boundaryAge * 4.5),
    );
    const currentCharacter = state.text[estimatedIndex] ?? "";
    const pauseScale = PAUSE_CHARACTER.test(currentCharacter) ? 0.12 : 1;

    const syllablePulse = Math.pow(
      Math.max(0, Math.sin(elapsed * Math.PI * 7.2)),
      0.55,
    );
    const boundaryPulse =
      boundaryAge < 0.18
        ? Math.sin((boundaryAge / 0.18) * Math.PI)
        : 0;
    const phraseShape = 0.82 + Math.sin(elapsed * 2.1) * 0.12;
    const mouthOpen = Math.min(
      0.92,
      (0.08 + syllablePulse * 0.62 + boundaryPulse * 0.18) *
        phraseShape *
        pauseScale,
    );
    const mouthForm =
      Math.sin(elapsed * 5.3) * 0.38 + Math.sin(elapsed * 2.7) * 0.16;

    return {
      volume: mouthOpen,
      mouthOpen,
      mouthForm: Math.max(-0.65, Math.min(0.65, mouthForm)),
    };
  }, [getAnalysedAudioLevels]);

  const stopCurrentPlayback = useCallback(() => {
    const current = currentPlaybackRef.current;
    if (!current) return;
    current.stop();
    current.finish();
  }, []);

  const processQueue = useCallback(async () => {
    if (playingRef.current) return;
    playingRef.current = true;

    try {
      while (true) {
        const action = queueRef.current.peekNext();
        if (action.kind === "wait") break;
        if (action.kind === "complete") {
          queueRef.current.acknowledgeComplete(action.requestId);
          setSpeechSessionActive(false);
          onAudioDoneRef.current?.(action.requestId);
          break;
        }
        if (action.kind === "skip") {
          queueRef.current.advance(action.requestId, action.index);
          continue;
        }

        if (action.kind === "play" || action.kind === "speak") {
          setSpeaking(true);
          setSpeakingSentence(action.task.text);
          onExpressionChangeRef.current?.(action.task.expression);
          if (action.kind === "play") {
            await playAudioChunk(action.audio);
          } else {
            await playSpeechFallback(action.task.text, action.voice);
          }
          if (queueRef.current.activeRequestId() !== action.requestId) break;
          queueRef.current.advance(action.requestId, action.index);
        }
      }
    } finally {
      playingRef.current = false;
      setSpeaking(false);
      setSpeakingSentence(null);
      onExpressionChangeRef.current?.(neutralExpressionRef.current);
      if (queueRef.current.peekNext().kind !== "wait") {
        queueMicrotask(() => processQueueRef.current());
      }
    }
  }, [playAudioChunk, playSpeechFallback]);

  const processQueueRef = useRef(processQueue);
  useEffect(() => {
    processQueueRef.current = processQueue;
  }, [processQueue]);

  const processAcceptedMutation = useCallback((result: "accepted" | "ignored") => {
    if (result === "accepted") processQueueRef.current();
    return result;
  }, []);

  const beginRequest = useCallback((requestId: string) => {
    stopCurrentPlayback();
    queueRef.current.begin(requestId);
    setSpeaking(false);
    setSpeakingSentence(null);
    setSpeechSessionActive(true);
    processQueueRef.current();
  }, [stopCurrentPlayback]);

  const addSentence = useCallback((requestId: string, task: SentenceTask) => {
    return processAcceptedMutation(queueRef.current.addSentence(requestId, task));
  }, [processAcceptedMutation]);

  const addAudio = useCallback((requestId: string, index: number, audio: string) => {
    return processAcceptedMutation(queueRef.current.addAudio(requestId, index, audio));
  }, [processAcceptedMutation]);

  const failAudio = useCallback((requestId: string, index: number) => {
    return processAcceptedMutation(queueRef.current.failAudio(requestId, index));
  }, [processAcceptedMutation]);

  const useSystemSpeech = useCallback((requestId: string, index: number, voice: string) => {
    return processAcceptedMutation(
      queueRef.current.useSystemSpeech(requestId, index, voice),
    );
  }, [processAcceptedMutation]);

  const markTextDone = useCallback((requestId: string) => {
    return processAcceptedMutation(queueRef.current.markTextDone(requestId));
  }, [processAcceptedMutation]);

  const failRequest = useCallback((requestId: string) => {
    const result = processAcceptedMutation(queueRef.current.failPendingAndMarkDone(requestId));
    if (result === "accepted") {
      setSpeechSessionActive(false);
    }
    return result;
  }, [processAcceptedMutation]);

  const clearQueue = useCallback(() => {
    stopCurrentPlayback();
    queueRef.current.clear();
    setSpeaking(false);
    setSpeakingSentence(null);
    setSpeechSessionActive(false);
    onExpressionChangeRef.current?.(neutralExpressionRef.current);
  }, [stopCurrentPlayback]);

  useEffect(() => () => {
    stopCurrentPlayback();
    systemSpeechLipSyncRef.current = {
      ...systemSpeechLipSyncRef.current,
      active: false,
      text: "",
    };
    queueRef.current.clear();
  }, [stopCurrentPlayback]);

  const setOnExpressionChange = useCallback((cb: (expr: string) => void) => {
    onExpressionChangeRef.current = cb;
  }, []);

  const setOnAudioDone = useCallback((cb: (requestId: string) => void) => {
    onAudioDoneRef.current = cb;
  }, []);

  const setNeutralExpression = useCallback((expr: string) => {
    neutralExpressionRef.current = expr;
  }, []);

  return {
    speaking,
    speakingSentence,
    speechSessionActive,
    beginRequest,
    addSentence,
    addAudio,
    failAudio,
    useSystemSpeech,
    markTextDone,
    failRequest,
    clearQueue,
    getAudioLevels,
    setOnExpressionChange,
    setOnAudioDone,
    setNeutralExpression,
  };
}
