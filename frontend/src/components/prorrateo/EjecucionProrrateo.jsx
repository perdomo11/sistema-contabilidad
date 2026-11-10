import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { Link } from 'react-router-dom'
import { api, mensajeError } from '../../api'
import { formatoFecha, formatoFechaHora, formatoMonto } from '../../formato'
import EstadoVacio from '../EstadoVacio'
import SelectorPeriodo from '../SelectorPeriodo'

const ESTADO = {
  PENDIENTE: ['warning', 'Pendiente'],
  EJECUTADA: ['success', 'Ejecutada'],
  ANULADA: ['secondary', 'Anulada'],
}

const pct = (v) => `${Number(v).toLocaleString('es-SV', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %`

/** Ventana con la vista previa (o el detalle guardado) de una distribución. */
function DetalleDistribucion({ datos, titulo, onHide, accion }) {
  return (
    <Modal show={Boolean(datos)} onHide={onHide} size="xl" centered scrollable>
      <Modal.Header closeButton>
        <Modal.Title as="h2" className="h5">
          {titulo}
        </Modal.Title>
      </Modal.Header>
      {datos && (
        <Modal.Body>
          <Row className="g-3 mb-3">
            <Col md={4}>
              <div className="small text-suave">Centro origen</div>
              <div>
                <code className="me-1">{datos.centro_origen.codigo}</code>
                {datos.centro_origen.nombre}
              </div>
            </Col>
            <Col md={4}>
              <div className="small text-suave">Base</div>
              <div>
                {datos.base.nombre} · total {Number(datos.total_pesos).toLocaleString('es-SV')} {datos.base.unidad}
              </div>
            </Col>
            <Col md={4} className="text-md-end">
              <div className="small text-suave">Total a distribuir</div>
              <div className="monto fs-5 fw-semibold">{formatoMonto(datos.total)}</div>
            </Col>
          </Row>

          <h3 className="h6">Distribución por centro</h3>
          <div className="table-responsive mb-3">
            <Table size="sm" className="align-middle">
              <thead className="table-light">
                <tr className="small text-uppercase text-muted">
                  <th>Centro destino</th>
                  <th className="text-end">Medida</th>
                  <th className="text-end">Porcentaje</th>
                  <th className="text-end">Monto</th>
                </tr>
              </thead>
              <tbody>
                {datos.destinos.map((d) => (
                  <tr key={d.centro_costo}>
                    <td>
                      <code className="me-1">{d.codigo}</code>
                      {d.nombre}
                    </td>
                    <td className="monto">{Number(d.valor).toLocaleString('es-SV')}</td>
                    <td className="monto">{pct(d.porcentaje)}</td>
                    <td className="monto">{formatoMonto(d.monto)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="table-light">
                <tr className="fw-semibold">
                  <td colSpan={3}>Total</td>
                  <td className="monto">{formatoMonto(datos.total)}</td>
                </tr>
              </tfoot>
            </Table>
          </div>

          <h3 className="h6">
            Líneas de origen <span className="text-suave small fw-normal">({datos.origen.length})</span>
          </h3>
          {datos.origen.length === 0 ? (
            <Alert variant="light" className="border small">
              No hay costos en el centro origen para las cuentas de la regla en este periodo.
            </Alert>
          ) : (
            <div className="table-responsive">
              <Table size="sm" className="align-middle small">
                <thead className="table-light">
                  <tr className="text-uppercase text-muted">
                    <th>Fecha</th>
                    <th>Asiento</th>
                    <th>Concepto</th>
                    <th>Cuenta</th>
                    <th className="text-end">Cargo</th>
                    <th className="text-end">Abono</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.origen.map((o) => (
                    <tr key={o.linea}>
                      <td className="text-nowrap">{formatoFecha(o.fecha)}</td>
                      <td>
                        <Link to={`/asientos/${o.asiento_id}`}>
                          <code>{o.asiento_codigo}</code>
                        </Link>
                      </td>
                      <td>{o.concepto}</td>
                      <td>
                        <code className="me-1">{o.cuenta_codigo}</code>
                        {o.cuenta_nombre}
                      </td>
                      <td className="monto">{formatoMonto(o.debe, { vacioSiCero: true })}</td>
                      <td className="monto">{formatoMonto(o.haber, { vacioSiCero: true })}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
          <div className="small text-suave">
            Se generarán (o se generaron) {datos.lineas_generadas} líneas, cada una con referencia a su línea de origen.
          </div>
        </Modal.Body>
      )}
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide}>
          Cerrar
        </Button>
        {accion}
      </Modal.Footer>
    </Modal>
  )
}

export default function EjecucionProrrateo({ periodos, periodo, onPeriodo, puedeEditar }) {
  const [filas, setFilas] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [vista, setVista] = useState(null) // {datos, titulo, regla?}
  const [porAnular, setPorAnular] = useState(null)
  const [motivo, setMotivo] = useState('')

  const datosPeriodo = periodos?.find((p) => p.id === periodo)
  const abierto = datosPeriodo?.estado === 'ABIERTO'

  const cargar = useCallback(async () => {
    if (!periodo) return
    const resp = await api(`/api/prorrateo/ejecuciones/?periodo=${periodo}`)
    if (!resp.ok) {
      setFilas([])
      return setError(await mensajeError(resp))
    }
    setFilas(await resp.json())
  }, [periodo])

  useEffect(() => {
    setFilas(null)
    cargar()
  }, [cargar])

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const previsualizar = async (regla) => {
    setOcupado(true)
    const resp = await api(`/api/prorrateo/ejecuciones/previsualizar/?regla=${regla.id}&periodo=${periodo}`)
    setOcupado(false)
    if (!resp.ok) return setError(await mensajeError(resp))
    setVista({ datos: await resp.json(), titulo: `Vista previa: ${regla.nombre}`, regla })
  }

  const ejecutar = async (regla) => {
    setOcupado(true)
    setVista(null)
    const resp = await api('/api/prorrateo/ejecuciones/', { method: 'POST', body: { regla: regla.id, periodo } })
    setOcupado(false)
    if (!resp.ok) return setError(await mensajeError(resp))
    const e = await resp.json()
    notificar(`«${regla.nombre}»: se distribuyeron ${formatoMonto(e.total_distribuido)} mediante el asiento ${e.asiento_codigo}.`)
    cargar()
  }

  const ejecutarPendientes = async () => {
    setOcupado(true)
    const resp = await api('/api/prorrateo/ejecuciones/pendientes/', { method: 'POST', body: { periodo } })
    setOcupado(false)
    if (!resp.ok) return setError(await mensajeError(resp))
    const resultados = await resp.json()
    notificar(
      resultados
        .map((r) => (r.resultado === 'EJECUTADA' ? `«${r.regla}»: ${formatoMonto(r.total)} (${r.asiento})` : `«${r.regla}»: sin costos`))
        .join(' · '),
    )
    cargar()
  }

  const anular = async (e) => {
    e.preventDefault()
    setOcupado(true)
    const resp = await api(`/api/prorrateo/ejecuciones/${porAnular.vigente.id}/anular/`, { method: 'POST', body: { motivo } })
    setOcupado(false)
    if (!resp.ok) return setError(await mensajeError(resp))
    const r = await resp.json()
    setPorAnular(null)
    notificar(`Prorrateo «${porAnular.regla.nombre}» anulado mediante ${r.reversion?.codigo}.`)
    cargar()
  }

  const pendientes = (filas || []).filter((f) => f.estado !== 'EJECUTADA' && f.regla.activa).length

  return (
    <>
      <Card className="mb-3">
        <Card.Body>
          <Row className="g-2 align-items-end">
            <Col xs={12} md={4}>
              <Form.Label htmlFor="periodo-ejecucion" className="small text-suave mb-1">
                Periodo
              </Form.Label>
              <SelectorPeriodo id="periodo-ejecucion" periodos={periodos} valor={periodo} onChange={onPeriodo} />
            </Col>
            {puedeEditar && (
              <Col xs={12} md="auto" className="ms-md-auto">
                <Button disabled={!abierto || ocupado || pendientes === 0} onClick={ejecutarPendientes}>
                  {ocupado ? <Spinner animation="border" size="sm" className="me-2" /> : <i className="bi bi-play-fill me-1" />}
                  Ejecutar pendientes ({pendientes})
                </Button>
              </Col>
            )}
          </Row>
          {datosPeriodo && !abierto && (
            <div className="small text-suave mt-2">
              <i className="bi bi-lock me-1" />
              El periodo está cerrado: se puede consultar, pero no ejecutar ni anular.
            </div>
          )}
        </Card.Body>
      </Card>

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

      {!filas ? (
        <Spinner animation="border" />
      ) : (
        <Card className="mb-4">
          <div className="table-responsive">
            <Table hover className="align-middle">
              <thead>
                <tr>
                  <th style={{ width: '4rem' }}>Orden</th>
                  <th>Regla</th>
                  <th>Estado</th>
                  <th className="text-end">Distribuido</th>
                  <th>Asiento</th>
                  <th className="text-end">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((f) => {
                  const [color, texto] = ESTADO[f.estado]
                  const v = f.vigente
                  const anuladas = f.historial.filter((h) => h.estado === 'ANULADA')
                  return (
                    <tr key={f.regla.id} className={f.regla.activa ? '' : 'text-suave'}>
                      <td className="text-center">{f.regla.orden}</td>
                      <td>
                        <div>{f.regla.nombre}</div>
                        <div className="small text-suave">
                          Desde <code>{f.regla.centro_origen_codigo}</code> {f.regla.centro_origen_nombre} · {f.regla.base_nombre}
                          {!f.regla.activa && ' · inactiva'}
                        </div>
                      </td>
                      <td>
                        <Badge bg={`${color}-subtle`} text={`${color}-emphasis`}>
                          {texto}
                        </Badge>
                        {anuladas.length > 0 && (
                          <div className="small text-suave mt-1" title={anuladas.map((a) => a.motivo_anulacion).join(' · ')}>
                            {anuladas.length} anulada(s)
                          </div>
                        )}
                      </td>
                      <td className="monto">{v ? formatoMonto(v.total_distribuido) : ''}</td>
                      <td className="small">
                        {v && (
                          <>
                            <Link to={`/asientos/${v.asiento}`}>
                              <code>{v.asiento_codigo}</code>
                            </Link>
                            <div className="text-suave">
                              {v.ejecutado_por} · {formatoFechaHora(v.ejecutado_en)}
                            </div>
                          </>
                        )}
                      </td>
                      <td className="text-end text-nowrap">
                        {v ? (
                          <>
                            <Button
                              size="sm"
                              variant="outline-secondary"
                              className="me-1"
                              title="Ver distribución"
                              onClick={() => setVista({ datos: v.detalle, titulo: `${f.regla.nombre} · ${v.asiento_codigo}` })}
                            >
                              <i className="bi bi-eye" />
                            </Button>
                            {puedeEditar && abierto && (
                              <Button
                                size="sm"
                                variant="outline-danger"
                                title="Anular"
                                onClick={() => {
                                  setMotivo('')
                                  setPorAnular(f)
                                }}
                              >
                                <i className="bi bi-arrow-counterclockwise" />
                              </Button>
                            )}
                          </>
                        ) : (
                          f.regla.activa && (
                            <>
                              <Button size="sm" variant="outline-secondary" className="me-1" disabled={ocupado} onClick={() => previsualizar(f.regla)}>
                                <i className="bi bi-eye me-1" />
                                Vista previa
                              </Button>
                              {puedeEditar && abierto && (
                                <Button size="sm" disabled={ocupado} onClick={() => ejecutar(f.regla)}>
                                  <i className="bi bi-play-fill me-1" />
                                  Ejecutar
                                </Button>
                              )}
                            </>
                          )
                        )}
                      </td>
                    </tr>
                  )
                })}
                {filas.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <EstadoVacio icono="bi-shuffle">No hay reglas de prorrateo activas. Créelas en la pestaña Reglas.</EstadoVacio>
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
        </Card>
      )}

      <DetalleDistribucion
        datos={vista?.datos}
        titulo={vista?.titulo}
        onHide={() => setVista(null)}
        accion={
          vista?.regla &&
          puedeEditar &&
          abierto &&
          vista.datos.origen.length > 0 && (
            <Button disabled={ocupado} onClick={() => ejecutar(vista.regla)}>
              <i className="bi bi-play-fill me-1" />
              Ejecutar y contabilizar
            </Button>
          )
        }
      />

      <Modal show={Boolean(porAnular)} onHide={() => setPorAnular(null)} centered>
        <Form onSubmit={anular}>
          <Modal.Header closeButton>
            <Modal.Title as="h2" className="h5">
              Anular prorrateo
            </Modal.Title>
          </Modal.Header>
          <Modal.Body>
            <p>
              Se registrará la reversión del asiento <code>{porAnular?.vigente?.asiento_codigo}</code> con fecha de cierre del
              periodo. Después podrá corregir medidas o la regla y volver a ejecutar.
            </p>
            <Form.Group controlId="motivo-anulacion">
              <Form.Label>Motivo</Form.Label>
              <Form.Control value={motivo} maxLength={200} onChange={(e) => setMotivo(e.target.value)} autoFocus required />
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setPorAnular(null)}>
              Cancelar
            </Button>
            <Button type="submit" variant="danger" disabled={ocupado || !motivo.trim()}>
              Anular
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>
    </>
  )
}
