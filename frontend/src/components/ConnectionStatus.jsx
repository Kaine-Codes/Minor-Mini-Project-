import { correctedNowMs, parseTimestamp } from '../utils/timeSync'

// Firmware posts a reading every 5s (POST_INTERVAL_MS in the .ino).
// Give it a couple of missed cycles of slack before calling it disconnected,
// so one dropped WiFi packet doesn't flash a false alarm.
const STALE_AFTER_MS = 15000

export default function ConnectionStatus({ reading }) {
  const lastSeenMs = parseTimestamp(reading?.timestamp)
  const connected = lastSeenMs !== null && correctedNowMs() - lastSeenMs < STALE_AFTER_MS

  return (
    <div className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
      <span className="status-dot" />
      {connected ? 'ESP32 connected' : 'ESP32 not responding'}
    </div>
  )
}
