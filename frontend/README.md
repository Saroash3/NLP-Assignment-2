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
| `src/components/Landing.tsx` | Landing page: composes the sections below inside `MotionConfig reducedMotion="user"` |
| `src/components/landing/` | Sections: `Nav` (shadcn Dialog mobile menu), `Hero` (GSAP-pinned) + lazy `HeroCanvas` (R3F/drei low-poly), `Stats` (GSAP counters), `Plans` (shadcn Tabs, animated PKR prices), `Classes`, `Coaches` (Embla; lazy-loaded; illustrated Pakistani coach avatars generated locally with DiceBear in `avatar.ts`), `Facilities` (GSAP parallax), `Ladies`, `Stories` (Embla autoplay), `Branches` (shadcn Card), `Faq` (shadcn Accordion), `Footer`; `useSmoothScroll` (Lenis synced with ScrollTrigger, `lerp` 0.25 for normal scroll speed); `SectionBoundary` (a failed lazy section is skipped instead of blanking the page) |
| `src/components/ui/` | shadcn/ui components (Radix): button, card, tabs, accordion, dialog |
| `src/styles/tailwind.css` | Tailwind v4 entry + theme tokens ("Volt on Graphite" palette, Anton + Inter via @fontsource) |
| `src/components/MessageBubble.tsx` / `TypingIndicator.tsx` / `StageBadge.tsx` | Small presentational pieces, animated with Framer Motion |
| `src/data/gymData.ts` | All landing data (plans, PKR prices, timetable, coaches, branches, FAQ), mirrors `facts_source_of_truth.md` so the page never contradicts Nova's documents |
| `src/types.ts` | Shared TS types for the WebSocket protocol (mirrors `backend/app/schemas.py`) |
