import { useCallback, useRef, useState } from "react";

/**
 * Plays the assistant's speech: each `audio` event (one sentence of base64 16-bit PCM) is
 * scheduled to start exactly when the previous one ends, so sentences play gap-free and in
 * order while later ones are still being generated. `playing` is true until the last
 * scheduled sentence finishes AND the server has said audio_end.
 */
export function useAudioPlayer() {
  const [playing, setPlaying] = useState(false);
  const contextRef = useRef<AudioContext | null>(null);
  const nextStartRef = useRef(0);
  const sourcesRef = useRef(new Set<AudioBufferSourceNode>());
  const endedRef = useRef(true); // audio_end received for the current reply

  const finishIfDone = useCallback(() => {
    if (endedRef.current && sourcesRef.current.size === 0) setPlaying(false);
  }, []);

  /** Must be called from a click (browsers only allow audio after a user gesture). */
  const unlock = useCallback(() => {
    if (!contextRef.current) contextRef.current = new AudioContext();
    void contextRef.current.resume();
  }, []);

  const enqueue = useCallback((base64: string, sampleRate: number) => {
    const context = contextRef.current;
    if (!context) return;
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const pcm = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
    const buffer = context.createBuffer(1, pcm.length, sampleRate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 0x8000;

    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    const startAt = Math.max(context.currentTime + 0.02, nextStartRef.current);
    source.start(startAt);
    nextStartRef.current = startAt + buffer.duration;
    sourcesRef.current.add(source);
    endedRef.current = false;
    setPlaying(true);
    source.onended = () => {
      sourcesRef.current.delete(source);
      finishIfDone();
    };
  }, [finishIfDone]);

  /** The server sent audio_end: no more sentences for this reply. */
  const markEnd = useCallback(() => {
    endedRef.current = true;
    finishIfDone();
  }, [finishIfDone]);

  /** Stop speaking immediately (voice mode switched off). */
  const stopAll = useCallback(() => {
    sourcesRef.current.forEach((source) => {
      source.onended = null;
      source.stop();
    });
    sourcesRef.current.clear();
    nextStartRef.current = 0;
    endedRef.current = true;
    setPlaying(false);
  }, []);

  return { playing, unlock, enqueue, markEnd, stopAll };
}
