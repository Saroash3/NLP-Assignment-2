import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/** A page section with a consistent width and vertical rhythm. */
export function Section({ id, className, children }: { id?: string; className?: string; children: ReactNode }) {
  return (
    <section id={id} className={cn("relative mx-auto w-full max-w-6xl px-5 py-24 sm:px-8 sm:py-32", className)}>
      {children}
    </section>
  );
}

/** Eyebrow + big headline + subtitle, revealed when scrolled into view. */
export function SectionHeading({
  eyebrow,
  title,
  subtitle,
  accent = "volt",
}: {
  eyebrow: string;
  title: ReactNode;
  subtitle?: ReactNode;
  accent?: "volt" | "emerald";
}) {
  return (
    <motion.div
      className="mb-12 max-w-2xl"
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.6, ease: "easeOut" }}
    >
      <span
        className={cn(
          "mb-4 inline-block text-xs font-semibold uppercase tracking-[0.25em]",
          accent === "volt" ? "text-volt" : "text-emerald",
        )}
      >
        {eyebrow}
      </span>
      <h2 className="font-display text-5xl uppercase leading-[0.95] tracking-wide text-ink sm:text-6xl">{title}</h2>
      {subtitle && <p className="mt-5 text-base leading-relaxed text-mute sm:text-lg">{subtitle}</p>}
    </motion.div>
  );
}

/** Fade-and-rise wrapper for cards (whileInView = only animates when visible). */
export function Reveal({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.55, delay, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
