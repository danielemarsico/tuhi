# Tuhi Windows Port

## Overview

This port enables Tuhi to run on Windows by replacing all Linux-specific
dependencies with cross-platform alternatives. The original Linux code is
preserved unchanged.

## Architecture

| Linux Component | Windows Replacement | File |
|---|---|---|
| BlueZ (BLE) | bleak library | `tuhi/ble_bleak.py` |
| D-Bus (IPC) | Direct in-process calls | `tuhi/app.py` |
| UHID (/dev/uhid) | Logging stub | `tuhi/uhid_win.py` |
| GObject/GLib | Custom signal system | `tuhi/gobject_compat.py` |
| XDG directories | %APPDATA%/tuhi | `tuhi/config_win.py` |
| pycairo (PNG) | Pillow | `tuhi/export_win.py` |
| GTK GUI | tkinter GUI + CLI | `tuhi_gui.py`, `tuhi_cli.py` |

## Single-Process Architecture

All components run in a single Python process.  There is no daemon and no
network socket.  The CLI creates a `TuhiApp`, calls `start()` (which spins
up a background asyncio event loop for BLE via bleak), does its work, then
calls `stop()`.

```
┌──────────────────────────────────────────────────────────────┐
│                        tuhi_cli.py                           │
│                                                              │
│  cmd_list()  cmd_search()  cmd_listen()  cmd_fetch()         │
│       │            │             │             │             │
│       └────────────┴─────────────┴─────────────┘            │
│                         TuhiApp                              │
│                         (tuhi/app.py)                        │
│                              │                               │
│                         AppDevice                            │
│                         (per device, in-process state)       │
│                              │                               │
│                         TuhiDevice                           │
│                         (tuhi/base_win.py)                   │
│                              │                               │
│                         WacomDevice                          │
│              WacomProtocolSlate / IntuosPro / Spark          │
│                              │                               │
│                         BleakDeviceManager                   │
│                         BleakBLEDevice                       │
│                         BleakCharacteristic                  │
└──────────────────────────────┬───────────────────────────────┘
                               │  BLE (bleak / Windows Bluetooth API)
                               │
                        ┌──────┴──────┐
                        │ Wacom device │
                        │  (Bamboo,   │
                        │   Slate,    │
                        │  Intuos Pro)│
                        └─────────────┘
```

### Key objects

| Class | File | Role |
|---|---|---|
| `TuhiApp` | `tuhi/app.py` | Orchestrates BLE + config; public CLI API |
| `AppDevice` | `tuhi/app.py` | Per-device in-process state (replaces IPC proxy) |
| `TuhiDevice` | `tuhi/base_win.py` | Wires BleakBLEDevice to AppDevice; drives Wacom protocol |
| `BleakDeviceManager` | `tuhi/ble_bleak.py` | BLE scanning and connection (asyncio in background thread) |
| `TuhiConfig` | `tuhi/config_win.py` | Config/drawing persistence in `%APPDATA%\tuhi` |

---

## Usage

### GUI (recommended)

```
python tuhi_gui.py
```

Starts the tkinter GUI. No arguments needed — the registered device is loaded
from config automatically.

### CLI

```
python tuhi_cli.py list                        # List registered devices
python tuhi_cli.py search                      # Search for unregistered devices
python tuhi_cli.py search --register           # Search and register the first found device
python tuhi_cli.py listen XX:XX:XX:XX:XX:XX    # Listen for drawings (sync on button press)
python tuhi_cli.py fetch  XX:XX:XX:XX:XX:XX    # Export stored drawings as JSON
python tuhi_cli.py fetch  XX:XX:XX:XX:XX:XX --svg  # Export as JSON + SVG
python tuhi_cli.py live   XX:XX:XX:XX:XX:XX    # Stream live pen data; Ctrl+C writes JSON
python tuhi_cli.py live   XX:XX:XX:XX:XX:XX --svg  # Also write SVG on exit
```

---

---

## GUI Application (`tuhi_gui.py`)

The GUI is built with **tkinter** (Python built-in — zero extra dependencies).
Entry point: `python tuhi_gui.py`.

### Layout

```
┌──────────────────────────────────────────────────────────┐
│  daniele bamboo  F4:21:DE:4D:26:BF                       │
│  ● Normal  ○ Live        ● Landscape  ○ Portrait         │
│  [status bar]                                            │
├──────────────────────────────────────────────────────────┤
│  Normal:  [Register]  [Listen]  [Fetch]                  │
│           ┌──Notebook───────────────────────────────┐   │
│           │ 2024-01-15 10:30 │ 2024-01-16 … │       │   │
│           │  <DrawingCanvas>                        │   │
│           └─────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────┤
│  Live:    [Start Live]                                   │
│           ┌──LiveCanvas──────────────────────────────┐  │
│           │  (strokes appear here in realtime)        │  │
│           └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### Key classes

| Class | Role |
|---|---|
| `TuhiGUIApp(tk.Tk)` | Root window; owns `TuhiApp`, mode/orientation `StringVar`s, status label |
| `DrawingCanvas(tk.Canvas)` | Renders a `Drawing` as polylines; letterboxed, orientation-aware |
| `LiveCanvas(tk.Canvas)` | Streams live pen points in real time; same coord transform as `DrawingCanvas` |

### Orientation transform

Applied to every canvas before letterbox scaling:

| Mode | Transform |
|---|---|
| Landscape | Identity — `(x, y)` unchanged |
| Portrait | 90° CCW — `x' = y`, `y' = W − x`; canvas W↔H swapped |

Pressure → line width: `pressure / 0x10000 * 2 + 0.5` px (≈0.5 px at zero, ≈2.5 px at max).

### Normal mode flows

- **Register:** background `threading.Thread` calls `TuhiApp.search()`; status updates
  via `root.after(0, ...)`. On device found, a `tk.Toplevel` dialog prompts the user
  to press the hardware button; `TuhiApp.register()` completes pairing.
- **Listen:** background thread calls `TuhiApp.start_listening()`; button toggles to
  `[Stop]`. Each new drawing arrives via callback → added as a `ttk.Notebook` tab.
- **Fetch:** synchronous disk read via `TuhiApp.config.load_drawings()`; clears
  existing tabs and adds one per drawing.

### Live mode

Switching the `Normal | Live` selector hides the Notebook and shows a single
`LiveCanvas` filling the window. `[Start Live]` calls `TuhiApp.start_live()` with an
`on_pen_point` callback delivered via `root.after(0, ...)`:

- `in_proximity=True` → append point to current polyline segment and redraw.
- `in_proximity=False` (pen lift) → seal segment; next point starts a new one.

Switching back to Normal mode automatically calls `TuhiApp.stop_live()`.

### Thread safety

All BLE operations run in background `threading.Thread`s. UI mutations are always
posted to the main thread via `root.after(0, callback)` — never called directly
from BLE threads.

---

## Step-by-Step Flows

### 1. Device Registration (first-time pairing)

```
tuhi_cli.py (TuhiApp)                        Wacom device
    │                                              │
    │  search(timeout, on_found)                   │
    │── BLE scan start ─────────────────────────>  │
    │                                              │
    │                        <─ advertisement ────│
    │                           (mfr_data len=4   │
    │                            = pairing mode)  │
    │                                              │
    │  _add_device() → TuhiDevice(REGISTER)        │
    │  on_found("Found: <addr>")                   │
    │                                              │
    │  register(address, on_button_press)          │
    │── BLE connect ────────────────────────────> │
    │                         <─ connected ───────│
    │                                              │
    │── REGISTER_PRESS_BUTTON ──────────────────> │
    │  on_button_press() → "[Press the button]"    │
    │                         <─ button press ────│
    │                                              │
    │                           determine protocol │
    │── SET_TIME / GET_TIME / GET_FIRMWARE ──────> │
    │── GET_BATTERY ────────────────────────────> │
    │                                              │
    │                           save settings.ini  │
    │── BLE disconnect ─────────────────────────> │
    │  "Registration complete."                    │
```

### 2. Fetching Drawings (listen / sync)

```
tuhi_cli.py (TuhiApp)                        Wacom device
    │                                              │
    │  start_listening(address, on_drawings)       │
    │── BLE scan start ─────────────────────────> │
    │                                              │
    │                        <─ advertisement ────│
    │                           (device in config) │
    │                                              │
    │── BLE connect ────────────────────────────> │
    │                         <─ connected ───────│
    │                                              │
    │── SET_TIME / GET_BATTERY / GET_FIRMWARE ──> │
    │── SELECT_GATT ────────────────────────────> │
    │                                              │
    │                        <─ offline pen data ─│
    │                           (stroke packets)  │
    │                                              │
    │  parse strokes → save <timestamp>.json       │
    │  on_drawings(app_dev)                        │
    │── BLE disconnect ─────────────────────────> │
```

### 3. Live Pen Streaming

```
tuhi_cli.py / tuhi_gui.py (TuhiApp)         Wacom device
    │                                              │
    │  start_live(address, on_pen_point)           │
    │── BLE scan start ─────────────────────────> │
    │                        <─ advertisement ────│
    │── BLE connect ────────────────────────────> │
    │                         <─ connected ───────│
    │                                              │
    │── SET_MODE=LIVE ──────────────────────────> │
    │                                              │
    │           (per pen point, continuously)      │
    │                        <─ 0xa1 packet ──────│
    │  _on_pen_data_changed()                      │
    │  emit('live-pen-data', x, y, pressure, True) │
    │  on_pen_point(x, y, pressure, True)          │
    │                                              │
    │              (pen lifted)                    │
    │                        <─ ff ff ff ff ff ff ─│
    │  emit('live-pen-data', 0, 0, 0, False)       │
    │  on_pen_point(0, 0, 0, False)                │
    │                                              │
    │  [Ctrl+C or stop_live()]                     │
    │  seal drawing → write live_<ts>.json [.svg]  │
    │── BLE disconnect ─────────────────────────> │
```

Signal chain: `WacomProtocolBase → WacomDevice → TuhiDevice → AppDevice → caller callback`

### 4. Exporting Drawings

Drawings are read directly from disk — no BLE needed:

```python
app = TuhiApp()
app.start()
drawings = app.config.load_drawings(address)  # returns list of Drawing objects
for d in drawings:
    print(d.to_json())
app.stop()
```

---

## Data Storage

Drawings and config are stored in `%APPDATA%\tuhi\`:

```
C:\Users\<user>\AppData\Roaming\tuhi\
  F4_21_DE_4D_26_BF\          ← BT address with _ instead of :
    settings.ini               ← address, UUID, protocol, name
    <timestamp>.json           ← one file per drawing
    raw\
      log-*.yaml               ← raw BLE protocol log
  session-logs\
    tuhi-YY-MM-DD-HH-MM-SS.log
  cached_uuid.txt              ← registration UUID cache
```

---

## New Files

| File | Purpose |
|---|---|
| `tuhi/app.py` | `TuhiApp` (orchestrator) and `AppDevice` (in-process device state) |
| `tuhi/gobject_compat.py` | Lightweight GObject replacement (signals, properties, timers) |
| `tuhi/ble_bleak.py` | BLE backend using bleak (`BleakDeviceManager`, `BleakBLEDevice`, `BleakCharacteristic`) |
| `tuhi/uhid_win.py` | UHID stub — logs pen events; live mode pen injection not available on Windows |
| `tuhi/config_win.py` | Config using `%APPDATA%\tuhi` instead of XDG |
| `tuhi/drawing_win.py` | Drawing model without `gi.repository` |
| `tuhi/wacom_win.py` | Wacom protocol (same logic, Windows-compatible imports) |
| `tuhi/base_win.py` | `TuhiDevice` — wires BLE device to AppDevice and drives Wacom protocol |
| `tuhi/export_win.py` | SVG/PNG export using svgwrite + Pillow |
| `tuhi_cli.py` | CLI entry point |
| `tuhi_gui.py` | tkinter GUI entry point |

## Installation

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-windows.txt
.venv\Scripts\python tuhi_cli.py list
```

Requirements: `bleak`, `svgwrite`, `Pillow`. Python 3.12+.

## Known Issues / Design Notes

### BLE connection guard (`ble_bleak.py`)
BLE advertisements arrive ~10× per second during scanning. Each `device-updated`
event triggers `_add_device` → `d.listen()` → `connect_device()`. Without a guard,
every advertisement spawned a new connection thread, each overwriting the shared
`_bleak_client` reference before the previous thread finished connecting — causing
bleak to raise *"Service Discovery has not been performed yet"*.

**Fix:** `BleakBLEDevice` now has a `_connecting` flag. `connect_device()` returns
immediately if a connection is already in progress. The `BleakClient` instance is
kept as a local variable and only written to `self._bleak_client` after service
discovery succeeds.

## Limitations

- **Live mode — system injection**: Pen data is streamed into the GUI / CLI
  in real time but is NOT injected into the Windows input system.
  Windows has no equivalent of Linux's `/dev/uhid`. A future integration
  with ViGEmBus or a custom HID minidriver could enable this.
- **BLE stability**: bleak uses the Windows Bluetooth API, which may behave
  differently from BlueZ. Connection reliability depends on the Windows
  Bluetooth stack and driver quality.

## Compatibility

The original Linux codebase is completely untouched. All new Windows code
lives in separate files (`*_win.py`, `ble_bleak.py`, `app.py`, etc.).
