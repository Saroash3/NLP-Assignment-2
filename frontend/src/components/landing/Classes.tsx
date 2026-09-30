import { motion } from "framer-motion";
import { Clock, Moon, User } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TIMETABLE } from "@/data/gymData";
import { cn } from "@/lib/utils";
import { Section, SectionHeading } from "./Section";

export function Classes() {
  return (
    <Section id="classes">
      <SectionHeading
        eyebrow="Weekly timetable"
        title={
          <>
            17 classes. <span className="text-volt">3 branches.</span>
          </>
        }
        subtitle="Book in the Zor Fitness app or on WhatsApp up to 48 hours ahead (Elite: 72 hours). Included with Plus, Elite and Ladies Only."
      />

      <Tabs defaultValue="f7">
        <TabsList aria-label="Branch">
          {TIMETABLE.map((b) => (
            <TabsTrigger key={b.id} value={b.id}>
              {b.branch}
            </TabsTrigger>
          ))}
        </TabsList>
        {TIMETABLE.map((b) => (
          <TabsContent key={b.id} value={b.id}>
            <div className="grid gap-3 md:grid-cols-2">
              {b.classes.map((c, i) => (
                <motion.div
                  key={c.name + c.days}
                  initial={{ opacity: 0, x: -16 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.35, delay: i * 0.04 }}
                  className="group flex items-center justify-between gap-4 rounded-2xl border border-line bg-surface p-5 transition-colors hover:border-volt/60"
                >
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-ink">{c.name}</h3>
                      {c.ladies && (
                        <span className="rounded-full bg-emerald/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-emerald">
                          Ladies
                        </span>
                      )}
                    </div>
                    <p className="mt-1 flex items-center gap-1.5 text-sm text-mute">
                      <User className="size-3.5" /> {c.coach} · {c.level}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-display text-xl tracking-wide text-volt">{c.days}</p>
                    <p className={cn("flex items-center justify-end gap-1 text-sm text-mute")}>
                      <Clock className="size-3.5" /> {c.time}
                    </p>
                  </div>
                </motion.div>
              ))}
            </div>
          </TabsContent>
        ))}
      </Tabs>

      <div className="mt-8 flex items-start gap-3 rounded-2xl border border-emerald/30 bg-emerald/5 p-5 text-sm text-mute">
        <Moon className="mt-0.5 size-4 shrink-0 text-emerald" />
        <p>
          <span className="font-semibold text-ink">Ramadan:</span> 5 night classes after taraweeh (Zor Circuit, HIIT Blast, Spin
          Night, Ladies Yoga Flow, Ladies Zumba). No classes during the Friday 1:00–2:15pm Jumu'ah break.
        </p>
      </div>
    </Section>
  );
}
