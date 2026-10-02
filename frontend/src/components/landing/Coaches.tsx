import { useCallback, useEffect, useState } from "react";
import useEmblaCarousel from "embla-carousel-react";
import { ArrowLeft, ArrowRight, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TRAINERS } from "@/data/gymData";
import { cn } from "@/lib/utils";
import { avatarUri } from "./avatar";
import { Section, SectionHeading } from "./Section";

/** Embla carousel of the 9 coaches (drag/swipe, arrow buttons, keyboard-focusable buttons). */
export function Coaches() {
  const [emblaRef, embla] = useEmblaCarousel({ align: "start", dragFree: true });
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(true);

  const update = useCallback(() => {
    if (!embla) return;
    setCanPrev(embla.canScrollPrev());
    setCanNext(embla.canScrollNext());
  }, [embla]);

  useEffect(() => {
    if (!embla) return;
    update();
    embla.on("select", update).on("reInit", update).on("scroll", update);
  }, [embla, update]);

  return (
    <Section id="coaches" className="overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <SectionHeading
          eyebrow="Coaches"
          title={
            <>
              Nine specialists, <span className="text-volt">one front desk</span>
            </>
          }
          subtitle="Female coaches lead every class on the Ladies Floor and Ladies Wing. PT: 8 sessions for PKR 18,000 with any coach."
        />
        <div className="mb-12 flex gap-2">
          <Button variant="outline" size="icon" aria-label="Previous coaches" disabled={!canPrev} onClick={() => embla?.scrollPrev()}>
            <ArrowLeft />
          </Button>
          <Button variant="outline" size="icon" aria-label="Next coaches" disabled={!canNext} onClick={() => embla?.scrollNext()}>
            <ArrowRight />
          </Button>
        </div>
      </div>

      <div className="cursor-grab active:cursor-grabbing" ref={emblaRef}>
        <div className="flex gap-5">
          {TRAINERS.map((t) => (
            <article
              key={t.name}
              className="group min-w-0 shrink-0 basis-[80%] overflow-hidden rounded-3xl border border-line bg-surface sm:basis-[45%] lg:basis-[30%]"
            >
              <div
                className={cn(
                  "relative h-64 overflow-hidden",
                  t.female
                    ? "bg-[radial-gradient(70%_70%_at_50%_75%,rgba(16,185,129,0.28),transparent_70%)]"
                    : "bg-[radial-gradient(70%_70%_at_50%_75%,rgba(200,255,61,0.22),transparent_70%)]",
                )}
              >
                <img
                  src={avatarUri(t.name, t.look)}
                  alt={`Illustration of ${t.name}`}
                  className="absolute inset-x-0 bottom-0 mx-auto h-[92%] w-auto transition duration-500 group-hover:scale-105"
                />
                <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-surface to-transparent" />
                <span className="absolute bottom-4 left-4 inline-flex items-center gap-1 rounded-full bg-graphite/80 px-3 py-1 text-xs text-ink backdrop-blur">
                  <MapPin className="size-3 text-volt" /> {t.branch}
                </span>
              </div>
              <div className="p-6">
                <h3 className="font-display text-2xl uppercase tracking-wide">{t.name}</h3>
                <p className={t.female ? "text-sm font-medium text-emerald" : "text-sm font-medium text-volt"}>{t.specialty}</p>
                <p className="mt-3 text-sm leading-relaxed text-mute">{t.bio}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </Section>
  );
}
