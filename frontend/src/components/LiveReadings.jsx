export default function LiveReadings({ reading, thresholds }) {
  if (!reading || Object.keys(reading).length === 0) {
    return <div className="card">Waiting for sensor data...</div>
  }

  const gasAlert = reading.local_gas_override === 1
  const t = thresholds || {}

  const tempExceeded = t.temperature && reading.temperature > t.temperature
  const gasExceeded = t.gas && reading.gas_raw > t.gas
  const lightExceeded = t.light && reading.light_raw > t.light

  return (
    <div className="readings-grid">
      <div className={`sensor-card temp ${tempExceeded ? 'threshold-exceeded' : ''}`}>
        <div className="sensor-header">
          <span className="sensor-icon">🌡️</span>
          <span className="label">Temperature</span>
        </div>
        <span className="value">{reading.temperature?.toFixed(1)}°C</span>
        {tempExceeded && <span className="threshold-indicator">⚠ Above {t.temperature}°C</span>}
      </div>

      <div className="sensor-card humidity">
        <div className="sensor-header">
          <span className="sensor-icon">💧</span>
          <span className="label">Humidity</span>
        </div>
        <span className="value">{reading.humidity?.toFixed(1)}%</span>
      </div>

      <div className={`sensor-card gas ${gasAlert ? 'alert' : gasExceeded ? 'threshold-exceeded' : ''}`}>
        <div className="sensor-header">
          <span className="sensor-icon">💨</span>
          <span className="label">Gas Level</span>
        </div>
        <span className="value">{reading.gas_raw}</span>
        {gasAlert && <span className="badge">SAFETY OVERRIDE</span>}
        {!gasAlert && gasExceeded && <span className="threshold-indicator">⚠ Above {t.gas}</span>}
      </div>

      <div className={`sensor-card light ${lightExceeded ? 'threshold-exceeded' : ''}`}>
        <div className="sensor-header">
          <span className="sensor-icon">☀️</span>
          <span className="label">Light Level</span>
        </div>
        <span className="value">{reading.light_raw}</span>
        {lightExceeded && <span className="threshold-indicator">⚠ Above {t.light}</span>}
      </div>

      <div className="sensor-card motion">
        <div className="sensor-header">
          <span className="sensor-icon">🚶</span>
          <span className="label">Motion</span>
        </div>
        <span className="value">{reading.motion ? 'Detected' : 'None'}</span>
      </div>

      <div className="sensor-card vibration">
        <div className="sensor-header">
          <span className="sensor-icon">📳</span>
          <span className="label">Vibration</span>
        </div>
        <span className="value">{reading.vibration ? 'Detected' : 'None'}</span>
      </div>
    </div>
  )
}
