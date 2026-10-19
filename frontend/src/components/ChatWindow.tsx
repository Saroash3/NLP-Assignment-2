import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import { useChatSocket } from "../hooks/useChatSocket";
import { useVoiceChat } from "../hooks/useVoiceChat";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { StageBadge } from "./StageBadge";
import { MicButton } from "./MicButton";
import { VoiceStatus } from "./VoiceStatus";
import { LatencyPanel } from "./LatencyPanel";
import { Toaster } from "@/components/ui/sonner";

const SUGGESTIONS = [
  "What classes do you have on Tuesdays?",
  "What's included in the Elite plan?",
  "I'd like to book a trial session",
  "Can I freeze my membership?",
];

export function ChatWindow({ onExit }: { onExit: () => void }) {
  const {
    messages,
    status,
    stage,
    isStreaming,
    awaitingReply,
    sendMessage,
    resetSession,
    manualReconnect,
    send,
    sendAudio,
    addListener,
  } = useChatSocket();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Assignment 3: voice mode on the same socket.
  const socketApi = useMemo(() => ({ send, sendAudio, addListener }), [send, sendAudio, addListener]);
  const voice = useVoiceChat(socketApi);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, awaitingReply]);

  // Assignment 3: toast when an open connection drops (the banner below stays as before);
  // the server-side voice session is gone with it, so voice mode switches off.
  const wasOpen = useRef(false);
  const { active: voiceActive, stop: stopVoice } = voice;
  useEffect(() => {
    if (status === "open") wasOpen.current = true;
    else if (wasOpen.current) {
      wasOpen.current = false;
      toast.error("Connection to Nova lost -- reconnecting…");
      if (voiceActive) stopVoice();
    }
  }, [status, voiceActive, stopVoice]);

  const inputDisabled = status !== "open";
  const sendDisabled = inputDisabled || isStreaming || !draft.trim();

  function handleSend() {
    if (sendDisabled) return;
    sendMessage(draft);
    setDraft("");
  }

  return (
    <div className="chat-shell">
      <header className="chat-header">
        <button className="ghost-button" onClick={onExit}>
          &larr; Back
        </button>
        <div className="chat-header__title">
          <span className="chat-header__name">Nova</span>
          <span className="chat-header__sub">Zor Fitness Club Assistant</span>
        </div>
        <StageBadge stage={stage} />
        <button className="ghost-button" onClick={resetSession} disabled={status !== "open"}>
          New Session
        </button>
      </header>

      {status !== "open" && (
        <div className={`status-banner status-banner--${status}`}>
          {status === "connecting" && "Connecting to Nova..."}
          {status === "closed" && "Connection lost — reconnecting..."}
          {status === "error" && (
            <>
              Can't reach the server. Is the backend running?{" "}
              <button className="link-button" onClick={manualReconnect}>
                Retry
              </button>
            </>
          )}
        </div>
      )}

      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty-state">
            <p>Ask Nova about classes, membership plans, trainers, or book a session.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="suggestion-chip"
                  onClick={() => sendMessage(s)}
                  disabled={status !== "open"}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {awaitingReply && <TypingIndicator key="typing" />}
        </AnimatePresence>
      </div>

      {voice.active && <VoiceStatus state={voice.state} partial={voice.partial} />}
      <LatencyPanel latency={voice.latency} />
      <div className="chat-input-bar">
        <MicButton
          active={voice.active}
          disabled={inputDisabled}
          onToggle={() => (voice.active ? voice.stop() : void voice.start())}
        />
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSend();
          }}
          placeholder="Ask about classes, plans, trainers..."
          disabled={inputDisabled}
        />
        <motion.button
          whileTap={{ scale: 0.92 }}
          className="send-button"
          onClick={handleSend}
          disabled={sendDisabled}
        >
          Send
        </motion.button>
      </div>
      <Toaster />
    </div>
  );
}
