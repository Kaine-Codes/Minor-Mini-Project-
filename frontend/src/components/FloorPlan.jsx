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
        <rect x="10" y="10" width="300" height="220" rx="6" className="room-wall" />
        {/* doorway gap */}
        <rect x="145" y="228" width="30" height="6" className="room-door" />

        {/* bulb, top-left corner */}
        <g className={`bulb ${led ? 'on' : ''}`} transform="translate(44, 40)">
          <circle r="18" className="bulb-glow" />
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

        {/* Person silhouette — shown when PIR/IR sensor sees motion */}
        {motion && (
          <g transform="translate(160, 140)">
            {/* Pulsing motion ring */}
            <circle cx="0" cy="0" r="25" className="motion-ring" />
            <circle cx="0" cy="0" r="25" className="motion-ring" style={{ animationDelay: '0.7s' }} />

            {/* Person silhouette path */}
            <g className="person-silhouette" transform="translate(-12, -28)">
              {/* Head */}
              <circle cx="12" cy="6" r="6" />
              {/* Body */}
              <path d="M12,12 C6,14 3,20 4,30 L8,30 L10,22 L12,28 L14,22 L16,30 L20,30 C21,20 18,14 12,12Z" />
              {/* Arms */}
              <path d="M4,18 C2,16 0,18 1,20 L6,24" />
              <path d="M20,18 C22,16 24,18 23,20 L18,24" />
            </g>
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
