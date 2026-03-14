let ws = null;
let sessionId = null;
let signalCount = 0;
let timerInterval = null;
let seconds = 0;
let messageHistory = [];
let historyOpen = false;
let micStream = null;
let mediaRecorder = null;
let sessionEnded = false;
let audioQueue = [];
let isPlaying = false;

let apiBase = "http://127.0.0.1:8080";

function normalizeBase(url) {
  return (url || "").trim().replace(/\/$/, "");
}

function getWsBase(httpBase) {
  return httpBase.replace(/^https:/, "wss:").replace(/^http:/, "ws:");
}

function startTimer() {
  seconds = 0;
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    seconds++;
    const m = String(Math.floor(seconds / 60)).padStart(2, "0");
    const s = String(seconds % 60).padStart(2, "0");
    document.getElementById("timer").textContent = m + ":" + s;
  }, 1000);
}

function toggleHistory() {
  historyOpen = !historyOpen;
  const panel = document.getElementById("history-panel");
  const btn = document.getElementById("history-toggle");
  panel.style.display = historyOpen ? "block" : "none";
  btn.textContent = (historyOpen ? "▲" : "▼") + " Signal history (" + messageHistory.length + ")";
}

function updateHistoryPanel() {
  const panel = document.getElementById("history-panel");
  panel.innerHTML = messageHistory.slice().reverse().map((d) => `
    <div class="history-item">
      <div class="history-dot dot-${(d.type || "").toLowerCase()}"></div>
      <div class="history-text">${d.message || ""}</div>
    </div>
  `).join("");
  const btn = document.getElementById("history-toggle");
  btn.textContent = (historyOpen ? "▲" : "▼") + " Signal history (" + messageHistory.length + ")";
}

function showCard(data) {
  document.getElementById("empty-state").style.display = "none";
  const card = document.getElementById("card");
  card.style.display = "block";
  const badge = document.getElementById("card-badge");
  const type = (data.type || "SIGNAL").toUpperCase();
  badge.textContent = type;
  badge.className = "badge badge-" + type.toLowerCase();
  document.getElementById("confidence-pill").textContent = (data.confidence || "HIGH").toString().toUpperCase();
  document.getElementById("card-message").textContent = data.message || "";
  document.getElementById("card-reasoning").textContent = data.reasoning || "";
}

function speakMessage(text) {
  audioQueue.push(text);
  if (!isPlaying) processQueue();
}

function processQueue() {
  if (audioQueue.length === 0) {
    isPlaying = false;
    document.getElementById("speaking-indicator").classList.remove("active");
    return;
  }
  isPlaying = true;
  const text = audioQueue.shift();
  document.getElementById("speaking-indicator").classList.add("active");
  fetch(`${apiBase}/tts`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text})
  }).then((r) => r.blob()).then((blob) => {
    const audio = new Audio(URL.createObjectURL(blob));
    audio.onended = processQueue;
    audio.onerror = processQueue;
    audio.play();
  }).catch(processQueue);
}

async function endSession() {
  sessionEnded = true;
  clearInterval(timerInterval);
  if (ws) ws.close();
  if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  mediaRecorder = null;
  micStream = null;

  const sid = sessionId || "unknown";
  document.getElementById("footer-status").textContent = "Generating debrief...";

  try {
    const res = await fetch(`${apiBase}/debrief`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: sid})
    });
    const data = await res.json();
    showCard({
      type: "DEBRIEF",
      message: data.debrief_text || "Session complete.",
      confidence: "",
      reasoning: ""
    });
    document.getElementById("footer-status").textContent = "Session saved.";
    speakMessage("Session complete. " + ((data.debrief_text || "").split(".")[0] || ""));
  } catch (e) {
    showCard({type: "DEBRIEF", message: "Session complete. Review your notes.", confidence: "", reasoning: ""});
    document.getElementById("footer-status").textContent = "Session complete.";
  }
}

function connectWebSocket() {
  const wsBase = getWsBase(apiBase);
  ws = new WebSocket(wsBase + "/stream");

  document.getElementById("reconnecting").style.display = "none";
  document.getElementById("status-text").textContent = "Listening";
  document.getElementById("status-dot").style.background = "#22C55E";

  ws.onopen = async function() {
    startTimer();
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(micStream);
      mediaRecorder.ondataavailable = function(e) {
        if (e.data && e.data.size > 0 && ws.readyState === WebSocket.OPEN) ws.send(e.data);
      };
      mediaRecorder.start(500);
    } catch (err) {
      document.getElementById("status-text").textContent = "Mic blocked";
      document.getElementById("status-dot").style.background = "#F87171";
      console.log("Mic error:", err);
    }
  };

  ws.onmessage = function(event) {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "SESSION_INIT") { sessionId = data.session_id; return; }
      if (data.type === "ERROR") { console.error(data.message); return; }
      if (data.type === "SILENT") return;
      if (["TACTIC", "SIGNAL", "RED_FLAG", "DEBRIEF"].includes(data.type)) {
        signalCount++;
        document.getElementById("signal-count-badge").textContent = signalCount + " signals";
        showCard(data);
        messageHistory.push(data);
        updateHistoryPanel();
        if (["TACTIC", "RED_FLAG"].includes(data.type) && data.message) speakMessage(data.message);
      }
    } catch (e) {
      console.error("Parse error:", e);
    }
  };

  ws.onclose = function() {
    clearInterval(timerInterval);
    if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
    if (micStream) micStream.getTracks().forEach((t) => t.stop());
    mediaRecorder = null;
    micStream = null;
    if (sessionEnded) return;
    document.getElementById("reconnecting").style.display = "flex";
    document.getElementById("status-text").textContent = "Disconnected";
    document.getElementById("status-dot").style.background = "#F87171";
    setTimeout(connectWebSocket, 3000);
  };
}

async function loadConfig() {
  const input = document.getElementById("api-base");
  const saved = await chrome.storage.sync.get(["dealroomApiBase"]);
  const value = normalizeBase(saved.dealroomApiBase || apiBase);
  apiBase = value || apiBase;
  input.value = apiBase;
}

async function saveConfig() {
  const input = document.getElementById("api-base");
  const value = normalizeBase(input.value);
  if (!value) return;

  apiBase = value;
  await chrome.storage.sync.set({ dealroomApiBase: value });

  sessionEnded = false;
  if (ws) ws.close();
  document.getElementById("footer-status").textContent = "Backend saved.";
  connectWebSocket();
}

document.getElementById("history-toggle").addEventListener("click", toggleHistory);
document.getElementById("end-btn").addEventListener("click", endSession);
document.getElementById("save-config").addEventListener("click", saveConfig);

loadConfig().then(connectWebSocket);
