## Autonomous Mode 
- TODO list lives in `.claude/tasks/current.md` 
- Log progress to `.claude/tasks/PROGRESS.md`
- Porting to windows details to `tuhi_win/WINDOWS_PORT.md`

## GUI Layout (`tuhi_win/tuhi_gui.py`)

```
┌──────────────────────────────────────────────────────────┐
│  daniele bamboo  F4:21:DE:4D:26:BF                       │
│  ● Normal  ○ Live        ○ Landscape  ● Portrait         │
│  [status bar]                                            │
├──────────────────────────────────────────────────────────┤
│  Normal:  [Register]  [Listen]  [Fetch]                  │
│           ┌──Notebook───────────────────────────────┐   │
│           │ 2024-01-15 10:30 × │ 2024-01-16 × │      │   │
│           │  [Save SVG] [Delete]                    │   │
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
- Orientation selector (`Landscape | Portrait`) is always visible. Default is **Portrait**.
  Changing orientation does NOT redraw existing tabs — each drawing tab keeps the
  orientation it was opened with. The selector sets the default for new tabs and
  redraws the LiveCanvas. Portrait rotates coordinates 90° CW (swap W/H).
- **Normal mode**: Register → search + register new device. Listen → sync offline
  drawings from device (BLE). Fetch → reload drawings from disk. Drawings are also
  loaded automatically at startup.
- **Tab close**: each tab label ends with `×`; clicking it closes the tab without
  deleting the file from disk.
- **Per-tab toolbar**: two buttons inside each drawing tab:
  - `[Save SVG]` — export the drawing as SVG (file save dialog).
  - `[Delete]` — permanently delete the drawing file from disk and close the tab.
- **Live mode**: Start Live → streams real-time pen strokes into LiveCanvas.
  One fullscreen canvas, no tabs.