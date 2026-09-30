# Frontend — Nova Chat UI

React + Vite chat interface for the Zor Fitness Club assistant. Full project docs are in the
[root README](../README.md) — this file is just quick-start commands for this directory.

## Run it

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. Expects the backend at `ws://localhost:8000/ws/chat` by default;
copy `.env.example` to `.env.local` to point elsewhere.

## Layout

| File | Responsibility |
|---|---|
| `src/App.tsx` | Switches between the landing screen and the chat screen |
| `src/hooks/useChatSocket.ts` | Owns the WebSocket connection; the only place that speaks the wire protocol |
| `src/components/ChatWindow.tsx` | Chat UI: message list, input bar, stage badge, connection banner |
| `src/components/Landing.tsx` / `HeroScene.tsx` | Landing screen: GSAP stat counters + staggered trainer/facility cards, Three.js hero orb |
| `src/components/TrainerCard.tsx` / `FacilityCard.tsx` | Trainer bios with illustrated avatars, and gym facilities/amenities cards |
| `src/components/MessageBubble.tsx` / `TypingIndicator.tsx` / `StageBadge.tsx` | Small presentational pieces, animated with Framer Motion |
| `src/data/gymData.ts` | Trainer/facility display copy, mirrors `facts_source_of_truth.md` so the landing page never says something Nova's documents don't |
| `src/types.ts` | Shared TS types for the WebSocket protocol (mirrors `backend/app/schemas.py`) |
