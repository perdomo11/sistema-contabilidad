import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, ProgressBar, Row, Spinner, Table } from 'react-bootstrap'
import { Link } from 'react-router-dom'
import { api, mensajeError } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { descargarCSV } from '../exportar'
import { formatoFecha, formatoMonto, hoyISO } from '../formato'

const TRAMOS = {
  VENCIDO: { texto: 'Vencido', color: 'danger' },
  D30: { texto: '0 a 30 días', color: 'warning' },
  D60: { texto: '31 a 60 días', color: 'primary' },
  D90: { texto: '61 a 90 días', color: 'secondary' },
}
const ORDEN = ['VENCIDO', 'D30', 'D60', 'D90']

function InsigniaTramo({ tramo }) {
  const t = TRAMOS[tramo]
  return (
    <Badge bg={`${t.color}-subtle`} text={`${t.color}-emphasis`} className="fw-normal">
      {t.texto}
    </Badge>
  )
}

export default function ProyeccionEgresos() {
  const [fecha, setFecha] = useState(hoyISO())
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)
  const [tramo, setTramo] = useState('')

  const consultar = useCallback(async () => {
    setCargando(true)
    const resp = await api(`/api/tesoreria/proyeccion-egresos/?fecha=${fecha}`)
    setCargando(false)
    if (!resp.ok) {
      setDatos(null)
      return setError(await mensajeError(resp))
    }
    setError('')
    setDatos(await resp.json())
  }, [fecha])

  useEffect(() => {
    consultar()
  }, [consultar])

  const exportar = () => {
    const filas = datos.detalle.map((d) => [
      d.fecha,
      TRAMOS[d.tramo].texto,
      d.categoria_nombre,
      d.concepto,
      d.proveedor?.nombre || '',
      d.monto,
      d.origen === 'CUENTA_POR_PAGAR' ? (d.programado ? `Programado (vence ${d.vencimiento})` : 'Vencimiento') : 'Egreso programado',
    ])
    descargarCSV(`proyeccion_egresos_${datos.fecha}.csv`, ['Fecha', 'Tramo', 'Categoría', 'Concepto', 'Proveedor', 'Monto', 'Base de la fecha'], filas)
  }

  const tramos = datos ? Object.fromEntries(datos.tramos.map((t) => [t.tramo, t])) : {}
  const maxSemana = datos ? Math.max(1, ...datos.semanas.map((s) => Number(s.monto))) : 1
  const detalle = datos ? datos.detalle.filter((d) => !tramo || d.tramo === tramo) : []

  return (
    <>
      <EncabezadoPagina
        titulo="Proyección de egresos"
        descripcion="Salidas de efectivo comprometidas para los próximos 30, 60 y 90 días: cuentas por pagar según su vencimiento o fecha programada, y egresos programados."
        migas={[{ texto: 'Tesorería' }, { texto: 'Proyección de egresos' }]}
      />

      <Card className="mb-3 no-imprimir">
        <Card.Body>
          <Row className="g-2 align-items-end">
            <Col xs={6} md={3}>
              <Form.Label htmlFor="fecha-ref" className="small text-suave mb-1">
                Fecha de referencia
              </Form.Label>
              <Form.Control id="fecha-ref" size="sm" type="date" value={fecha} onChange={(e) => e.target.value && setFecha(e.target.value)} />
            </Col>
            <Col className="text-end">
              <Button as={Link} to="/tesoreria/egresos-programados" size="sm" variant="outline-primary" className="me-2">
                <i className="bi bi-calendar-plus me-1" /> Egresos programados
              </Button>
              <Button size="sm" variant="outline-secondary" className="me-2" disabled={!datos} onClick={exportar}>
                <i className="bi bi-filetype-csv me-1" /> CSV
              </Button>
              <Button size="sm" variant="outline-secondary" disabled={!datos} onClick={() => window.print()}>
                <i className="bi bi-printer me-1" /> Imprimir
              </Button>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {error && <Alert variant="danger">{error}</Alert>}
      {cargando && <Spinner animation="border" />}

      {datos && !cargando && (
        <>
          <div className="encabezado-reporte">
            <strong>Proyección de egresos</strong> al {formatoFecha(datos.fecha)} · horizonte {datos.horizonte} días
          </div>

          <Row className="g-3 mb-3">
            <Col xs={6} lg={3}>
              <Card className="h-100 border-danger-subtle">
                <Card.Body>
                  <div className="small text-suave">Vencido (exigible ya)</div>
                  <div className={`fs-5 fw-semibold ${Number(tramos.VENCIDO.monto) ? 'text-danger' : ''}`}>{formatoMonto(tramos.VENCIDO.monto)}</div>
                </Card.Body>
              </Card>
            </Col>
            {[
              ['30', 'D30'],
              ['60', 'D60'],
              ['90', 'D90'],
            ].map(([dias, t]) => (
              <Col xs={6} lg={3} key={dias}>
                <Card className="h-100">
                  <Card.Body>
                    <div className="small text-suave">A {dias} días (acumulado)</div>
                    <div className="fs-5 fw-semibold">{formatoMonto(datos.acumulado[dias])}</div>
                    <div className="small text-suave">
                      {TRAMOS[t].texto}: {formatoMonto(tramos[t].monto)} · hasta {formatoFecha(tramos[t].hasta)}
                    </div>
                  </Card.Body>
                </Card>
              </Col>
            ))}
          </Row>

          {datos.detalle.length === 0 ? (
            <Card className="mb-3">
              <EstadoVacio icono="bi-calendar-check">
                No hay egresos comprometidos en los próximos {datos.horizonte} días. Registre cuentas por pagar o egresos programados.
              </EstadoVacio>
            </Card>
          ) : (
            <>
              <Card className="mb-3">
                <Card.Header className="fw-semibold">Por categoría</Card.Header>
                <div className="table-responsive">
                  <Table size="sm" className="tabla-matriz align-middle mb-0">
                    <thead className="table-light">
                      <tr>
                        <th>Categoría</th>
                        {ORDEN.map((t) => (
                          <th key={t} className="text-end">
                            {TRAMOS[t].texto}
                          </th>
                        ))}
                        <th className="text-end col-total">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {datos.por_categoria.map((c) => (
                        <tr key={c.categoria}>
                          <td>{c.nombre}</td>
                          {ORDEN.map((t) => (
                            <td key={t} className="monto">
                              {Number(c.tramos[t]) ? formatoMonto(c.tramos[t]) : <span className="text-suave">–</span>}
                            </td>
                          ))}
                          <td className="monto col-total">{formatoMonto(c.total)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="table-light">
                      <tr className="fila-subtotal">
                        <td>Total</td>
                        {ORDEN.map((t) => (
                          <td key={t} className="monto">
                            {formatoMonto(tramos[t].monto)}
                          </td>
                        ))}
                        <td className="monto col-total">{formatoMonto(datos.total)}</td>
                      </tr>
                    </tfoot>
                  </Table>
                </div>
              </Card>

              <Row className="g-3 mb-3">
                <Col lg={7}>
                  <Card className="h-100">
                    <Card.Header className="fw-semibold">Calendario semanal (sin vencidos)</Card.Header>
                    <Table size="sm" className="align-middle mb-0">
                      <tbody>
                        {datos.semanas.map((s) => (
                          <tr key={s.semana} className="small">
                            <td className="text-nowrap text-suave" style={{ width: '9rem' }}>
                              {formatoFecha(s.desde).slice(0, 5)} – {formatoFecha(s.hasta).slice(0, 5)}
                            </td>
                            <td>
                              <ProgressBar now={(Number(s.monto) / maxSemana) * 100} style={{ height: '0.5rem' }} aria-label={`Semana ${s.semana}`} />
                            </td>
                            <td className="monto" style={{ width: '8rem' }}>
                              {Number(s.monto) ? formatoMonto(s.monto) : <span className="text-suave">–</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </Card>
                </Col>
                <Col lg={5}>
                  <Card className="h-100">
                    <Card.Header className="fw-semibold">Principales proveedores</Card.Header>
                    {datos.proveedores.length === 0 ? (
                      <EstadoVacio icono="bi-truck">Sin pagos a proveedores en el horizonte.</EstadoVacio>
                    ) : (
                      <Table size="sm" className="mb-0">
                        <tbody>
                          {datos.proveedores.map((p) => (
                            <tr key={p.id} className="small">
                              <td>{p.nombre}</td>
                              <td className="monto">{formatoMonto(p.monto)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    )}
                  </Card>
                </Col>
              </Row>

              <Card className="mb-3">
                <Card.Header className="d-flex flex-wrap align-items-center gap-2">
                  <span className="fw-semibold me-auto">Detalle de egresos</span>
                  <Form.Select size="sm" style={{ width: 'auto' }} value={tramo} onChange={(e) => setTramo(e.target.value)} aria-label="Filtrar por tramo">
                    <option value="">Todos los tramos</option>
                    {ORDEN.map((t) => (
                      <option key={t} value={t}>
                        {TRAMOS[t].texto}
                      </option>
                    ))}
                  </Form.Select>
                </Card.Header>
                <div className="table-responsive">
                  <Table size="sm" hover className="align-middle mb-0">
                    <thead className="table-light">
                      <tr>
                        <th>Fecha</th>
                        <th>Tramo</th>
                        <th>Categoría</th>
                        <th>Concepto</th>
                        <th>Proveedor</th>
                        <th className="text-end">Monto</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detalle.map((d, i) => (
                        <tr key={`${d.origen}-${d.id}-${d.fecha}-${i}`} className="small">
                          <td className="text-nowrap">
                            {formatoFecha(d.fecha)}
                            {d.origen === 'CUENTA_POR_PAGAR' && d.programado && (
                              <div className="text-suave" title="Fecha de pago programada">
                                <i className="bi bi-calendar-event me-1" />
                                vence {formatoFecha(d.vencimiento)}
                              </div>
                            )}
                          </td>
                          <td>
                            <InsigniaTramo tramo={d.tramo} />
                          </td>
                          <td>{d.categoria_nombre}</td>
                          <td>
                            {d.origen === 'CUENTA_POR_PAGAR' ? (
                              <Link to={`/tesoreria/cuentas-por-pagar?documento=${d.id}`}>{d.concepto}</Link>
                            ) : (
                              d.concepto
                            )}
                          </td>
                          <td>{d.proveedor?.nombre || <span className="text-suave">—</span>}</td>
                          <td className="monto">{formatoMonto(d.monto)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </Card>
            </>
          )}
          <div className="small text-suave mb-4 no-imprimir">
            <i className="bi bi-info-circle me-1" />
            Proyección basada en compromisos ciertos: saldo de cada cuenta por pagar en su fecha de pago programada (o en su vencimiento) y
            egresos programados activos. Los egresos programados anteriores a la fecha de referencia se suponen atendidos.
          </div>
        </>
      )}
    </>
  )
}
