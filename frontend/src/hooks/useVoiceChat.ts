import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { ClientEvent, LatencyStats, ServerEvent, VoiceState } from "../types";
import type { ServerEventListener } from "./useChatSocket";
import { useAudioPlayer } from "./useAudioPlayer";
import { useMicrophone } from "./useMicrophone";

interface SocketApi {
  send: (event: ClientEvent) => boolean;
  sendAudio: (chunk: ArrayBuffer) => void;
  addListener: (listener: ServerEventListener) => () => void;
}

/**
 * "tap"       tap-to-talk (default): tap the mic to start recording, tap again to send. Nothing is
 *             cut off by automatic end-of-speech detection, and noise can't start a turn.
 * "handsfree" the mic stays on and the server's VAD decides when each utterance ends.
 */
export type VoiceMode = "tap" | "handsfree";

function savedMode(): VoiceMode {
  try {
    return localStorage.getItem("zor_voice_mode") === "handsfree" ? "handsfree" : "tap";
  } catch {
    return "tap";
  }
}

/**
 * Voice on top of the EXISTING chat socket (no second connection):
 *   mic chunks -> binary frames;  voice_state / transcript / audio / latency events -> state.
 *
 * Half-duplex on purpose: mic audio is only SENT while recording (tap mode) or while the server
 * listens and nothing is playing (hands-free), so Nova never transcribes its own voice.
 */
export function useVoiceChat(socket: SocketApi) {
  const [mode, setModeState] = useState<VoiceMode>(savedMode);
  const [active, setActive] = useState(false); // hands-free mode is on
  const [recording, setRecording] = useState(false); // tap mode: between the two taps
  const [serverState, setServerState] = useState<VoiceState>("idle");
  const [partial, setPartial] = useState("");
  const [latency, setLatency] = useState<LatencyStats | null>(null);
  const { playing, unlock, enqueue, markEnd, stopAll } = useAudioPlayer();

  // Read inside the mic callback (which must not be recreated on every render).
  const gateOpen = useRef(false);
  gateOpen.current = mode === "tap" ? recording : active && serverState === "listening" && !playing;

  const { send, sendAudio, addListener } = socket;
  const { start: micStart, stop: micStop } = useMicrophone((chunk) => {
    if (gateOpen.current) sendAudio(chunk);
  });

  /** Open the mic (inside the click handler, so audio playback is allowed too). */
  const openMic = useCallback(async (): Promise<boolean> => {
    unlock();
    const error = await micStart();
    if (error === "cancelled") return false; // switched off while it was starting
    if (error) {
      toast.error(
        error === "permission_denied"
          ? "Microphone permission denied. Allow mic access in the browser to use voice."
          : "No microphone available.",
      );
      return false;
    }
    return true;
  }, [unlock, micStart]);

  /** Switch everything off (either mode). */
  const stop = useCallback(() => {
    micStop();
    stopAll();
    if (active) send({ type: "voice_stop" });
    setActive(false);
    setRecording(false);
    setServerState("idle");
    setPartial("");
  }, [micStop, stopAll, send, active]);

  // --- tap-to-talk ---
  const startRecording = useCallback(async () => {
    stopAll(); // tapping while Nova talks interrupts her
    if (!(await openMic())) return;
    if (!send({ type: "record_start" })) {
      micStop();
      toast.error("Not connected to the server.");
      return;
    }
    setRecording(true);
  }, [stopAll, openMic, send, micStop]);

  const stopRecording = useCallback(() => {
    setRecording(false); // close the gate first; audio already sent arrives before record_stop
    micStop();
    send({ type: "record_stop" });
  }, [micStop, send]);

  // --- hands-free ---
  const startHandsFree = useCallback(async () => {
    if (!(await openMic())) return;
    if (!send({ type: "voice_start" })) {
      micStop();
      toast.error("Not connected to the server.");
      return;
    }
    setActive(true);
  }, [openMic, send, micStop]);

  /** What the mic button does. */
  const toggle = useCallback(() => {
    if (mode === "tap") return recording ? stopRecording() : void startRecording();
    return active ? stop() : void startHandsFree();
  }, [mode, recording, active, stopRecording, startRecording, stop, startHandsFree]);

  const setMode = useCallback(
    (next: VoiceMode) => {
      stop();
      setModeState(next);
      try {
        localStorage.setItem("zor_voice_mode", next);
      } catch {
        /* storage blocked: the choice just isn't remembered */
      }
    },
    [stop],
  );

  useEffect(
    () =>
      addListener((event: ServerEvent) => {
        switch (event.type) {
          case "voice_state":
            setServerState(event.state);
            if (event.state !== "listening") setPartial("");
            break;
          case "transcript":
            setPartial(event.final ? "" : event.text);
            break;
          case "audio":
            enqueue(event.data, event.sample_rate);
            break;
          case "audio_end":
            markEnd();
            break;
          case "latency": {
            const { type: _type, ...stats } = event;
            setLatency(stats);
            break;
          }
          case "tool_result":
            if (!event.ok) toast.error(`Tool "${event.name}" failed: ${String(event.result)}`);
            break;
          case "error":
            if (event.code === "voice_unavailable") {
              toast.error(event.message);
              stop();
            } else if (event.code === "asr_error" || event.code === "tts_error" || event.code === "mic_silent") {
              toast.error(event.message);
            }
            break;
        }
      }),
    [addListener, enqueue, markEnd, stop],
  );

  useEffect(() => micStop, [micStop]); // release the mic when the chat screen closes

  // Tap mode: while Nova transcribes/thinks, a new recording would only queue up -- wait.
  const busy = mode === "tap" && !recording && (serverState === "transcribing" || serverState === "thinking");
  let state: VoiceState;
  if (mode === "tap") state = recording ? "listening" : playing ? "speaking" : serverState;
  else state = !active ? "idle" : playing ? "speaking" : serverState;

  return { mode, setMode, active, recording, busy, state, partial, latency, toggle, stop };
}
