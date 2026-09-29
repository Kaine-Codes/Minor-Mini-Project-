import { useState } from 'react'
import { login } from '../api'

export default function Login({ onLoggedIn, theme, onToggleTheme }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    try {
      await login(username, password)
      onLoggedIn()
    } catch (err) {
      if (err.message === 'Failed to fetch') {
        setError('Network error — could not reach the server. Check your connection and try again.')
      } else {
        setError(err.message || 'Login failed')
      }
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-brand">
          <h1>ARIA</h1>
          <p className="subtitle">Adaptive Room Intelligence & Automation</p>
        </div>
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        {error && <p className="error">{error}</p>}
        <button type="submit">Log In</button>
        {onToggleTheme && (
          <button
            type="button"
            className="theme-toggle"
            onClick={onToggleTheme}
            style={{ alignSelf: 'center', marginTop: '4px' }}
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
        )}
      </form>
    </div>
  )
}
