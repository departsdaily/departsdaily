/* =====================================================================
   DEPARTS DAILY — LIVE BOARD DATA
   This file is REWRITTEN AUTOMATICALLY every hour by
   scripts/update_deals.py (GitHub Actions), using live fare data from
   the Travelpayouts/Aviasales search cache. Do not hand-edit.

   Field contract (read by index.html renderers):
     BOARD.updated  ISO timestamp of this refresh (ET) — board stamp
     BOARD.weekOf   label for the weekly top-10 board
     BOARD.weekExp  last day the weekly board shows before refresh
     deal.to        destination IATA code (must exist in ROUTES)
     deal.d1/d2     outbound / return dates (day-of-week is computed)
     deal.dep       exact departure time of the found fare (verified)
     deal.al        marketing airline name
     deal.stops     0 = nonstop
     deal.exp       last day this deal shows before auto-removal
   ===================================================================== */
const BOARD={
 updated:"2026-07-24T07:00:00-04:00",
 weekOf:"WEEK OF JUL 20–26",
 weekExp:"2026-07-26"
};
const DEALS={CLT:[
 {to:"LAS",city:"Las Vegas",price:87,d1:"2026-09-09",d2:"2026-09-14",dates:"SEP 9–14",al:"Spirit",stops:1,exp:"2026-07-28"},
 {to:"CUN",city:"Cancún",price:162,d1:"2026-09-15",d2:"2026-09-19",dates:"SEP 15–19",al:"American",stops:0,exp:"2026-07-28"},
 {to:"FLL",city:"Ft. Lauderdale",price:59,d1:"2026-08-26",d2:"2026-08-30",dates:"AUG 26–30",al:"Spirit",stops:0,exp:"2026-07-27"},
 {to:"MIA",city:"Miami",price:69,d1:"2026-09-03",d2:"2026-09-07",dates:"SEP 3–7",al:"American",stops:0,exp:"2026-07-27"},
 {to:"MCO",city:"Orlando",price:82,d1:"2026-08-20",d2:"2026-08-24",dates:"AUG 20–24",al:"Frontier",stops:0,exp:"2026-07-27"}]};
const DEALS_WEEK={CLT:[
 {to:"FLL",city:"Ft. Lauderdale",price:59,d1:"2026-08-26",d2:"2026-08-30",dates:"AUG 26–30",al:"Spirit",stops:0},
 {to:"MIA",city:"Miami",price:69,d1:"2026-09-03",d2:"2026-09-07",dates:"SEP 3–7",al:"American",stops:0},
 {to:"NYC",city:"New York City",price:78,d1:"2026-09-10",d2:"2026-09-13",dates:"SEP 10–13",al:"American",stops:0},
 {to:"MCO",city:"Orlando",price:82,d1:"2026-08-20",d2:"2026-08-24",dates:"AUG 20–24",al:"Frontier",stops:0},
 {to:"LAS",city:"Las Vegas",price:118,d1:"2026-09-09",d2:"2026-09-14",dates:"SEP 9–14",al:"Spirit",stops:1},
 {to:"DEN",city:"Denver",price:128,d1:"2026-09-16",d2:"2026-09-20",dates:"SEP 16–20",al:"Frontier",stops:0},
 {to:"CUN",city:"Cancún",price:162,d1:"2026-09-15",d2:"2026-09-19",dates:"SEP 15–19",al:"American",stops:0},
 {to:"NAS",city:"Nassau",price:218,d1:"2026-09-22",d2:"2026-09-26",dates:"SEP 22–26",al:"American",stops:0},
 {to:"PUJ",city:"Punta Cana",price:289,d1:"2026-10-06",d2:"2026-10-11",dates:"OCT 6–11",al:"American",stops:0},
 {to:"LHR",city:"London",price:498,d1:"2026-10-13",d2:"2026-10-20",dates:"OCT 13–20",al:"American",stops:0}]};
