# Task Progress

## Macro-activity A: Simple GUI
**Status: PLANNED — not started**
See `current.md` tasks A1–A5.

Key design decisions recorded here:
- **Framework:** tkinter (zero extra dependencies).
- **Rendering:** stroke data from `Drawing.strokes` drawn directly as
  `Canvas.create_line` polylines — no SVG library needed.
- **Coordinate space:** `Drawing.dimensions = (W, H)` in device units; scale to
  canvas pixel size preserving aspect ratio.
- **Pressure → line width:** `pressure / 0x10000 * 2 + 0.5 px`.
- **Async safety:** all BLE operations run in background threads; UI updates use
  `root.after(0, callback)`.
- **Multi-drawing:** `ttk.Notebook`, one tab per `Drawing` with timestamp label.

---

## Macro-activity B: Live mode
**Status: PLANNED — not started**
See `current.md` tasks B1–B5.

Key design decisions recorded here:
- Device (`daniele bamboo`, `F4:21:DE:4D:26:BF`) registered as `Protocol = slate`;
  `WacomProtocolSlate` already sends `SET_MODE=LIVE` in `start_live()`.
- Live pen data decoded in `WacomProtocolBase._on_pen_data_changed()`:
  `0xa1` packets → `(x, y, pressure)` in device units (same range as stored drawings).
  Pen-lift: `\xff\xff\xff\xff\xff\xff`.
- On Windows, UHID injection is a no-op stub; live data routed via a new
  `live-pen-data` signal: `WacomProtocolBase → WacomDevice → TuhiDevice → AppDevice`.
- **CLI output format:** JSON (same `Drawing.to_json()` schema as stored drawings) +
  optional `--svg`. File written on Ctrl+C: `live_<timestamp>.json`.
- **GUI:** `Normal | Live` mode selector. Normal = existing Register/Listen/Fetch/Notebook.
  Live = fullscreen `LiveCanvas` + `[Start Live]`/`[Stop Live]` toggle. Switching away
  from Live mode auto-stops the session.
- No changes to the Linux code path needed.

---

## Task 1: Fix registration lost after server restart
**Status: DONE**

**Root cause:** In `_add_device` (base_win.py:320), the REGISTER mode condition did not check
whether the device already had a UUID in config. Wacom devices routinely advertise with
4-byte manufacturer_data regardless of pairing state, so every restart would force the
already-registered device back into REGISTER mode, losing the saved config.

**Fix:** Added `uuid is None` guard to the condition:
```python
# Before
if from_live_update and len(bluez_device.manufacturer_data or []) == 4:
# After
if uuid is None and from_live_update and len(bluez_device.manufacturer_data or []) == 4:
```

---

## Task 3: Single-process refactor
**Status: DONE**

### Changes made

**`tuhi_win/tuhi/app.py`** (new file)
- `AppDevice(Object)` — lightweight in-process device state; satisfies the
  same interface that `TuhiDevice` expects from its `dbus_device` slot
  (signals `register-requested`, `notify::listening`, `notify::live`;
  methods `add_drawing()`, `notify_button_press_required()`; property `uhid_fd`).
- `TuhiApp` — orchestrates `BleakDeviceManager` + `TuhiConfig` without any
  TCP socket.  Public API: `start()`, `stop()`, `list_devices()`, `search()`,
  `register()`, `start_listening()`, `stop_listening()`.
  `AppDevice` objects are created eagerly in `start_listening()` so that
  a pre-created device state is available when BLE discovery fires.

**`tuhi_win/tuhi_cli.py`** (rewritten)
- Each command (`list`, `search`, `listen`, `fetch`) creates a `TuhiApp`,
  calls `start()`, uses the public API, then calls `stop()`.
- No `TuhiIPCClientManager`, `IPCConnection`, or TCP socket anywhere.

**`tuhi_win/tuhi/base_win.py`** (simplified)
- Removed: `Tuhi` class (replaced by `TuhiApp`), IPC imports, battery timer
  (`BATTERY_UPDATE_MIN_INTERVAL`, `_battery_timer_source`,
  `_last_battery_update_time`, `_on_battery_timeout`).
- Kept: `TuhiDevice`, `setup_logging`.
- `_on_battery_status` now just sets state/percent on connect — no timer.

**Deleted**: `tuhi_win/tuhi/ipc_server.py`, `tuhi_win/tuhi/ipc_client.py`

**`tuhi_win/tuhi_windows.py`** (stub)
- No longer a server daemon; prints a redirect message to `tuhi_cli.py`.

**`tuhi_win/WINDOWS_PORT.md`** — updated to describe single-process architecture.

---

## Bug fix: BLE connection race condition
**Status: DONE — verified on real hardware (Wacom Bamboo F4:21:DE:4D:26:BF)**

**Root cause:** `BleakBLEDevice.connect_device()` started a new OS thread on every
call. BLE advertisement events (`device-updated`) fire ~10× per second during scanning,
so each scan update triggered another thread. Each thread overwrote the shared
`self._bleak_client` attribute with a freshly-created (not yet connected) `BleakClient`.
The first thread's `_async_connect` then read back the replacement client, which had not
had `connect()` called on it, causing bleak to raise
`"Service Discovery has not been performed yet"`.

**Symptom:** rapid repeated `ERROR: Connection failed: Service Discovery has not been
performed yet` and no drawings synced.

**Fix (`tuhi_win/tuhi/ble_bleak.py`):**
- Added `self._connecting = False` flag to `BleakBLEDevice.__init__`.
- `connect_device()` returns immediately if `_connecting` is already True.
- The `BleakClient` instance is now a local variable inside the connection thread —
  it is never written to `self._bleak_client` until after `_async_connect` succeeds.
- `_async_connect(client)` now receives the client as an explicit parameter, sets
  `self._bleak_client = client` only after service discovery completes, then clears
  `_connecting`.

---

## Bug fix: device name not persisted
**Status: DONE**

**Root cause:** `TuhiConfig.new_device()` only saved Address, UUID, Protocol to
`settings.ini`. The friendly name (e.g. "daniele bamboo") came from the BLE
advertisement and was lost after registration.

**Fix:**
- `config_win.py`: added optional `name` parameter to `new_device()`; written to
  `settings.ini` when present.
- `base_win.py` `_on_uuid_updated`: passes `bluez_device.name` to `new_device()`.
- `app.py` `list_devices()`: reads `name` key from config (with `Name` fallback).

---

## Task 2: Analyse single-process feasibility
**Status: DONE — feasible, plan below**

### Findings

The client/server split exists for operational convenience (keep a daemon running, issue
short-lived CLI commands), not for any hard technical reason. All state is either transient
or already persisted to disk (`%APPDATA%\tuhi`).

**What the server maintains across CLI invocations:**
- Device metadata (address, UUID, protocol) — already on disk in `settings.ini`
- Drawings — already on disk as `<timestamp>.json`
- Battery state — transient, refetched on each BLE connection
- Active BLE connections / asyncio event loop

**No technical blocker** prevents collapsing to a single process. The Bleak asyncio loop
can run in a background thread within the CLI process, exactly as it already does in the
server. The IPC layer (TCP JSON-RPC, ~500 lines across `ipc_server.py` + `ipc_client.py`)
becomes unnecessary.

### Plan

Add the following tasks to current.md for the single-process refactor:

1. **Create `tuhi/app.py`** — a `TuhiApp` singleton class (wrapping the current `Tuhi`
   orchestrator) that each CLI command can instantiate. It initialises the BLE event loop
   and loads config from disk. No TCP socket.

2. **Rewrite `tuhi_cli.py`** to import `TuhiApp` directly instead of
   `TuhiIPCClientManager`. Each command calls app methods and hooks into signals directly.
   Remove all `IPCConnection` / `TuhiIPCClient*` usage.

3. **Remove `ipc_server.py` and `ipc_client.py`** once CLI is ported.

4. **Remove the daemon socket / server thread** from `base_win.py` (`TuhiIPCServer`
   instantiation).

5. **Battery polling:** simplify to a single fetch-on-connect (drop
   `_battery_timer_source` cross-invocation persistence).

6. **Async lifecycle:** each CLI command calls `app.start()` (spins up BLE loop) and
   `app.stop()` on exit.

**Estimated scope:** ~1 000–1 500 lines changed. The protocol, BLE, config, and export
code remain untouched.

**Trade-offs:**
- Pro: no daemon to manage, simpler deployment, fewer threads/sockets
- Con: slightly longer startup per command (BLE init ~200 ms); cannot run two CLI
  commands simultaneously (shared asyncio loop — mitigatable with a lock or by
  running the loop for the duration of the command only)
