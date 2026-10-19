import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, ClientEvent, ConnectionStatus, ServerEvent } from "../types";

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? "ws://localhost:8000/ws/chat";
const MAX_RECONNECT_ATTEMPTS = 5;
/** Assignment 3: errors about voice/TTS only -- shown as a toast, never as a chat bubble. */
const SIDE_ERROR_CODES = new Set(["voice_unavailable", "asr_error", "tts_error", "mic_silent"]);

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Assignment 3: a stable per-browser id, so workouts/profile survive page reloads. */
function userId(): string {
  try {
    let id = localStorage.getItem("zor_user_id");
    if (!id) {
      id = uid();
      localStorage.setItem("zor_user_id", id);
    }
    return id;
  } catch {
    return uid(); // storage blocked: still works, just not remembered
  }
}

export type ServerEventListener = (event: ServerEvent) => void;

/**
 * Owns the single WebSocket connection to /ws/chat and turns the raw
 * session/token/done/error event stream into plain React state: a message
 * list, connection status, the current conversation stage, and whether a
 * reply is in flight. This is the only place in the frontend that speaks
 * the wire protocol -- components just call sendMessage()/resetSession().
 */
export function useChatSocket() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [stage, setStage] = useState("greeting");
  const [isStreaming, setIsStreaming] = useState(false);
  const [awaitingReply, setAwaitingReply] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const streamingIdRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Assignment 3: other hooks (voice, latency, toasts) subscribe to the raw event stream.
  const listenersRef = useRef(new Set<ServerEventListener>());

  const connect = useCallback(() => {
    setStatus("connecting");
    // Assignment 3: extended=1 opts in to the new event types; user_id keys per-user data.
    const params = new URLSearchParams({ extended: "1", user_id: userId() });
    if (sessionIdRef.current) params.set("session_id", sessionIdRef.current);
    const url = `${WS_URL}?${params.toString()}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    // React StrictMode (dev only) mounts this effect, runs its cleanup, then mounts it
    // again -- so a first, throwaway socket is created and closed immediately. Its close
    // event still fires asynchronously, *after* the real socket below is already open.
    // Every handler below checks `wsRef.current === ws` first so a stale socket's events
    // can never clobber the state of whichever socket is actually current.
    const isCurrent = () => wsRef.current === ws;

    ws.onopen = () => {
      if (!isCurrent()) return;
      reconnectAttempts.current = 0;
      setStatus("open");
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      if (!isCurrent()) return;
      let data: ServerEvent;
      try {
        data = JSON.parse(event.data) as ServerEvent;
      } catch {
        return; // ignore anything unparsable -- the server never sends non-JSON
      }

      listenersRef.current.forEach((listener) => listener(data));
      if (data.type === "error" && SIDE_ERROR_CODES.has(data.code)) return; // a toast, not a bubble

      switch (data.type) {
        case "session": {
          sessionIdRef.current = data.session_id;
          setSessionId(data.session_id);
          setStage(data.stage);
          break;
        }
        case "token": {
          setAwaitingReply(false);
          setIsStreaming(true);
          // The updater passed to setMessages must be a pure function of `prev` -- React
          // (in StrictMode, dev only) invokes it twice per call to catch exactly this kind
          // of bug, and a mutation like `streamingIdRef.current = id` happening *inside*
          // the updater leaks between those two invocations and silently corrupts the
          // result. So every ref read/write here happens outside the updater, once.
          const currentStreamingId = streamingIdRef.current;
          if (currentStreamingId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === currentStreamingId ? { ...m, content: m.content + data.content } : m,
              ),
            );
          } else {
            const id = uid();
            streamingIdRef.current = id;
            setMessages((prev) => [...prev, { id, role: "assistant", content: data.content }]);
          }
          break;
        }
        case "done": {
          // Citations (optional field): attach them to the reply that just finished streaming.
          const finishedId = streamingIdRef.current;
          const sources = data.sources;
          if (finishedId && sources && sources.length > 0) {
            setMessages((prev) => prev.map((m) => (m.id === finishedId ? { ...m, sources } : m)));
          }
          setStage(data.stage);
          setIsStreaming(false);
          setAwaitingReply(false);
          streamingIdRef.current = null;
          break;
        }
        case "error": {
          setIsStreaming(false);
          setAwaitingReply(false);
          streamingIdRef.current = null;
          const errorId = uid();
          setMessages((prev) => [
            ...prev,
            { id: errorId, role: "assistant", content: data.message, isError: true },
          ]);
          break;
        }
        // --- Assignment 3 ---
        case "tool_call": {
          // An inline card, placed before the answer that is about to stream.
          const tool = { id: data.id, name: data.name, arguments: data.arguments, status: "running" as const };
          setMessages((prev) => [...prev, { id: uid(), role: "assistant", content: "", tool }]);
          break;
        }
        case "tool_result": {
          const status = data.ok ? ("ok" as const) : ("error" as const);
          setMessages((prev) =>
            prev.map((m) =>
              m.tool?.id === data.id ? { ...m, tool: { ...m.tool, status, result: data.result } } : m,
            ),
          );
          break;
        }
        case "transcript": {
          // The final transcript is the user's turn: show it like a typed message.
          if (data.final) {
            setAwaitingReply(true);
            setMessages((prev) => [...prev, { id: uid(), role: "user", content: data.text, spoken: true }]);
          }
          break;
        }
        // voice_state / audio / audio_end / latency: handled by the listeners (useVoiceChat).
      }
    };

    ws.onclose = () => {
      if (!isCurrent()) return; // a stale/replaced socket closing is not a real disconnect
      wsRef.current = null;
      if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 10000);
        reconnectAttempts.current += 1;
        setStatus("closed");
        reconnectTimer.current = setTimeout(connect, delay);
      } else {
        setStatus("error");
      }
    };

    ws.onerror = () => {
      // The browser always follows an error event with a close event, which
      // is where reconnect/backoff logic lives -- nothing else to do here.
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((event: ClientEvent) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return false;
    wsRef.current.send(JSON.stringify(event));
    return true;
  }, []);

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const sent = send({ type: "message", content: trimmed });
      if (!sent) return;
      setAwaitingReply(true);
      const id = uid();
      setMessages((prev) => [...prev, { id, role: "user", content: trimmed }]);
    },
    [send],
  );

  const resetSession = useCallback(() => {
    if (!send({ type: "reset" })) return;
    setMessages([]);
    setAwaitingReply(false);
    setIsStreaming(false);
    streamingIdRef.current = null;
  }, [send]);

  const manualReconnect = useCallback(() => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    reconnectAttempts.current = 0;
    connect();
  }, [connect]);

  // --- Assignment 3 additions ---
  const addListener = useCallback((listener: ServerEventListener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  /** Raw microphone audio (16 kHz 16-bit PCM) as a binary frame. */
  const sendAudio = useCallback((chunk: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(chunk);
  }, []);

  return {
    send,
    addListener,
    sendAudio,
    messages,
    status,
    stage,
    isStreaming,
    awaitingReply,
    sessionId,
    sendMessage,
    resetSession,
    manualReconnect,
  };
}
