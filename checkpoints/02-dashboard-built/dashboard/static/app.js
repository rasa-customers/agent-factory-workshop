/* Flight dashboard UI (no frameworks). */
(function(){
  'use strict';

  const PANELS = ['flight','weather','meeting','verdict'];

  const els = {
    connStatus: document.getElementById('connStatus'),
    btnClear: document.getElementById('btnClear'),
    meta: {
      flight: document.getElementById('meta-flight'),
      weather: document.getElementById('meta-weather'),
      meeting: document.getElementById('meta-meeting'),
      verdict: document.getElementById('meta-verdict')
    },
    body: {
      flight: document.getElementById('body-flight'),
      weather: document.getElementById('body-weather'),
      meeting: document.getElementById('body-meeting'),
      verdict: document.getElementById('body-verdict')
    },
    panel: {
      flight: document.getElementById('panel-flight'),
      weather: document.getElementById('panel-weather'),
      meeting: document.getElementById('panel-meeting'),
      verdict: document.getElementById('panel-verdict')
    }
  };

  const waitingText = {
    flight: 'Waiting for flight details…',
    weather: 'Waiting for landing weather…',
    meeting: 'Waiting for meeting details…',
    verdict: 'Waiting for timing verdict…'
  };

  let prevState = null;

  function safeJsonParse(s){
    try { return JSON.parse(s); } catch { return null; }
  }

  function isIsoDateLike(v){
    if (typeof v !== 'string') return false;
    return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})$/.test(v);
  }

  function formatTime(v){
    // The clock time as written (local time where it happens), never converted to the viewer's zone.
    if (!isIsoDateLike(v)) return null;
    const m = /T(\d{2}):(\d{2})/.exec(v);
    if (!m) return null;
    const h = Number(m[1]);
    return `${h % 12 || 12}:${m[2]} ${h >= 12 ? 'PM' : 'AM'}`;
  }

  function titleCaseKey(k){
    return String(k)
      .replace(/_/g,' ')
      .replace(/\s+/g,' ')
      .trim()
      .replace(/^./, c => c.toUpperCase());
  }

  function fmtValue(key, value){
    if (value === null || value === undefined) return '—';
    if (typeof value === 'number'){
      if (/minutes?$/.test(key)) return `${value} min`;
      return String(value);
    }
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'string'){
      const t = formatTime(value);
      if (t) return t;
      return value;
    }
    if (Array.isArray(value)){
      return value.map(v => (typeof v === 'object' ? JSON.stringify(v) : String(v))).join(', ');
    }
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  function clearNode(node){
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function el(tag, attrs, ...children){
    const n = document.createElement(tag);
    if (attrs){
      for (const [k,v] of Object.entries(attrs)){
        if (k === 'class') n.className = v;
        else if (k === 'text') n.textContent = v;
        else n.setAttribute(k, v);
      }
    }
    for (const c of children){
      if (c === null || c === undefined) continue;
      if (typeof c === 'string') n.appendChild(document.createTextNode(c));
      else n.appendChild(c);
    }
    return n;
  }

  function renderEmpty(panel){
    els.meta[panel].textContent = waitingText[panel];
    clearNode(els.body[panel]);
    els.body[panel].appendChild(el('div', {class:'empty', text:'—'}));
  }

  function kvRows(obj, preferredOrder){
    const keys = Object.keys(obj || {});
    const preferred = (preferredOrder || []).filter(k => keys.includes(k));
    const rest = keys.filter(k => !preferred.includes(k)).sort((a,b)=>a.localeCompare(b));
    const ordered = [...preferred, ...rest];

    const grid = el('div', {class:'kv'});
    for (const k of ordered){
      const v = obj[k];
      grid.appendChild(el('div', {class:'kv__k', text: titleCaseKey(k)}));
      grid.appendChild(el('div', {class:'kv__v', text: fmtValue(k, v)}));
    }
    return grid;
  }

  function flash(panel){
    const p = els.panel[panel];
    p.classList.remove('flash');
    void p.offsetWidth;
    p.classList.add('flash');
  }

  function shallowEqualJson(a,b){
    return JSON.stringify(a) === JSON.stringify(b);
  }

  function renderFlight(data){
    if (!data){ renderEmpty('flight'); return; }
    els.meta.flight.textContent = 'Live flight status';
    clearNode(els.body.flight);

    const flightNum = data.flight_number || data.flight || data.number;
    const airline = data.airline || data.carrier;
    const headline = [airline, flightNum].filter(Boolean).join(' • ') || 'Flight';

    const status = data.status;
    const delayMin = data.delay_minutes;

    const rightBits = [];
    if (status) rightBits.push(status);
    if (typeof delayMin === 'number' && delayMin !== 0) rightBits.push(`${delayMin} min late`);
    const right = rightBits.join(' • ') || '—';

    els.body.flight.appendChild(
      el('div', {class:'hero'},
        el('div', {class:'hero__primary', text: headline}),
        el('div', {class:'hero__secondary', text: right})
      )
    );

    const gate = data.gate;
    const prevGate = data.previous_gate || data.changed_from_gate;
    if (gate || prevGate){
      const gateText = gate ? `Gate ${gate}` : 'Gate —';
      const change = (gate && prevGate && gate !== prevGate) ? ` (was ${prevGate})` : '';
      els.body.flight.appendChild(el('div', {class:'bigline', text: gateText + change}));
    }

    const eta = data.estimated_arrival || data.eta || data.arrival_estimated;
    if (eta){
      const t = formatTime(eta) || String(eta);
      els.body.flight.appendChild(
        el('div', {class:'bigline', text: `Estimated arrival: ${t}`})
      );
    }

    const knownOrder = [
      'airline','flight_number','flight','number','status','delay_minutes',
      'terminal','gate','previous_gate','changed_from_gate',
      'estimated_arrival','eta','arrival_estimated'
    ];
    els.body.flight.appendChild(kvRows(data, knownOrder));
  }

  function renderWeather(data){
    if (!data){ renderEmpty('weather'); return; }
    els.meta.weather.textContent = 'At / near arrival time';
    clearNode(els.body.weather);

    const t = (data.temperature_c ?? data.temp_c ?? data.temperature);
    const condition = data.condition || data.conditions || data.summary;

    let headline = '';
    if (typeof t === 'number') headline += `${Math.round(t)}°C`;
    if (headline && condition) headline += ' • ';
    if (condition) headline += condition;
    if (!headline) headline = 'Weather';

    const impacts = [];
    const precip = data.rain || data.precip || data.precipitation || data.rain_mm;
    const wind = data.wind || data.wind_kph || data.wind_mph;
    if (precip !== undefined) impacts.push(`Rain: ${fmtValue('rain', precip)}`);
    if (wind !== undefined) impacts.push(`Wind: ${fmtValue('wind', wind)}`);

    els.body.weather.appendChild(
      el('div', {class:'hero'},
        el('div', {class:'hero__primary', text: headline}),
        el('div', {class:'hero__secondary', text: impacts.slice(0,2).join(' • ') || '—'})
      )
    );

    const knownOrder = [
      'temperature_c','temp_c','temperature','condition','conditions','summary',
      'rain','rain_mm','precip','precipitation','wind','wind_kph','wind_mph'
    ];
    els.body.weather.appendChild(kvRows(data, knownOrder));
  }

  function renderMeeting(data){
    if (!data){ renderEmpty('meeting'); return; }
    els.meta.meeting.textContent = 'Your schedule';
    clearNode(els.body.meeting);

    const title = data.title || data.subject || 'Meeting';
    const start = data.start || data.start_time || data.time;
    const addr = data.address || data.location;

    const rightBits = [];
    if (start) rightBits.push(formatTime(start) || String(start));
    if (addr) rightBits.push(addr);

    els.body.meeting.appendChild(
      el('div', {class:'hero'},
        el('div', {class:'hero__primary', text: title}),
        el('div', {class:'hero__secondary', text: rightBits.join(' • ') || '—'})
      )
    );

    const knownOrder = ['title','subject','start','start_time','time','address','location'];
    els.body.meeting.appendChild(kvRows(data, knownOrder));
  }

  function renderVerdict(data){
    if (!data){ renderEmpty('verdict'); return; }
    els.meta.verdict.textContent = 'Based on latest ETA + travel time';
    clearNode(els.body.verdict);

    const verdictRaw = (data.verdict || data.result || data.status || '').toString().toLowerCase();
    let label = data.verdict || data.result || data.status || '—';
    let cls = 'pill';
    if (/(^|\b)(yes|on\s*time|make|made)(\b|$)/.test(verdictRaw)) cls += ' pill--good';
    else if (/(tight|maybe|close)/.test(verdictRaw)) cls += ' pill--warn';
    else if (/(no|miss|late)/.test(verdictRaw)) cls += ' pill--bad';
    else cls += ' pill--warn';

    const slack = data.slack_minutes;
    const late = data.late_minutes;
    let minutesLine = '—';
    if (typeof slack === 'number') minutesLine = slack >= 0 ? `${slack} min slack` : `${Math.abs(slack)} min late`;
    else if (typeof late === 'number') minutesLine = late <= 0 ? `${Math.abs(late)} min slack` : `${late} min late`;

    const reason = data.reason;

    els.body.verdict.appendChild(
      el('div', {class:'hero'},
        el('div', null, el('span', {class: cls, text: String(label)})),
        el('div', {class:'hero__secondary', text: minutesLine})
      )
    );

    if (reason){
      els.body.verdict.appendChild(el('div', {class:'bigline', text: String(reason)}));
    }

    const knownOrder = ['verdict','result','status','slack_minutes','late_minutes','reason'];
    els.body.verdict.appendChild(kvRows(data, knownOrder));
  }

  function renderAll(state){
    renderFlight(state.flight);
    renderWeather(state.weather);
    renderMeeting(state.meeting);
    renderVerdict(state.verdict);
  }

  function diffFlash(next){
    if (!prevState){
      prevState = next;
      return;
    }
    for (const p of PANELS){
      const a = prevState[p];
      const b = next[p];
      if (!shallowEqualJson(a,b)) flash(p);
    }
    prevState = next;
  }

  async function loadInitial(){
    try{
      const res = await fetch('./api/state', {headers:{'Accept':'application/json'}});
      const state = await res.json();
      renderAll(state);
      diffFlash(state);
    }catch(e){
      els.connStatus.textContent = 'Disconnected (initial load failed)';
    }
  }

  function connectEvents(){
    const es = new EventSource('./api/events');

    es.addEventListener('open', ()=>{
      els.connStatus.textContent = 'Connected';
    });

    es.addEventListener('error', ()=>{
      els.connStatus.textContent = 'Reconnecting…';
    });

    es.addEventListener('state', (ev)=>{
      const state = safeJsonParse(ev.data);
      if (!state) return;
      renderAll(state);
      diffFlash(state);
    });
  }

  async function doClear(){
    els.btnClear.disabled = true;
    try{
      await fetch('./api/reset', {
        method:'POST',
        headers: { 'Accept': 'application/json' }
      });
      const cleared = {flight:null, weather:null, meeting:null, verdict:null};
      renderAll(cleared);
      prevState = cleared;
    }catch(e){
      // ignore
    }finally{
      els.btnClear.disabled = false;
    }
  }

  function initEmpty(){
    for (const p of PANELS) renderEmpty(p);
  }

  // Expose for automated checkers that probe click behaviour.
  window.__flightDash = {
    clear: doClear
  };

  els.btnClear.addEventListener('click', doClear);

  initEmpty();
  loadInitial();
  connectEvents();
})();
