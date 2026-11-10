import { useEffect, useState } from 'react'
import { Alert, Spinner } from 'react-bootstrap'

export default function EstadoSistema() {
  const [estado, setEstado] = useState({ cargando: true })

  useEffect(() => {
    fetch('/api/health/')
      .then(async (resp) => {
        const datos = await resp.json().catch(() => ({}))
        setEstado({ cargando: false, ok: resp.ok && datos.status === 'ok', datos })
      })
      .catch((err) => setEstado({ cargando: false, ok: false, datos: { detalle: err.message } }))
  }, [])

  if (estado.cargando) {
    return (
      <Alert variant="secondary">
        <Spinner animation="border" size="sm" className="me-2" />
        Verificando conexión con el backend…
      </Alert>
    )
  }

  if (estado.ok) {
    return (
      <Alert variant="success">
        <Alert.Heading>Backend + Oracle: ok</Alert.Heading>
        <p className="mb-0">Versión de base de datos: {estado.datos.version}</p>
      </Alert>
    )
  }

  return (
    <Alert variant="danger">
      <Alert.Heading>Backend + Oracle: error</Alert.Heading>
      <p className="mb-0">{estado.datos?.detalle || 'No se pudo conectar con el backend.'}</p>
    </Alert>
  )
}
