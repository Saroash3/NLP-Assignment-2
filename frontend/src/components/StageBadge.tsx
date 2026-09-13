const STAGE_LABELS: Record<string, string> = {
  greeting: "Greeting",
  information_gathering: "Gathering Info",
  action: "Booking",
  confirmation: "Confirming",
  closing: "Closing",
};

export function StageBadge({ stage }: { stage: string }) {
  return <span className="stage-badge">{STAGE_LABELS[stage] ?? stage}</span>;
}
