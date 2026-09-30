import { useMemo } from "react";
import useEmblaCarousel from "embla-carousel-react";
import Autoplay from "embla-carousel-autoplay";
import { Quote } from "lucide-react";
import { STORIES } from "@/data/gymData";
import { Section, SectionHeading } from "./Section";

/**
 * Member stories in an Embla carousel with autoplay (off for reduced motion).
 * Clearly labelled as illustrative: Zor Fitness Club is fictional, so these are not real reviews.
 */
export function Stories({ reducedMotion }: { reducedMotion: boolean }) {
  const plugins = useMemo(
    () => (reducedMotion ? [] : [Autoplay({ delay: 5000, stopOnInteraction: true, stopOnMouseEnter: true })]),
    [reducedMotion],
  );
  const [emblaRef] = useEmblaCarousel({ loop: true, align: "start" }, plugins);

  return (
    <Section id="stories" className="overflow-hidden">
      <SectionHeading
        eyebrow="Member stories"
        title={
          <>
            Stronger, <span className="text-volt">every week</span>
          </>
        }
        subtitle="Illustrative stories -- Zor Fitness Club is a fictional gym built for this project."
      />
      <div className="cursor-grab active:cursor-grabbing" ref={emblaRef}>
        <div className="flex gap-5">
          {STORIES.map((s) => (
            <figure
              key={s.name}
              className="min-w-0 shrink-0 basis-[88%] rounded-3xl border border-line bg-surface p-8 sm:basis-[60%] lg:basis-[40%]"
            >
              <Quote className="mb-5 size-8 text-volt" />
              <blockquote className="text-lg leading-relaxed text-ink">{s.quote}</blockquote>
              <figcaption className="mt-6 text-sm">
                <span className="font-semibold text-ink">{s.name}</span>
                <span className="text-mute"> · {s.detail}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </Section>
  );
}
