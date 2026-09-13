import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, ClientEvent, ConnectionStatus, ServerEvent } from "../types";

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? "ws://localhost:8000/ws/chat";
const MAX_RECONNECT_ATTEMPTS = 5;

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

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

  const connect = useCallback(() => {
    setStatus("connecting");
    const url = sessionIdRef.current
      ? `${WS_URL}?session_id=${encodeURIComponent(sessionIdRef.current)}`
      : WS_URL;
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

  return {
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
