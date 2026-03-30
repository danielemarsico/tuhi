# Task Progress

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
