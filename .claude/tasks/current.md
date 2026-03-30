## Tasks
Complete these in order. After each task, append status to PROGRESS.md. Stop and write "LIMIT REACHED" to PROGRESS.md if you hit token/context limits.
- [x] Fix the registration is lost after every restart of the server
- [x] Analyse if we can avoid to have a client/server architecture, and move everything in a single process (using threads). If it is feasible prepare a plan and add the tasks to this file

## Single-process refactor (from analysis above)
- [ ] Create `tuhi/app.py` — `TuhiApp` singleton that wraps the current `Tuhi` orchestrator, initialises the BLE event loop and loads config. No TCP socket.
- [ ] Rewrite `tuhi_cli.py` to import `TuhiApp` directly (no IPC client). Each command calls app methods and hooks signals directly.
- [ ] Simplify battery polling: drop cross-invocation timer, fetch once on connect.
- [ ] Remove `ipc_server.py`, `ipc_client.py`, and `TuhiIPCServer` instantiation from `base_win.py` once CLI is fully ported.
- [ ] Update WINDOWS_PORT.md with the the description of the architecture in a single process.