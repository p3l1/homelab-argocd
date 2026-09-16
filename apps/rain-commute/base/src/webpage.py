"""Die Bedienseite: Datumswahl plus Zeitregler über den gewählten Tag."""

import json

import render

_W = render.HALF * 2 * render.SCALE
_HEAD, _LEGEND = 44, 46
_H = _HEAD + _W + _LEGEND

_TEMPLATE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Regenradar Arbeitsweg</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #0b1016; color: #e6edf3;
    font: 15px/1.5 system-ui, -apple-system, sans-serif;
    display: flex; flex-direction: column; align-items: center;
    padding: 12px 12px calc(16px + env(safe-area-inset-bottom));
  }}
  .stage {{
    position: relative; width: min(100%, {w}px); aspect-ratio: {w} / {h};
    border-radius: 10px; overflow: hidden; background: #0b1016;
  }}
  .stage img {{ position: absolute; left: 0; width: 100%; display: block; }}
  .map {{ top: {map_top}%; height: {map_h}%; }}
  .rain {{ top: 0; height: 100%; }}
  .bar {{ width: min(100%, {w}px); }}
  .datum {{ display: flex; gap: 8px; align-items: center; margin: 14px 0 10px; }}
  input[type=date] {{
    flex: 1; padding: 9px 10px; font: inherit; color: #e6edf3;
    background: #1b2530; border: 1px solid #2b3a49; border-radius: 8px;
  }}
  .stamp {{
    display: flex; justify-content: space-between; align-items: baseline;
    font-variant-numeric: tabular-nums; margin-bottom: 6px;
  }}
  .stamp b {{ font-size: 18px; font-weight: 600; }}
  .stamp span {{ font-size: 13px; color: #8b949e; }}
  .stamp span.fc {{ color: #f2d24b; }}
  input[type=range] {{ width: 100%; margin: 0; accent-color: #2fa3dd; height: 28px; }}
  .ticks {{ display: flex; justify-content: space-between; color: #8b949e;
            font-size: 11px; margin-top: -2px; }}
  .row {{ display: flex; gap: 8px; margin-top: 12px; }}
  button {{
    flex: 1; padding: 11px 0; font: inherit; font-weight: 600; color: #e6edf3;
    background: #1b2530; border: 1px solid #2b3a49; border-radius: 8px;
    cursor: pointer; -webkit-tap-highlight-color: transparent;
  }}
  button:hover {{ background: #22303e; }}
  button.on {{ background: #2fa3dd; border-color: #2fa3dd; color: #04121c; }}
  button:disabled {{ opacity: .45; cursor: default; }}
  .hint {{ color: #8b949e; font-size: 12px; margin-top: 12px; text-align: center; }}
</style>
</head>
<body>
  <div class="stage">
    <img class="map" src="karte.webp" alt="Karte">
    <img class="rain" id="rain" alt="Regenradar">
  </div>

  <div class="bar">
    <div class="datum">
      <button id="dayback" type="button" style="flex:0 0 46px">‹</button>
      <input type="date" id="day" min="{first_day}" max="{max_day}" value="{today}">
      <button id="dayfwd" type="button" style="flex:0 0 46px">›</button>
    </div>

    <div class="stamp"><b id="clock">–</b><span id="kind">–</span></div>
    <input type="range" id="slider" min="0" max="0" value="0" step="1">
    <div class="ticks"><span id="t0">–</span><span id="t1">–</span></div>

    <div class="row">
      <button id="prev" type="button">‹ 5 Min</button>
      <button id="play" type="button">Abspielen</button>
      <button id="next" type="button">5 Min ›</button>
    </div>
    <div class="row"><button id="now" type="button">Zurück zu jetzt</button></div>
    <div class="hint">{count} Zeitschritte in der Ablage. Pfeiltasten und Leertaste bedienen mit.</div>
  </div>

<script>
const TODAY = "{today}";
let steps = {steps};
let timer = null;
const $ = id => document.getElementById(id);
const rain = $('rain'), slider = $('slider'), clock = $('clock'), kind = $('kind'), play = $('play');

function url(s) {{ return 'radar.svg?at=' + encodeURIComponent(s.at) + '&bare=1'; }}

function show(i) {{
  if (!steps.length) return;
  i = Math.max(0, Math.min(steps.length - 1, i));
  slider.value = i;
  const s = steps[i];
  rain.src = url(s);
  clock.textContent = s.clock;
  kind.textContent = s.kind === 'vorhersage' ? 'Vorhersage' : 'gemessen';
  kind.className = s.kind === 'vorhersage' ? 'fc' : '';
}}

function render(list, startAt) {{
  steps = list;
  slider.max = Math.max(0, steps.length - 1);
  $('t0').textContent = steps.length ? steps[0].clock : '–';
  $('t1').textContent = steps.length ? steps[steps.length - 1].clock : '–';
  const i = startAt != null ? startAt
    : Math.max(0, steps.findIndex(s => s.kind === 'vorhersage') - 1);
  show(i >= 0 ? i : steps.length - 1);
  // Vorladen, sonst flackert die Animation bei jedem Bildwechsel.
  steps.forEach(s => {{ const im = new Image(); im.src = url(s); }});
}}

async function load(day, startAt) {{
  stop();
  const r = await fetch('api/day?d=' + day);
  render(await r.json(), startAt);
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

$('prev').addEventListener('click', () => show(+slider.value - 1));
$('next').addEventListener('click', () => show(+slider.value + 1));
slider.addEventListener('input', () => show(+slider.value));
$('now').addEventListener('click', () => {{ $('day').value = TODAY; load(TODAY); }});

function stop() {{ clearInterval(timer); timer = null; play.classList.remove('on'); play.textContent = 'Abspielen'; }}
play.addEventListener('click', () => {{
  if (timer) return stop();
  play.classList.add('on'); play.textContent = 'Anhalten';
  show(0);
  timer = setInterval(() => {{
    const n = +slider.value + 1;
    if (n >= steps.length) return stop();
    show(n);
  }}, 300);
}});

document.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT' && e.target.type === 'date') return;
  if (e.key === 'ArrowLeft') $('prev').click();
  if (e.key === 'ArrowRight') $('next').click();
  if (e.key === ' ') {{ e.preventDefault(); play.click(); }}
}});

render(steps);
</script>
</body>
</html>
"""


def page(today, first_day, steps, count):
    """today/first_day sind date-Objekte, steps eine Liste von (Zeit, Art)."""
    data = [{"at": w.isoformat(), "clock": w.strftime("%H:%M"), "kind": k}
            for w, k in steps]
    max_day = today.isoformat()
    return _TEMPLATE.format(
        w=_W, h=_H,
        map_top=round(_HEAD / _H * 100, 3),
        map_h=round(_W / _H * 100, 3),
        today=today.isoformat(),
        first_day=first_day.isoformat(),
        max_day=max_day,
        steps=json.dumps(data, ensure_ascii=False),
        count=count,
    )
