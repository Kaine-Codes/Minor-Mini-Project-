import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { parseTimestamp } from '../utils/timeSync'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler)

export default function HistoryChart({ history, theme, thresholds }) {
  if (!history || history.length === 0) {
    return <div className="card">No history yet — check back once readings arrive.</div>
  }

  const isDark = theme === 'dark'
  const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'
  const textColor = isDark ? '#9ca3af' : '#6b7280'
  const tooltipBg = isDark ? '#1e212a' : '#ffffff'
  const tooltipText = isDark ? '#f0f0f4' : '#111827'
  const tooltipBorder = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'

  const labels = history.map((r) => {
    const ms = parseTimestamp(r.timestamp)
    return ms === null
      ? '?'
      : new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  })

  const datasets = [
    {
      label: 'Temperature (°C)',
      data: history.map((r) => r.temperature),
      borderColor: '#f43f5e',
      backgroundColor: 'rgba(244, 63, 94, 0.08)',
      tension: 0.4,
      pointRadius: 0,
      pointHitRadius: 10,
      borderWidth: 2,
    },
    {
      label: 'Humidity (%)',
      data: history.map((r) => r.humidity),
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59, 130, 246, 0.08)',
      tension: 0.4,
      pointRadius: 0,
      pointHitRadius: 10,
      borderWidth: 2,
    },
    {
      label: 'Gas (raw)',
      data: history.map((r) => r.gas_raw),
      borderColor: '#14b8a6',
      backgroundColor: 'rgba(20, 184, 166, 0.08)',
      tension: 0.4,
      pointRadius: 0,
      pointHitRadius: 10,
      borderWidth: 2,
      yAxisID: 'y1',
    },
  ]

  // Add threshold reference lines
  if (thresholds?.temperature) {
    datasets.push({
      label: 'Temp Threshold',
      data: history.map(() => thresholds.temperature),
      borderColor: 'rgba(244, 63, 94, 0.35)',
      borderDash: [6, 4],
      borderWidth: 1,
      pointRadius: 0,
      pointHitRadius: 0,
      fill: false,
    })
  }

  if (thresholds?.gas) {
    datasets.push({
      label: 'Gas Threshold',
      data: history.map(() => thresholds.gas),
      borderColor: 'rgba(20, 184, 166, 0.35)',
      borderDash: [6, 4],
      borderWidth: 1,
      pointRadius: 0,
      pointHitRadius: 0,
      fill: false,
      yAxisID: 'y1',
    })
  }

  const data = { labels, datasets }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        labels: {
          color: textColor,
          font: { family: 'Inter', size: 12 },
          usePointStyle: true,
          pointStyle: 'circle',
          padding: 16,
          filter: (item) => !item.text.includes('Threshold'),
        },
      },
      tooltip: {
        backgroundColor: tooltipBg,
        titleColor: tooltipText,
        bodyColor: tooltipText,
        borderColor: tooltipBorder,
        borderWidth: 1,
        cornerRadius: 8,
        padding: 12,
        titleFont: { family: 'Inter', weight: '600' },
        bodyFont: { family: 'Inter' },
        filter: (item) => !item.dataset.label.includes('Threshold'),
      },
    },
    scales: {
      x: {
        ticks: { color: textColor, font: { family: 'Inter', size: 11 }, maxRotation: 0, autoSkipPadding: 20 },
        grid: { color: gridColor },
      },
      y: {
        type: 'linear',
        position: 'left',
        title: { display: true, text: 'Temp / Humidity', color: textColor, font: { family: 'Inter', size: 12 } },
        ticks: { color: textColor, font: { family: 'Inter', size: 11 } },
        grid: { color: gridColor },
      },
      y1: {
        type: 'linear',
        position: 'right',
        grid: { drawOnChartArea: false },
        title: { display: true, text: 'Gas (raw)', color: textColor, font: { family: 'Inter', size: 12 } },
        ticks: { color: textColor, font: { family: 'Inter', size: 11 } },
      },
    },
  }

  return (
    <div className="card chart-card">
      <h2>History</h2>
      <div className="chart-container">
        <Line data={data} options={options} />
      </div>
    </div>
  )
}
