// The whole page: top bar, conversation, composer. The pieces get their data from three hooks —
// useChat (the conversation), useHealth (is the backend up?) and useTheme (dark/light).

import { MotionConfig } from "motion/react";
import { Composer } from "./components/Composer";
import { Conversation } from "./components/Conversation";
import { TopBar } from "./components/TopBar";
import { useChat } from "./hooks/useChat";
import { useHealth } from "./hooks/useHealth";
import { useTheme } from "./hooks/useTheme";
import "./app.css";

export default function App() {
  const chat = useChat();
  const { health, error } = useHealth();
  const { theme, toggle } = useTheme();
  const locked = chat.role === "patient" && !chat.patient;

  return (
    // reducedMotion="user": every motion animation (slides, scales, height, the role pill) turns into a
    // simple fade when the computer asks for less motion (final review: only the orbs did before).
    <MotionConfig reducedMotion="user">
    <div className="app">
      <TopBar
        role={chat.role}
        patient={chat.patient}
        onRole={(role, patient = null) => chat.setRole(role, patient)}
        health={health}
        healthError={error}
        theme={theme}
        onTheme={toggle}
      />
      <main className="app__main">
        <div className="column">
          <Conversation messages={chat.messages} pending={chat.pending} role={chat.role} locked={locked} onExample={chat.send} />
        </div>
      </main>
      <footer className="app__footer">
        <div className="column">
          <Composer role={chat.role} locked={locked} pending={chat.pending} onSend={chat.send} />
        </div>
      </footer>
    </div>
    </MotionConfig>
  );
}
