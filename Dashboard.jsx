import { useEffect, useState } from "react";
import TrainMap from "../components/TrainMap";
import ETACard from "../components/ETACard";
import StatusBadge from "../components/StatusBadge";
import { startTrain, getEta, getRoute, getSchedule, telemetrySocket } from "../services/api";

export default function Dashboard() {
  const [trainNo, setTrainNo] = useState("12301");
  const [telemetry, setTelemetry] = useState(null);
  const [eta, setEta] = useState(null);
  const [route, setRoute] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [status, setStatus] = useState("Disconnected");
  const [error, setError] = useState("");

  async function connect() {
    setError("");
    try {
      await startTrain(trainNo);
      const [etaData, routeData, scheduleData] = await Promise.all([
        getEta(trainNo), getRoute(trainNo), getSchedule(trainNo)
      ]);
      setEta(etaData);
      setRoute(routeData);
      setSchedule(scheduleData);

      const ws = telemetrySocket(trainNo);
      ws.onopen = () => setStatus("Live");
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setTelemetry(data);
        setEta(prev => ({
          ...(prev || {}),
          train_no: trainNo,
          next_station: data.next_station || prev?.next_station || "Howrah Jn",
          predicted_remaining_time_min: data.predicted_remaining_time_min,
          current_delay_min: data.current_delay_min,
          model_source: data.model_source
        }));
      };
      ws.onerror = () => setStatus("Polling");
      ws.onclose = () => setStatus("Disconnected");
      return () => ws.close();
    } catch (e) {
      setError(e.message);
      setStatus("Disconnected");
    }
  }

  useEffect(() => {
    let cleanup;
    connect().then(fn => cleanup = fn);
    return () => cleanup?.();
  }, []);

  return (
    <main className="shell">
      <header>
        <div>
          <p className="eyebrow">SIH 2026 · SMART AUTOMATION</p>
          <h1>YatraSuchak</h1>
          <p className="subtitle">Dynamic ETA intelligence for coaching trains</p>
        </div>
        <StatusBadge status={status} />
      </header>

      <section className="toolbar">
        <input value={trainNo} onChange={e => setTrainNo(e.target.value)} />
        <button onClick={connect}>Track train</button>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="grid">
        <ETACard eta={eta} />

        <div className="card">
          <h3>Live telemetry</h3>
          <div className="metric"><span>Speed</span><strong>{telemetry?.speed_kmph ?? "--"} km/h</strong></div>
          <div className="metric"><span>Distance</span><strong>{telemetry?.distance_to_station_km ?? "--"} km</strong></div>
          <div className="metric"><span>Congestion</span><strong>{telemetry?.congestion_index ?? "--"}</strong></div>
          <div className="metric"><span>Signal delay</span><strong>{telemetry?.signal_delay_min ?? "--"} min</strong></div>
        </div>

        <div className="card schedule">
          <h3>Upcoming stations</h3>
          {schedule?.stations?.map(s => (
            <div className="station" key={s.station}>
              <span>{s.station}</span>
              <span>{s.predicted}</span>
              <small>+{s.delay_min} min</small>
            </div>
          ))}
        </div>
      </section>

      <section className="map-card">
        <TrainMap telemetry={telemetry} route={route} />
      </section>
    </main>
  )
}
