import { useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { FACILITIES } from "@/data/gymData";
import { cn } from "@/lib/utils";
import { Section, SectionHeading } from "./Section";

/** Tile grid with GSAP ScrollTrigger parallax: alternate columns drift at different speeds. */
export function Facilities({ reducedMotion }: { reducedMotion: boolean }) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (reducedMotion) return;
    const ctx = gsap.context(() => {
      gsap.utils.toArray<HTMLElement>("[data-speed]").forEach((el) => {
        gsap.fromTo(
          el,
          { yPercent: Number(el.dataset.speed) },
          {
            yPercent: -Number(el.dataset.speed),
            ease: "none",
            scrollTrigger: { trigger: rootRef.current, start: "top bottom", end: "bottom top", scrub: true },
          },
        );
      });
    }, rootRef);
    return () => ctx.revert();
  }, [reducedMotion]);

  return (
    <div ref={rootRef}>
      <Section id="facilities">
        <SectionHeading
          eyebrow="Facilities"
          title={
            <>
              Built for <span className="text-volt">zor</span>
            </>
          }
          subtitle="Generators and UPS at every branch -- we stay open through load-shedding."
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FACILITIES.map((f, i) => {
            const Icon = f.icon;
            return (
              <div
                key={f.name}
                data-speed={i % 2 === 0 ? 6 : 14}
                className={cn(
                  "rounded-3xl border border-line bg-surface p-6 transition-colors hover:border-volt/60",
                  i === 0 && "lg:col-span-2",
                  i === 5 && "lg:col-span-2",
                )}
              >
                <div className="mb-5 inline-flex size-12 items-center justify-center rounded-2xl bg-volt/10 text-volt">
                  <Icon className="size-6" />
                </div>
                <h3 className="text-lg font-semibold text-ink">{f.name}</h3>
                <p className="mt-2 text-sm leading-relaxed text-mute">{f.description}</p>
              </div>
            );
          })}
        </div>
      </Section>
    </div>
  );
}
