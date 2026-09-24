export default function ETACard({eta}) {
  return (
    <div className="card">
      <h3>Dynamic ETA</h3>
      <div className="big">{eta ? `${eta.predicted_remaining_time_min} min` : "--"}</div>
      <p>Next station: {eta?.next_station || "--"}</p>
      <p>Delay: {eta?.current_delay_min ?? "--"} min</p>
      <p>Model: {eta?.model_source || "--"}</p>
      <p>Cause: {eta?.delay?.likely_cause || "--"}</p>
    </div>
  )
}
