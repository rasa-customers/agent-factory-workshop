# Dashboard workspace

`app.py` is the fixed server contract (see its docstring). **Do not change it.**
Build the user interface in `static/` — plain HTML, CSS and JavaScript, no build step.
The page should load the current state from `GET /api/state` and stay live with `EventSource('/api/events')`
(listen for the `state` event; its data is the full state JSON).

The state has four panels (`flight`, `weather`, `meeting`, `verdict`) and one extra key, `route`: data for
a map, when someone asks for one —
`{"from": {"name", "lat", "lon"}, "to": {"name", "lat", "lon"}, "mode": "car"|"subway", "minutes": 55}`.
Don't show `route` as a panel of its own unless the brief asks for a map.

Nothing loads from the internet, with one exception: if the brief asks for a map, use Leaflet
(`https://unpkg.com/leaflet@1.9.4/dist/leaflet.css` and `.../leaflet.js`) with OpenStreetMap tiles
(`https://tile.openstreetmap.org/{z}/{x}/{y}.png`, attribution "© OpenStreetMap contributors"). Draw a
marker at `route.from` and `route.to` and a line between them, and fit the map to both.
