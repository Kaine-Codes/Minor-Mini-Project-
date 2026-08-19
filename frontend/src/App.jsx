import { useEffect, useState, useCallback } from 'react'
import Login from './components/Login'
import LiveReadings from './components/LiveReadings'
import HistoryChart from './components/HistoryChart'
import Controls from './components/Controls'
import FloorPlan from './components/FloorPlan'
import ConnectionStatus from './components/ConnectionStatus'
import GasDangerBanner from './components/GasDangerBanner'
import ThresholdSettings from './components/ThresholdSettings'
import { getStatus, getLatest, getHistory, getCommands, sendCommand, logout } from './api'
import { syncClock } from './utils/timeSync'

const POLL_MS = 4000

const DEFAULT_THRESHOLDS = {
  temperature: 40,
  gas: 1800,
  light: 3000,
  vibration: 1,  // 1 = any vibration triggers alert
}

function loadThresholds() {
  try {
    const saved = localStorage.getItem('aria-thresholds')
    return saved ? { ...DEFAULT_THRESHOLDS, ...JSON.parse(saved) } : DEFAULT_THRESHOLDS
  } catch {
    return DEFAULT_THRESHOLDS
  }
}

function loadTheme() {
  try {
    return localStorage.getItem('aria-theme') || 'dark'
  } catch {
    return 'dark'
  }
}

export default function App() {
  const [loggedIn, setLoggedIn] = useState(null) // null = checking
  const [reading, setReading] = useState(null)
  const [history, setHistory] = useState([])
  const [led, setLed] = useState(false)
  const [fan, setFan] = useState(false)
  const [sending, setSending] = useState(false)
  const [theme, setTheme] = useState(loadTheme)
  const [thresholds, setThresholds] = useState(loadThresholds)

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('aria-theme', theme)
  }, [theme])

  // Save thresholds
  const updateThresholds = useCallback((newThresholds) => {
    setThresholds(newThresholds)
    localStorage.setItem('aria-thresholds', JSON.stringify(newThresholds))
  }, [])

  // One-time internet time check
  useEffect(() => {
    syncClock()
  }, [])

  useEffect(() => {
    getStatus()
      .then((s) => setLoggedIn(s.logged_in))
      .catch(() => setLoggedIn(false))
  }, [])

  useEffect(() => {
    if (!loggedIn) return

    const fetchData = () => {
      getLatest().then(setReading).catch(() => {})
      getHistory(200).then(setHistory).catch(() => {})
      getCommands()
        .then((c) => {
          setLed(!!c.led)
          setFan(!!c.fan)
        })
        .catch(() => {})
    }

    fetchData()
    const interval = setInterval(fetchData, POLL_MS)
    return () => clearInterval(interval)
  }, [loggedIn])

  async function toggleLed() {
    const next = !led
    setLed(next)
    setSending(true)
    try {
      await sendCommand(next, undefined)
    } finally {
      setSending(false)
    }
  }

  async function toggleFan() {
    const next = !fan
    setFan(next)
    setSending(true)
    try {
      await sendCommand(undefined, next)
    } finally {
      setSending(false)
    }
  }

  function toggleTheme() {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }

  if (loggedIn === null) {
    return <div className="loading-screen">Loading...</div>
  }

  if (!loggedIn) {
    return <Login onLoggedIn={() => setLoggedIn(true)} theme={theme} onToggleTheme={toggleTheme} />
  }

  const gasOverrideActive = reading?.local_gas_override === 1
  const fanDisplayState = fan || gasOverrideActive

  return (
    <div className="dashboard">
      <header>
        <h1>ARIA Dashboard</h1>
        <div className="header-right">
          <ConnectionStatus reading={reading} />
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <button
            className="logout-btn"
            onClick={() => logout().then(() => setLoggedIn(false))}
          >
            Log Out
          </button>
        </div>
      </header>

      <GasDangerBanner active={gasOverrideActive} />

      <div className="main-grid">
        <FloorPlan reading={reading} led={led} fan={fanDisplayState} />
        <div className="side-panel">
          <LiveReadings reading={reading} thresholds={thresholds} />
          <Controls
            led={led}
            fan={fanDisplayState}
            onToggleLed={toggleLed}
            onToggleFan={toggleFan}
            sending={sending}
            gasOverrideActive={gasOverrideActive}
          />
          <ThresholdSettings
            thresholds={thresholds}
            onUpdate={updateThresholds}
            reading={reading}
          />
        </div>
      </div>

      <HistoryChart history={history} theme={theme} thresholds={thresholds} />
    </div>
  )
}
