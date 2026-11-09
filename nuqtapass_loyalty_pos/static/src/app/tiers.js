// The customer's tier on their current points card (NuqtaPass /customer `tier`), as the till shows it next to the
// customer: "Gold member · 10% cash-back" and "230 more points to Gold". Plain JS: tests/js/tiers.test.mjs.

const NAMES = ["BRONZE", "SILVER", "GOLD"];

const grouped = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");

/** { name, pct: "7.5%", next: { name, points: "3,800" } or null, color or null }, or null with no tier. */
export function tierParts(tier) {
    if (!tier || !NAMES.includes(tier.name)) {
        return null;
    }
    const pct = `${Number(Number(tier.cashbackPct || 0).toFixed(2))}%`;
    const next = tier.next && NAMES.includes(tier.next.name)
        ? { name: tier.next.name, points: grouped(tier.next.pointsToGo || 0) }
        : null;
    return { name: tier.name, pct, next, color: tier.color || null };
}
