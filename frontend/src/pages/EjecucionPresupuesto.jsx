import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, ProgressBar, Row, Spinner, Table } from 'react-bootstrap'
import { useSearchParams } from 'react-router-dom'
import { api, mensajeError } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { Monto, Porcentaje } from '../components/reportes/ReporteSegmentado'
import { descargarCSV } from '../exportar'
import { formatoMonto } from '../formato'

const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

const ESTADO = {
  SOBREGIRO: { color: 'danger', texto: 'Sobregiro', icono: 'bi-exclamation-octagon' },
  DESVIACION: { color: 'warning', texto: 'Desviación', icono: 'bi-exclamation-triangle' },
  SIN_PRESUPUESTO: { color: 'warning', texto: 'Gasto sin presupuesto', icono: 'bi-question-circle' },
  SUBEJECUCION: { color: 'info', texto: 'Subejecución', icono: 'bi-info-circle' },
  EN_RANGO: { color: 'success', texto: 'En rango', icono: 'bi-check-circle' },
}
const NIVEL = {
  CRITICA: { color: 'danger', texto: 'Crítica' },
  ADVERTENCIA: { color: 'warning', texto: 'Advertencia' },
  INFORMATIVA: { color: 'info', texto: 'Informativa' },
}

function InsigniaEstado({ estado }) {
  const e = ESTADO[estado]
  return (
    <Badge bg={`${e.color}-subtle`} text={`${e.color}-emphasis`} className="fw-normal">
      <i className={`bi ${e.icono} me-1`} />
      {e.texto}
    </Badge>
  )
}

/** Barra de lo ejecutado frente al presupuesto anual; en rojo si lo supera. */
function BarraEjecucion({ porcentaje }) {
  if (porcentaje === null) return <span className="small text-suave">sin presupuesto</span>
  const n = Number(porcentaje)
  return (
    <div title={`${porcentaje} % del presupuesto anual`}>
      <ProgressBar
        now={Math.min(n, 100)}
        variant={n > 100 ? 'danger' : n >= 90 ? 'warning' : 'primary'}
        style={{ height: '0.5rem' }}
        aria-label={`${porcentaje} % del presupuesto anual`}
      />
      <div className="small text-suave text-end">{porcentaje} % del anual</div>
    </div>
  )
}

function Tarjeta({ titulo, children, pie }) {
  return (
    <Col xs={6} lg={3}>
      <Card className="h-100">
        <Card.Body>
          <div className="small text-suave">{titulo}</div>
          <div className="fs-5 fw-semibold monto text-start">{children}</div>
          {pie && <div className="small text-suave">{pie}</div>}
        </Card.Body>
      </Card>
    </Col>
  )
}

/** Comparación mes a mes (presupuesto, ejecutado y acumulados). */
function TablaMensual({ mensual, corte }) {
  return (
    <div className="table-responsive">
      <Table size="sm" className="tabla-matriz align-middle mb-0">
        <thead className="table-light">
          <tr>
            <th>Mes</th>
            <th className="text-end">Presupuesto</th>
            <th className="text-end">Ejecutado</th>
            <th className="text-end">Presupuesto acumulado</th>
            <th className="text-end">Ejecutado acumulado</th>
            <th className="text-end">Variación acumulada</th>
          </tr>
        </thead>
        <tbody>
          {mensual.map((m) => (
            <tr key={m.mes} className={m.mes > corte ? 'text-suave' : m.mes === corte ? 'fila-subtotal' : ''}>
              <td>
                {MESES[m.mes - 1]}
                {m.mes === corte && (
                  <Badge bg="primary-subtle" text="primary-emphasis" className="ms-2 fw-normal">
                    corte
                  </Badge>
                )}
              </td>
              <td className="monto">{formatoMonto(m.presupuesto)}</td>
              <td className="monto">{formatoMonto(m.ejecutado)}</td>
              <td className="monto">{formatoMonto(m.presupuesto_acumulado)}</td>
              <td className="monto">{formatoMonto(m.ejecutado_acumulado)}</td>
              <td className="monto">
                <Monto valor={m.variacion_acumulada} alertar />
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}

export default function EjecucionPresupuesto() {
  const [params, setParams] = useSearchParams()
  const [presupuestos, setPresupuestos] = useState(null)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)
  const [umbral, setUmbral] = useState(params.get('umbral') || '10')

  const presupuestoId = params.get('presupuesto')
  const corte = params.get('corte') || ''
  const centroId = params.get('centro') || ''

  useEffect(() => {
    api('/api/presupuestos/').then(async (r) => {
      const lista = r.ok ? await r.json() : []
      setPresupuestos(lista)
      if (!params.get('presupuesto') && lista.length) {
        const actual = lista.find((p) => p.anio === new Date().getFullYear()) || lista[0]
        setParams({ presupuesto: actual.id }, { replace: true })
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const consultar = useCallback(async () => {
    if (!presupuestoId) return
    setCargando(true)
    const q = new URLSearchParams({ umbral: params.get('umbral') || '10' })
    if (corte) q.set('corte', corte)
    if (centroId) q.set('centro', centroId)
    const resp = await api(`/api/presupuestos/${presupuestoId}/ejecucion/?${q}`)
    setCargando(false)
    if (!resp.ok) {
      setDatos(null)
      return setError(await mensajeError(resp))
    }
    setError('')
    setDatos(await resp.json())
  }, [presupuestoId, corte, centroId, params])

  useEffect(() => {
    consultar()
  }, [consultar])

  const cambiar = (cambios) => {
    const p = Object.fromEntries([...params.entries()])
    const nuevo = { ...p, ...cambios }
    Object.keys(nuevo).forEach((k) => (nuevo[k] === '' || nuevo[k] === null) && delete nuevo[k])
    setParams(nuevo)
  }

  const exportar = () => {
    const filas = datos.departamentos.map((d) => [
      `${d.centro.codigo} ${d.centro.nombre}`,
      d.presupuesto_anual,
      d.presupuesto_al_corte,
      d.ejecutado_al_corte,
      d.variacion,
      d.porcentaje_ejecucion ?? '',
      d.disponible_anual,
      ESTADO[d.estado].texto,
    ])
    const t = datos.totales
    filas.push(['Total', t.presupuesto_anual, t.presupuesto_al_corte, t.ejecutado_al_corte, t.variacion, t.porcentaje_ejecucion ?? '', t.disponible_anual, ''])
    filas.push([])
    datos.alertas.forEach((a) => filas.push([NIVEL[a.nivel].texto, a.mensaje]))
    descargarCSV(
      `ejecucion_presupuesto_${datos.presupuesto.anio}_corte_${datos.corte}.csv`,
      ['Departamento', 'Presupuesto anual', 'Presupuesto al corte', 'Ejecutado al corte', 'Variación', '% ejecución', 'Disponible anual', 'Estado'],
      filas,
    )
  }

  const t = datos?.totales
  const c = datos?.centro

  return (
    <>
      <EncabezadoPagina
        titulo="Ejecución vs. presupuesto"
        descripcion="Gasto real de cada departamento frente a lo presupuestado, acumulado al mes de corte, con alertas de desviación."
        migas={[{ texto: 'Presupuesto' }, { texto: 'Ejecución vs. presupuesto' }]}
      />

      {presupuestos && presupuestos.length === 0 ? (
        <Card>
          <EstadoVacio icono="bi-wallet2">Primero registre y distribuya un presupuesto institucional.</EstadoVacio>
        </Card>
      ) : (
        <Card className="mb-3 no-imprimir">
          <Card.Body>
            <Form
              onSubmit={(e) => {
                e.preventDefault()
                cambiar({ umbral })
              }}
            >
              <Row className="g-2 align-items-end">
                <Col xs={6} md={3}>
                  <Form.Label htmlFor="ejercicio" className="small text-suave mb-1">
                    Ejercicio
                  </Form.Label>
                  <Form.Select id="ejercicio" size="sm" value={presupuestoId || ''} onChange={(e) => cambiar({ presupuesto: e.target.value, centro: '' })}>
                    {(presupuestos || []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.anio} · {p.estado_display}
                      </option>
                    ))}
                  </Form.Select>
                </Col>
                <Col xs={6} md={3}>
                  <Form.Label htmlFor="corte" className="small text-suave mb-1">
                    Acumulado hasta
                  </Form.Label>
                  <Form.Select id="corte" size="sm" value={corte || datos?.corte || ''} onChange={(e) => cambiar({ corte: e.target.value })}>
                    {MESES.map((m, i) => (
                      <option key={m} value={i + 1}>
                        {m}
                      </option>
                    ))}
                  </Form.Select>
                </Col>
                <Col xs={6} md={2}>
                  <Form.Label htmlFor="umbral" className="small text-suave mb-1">
                    Tolerancia (%)
                  </Form.Label>
                  <Form.Control id="umbral" size="sm" type="number" min="0" max="100" step="1" value={umbral} onChange={(e) => setUmbral(e.target.value)} />
                </Col>
                <Col xs={6} md="auto">
                  <Button type="submit" size="sm" variant="outline-primary">
                    <i className="bi bi-arrow-repeat me-1" /> Aplicar
                  </Button>
                </Col>
                <Col className="text-md-end">
                  <Button size="sm" variant="outline-secondary" className="me-2" disabled={!datos} onClick={exportar}>
                    <i className="bi bi-filetype-csv me-1" /> CSV
                  </Button>
                  <Button size="sm" variant="outline-secondary" disabled={!datos} onClick={() => window.print()}>
                    <i className="bi bi-printer me-1" /> Imprimir
                  </Button>
                </Col>
              </Row>
            </Form>
          </Card.Body>
        </Card>
      )}

      {error && <Alert variant="danger">{error}</Alert>}
      {(cargando || !presupuestos) && <Spinner animation="border" />}

      {datos && !cargando && (
        <>
          <div className="encabezado-reporte">
            <strong>Ejecución del presupuesto {datos.presupuesto.anio}</strong> · acumulado a {MESES[datos.corte - 1].toLowerCase()} ·
            tolerancia {Number(datos.umbral)} %
          </div>

          <Row className="g-3 mb-3">
            <Tarjeta titulo="Presupuesto al corte" pie={`Anual distribuido: ${formatoMonto(t.presupuesto_anual)}`}>
              {formatoMonto(t.presupuesto_al_corte)}
            </Tarjeta>
            <Tarjeta titulo="Ejecutado al corte" pie={Number(datos.sin_centro) ? `Gasto sin centro (no atribuido): ${formatoMonto(datos.sin_centro)}` : null}>
              {formatoMonto(t.ejecutado_al_corte)}
            </Tarjeta>
            <Tarjeta titulo="Variación (presupuesto − ejecutado)" pie="Negativa = sobregasto">
              <Monto valor={t.variacion} alertar />
            </Tarjeta>
            <Tarjeta titulo="% de ejecución al corte" pie={`Disponible anual: ${formatoMonto(t.disponible_anual)}`}>
              <Porcentaje valor={t.porcentaje_ejecucion} />
            </Tarjeta>
          </Row>

          <Card className="mb-3">
            <Card.Header className="d-flex flex-wrap gap-2 align-items-center">
              <span className="fw-semibold me-auto">Alertas</span>
              {Object.entries(datos.resumen_alertas).map(([n, cant]) => (
                <Badge key={n} bg={`${NIVEL[n].color}-subtle`} text={`${NIVEL[n].color}-emphasis`} className="fw-normal">
                  {NIVEL[n].texto}: {cant}
                </Badge>
              ))}
            </Card.Header>
            {datos.alertas.length === 0 ? (
              <EstadoVacio icono="bi-check2-circle">Sin alertas: la ejecución está dentro de la tolerancia.</EstadoVacio>
            ) : (
              <div className="list-group list-group-flush" style={{ maxHeight: '18rem', overflowY: 'auto' }}>
                {datos.alertas.map((a, i) => (
                  <div key={i} className="list-group-item d-flex gap-2 align-items-start small">
                    <Badge bg={`${NIVEL[a.nivel].color}-subtle`} text={`${NIVEL[a.nivel].color}-emphasis`} className="fw-normal mt-1">
                      {ESTADO[a.tipo].texto}
                    </Badge>
                    <span className="me-auto">{a.mensaje}</span>
                    <Button variant="link" size="sm" className="p-0 no-imprimir text-nowrap" onClick={() => cambiar({ centro: a.centro.id })}>
                      Ver detalle
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card className="mb-3">
            <Card.Header className="fw-semibold">Departamentos</Card.Header>
            <div className="table-responsive">
              <Table hover className="align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th>Departamento</th>
                    <th className="text-end">Presupuesto al corte</th>
                    <th className="text-end">Ejecutado al corte</th>
                    <th className="text-end">Variación</th>
                    <th className="text-end">% ejecución</th>
                    <th style={{ minWidth: '9rem' }}>Presupuesto anual</th>
                    <th>Estado</th>
                    <th className="no-imprimir" />
                  </tr>
                </thead>
                <tbody>
                  {datos.departamentos.map((d) => (
                    <tr key={d.centro.id} className={String(d.centro.id) === centroId ? 'table-active' : ''}>
                      <td>
                        <code className="me-2">{d.centro.codigo}</code>
                        {d.centro.nombre}
                      </td>
                      <td className="monto">{formatoMonto(d.presupuesto_al_corte)}</td>
                      <td className="monto">{formatoMonto(d.ejecutado_al_corte)}</td>
                      <td className="monto">
                        <Monto valor={d.variacion} alertar />
                      </td>
                      <td className="monto">
                        <Porcentaje valor={d.porcentaje_ejecucion} />
                      </td>
                      <td>
                        {d.con_asignacion && <div className="small monto text-start">{formatoMonto(d.presupuesto_anual)}</div>}
                        <BarraEjecucion porcentaje={d.porcentaje_anual} />
                      </td>
                      <td>
                        <InsigniaEstado estado={d.estado} />
                      </td>
                      <td className="text-end no-imprimir">
                        <Button
                          size="sm"
                          variant={String(d.centro.id) === centroId ? 'primary' : 'outline-primary'}
                          onClick={() => cambiar({ centro: String(d.centro.id) === centroId ? '' : d.centro.id })}
                        >
                          Detalle
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {datos.departamentos.length === 0 && (
                    <tr>
                      <td colSpan={8}>
                        <EstadoVacio icono="bi-diagram-2">
                          No hay departamentos con presupuesto ni gasto en {datos.presupuesto.anio}. Distribuya el presupuesto en Presupuesto → Distribución a
                          departamentos.
                        </EstadoVacio>
                      </td>
                    </tr>
                  )}
                </tbody>
                {datos.departamentos.length > 0 && (
                  <tfoot className="table-light">
                    <tr className="fila-subtotal">
                      <td>Total</td>
                      <td className="monto">{formatoMonto(t.presupuesto_al_corte)}</td>
                      <td className="monto">{formatoMonto(t.ejecutado_al_corte)}</td>
                      <td className="monto">
                        <Monto valor={t.variacion} alertar />
                      </td>
                      <td className="monto">
                        <Porcentaje valor={t.porcentaje_ejecucion} />
                      </td>
                      <td colSpan={3} />
                    </tr>
                  </tfoot>
                )}
              </Table>
            </div>
          </Card>

          {c && (
            <Card className="mb-3">
              <Card.Header className="d-flex justify-content-between align-items-center">
                <span className="fw-semibold">
                  Detalle · <code>{c.codigo}</code> {c.nombre}
                </span>
                <Button size="sm" variant="link" className="no-imprimir" onClick={() => cambiar({ centro: '' })}>
                  Cerrar
                </Button>
              </Card.Header>
              <div className="table-responsive">
                <Table size="sm" className="tabla-matriz align-middle mb-0">
                  <thead className="table-light">
                    <tr>
                      <th>Cuenta</th>
                      <th className="text-end">Presupuesto anual</th>
                      <th className="text-end">Presupuesto al corte</th>
                      <th className="text-end">Ejecutado al corte</th>
                      <th className="text-end">Variación</th>
                      <th className="text-end">% ejecución</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.cuentas.map((f) => (
                      <tr key={f.cuenta.id}>
                        <td className="small">
                          <code className="me-2">{f.cuenta.codigo}</code>
                          {f.cuenta.nombre}
                        </td>
                        <td className="monto">{formatoMonto(f.presupuesto_anual)}</td>
                        <td className="monto">{formatoMonto(f.presupuesto_al_corte)}</td>
                        <td className="monto">{formatoMonto(f.ejecutado_al_corte)}</td>
                        <td className="monto">
                          <Monto valor={f.variacion} alertar />
                        </td>
                        <td className="monto">
                          {f.porcentaje_ejecucion === null && Number(f.ejecutado_al_corte) > 0 ? (
                            <Badge bg="warning-subtle" text="warning-emphasis" className="fw-normal">
                              sin presupuesto
                            </Badge>
                          ) : (
                            <Porcentaje valor={f.porcentaje_ejecucion} />
                          )}
                        </td>
                      </tr>
                    ))}
                    {c.cuentas.length === 0 && (
                      <tr>
                        <td colSpan={6}>
                          <EstadoVacio icono="bi-grid-3x3">Sin presupuesto detallado ni gasto en este departamento.</EstadoVacio>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </Table>
              </div>
              <Card.Header className="fw-semibold border-top">Mes a mes</Card.Header>
              <TablaMensual mensual={c.mensual} corte={datos.corte} />
            </Card>
          )}

          {!c && (
            <Card className="mb-3">
              <Card.Header className="fw-semibold">Mes a mes · toda la institución</Card.Header>
              <TablaMensual mensual={datos.mensual} corte={datos.corte} />
            </Card>
          )}

          <div className="small text-suave mb-4 no-imprimir">
            <i className="bi bi-info-circle me-1" />
            Ejecutado = gasto de asientos contabilizados por centro, sin los asientos de prorrateo (miden el gasto que controla cada responsable).
            Sobregiro: el ejecutado supera el presupuesto anual del departamento. Desviación y subejecución: el % de ejecución al corte queda fuera de
            100 % ± la tolerancia.
          </div>
        </>
      )}
    </>
  )
}
