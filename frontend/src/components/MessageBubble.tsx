import { motion } from "framer-motion";
import { FileText } from "lucide-react";
import type { ChatMessage } from "../types";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const sources = message.sources ?? [];
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}
    >
      <div className="bubble-stack">
        <div
          className={[
            "bubble",
            isUser ? "bubble--user" : "bubble--assistant",
            message.isError ? "bubble--error" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {message.content}
        </div>
        {/* Citations bonus: only rendered when the answer was grounded in documents. */}
        {sources.length > 0 && (
          <motion.div
            className="source-chips"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            aria-label="Sources"
          >
            <span className="source-chips__label">Sources</span>
            {sources.map((source) => (
              <span className="source-chip" key={source} title={`Answer grounded in ${source}`}>
                <FileText size={12} aria-hidden />
                {source}
              </span>
            ))}
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
