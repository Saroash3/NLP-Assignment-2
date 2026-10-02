/**
 * Landing-page data. Every price, time, name and rule here mirrors
 * facts_source_of_truth.md -- the same file the RAG documents were written
 * from -- so the page never says something Nova's documents contradict.
 * Static display data only (no API call).
 */
import type { LucideIcon } from "lucide-react";
import type { AvatarLook } from "@/components/landing/avatar";
import { Baby, Bike, Citrus, Dumbbell, Flame, ShowerHead, Users, Waves } from "lucide-react";

// ---------------------------------------------------------------- stats

export const STATS = [
  { label: "Branches", value: 3, suffix: "" },
  { label: "Weekly classes", value: 17, suffix: "" },
  { label: "Expert coaches", value: 9, suffix: "" },
  { label: "Training since", value: 2019, suffix: "" },
];

// ---------------------------------------------------------------- plans (PKR)

export type Term = "1" | "3" | "6" | "12";
export const TERMS: { id: Term; label: string; note: string }[] = [
  { id: "1", label: "Monthly", note: "+ PKR 10,000 one-time admission" },
  { id: "3", label: "3 months", note: "10% off · + PKR 10,000 admission" },
  { id: "6", label: "6 months", note: "15% off · admission waived" },
  { id: "12", label: "12 months", note: "25% off · admission waived · 2 instalments" },
];

export interface Plan {
  name: string;
  tagline: string;
  prices: Record<Term, number>;
  /** Standard only: the cheaper G-11 price for the same term. */
  g11Prices?: Record<Term, number>;
  features: string[];
  highlight?: boolean;
  ladies?: boolean;
}

export const PLANS: Plan[] = [
  {
    name: "Standard",
    tagline: "Your home branch, your pace",
    prices: { "1": 12000, "3": 32400, "6": 61200, "12": 108000 },
    g11Prices: { "1": 8000, "3": 21600, "6": 40800, "12": 72000 },
    features: ["Gym floor at your home branch", "Free day lockers", "1 InBody scan per quarter", "Classes as drop-in (PKR 1,000)"],
  },
  {
    name: "Plus",
    tagline: "Every branch, every class",
    prices: { "1": 16000, "3": 43200, "6": 81600, "12": 144000 },
    features: ["All 3 branches", "All group classes", "Steam & sauna (F-7), steam (Bahria)", "1 InBody scan per month"],
    highlight: true,
  },
  {
    name: "Elite",
    tagline: "Coaching, nutrition & the pool",
    prices: { "1": 26000, "3": 70200, "6": 132600, "12": 234000 },
    features: ["Everything in Plus", "4 PT sessions / month", "Monthly nutrition consult", "Pool access + 2 guest passes / month"],
  },
  {
    name: "Ladies Only",
    tagline: "Women-only floors at all 3",
    prices: { "1": 10000, "3": 27000, "6": 51000, "12": 90000 },
    features: ["Ladies Floor, Ladies Wing & G-11 ladies hours", "All ladies classes", "Ladies steam + pool session", "Female coaches & staff"],
    ladies: true,
  },
];

// ---------------------------------------------------------------- timetable

export interface ClassSlot {
  name: string;
  days: string;
  time: string;
  coach: string;
  level: string;
  ladies?: boolean;
}

export const TIMETABLE: { branch: string; id: string; classes: ClassSlot[] }[] = [
  {
    branch: "F-7 Islamabad",
    id: "f7",
    classes: [
      { name: "Strength Foundations", days: "Mon · Wed", time: "7:00–8:00pm", coach: "Hamza Qureshi", level: "Beginner" },
      { name: "Powerlifting Club", days: "Sat", time: "9:00–11:00am", coach: "Hamza Qureshi", level: "Intermediate+" },
      { name: "Boxing Conditioning", days: "Tue · Thu", time: "8:00–9:00pm", coach: "Bilal Khattak", level: "All levels" },
      { name: "Muscle Building Clinic", days: "Fri", time: "6:00–7:00pm", coach: "Ali Raza", level: "Intermediate" },
      { name: "Ladies Strength & PCOS", days: "Mon · Wed · Fri", time: "11:00am–12:00pm", coach: "Sana Iftikhar", level: "All levels", ladies: true },
      { name: "Yoga Flow", days: "Tue · Thu", time: "10:00–11:00am", coach: "Mahnoor Rizvi", level: "All levels", ladies: true },
      { name: "Prenatal Yoga", days: "Sat", time: "11:00am–12:00pm", coach: "Mahnoor Rizvi", level: "Doctor's clearance", ladies: true },
      { name: "Zumba", days: "Mon · Wed", time: "5:00–6:00pm", coach: "Farah Naz", level: "All levels", ladies: true },
    ],
  },
  {
    branch: "G-11 Islamabad",
    id: "g11",
    classes: [
      { name: "Zor Circuit", days: "Mon · Wed · Fri", time: "7:00–7:45am", coach: "Usman Tariq", level: "All levels" },
      { name: "Ladies Zor Circuit", days: "Tue · Thu", time: "11:00–11:45am", coach: "Hira Saleem", level: "All levels", ladies: true },
      { name: "Ladies Stretch & Mobility", days: "Sat", time: "12:00–12:45pm", coach: "Hira Saleem", level: "All levels", ladies: true },
    ],
  },
  {
    branch: "Bahria Town Ph 7",
    id: "bahria",
    classes: [
      { name: "Spin", days: "Mon · Wed · Fri", time: "6:30–7:15am", coach: "Zeeshan Haider", level: "All levels" },
      { name: "Spin Night", days: "Tue · Thu", time: "7:30–8:15pm", coach: "Zeeshan Haider", level: "All levels" },
      { name: "Sunday Long Ride", days: "Sun", time: "11:00am–12:00pm", coach: "Zeeshan Haider", level: "Intermediate" },
      { name: "HIIT Blast", days: "Tue · Thu · Sat", time: "6:00–6:45pm", coach: "Bilal Khattak", level: "Intermediate" },
      { name: "Pilates", days: "Mon · Wed", time: "10:00–11:00am", coach: "Mahnoor Rizvi", level: "All levels", ladies: true },
      { name: "Zumba", days: "Tue · Thu", time: "4:00–5:00pm", coach: "Farah Naz", level: "All levels", ladies: true },
    ],
  },
];

// ---------------------------------------------------------------- coaches

export interface TrainerInfo {
  name: string;
  specialty: string;
  branch: string;
  bio: string;
  /** Illustrated portrait settings (see components/landing/avatar.ts): South Asian skin tones,
   *  black hair, beards and hijab, so the fictional coaches look Pakistani. */
  look: AvatarLook;
  female?: boolean;
}

export const TRAINERS: TrainerInfo[] = [
  { name: "Hamza Qureshi", specialty: "Head Coach · Strength & Powerlifting", branch: "F-7", bio: "11 years coaching. Rule: form before weight -- three clean reps before adding a plate.", look: { skin: "d08b5b", top: "shortFlat", beard: "beardMedium", clothing: "shirtCrewNeck", clothesColor: "262e33" } },
  { name: "Sana Iftikhar", specialty: "Women's Strength & PCOS", branch: "F-7 Ladies Floor", bio: "Former national-level netball player; built the Ladies Strength & PCOS Program.", look: { skin: "edb98a", top: "hijab", hijabColor: "25557c", clothing: "shirtScoopNeck", clothesColor: "3c4f5c" }, female: true },
  { name: "Mahnoor Rizvi", specialty: "Yoga, Pilates & Prenatal", branch: "F-7 · Bahria", bio: "500-hour yoga teacher and certified prenatal instructor.", look: { skin: "edb98a", top: "straight01", clothing: "shirtVNeck", clothesColor: "929598" }, female: true },
  { name: "Farah Naz", specialty: "Zumba & Dance Fitness", branch: "F-7 · Bahria", bio: "Licensed Zumba instructor since 2018 -- Latin, Bollywood and Punjabi beats.", look: { skin: "d08b5b", top: "bun", clothing: "hoodie", clothesColor: "ff488e" }, female: true },
  { name: "Bilal Khattak", specialty: "HIIT & Boxing", branch: "Bahria · F-7", bio: "Former amateur boxer from Peshawar. Pad work, footwork -- no sparring.", look: { skin: "edb98a", top: "shortRound", beard: "beardMajestic", clothing: "hoodie", clothesColor: "262e33" } },
  { name: "Zeeshan Haider", specialty: "Spin & Endurance", branch: "Bahria", bio: "Three-time Lahore Marathon finisher; runs the 24-bike spin studio.", look: { skin: "d08b5b", top: "theCaesarAndSidePart", beard: "beardLight", clothing: "shirtVNeck", clothesColor: "5199e4" } },
  { name: "Usman Tariq", specialty: "Kettlebells · Zor Circuit", branch: "G-11", bio: "Created Zor Circuit: 45 minutes, full body, small floor.", look: { skin: "ae5d29", top: "shortWaved", beard: "beardLight", clothing: "shirtCrewNeck", clothesColor: "3c4f5c" } },
  { name: "Hira Saleem", specialty: "Ladies Functional & Weight Loss", branch: "G-11 ladies hours", bio: "Certified PT who tracks fat loss with InBody, not just the scale.", look: { skin: "d08b5b", top: "hijab", hijabColor: "262e33", clothing: "collarAndSweater", clothesColor: "65c9ff" }, female: true },
  { name: "Ali Raza", specialty: "Bodybuilding & Muscle Gain", branch: "G-11 · F-7", bio: "9 years coaching; provincial-level physique competitor.", look: { skin: "ae5d29", top: "shavedSides", beard: "beardMedium", clothing: "shirtCrewNeck", clothesColor: "262e33" } },
];

// ---------------------------------------------------------------- facilities

export interface FacilityInfo {
  name: string;
  description: string;
  icon: LucideIcon;
}

export const FACILITIES: FacilityInfo[] = [
  { name: "Heated Indoor Pool", description: "20m, 4 lanes at F-7, heated to 28°C Nov–Mar. Ladies session Mon–Sat 11am–3pm; family swim Sundays.", icon: Waves },
  { name: "Strength Floor", description: "6 power racks and a deadlift platform at F-7, 4 racks at Bahria. Dumbbells up to 50 kg.", icon: Dumbbell },
  { name: "Spin Studio & Boxing", description: "24-bike spin studio plus 4 heavy bags and a ring at Bahria Town Phase 7.", icon: Bike },
  { name: "Steam & Sauna", description: "Steam and sauna for men and ladies at F-7; steam rooms at Bahria. 15-minute sessions.", icon: Flame },
  { name: "Kids' Play Area", description: "Free, supervised (ages 3–8) on the F-7 Ladies Floor while mum trains, 10am–4pm.", icon: Baby },
  { name: "Ladies Floor & Wing", description: "A whole women-only floor at F-7 and a separate Ladies Wing at Bahria.", icon: Users },
  { name: "Juice Bar & Café", description: "Whey shakes, banana-date shakes, shikanjabeen, wraps. 10% off for members.", icon: Citrus },
  { name: "Changing & Prayer Rooms", description: "Separate changing rooms with lockers and showers, plus prayer rooms at every branch.", icon: ShowerHead },
];

// ---------------------------------------------------------------- branches

export interface Branch {
  name: string;
  address: string;
  hours: { area: string; weekdays: string; sunday: string; ladies?: boolean }[];
  highlight: string;
}

export const BRANCHES: Branch[] = [
  {
    name: "F-7 Islamabad",
    address: "Plot 14, Jinnah Super Market, F-7 Markaz",
    hours: [
      { area: "Main floor", weekdays: "6:00am–11:00pm", sunday: "8:00am–8:00pm" },
      { area: "Ladies Floor", weekdays: "7:00am–10:00pm", sunday: "10:00am–6:00pm", ladies: true },
    ],
    highlight: "Flagship: pool, sauna, kids' area",
  },
  {
    name: "G-11 Islamabad",
    address: "2nd floor, Al-Hafeez Plaza, G-11 Markaz",
    hours: [
      { area: "Men", weekdays: "6:00–10:00am · 5:00–11:00pm", sunday: "Closed" },
      { area: "Ladies hours", weekdays: "10:30am–4:30pm", sunday: "Closed", ladies: true },
    ],
    highlight: "Compact · from PKR 8,000 / month",
  },
  {
    name: "Bahria Town Phase 7",
    address: "Plot 3, Spring North Commercial, Rawalpindi",
    hours: [
      { area: "Main floor", weekdays: "6:00am–12:00am", sunday: "10:00am–8:00pm" },
      { area: "Ladies Wing", weekdays: "8:00am–9:00pm", sunday: "Closed", ladies: true },
    ],
    highlight: "Spin studio · boxing zone · open till midnight",
  },
];

// ---------------------------------------------------------------- FAQ

export const FAQS: { q: string; a: string }[] = [
  { q: "How much is the admission fee?", a: "A one-time PKR 10,000. It is waived on 6- and 12-month plans, for corporate members, and with the Ramadan Fit Pass." },
  { q: "Can I freeze my membership?", a: "Monthly plans can't be frozen. 3-month plans get 7 days, 6-month plans 15 days and 12-month plans 30 days (minimum 7 days, requested 48 hours ahead). A medical freeze of up to 60 days is free with a doctor's certificate." },
  { q: "Can I bring a guest?", a: "Yes -- PKR 1,000 per visit. Guests must be 16+ with a CNIC; up to 4 guest visits per member per month, the same guest at most twice. No guests at G-11 Mon–Fri 6:00–9:00pm." },
  { q: "What's the dress code?", a: "Athletic wear, closed sports shoes and a towel. No jeans or chappals. Shalwar kameez isn't allowed on the gym floor but is fine in yoga and Pilates. Sports hijab and full-length athletic wear are welcome." },
  { q: "Is there a student discount?", a: "25% off Standard or Plus for ages 16–25 with a valid student ID, with off-peak entry (Mon–Fri 6:00am–4:00pm)." },
  { q: "What are the Ramadan timings?", a: "Men: 10:00am–3:00pm and 9:30pm–2:00am. Ladies: 11:00am–3:00pm and 9:00pm–12:00am. The pool is closed in Ramadan, and new members can join with the Ramadan Fit Pass: 1 month of Plus for PKR 11,000." },
  { q: "Kya ladies ke liye alag timing hai?", a: "Ji haan! F-7 Ladies Floor: Mon–Sat 7:00am–10:00pm, Itwar 10:00am–6:00pm. Bahria Ladies Wing: Mon–Sat 8:00am–9:00pm. G-11 mein ladies hours Mon–Sat 10:30am–4:30pm." },
];

// ---------------------------------------------------------------- member stories (illustrative)

export const STORIES: { quote: string; name: string; detail: string }[] = [
  { quote: "Sana's PCOS program finally made lifting make sense to me. Three mornings a week on the Ladies Floor, and my kids are in the play area while I train.", name: "Ayesha", detail: "Ladies Only · F-7" },
  { quote: "Spin Night at Bahria after work is the best 45 minutes of my week. Book early -- the 24 bikes go fast.", name: "Hassan", detail: "Plus · Bahria" },
  { quote: "Student plan at G-11 and Ladies Zor Circuit at 11am between lectures. PKR 6,000 a month and I'm stronger than ever.", name: "Maria", detail: "Student · G-11" },
  { quote: "Hamza fixed my deadlift form in two Powerlifting Club sessions. Form before weight -- he means it.", name: "Usama", detail: "Elite · F-7" },
];

// ---------------------------------------------------------------- contact

export const CONTACT = {
  uan: "051-111-967-348",
  whatsapp: "0333-5550967",
  email: "hello@zorfitness.pk",
};
