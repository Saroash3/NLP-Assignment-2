import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { FAQS } from "@/data/gymData";
import { Section, SectionHeading } from "./Section";

export function Faq() {
  return (
    <Section id="faq">
      <div className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
        <SectionHeading
          eyebrow="FAQ"
          title={
            <>
              Quick <span className="text-volt">answers</span>
            </>
          }
          subtitle="Anything else? Nova answers from all 80 Zor documents -- in English or Roman Urdu."
        />
        <Accordion type="single" collapsible className="w-full">
          {FAQS.map((f, i) => (
            <AccordionItem key={f.q} value={`q${i}`}>
              <AccordionTrigger>{f.q}</AccordionTrigger>
              <AccordionContent>{f.a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </Section>
  );
}
