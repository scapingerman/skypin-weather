import { Component } from 'react'

/**
 * Atrapa errores en el subárbol y muestra un mensaje útil en vez de blanquear
 * la pantalla entera. Sin esto, un solo campo mal tipado en una zona
 * (p.ej. zona sobre agua con NDVI fuera de dominio) tumba toda la app.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught:', error, info?.componentStack)
  }

  reset = () => this.setState({ error: null })

  render() {
    if (this.state.error) {
      return (
        <div className="empty" style={{ margin: 16 }}>
          <strong>Algo se rompió al renderizar este panel</strong>
          <div style={{ fontSize: 12, color: '#a8b3c2', marginTop: 8 }}>
            {String(this.state.error?.message || this.state.error)}
          </div>
          <div style={{ fontSize: 11, color: '#6f7b8c', marginTop: 8 }}>
            Probá refrescar la página o eliminar la última zona que creaste
            (posiblemente está sobre agua o fuera de cobertura).
          </div>
          <button
            className="btn"
            style={{ marginTop: 10 }}
            onClick={this.reset}
          >
            Reintentar
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
