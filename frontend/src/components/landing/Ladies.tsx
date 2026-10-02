import { Baby, CameraOff, Clock, ShieldCheck, Waves } from "lucide-react";
import { Reveal, Section, SectionHeading } from "./Section";

const POINTS = [
  { icon: Clock, title: "Separate timings", text: "F-7 Ladies Floor Mon–Sat 7am–10pm & Sun 10am–6pm · Bahria Ladies Wing Mon–Sat 8am–9pm · G-11 ladies hours 10:30am–4:30pm." },
  { icon: ShieldCheck, title: "Female coaches & staff", text: "Sana Iftikhar, Mahnoor Rizvi, Farah Naz and Hira Saleem. Sports hijab and full-length activewear welcome." },
  { icon: Waves, title: "Ladies pool session", text: "Mon–Sat 11am–3pm at F-7 with a female lifeguard. Burkinis welcome." },
  { icon: Baby, title: "Kids' play area", text: "Free for children aged 3–8 of any female member training on the F-7 Ladies Floor, up to 90 minutes." },
  { icon: CameraOff, title: "Strict privacy", text: "No photography or filming on the Ladies Floor, in the Ladies Wing or in changing rooms -- not even selfies." },
];

export function Ladies() {
  return (
    <div id="ladies" className="border-y border-line bg-[radial-gradient(70%_60%_at_20%_0%,rgba(16,185,129,0.12),transparent_70%)]">
      <Section>
        <div className="grid gap-12 lg:grid-cols-[1fr_1.2fr] lg:items-start">
          <SectionHeading
            accent="emerald"
            eyebrow="Women-only spaces"
            title={
              <>
                Her floor. <span className="text-emerald">Her rules.</span>
              </>
            }
            subtitle="Every branch has a women-only option, with its own entrance or hours. The Ladies Only plan (PKR 10,000 / month) covers all three."
          />
          <ul className="grid gap-4 sm:grid-cols-2">
            {POINTS.map((p, i) => (
              <Reveal key={p.title} delay={i * 0.06} className={i === 0 ? "sm:col-span-2" : undefined}>
                <li className="h-full rounded-3xl border border-emerald/20 bg-surface p-6">
                  <p.icon className="mb-4 size-6 text-emerald" />
                  <h3 className="font-semibold text-ink">{p.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-mute">{p.text}</p>
                </li>
              </Reveal>
            ))}
          </ul>
        </div>
      </Section>
    </div>
  );
}
