import { motion } from "framer-motion";
import type { TrainerInfo } from "../data/gymData";

export function TrainerCard({ trainer }: { trainer: TrainerInfo }) {
  return (
    <motion.div
      className="trainer-card"
      whileHover={{ y: -6, borderColor: "var(--accent)" }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <img
        className="trainer-card__avatar"
        src={trainer.photoUrl}
        alt={`Portrait of ${trainer.name}`}
        loading="lazy"
        width={84}
        height={84}
      />
      <div className="trainer-card__name">{trainer.name}</div>
      <div className="trainer-card__specialty">{trainer.specialty}</div>
      <p className="trainer-card__bio">{trainer.bio}</p>
    </motion.div>
  );
}
