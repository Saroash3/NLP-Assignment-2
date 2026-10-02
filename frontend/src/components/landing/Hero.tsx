import { lazy, Suspense, useLayoutEffect, useRef } from "react";
import { motion } from "framer-motion";
import gsap from "gsap";
import { ArrowDown, MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

// three.js + R3F are only downloaded when the hero actually renders (separate chunk).
const HeroCanvas = lazy(() => import("./HeroCanvas"));

export function Hero({
  onChat,
  onNavigate,
  reducedMotion,
}: {
  onChat: () => void;
  onNavigate: (id: string) => void;
  reducedMotion: boolean;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  // GSAP ScrollTrigger: the hero is pinned for a short scroll while the copy fades and lifts
  // and the 3D scene pushes back -- a scroll-driven transition into the page.
  useLayoutEffect(() => {
    if (reducedMotion) return;
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        scrollTrigger: { trigger: rootRef.current, start: "top top", end: "+=60%", scrub: true, pin: true },
      });
      tl.to(".hero-copy", { yPercent: -18, opacity: 0, ease: "none" }, 0).to(
        ".hero-canvas",
        { scale: 1.35, opacity: 0.25, ease: "none" },
        0,
      );
    }, rootRef);
    return () => ctx.revert();
  }, [reducedMotion]);

  const rise = (delay: number) => ({
    initial: { opacity: 0, y: 28 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.7, delay, ease: "easeOut" as const },
  });

  return (
    <div ref={rootRef} id="top" className="relative flex min-h-svh items-center overflow-hidden">
      {/* Glow + grid backdrop */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_70%_40%,rgba(200,255,61,0.12),transparent_70%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:64px_64px] [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_75%)]" />

      {/* Mobile: small, dimmed, top-right (never behind the text). Desktop: the right half. */}
      <div className="hero-canvas absolute -right-16 top-10 h-72 w-72 opacity-35 md:inset-y-0 md:right-0 md:top-0 md:h-full md:w-1/2 md:opacity-100">
        <Suspense fallback={null}>
          <HeroCanvas reducedMotion={reducedMotion} />
        </Suspense>
      </div>

      <div className="hero-copy relative z-10 mx-auto w-full max-w-6xl px-5 pt-24 sm:px-8">
        <motion.p {...rise(0)} className="mb-6 text-xs font-semibold uppercase tracking-[0.3em] text-volt">
          Islamabad · Rawalpindi · Since 2019
        </motion.p>
        <motion.h1
          {...rise(0.1)}
          className="font-display text-[clamp(4.5rem,15vw,11rem)] uppercase leading-[0.85] tracking-wide text-ink"
        >
          Train
          <br />
          with <span className="text-volt">Zor.</span>
        </motion.h1>
        <motion.p {...rise(0.25)} className="mt-8 max-w-md text-lg leading-relaxed text-mute">
          Three branches, 17 weekly classes, women-only floors -- and Nova, an AI front desk that answers
          from our own documents.
        </motion.p>
        <motion.div {...rise(0.4)} className="mt-10 flex flex-wrap gap-3">
          <Button size="lg" onClick={onChat}>
            <MessageCircle /> Chat with Nova
          </Button>
          <Button size="lg" variant="outline" onClick={() => onNavigate("plans")}>
            See plans <ArrowDown />
          </Button>
        </motion.div>
      </div>
    </div>
  );
}
