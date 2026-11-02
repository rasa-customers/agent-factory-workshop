# Dashboard workspace

`app.py` is the fixed server contract (see its docstring). **Do not change it.**
Build the user interface in `static/` — plain HTML, CSS and JavaScript, no build step, no CDN.
The page should load the current state from `GET /api/state` and stay live with `EventSource('/api/events')`
(listen for the `state` event; its data is the full state JSON).
