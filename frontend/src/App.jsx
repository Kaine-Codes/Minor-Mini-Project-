import { useEffect, useState } from 'react'
import Login from './components/Login'
import LiveReadings from './components/LiveReadings'
import HistoryChart from './components/HistoryChart'
import Controls from './components/Controls'
import FloorPlan from './components/FloorPlan'
import ConnectionStatus from './components/ConnectionStatus'
import GasDangerBanner from './components/GasDangerBanner'
import { getStatus, getLatest, getHistory, getCommands, sendCommand, logout } from './api'
import { syncClock } from './utils/timeSync'

const POLL_MS = 4000

export default function App() {
  const [loggedIn, setLoggedIn] = useState(null) // null = checking
  const [reading, setReading] = useState(null)
  const [history, setHistory] = useState([])
  const [led, setLed] = useState(false)
  const [fan, setFan] = useState(false)
  const [sending, setSending] = useState(false)

  // One-time internet time check, used only to correct the ESP32
  // connected/disconnected freshness check -- see utils/timeSync.js
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
      // Each call re-fetches the current sliding window from the backend
      // (last 200 rows, most recent first) -- there's no separate
      // "trim the oldest point" step needed on the frontend, the backend
      // query already only ever returns the newest N readings.
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

  if (loggedIn === null) {
    return <div className="loading-screen">Loading...</div>
  }

  if (!loggedIn) {
    return <Login onLoggedIn={() => setLoggedIn(true)} />
  }

  const gasOverrideActive = reading?.local_gas_override === 1
  // While the override is active the ESP32 forces the fan on locally,
  // ignoring dashboard commands -- reflect that in the UI regardless of
  // what was last commanded.
  const fanDisplayState = fan || gasOverrideActive

  return (
    <div className="dashboard">
      <header>
        <h1>ARIA Dashboard</h1>
        <div className="header-right">
          <ConnectionStatus reading={reading} />
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
          <LiveReadings reading={reading} />
          <Controls
            led={led}
            fan={fanDisplayState}
            onToggleLed={toggleLed}
            onToggleFan={toggleFan}
            sending={sending}
            gasOverrideActive={gasOverrideActive}
          />
        </div>
      </div>

      <HistoryChart history={history} />
    </div>
  )
}
