import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Container, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'

const formatoFecha = (iso) => {
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

const formatoFechaHora = new Intl.DateTimeFormat('es-SV', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'America/El_Salvador',
})

export default function Periodos() {
  const { usuario } = useAuth()
  const esContador = tieneRol(usuario, ROLES.CONTADOR)
  const esAdmin = usuario.es_admin

  const [ejercicios, setEjercicios] = useState(null)
  const [anio, setAnio] = useState(null)
  const [periodos, setPeriodos] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [trabajando, setTrabajando] = useState(false)

  const [nuevoAnio, setNuevoAnio] = useState(null) // modal "crear ejercicio"
  const [porCerrar, setPorCerrar] = useState(null)
  const [porReabrir, setPorReabrir] = useState(null)
  const [motivo, setMotivo] = useState('')
  const [errorModal, setErrorModal] = useState('')

  const cargarEjercicios = useCallback(async (seleccionar) => {
    const resp = await api('/api/periodos/ejercicios/')
    if (!resp.ok) return setError(await mensajeError(resp))
    const datos = await resp.json()
    setEjercicios(datos)
    setAnio((actual) => {
      if (seleccionar) return seleccionar
      if (actual && datos.some((e) => e.anio === actual)) return actual
      const hoy = new Date().getFullYear()
      return datos.find((e) => e.anio === hoy)?.anio ?? datos[0]?.anio ?? null
    })
  }, [])

  const cargarPeriodos = useCallback(async () => {
    if (!anio) return setPeriodos([])
    const resp = await api(`/api/periodos/?anio=${anio}`)
    if (!resp.ok) return setError(await mensajeError(resp))
    setPeriodos(await resp.json())
  }, [anio])

  useEffect(() => {
    cargarEjercicios()
  }, [cargarEjercicios])

  useEffect(() => {
    cargarPeriodos()
  }, [cargarPeriodos])

  const recargar = async (seleccionar) => {
    await cargarEjercicios(seleccionar)
    // Si cambia el ejercicio seleccionado, el efecto de `anio` recarga los periodos.
    if (!seleccionar || seleccionar === anio) await cargarPeriodos()
  }

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const cerrarModales = () => {
    setNuevoAnio(null)
    setPorCerrar(null)
    setPorReabrir(null)
    setMotivo('')
    setErrorModal('')
  }

  const ejecutar = async (url, cuerpo, mensajeExito, seleccionar) => {
    setTrabajando(true)
    setErrorModal('')
    const resp = await api(url, { method: 'POST', body: cuerpo })
    setTrabajando(false)
    if (!resp.ok) return setErrorModal(await mensajeError(resp))
    cerrarModales()
    notificar(mensajeExito)
    recargar(seleccionar)
  }

  const crearEjercicio = (e) => {
    e.preventDefault()
    const valor = Number(nuevoAnio)
    ejecutar('/api/periodos/ejercicios/', { anio: valor }, `Ejercicio ${valor} creado con 12 periodos abiertos.`, valor)
  }

  // Primer periodo abierto del año mostrado (el único que se puede cerrar si el año anterior está cerrado).
  const primerAbierto = periodos?.find((p) => p.estado === 'ABIERTO')
  const ultimoCerrado = periodos ? [...periodos].reverse().find((p) => p.estado === 'CERRADO') : null
  const resumen = ejercicios?.find((e) => e.anio === anio)

  return (
    <Container fluid className="px-0">
      <EncabezadoPagina
        titulo="Periodos contables"
        descripcion="Apertura y cierre mensual del ejercicio. Los periodos se cierran en orden."
        migas={[{ texto: 'Configuración' }, { texto: 'Periodos contables' }]}
      >
        {esContador && (
          <Button
            onClick={() => {
              const maximo = ejercicios?.length ? Math.max(...ejercicios.map((e) => e.anio)) + 1 : new Date().getFullYear()
              setNuevoAnio(String(maximo))
            }}
          >
            <i className="bi bi-calendar-plus me-1" /> Crear ejercicio
          </Button>
        )}
      </EncabezadoPagina>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      {aviso && (
        <Alert variant="success" dismissible onClose={() => setAviso('')}>
          {aviso}
        </Alert>
      )}

      {!ejercicios ? (
        <Spinner animation="border" />
      ) : ejercicios.length === 0 ? (
        <Alert variant="info">
          No hay ejercicios creados.{' '}
          {esContador ? 'Use "Crear ejercicio" para generar los 12 periodos del año.' : 'El contador debe crear el primero.'}
        </Alert>
      ) : (
        <>
          <Row className="g-2 mb-3 align-items-end">
            <Col xs={12} sm={6} md={3}>
              <Form.Label htmlFor="ejercicio">Ejercicio</Form.Label>
              <Form.Select id="ejercicio" value={anio ?? ''} onChange={(e) => setAnio(Number(e.target.value))}>
                {ejercicios.map((e) => (
                  <option key={e.anio} value={e.anio}>
                    {e.anio}
                  </option>
                ))}
              </Form.Select>
            </Col>
            {resumen && (
              <Col xs={12} sm={6} md={9} className="text-muted small pb-2">
                {resumen.abiertos} abierto(s) · {resumen.cerrados} cerrado(s). Los periodos se cierran en orden; solo el
                administrador puede reabrir el último periodo cerrado.
              </Col>
            )}
          </Row>

          {!periodos ? (
            <Spinner animation="border" />
          ) : (
            <Card className="mb-4">
            <div className="table-responsive">
              <Table hover className="align-middle">
                <thead>
                  <tr>
                    <th>Periodo</th>
                    <th>Desde</th>
                    <th>Hasta</th>
                    <th>Estado</th>
                    <th>Último cierre</th>
                    {(esContador || esAdmin) && <th className="text-end">Acciones</th>}
                  </tr>
                </thead>
                <tbody>
                  {periodos.map((p) => (
                    <tr key={p.id}>
                      <td>{p.nombre}</td>
                      <td>{formatoFecha(p.fecha_inicio)}</td>
                      <td>{formatoFecha(p.fecha_fin)}</td>
                      <td>
                        {p.estado === 'ABIERTO' ? (
                          <Badge bg="success-subtle" text="success-emphasis">
                            <i className="bi bi-unlock me-1" />
                            Abierto
                          </Badge>
                        ) : (
                          <Badge bg="secondary-subtle" text="secondary-emphasis">
                            <i className="bi bi-lock me-1" />
                            Cerrado
                          </Badge>
                        )}
                      </td>
                      <td className="small">
                        {p.cerrado_en ? `${p.cerrado_por} · ${formatoFechaHora.format(new Date(p.cerrado_en))}` : '—'}
                      </td>
                      {(esContador || esAdmin) && (
                        <td className="text-end text-nowrap">
                          {esContador && p.estado === 'ABIERTO' && (
                            <Button
                              size="sm"
                              variant={p.id === primerAbierto?.id ? 'outline-primary' : 'outline-secondary'}
                              onClick={() => setPorCerrar(p)}
                              title={p.id === primerAbierto?.id ? '' : 'Los periodos anteriores deben estar cerrados'}
                            >
                              Cerrar
                            </Button>
                          )}
                          {esAdmin && p.estado === 'CERRADO' && p.id === ultimoCerrado?.id && (
                            <Button size="sm" variant="outline-warning" className="ms-1" onClick={() => setPorReabrir(p)}>
                              Reabrir
                            </Button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
            </Card>
          )}
        </>
      )}

      {/* Crear ejercicio */}
      <Modal show={nuevoAnio !== null} onHide={cerrarModales} centered>
        <Form onSubmit={crearEjercicio}>
          <Modal.Header closeButton>
            <Modal.Title as="h2" className="h5">
              Crear ejercicio
            </Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {errorModal && <Alert variant="danger">{errorModal}</Alert>}
            <Form.Group controlId="nuevo-anio">
              <Form.Label>Año</Form.Label>
              <Form.Control
                type="number"
                min={2000}
                max={2100}
                value={nuevoAnio ?? ''}
                onChange={(e) => setNuevoAnio(e.target.value)}
                required
                autoFocus
              />
              <Form.Text>Se crearán los 12 periodos mensuales del año, todos abiertos.</Form.Text>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={cerrarModales}>
              Cancelar
            </Button>
            <Button type="submit" disabled={trabajando || !nuevoAnio}>
              {trabajando && <Spinner animation="border" size="sm" className="me-2" />}
              Crear
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Cerrar periodo */}
      <Modal show={Boolean(porCerrar)} onHide={cerrarModales} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Cerrar {porCerrar?.nombre}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {errorModal && <Alert variant="danger">{errorModal}</Alert>}
          Una vez cerrado no se podrá registrar con fechas de este periodo. Solo el administrador puede reabrirlo.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={cerrarModales}>
            Cancelar
          </Button>
          <Button
            disabled={trabajando}
            onClick={() => ejecutar(`/api/periodos/${porCerrar.id}/cerrar/`, undefined, `Periodo ${porCerrar.nombre} cerrado.`)}
          >
            {trabajando && <Spinner animation="border" size="sm" className="me-2" />}
            Cerrar periodo
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Reabrir periodo */}
      <Modal show={Boolean(porReabrir)} onHide={cerrarModales} centered>
        <Form
          onSubmit={(e) => {
            e.preventDefault()
            ejecutar(`/api/periodos/${porReabrir.id}/reabrir/`, { motivo }, `Periodo ${porReabrir.nombre} reabierto.`)
          }}
        >
          <Modal.Header closeButton>
            <Modal.Title as="h2" className="h5">
              Reabrir {porReabrir?.nombre}
            </Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {errorModal && <Alert variant="danger">{errorModal}</Alert>}
            <Form.Group controlId="motivo">
              <Form.Label>Motivo de la reapertura</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                maxLength={400}
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                required
                autoFocus
              />
              <Form.Text>Queda registrado en la bitácora de auditoría.</Form.Text>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={cerrarModales}>
              Cancelar
            </Button>
            <Button type="submit" variant="warning" disabled={trabajando || !motivo.trim()}>
              {trabajando && <Spinner animation="border" size="sm" className="me-2" />}
              Reabrir
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>
    </Container>
  )
}
