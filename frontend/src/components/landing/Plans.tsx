import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PLANS, TERMS, type Term } from "@/data/gymData";
import { cn } from "@/lib/utils";
import { Reveal, Section, SectionHeading } from "./Section";

const pkr = (n: number) => n.toLocaleString("en-US");

/** Price that re-animates whenever the selected term changes. */
function Price({ value, term }: { value: number; term: Term }) {
  return (
    <AnimatePresence mode="popLayout" initial={false}>
      <motion.span
        key={`${term}-${value}`}
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -14 }}
        transition={{ duration: 0.25 }}
        className="inline-block"
      >
        {pkr(value)}
      </motion.span>
    </AnimatePresence>
  );
}

export function Plans({ onChat }: { onChat: () => void }) {
  const [term, setTerm] = useState<Term>("1");
  const termInfo = TERMS.find((t) => t.id === term)!;

  return (
    <Section id="plans">
      <SectionHeading
        eyebrow="Membership · PKR"
        title={
          <>
            Pick your <span className="text-volt">plan</span>
          </>
        }
        subtitle="Prices from our fee structure. Prepay and save up to 25% -- the admission fee is waived on 6- and 12-month plans."
      />

      <Tabs value={term} onValueChange={(v) => setTerm(v as Term)} className="mb-3">
        <TabsList aria-label="Billing term">
          {TERMS.map((t) => (
            <TabsTrigger key={t.id} value={t.id}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <p className="mb-10 text-sm text-mute">{termInfo.note}</p>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {PLANS.map((plan, i) => (
          <Reveal key={plan.name} delay={i * 0.08}>
            <motion.article
              whileHover={{ y: -8 }}
              transition={{ type: "spring", stiffness: 300, damping: 22 }}
              className={cn(
                "relative flex h-full flex-col rounded-3xl border p-6",
                plan.highlight ? "border-volt bg-surface shadow-[0_0_60px_-20px_rgba(200,255,61,0.5)]" : "border-line bg-surface",
              )}
            >
              {plan.highlight && (
                <span className="absolute -top-3 left-6 inline-flex items-center gap-1 rounded-full bg-volt px-3 py-1 text-xs font-bold text-graphite">
                  <Sparkles className="size-3" /> Most popular
                </span>
              )}
              {plan.ladies && (
                <span className="absolute -top-3 left-6 rounded-full bg-emerald px-3 py-1 text-xs font-bold text-graphite">
                  Women only
                </span>
              )}
              <h3 className="font-display text-3xl uppercase tracking-wide">{plan.name}</h3>
              <p className="mt-1 text-sm text-mute">{plan.tagline}</p>
              <p className="mt-6 font-display text-5xl tracking-wide text-ink">
                <span className="mr-1 align-top text-lg text-mute">PKR</span>
                <Price value={plan.prices[term]} term={term} />
              </p>
              <p className="mt-1 text-xs text-mute">
                {term === "1" ? "per month" : `for ${termInfo.label}`}
                {plan.g11Prices && (
                  <>
                    {" "}· F-7 / Bahria. <span className="text-volt">G-11: PKR {pkr(plan.g11Prices[term])}</span>
                  </>
                )}
              </p>
              <ul className="mt-6 flex-1 space-y-3">
                {plan.features.map((f) => (
                  <li key={f} className="flex gap-2 text-sm text-ink/90">
                    <Check className="mt-0.5 size-4 shrink-0 text-volt" />
                    {f}
                  </li>
                ))}
              </ul>
              <Button variant={plan.highlight ? "default" : "outline"} className="mt-8 w-full" onClick={onChat}>
                Ask Nova about {plan.name}
              </Button>
            </motion.article>
          </Reveal>
        ))}
      </div>
      <p className="mt-8 text-xs text-mute">
        Discounts (student 25%, couple 10%, family 15%, corporate 15–20%, senior 20%) don't stack -- one at a time.
      </p>
    </Section>
  );
}
