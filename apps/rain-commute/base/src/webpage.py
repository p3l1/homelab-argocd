"""Die Bedienseite: Vektorkarte mit Radar, Datumswahl und Zeitregler."""

import json
import os

import render

# Der eigene Kachelserver. Keine Nutzungsgrenzen, kein Schluessel - und die
# Karte bleibt in jeder Zoomstufe scharf, weil sie vektoriell gezeichnet wird.
TILES = os.environ.get("TILES_BASE", "https://tiles.cloud.p3l1.de")
TILE_SET = os.environ.get("TILES_SET", "bonn")

_TEMPLATE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Regenradar Arbeitsweg</title>
<link href="{tiles}/assets/lib/maplibre-gl/maplibre-gl.css" rel="stylesheet">
<script src="{tiles}/assets/lib/maplibre-gl/maplibre-gl.js"></script>
<script src="{tiles}/assets/lib/versatiles-style/versatiles-style.js"></script>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}
  body {{
    margin: 0; background: #0b1016; color: #e6edf3;
    font: 15px/1.5 system-ui, -apple-system, sans-serif;
    display: flex; flex-direction: column;
  }}
  #map {{ flex: 1 1 auto; min-height: 260px; }}
  .panel {{
    flex: 0 0 auto; padding: 10px 14px calc(12px + env(safe-area-inset-bottom));
    background: #0b1016; border-top: 1px solid #1b2530;
  }}
  .datum {{ display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }}
  input[type=date] {{
    flex: 1; padding: 8px 10px; font: inherit; color: #e6edf3;
    background: #1b2530; border: 1px solid #2b3a49; border-radius: 8px;
  }}
  .stamp {{ display: flex; justify-content: space-between; align-items: baseline;
            font-variant-numeric: tabular-nums; }}
  .stamp b {{ font-size: 18px; font-weight: 600; }}
  .stamp span {{ font-size: 13px; color: #8b949e; }}
  .stamp span.fc {{ color: #f2d24b; }}
  input[type=range] {{ width: 100%; margin: 4px 0 0; accent-color: #2fa3dd; height: 26px; }}
  .ticks {{ display: flex; justify-content: space-between; color: #8b949e; font-size: 11px; }}
  .row {{ display: flex; gap: 8px; margin-top: 8px; }}
  button {{
    flex: 1; padding: 10px 0; font: inherit; font-weight: 600; color: #e6edf3;
    background: #1b2530; border: 1px solid #2b3a49; border-radius: 8px;
    cursor: pointer; -webkit-tap-highlight-color: transparent;
  }}
  button:hover {{ background: #22303e; }}
  button.on {{ background: #2fa3dd; border-color: #2fa3dd; color: #04121c; }}
  .legend {{
    display: flex; align-items: center; gap: 6px; margin-top: 10px;
    color: #8b949e; font-size: 11px;
  }}
  .legend i {{ width: 26px; height: 11px; display: block; }}
  .hint {{ color: #8b949e; font-size: 12px; margin-top: 8px; }}
</style>
</head>
<body>
  <div id="map"></div>
  <div class="panel">
    <div class="datum">
      <button id="dayback" type="button" style="flex:0 0 44px">‹</button>
      <input type="date" id="day" min="{first_day}" max="{max_day}" value="{today}">
      <button id="dayfwd" type="button" style="flex:0 0 44px">›</button>
    </div>
    <div class="stamp"><b id="clock">–</b><span id="kind">–</span></div>
    <input type="range" id="slider" min="0" max="0" value="0" step="1">
    <div class="ticks"><span id="t0">–</span><span id="t1">–</span></div>
    <div class="row">
      <button id="prev" type="button">‹ 5 Min</button>
      <button id="play" type="button">Abspielen</button>
      <button id="next" type="button">5 Min ›</button>
    </div>
    <div class="legend" id="legend"><span>mm/h</span></div>
    <div class="hint">{count} Zeitschritte vorgehalten. Karte © OpenStreetMap-Mitwirkende</div>
  </div>

<script>
const TODAY = "{today}";
const TILES = "{tiles}";
const SET = "{tileset}";
const SCALE = {scale};
let steps = {steps};
let timer = null, ready = false;
const $ = id => document.getElementById(id);

const legend = $('legend');
SCALE.forEach(s => {{
  const i = document.createElement('i'); i.style.background = s[1];
  legend.appendChild(i);
  const t = document.createElement('span'); t.textContent = s[2]; legend.appendChild(t);
}});

const style = VersaTilesStyle.eclipse({{
  tiles: [TILES + '/tiles/' + SET + '/{{z}}/{{x}}/{{y}}'],
  baseUrl: TILES,
}});
const map = new maplibregl.Map({{
  container: 'map', style,
  center: [{lon}, {lat}], zoom: 10.6, attributionControl: false,
}});
map.addControl(new maplibregl.NavigationControl({{showCompass: false}}), 'top-right');

map.on('load', () => {{
  map.addSource('rain', {{type: 'geojson', data: {{type: 'FeatureCollection', features: []}}}});
  map.addLayer({{
    id: 'rain', type: 'fill', source: 'rain',
    // Die Farbe steckt im Merkmal - so bleibt die Skala an einer Stelle,
    // naemlich im Exporter, statt hier noch einmal zu stehen.
    paint: {{'fill-color': ['get', 'colour'], 'fill-opacity': 0.62}},
  }});
  map.addSource('route', {{type: 'geojson', data: {route}}});
  map.addLayer({{id: 'route-halo', type: 'line', source: 'route',
    filter: ['==', ['get', 'kind'], 'route'],
    paint: {{'line-color': '#000000', 'line-width': 7, 'line-opacity': 0.55}}}});
  map.addLayer({{id: 'route', type: 'line', source: 'route',
    filter: ['==', ['get', 'kind'], 'route'],
    layout: {{'line-cap': 'round', 'line-join': 'round'}},
    paint: {{'line-color': '#ffffff', 'line-width': 3}}}});
  map.addLayer({{id: 'ends', type: 'circle', source: 'route',
    filter: ['==', ['get', 'kind'], 'end'],
    paint: {{'circle-radius': 6, 'circle-color': '#ffffff',
             'circle-stroke-color': '#000000', 'circle-stroke-width': 2}}}});
  ready = true;
  show(startIndex());
}});

function startIndex() {{
  const i = steps.findIndex(s => s.kind === 'vorhersage');
  return i > 0 ? i - 1 : Math.max(0, steps.length - 1);
}}

async function show(i) {{
  if (!steps.length) return;
  i = Math.max(0, Math.min(steps.length - 1, i));
  $('slider').value = i;
  const s = steps[i];
  $('clock').textContent = s.clock;
  $('kind').textContent = s.kind === 'vorhersage' ? 'Vorhersage' : 'gemessen';
  $('kind').className = s.kind === 'vorhersage' ? 'fc' : '';
  if (!ready) return;
  const r = await fetch('radar.geojson?at=' + encodeURIComponent(s.at));
  map.getSource('rain').setData(await r.json());
}}

function render(list, at) {{
  steps = list;
  $('slider').max = Math.max(0, steps.length - 1);
  $('t0').textContent = steps.length ? steps[0].clock : '–';
  $('t1').textContent = steps.length ? steps[steps.length - 1].clock : '–';
  show(at != null ? at : startIndex());
}}

async function load(day, at) {{
  stop();
  render(await (await fetch('api/day?d=' + day)).json(), at);
}}

$('day').addEventListener('change', e => load(e.target.value, 0));
$('dayback').addEventListener('click', () => shiftDay(-1));
$('dayfwd').addEventListener('click', () => shiftDay(1));
function shiftDay(n) {{
  const d = new Date($('day').value + 'T12:00:00');
  d.setDate(d.getDate() + n);
  const v = d.toISOString().slice(0, 10);
  if (v < $('day').min || v > $('day').max) return;
  $('day').value = v; load(v, 0);
}}
$('prev').addEventListener('click', () => show(+$('slider').value - 1));
$('next').addEventListener('click', () => show(+$('slider').value + 1));
$('slider').addEventListener('input', () => show(+$('slider').value));

function stop() {{ clearInterval(timer); timer = null;
  $('play').classList.remove('on'); $('play').textContent = 'Abspielen'; }}
$('play').addEventListener('click', () => {{
  if (timer) return stop();
  $('play').classList.add('on'); $('play').textContent = 'Anhalten';
  show(0);
  timer = setInterval(() => {{
    const n = +$('slider').value + 1;
    if (n >= steps.length) return stop();
    show(n);
  }}, 500);
}});
document.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT' && e.target.type === 'date') return;
  if (e.key === 'ArrowLeft') $('prev').click();
  if (e.key === 'ArrowRight') $('next').click();
  if (e.key === ' ') {{ e.preventDefault(); $('play').click(); }}
}});
</script>
</body>
</html>
"""


def page(today, first_day, steps, count):
    data = [{"at": w.isoformat(), "clock": w.strftime("%H:%M"), "kind": k}
            for w, k in steps]
    pts = render.ROUTE_POINTS
    return _TEMPLATE.format(
        tiles=TILES, tileset=TILE_SET,
        lon=round(sum(p[0] for p in pts) / len(pts), 4),
        lat=round(sum(p[1] for p in pts) / len(pts), 4),
        today=today.isoformat(),
        first_day=first_day.isoformat(),
        max_day=today.isoformat(),
        steps=json.dumps(data, ensure_ascii=False),
        route=json.dumps(render.route_geojson()),
        scale=json.dumps([[s[0], s[1], s[2]] for s in render._SCALE[:-1]]),
        count=count,
    )
