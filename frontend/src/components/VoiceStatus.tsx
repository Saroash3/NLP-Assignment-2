import type { VoiceState } from "../types";
import { cn } from "@/lib/utils";

const LABELS: Record<VoiceState, string> = {
  idle: "Voice off",
  listening: "Listening…",
  transcribing: "Transcribing…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

// Dot colour per state: volt while it's the member's turn, emerald while Nova works/talks.
const DOT: Record<VoiceState, string> = {
  idle: "bg-mute",
  listening: "bg-volt animate-pulse",
  transcribing: "bg-volt",
  thinking: "bg-emerald animate-pulse",
  speaking: "bg-emerald",
};

/** One line above the input bar: the voice state and the live (partial) transcript. */
export function VoiceStatus({ state, partial }: { state: VoiceState; partial: string }) {
  return (
    <div className="flex items-center gap-3 border-t border-line bg-surface px-6 py-2 text-sm" aria-live="polite">
      <span className={cn("size-2.5 shrink-0 rounded-full", DOT[state])} />
      <span className="shrink-0 font-semibold text-ink">{LABELS[state]}</span>
      {partial && <span className="truncate italic text-mute">“{partial}”</span>}
    </div>
  );
}
