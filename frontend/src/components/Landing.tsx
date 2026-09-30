import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { motion } from "framer-motion";
import { HeroScene } from "./HeroScene";
import { TrainerCard } from "./TrainerCard";
import { FacilityCard } from "./FacilityCard";
import { TRAINERS, FACILITIES } from "../data/gymData";

gsap.registerPlugin(ScrollTrigger);

const STATS = [
  { label: "Branches", value: 3, suffix: "" },
  { label: "Weekly Classes", value: 17, suffix: "" },
  { label: "Expert Coaches", value: 9, suffix: "" },
  { label: "Years Running", value: 7, suffix: "" },
];

export function Landing({ onEnter }: { onEnter: () => void }) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const statRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const trainerSectionRef = useRef<HTMLDivElement | null>(null);
  const facilitySectionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // gsap.context scopes selectors to this component and gives us one
    // revert() to undo every tween/ScrollTrigger it created -- important
    // under React StrictMode, which mounts effects twice in dev.
    const ctx = gsap.context(() => {
      statRefs.current.forEach((el, i) => {
        if (!el) return;
        const counter = { val: 0 };
        gsap.to(counter, {
          val: STATS[i].value,
          duration: 1.6,
          delay: 0.3 + i * 0.15,
          ease: "power2.out",
          onUpdate: () => {
            el.textContent = Math.round(counter.val).toString();
          },
        });
      });

      gsap.fromTo(
        ".trainer-card",
        { opacity: 0, y: 40 },
        {
          opacity: 1,
          y: 0,
          duration: 0.7,
          stagger: 0.12,
          ease: "power3.out",
          scrollTrigger: {
            trigger: trainerSectionRef.current,
            start: "top 80%",
          },
        },
      );

      gsap.fromTo(
        ".facility-card",
        { opacity: 0, y: 30, scale: 0.96 },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.6,
          stagger: 0.08,
          ease: "power3.out",
          scrollTrigger: {
            trigger: facilitySectionRef.current,
            start: "top 82%",
          },
        },
      );
    }, rootRef);

    return () => ctx.revert();
  }, []);

  return (
    <div className="landing" ref={rootRef}>
      <section className="hero">
        <HeroScene />
        <div className="hero__content">
          <motion.span
            className="hero__eyebrow"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            ZOR FITNESS CLUB · ISLAMABAD & RAWALPINDI
          </motion.span>
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
          >
            Meet Nova, your 24/7 fitness front desk.
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
          >
            Classes, memberships, trainers, and bookings — answered instantly by an AI
            assistant running entirely on a local model.
          </motion.p>
          <motion.button
            className="cta-button"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3 }}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            onClick={onEnter}
          >
            Start Chatting
          </motion.button>
        </div>
      </section>

      <section className="stats">
        {STATS.map((s, i) => (
          <div className="stat" key={s.label}>
            <div className="stat__value">
              <span
                ref={(el) => {
                  statRefs.current[i] = el;
                }}
              >
                0
              </span>
              {s.suffix}
            </div>
            <div className="stat__label">{s.label}</div>
          </div>
        ))}
      </section>

      <section className="trainers" ref={trainerSectionRef}>
        <span className="section-eyebrow">Our Coaches</span>
        <h2>Meet the Team</h2>
        <p className="section-subtitle">
          Nine specialists, one front desk. Ask Nova about any of them.
        </p>
        <div className="trainer-grid">
          {TRAINERS.map((trainer) => (
            <TrainerCard key={trainer.name} trainer={trainer} />
          ))}
        </div>
      </section>

      <section className="facilities" ref={facilitySectionRef}>
        <span className="section-eyebrow">Inside Zor</span>
        <h2>Everything You Need, Under One Roof</h2>
        <p className="section-subtitle">
          Three branches: F-7 and G-11 Islamabad, and Bahria Town Phase 7 Rawalpindi.
        </p>
        <div className="facility-grid">
          {FACILITIES.map((facility) => (
            <FacilityCard key={facility.name} facility={facility} />
          ))}
        </div>
      </section>
    </div>
  );
}
