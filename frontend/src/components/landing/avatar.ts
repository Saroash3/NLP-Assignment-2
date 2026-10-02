import { createAvatar } from "@dicebear/core";
import * as avataaars from "@dicebear/avataaars";

/**
 * Illustrated coach portraits (DiceBear "avataaars"), generated locally in the browser -- no
 * image requests. Used instead of photos: the coaches are fictional, and a real person's photo
 * would attach invented names and bios to a real individual. Each look is set per coach in
 * gymData.ts (South Asian skin tones, black hair, beards, hijab) so they read as Pakistani.
 */
export interface AvatarLook {
  skin: string; // avataaars skinColor hex, e.g. "d08b5b"
  top: string; // hairstyle or headwear, e.g. "shortFlat", "hijab", "bun"
  beard?: string; // e.g. "beardMedium"; omitted = clean-shaven
  clothing: string; // e.g. "hoodie"
  clothesColor: string;
  hijabColor?: string;
}

const cache = new Map<string, string>();

export function avatarUri(name: string, look: AvatarLook): string {
  const cached = cache.get(name);
  if (cached) return cached;
  const uri = createAvatar(avataaars, {
    seed: name,
    skinColor: [look.skin],
    top: [look.top] as never,
    hairColor: ["2c1b18"], // black
    hatColor: [look.hijabColor ?? "262e33"],
    facialHair: look.beard ? ([look.beard] as never) : undefined,
    facialHairProbability: look.beard ? 100 : 0,
    facialHairColor: ["2c1b18"],
    clothing: [look.clothing] as never,
    clothesColor: [look.clothesColor],
    accessoriesProbability: 0,
    eyes: ["default"],
    eyebrows: ["defaultNatural"],
    mouth: ["smile"],
  }).toDataUri();
  cache.set(name, uri);
  return uri;
}
