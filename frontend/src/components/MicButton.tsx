import { Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Toggle for voice mode, placed next to the text input. Volt-filled while voice is on. */
export function MicButton({ active, disabled, onToggle }: { active: boolean; disabled: boolean; onToggle: () => void }) {
  return (
    <Button
      type="button"
      size="icon"
      variant={active ? "default" : "outline"}
      className={cn("size-[46px] shrink-0", active && "animate-pulse")}
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={active}
      aria-label={active ? "Turn voice mode off" : "Talk to Nova (voice mode)"}
      title={active ? "Voice mode on: click to stop" : "Voice mode: talk instead of typing"}
    >
      <Mic />
    </Button>
  );
}
