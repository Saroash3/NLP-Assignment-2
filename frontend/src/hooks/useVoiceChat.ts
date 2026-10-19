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
 * Voice mode on top of the EXISTING chat socket (no second connection):
 *   mic chunks -> binary frames;  voice_state / transcript / audio / latency events -> state.
 *
 * Half-duplex on purpose: the mic audio is only SENT while the server is listening and the
 * assistant is not speaking, so the assistant never transcribes its own voice from the speakers.
 */
export function useVoiceChat(socket: SocketApi) {
  const [active, setActive] = useState(false);
  const [serverState, setServerState] = useState<VoiceState>("idle");
  const [partial, setPartial] = useState("");
  const [latency, setLatency] = useState<LatencyStats | null>(null);
  const { playing, unlock, enqueue, markEnd, stopAll } = useAudioPlayer();

  // Read inside the mic callback (which must not be recreated on every render).
  const gateOpen = useRef(false);
  gateOpen.current = active && serverState === "listening" && !playing;

  const { send, sendAudio, addListener } = socket;
  const { start: micStart, stop: micStop } = useMicrophone((chunk) => {
    if (gateOpen.current) sendAudio(chunk);
  });

  const stop = useCallback(() => {
    micStop();
    stopAll();
    send({ type: "voice_stop" });
    setActive(false);
    setServerState("idle");
    setPartial("");
  }, [micStop, stopAll, send]);

  const start = useCallback(async () => {
    unlock(); // inside the click handler: browsers only allow audio after a gesture
    const error = await micStart();
    if (error === "cancelled") return; // the mic was switched off while it was starting
    if (error) {
      toast.error(
        error === "permission_denied"
          ? "Microphone permission denied. Allow mic access in the browser to use voice."
          : "No microphone available.",
      );
      return;
    }
    if (!send({ type: "voice_start" })) {
      micStop();
      toast.error("Not connected to the server.");
      return;
    }
    setActive(true);
  }, [unlock, micStart, micStop, send]);

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

  const state: VoiceState = !active ? "idle" : playing ? "speaking" : serverState;
  return { active, state, partial, latency, start, stop };
}
