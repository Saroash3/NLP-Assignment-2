import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Landing } from "./components/Landing";
import { ChatWindow } from "./components/ChatWindow";

type Screen = "landing" | "chat";

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");

  return (
    <AnimatePresence mode="wait">
      {screen === "landing" ? (
        <motion.div key="landing" exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
          <Landing onEnter={() => setScreen("chat")} />
        </motion.div>
      ) : (
        <motion.div
          key="chat"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="app-screen"
        >
          <ChatWindow onExit={() => setScreen("landing")} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
