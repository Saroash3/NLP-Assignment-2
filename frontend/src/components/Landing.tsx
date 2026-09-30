import { MotionConfig, useReducedMotion } from "framer-motion";
import { Nav } from "./landing/Nav";
import { Hero } from "./landing/Hero";
import { Stats } from "./landing/Stats";
import { Plans } from "./landing/Plans";
import { Classes } from "./landing/Classes";
import { Coaches } from "./landing/Coaches";
import { Facilities } from "./landing/Facilities";
import { Ladies } from "./landing/Ladies";
import { Stories } from "./landing/Stories";
import { Branches } from "./landing/Branches";
import { Faq } from "./landing/Faq";
import { Footer } from "./landing/Footer";
import { useSmoothScroll } from "./landing/useSmoothScroll";

/**
 * The marketing landing page. Every "Chat with Nova" button calls onEnter, which switches
 * App to the (unchanged) chat screen. Motion: Framer Motion for reveals/hover, GSAP
 * ScrollTrigger for the pinned hero, counters and parallax, Lenis for smooth scrolling --
 * all reduced or switched off when the user prefers reduced motion.
 */
export function Landing({ onEnter }: { onEnter: () => void }) {
  const reducedMotion = useReducedMotion() ?? false;
  const scrollToSection = useSmoothScroll(reducedMotion);

  return (
    <MotionConfig reducedMotion="user">
      <div className="min-h-svh bg-graphite font-sans text-ink antialiased">
        <Nav onChat={onEnter} onNavigate={scrollToSection} />
        <main>
          <Hero onChat={onEnter} onNavigate={scrollToSection} reducedMotion={reducedMotion} />
          <Stats reducedMotion={reducedMotion} />
          <Plans onChat={onEnter} />
          <Classes />
          <Coaches />
          <Facilities reducedMotion={reducedMotion} />
          <Ladies />
          <Stories reducedMotion={reducedMotion} />
          <Branches />
          <Faq />
        </main>
        <Footer onChat={onEnter} />
      </div>
    </MotionConfig>
  );
}
