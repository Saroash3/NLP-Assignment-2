/**
 * Landing-page copy for trainers and facilities. Mirrors facts_source_of_truth.md
 * (the same file the RAG documents are written from), so the marketing page never
 * says something Nova can't back up from its documents. Static display data only --
 * there is no API call behind it.
 */
import type { LucideIcon } from "lucide-react";
import { Baby, Bike, Citrus, Dumbbell, Flame, ShowerHead, Waves, Users } from "lucide-react";

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
    name: "Hamza Qureshi",
    specialty: "Head Coach — Strength & Powerlifting",
    bio: "11 years coaching; runs Strength Foundations and the Saturday Powerlifting Club at F-7.",
    photoUrl: "https://randomuser.me/api/portraits/men/32.jpg",
  },
  {
    name: "Sana Iftikhar",
    specialty: "Women's Strength & PCOS",
    bio: "Former national-level netball player; leads the Ladies Strength & PCOS Program on the F-7 Ladies Floor.",
    photoUrl: "https://randomuser.me/api/portraits/women/44.jpg",
  },
  {
    name: "Mahnoor Rizvi",
    specialty: "Yoga, Pilates & Prenatal",
    bio: "500-hr yoga teacher and certified prenatal instructor; teaches at F-7 and the Bahria Ladies Wing.",
    photoUrl: "https://randomuser.me/api/portraits/women/65.jpg",
  },
  {
    name: "Farah Naz",
    specialty: "Zumba & Dance Fitness",
    bio: "Licensed Zumba instructor since 2018; runs ladies Zumba at F-7 and Bahria.",
    photoUrl: "https://randomuser.me/api/portraits/women/21.jpg",
  },
  {
    name: "Bilal Khattak",
    specialty: "HIIT & Boxing Conditioning",
    bio: "Former amateur boxer from Peshawar; coaches HIIT Blast at Bahria and Boxing Conditioning at F-7.",
    photoUrl: "https://randomuser.me/api/portraits/men/78.jpg",
  },
  {
    name: "Zeeshan Haider",
    specialty: "Spin & Endurance",
    bio: "Three-time Lahore Marathon finisher; runs the 24-bike spin studio at Bahria.",
    photoUrl: "https://randomuser.me/api/portraits/men/67.jpg",
  },
  {
    name: "Usman Tariq",
    specialty: "Functional Training & Kettlebells",
    bio: "6 years coaching; created Zor Circuit, our signature class at G-11.",
    photoUrl: "https://randomuser.me/api/portraits/men/45.jpg",
  },
  {
    name: "Hira Saleem",
    specialty: "Ladies Functional Training & Weight Loss",
    bio: "Certified PT; runs Ladies Zor Circuit and Stretch & Mobility during G-11 ladies hours.",
    photoUrl: "https://randomuser.me/api/portraits/women/33.jpg",
  },
  {
    name: "Ali Raza",
    specialty: "Bodybuilding & Muscle Gain",
    bio: "9 years coaching, provincial-level competitor; runs the Friday Muscle Building Clinic at F-7.",
    photoUrl: "https://randomuser.me/api/portraits/men/52.jpg",
  },
];

export interface FacilityInfo {
  name: string;
  description: string;
  icon: LucideIcon;
}

export const FACILITIES: FacilityInfo[] = [
  {
    name: "Heated Indoor Pool",
    description:
      "20m, 4-lane pool at F-7, heated to 28°C Nov–Mar. Ladies session Mon–Sat 11am–3pm; family swim Sundays.",
    icon: Waves,
  },
  {
    name: "Strength Floor",
    description:
      "6 power racks and a deadlift platform at F-7, 4 racks at Bahria, 2 at G-11. Dumbbells up to 50 kg.",
    icon: Dumbbell,
  },
  {
    name: "Ladies Floor & Wing",
    description:
      "A full women-only floor at F-7 and a separate Ladies Wing at Bahria, with female trainers and staff.",
    icon: Users,
  },
  {
    name: "Spin Studio & Boxing Zone",
    description: "24-bike spin studio plus 4 heavy bags and a ring at Bahria Town Phase 7.",
    icon: Bike,
  },
  {
    name: "Steam & Sauna",
    description: "Steam and sauna for men and ladies at F-7; steam rooms at Bahria. Max 15 minutes.",
    icon: Flame,
  },
  {
    name: "Kids' Play Area",
    description:
      "Free supervised play area (ages 3–8) on the F-7 Ladies Floor while mum trains, 10am–4pm.",
    icon: Baby,
  },
  {
    name: "Zor Juice Bar & Café",
    description: "Protein shakes, banana-date shakes, shikanjabeen and wraps. 10% off for members.",
    icon: Citrus,
  },
  {
    name: "Changing Rooms & Prayer Rooms",
    description:
      "Separate changing rooms with lockers and showers, plus separate prayer rooms at every branch.",
    icon: ShowerHead,
  },
];
