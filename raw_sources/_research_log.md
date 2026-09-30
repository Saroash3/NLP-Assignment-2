# Research log (Phase 0, Step A)

Date: 2026-09-30. Method: web search, then one fetch per public page. No logins, no paywalls, and no repeated or aggressive fetching.
These notes are **inspiration only** (structure and price ranges). None of these gyms' facts are presented as our gym's facts.

## Used

| Gym / source | City | Page(s) | Notes file |
|---|---|---|---|
| Activo Fitness | Lahore (DHA Ph 4, Ph 6) | activofitness.co/fee-structure | activo_fitness_lahore_pricing_policies.txt |
| OXYGYM | Lahore (DHA Ph 4) | lhr.oxygymclub.com | oxygym_lahore_facilities_policies.txt |
| ABS Wellness Club | Lahore (Garden Town, Fortress) | abswellnessclub.com | abs_wellness_lahore_hours_policies.txt |
| Shoaib Gym | Lahore (12 branches) | shoaibgym.com/membership | shoaib_gym_lahore_membership.txt |
| Nutra Fit Studio | Lahore (Canal Road) | nutrafitgym.com | nutrafit_lahore_ladies_gym.txt |
| Vanguard Arena | Islamabad (F-10, I-8) | vanguardarena.com/gym-membership | vanguard_arena_islamabad_pricing.txt |
| Ginnastic Arena | Islamabad (I-8) | ginnasticarena.com rules page | ginnastic_arena_islamabad_rules.txt |
| Sky Fitness | Islamabad (Bahria) | skyfitness.pk | sky_fitness_islamabad_pricing.txt |
| Bahria Active | Rawalpindi/Islamabad | bahriaactive.com | bahria_active_rawalpindi_plans.txt |
| The Spa Bahria (ladies gym) | Rawalpindi | thespabahria.com/ladies-gym | the_spa_bahria_rawalpindi_ladies_gym.txt |
| Platinum Fitness | Karachi (Clifton) | platinumfitnesspk.com/womens-gym | platinum_fitness_karachi_womens_gym.txt |
| CORE | Karachi (Clifton) | corekarachi.pk | core_gym_karachi.txt |
| Shapes (third-party figures) | Karachi | he.com.pk listing (snippet) | shapes_karachi_pricing.txt |
| Islamabad market overview | Islamabad | islamabad.org.pk aggregator | islamabad_market_overview.txt |
| Faisalabad listing | Faisalabad | gymnavigator.com | faisalabad_listing.txt |
| Ramadan 2026 timings | All | propakistani.pk, wego (snippets) | ramadan_timings_2026.txt |
| Rules patterns | — | NUST SOPs (snippet), Ginnastic Arena | general_rules_patterns.txt |

## Failed or thin

- `dha.vibegym.pk/pricing-plans/`: DNS failure. Only a search snippet was used.
- `shapes.pk/membership-pricing/` and `shapes.pk/membership-pricing-dha-lahore-branch/`: HTTP 404.
- `sports.gov.pk` monthly package PDF: fetched but no text could be extracted (binary PDF). Not used.
- `citybook.pk` (Faisalabad ladies gym): DNS failure.
- Faisalabad in general: no published prices anywhere, so only area names were used.
- Gym-specific Ramadan schedules or offers: none found online. Our Ramadan schedule is invented from common practice.
- The aggregators (islamabad.org.pk, he.com.pk, blogpakistan.pk) are unverified and were used only for ranges.

## Patterns extracted (these drive `facts_source_of_truth.md`)

- **Monthly price bands (PKR):** budget 3k–5k, mid 6k–12k, premium 12k–20k.
- **Admission/registration fee:** common, 5k–20k. It is often **waived on 6/12-month prepaid plans** (Vanguard).
- **Prepay discounts:** a 3-month plan is roughly 10–15% cheaper per month, 6 months about 20%, 12 months about 30%.
- **Per-day/visit pass:** 1,000–2,000.
- **Separate women's provision:** a separate ladies floor or hall, or dedicated ladies hours (commonly around 10am–4/5pm), with female trainers and staff.
- **Sunday:** often closed or shorter hours.
- **Branch-based pricing:** the fee varies by area (Shoaib, Sky Fitness, Activo).
- **Freeze:** restrictive. Examples: 15 days/yr (ABS), 1 month for yearly members only with a Rs. 6,000 charge (OXYGYM), or no freeze at all (Activo).
- **Refunds / cancellation:** typically **non-refundable** and cancellation "not permitted".
- **Guests:** allowed for a fee, accompanied by the member, who is responsible for them; guests sign a health form.
- **Replacement card:** Rs. 1,000. The membership is non-transferable.
- **Discounts:** students, couples, corporate groups, and bank-card partnerships (CORE: up to 40% with JS Bank cards).
- **Add-ons:** PT billed separately (20k–23k/month), home training, physio, nutritionist, steam/sauna.
- **Programs popular with women:** PCOS/hormonal programs, postpartum, prenatal, Zumba, yoga, Pilates.
