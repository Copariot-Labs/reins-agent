import { useRef, useCallback, useState, useEffect } from "react";
import { OrderedAudioQueue } from "../audio/orderedAudioQueue";
import type { SentenceTask } from "../audio/orderedAudioQueue";
import { useAudioAnalyser } from "./useAudioAnalyser";

export type { SentenceTask } from "../audio/orderedAudioQueue";

interface CurrentPlayback {
  stop: () => void;
  finish: () => void;
}

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
  const { connectAudio, getAudioLevels, disconnect } = useAudioAnalyser();

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

  const playSpeechFallback = useCallback((text: string): Promise<void> => {
    return new Promise((resolve) => {
      const synth = window.speechSynthesis;
      if (!text.trim() || !synth || typeof SpeechSynthesisUtterance === "undefined") {
        resolve();
        return;
      }

      disconnectRef.current();

      const utterance = new SpeechSynthesisUtterance(text);
      let settled = false;

      const finish = () => {
        if (settled) return;
        settled = true;
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
            await playSpeechFallback(action.task.text);
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
    markTextDone,
    failRequest,
    clearQueue,
    getAudioLevels,
    setOnExpressionChange,
    setOnAudioDone,
    setNeutralExpression,
  };
}
