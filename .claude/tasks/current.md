## Tasks
Complete these in order. After each task, append status to PROGRESS.md. Stop and write "LIMIT REACHED" to PROGRESS.md if you hit token/context limits.
- [x] Fix the registration is lost after every restart of the server
- [x] Analyse if we can avoid to have a client/server architecture, and move everything in a single process (using threads). If it is feasible prepare a plan and add the tasks to this file

## Single-process refactor (from analysis above)
- [x] Create `tuhi/app.py` — `TuhiApp` singleton that wraps the current `Tuhi` orchestrator, initialises the BLE event loop and loads config. No TCP socket.
- [x] Rewrite `tuhi_cli.py` to import `TuhiApp` directly (no IPC client). Each command calls app methods and hooks signals directly.
- [x] Simplify battery polling: drop cross-invocation timer, fetch once on connect.
- [x] Remove `ipc_server.py`, `ipc_client.py`, and `TuhiIPCServer` instantiation from `base_win.py` once CLI is fully ported.
- [x] Update WINDOWS_PORT.md with the the description of the architecture in a single process.

## Bug fixes (post-refactor, verified working on real hardware)
- [x] Fix BLE connection race condition in `ble_bleak.py` (`connect_device` spawning multiple threads)
- [x] Persist device name in `settings.ini` during registration

---

## Macro-activity A: Simple GUI (`tuhi_gui.py`)

**Framework:** tkinter (built-in, zero extra dependencies).
**Rendering:** draw strokes directly from `Drawing.strokes` onto `tkinter.Canvas`
— no SVG library needed.

### A1 — Window skeleton
- [ ] Create `tuhi_win/tuhi_gui.py` with `TuhiGUIApp(tk.Tk)`.
- [ ] Top bar: `device_label` (StringVar — shows address + name, or "No device registered"),
  three buttons `[Register]` `[Listen]` `[Fetch]`, a `status_label` for
  live feedback ("Searching…", "Listening…", "Ready", etc.).
- [ ] Main area: `ttk.Notebook` (empty at startup).
- [ ] On startup: read `TuhiConfig`, populate `device_label` if a device is already registered.

### A2 — DrawingCanvas widget
- [ ] `DrawingCanvas(tk.Canvas)`: takes a `Drawing` object, renders all strokes
  as polylines.
- [ ] Coordinate normalisation: `Drawing.dimensions = (W, H)` in device units →
  scale to canvas pixel size, preserving aspect ratio with letterboxing.
- [ ] Pressure → line width: map `pressure / 0x10000 * 2 + 0.5` px
  (thin at zero, ~2.5 px at max).
- [ ] Pen-up gaps (consecutive points with `position is None`) break the polyline.

### A3 — Register flow
- [ ] `[Register]` button: disabled while another operation is running.
- [ ] Run `TuhiApp.search(timeout=30, on_found=..., stop_early=True)` in a
  `threading.Thread`; update `status_label` via `root.after(0, ...)` on each event.
- [ ] When a device is found: show a `tk.Toplevel` dialog "Press the button on
  your device" and call `TuhiApp.register(address, on_button_press=...)`.
- [ ] On completion: update `device_label`, re-enable buttons.

### A4 — Listen flow
- [ ] `[Listen]` button: calls `TuhiApp.start_listening(address, on_drawings=cb)`
  in a background thread; button label toggles to `[Stop]`.
- [ ] `on_drawings(app_dev)` callback (arrives on BLE thread): calls
  `root.after(0, lambda: _add_drawing_tab(drawing))` for each new drawing.
- [ ] `[Stop]` calls `TuhiApp.stop_listening(address)`.

### A5 — Fetch flow
- [ ] `[Fetch]` button: calls `TuhiApp.config.load_drawings(address)` (disk read,
  no BLE needed); for each `Drawing` adds a `ttk.Notebook` tab labelled with the
  human-readable timestamp and shows a `DrawingCanvas`.
- [ ] If Notebook already has tabs, clear them first.
- [ ] If no drawings: show a `tk.messagebox` info prompt.

---

## Macro-activity B: Live mode (`tuhi_win`)

**Device:** Bamboo Folio registers as `Protocol = slate`.
**Protocol:** `WacomProtocolSlate` supports live mode via `SET_MODE=LIVE`.
Live pen data arrives as BLE GATT notifications on
`WACOM_CHRC_LIVE_PEN_DATA_UUID` and is decoded in `_on_pen_data_changed()`.
**Current Windows stub:** coordinates from `0xa1` packets are parsed but only
forwarded to `UHIDDevice.call_input_event()` (a no-op stub on Windows).

**Output format for CLI live command:** JSON (same schema as stored drawings,
produced by `Drawing.to_json()`). Optional `--svg` flag also writes an SVG
alongside. Filename: `live_<timestamp>.json` / `live_<timestamp>.svg`.
Drawings are accumulated in memory during the live session; file is written on
`Ctrl+C` (or when the BLE session ends naturally).

**GUI mode switch:** a `ttk.Combobox` (or pair of radio buttons)
`Normal | Live` at the top of the window.
- **Normal mode** (default): shows `[Register]` `[Listen]` `[Fetch]` buttons and
  the Notebook of fetched drawings.
- **Live mode**: hides Listen/Fetch, shows `[Start Live]` / `[Stop Live]` toggle
  and a single fullscreen "Live" canvas that streams incoming pen data in real time.
  Switching back to Normal mode stops any active live session.

### B1 — Expose live pen data as a signal
- [ ] Add `'live-pen-data': (1, None, (int, int, int, bool))` signal to
  `WacomProtocolBase.__gsignals__` and `WacomDevice.__gsignals__`.
- [ ] In `WacomProtocolBase._on_pen_data_changed()`:
  - `0xa1` in-proximity point → `emit('live-pen-data', x, y, pressure, True)`.
  - `0xa1` `\xff\xff\xff\xff\xff\xff` pen-lift → `emit('live-pen-data', 0, 0, 0, False)`.
  - Keep existing UHID call so Linux behaviour is unchanged.
- [ ] `WacomDevice`: forward the signal from the inner protocol object (same
  pattern as `drawing` and `battery-status` signals).

### B2 — Wire live signal through AppDevice / TuhiDevice / TuhiApp
- [ ] Add `'live-pen-data': (1, None, (int, int, int, bool))` to
  `AppDevice.__gsignals__`.
- [ ] In `TuhiDevice._on_bluez_device_connected` (LIVE branch): connect
  `wacom_device.live-pen-data → app_dev.emit('live-pen-data', ...)`.
- [ ] `TuhiApp.start_live(address, on_pen_point=None)`:
  set `app_dev.live = True`; if `on_pen_point` given, connect it to
  `app_dev.live-pen-data` and start discovery.
- [ ] `TuhiApp.stop_live(address)`: set `app_dev.live = False`.

### B3 — CLI `live` command
- [ ] Add `live` subparser to `tuhi_cli.py`:
  ```
  python tuhi_cli.py live XX:XX:XX:XX:XX:XX [--svg] [--output PATH]
  ```
- [ ] Accumulate incoming `(x, y, pressure, in_proximity)` events into a
  `Drawing` object (device dimensions from `TuhiConfig`).
  - `in_proximity=True` → add point to current stroke.
  - `in_proximity=False` (pen lift) → seal stroke, start next.
- [ ] On `Ctrl+C` or BLE disconnect: seal the drawing, call
  `Drawing.to_json()`, write `live_<timestamp>.json`.
- [ ] If `--svg`: also write `live_<timestamp>.svg` via `export_win.JsonSvg`.
- [ ] Print summary: number of strokes, output files written.

### B4 — GUI mode switch + live canvas
- [ ] Add `Normal | Live` mode selector (radio buttons or segmented control)
  below the device label.
- [ ] **Normal mode:** existing Register / Listen / Fetch / Notebook layout.
- [ ] **Live mode:** hide Notebook; show a single `LiveCanvas(tk.Canvas)` that
  fills the window. `[Start Live]` / `[Stop Live]` toggle button.
- [ ] `LiveCanvas` receives `on_pen_point(x, y, pressure, in_proximity)` via
  `root.after(0, ...)`:
  - `in_proximity=True`: append to current polyline segment; redraw.
  - `in_proximity=False`: seal segment; next point starts a new segment.
  - Coordinates normalised using device dimensions from config.
- [ ] Switching mode selector back to Normal stops any active live session.

### B5 — Bamboo Folio smoke-test
- [ ] CLI: `python tuhi_cli.py live F4:21:DE:4D:26:BF --svg` → draw → Ctrl+C →
  verify `live_<ts>.json` and `live_<ts>.svg` are written correctly.
- [ ] GUI: switch to Live mode → `[Start Live]` → draw → strokes appear in
  real time → `[Stop Live]` → switch back to Normal mode.