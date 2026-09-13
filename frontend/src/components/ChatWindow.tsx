import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useChatSocket } from "../hooks/useChatSocket";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { StageBadge } from "./StageBadge";

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
  } = useChatSocket();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, awaitingReply]);

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
          <span className="chat-header__sub">Apex Fitness Club Assistant</span>
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

      <div className="chat-input-bar">
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
    </div>
  );
}
