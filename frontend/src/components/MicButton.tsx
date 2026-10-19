import { Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { VoiceMode } from "../hooks/useVoiceChat";

const LABELS: Record<VoiceMode, [idle: string, on: string]> = {
  tap: ["Tap to talk", "Tap again to send"],
  handsfree: ["Turn on hands-free voice", "Turn voice mode off"],
};

/** The mic next to the text input. Volt-filled while recording (tap) or listening (hands-free). */
export function MicButton({ mode, on, disabled, onToggle }: {
  mode: VoiceMode; on: boolean; disabled: boolean; onToggle: () => void;
}) {
  const label = LABELS[mode][on ? 1 : 0];
  return (
    <Button
      type="button"
      size="icon"
      variant={on ? "default" : "outline"}
      className={cn("size-[46px] shrink-0", on && "animate-pulse")}
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={on}
      aria-label={label}
      title={label}
    >
      {mode === "tap" && on ? <Square /> : <Mic />}
    </Button>
  );
}

/** Small switch between tap-to-talk (default) and hands-free (the VAD ends each utterance). */
export function VoiceModeToggle({ mode, onChange }: { mode: VoiceMode; onChange: (m: VoiceMode) => void }) {
  const next = mode === "tap" ? "handsfree" : "tap";
  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      className="h-[46px] shrink-0 px-3 text-xs text-mute"
      onClick={() => onChange(next)}
      title={mode === "tap" ? "Switch to hands-free voice" : "Switch to tap-to-talk"}
      aria-label={`Voice mode: ${mode === "tap" ? "tap to talk" : "hands-free"}. Click to switch.`}
    >
      {mode === "tap" ? "Tap to talk" : "Hands-free"}
    </Button>
  );
}
