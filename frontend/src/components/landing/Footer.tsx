import { motion } from "framer-motion";
import { Mail, MessageCircle, Phone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BRANCHES, CONTACT } from "@/data/gymData";

/** Final call to action + footer with contact details. */
export function Footer({ onChat }: { onChat: () => void }) {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="relative overflow-hidden rounded-[2rem] bg-volt px-8 py-16 text-graphite sm:px-14"
        >
          <p className="text-xs font-bold uppercase tracking-[0.3em]">Nova · AI front desk</p>
          <h2 className="mt-4 max-w-2xl font-display text-5xl uppercase leading-[0.95] sm:text-7xl">Questions? Ask Nova.</h2>
          <p className="mt-5 max-w-lg text-base font-medium text-graphite/75">
            Prices, timings, freeze rules, Ramadan hours -- answered in seconds from our own documents, with the sources shown.
          </p>
          <Button onClick={onChat} size="lg" className="mt-8 bg-graphite text-volt hover:shadow-none hover:brightness-125">
            <MessageCircle /> Start chatting
          </Button>
          <span className="pointer-events-none absolute -right-6 -bottom-16 font-display text-[16rem] leading-none text-graphite/10 select-none">
            ZOR
          </span>
        </motion.div>

        <div className="mt-20 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="font-display text-4xl tracking-wider">
              ZOR<span className="text-volt">.</span>
            </p>
            <p className="mt-3 text-sm text-mute">Zor Fitness Club -- "zor" means strength. Since 2019.</p>
          </div>
          <div>
            <h3 className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-mute">Contact</h3>
            <ul className="space-y-3 text-sm">
              <li className="flex items-center gap-2"><Phone className="size-4 text-volt" /> UAN {CONTACT.uan}</li>
              <li className="flex items-center gap-2"><MessageCircle className="size-4 text-volt" /> WhatsApp {CONTACT.whatsapp}</li>
              <li className="flex items-center gap-2"><Mail className="size-4 text-volt" /> {CONTACT.email}</li>
            </ul>
          </div>
          <div className="lg:col-span-2">
            <h3 className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-mute">Branches</h3>
            <ul className="space-y-3 text-sm">
              {BRANCHES.map((b) => (
                <li key={b.name}>
                  <span className="font-medium text-ink">{b.name}</span>
                  <span className="text-mute"> · {b.address}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="mt-16 border-t border-line pt-8 text-xs text-mute">
          Zor Fitness Club is a fictional gym created for a university assignment. Prices, people and contact details are
          invented.
        </p>
      </div>
    </footer>
  );
}
