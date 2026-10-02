import { MapPin } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BRANCHES } from "@/data/gymData";
import { cn } from "@/lib/utils";
import { Reveal, Section, SectionHeading } from "./Section";

export function Branches() {
  return (
    <Section id="branches">
      <SectionHeading
        eyebrow="Branches & hours"
        title={
          <>
            Twin cities, <span className="text-volt">three floors of zor</span>
          </>
        }
        subtitle="All branches close Fridays 1:00–2:15pm for Jumu'ah. Last entry is 45 minutes before closing."
      />
      <div className="grid gap-5 lg:grid-cols-3">
        {BRANCHES.map((b, i) => (
          <Reveal key={b.name} delay={i * 0.08}>
            <Card className="h-full transition-colors hover:border-volt/60">
              <CardHeader>
                <CardTitle>{b.name}</CardTitle>
                <CardDescription className="flex items-start gap-1.5">
                  <MapPin className="mt-0.5 size-4 shrink-0 text-volt" /> {b.address}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wider text-mute">
                      <th className="pb-2 font-medium">Area</th>
                      <th className="pb-2 font-medium">Mon–Sat</th>
                      <th className="pb-2 font-medium">Sun</th>
                    </tr>
                  </thead>
                  <tbody>
                    {b.hours.map((h) => (
                      <tr key={h.area} className="border-t border-line align-top">
                        <td className={cn("py-3 pr-3 font-medium", h.ladies ? "text-emerald" : "text-ink")}>{h.area}</td>
                        <td className="py-3 pr-3 text-ink/90">{h.weekdays}</td>
                        <td className={cn("py-3", h.sunday === "Closed" ? "text-mute" : "text-ink/90")}>{h.sunday}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-4 rounded-2xl bg-surface-2 px-4 py-3 text-xs text-mute">{b.highlight}</p>
              </CardContent>
            </Card>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
