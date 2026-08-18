export default function Controls({ led, fan, onToggleLed, onToggleFan, sending, gasOverrideActive }) {
  return (
    <div className="card controls-card">
      <h2>Controls</h2>
      <p className="hint">
        Manual overrides. During a gas safety event, the fan is controlled locally by
        the ESP32 and will not respond to remote commands.
      </p>
      <div className="controls-row">
        <button className={led ? 'toggle on' : 'toggle'} onClick={onToggleLed} disabled={sending}>
          Light: {led ? 'ON' : 'OFF'}
        </button>
        <button
          className={fan ? 'toggle on' : 'toggle'}
          onClick={onToggleFan}
          disabled={sending || gasOverrideActive}
          title={gasOverrideActive ? 'Locked on by the local gas safety override' : undefined}
        >
          Fan: {fan ? 'ON' : 'OFF'}{gasOverrideActive ? ' (locked)' : ''}
        </button>
      </div>
    </div>
  )
}
