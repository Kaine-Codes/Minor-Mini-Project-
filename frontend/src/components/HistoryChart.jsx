import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js'
import { parseTimestamp } from '../utils/timeSync'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

export default function HistoryChart({ history }) {
  if (!history || history.length === 0) {
    return <div className="card">No history yet — check back once readings arrive.</div>
  }

  const labels = history.map((r) => {
    const ms = parseTimestamp(r.timestamp)
    return ms === null
      ? '?'
      : new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  })

  const data = {
    labels,
    datasets: [
      {
        label: 'Temperature (°C)',
        data: history.map((r) => r.temperature),
        borderColor: '#e74c3c',
        tension: 0.3,
      },
      {
        label: 'Humidity (%)',
        data: history.map((r) => r.humidity),
        borderColor: '#3498db',
        tension: 0.3,
      },
      {
        label: 'Gas (raw)',
        data: history.map((r) => r.gas_raw),
        borderColor: '#2ecc71',
        tension: 0.3,
        yAxisID: 'y1',
      },
    ],
  }

  const options = {
    responsive: true,
    interaction: { mode: 'index', intersect: false },
    scales: {
      y: { type: 'linear', position: 'left', title: { display: true, text: 'Temp / Humidity' } },
      y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Gas (raw)' } },
    },
  }

  return (
    <div className="card chart-card">
      <h2>History</h2>
      <Line data={data} options={options} />
    </div>
  )
}
