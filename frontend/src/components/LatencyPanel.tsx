import { Gauge } from "lucide-react";
import type { LatencyStats } from "../types";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

const ROWS: [keyof LatencyStats, string][] = [
  ["asr_ms", "ASR"],
  ["retrieval_ms", "Retrieval + routing"],
  ["tool_ms", "Tool"],
  ["llm_first_token_ms", "LLM first token"],
  ["tts_first_audio_ms", "TTS first audio"],
  ["total_ms", "End of speech → first audio"],
];

/** Collapsible panel with the last turn's timings (reuses the existing shadcn Accordion). */
export function LatencyPanel({ latency }: { latency: LatencyStats | null }) {
  return (
    <Accordion type="single" collapsible className="border-t border-line bg-surface px-6">
      <AccordionItem value="latency" className="border-0">
        <AccordionTrigger className="py-2 text-xs text-mute">
          <span className="flex items-center gap-2">
            <Gauge className="size-3.5" aria-hidden />
            Latency (last turn)
            {latency?.total_ms !== undefined && <span className="text-volt">{latency.total_ms} ms to first audio</span>}
          </span>
        </AccordionTrigger>
        <AccordionContent className="pb-3">
          {latency ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
              {ROWS.map(([key, label]) => (
                <div key={key} className="flex justify-between gap-2">
                  <dt className="text-mute">{label}</dt>
                  <dd className="font-semibold text-ink tabular-nums">{latency[key] !== undefined ? `${latency[key]} ms` : "—"}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-xs text-mute">Send a message or speak to see the timings.</p>
          )}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
