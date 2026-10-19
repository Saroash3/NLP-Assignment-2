import { useCallback, useRef } from "react";

export type MicError = "permission_denied" | "unavailable" | "cancelled";

/**
 * Captures the microphone through an AudioWorklet (public/mic-processor.js) and calls
 * `onChunk` with 64 ms chunks of 16 kHz 16-bit mono PCM. Echo cancellation is on (so Nova never
 * hears itself); noise suppression and auto-gain are off (they hurt speech recognition).
 */
export function useMicrophone(onChunk: (chunk: ArrayBuffer) => void) {
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const onChunkRef = useRef(onChunk);
  onChunkRef.current = onChunk;
  // Bumped by every start/stop. A start() that finishes after a newer start/stop is stale and
  // closes what it opened -- so two mic pipelines can never run (and interleave audio) at once.
  const generationRef = useRef(0);

  const stop = useCallback(() => {
    generationRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    void contextRef.current?.close();
    streamRef.current = null;
    contextRef.current = null;
  }, []);

  /** Resolves to null on success, or the reason it failed. */
  const start = useCallback(async (): Promise<MicError | null> => {
    stop(); // always start from nothing
    const generation = generationRef.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        // Echo cancellation stays ON (Nova must not hear itself). Noise suppression and
        // auto-gain are OFF: they distort speech in ways Whisper (trained on raw audio) handles
        // badly; the server normalises the volume instead.
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: false },
      });
      if (generation !== generationRef.current) {
        stream.getTracks().forEach((track) => track.stop()); // stopped while we were waiting
        return "cancelled";
      }
      // Ask for a 16 kHz context so the browser's high-quality resampler converts the mic;
      // some browsers can't connect a 48 kHz mic to it -- then use the default rate and let
      // the worklet downsample.
      let context: AudioContext;
      let source: MediaStreamAudioSourceNode;
      try {
        context = new AudioContext({ sampleRate: 16000 });
        source = context.createMediaStreamSource(stream);
      } catch {
        context = new AudioContext();
        source = context.createMediaStreamSource(stream);
      }
      // Created after the permission prompt (outside the click), Chrome may start it
      // "suspended" -- then the worklet never runs and no audio is sent. Resume explicitly.
      await context.resume();
      await context.audioWorklet.addModule("/mic-processor.js");
      const worklet = new AudioWorkletNode(context, "mic-processor");
      worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => onChunkRef.current(event.data);
      source.connect(worklet);
      // Some Chrome builds only pull audio through nodes that reach the speakers; a muted
      // (gain 0) path to the output keeps the worklet fed without playing the mic back.
      const mute = context.createGain();
      mute.gain.value = 0;
      worklet.connect(mute).connect(context.destination);
      if (generation !== generationRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        void context.close();
        return "cancelled";
      }
      streamRef.current = stream;
      contextRef.current = context;
      return null;
    } catch (err) {
      if (generation === generationRef.current) stop();
      const denied = err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "SecurityError");
      return denied ? "permission_denied" : "unavailable";
    }
  }, [stop]);

  return { start, stop };
}
