"""Die Route, die Pendelzeiten und ihre Bewertung."""

HOME = (7.0822, 50.7377)   # Bornheimer Strasse 144
WORK = (7.1544, 50.7179)   # Konrad-Zuse-Platz

# Aus dem Fahrradrouting (6,60 km) einmalig abgeleitet und im Entwurf belegt.
# Fest hinterlegt, weil die Route sich nicht aendert - ein Routing-Dienst zur
# Laufzeit waere eine Abhaengigkeit ohne Gegenwert.
ROUTE_CELLS = [
    (625, 327), (625, 328), (625, 329),
    (626, 327), (626, 328), (626, 329), (626, 330),
    (627, 330), (627, 331), (627, 332),
    (628, 332),
]

# Die gefahrene Linie, aus der OSRM-Route auf 13 Stuetzpunkte ausgeduennt
# (Douglas-Peucker). Fuer das Kartenbild - ROUTE_CELLS daneben ist das
# gerasterte Gegenstueck fuer die Messung.
ROUTE_POINTS = [
    (7.08203, 50.73776), (7.08123, 50.73676), (7.09034, 50.73451),
    (7.09756, 50.73726), (7.10470, 50.73740), (7.11588, 50.73889),
    (7.11721, 50.73663), (7.11994, 50.73716), (7.12311, 50.73258),
    (7.13025, 50.72679), (7.13802, 50.72374), (7.14850, 50.72104),
    (7.15438, 50.71791),
]

# (Name, Startminute, Endminute) seit Mitternacht, Ortszeit.
WINDOWS = [("hinweg", 6 * 60 + 30, 8 * 60 + 30), ("rueckweg", 16 * 60, 18 * 60)]

TRAVEL_MINUTES = 45        # Fahrtdauer samt Puffer

# Die Regenschwelle steht bewusst nur in der VMRule: dort laesst sie sich aendern,
# ohne den Pod neu zu starten, und zwei Wahrheiten dafuer waeren eine zu viel.


def max_on_route(composite, cells=ROUTE_CELLS):
    """Der nasseste Punkt der Route, oder None wenn keine Zelle Daten hat."""
    seen = [v for v in (composite.value_at(r, c) for r, c in cells) if v is not None]
    return max(seen) if seen else None


def window_active(now):
    """Laeuft gerade ein Pendelfenster? Erwartet eine zeitzonenbehaftete Zeit."""
    if now.weekday() > 4:
        return False
    minutes = now.hour * 60 + now.minute
    return any(start <= minutes < end for _, start, end in WINDOWS)


def expected_rain(composites, cells=ROUTE_CELLS, horizon=TRAVEL_MINUTES):
    """Staerkster Regen auf der Route innerhalb der naechsten Fahrt."""
    seen = [
        v
        for c in composites
        if c.forecast_minutes <= horizon
        for v in [max_on_route(c, cells)]
        if v is not None
    ]
    return max(seen) if seen else None


# Umgangssprache statt Messtechnik: "mm je 5 Minuten" hat niemand im Kopf.
# Schwellen in mm/h, grob nach der ueblichen Einteilung des DWD.
_WORDS = [(0.5, "Nieselregen"), (2.5, "leichter Regen"), (10.0, "mäßiger Regen"),
          (50.0, "starker Regen"), (float("inf"), "Platzregen")]


def intensity_word(mm_per_hour):
    for limit, word in _WORDS:
        if mm_per_hour < limit:
            return word
    return _WORDS[-1][1]


def describe(composites, cells=ROUTE_CELLS, horizon=TRAVEL_MINUTES, threshold=0.1):
    """Was auf dem Weg passiert - oder None, wenn es trocken bleibt.

    Liefert Beginn und Ende in Minuten ab jetzt, die Spitzenintensitaet in mm/h
    und ein Wort dafuer. Beginn 0 heisst: es regnet bereits.
    """
    wet = []
    for c in composites:
        if c.forecast_minutes > horizon:
            continue
        v = max_on_route(c, cells)
        if v is not None and v >= threshold:
            wet.append((c.forecast_minutes, v))
    if not wet:
        return None
    peak = max(v for _, v in wet)
    return {
        "starts_in": wet[0][0],
        "ends_in": wet[-1][0] + 5,      # der Schritt deckt die folgenden 5 Minuten ab
        "peak_mm_h": peak * 12,         # mm je 5 Minuten sind ein Zwoelftel einer Stunde
        "word": intensity_word(peak * 12),
    }
