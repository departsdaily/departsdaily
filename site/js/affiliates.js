// ===== DEPARTS DAILY — AFFILIATE CONFIG =====
// Paste your IDs here as programs approve you. Every button on every
// destination page works today with untracked fallback links; each ID
// you add below upgrades that whole category to tracked (paid) links.
window.AFF = {
  tpMarker: "",        // Travelpayouts marker  -> monetizes flight links
  viatorPid: "",       // Viator PID (P00xxxxx) -> monetizes activity links
  bookingAid: "",      // Booking.com affiliate id -> hotel links
  discoverCarsRef: "", // DiscoverCars ref      -> car rental links
  ITEM_LINKS: {}       // paste per-item deep links: {"vegas-hotel-mid":"https://..."}
};
window.affLink = function(kind, fallback, itemKey){
  const A = window.AFF;
  if (itemKey && A.ITEM_LINKS[itemKey]) return A.ITEM_LINKS[itemKey];
  try {
    const u = new URL(fallback);
    if (kind==="hotel"  && A.bookingAid)      u.searchParams.set("aid", A.bookingAid);
    if (kind==="act"    && A.viatorPid)       u.searchParams.set("pid", A.viatorPid);
    if (kind==="car"    && A.discoverCarsRef) u.searchParams.set("a_aid", A.discoverCarsRef);
    if (kind==="flight" && A.tpMarker)        u.searchParams.set("marker", A.tpMarker);
    return u.toString();
  } catch(e){ return fallback; }
};
