export default function LiveReadings({ reading }) {
  if (!reading || Object.keys(reading).length === 0) {
    return <div className="card">Waiting for sensor data...</div>
  }

  const gasAlert = reading.local_gas_override === 1

  return (
    <div className="readings-grid">
      <div className="card">
        <span className="label">Temperature</span>
        <span className="value">{reading.temperature?.toFixed(1)} °C</span>
      </div>
      <div className="card">
        <span className="label">Humidity</span>
        <span className="value">{reading.humidity?.toFixed(1)} %</span>
      </div>
      <div className={`card ${gasAlert ? 'alert' : ''}`}>
        <span className="label">Gas Level (raw)</span>
        <span className="value">{reading.gas_raw}</span>
        {gasAlert && <span className="badge">SAFETY OVERRIDE ACTIVE</span>}
      </div>
      <div className="card">
        <span className="label">Light Level (raw)</span>
        <span className="value">{reading.light_raw}</span>
      </div>
      <div className="card">
        <span className="label">Motion</span>
        <span className="value">{reading.motion ? 'Detected' : 'None'}</span>
      </div>
      <div className="card">
        <span className="label">Vibration</span>
        <span className="value">{reading.vibration ? 'Detected' : 'None'}</span>
      </div>
    </div>
  )
}
