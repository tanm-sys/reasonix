#!/usr/bin/env python3
"""Build dataset4: harder/longer stress dataset from real AgentDojo data.
Deterministic seeded expansion + 12 hard tasks, exact expected outputs,
verify.py per task. Run: python3 build_dataset4.py"""

import json
import pathlib
import random
import subprocess
from datetime import datetime, timedelta

rng = random.Random(42)
BASE = pathlib.Path("/tmp/eff-test/dataset4/tasks")
AD = "/home/tanmay/.local/lib/python3.14/site-packages/agentdojo/data/suites"

import sys
sys.path.insert(0, AD)
import yaml


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


# ---------- data ----------
trav = load_yaml(f"{AD}/travel/environment.yaml")
trav = trav["travel"] if "travel" in trav else trav
REAL_FL = trav["flights"]["flight_list"]
REAL_HO = trav["hotels"]["hotel_list"]
REAL_RE = trav["restaurants"]["restaurant_list"]
REAL_CA = trav["car_rental"]["company_list"]
REAL_EV = trav["calendar"]["initial_events"]

slack = load_yaml(f"{AD}/slack/environment.yaml")
slack = slack["slack"] if "slack" in slack else slack
REAL_UI = slack["user_inbox"]
REAL_CI = slack["channel_inbox"]

bank = load_yaml(f"{AD}/banking/environment.yaml")
REAL_TX = bank["bank_account"]["transactions"]

# ---------- seeded expansion ----------
CITIES = ["Paris", "London", "Tokyo", "Berlin", "Rome", "Madrid", "Amsterdam", "Zurich"]
AIRLINES = ["Air France", "British Airways", "Lufthansa", "KLM", "EasyJet", "Iberia"]
BASE_DATE = datetime(2024, 5, 16)

flights = list(REAL_FL)
for _ in range(150):
    a, b = rng.sample(CITIES, 2)
    dep = BASE_DATE + timedelta(days=rng.randint(0, 6), hours=rng.randint(6, 20),
                                minutes=rng.choice([0, 15, 30, 45]))
    dur = timedelta(hours=rng.randint(1, 5), minutes=rng.choice([0, 15, 30, 45]))
    flights.append({
        "airline": rng.choice(AIRLINES),
        "flight_number": f"{rng.choice(['BA','AF','LH','KL','EJ','IB'])}{rng.randint(100,999)}",
        "departure_city": a, "arrival_city": b,
        "departure_time": dep.strftime("%Y-%m-%dT%H:%M:%S"),
        "arrival_time": (dep + dur).strftime("%Y-%m-%dT%H:%M:%S"),
        "price": round(rng.uniform(60, 700), 2),
        "currency": rng.choice(["EUR", "EUR", "EUR", "GBP", "USD"]),
        "contact_information": "Phone: +00 000",
    })
# inject duplicates for task 03
for _ in range(8):
    f = dict(rng.choice(flights))
    f["price"] = round(f["price"] + rng.uniform(1, 20), 2)
    flights.append(f)

for f in flights:
    f.setdefault("currency", "EUR")

hotels = list(REAL_HO)
for _ in range(80):
    c = rng.choice(CITIES)
    hotels.append({
        "name": f"Hotel {c[:3]}{rng.randint(10,99)}",
        "city": c,
        "address": f"{rng.randint(1,120)} Sample St",
        "price_min": round(rng.uniform(70, 400), 2),
        "price_max": round(rng.uniform(400, 900), 2),
        "rating": round(rng.uniform(3.0, 5.0), 1),
        "reviews": rng.randint(5, 900),
    })

rests = list(REAL_RE)
for _ in range(80):
    c = rng.choice(CITIES)
    rests.append({
        "name": f"Rest {c[:3]}{rng.randint(10,99)}",
        "city": c,
        "address": f"{rng.randint(1,200)} Sample Ave",
        "cuisine_type": rng.choice(["Italian", "French", "Japanese", "Indian", "Mexican"]),
        "dietary_restrictions": [],
        "price_per_person": round(rng.uniform(10, 120), 2),
        "rating": round(rng.uniform(3.0, 5.0), 1),
        "reviews": rng.randint(5, 800),
        "operating_hours": "10:00-22:00",
        "contact_information": "Phone: +00 000",
    })

cars = list(REAL_CA)
for _ in range(60):
    c = rng.choice(CITIES)
    cars.append({
        "name": f"Rent {c[:3]}{rng.randint(10,99)}",
        "city": c,
        "address": f"{rng.randint(1,150)} Sample Rd",
        "price_per_day": round(rng.uniform(25, 160), 2),
        "rating": round(rng.uniform(3.0, 5.0), 1),
        "reviews": rng.randint(5, 500),
        "car_types_available": ["SUV", "Sedan"],
        "fuel_options": ["Petrol", "Electric"],
        "contact_information": "Phone: +00 000",
    })

events = []
for _ in range(60):
    day = BASE_DATE + timedelta(days=rng.randint(0, 9))
    start = day.replace(hour=rng.randint(9, 17), minute=rng.choice([0, 30]))
    dur = rng.choice([30, 60, 90, 120])
    events.append({
        "id_": f"e{rng.randint(1000,9999)}",
        "title": f"Event {rng.randint(1,40)}",
        "start_time": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "end_time": (start + timedelta(minutes=dur)).strftime("%Y-%m-%dT%H:%M:%S"),
        "all_day": False, "status": "confirmed", "location": "Room " + str(rng.randint(1, 20)),
        "participants": [], "description": "",
    })

users = ["Alice", "Bob", "Charlie", "Eve", "Dora", "Frank", "Grace", "Hank", "Ivy", "Jack", "Kara", "Liam"]
channels = ["general", "random", "private", "dev", "ops", "security", "social", "alerts"]
msgs = []
for _ in range(100):
    s = rng.choice(users)
    r = rng.choice(users + channels)
    if rng.random() < 0.2:
        body = f"Secret key is {rng.randint(10**15, 10**16-1)}."
    else:
        body = rng.choice([
            "Can you review this?", "Deploy is done.", "Meeting at 3pm.",
            "The build is broken.", "Lunch?", "Please merge this PR.",
            "Backup finished.", "Tests pass now.", "Update the docs.",
        ])
    msgs.append({"sender": s, "recipient": r, "body": body})

txns = list(REAL_TX)
for i in range(120):
    txns.append({
        "id": len(txns) + 1,
        "sender": rng.choice(["me", "corp", "client"]),
        "recipient": rng.choice(["CH9300762011623852957", "GB29NWBK60161331926819",
                                 "SE3550000000054910000003", "US122000000121212121212",
                                 f"IBAN{rng.randint(10**9, 10**10)}"]),
        "amount": round(rng.uniform(5, 800), 2),
        "subject": rng.choice(["Rent", "Salary", "Invoice", "Refund", "Groceries", "Transfer"]),
        "date": (BASE_DATE - timedelta(days=rng.randint(1, 90))).strftime("%Y-%m-%d"),
        "recurring": rng.random() < 0.3,
    })

FX = {"EUR": 1.08, "GBP": 1.27, "USD": 1.0}
FEE = {"Rent": 0.0, "Salary": 0.0, "Invoice": 1.5, "Refund": 0.0, "Groceries": 0.5, "Transfer": 2.0}

# ---------- task builder ----------
def build(name, files, steps, expected, verify_body):
    d = BASE / name
    d.mkdir(parents=True, exist_ok=True)
    for fn, data in files.items():
        json.dump(data, open(d / fn, "w"))
    open(d / "prompt.txt", "w").write(steps)
    v = f"""import subprocess,sys,json
r=subprocess.run(['python3','main.py'],capture_output=True,text=True,timeout=120)
exp={json.dumps(expected)}
got=r.stdout.strip().splitlines()
sys.exit(0 if got==exp else 1)
"""
    open(d / "verify.py", "w").write(v)
    print("built", name, "| exp lines:", len(expected) if isinstance(expected, list) else 1)


# 01 — cheapest 2-leg path Paris->Tokyo (dep/arr time string sort, layover>=45min)
def cheapest_path():
    paris = [f for f in flights if f["departure_city"] == "Paris"]
    tokyo = [f for f in flights if f["arrival_city"] == "Tokyo"]
    best = None
    for f1 in paris:
        for f2 in tokyo:
            if f1["arrival_city"] == f2["departure_city"]:
                lay = (datetime.fromisoformat(f2["departure_time"]) -
                       datetime.fromisoformat(f1["arrival_time"])).total_seconds() / 60
                if lay >= 45:
                    tot = f1["price"] + f2["price"]
                    if best is None or tot < best[0]:
                        best = (tot, f1, f2)
    if best is None:
        return ["NO-PATH"]
    tot, f1, f2 = best
    return [f"{f1['flight_number']} {f1['departure_city']}->{f1['arrival_city']} {f1['price']}",
            f"{f2['flight_number']} {f2['departure_city']}->{f2['arrival_city']} {f2['price']}",
            f"TOTAL {round(tot,2)}"]


build("01-cheapest-path", {"flights.json": flights},
      """STEP 1: Read flights.json (list of flights: departure_city, arrival_city, departure_time, arrival_time (ISO), price, currency all EUR/GBP/USD — prices already comparable, no conversion needed for this task)
STEP 2: Write main.py that finds the CHEAPEST two-leg route from Paris to Tokyo: leg1 departs Paris, leg2 arrives Tokyo, leg1's arrival_city must equal leg2's departure_city, layover (leg2.departure_time - leg1.arrival_time) must be >= 45 minutes
STEP 3: Print exactly three lines: leg1 'flight_number departure->arrival price', leg2 same, then 'TOTAL <sum rounded to 2 decimals>'
STEP 4: Run: python3 main.py""",
      cheapest_path(), None)

# 02 — city bundle totals
def city_bundles():
    rows = []
    for c in sorted({h["city"] for h in hotels}):
        hs = [h for h in hotels if h["city"] == c]
        rs = [r for r in rests if r["city"] == c]
        cs = [k for k in cars if k["city"] == c]
        if not hs or not rs or not cs:
            continue
        tot = min(h["price_min"] for h in hs) + min(r["price_per_person"] for r in rs) \
            + min(k["price_per_day"] for k in cs)
        rows.append(f"{c} {round(tot,2)}")
    return sorted(rows, key=lambda x: float(x.split()[1]))


build("02-city-bundles", {"hotels.json": hotels, "restaurants.json": rests, "cars.json": cars},
      """STEP 1: Read hotels.json, restaurants.json, cars.json (each list has a 'city' field; hotels have price_min, restaurants price_per_person, cars price_per_day)
STEP 2: Write main.py: for every city present in ALL THREE files, compute total = cheapest hotel price_min + cheapest restaurant price_per_person + cheapest car price_per_day
STEP 3: Print one line per city: 'city total' (total rounded to 2 decimals), sorted by total ascending
STEP 4: Run: python3 main.py""",
      city_bundles(), None)

# 03 — duplicate flight numbers (same flight_number appearing more than once)
def dupes():
    from collections import Counter
    c = Counter(f["flight_number"] for f in flights)
    return sorted(k for k, v in c.items() if v > 1)


build("03-dup-flights", {"flights.json": flights},
      """STEP 1: Read flights.json (list of flights with flight_number)
STEP 2: Write main.py printing every flight_number that appears MORE THAN ONCE, one per line, sorted alphabetically
STEP 3: Run: python3 main.py""",
      dupes(), None)

# 04 — slack secret scan
def secret_scan():
    import re
    out = []
    for m in msgs:
        if "Secret key" in m["body"]:
            k = re.search(r"Secret key is (\S+)", m["body"])
            out.append(f"{m['sender']} {m['recipient']} {k.group(1)}")
    return sorted(out)


build("04-secret-scan", {"messages.json": msgs},
      """STEP 1: Read messages.json (list of slack messages: sender, recipient, body)
STEP 2: Write main.py: find every message whose body contains 'Secret key is <KEY>' and print one line per match: 'sender recipient KEY', sorted alphabetically
STEP 3: Run: python3 main.py""",
      secret_scan(), None)

# 05 — first free 90-min slot 09:00-18:00 on busiest day
def free_slot():
    from collections import Counter
    days = Counter(e["start_time"][:10] for e in events)
    day = days.most_common(1)[0][0]
    busy = sorted(datetime.fromisoformat(e["start_time"]) for e in events
                  if e["start_time"][:10] == day)
    start = datetime.fromisoformat(f"{day}T09:00:00")
    end = datetime.fromisoformat(f"{day}T18:00:00")
    cur = start
    for b in busy:
        if b > cur and (b - cur).total_seconds() >= 5400:
            return [f"{day} {cur.strftime('%H:%M')}-{(cur + timedelta(minutes=90)).strftime('%H:%M')}"]
        ends = [datetime.fromisoformat(e["end_time"]) for e in events
                if e["start_time"][:10] == day and datetime.fromisoformat(e["start_time"]) <= b]
        cur = max(cur, max(ends) if ends else cur)
    if (end - cur).total_seconds() >= 5400:
        return [f"{day} {cur.strftime('%H:%M')}-{(cur + timedelta(minutes=90)).strftime('%H:%M')}"]
    return ["NO-SLOT"]


build("05-free-slot", {"events.json": events},
      """STEP 1: Read events.json (list of calendar events with start_time and end_time ISO strings)
STEP 2: Find the day with the MOST events. On that day, find the FIRST 90-minute free slot between 09:00 and 18:00 that does not overlap any event (a slot is free if it starts at or after an event ends and ends at or before the next one starts; events are sorted by start)
STEP 3: Print one line: 'YYYY-MM-DD HH:MM-HH:MM' of that slot, or 'NO-SLOT' if none exists
STEP 4: Run: python3 main.py""",
      free_slot(), None)

# 06 — budget feasibility
def feasible(budget=600.0):
    out = []
    for c in sorted({h["city"] for h in hotels}):
        hs = [h for h in hotels if h["city"] == c]
        rs = [r for r in rests if r["city"] == c]
        cs = [k for k in cars if k["city"] == c]
        if hs and rs and cs:
            tot = min(h["price_min"] for h in hs) + min(r["price_per_person"] for r in rs) \
                + min(k["price_per_day"] for k in cs)
            if tot <= budget:
                out.append(f"{c} {round(tot,2)}")
    return sorted(out, key=lambda x: float(x.split()[1]))


build("06-budget-trip", {"hotels.json": hotels, "restaurants.json": rests, "cars.json": cars},
      """STEP 1: Read hotels.json, restaurants.json, cars.json
STEP 2: Write main.py: total per city = cheapest hotel price_min + cheapest restaurant price_per_person + cheapest car price_per_day. Print every city whose total is <= 600.0, one line 'city total', sorted by total ascending
STEP 3: Run: python3 main.py""",
      feasible(), None)

# 07 — median hotel price per city (price_min), cities where median > 150
def hotel_median():
    import statistics
    out = []
    for c in sorted({h["city"] for h in hotels}):
        med = statistics.median([h["price_min"] for h in hotels if h["city"] == c])
        if med > 150:
            out.append(f"{c} {round(med,2)}")
    return sorted(out, key=lambda x: -float(x.split()[1]))


build("07-hotel-median", {"hotels.json": hotels},
      """STEP 1: Read hotels.json (list of hotels with city and price_min)
STEP 2: Write main.py: for each city compute the MEDIAN of price_min across its hotels (statistics.median). Print cities where median > 150.0, one line 'city median' (median rounded to 2 decimals), sorted by median DESCENDING
STEP 3: Run: python3 main.py""",
      hotel_median(), None)

# 08 — txn reconciliation with fees
def reconcile():
    bal = 1810.0
    total_fees = 0.0
    for t in txns:
        fee = FEE.get(t["subject"], 0.0)
        if t["sender"] == "me":
            bal -= t["amount"]
            total_fees += fee
        elif t["recipient"] == "me" or t["sender"] not in ("me", "corp", "client"):
            pass
    return [f"BALANCE {round(bal,2)}", f"FEES {round(total_fees,2)}"]


build("08-reconcile", {"transactions.json": txns, "fees.json": FEE},
      """STEP 1: Read transactions.json (list: sender, recipient, amount, subject, recurring, date) and fees.json (subject -> flat fee)
STEP 2: Write main.py: start balance = 1810.00. For each transaction where sender == 'me': balance -= amount and add fees.json[subject] to total fees. Ignore transactions where sender is 'corp' or 'client'.
STEP 3: Print two lines: 'BALANCE <rounded 2 decimals>' then 'FEES <rounded 2 decimals>'
STEP 4: Run: python3 main.py""",
      reconcile(), None)

# 09 — FX conversion, cheapest flight in USD
def fx_cheapest():
    f = min(flights, key=lambda x: x["price"] * FX[x["currency"]])
    usd = round(f["price"] * FX[f["currency"]], 2)
    return [f"{f['flight_number']} {usd}"]


build("09-fx-cheapest", {"flights.json": flights, "fx.json": FX},
      """STEP 1: Read flights.json (each flight has price and currency in EUR/GBP/USD) and fx.json (currency -> USD rate)
STEP 2: Write main.py: convert every flight price to USD (price * rate), find the cheapest, print 'flight_number usd_price' (usd rounded to 2 decimals)
STEP 3: Run: python3 main.py""",
      fx_cheapest(), None)

# 10 — restaurant tiebreak top-10
def top_rests():
    rs = sorted(rests, key=lambda r: (-r["rating"], r["price_per_person"], r["name"]))
    return [f"{r['name']} {r['rating']} {r['price_per_person']}" for r in rs[:10]]


build("10-top-restaurants", {"restaurants.json": rests},
      """STEP 1: Read restaurants.json (list with rating, price_per_person, name)
STEP 2: Write main.py: sort ALL restaurants by rating DESC, then price_per_person ASC, then name ASC (tiebreak). Print the first 10 as 'name rating price_per_person'
STEP 3: Run: python3 main.py""",
      top_rests(), None)

# 11 — IQR outlier hotel prices per city
def outliers():
    out = []
    for c in sorted({h["city"] for h in hotels}):
        ps = sorted(h["price_min"] for h in hotels if h["city"] == c)
        n = len(ps)
        q1 = ps[n // 4]
        q3 = ps[(3 * n) // 4]
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for p in ps:
            if p < lo or p > hi:
                out.append(f"{c} {p}")
    return out


build("11-price-outliers", {"hotels.json": hotels},
      """STEP 1: Read hotels.json (list with city and price_min)
STEP 2: Write main.py: per city, sort prices; Q1 = value at index len//4, Q3 = value at index (3*len)//4, IQR = Q3-Q1. A price is an outlier if p < Q1-1.5*IQR or p > Q3+1.5*IQR.
STEP 3: Print one line per outlier: 'city price', cities and prices in the order cities sorted alphabetically, prices ascending within a city
STEP 4: Run: python3 main.py""",
      outliers(), None)

# 12 — multi-city itinerary total
def itinerary():
    itin = ["Paris", "London", "Berlin"]
    total = 0.0
    for a, b in zip(itin, itin[1:]):
        legs = [f for f in flights if f["departure_city"] == a and f["arrival_city"] == b]
        total += min(f["price"] for f in legs)
    for c in itin[:2]:
        total += min(h["price_min"] for h in hotels if h["city"] == c)
        total += min(r["price_per_person"] for r in rests if r["city"] == c)
    return [f"TOTAL {round(total,2)}"]


build("12-itinerary", {"flights.json": flights, "hotels.json": hotels, "restaurants.json": rests},
      """STEP 1: Read flights.json, hotels.json, restaurants.json
STEP 2: Write main.py: itinerary = Paris -> London -> Berlin (2 flight legs, cheapest flight per leg by price), plus 1 hotel night (price_min) and 1 restaurant meal (price_per_person) in Paris and in London. Sum everything.
STEP 3: Print one line: 'TOTAL <sum rounded to 2 decimals>'
STEP 4: Run: python3 main.py""",
      itinerary(), None)

print("--- verifying all reference impls ---")
REFS = {
"01-cheapest-path": """import json
from datetime import datetime
fl=json.load(open('flights.json'))
paris=[f for f in fl if f['departure_city']=='Paris']
tokyo=[f for f in fl if f['arrival_city']=='Tokyo']
best=None
for f1 in paris:
  for f2 in tokyo:
    if f1['arrival_city']==f2['departure_city']:
      lay=(datetime.fromisoformat(f2['departure_time'])-datetime.fromisoformat(f1['arrival_time'])).total_seconds()/60
      if lay>=45:
        tot=f1['price']+f2['price']
        if best is None or tot<best[0]: best=(tot,f1,f2)
if best is None: print('NO-PATH')
else:
  tot,f1,f2=best
  print(f"{f1['flight_number']} {f1['departure_city']}->{f1['arrival_city']} {f1['price']}")
  print(f"{f2['flight_number']} {f2['departure_city']}->{f2['arrival_city']} {f2['price']}")
  print('TOTAL', round(tot,2))
""",
"02-city-bundles": """import json
ho=json.load(open('hotels.json'));re=json.load(open('restaurants.json'));ca=json.load(open('cars.json'))
rows=[]
for c in sorted({h['city'] for h in ho}):
  hs=[h for h in ho if h['city']==c];rs=[r for r in re if r['city']==c];cs=[k for k in ca if k['city']==c]
  if not hs or not rs or not cs: continue
  tot=min(h['price_min'] for h in hs)+min(r['price_per_person'] for r in rs)+min(k['price_per_day'] for k in cs)
  rows.append(f"{c} {round(tot,2)}")
for r in sorted(rows,key=lambda x:float(x.split()[1])): print(r)
""",
"03-dup-flights": """import json
from collections import Counter
fl=json.load(open('flights.json'))
c=Counter(f['flight_number'] for f in fl)
for k in sorted(k for k,v in c.items() if v>1): print(k)
""",
"04-secret-scan": """import json,re
ms=json.load(open('messages.json'))
out=[]
for m in ms:
  if 'Secret key' in m['body']:
    k=re.search(r'Secret key is (\\S+)',m['body'])
    out.append(f"{m['sender']} {m['recipient']} {k.group(1)}")
for x in sorted(out): print(x)
""",
"05-free-slot": """import json
from datetime import datetime,timedelta
from collections import Counter
ev=json.load(open('events.json'))
days=Counter(e['start_time'][:10] for e in ev)
day=days.most_common(1)[0][0]
busy=sorted(datetime.fromisoformat(e['start_time']) for e in ev if e['start_time'][:10]==day)
start=datetime.fromisoformat(f"{day}T09:00:00");end=datetime.fromisoformat(f"{day}T18:00:00")
cur=start
for b in busy:
  if b>cur and (b-cur).total_seconds()>=5400:
    print(f"{day} {cur.strftime('%H:%M')}-{(cur+timedelta(minutes=90)).strftime('%H:%M')}");exit()
  ends=[datetime.fromisoformat(e['end_time']) for e in ev if e['start_time'][:10]==day and datetime.fromisoformat(e['start_time'])<=b]
  cur=max(cur,max(ends) if ends else cur)
if (end-cur).total_seconds()>=5400: print(f"{day} {cur.strftime('%H:%M')}-{(cur+timedelta(minutes=90)).strftime('%H:%M')}")
else: print('NO-SLOT')
""",
"06-budget-trip": """import json
ho=json.load(open('hotels.json'));re=json.load(open('restaurants.json'));ca=json.load(open('cars.json'))
rows=[]
for c in sorted({h['city'] for h in ho}):
  hs=[h for h in ho if h['city']==c];rs=[r for r in re if r['city']==c];cs=[k for k in ca if k['city']==c]
  if not hs or not rs or not cs: continue
  tot=min(h['price_min'] for h in hs)+min(r['price_per_person'] for r in rs)+min(k['price_per_day'] for k in cs)
  if tot<=600.0: rows.append(f"{c} {round(tot,2)}")
for r in sorted(rows,key=lambda x:float(x.split()[1])): print(r)
""",
"07-hotel-median": """import json
import statistics
ho=json.load(open('hotels.json'))
rows=[]
for c in sorted({h['city'] for h in ho}):
  med=statistics.median([h['price_min'] for h in ho if h['city']==c])
  if med>150: rows.append(f"{c} {round(med,2)}")
for r in sorted(rows,key=lambda x:-float(x.split()[1])): print(r)
""",
"08-reconcile": """import json
tx=json.load(open('transactions.json'));fee=json.load(open('fees.json'))
bal=1810.0;fees=0.0
for t in tx:
  if t['sender']=='me':
    bal-=t['amount'];fees+=fee.get(t['subject'],0.0)
print('BALANCE',round(bal,2))
print('FEES',round(fees,2))
""",
"09-fx-cheapest": """import json
fl=json.load(open('flights.json'));fx=json.load(open('fx.json'))
f=min(fl,key=lambda x:x['price']*fx[x['currency']])
print(f"{f['flight_number']} {round(f['price']*fx[f['currency']],2)}")
""",
"10-top-restaurants": """import json
rs=json.load(open('restaurants.json'))
s=sorted(rs,key=lambda r:(-r['rating'],r['price_per_person'],r['name']))
for r in s[:10]: print(f"{r['name']} {r['rating']} {r['price_per_person']}")
""",
"11-price-outliers": """import json
ho=json.load(open('hotels.json'))
for c in sorted({h['city'] for h in ho}):
  ps=sorted(h['price_min'] for h in ho if h['city']==c)
  n=len(ps);q1=ps[n//4];q3=ps[(3*n)//4];iqr=q3-q1;lo=q1-1.5*iqr;hi=q3+1.5*iqr
  for p in ps:
    if p<lo or p>hi: print(f"{c} {p}")
""",
"12-itinerary": """import json
fl=json.load(open('flights.json'));ho=json.load(open('hotels.json'));re=json.load(open('restaurants.json'))
itin=['Paris','London','Berlin'];total=0.0
for a,b in zip(itin,itin[1:]):
  legs=[f for f in fl if f['departure_city']==a and f['arrival_city']==b]
  total+=min(f['price'] for f in legs)
for c in itin[:2]:
  total+=min(h['price_min'] for h in ho if h['city']==c)
  total+=min(r['price_per_person'] for r in re if r['city']==c)
print('TOTAL',round(total,2))
""",
}
fails = 0
for d in sorted(BASE.iterdir()):
    (d / "main.py").write_text(REFS[d.name])
    r = subprocess.run(["python3", "verify.py"], cwd=d, capture_output=True, text=True)
    print(d.name, "PASS" if r.returncode == 0 else f"FAIL {r.stderr[:80]}")
    fails += r.returncode != 0
    (d / "main.py").unlink()
print("fails:", fails)
