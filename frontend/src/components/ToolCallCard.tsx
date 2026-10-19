import { motion } from "framer-motion";
import { CheckCircle2, Loader2, Wrench, XCircle } from "lucide-react";
import type { ToolCallInfo } from "../types";
import { Card } from "@/components/ui/card";

const TITLES: Record<string, string> = {
  calculate_fitness_metrics: "Fitness calculator",
  lookup_nutrition: "Nutrition lookup",
  workout_schedule: "Workout schedule",
  user_profile: "Member profile",
};

function format(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.map(format).join("; ") : "none";
  if (value && typeof value === "object") {
    return Object.entries(value).map(([k, v]) => `${k.replace(/_/g, " ")}: ${format(v)}`).join(", ");
  }
  return String(value);
}

/** Inline card in the chat for one tool call: name, arguments, then the result (or error). */
export function ToolCallCard({ tool }: { tool: ToolCallInfo }) {
  const args = Object.entries(tool.arguments);
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="message-row message-row--assistant"
    >
      <Card className="w-full max-w-[min(70ch,78%)] rounded-2xl bg-surface-2 px-4 py-3 text-sm">
        <div className="flex items-center gap-2 font-semibold text-ink">
          <Wrench className="size-4 text-volt" aria-hidden />
          {TITLES[tool.name] ?? tool.name}
          <code className="text-xs font-normal text-mute">{tool.name}</code>
          <span className="ml-auto">
            {tool.status === "running" && <Loader2 className="size-4 animate-spin text-mute" aria-label="Running" />}
            {tool.status === "ok" && <CheckCircle2 className="size-4 text-emerald" aria-label="Done" />}
            {tool.status === "error" && <XCircle className="size-4 text-[#ff6b6b]" aria-label="Failed" />}
          </span>
        </div>
        {args.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {args.map(([key, value]) => (
              <span key={key} className="rounded-full border border-line px-2 py-0.5 text-xs text-mute">
                {key.replace(/_/g, " ")}: <span className="text-ink">{format(value)}</span>
              </span>
            ))}
          </div>
        )}
        {tool.status === "running" && <p className="mt-2 text-xs text-mute">Running…</p>}
        {tool.result !== undefined && (
          <p className={`mt-2 text-xs leading-relaxed ${tool.status === "error" ? "text-[#ffb4b4]" : "text-ink"}`}>
            {format(tool.result)}
          </p>
        )}
      </Card>
    </motion.div>
  );
}
