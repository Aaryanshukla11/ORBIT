/**
 * ORBIT Milestone M0 Developer Console Client
 */

let ws = null;
let currentTaskId = null;

// DOM Elements
const wsUrlInput = document.getElementById("wsUrl");
const btnConnect = document.getElementById("btnConnect");
const btnDisconnect = document.getElementById("btnDisconnect");
const connIndicator = document.getElementById("connIndicator");
const connStatus = document.getElementById("connStatus");
const systemStateBadge = document.getElementById("systemStateBadge");

const taskPromptInput = document.getElementById("taskPrompt");
const btnSubmitTask = document.getElementById("btnSubmitTask");
const btnCancelTask = document.getElementById("btnCancelTask");

const btnTriggerTakeover = document.getElementById("btnTriggerTakeover");
const btnReleaseTakeover = document.getElementById("btnReleaseTakeover");

const logTimeline = document.getElementById("logTimeline");
const btnClearLogs = document.getElementById("btnClearLogs");

function updateConnectionState(connected) {
  if (connected) {
    connIndicator.classList.add("connected");
    connStatus.textContent = "Connected";
    btnConnect.disabled = true;
    btnDisconnect.disabled = false;
    btnSubmitTask.disabled = false;
    btnTriggerTakeover.disabled = false;
  } else {
    connIndicator.classList.remove("connected");
    connStatus.textContent = "Disconnected";
    btnConnect.disabled = false;
    btnDisconnect.disabled = true;
    btnSubmitTask.disabled = true;
    btnCancelTask.disabled = true;
    btnTriggerTakeover.disabled = true;
    btnReleaseTakeover.disabled = true;
  }
}

function appendLog(event) {
  const entry = document.createElement("div");
  entry.className = "log-entry";

  const timeStr = new Date(event.timestamp || Date.now()).toLocaleTimeString();
  const seq = event.event_seq ? `#${event.event_seq}` : "-";
  const type = event.event_type || "UNKNOWN";
  const payloadStr = JSON.stringify(event.payload || {});

  entry.innerHTML = `
    <span class="log-time">${timeStr}</span>
    <span class="log-seq">${seq}</span>
    <span class="log-type ${type}">${type}</span>
    <span class="log-payload">${payloadStr}</span>
  `;

  logTimeline.appendChild(entry);
  logTimeline.scrollTop = logTimeline.scrollHeight;

  // Update badges
  if (event.payload && event.payload.system_state) {
    systemStateBadge.textContent = event.payload.system_state;
  }
  if (type === "TASK_STATE_CHANGED") {
    if (event.payload.status === "RUNNING") {
      btnCancelTask.disabled = false;
    } else if (["COMPLETED", "FAILED", "CANCELLED"].includes(event.payload.status)) {
      btnCancelTask.disabled = true;
    }
  }
  if (type === "TAKEOVER_EVENT") {
    if (event.payload.is_active) {
      systemStateBadge.textContent = "HUMAN_TAKEOVER";
      btnReleaseTakeover.disabled = false;
      btnTriggerTakeover.disabled = true;
    } else {
      btnReleaseTakeover.disabled = true;
      btnTriggerTakeover.disabled = false;
    }
  }
}

function sendCommand(type, payload = {}) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const cmd = {
    command_id: `cmd_${Math.random().toString(36).substring(2, 10)}`,
    command_type: type,
    session_id: "dev_console_sess",
    timestamp: new Date().toISOString(),
    payload: payload,
  };
  ws.send(JSON.stringify(cmd));
}

// Event Listeners
btnConnect.addEventListener("click", () => {
  const url = wsUrlInput.value.trim();
  try {
    ws = new WebSocket(url);

    ws.onopen = () => {
      updateConnectionState(true);
      appendLog({ event_type: "CLIENT_CONNECTED", payload: { url } });
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        appendLog(data);
      } catch (e) {
        console.error("Failed to parse event:", evt.data);
      }
    };

    ws.onclose = () => {
      updateConnectionState(false);
      appendLog({ event_type: "CLIENT_DISCONNECTED", payload: {} });
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };
  } catch (e) {
    alert(`Connection failed: ${e.message}`);
  }
});

btnDisconnect.addEventListener("click", () => {
  if (ws) ws.close();
});

btnSubmitTask.addEventListener("click", () => {
  const prompt = taskPromptInput.value.trim();
  if (!prompt) return;
  sendCommand("SUBMIT_TASK", { prompt });
});

btnCancelTask.addEventListener("click", () => {
  if (currentTaskId) {
    sendCommand("CANCEL_TASK", { task_id: currentTaskId });
  } else {
    sendCommand("CANCEL_TASK", { task_id: "active" });
  }
});

btnTriggerTakeover.addEventListener("click", () => {
  sendCommand("TRIGGER_TAKEOVER", { reason: "Operator clicked manual takeover" });
});

btnReleaseTakeover.addEventListener("click", () => {
  sendCommand("RELEASE_TAKEOVER", {});
});

btnClearLogs.addEventListener("click", () => {
  logTimeline.innerHTML = "";
});
