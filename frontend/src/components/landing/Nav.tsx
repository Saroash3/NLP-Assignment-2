import { useEffect, useState } from "react";
import { Menu, MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const LINKS = [
  { id: "plans", label: "Plans" },
  { id: "classes", label: "Classes" },
  { id: "coaches", label: "Coaches" },
  { id: "ladies", label: "Ladies" },
  { id: "branches", label: "Branches" },
  { id: "faq", label: "FAQ" },
];

export function Nav({ onChat, onNavigate }: { onChat: () => void; onNavigate: (id: string) => void }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-40 transition-colors duration-300",
        scrolled ? "border-b border-line bg-graphite/80 backdrop-blur-md" : "bg-transparent",
      )}
    >
      <nav className="mx-auto flex h-18 max-w-6xl items-center justify-between px-5 sm:px-8" aria-label="Main">
        <button onClick={() => onNavigate("top")} className="cursor-pointer font-display text-3xl tracking-wider text-ink">
          ZOR<span className="text-volt">.</span>
        </button>
        <ul className="hidden items-center gap-8 lg:flex">
          {LINKS.map((link) => (
            <li key={link.id}>
              <button
                onClick={() => onNavigate(link.id)}
                className="cursor-pointer text-sm font-medium text-mute transition-colors hover:text-volt"
              >
                {link.label}
              </button>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={onChat} className="hidden sm:inline-flex">
            <MessageCircle /> Chat with Nova
          </Button>
          {/* Mobile menu: a Radix Dialog (focus trap, Esc to close). */}
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu">
                <Menu className="size-5!" />
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogTitle className="font-display text-3xl tracking-wider">
                ZOR<span className="text-volt">.</span>
              </DialogTitle>
              <DialogDescription className="sr-only">Site navigation</DialogDescription>
              <ul className="mt-6 flex flex-col gap-1">
                {LINKS.map((link) => (
                  <li key={link.id}>
                    <DialogClose asChild>
                      <button
                        onClick={() => onNavigate(link.id)}
                        className="w-full cursor-pointer rounded-xl px-3 py-3 text-left text-lg font-medium hover:bg-surface-2 hover:text-volt"
                      >
                        {link.label}
                      </button>
                    </DialogClose>
                  </li>
                ))}
              </ul>
              <DialogClose asChild>
                <Button className="mt-6 w-full" onClick={onChat}>
                  <MessageCircle /> Chat with Nova
                </Button>
              </DialogClose>
            </DialogContent>
          </Dialog>
        </div>
      </nav>
    </header>
  );
}
