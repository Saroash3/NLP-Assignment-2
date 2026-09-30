import { useCallback, useEffect, useRef } from "react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

/**
 * Lenis smooth scrolling for the landing page, synced with GSAP ScrollTrigger:
 * Lenis is driven by GSAP's ticker, and every Lenis scroll tells ScrollTrigger to update.
 * Turned off entirely when the user prefers reduced motion. Destroyed on unmount, so the
 * chat screen always gets normal native scrolling.
 */
export function useSmoothScroll(reducedMotion: boolean) {
  const lenisRef = useRef<Lenis | null>(null);

  useEffect(() => {
    window.scrollTo(0, 0);
    if (reducedMotion) return;
    const lenis = new Lenis({ lerp: 0.1 });
    lenisRef.current = lenis;
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(tick);
      lenis.destroy();
      lenisRef.current = null;
    };
  }, [reducedMotion]);

  /** Smooth-scroll to a section id (used by the nav links). */
  return useCallback((id: string) => {
    const target = document.getElementById(id);
    if (!target) return;
    if (lenisRef.current) lenisRef.current.scrollTo(target, { offset: -72 });
    else target.scrollIntoView({ behavior: "auto", block: "start" });
  }, []);
}
