import { MapContainer, TileLayer, Marker, Popup, Polyline } from "react-leaflet";
import L from "leaflet";

const trainIcon = L.divIcon({
  className: "train-icon",
  html: "🚆",
  iconSize: [30, 30],
  iconAnchor: [15, 15]
});

export default function TrainMap({telemetry, route}) {
  const position = telemetry ? [telemetry.latitude, telemetry.longitude] : [22.5726, 88.3639];
  const coords = route?.features?.find(f => f.geometry?.type === "LineString")
    ?.geometry?.coordinates?.map(([lng,lat]) => [lat,lng]) || [];

  return (
    <MapContainer center={position} zoom={11} className="map">
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {coords.length > 0 && <Polyline positions={coords} />}
      <Marker position={position} icon={trainIcon}>
        <Popup>
          Train {telemetry?.train_no || "12301"}<br/>
          Speed: {telemetry?.speed_kmph ?? "--"} km/h
        </Popup>
      </Marker>
    </MapContainer>
  )
}
