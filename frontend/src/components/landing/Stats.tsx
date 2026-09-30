import { useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { STATS } from "@/data/gymData";

/** Stat counters that count up (GSAP) the first time they scroll into view. */
export function Stats({ reducedMotion }: { reducedMotion: boolean }) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      gsap.utils.toArray<HTMLElement>(".stat-number").forEach((el, i) => {
        const target = STATS[i].value;
        if (reducedMotion) {
          el.textContent = String(target);
          return;
        }
        // Count 2019 up from 2000 (not 0), so the year doesn't spin through meaningless numbers.
        const counter = { val: target > 1000 ? target - 19 : 0 };
        gsap.to(counter, {
          val: target,
          duration: 1.6,
          ease: "power2.out",
          scrollTrigger: { trigger: el, start: "top 90%", once: true },
          onUpdate: () => {
            el.textContent = String(Math.round(counter.val));
          },
        });
      });
    }, rootRef);
    return () => ctx.revert();
  }, [reducedMotion]);

  return (
    <div ref={rootRef} className="border-y border-line bg-surface">
      <dl className="mx-auto grid max-w-6xl grid-cols-2 gap-px bg-line md:grid-cols-4">
        {STATS.map((stat) => (
          <div key={stat.label} className="bg-surface px-6 py-10 text-center">
            <dd className="font-display text-6xl text-volt sm:text-7xl">
              <span className="stat-number">0</span>
              {stat.suffix}
            </dd>
            <dt className="mt-2 text-xs font-semibold uppercase tracking-[0.2em] text-mute">{stat.label}</dt>
          </div>
        ))}
      </dl>
    </div>
  );
}
