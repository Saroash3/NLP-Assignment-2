import { motion } from "framer-motion";
import type { FacilityInfo } from "../data/gymData";

export function FacilityCard({ facility }: { facility: FacilityInfo }) {
  const Icon = facility.icon;
  return (
    <motion.div
      className="facility-card"
      whileHover={{ y: -4, borderColor: "var(--accent)" }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <div className="facility-card__icon">
        <Icon size={22} strokeWidth={1.75} />
      </div>
      <div className="facility-card__name">{facility.name}</div>
      <p className="facility-card__description">{facility.description}</p>
    </motion.div>
  );
}
