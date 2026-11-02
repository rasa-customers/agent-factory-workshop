(() => {
  const $ = (sel) => document.querySelector(sel);

  const els = {
    connectionStatus: $('#connectionStatus'),
    clearBtn: $('#clearBtn'),

    verdictHero: $('#verdictHero'),
    verdictStatus: $('#verdictStatus'),
    verdictSlack: $('#verdictSlack'),
    verdictReason: $('#verdictReason'),
    verdictKV: $('#verdictKV'),

    flightHint: $('#flightHint'),
    flightMain: $('#flightMain'),
    flightStatus: $('#flightStatus'),
    flightKV: $('#flightKV'),

    weatherHint: $('#weatherHint'),
    weatherTemp: $('#weatherTemp'),
    weatherCond: $('#weatherCond'),
    weatherKV: $('#weatherKV'),

    meetingHint: $('#meetingHint'),
    meetingTitle: $('#meetingTitle'),
    meetingTime: $('#meetingTime'),
    meetingAddr: $('#meetingAddr'),
    meetingKV: $('#meetingKV'),

    routeHint: $('#routeHint'),
    routeKV: $('#routeKV'),
    map: $('#map')
  };

  function titleize(key){
    return String(key)
      .replace(/_/g,' ')
      .replace(/\s+/g,' ')
      .trim()
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  function isIsoWithOffset(s){
    return typeof s === 'string' && /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)$/.test(s);
  }

  // Show the clock time written in the ISO string, ignoring viewer timezone.
  function isoToLocalClockString(iso){
    const m = String(iso).match(/^\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2})(?::\d{2})?(?:\.\d+)?([+-]\d{2}:\d{2}|Z)$/);
    if(!m) return iso;
    let hh = parseInt(m[1],10);
    const mm = m[2];
    const ampm = hh >= 12 ? 'PM' : 'AM';
    hh = hh % 12; if(hh === 0) hh = 12;
    return `${hh}:${mm} ${ampm}`;
  }

  function formatValue(v){
    if(v === null || v === undefined) return '—';
    if(typeof v === 'number') return Number.isFinite(v) ? String(v) : '—';
    if(typeof v === 'boolean') return v ? 'Yes' : 'No';
    if(typeof v === 'string') return isIsoWithOffset(v) ? isoToLocalClockString(v) : v;
    if(Array.isArray(v)) return v.map(formatValue).join(', ');
    if(typeof v === 'object') return JSON.stringify(v);
    return String(v);
  }

  function setKV(container, obj, recognizedKeys){
    container.innerHTML = '';
    if(!obj) return;

    const keys = Object.keys(obj);
    const rest = keys.filter(k => !recognizedKeys.has(k));
    const ordered = [...recognizedKeys].filter(k => k in obj).concat(rest);

    for(const k of ordered){
      const row = document.createElement('div');
      row.className = 'kvRow';
      const kk = document.createElement('div');
      kk.className = 'kvRow__k';
      kk.textContent = titleize(k);
      const vv = document.createElement('div');
      vv.className = 'kvRow__v';
      vv.textContent = formatValue(obj[k]);
      row.appendChild(kk);
      row.appendChild(vv);
      container.appendChild(row);
    }
  }

  let lastVerdictKey = null;
  let verdictAnimTimer = null;

  function pulseVerdict(){
    // Respect prefers-reduced-motion
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if(!els.verdictHero) return;

    els.verdictHero.classList.remove('is-updated');
    // Force reflow so re-adding the class retriggers transition.
    // eslint-disable-next-line no-unused-expressions
    els.verdictHero.offsetWidth;
    els.verdictHero.classList.add('is-updated');

    if(verdictAnimTimer) window.clearTimeout(verdictAnimTimer);
    verdictAnimTimer = window.setTimeout(() => {
      els.verdictHero.classList.remove('is-updated');
    }, 600);
  }

  function renderFlight(flight){
    if(!flight){
      els.flightHint.textContent = 'Waiting for flight details…';
      els.flightMain.textContent = '—';
      els.flightStatus.textContent = '—';
      els.flightKV.innerHTML = '';
      return;
    }

    const airline = flight.airline || '';
    const number = flight.flight_number || flight.number || '';
    els.flightMain.textContent = [airline, number].filter(Boolean).join(' ') || 'Flight';

    const status = flight.status;
    const delay = flight.delay_minutes;
    let statusText = status ? String(status) : 'On time';
    if(typeof delay === 'number' && Number.isFinite(delay) && delay !== 0){
      statusText += ` · ${delay > 0 ? '+' : ''}${delay} min`;
    }
    els.flightStatus.textContent = statusText;

    const hintParts = [];
    if(flight.estimated_arrival) hintParts.push(`ETA ${formatValue(flight.estimated_arrival)}`);
    if(flight.terminal) hintParts.push(`Terminal ${formatValue(flight.terminal)}`);
    if(flight.gate) hintParts.push(`Gate ${formatValue(flight.gate)}`);
    els.flightHint.textContent = hintParts.length ? hintParts.join(' · ') : 'Flight details updated.';

    const recognized = new Set([
      'airline','flight_number','number','status','delay_minutes',
      'gate','previous_gate','terminal','estimated_arrival','arrival','departure','estimated_departure'
    ]);
    setKV(els.flightKV, flight, recognized);
  }

  function renderWeather(weather){
    if(!weather){
      els.weatherHint.textContent = 'Waiting for weather…';
      els.weatherTemp.textContent = '—';
      els.weatherCond.textContent = '—';
      els.weatherKV.innerHTML = '';
      return;
    }

    const t = (weather.temperature_c ?? weather.temp_c ?? weather.temperature_f ?? weather.temp_f);
    let tempText = '—';
    if(typeof (weather.temperature_c ?? weather.temp_c) === 'number') tempText = `${Math.round(weather.temperature_c ?? weather.temp_c)}°C`;
    else if(typeof (weather.temperature_f ?? weather.temp_f) === 'number') tempText = `${Math.round(weather.temperature_f ?? weather.temp_f)}°F`;
    else if(typeof t === 'string') tempText = t;
    els.weatherTemp.textContent = tempText;

    els.weatherCond.textContent = weather.condition ? String(weather.condition) : (weather.conditions ? String(weather.conditions) : '—');

    const hintParts = [];
    if(weather.rain) hintParts.push('Rain');
    if(weather.wind_kph || weather.wind_mph) hintParts.push('Wind');
    if(weather.alert) hintParts.push('Alert');
    els.weatherHint.textContent = hintParts.length ? hintParts.join(' · ') : 'Weather updated.';

    const recognized = new Set([
      'temperature_c','temp_c','temperature_f','temp_f','condition','conditions',
      'rain','precip_mm','precip_chance','wind_kph','wind_mph','gust_kph','gust_mph','humidity','alert'
    ]);
    setKV(els.weatherKV, weather, recognized);
  }

  function renderMeeting(meeting){
    if(!meeting){
      els.meetingHint.textContent = 'Waiting for meeting details…';
      els.meetingTitle.textContent = '—';
      els.meetingTime.textContent = '—';
      els.meetingAddr.textContent = '—';
      els.meetingKV.innerHTML = '';
      return;
    }

    els.meetingTitle.textContent = meeting.title ? String(meeting.title) : (meeting.name ? String(meeting.name) : 'Meeting');

    const start = meeting.start || meeting.start_time || meeting.time;
    els.meetingTime.textContent = start ? `Starts ${formatValue(start)}` : 'Start time —';

    els.meetingAddr.textContent = meeting.address ? String(meeting.address) : (meeting.location ? String(meeting.location) : 'Address —');

    const hintParts = [];
    if(start) hintParts.push(formatValue(start));
    if(meeting.address) hintParts.push('Address ready');
    els.meetingHint.textContent = hintParts.length ? hintParts.join(' · ') : 'Meeting updated.';

    const recognized = new Set(['title','name','start','start_time','time','address','location','end','end_time']);
    setKV(els.meetingKV, meeting, recognized);
  }

  function renderVerdict(verdict){
    if(!verdict){
      lastVerdictKey = null;
      els.verdictHero.className = 'verdictHero is-waiting';
      els.verdictStatus.textContent = 'WAITING';
      els.verdictSlack.textContent = 'Waiting for a verdict…';
      els.verdictReason.textContent = '—';
      els.verdictKV.innerHTML = '';
      return;
    }

    const status = (verdict.status || 'tight').toLowerCase();
    const slack = verdict.slack_minutes;
    const reason = verdict.reason;

    const normalizedStatus = ['yes','tight','no'].includes(status) ? status : 'tight';
    els.verdictHero.className = `verdictHero is-${normalizedStatus}`;
    els.verdictStatus.textContent = normalizedStatus.toUpperCase();

    if(typeof slack === 'number' && Number.isFinite(slack)){
      if(slack >= 0) els.verdictSlack.textContent = `${slack} min of slack`;
      else els.verdictSlack.textContent = `${Math.abs(slack)} min late`;
    } else {
      els.verdictSlack.textContent = 'Timing unknown';
    }

    els.verdictReason.textContent = reason ? String(reason) : '—';

    const recognized = new Set(['status','slack_minutes','reason']);
    setKV(els.verdictKV, verdict, recognized);

    // Animate only when status or slack changes (not on first load)
    const verdictKey = `${normalizedStatus}|${(typeof slack === 'number' && Number.isFinite(slack)) ? slack : 'x'}`;
    if(lastVerdictKey !== null && verdictKey !== lastVerdictKey){
      pulseVerdict();
    }
    lastVerdictKey = verdictKey;
  }

  // ----- Map (route) -----
  let map = null;
  let mapLayer = null;
  let fromMarker = null;
  let toMarker = null;
  let routeLine = null;

  function ensureMap(){
    if(map || !els.map) return;
    if(!window.L) return;

    map = L.map(els.map, { zoomControl: true, attributionControl: true });
    mapLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Default view (NYC-ish) until route arrives
    map.setView([40.758, -73.9855], 11);
  }

  function renderRoute(route){
    if(!route){
      els.routeHint.textContent = 'Waiting for route…';
      els.routeKV.innerHTML = '';
      if(routeLine){ routeLine.remove(); routeLine = null; }
      if(fromMarker){ fromMarker.remove(); fromMarker = null; }
      if(toMarker){ toMarker.remove(); toMarker = null; }
      return;
    }

    const recognized = new Set(['from','to','mode','minutes']);
    setKV(els.routeKV, route, recognized);

    const from = route.from;
    const to = route.to;
    const mode = route.mode;
    const mins = route.minutes;

    const hintBits = [];
    if(mode) hintBits.push(String(mode).toUpperCase());
    if(typeof mins === 'number' && Number.isFinite(mins)) hintBits.push(`${mins} min`);
    if(from?.name && to?.name) hintBits.push(`${from.name} → ${to.name}`);
    els.routeHint.textContent = hintBits.length ? hintBits.join(' · ') : 'Route updated.';

    const hasCoords = (p) => p && Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lon));
    if(!hasCoords(from) || !hasCoords(to)) return;

    ensureMap();
    if(!map) return;

    const fromLatLng = [Number(from.lat), Number(from.lon)];
    const toLatLng = [Number(to.lat), Number(to.lon)];

    if(fromMarker){ fromMarker.remove(); }
    if(toMarker){ toMarker.remove(); }
    if(routeLine){ routeLine.remove(); }

    fromMarker = L.marker(fromLatLng).addTo(map).bindPopup(from.name || 'Arrival');
    toMarker = L.marker(toLatLng).addTo(map).bindPopup(to.name || 'Meeting');

    routeLine = L.polyline([fromLatLng, toLatLng], {
      color: '#89b4fa',
      weight: 5,
      opacity: 0.9
    }).addTo(map);

    const bounds = L.latLngBounds([fromLatLng, toLatLng]);
    map.fitBounds(bounds.pad(0.25));

    // If container was hidden/collapsed before, ensure proper sizing.
    setTimeout(() => map && map.invalidateSize(), 50);
  }

  function render(state){
    renderVerdict(state?.verdict ?? null);
    renderFlight(state?.flight ?? null);
    renderWeather(state?.weather ?? null);
    renderMeeting(state?.meeting ?? null);
    renderRoute(state?.route ?? null);
  }

  async function loadInitial(){
    try{
      const res = await fetch('./api/state', {cache:'no-store'});
      const data = await res.json();
      render(data);
    } catch (e){
      // keep empty state
    }
  }

  function connectEvents(){
    const es = new EventSource('./api/events');

    es.addEventListener('open', () => {
      els.connectionStatus.textContent = 'Live';
    });

    es.addEventListener('error', () => {
      els.connectionStatus.textContent = 'Reconnecting…';
    });

    es.addEventListener('state', (ev) => {
      try{
        const data = JSON.parse(ev.data);
        render(data);
        els.connectionStatus.textContent = 'Live';
      } catch (e) {
        // ignore bad payload
      }
    });
  }

  els.clearBtn.addEventListener('click', async () => {
    els.clearBtn.disabled = true;
    try{
      await fetch('./api/reset', {method:'POST'});
    } finally {
      els.clearBtn.disabled = false;
    }
  });

  // boot
  loadInitial();
  connectEvents();
})();
