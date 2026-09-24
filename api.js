const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function startTrain(trainNo) {
  const res = await fetch(`${API}/api/train/start`, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({train_no: trainNo})
  });
  if (!res.ok) throw new Error("Unable to start train");
  return res.json();
}

export async function getEta(trainNo) {
  const res = await fetch(`${API}/api/train/${trainNo}/eta`);
  if (!res.ok) throw new Error("Unable to fetch ETA");
  return res.json();
}

export async function getRoute(trainNo) {
  const res = await fetch(`${API}/api/train/${trainNo}/route`);
  if (!res.ok) throw new Error("Unable to fetch route");
  return res.json();
}

export async function getSchedule(trainNo) {
  const res = await fetch(`${API}/api/train/${trainNo}/schedule`);
  if (!res.ok) throw new Error("Unable to fetch schedule");
  return res.json();
}

export function telemetrySocket(trainNo) {
  const url = API.replace("http://", "ws://").replace("https://", "wss://");
  return new WebSocket(`${url}/ws/telemetry/${trainNo}`);
}
