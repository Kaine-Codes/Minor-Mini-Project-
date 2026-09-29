import { useState } from 'react'

export default function ThresholdSettings({ thresholds, onUpdate, reading }) {
  const [open, setOpen] = useState(false)

  function handleChange(key, value) {
    onUpdate({ ...thresholds, [key]: Number(value) })
  }

  const configs = [
    {
      key: 'temperature',
      name: '🌡️ Temperature',
      min: 15,
      max: 60,
      step: 1,
      unit: '°C',
      current: reading?.temperature?.toFixed(1),
    },
    {
      key: 'gas',
      name: '💨 Gas Level',
      min: 0,
      max: 4095,
      step: 50,
      unit: '',
      current: reading?.gas_raw,
    },
    {
      key: 'light',
      name: '☀️ Light Level',
      min: 0,
      max: 4095,
      step: 50,
      unit: '',
      current: reading?.light_raw,
    },
  ]

  return (
    <div className="card threshold-card">
      <button className="threshold-toggle-btn" onClick={() => setOpen(!open)}>
        Thresholds
        <span className={`threshold-chevron ${open ? 'open' : ''}`}>▼</span>
      </button>

      <div className={`threshold-body ${open ? 'open' : ''}`}>
        {configs.map(({ key, name, min, max, step, unit, current }) => (
          <div className="threshold-row" key={key}>
            <span className="threshold-name">{name}</span>
            <input
              type="range"
              className="threshold-slider"
              min={min}
              max={max}
              step={step}
              value={thresholds[key]}
              onChange={(e) => handleChange(key, e.target.value)}
            />
            <span className="threshold-values">
              <span className="current-val">{current ?? '—'}{unit}</span>
              {' / '}
              <span className="thresh-val">{thresholds[key]}{unit}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
