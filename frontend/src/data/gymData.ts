/**
 * Landing-page copy for trainers and facilities. Deliberately mirrors
 * backend/app/knowledge_base.py's TRAINERS/FACILITIES data (same names,
 * specialties, and bios) so the marketing page never says something Nova
 * herself doesn't know -- there is no API call backing this, it's static
 * display data for a static landing page, same as the backend's copy.
 */
import type { LucideIcon } from "lucide-react";
import { Car, Citrus, Dumbbell, Flame, ShowerHead, Waves, Zap, Activity } from "lucide-react";

export interface TrainerInfo {
  name: string;
  specialty: string;
  bio: string;
  /** randomuser.me is a placeholder-portrait service built for exactly this: realistic-looking
   *  photos with no real identity attached, meant to stand in for a person in a demo/mockup --
   *  not a photo of any actual named individual. */
  photoUrl: string;
}

export const TRAINERS: TrainerInfo[] = [
  {
    name: "Jordan Reyes",
    specialty: "Strength & Conditioning",
    bio: "8 years coaching competitive powerlifters; leads Strength Foundations and the Saturday Powerlifting Club.",
    photoUrl: "https://randomuser.me/api/portraits/men/32.jpg",
  },
  {
    name: "Maya Chen",
    specialty: "Yoga & Mobility",
    bio: "Former physiotherapist turned instructor, certified in Vinyasa and Yin yoga.",
    photoUrl: "https://randomuser.me/api/portraits/women/44.jpg",
  },
  {
    name: "Diego Santos",
    specialty: "HIIT & Spin",
    bio: "Ex-competitive cyclist; high-energy coach for Spin Cycle and HIIT Blast.",
    photoUrl: "https://randomuser.me/api/portraits/men/67.jpg",
  },
  {
    name: "Aisha Bello",
    specialty: "Nutrition & Weight Management",
    bio: "Certified nutritionist and personal trainer; runs the 1-on-1 nutrition consultations included with Elite membership.",
    photoUrl: "https://randomuser.me/api/portraits/women/21.jpg",
  },
  {
    name: "Liam O'Connor",
    specialty: "Boxing & Functional Fitness",
    bio: "Ex-amateur boxer; leads Saturday Boxing Conditioning.",
    photoUrl: "https://randomuser.me/api/portraits/men/78.jpg",
  },
];

export interface FacilityInfo {
  name: string;
  description: string;
  icon: LucideIcon;
}

export const FACILITIES: FacilityInfo[] = [
  {
    name: "Swimming Pool",
    description:
      "Heated indoor 25m lap pool plus a separate warm-water recovery pool, open during all gym hours.",
    icon: Waves,
  },
  {
    name: "Free Weights & Strength Zone",
    description:
      "Full range of barbells and dumbbells up to 150lb, power racks, and lifting platforms.",
    icon: Dumbbell,
  },
  {
    name: "Cardio Deck",
    description: "Treadmills, ellipticals, rowers, and stationary bikes, each with a personal screen.",
    icon: Activity,
  },
  {
    name: "Functional Training Zone",
    description: "Kettlebells, battle ropes, TRX straps, and a sprint turf lane for functional workouts.",
    icon: Zap,
  },
  {
    name: "Sauna & Steam Room",
    description: "A quiet space to unwind and recover after a workout.",
    icon: Flame,
  },
  {
    name: "Locker Rooms & Showers",
    description: "Full locker rooms with showers; towels provided for Premium and Elite members.",
    icon: ShowerHead,
  },
  {
    name: "Juice & Recovery Bar",
    description: "Protein shakes, smoothies, and light snacks available on-site.",
    icon: Citrus,
  },
  {
    name: "Free On-Site Parking",
    description: "Free parking available for all members during gym hours.",
    icon: Car,
  },
];
