// MQ-135/LDR are read via the ESP32's 12-bit ADC (0-4095 raw range).
const ADC_MAX = 4095

export default function FloorPlan({ reading, led, fan }) {
  const light = reading?.light_raw ?? 0
  const humidity = reading?.humidity ?? 0
  const vibration = !!reading?.vibration
  const motion = !!reading?.motion

  const lightPct = Math.min(100, Math.max(0, (light / ADC_MAX) * 100))
  const humidityPct = Math.min(100, Math.max(0, humidity))

  return (
    <div className="floorplan-card card">
      <h2>Room</h2>

      <svg
        viewBox="0 0 320 260"
        className="floorplan-svg"
        role="img"
        aria-label={`Room view. Light ${led ? 'on' : 'off'}, fan ${fan ? 'on' : 'off'}, ${motion ? 'motion detected' : 'no motion'}.`}
      >
        {/* room outline */}
        <rect x="10" y="10" width="300" height="220" rx="4" className="room-wall" />
        <rect x="150" y="230" width="20" height="0" />
        {/* doorway gap */}
        <rect x="145" y="228" width="30" height="6" className="room-door" />

        {/* bulb, top-left corner */}
        <g className={`bulb ${led ? 'on' : ''}`} transform="translate(44, 40)">
          <circle r="16" className="bulb-glow" />
          <circle r="10" className="bulb-body" />
          <line x1="-5" y1="9" x2="5" y2="9" className="bulb-base" />
        </g>

        {/* fan, on the opposite wall */}
        <g className={`fan ${fan ? 'spinning' : ''}`} transform="translate(276, 40)">
          <g className="fan-blades">
            <ellipse cx="0" cy="-10" rx="4" ry="10" />
            <ellipse cx="0" cy="10" rx="4" ry="10" />
            <ellipse cx="-10" cy="0" rx="10" ry="4" />
            <ellipse cx="10" cy="0" rx="10" ry="4" />
          </g>
          <circle r="4" className="fan-hub" />
        </g>

        {/* stick figure -- only rendered while the PIR/IR sensor sees motion */}
        {motion && (
          <g className="stick-figure" transform="translate(160, 150)">
            <circle cx="0" cy="-24" r="8" />
            <line x1="0" y1="-16" x2="0" y2="16" />
            <line x1="0" y1="-6" x2="-15" y2="4" />
            <line x1="0" y1="-6" x2="15" y2="4" />
            <line x1="0" y1="16" x2="-11" y2="34" />
            <line x1="0" y1="16" x2="11" y2="34" />
          </g>
        )}

        {/* vibration indicator */}
        <g transform="translate(50, 195)">
          <circle r="7" className={`vibration-dot ${vibration ? 'active' : ''}`} />
          <text x="16" y="4" className="floorplan-label">Vibration</text>
        </g>
      </svg>

      <div className="floorplan-bars">
        <div className="bar-row">
          <span className="bar-label">Light</span>
          <div className="bar-track">
            <div className="bar-fill light" style={{ width: `${lightPct}%` }} />
          </div>
        </div>
        <div className="bar-row">
          <span className="bar-label">Humidity</span>
          <div className="bar-track">
            <div className="bar-fill humidity" style={{ width: `${humidityPct}%` }} />
          </div>
        </div>
      </div>
    </div>
  )
}
