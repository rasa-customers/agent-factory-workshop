(() => {
  'use strict';

  const $ = (sel) => document.querySelector(sel);

  const panels = {
    flight: { el: $('#panel-flight'), body: $('#flightBody'), meta: $('#flightMeta') },
    weather:{ el: $('#panel-weather'), body: $('#weatherBody'), meta: $('#weatherMeta') },
    meeting:{ el: $('#panel-meeting'), body: $('#meetingBody'), meta: $('#meetingMeta') },
    verdict:{ el: $('#panel-verdict'), body: $('#verdictBody'), meta: $('#verdictMeta') },
  };

  const connDot = $('#connDot');
  const connText = $('#connText');

  let lastStateStr = '';
  let lastPanelsStr = { flight:'', weather:'', meeting:'', verdict:'' };

  function setConn(mode, text){
    connText.textContent = text;
    if(mode === 'ok') connDot.style.background = 'rgba(38,208,124,.85)';
    else if(mode === 'warn') connDot.style.background = 'rgba(255,204,0,.85)';
    else if(mode === 'bad') connDot.style.background = 'rgba(255,77,77,.85)';
    else connDot.style.background = 'rgba(255,255,255,.22)';
  }

  function isObject(x){ return x && typeof x === 'object' && !Array.isArray(x); }

  function titleCase(s){
    return String(s)
      .replace(/_/g,' ')
      .replace(/\s+/g,' ')
      .trim()
      .replace(/\b\w/g, (m) => m.toUpperCase());
  }

  function formatValue(key, value){
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'number') {
      if (/(minutes?|mins?)$/i.test(key) || /_minutes$/i.test(key)) return `${value} min`;
      return String(value);
    }
    if (typeof value === 'string') {
      const dt = tryParseISO(value);
      if (dt) return formatTime(dt);
      return value;
    }
    if (Array.isArray(value)) return value.map(v => (typeof v === 'string' ? v : JSON.stringify(v))).join(', ');
    if (isObject(value)) return JSON.stringify(value);
    return String(value);
  }

  function tryParseISO(s){
    if (typeof s !== 'string') return null;
    const looks = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s);
    if (!looks) return null;
    const d = new Date(s);
    if (isNaN(d.getTime())) return null;
    return d;
  }

  function formatTime(d){
    try{
      return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    } catch { return d.toString(); }
  }

  function kvRow(k, v){
    const row = document.createElement('div');
    row.className = 'kv';
    row.innerHTML = `<div class="kv__k">${escapeHtml(k)}</div><div class="kv__v">${escapeHtml(v)}</div>`;
    return row;
  }

  function escapeHtml(s){
    return String(s)
      .replaceAll('&','&amp;')
      .replaceAll('<','&lt;')
      .replaceAll('>','&gt;')
      .replaceAll('"','&quot;')
      .replaceAll("'",'&#039;');
  }

  function flash(panelKey){
    const el = panels[panelKey]?.el;
    if(!el) return;
    el.classList.remove('panel--flash');
    // Force reflow
    void el.offsetWidth;
    el.classList.add('panel--flash');
  }

  function renderPanel(panelKey, obj){
    if (!obj) return renderEmpty(panelKey);

    if(panelKey === 'flight') return renderFlight(obj);
    if(panelKey === 'weather') return renderWeather(obj);
    if(panelKey === 'meeting') return renderMeeting(obj);
    if(panelKey === 'verdict') return renderVerdict(obj);
  }

  function renderEmpty(panelKey){
    const b = panels[panelKey].body;
    const msg = {
      flight: 'Waiting for flight details…',
      weather: 'Waiting for landing weather…',
      meeting: 'Waiting for meeting details…',
      verdict: 'Waiting for timing verdict…',
    }[panelKey] || 'Waiting for details…';
    panels[panelKey].meta.textContent = '';
    b.innerHTML = `<div class="empty">${escapeHtml(msg)}</div>`;
  }

  function renderGenericRows(obj, knownKeys){
    const extras = [];
    for (const [k, v] of Object.entries(obj)){
      if (knownKeys.has(k)) continue;
      extras.push([k, v]);
    }
    if (!extras.length) return '';

    const rows = extras.map(([k,v]) => {
      return `<div class="kv__k">${escapeHtml(titleCase(k))}</div><div class="kv__v">${escapeHtml(formatValue(k, v))}</div>`;
    }).join('');
    return `<div class="kv" style="margin-top:12px">${rows}</div>`;
  }

  function renderFlight(obj){
    const known = new Set([
      'flight_number','airline','status','delay_minutes','gate','previous_gate','terminal','estimated_arrival','arrival_estimated'
    ]);

    const flightNumber = obj.flight_number ?? obj.number ?? obj.flight ?? null;
    const airline = obj.airline ?? obj.carrier ?? null;
    const status = obj.status ?? null;
    const delayMin = obj.delay_minutes ?? obj.delay_min ?? null;
    const gate = obj.gate ?? null;
    const prevGate = obj.previous_gate ?? obj.gate_previous ?? obj.from_gate ?? null;
    const terminal = obj.terminal ?? null;
    const eta = obj.estimated_arrival ?? obj.arrival_estimated ?? obj.eta ?? null;

    const primary = [airline, flightNumber].filter(Boolean).join(' · ') || 'Flight';
    const statusBits = [];
    if (status) statusBits.push(status);
    if (typeof delayMin === 'number') statusBits.push(`${delayMin} min late`);

    panels.flight.meta.textContent = statusBits.join(' • ');

    const gateLine = gate ? (prevGate && prevGate !== gate ? `${gate} (was ${prevGate})` : gate) : null;

    const lines = [];
    lines.push(`<div class="bigline"><div class="bigline__primary">${escapeHtml(primary)}</div>${status ? `<span class="badge">${escapeHtml(status)}</span>`:''}${typeof delayMin === 'number' ? `<span class="badge">${escapeHtml(delayMin)} min late</span>`:''}</div>`);

    const kv = [];
    if (terminal) kv.push(['Terminal', formatValue('terminal', terminal)]);
    if (gateLine) kv.push(['Gate', gateLine]);
    if (eta) kv.push(['Estimated arrival', formatValue('estimated_arrival', eta)]);

    if (!kv.length){
      kv.push(['Details', '—']);
    }

    const kvHtml = `<div class="kv">${kv.map(([k,v])=>`<div class="kv__k">${escapeHtml(k)}</div><div class="kv__v">${escapeHtml(v)}</div>`).join('')}</div>`;
    const extraHtml = renderGenericRows(obj, known);

    panels.flight.body.innerHTML = kvHtml + extraHtml;
  }

  function renderWeather(obj){
    const known = new Set([
      'temperature_c','temperature_f','temp_c','temp_f','condition','conditions','wind_kph','wind_mph','wind','rain','precip_mm','precip_chance','humidity'
    ]);

    const tC = obj.temperature_c ?? obj.temp_c ?? null;
    const tF = obj.temperature_f ?? obj.temp_f ?? null;
    const cond = obj.condition ?? obj.conditions ?? null;

    let temp = null;
    if (typeof tC === 'number') temp = `${tC}°C`;
    else if (typeof tF === 'number') temp = `${tF}°F`;

    const primary = [temp, cond].filter(Boolean).join(' · ') || 'Weather';
    panels.weather.meta.textContent = '';

    const header = `<div class="bigline"><div class="bigline__primary">${escapeHtml(primary)}</div></div>`;

    const kv = [];
    if (typeof tC === 'number') kv.push(['Temperature (C)', `${tC}°C`]);
    if (typeof tF === 'number') kv.push(['Temperature (F)', `${tF}°F`]);
    if (cond) kv.push(['Conditions', formatValue('condition', cond)]);

    // Getting-around factors
    if (obj.rain !== undefined) kv.push(['Rain', formatValue('rain', obj.rain)]);
    if (obj.precip_chance !== undefined) kv.push(['Precip chance', formatValue('precip_chance', obj.precip_chance)]);
    if (obj.wind !== undefined) kv.push(['Wind', formatValue('wind', obj.wind)]);
    if (obj.wind_mph !== undefined) kv.push(['Wind (mph)', formatValue('wind_mph', obj.wind_mph)]);
    if (obj.wind_kph !== undefined) kv.push(['Wind (kph)', formatValue('wind_kph', obj.wind_kph)]);

    if (!kv.length) kv.push(['Details', '—']);

    const kvHtml = `<div class="kv">${kv.map(([k,v])=>`<div class="kv__k">${escapeHtml(k)}</div><div class="kv__v">${escapeHtml(v)}</div>`).join('')}</div>`;
    const extraHtml = renderGenericRows(obj, known);

    panels.weather.body.innerHTML = header + kvHtml + extraHtml;
  }

  function renderMeeting(obj){
    const known = new Set(['title','start','start_time','address','location','room']);

    const title = obj.title ?? obj.subject ?? 'Meeting';
    const start = obj.start ?? obj.start_time ?? null;
    const address = obj.address ?? obj.location ?? null;

    panels.meeting.meta.textContent = start ? `Starts ${formatValue('start', start)}` : '';

    const header = `<div class="bigline"><div class="bigline__primary">${escapeHtml(title)}</div></div>`;

    const kv = [];
    if (start) kv.push(['Start time', formatValue('start', start)]);
    if (address) kv.push(['Address', formatValue('address', address)]);

    if (obj.room) kv.push(['Room', formatValue('room', obj.room)]);

    if (!kv.length) kv.push(['Details', '—']);

    const kvHtml = `<div class="kv">${kv.map(([k,v])=>`<div class="kv__k">${escapeHtml(k)}</div><div class="kv__v">${escapeHtml(v)}</div>`).join('')}</div>`;
    const extraHtml = renderGenericRows(obj, known);

    panels.meeting.body.innerHTML = header + kvHtml + extraHtml;
  }

  function normalizeVerdictWord(v){
    if (!v) return null;
    const s = String(v).toLowerCase();
    if (s.includes('yes') || s.includes('make')) return 'YES';
    if (s.includes('tight')) return 'TIGHT';
    if (s.includes('no') || s.includes("won't") || s.includes('miss')) return 'NO';
    return String(v).toUpperCase();
  }

  function verdictClass(word){
    const w = (word||'').toUpperCase();
    if (w === 'YES') return 'pill--good';
    if (w === 'TIGHT') return 'pill--warn';
    if (w === 'NO') return 'pill--bad';
    return '';
  }

  function renderVerdict(obj){
    const known = new Set(['verdict','status','slack_minutes','minutes_slack','late_minutes','reason']);

    const word = normalizeVerdictWord(obj.verdict ?? obj.status ?? null) || '—';
    const slack = obj.slack_minutes ?? obj.minutes_slack ?? null;
    const late = obj.late_minutes ?? null;
    const reason = obj.reason ?? null;

    panels.verdict.meta.textContent = '';

    let detail = '';
    if (typeof slack === 'number') detail = `${slack} min slack`;
    else if (typeof late === 'number') detail = `${late} min late`;

    const pill = `
      <div class="verdict__pill ${verdictClass(word)}">
        <div>
          <div class="verdict__word">${escapeHtml(word)}</div>
          <div class="verdict__detail">${escapeHtml(detail || ' ')}</div>
        </div>
      </div>
    `;

    const reasonLine = reason ? `<div class="verdict__reason">${escapeHtml(reason)}</div>` : `<div class="verdict__reason" style="color: var(--muted)">Waiting for reasoning…</div>`;

    const kv = [];
    if (typeof slack === 'number') kv.push(['Slack', `${slack} min`]);
    if (typeof late === 'number') kv.push(['Late by', `${late} min`]);

    const kvHtml = kv.length ? `<div class="kv">${kv.map(([k,v])=>`<div class="kv__k">${escapeHtml(k)}</div><div class="kv__v">${escapeHtml(v)}</div>`).join('')}</div>` : '';
    const extraHtml = renderGenericRows(obj, known);

    panels.verdict.body.innerHTML = `<div class="verdict">${pill}${reasonLine}${kvHtml}${extraHtml}</div>`;
  }

  function applyState(state){
    const stateStr = JSON.stringify(state || {});
    if (stateStr === lastStateStr) return;
    lastStateStr = stateStr;

    for (const key of ['flight','weather','meeting','verdict']){
      const panelData = state ? state[key] : null;
      const panelStr = JSON.stringify(panelData || null);
      if (panelStr !== lastPanelsStr[key]){
        lastPanelsStr[key] = panelStr;
        renderPanel(key, panelData);
        flash(key);
      }
    }
  }

  async function loadInitial(){
    try{
      const res = await fetch('./api/state', { cache: 'no-store' });
      if(!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      applyState(data);
      setConn('ok', 'Live');
    } catch (e){
      setConn('bad', 'Offline (retrying)');
      console.error(e);
    }
  }

  function connectSSE(){
    const es = new EventSource('./api/events');

    es.addEventListener('open', () => setConn('ok', 'Live'));
    es.addEventListener('error', () => setConn('warn', 'Reconnecting…'));

    es.addEventListener('state', (ev) => {
      try{
        const data = JSON.parse(ev.data);
        applyState(data);
        setConn('ok', 'Live');
      } catch (e){
        console.error('Bad SSE data', e);
      }
    });

    return es;
  }

  // Kick off
  renderEmpty('flight');
  renderEmpty('weather');
  renderEmpty('meeting');
  renderEmpty('verdict');

  loadInitial();
  connectSSE();
})();
