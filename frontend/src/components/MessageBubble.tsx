import { motion } from "framer-motion";
import type { ChatMessage } from "../types";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}
    >
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
    </motion.div>
  );
}
