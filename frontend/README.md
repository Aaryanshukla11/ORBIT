# ORBIT Frontend Developer Console (Milestone M0)

This is the lightweight developer test interface establishing the WebSocket client $\leftrightarrow$ backend runtime boundary for Milestone M0.

## Running Locally

1. Start the ORBIT backend gateway:
```powershell
python -m orbit --port 8765
```

2. Serve or open `frontend/index.html` directly in any modern browser:
- Using Python's built-in HTTP server:
```powershell
python -m http.server 3000 --directory frontend
```
- Open `http://localhost:3000` in Google Chrome or Microsoft Edge.

3. Click **Connect** to connect to `ws://127.0.0.1:8765/ws`.
4. Enter a task instruction (e.g. "Move cursor and type test text") and click **Submit Task**.
5. Watch real-time streaming state changes, plan updates, action stages, and test human takeover preemption buttons.
