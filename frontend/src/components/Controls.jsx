export default function Controls({ led, fan, onToggleLed, onToggleFan, sending, gasOverrideActive }) {
  return (
    <div className="card controls-card">
      <h2>Controls</h2>
      <p className="hint">
        Manual overrides. During a gas safety event, the fan is controlled locally by
        the ESP32 and will not respond to remote commands.
      </p>
      <div className="controls-row">
        <div
          className={`toggle-switch ${sending ? 'disabled' : ''}`}
          onClick={!sending ? onToggleLed : undefined}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && !sending && onToggleLed()}
        >
          <div className={`toggle-track ${led ? 'on' : ''}`}>
            <div className="toggle-knob" />
          </div>
          <span className="toggle-label">
            💡 Light
            <small>{led ? 'ON' : 'OFF'}</small>
          </span>
        </div>

        <div
          className={`toggle-switch ${sending || gasOverrideActive ? 'disabled' : ''}`}
          onClick={!(sending || gasOverrideActive) ? onToggleFan : undefined}
          role="button"
          tabIndex={0}
          title={gasOverrideActive ? 'Locked on by the local gas safety override' : undefined}
          onKeyDown={(e) => e.key === 'Enter' && !(sending || gasOverrideActive) && onToggleFan()}
        >
          <div className={`toggle-track ${fan ? 'on' : ''}`}>
            <div className="toggle-knob" />
          </div>
          <span className="toggle-label">
            🌀 Fan
            <small>{fan ? 'ON' : 'OFF'}{gasOverrideActive ? ' (locked)' : ''}</small>
          </span>
        </div>
      </div>
    </div>
  )
}
