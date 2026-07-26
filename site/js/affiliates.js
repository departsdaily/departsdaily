/* =====================================================================
   DEPARTS DAILY — AFFILIATE ENGINE
   =====================================================================
   THIS IS THE ONLY FILE YOU EDIT TO GET PAID.

   Every booking link on the site — the deal board rows, the "book the
   rest of the trip" tiles, and every recommended hotel & tour on the
   city guide pages — is wired through this file. Right now the links
   point to the travel sites WITHOUT tracking (so the site works today).
   As each affiliate program approves you, paste your IDs/links below
   and every link site-wide instantly becomes a paying link.

   WHERE TO GET EACH ID:
   1. TRAVELPAYOUTS — travelpayouts.com (free). Your "marker" number is
      in your profile. Join brands inside it: Aviasales/WayAway
      (flights), Hotellook (hotels), GetYourGuide/Viator (tours),
      DiscoverCars (cars), Kiwitaxi (transfers), Airalo (eSIM),
      insurance brands, etc.
   2. EXPEDIA GROUP — partner.expediagroup.com (hotels, packages, cars).
      Use their link builder; paste generated links below.
   3. VIATOR — viator.com affiliate program (or via Travelpayouts).
   4. AMAZON ASSOCIATES — affiliate-program.amazon.com (travel gear).

   WORKS WITH ANY NETWORK: every "" field below accepts a full link
   from ANY affiliate network — CJ (cj.com), Impact (impact.com),
   Awin (awin.com), ShareASale, FlexOffers, Partnerize, or a brand's
   own program (Booking.com, Klook, SafetyWing...). Whatever tracked
   URL a network's link generator gives you, paste it in — the engine
   doesn't care which network it came from. Sign up with as many as
   you want; more networks = more brands to monetize.
   ===================================================================== */

const AFF = {

  /* ------------------------------------------------------------------
     STEP 1 — your Travelpayouts marker (a number, e.g. "654321").
     Once set, EVERY deal-board row automatically becomes a tracked
     Aviasales flight search with your marker — flights monetized. */
  tpMarker: "755800",       // Joe's Travelpayouts marker (trs=554658 is the Drive project id)

  /* ------------------------------------------------------------------
     STEP 2 — your Amazon Associates tracking ID (e.g. "departsdaily-20").
     Every gear link automatically gets ?tag= added. */
  amazonTag: "departsdaily-20",

  /* ------------------------------------------------------------------
     STEP 3 — your Viator partner ID (PID, looks like "P00123456") if
     you join Viator directly. Leave blank if using pasted links. */
  viatorPid: "",            // e.g. "P00123456"

  /* ------------------------------------------------------------------
     STEP 4 — generic links from your networks' link generators.
     Whatever you paste REPLACES the default link for that button type
     across the whole site. Leave "" to keep untracked defaults. */
  LINKS: {
    flights: "",    // e.g. tp.media/r?... link to Aviasales/WayAway
    hotels: "",     // Hotellook (Travelpayouts) or Expedia link
    tours: "",      // Viator or GetYourGuide affiliate link
    cars: "",       // e.g. DiscoverCars via Travelpayouts
    insurance: "",  // e.g. VisitorsCoverage via Travelpayouts, or SafetyWing direct
    esim: "",       // e.g. Airalo via Travelpayouts
    transfers: ""   // e.g. Kiwitaxi via Travelpayouts, or Welcome Pickups direct
  },

  /* ------------------------------------------------------------------
     STEP 5 — per-city links (higher conversion). Generate city-level
     links (e.g. Hotellook "Las Vegas hotels", Viator "Las Vegas") and
     paste them here. Falls back to LINKS above, then to defaults. */
  DEST_LINKS: {
    // vegas:   { flights: "", hotels: "", tours: "", cars: "" },
    // cancun:  { flights: "", hotels: "", tours: "" },
    // miami:   { flights: "", hotels: "", tours: "" },
    // orlando: { flights: "", hotels: "", tours: "" },
    // fll:     { flights: "", hotels: "", tours: "" },
  },

  /* ------------------------------------------------------------------
     STEP 6 (the money-makers) — SPECIFIC hotel & tour picks on the
     city guide pages. Each has a slug (data-item="..." in the HTML).
     In your network's link builder, generate a deep link to THAT exact
     hotel/tour page and paste it here. Until then, buttons fall back
     to an untracked search for that hotel/tour. */
  ITEM_LINKS: {
    // --- New York City ---
    "new-york-hotel-budget": "",
    "new-york-hotel-mid": "",
    "new-york-hotel-splurge": "",
    "new-york-tour-1": "",
    "new-york-tour-2": "",
    "new-york-tour-3": "",
    // --- Boston ---
    "boston-hotel-budget": "",
    "boston-hotel-mid": "",
    "boston-hotel-splurge": "",
    "boston-tour-1": "",
    "boston-tour-2": "",
    "boston-tour-3": "",
    // --- Miami ---
    "miami-hotel-budget": "",
    "miami-hotel-mid": "",
    "miami-hotel-splurge": "",
    "miami-tour-everglades": "",
    "miami-tour-boat": "",
    "miami-tour-havana": "",
    // --- Ft. Lauderdale ---
    "fll-hotel-budget": "",
    "fll-hotel-mid": "",
    "fll-hotel-splurge": "",
    "fll-tour-everglades": "",
    "fll-tour-watertaxi": "",
    "fll-tour-cruise": "",
    // --- Washington DC ---
    "washington-dc-hotel-budget": "",
    "washington-dc-hotel-mid": "",
    "washington-dc-hotel-splurge": "",
    "washington-dc-tour-1": "",
    "washington-dc-tour-2": "",
    "washington-dc-tour-3": "",
    // --- Chicago ---
    "chicago-hotel-budget": "",
    "chicago-hotel-mid": "",
    "chicago-hotel-splurge": "",
    "chicago-tour-1": "",
    "chicago-tour-2": "",
    "chicago-tour-3": "",
    // --- Dallas ---
    "dallas-hotel-budget": "",
    "dallas-hotel-mid": "",
    "dallas-hotel-splurge": "",
    "dallas-tour-1": "",
    "dallas-tour-2": "",
    "dallas-tour-3": "",
    // --- Orlando ---
    "orlando-hotel-budget": "",
    "orlando-hotel-mid": "",
    "orlando-hotel-splurge": "",
    "orlando-tour-parks": "",
    "orlando-tour-kennedy": "",
    "orlando-tour-airboat": "",
    // --- Los Angeles ---
    "los-angeles-hotel-budget": "",
    "los-angeles-hotel-mid": "",
    "los-angeles-hotel-splurge": "",
    "los-angeles-tour-1": "",
    "los-angeles-tour-2": "",
    "los-angeles-tour-3": "",
    // --- Denver ---
    "denver-hotel-budget": "",
    "denver-hotel-mid": "",
    "denver-hotel-splurge": "",
    "denver-tour-1": "",
    "denver-tour-2": "",
    "denver-tour-3": "",
    // --- Philadelphia ---
    "philadelphia-hotel-budget": "",
    "philadelphia-hotel-mid": "",
    "philadelphia-hotel-splurge": "",
    "philadelphia-tour-1": "",
    "philadelphia-tour-2": "",
    "philadelphia-tour-3": "",
    // --- Houston ---
    "houston-hotel-budget": "",
    "houston-hotel-mid": "",
    "houston-hotel-splurge": "",
    "houston-tour-1": "",
    "houston-tour-2": "",
    "houston-tour-3": "",
    // --- Las Vegas ---
    "vegas-hotel-budget": "",
    "vegas-hotel-mid": "",
    "vegas-hotel-splurge": "",
    "vegas-tour-canyon": "",
    "vegas-tour-heli": "",
    "vegas-tour-show": "",
    // --- Phoenix ---
    "phoenix-hotel-budget": "",
    "phoenix-hotel-mid": "",
    "phoenix-hotel-splurge": "",
    "phoenix-tour-1": "",
    "phoenix-tour-2": "",
    "phoenix-tour-3": "",
    // --- Tampa ---
    "tampa-hotel-budget": "",
    "tampa-hotel-mid": "",
    "tampa-hotel-splurge": "",
    "tampa-tour-1": "",
    "tampa-tour-2": "",
    "tampa-tour-3": "",
    // --- Nashville ---
    "nashville-hotel-budget": "",
    "nashville-hotel-mid": "",
    "nashville-hotel-splurge": "",
    "nashville-tour-1": "",
    "nashville-tour-2": "",
    "nashville-tour-3": "",
    // --- New Orleans ---
    "new-orleans-hotel-budget": "",
    "new-orleans-hotel-mid": "",
    "new-orleans-hotel-splurge": "",
    "new-orleans-tour-1": "",
    "new-orleans-tour-2": "",
    "new-orleans-tour-3": "",
    // --- San Francisco ---
    "san-francisco-hotel-budget": "",
    "san-francisco-hotel-mid": "",
    "san-francisco-hotel-splurge": "",
    "san-francisco-tour-1": "",
    "san-francisco-tour-2": "",
    "san-francisco-tour-3": "",
    // --- Seattle ---
    "seattle-hotel-budget": "",
    "seattle-hotel-mid": "",
    "seattle-hotel-splurge": "",
    "seattle-tour-1": "",
    "seattle-tour-2": "",
    "seattle-tour-3": "",
    // --- Austin ---
    "austin-hotel-budget": "",
    "austin-hotel-mid": "",
    "austin-hotel-splurge": "",
    "austin-tour-1": "",
    "austin-tour-2": "",
    "austin-tour-3": "",
    // --- Cancún ---
    "cancun-hotel-budget": "",
    "cancun-hotel-mid": "",
    "cancun-hotel-splurge": "",
    "cancun-tour-chichen": "",
    "cancun-tour-catamaran": "",
    "cancun-tour-cenotes": "",
    // --- Punta Cana ---
    "punta-cana-hotel-budget": "",
    "punta-cana-hotel-mid": "",
    "punta-cana-hotel-splurge": "",
    "punta-cana-tour-1": "",
    "punta-cana-tour-2": "",
    "punta-cana-tour-3": "",
    // --- Montego Bay ---
    "montego-bay-hotel-budget": "",
    "montego-bay-hotel-mid": "",
    "montego-bay-hotel-splurge": "",
    "montego-bay-tour-1": "",
    "montego-bay-tour-2": "",
    "montego-bay-tour-3": "",
    // --- Nassau ---
    "nassau-hotel-budget": "",
    "nassau-hotel-mid": "",
    "nassau-hotel-splurge": "",
    "nassau-tour-1": "",
    "nassau-tour-2": "",
    "nassau-tour-3": "",
    // --- Aruba ---
    "aruba-hotel-budget": "",
    "aruba-hotel-mid": "",
    "aruba-hotel-splurge": "",
    "aruba-tour-1": "",
    "aruba-tour-2": "",
    "aruba-tour-3": "",
    // --- San Juan, PR ---
    "san-juan-hotel-budget": "",
    "san-juan-hotel-mid": "",
    "san-juan-hotel-splurge": "",
    "san-juan-tour-1": "",
    "san-juan-tour-2": "",
    "san-juan-tour-3": "",
    // --- Grand Cayman ---
    "grand-cayman-hotel-budget": "",
    "grand-cayman-hotel-mid": "",
    "grand-cayman-hotel-splurge": "",
    "grand-cayman-tour-1": "",
    "grand-cayman-tour-2": "",
    "grand-cayman-tour-3": "",
    // --- London ---
    "london-hotel-budget": "",
    "london-hotel-mid": "",
    "london-hotel-splurge": "",
    "london-tour-1": "",
    "london-tour-2": "",
    "london-tour-3": "",
    // --- Paris ---
    "paris-hotel-budget": "",
    "paris-hotel-mid": "",
    "paris-hotel-splurge": "",
    "paris-tour-1": "",
    "paris-tour-2": "",
    "paris-tour-3": "",
    // --- Rome ---
    "rome-hotel-budget": "",
    "rome-hotel-mid": "",
    "rome-hotel-splurge": "",
    "rome-tour-1": "",
    "rome-tour-2": "",
    "rome-tour-3": "",
  }
};

/* =====================================================================
   Engine — no need to edit below this line
   ===================================================================== */

// Untracked defaults so every button works before you're approved.
const AFF_DEFAULTS = {
  flights:   (d) => d ? "https://www.aviasales.com/" : "https://www.aviasales.com/",
  hotels:    (d) => d ? `https://search.hotellook.com/?destination=${encodeURIComponent(d)}` : "https://search.hotellook.com/",
  tours:     (d) => d ? `https://www.viator.com/searchResults/all?text=${encodeURIComponent(d)}` : "https://www.viator.com/",  // TRUST-FIRST: Viator (unpaid until program unlocks at ~3mo traffic, then Drive auto-monetizes). Europe guide picks use Tiqets (paid now).
  cars:      ()  => "https://www.qeeq.com/",            // QEEQ = ACTIVE program (DiscoverCars locked for now)
  insurance: ()  => "https://ektatraveling.com/",       // EKTA = ACTIVE program, 25% (VisitorsCoverage locked for now)
  esim:      ()  => "https://www.airalo.com/",
  transfers: ()  => "https://kiwitaxi.com/"
};

function affResolve(type, destKey, destName) {
  const dl = AFF.DEST_LINKS[destKey];
  if (dl && dl[type]) return dl[type];
  if (AFF.LINKS[type]) return AFF.LINKS[type];
  if (type === "tours" && AFF.viatorPid) {
    const base = destName
      ? `https://www.viator.com/searchResults/all?text=${encodeURIComponent(destName)}`
      : "https://www.viator.com/";
    return `${base}${base.includes("?") ? "&" : "?"}pid=${AFF.viatorPid}&mcid=42383&medium=link`;
  }
  const fb = AFF_DEFAULTS[type];
  return fb ? fb(destName) : "#";
}

/* Deal-board flight deep link.
   With a Travelpayouts marker → tracked Aviasales search for the exact
   route & dates (this is how the board itself gets monetized).
   Without → falls back to Google Flights (untracked). */
function affFlightSearch(orig, dest, d1, d2) {
  if (AFF.tpMarker) {
    const ddmm = (s) => { const p = s.split("-"); return p[2] + p[1]; };
    return `https://www.aviasales.com/search/${orig}${ddmm(d1)}${dest}${ddmm(d2)}1?marker=${encodeURIComponent(AFF.tpMarker)}`;
  }
  return `https://www.google.com/travel/flights?q=Flights%20from%20${orig}%20to%20${dest}%20on%20${d1}%20through%20${d2}`;
}

function affAmazon(url) {
  if (!AFF.amazonTag) return url;
  try {
    const u = new URL(url);
    u.searchParams.set("tag", AFF.amazonTag);
    return u.toString();
  } catch (e) { return url; }
}

document.addEventListener("DOMContentLoaded", () => {
  // Travel buttons: <a data-aff="hotels" data-dest="vegas" data-dest-name="Las Vegas">
  // Item picks add data-item="vegas-hotel-mid" + data-fallback="https://...".
  document.querySelectorAll("[data-aff]").forEach((el) => {
    const type = el.getAttribute("data-aff");
    const destKey = el.getAttribute("data-dest") || "";
    const destName = el.getAttribute("data-dest-name") || "";
    const itemKey = el.getAttribute("data-item") || "";
    const fallback = el.getAttribute("data-fallback") || "";
    let href;
    if (itemKey && AFF.ITEM_LINKS[itemKey]) href = AFF.ITEM_LINKS[itemKey];
    else if (itemKey && fallback) href = fallback;
    else href = affResolve(type, destKey, destName);
    el.setAttribute("href", href);
    el.setAttribute("target", "_blank");
    el.setAttribute("rel", "sponsored noopener");
  });

  // Amazon gear links: <a data-amzn="https://www.amazon.com/dp/ASIN">
  document.querySelectorAll("[data-amzn]").forEach((el) => {
    el.setAttribute("href", affAmazon(el.getAttribute("data-amzn")));
    el.setAttribute("target", "_blank");
    el.setAttribute("rel", "sponsored noopener");
  });
});
