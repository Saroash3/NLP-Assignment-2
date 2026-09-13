"""
Static domain knowledge for Apex Fitness Club.

Per the assignment's no-RAG constraint, this data is never queried at
inference time. It is rendered ONCE into the system prompt (see prompts.py)
and lives in the model's context window like any other instruction -- there
is no lookup step during a conversation. Keeping it as structured Python
(instead of one hand-written prompt string) makes it easy to unit test and
to edit without touching prompt-formatting logic.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Trainer:
    name: str
    specialty: str
    bio: str


@dataclass(frozen=True)
class MembershipPlan:
    name: str
    price_per_month: int
    features: list[str]


@dataclass(frozen=True)
class ClassSession:
    name: str
    days: str
    time: str
    trainer: str
    level: str


@dataclass(frozen=True)
class Facility:
    name: str
    description: str


GYM_NAME = "Apex Fitness Club"

OPENING_HOURS = "Mon-Fri 5:00am-11:00pm, Sat-Sun 7:00am-9:00pm"
ADDRESS = "482 Riverside Drive, Springfield"

TRAINERS: list[Trainer] = [
    Trainer(
        "Jordan Reyes",
        "Strength & Conditioning",
        "8 years coaching competitive powerlifters; leads Strength Foundations and the "
        "Saturday Powerlifting Club.",
    ),
    Trainer(
        "Maya Chen",
        "Yoga & Mobility",
        "Former physiotherapist turned instructor, certified in Vinyasa and Yin yoga.",
    ),
    Trainer(
        "Diego Santos",
        "HIIT & Spin",
        "Ex-competitive cyclist; high-energy coach for Spin Cycle and HIIT Blast.",
    ),
    Trainer(
        "Aisha Bello",
        "Nutrition & Weight Management",
        "Certified nutritionist and personal trainer; runs the 1-on-1 nutrition consultations "
        "included with Elite membership.",
    ),
    Trainer(
        "Liam O'Connor",
        "Boxing & Functional Fitness",
        "Ex-amateur boxer; leads Saturday Boxing Conditioning.",
    ),
]

MEMBERSHIP_PLANS: list[MembershipPlan] = [
    MembershipPlan(
        "Basic",
        29,
        [
            "Gym floor access, off-peak hours only (6am-4pm weekdays)",
            "Standard equipment & locker room access",
            "1 guest pass per month",
        ],
    ),
    MembershipPlan(
        "Premium",
        59,
        [
            "24/7 full gym floor access, every day",
            "All group classes included",
            "2 guest passes per month",
            "Towel service",
        ],
    ),
    MembershipPlan(
        "Elite",
        99,
        [
            "Everything in Premium",
            "4 personal training sessions per month",
            "1 nutrition consultation per month with Aisha Bello",
            "Priority class booking",
            "Sauna & spa access",
            "Unlimited guest passes",
        ],
    ),
]

CLASS_SCHEDULE: list[ClassSession] = [
    ClassSession("Yoga Flow", "Mon/Wed/Fri", "7:00-8:00am", "Maya Chen", "All levels"),
    ClassSession("Spin Cycle", "Tue/Thu", "6:30-7:15am", "Diego Santos", "All levels"),
    ClassSession(
        "Strength Foundations", "Tue/Thu", "5:30-6:30pm", "Jordan Reyes", "Beginner-Intermediate"
    ),
    ClassSession("HIIT Blast", "Mon/Wed/Fri", "6:00-6:45pm", "Diego Santos", "Intermediate"),
    ClassSession("Boxing Conditioning", "Sat", "10:00-11:00am", "Liam O'Connor", "All levels"),
    ClassSession("Powerlifting Club", "Sat", "12:00-1:30pm", "Jordan Reyes", "Advanced"),
    ClassSession("Yin Yoga & Stretch", "Sun", "9:00-10:00am", "Maya Chen", "All levels"),
]

FACILITIES: list[Facility] = [
    Facility(
        "Swimming Pool",
        "Heated indoor 25m lap pool plus a separate warm-water recovery pool, open during all "
        "gym hours.",
    ),
    Facility(
        "Free Weights & Strength Zone",
        "Full range of barbells and dumbbells up to 150lb, power racks, and lifting platforms.",
    ),
    Facility(
        "Cardio Deck",
        "Treadmills, ellipticals, rowers, and stationary bikes, each with a personal screen.",
    ),
    Facility(
        "Functional Training Zone",
        "Kettlebells, battle ropes, TRX straps, and a sprint turf lane for functional workouts.",
    ),
    Facility(
        "Sauna & Steam Room",
        "A quiet space to unwind and recover after a workout.",
    ),
    Facility(
        "Locker Rooms & Showers",
        "Full locker rooms with showers; towels provided for Premium and Elite members.",
    ),
    Facility(
        "Juice & Recovery Bar",
        "Protein shakes, smoothies, and light snacks available on-site.",
    ),
    Facility(
        "Free On-Site Parking",
        "Free parking available for all members during gym hours.",
    ),
]

POLICIES: dict[str, str] = {
    "cancellation": (
        "Month-to-month membership, no long-term contract. Cancel anytime with 30 days' "
        "written notice via the front desk or member portal; no cancellation fee."
    ),
    "freeze": (
        "Freeze a membership for up to 2 months per year for a $10/month freeze fee (waived "
        "with medical documentation). Request at least 5 days before the next billing date."
    ),
    "guest_pass": (
        "Guests must be accompanied by the member and show photo ID. One guest visit per "
        "guest per month, subject to the member's plan allowance."
    ),
    "trial": (
        "Prospective members get one free 1-day trial pass. After that, single day passes "
        "are $15."
    ),
    "age_policy": (
        "Members must be 16+ for unsupervised gym floor access. Ages 13-15 are welcome with "
        "a supervising guardian."
    ),
    "refunds": (
        "Membership fees are non-refundable, except pro-rated refunds for documented medical "
        "issues or relocation more than 50 miles away."
    ),
    "payment": (
        "Monthly auto-billing to a major debit/credit card. No enrollment fee, no long-term "
        "contract."
    ),
}


def render_knowledge_base_text() -> str:
    """Render all domain data into one clean text block for the system prompt."""
    lines: list[str] = [
        f"GYM: {GYM_NAME}",
        f"ADDRESS: {ADDRESS}",
        f"OPENING HOURS: {OPENING_HOURS}",
        "",
    ]

    lines.append("MEMBERSHIP PLANS:")
    for plan in MEMBERSHIP_PLANS:
        features = "; ".join(plan.features)
        lines.append(f"- {plan.name} (${plan.price_per_month}/month): {features}")
    lines.append("")

    lines.append("TRAINERS:")
    for t in TRAINERS:
        lines.append(f"- {t.name} - {t.specialty}. {t.bio}")
    lines.append("")

    lines.append("WEEKLY CLASS SCHEDULE:")
    for c in CLASS_SCHEDULE:
        lines.append(f"- {c.name}: {c.days} {c.time}, taught by {c.trainer} ({c.level})")
    lines.append("")

    lines.append("FACILITIES:")
    for f in FACILITIES:
        lines.append(f"- {f.name}: {f.description}")
    lines.append("")

    lines.append("POLICIES:")
    for key, text in POLICIES.items():
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {text}")

    return "\n".join(lines)
