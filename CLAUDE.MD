## Autonomous Mode 
- TODO list lives in `.claude/tasks/current.md` 
- Log progress to `.claude/tasks/PROGRESS.md`
- Porting to windows details to `tuhi_win/WINDOWS_PORT.md`

## GUI Layout (`tuhi_win/tuhi_gui.py`)

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

- Mode selector (`Normal | Live`) is always visible; switching stops any active session.
- Orientation selector (`Landscape | Portrait`) is always visible; applies immediately
  to all visible canvases. Portrait rotates coordinates 90° CCW (swap W/H, flip Y→X).
- **Normal mode**: Register → search + register new device. Listen → sync offline
  drawings from device (BLE). Fetch → load drawings already on disk, populate Notebook tabs.
- **Live mode**: Start Live → streams real-time pen strokes into LiveCanvas.
  One fullscreen canvas, no tabs.