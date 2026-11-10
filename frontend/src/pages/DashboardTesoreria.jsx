import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Row, Spinner, Table } from 'react-bootstrap'
import { Link } from 'react-router-dom'
import { api, mensajeError } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { GraficoBarras, GraficoColumnas, GraficoLinea, TarjetaGrafico } from '../components/graficos/Graficos'
import { Monto } from '../components/reportes/ReporteSegmentado'
import { formatoFecha, formatoMonto, hoyISO } from '../formato'

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const NIVEL = {
  CRITICA: { variant: 'danger', icono: 'bi-exclamation-octagon', texto: 'Crítica' },
  ADVERTENCIA: { variant: 'warning', icono: 'bi-exclamation-triangle', texto: 'Advertencia' },
  INFORMATIVA: { variant: 'info', icono: 'bi-info-circle', texto: 'Informativa' },
}
const TRAMOS = { VENCIDO: 'Vencido', D30: '0 a 30 días', D60: '31 a 60 días', D90: '61 a 90 días' }
const ANTIGUEDAD = { '1-30': '1 a 30 días', '31-60': '31 a 60 días', '61-90': '61 a 90 días', mas_90: 'Más de 90' }
const SERIES_FLUJO = [
  { nombre: 'Entradas', color: 'var(--viz-serie-1)' },
  { nombre: 'Salidas', color: 'var(--viz-serie-2)' },
]

const corta = (iso) => formatoFecha(iso).slice(0, 5)

function Indicador({ titulo, valor, pie, alerta, enlace }) {
  return (
    <Col xs={6} xl={3}>
      <Card className="h-100">
        <Card.Body>
          <div className="small text-suave">{titulo}</div>
          <div className={`fs-5 fw-semibold ${alerta || ''}`}>{valor}</div>
          {pie && <div className="small text-suave">{pie}</div>}
          {enlace && (
            <Link to={enlace.a} className="small no-imprimir">
              {enlace.texto} <i className="bi bi-arrow-right-short" />
            </Link>
          )}
        </Card.Body>
      </Card>
    </Col>
  )
}

function SeccionFlujo({ datos }) {
  const f = datos.flujo
  if (!f) {
    return (
      <Alert variant="warning" className="d-flex flex-wrap align-items-center gap-2">
        <i className="bi bi-exclamation-triangle" />
        <span className="me-auto">{datos.aviso_flujo}</span>
        <Button as={Link} to="/tesoreria/flujo-efectivo?vista=configuracion" size="sm" variant="outline-dark">
          Configurar cuentas de efectivo
        </Button>
      </Alert>
    )
  }

  const puntos = [
    { etiqueta: `Hoy (${formatoFecha(datos.fecha)})`, etiquetaCorta: 'Hoy', valor: Number(f.saldo_actual), estado: 'OK' },
    ...f.semanas.map((s) => ({
      etiqueta: `Semana ${s.semana}: ${corta(s.desde)} – ${corta(s.hasta)}`,
      etiquetaCorta: corta(s.hasta),
      valor: Number(s.saldo_final),
      estado: s.estado,
      detalle: [
        { nombre: 'entradas estimadas', valor: formatoMonto(s.entradas) },
        { nombre: 'salidas comprometidas', valor: formatoMonto(s.salidas) },
      ],
    })),
  ]
  const deficit = f.semanas.some((s) => s.estado === 'DEFICIT')
  const bajo = f.semanas.some((s) => s.estado === 'BAJO_MINIMO')

  return (
    <>
      {f.alertas.length === 0 ? (
        <Alert variant="success" className="d-flex align-items-center gap-2">
          <i className="bi bi-check-circle" /> Sin déficit proyectado en las próximas 13 semanas.
        </Alert>
      ) : (
        f.alertas.map((a, i) => (
          <Alert key={i} variant={NIVEL[a.nivel].variant} className="d-flex align-items-start gap-2">
            <i className={`bi ${NIVEL[a.nivel].icono} mt-1`} />
            <span>
              <strong>{NIVEL[a.nivel].texto}:</strong> {a.mensaje}
            </span>
          </Alert>
        ))
      )}

      <Row className="g-3 mb-3">
        <Col lg={4}>
          <Card className="h-100">
            <Card.Body className="d-flex flex-column justify-content-center">
              <div className="small text-suave">Saldo de efectivo al {formatoFecha(datos.fecha)}</div>
              <div className={`cifra-principal ${Number(f.saldo_actual) < 0 ? 'text-danger' : ''}`}>{formatoMonto(f.saldo_actual)}</div>
              <div className="small text-suave mt-1">
                Mínimo de política: {formatoMonto(f.saldo_minimo)} · entradas estimadas {formatoMonto(f.entradas_diarias)}/día
              </div>
            </Card.Body>
          </Card>
        </Col>
        <Col lg={8}>
          <Row className="g-3 h-100">
            {['30', '60', '90'].map((d) => {
              const v = Number(f.saldo_proyectado[d])
              const estado = v < 0 ? 'DEFICIT' : v < Number(f.saldo_minimo) ? 'BAJO_MINIMO' : null
              return (
                <Col xs={12} sm={4} key={d}>
                  <Card className="h-100">
                    <Card.Body>
                      <div className="small text-suave">Saldo proyectado a {d} días</div>
                      <div className="fs-4 fw-semibold">
                        <Monto valor={f.saldo_proyectado[d]} alertar />
                      </div>
                      {estado && (
                        <Badge bg={estado === 'DEFICIT' ? 'danger-subtle' : 'warning-subtle'} text={estado === 'DEFICIT' ? 'danger-emphasis' : 'warning-emphasis'}>
                          <i className={`bi ${estado === 'DEFICIT' ? 'bi-exclamation-octagon' : 'bi-exclamation-triangle'} me-1`} />
                          {estado === 'DEFICIT' ? 'Déficit' : 'Bajo el mínimo'}
                        </Badge>
                      )}
                    </Card.Body>
                  </Card>
                </Col>
              )
            })}
          </Row>
        </Col>
      </Row>

      <Row className="g-3 mb-3">
        <Col lg={7}>
          <TarjetaGrafico
            titulo="Saldo de efectivo proyectado"
            subtitulo="Cierre de cada semana; línea gris = cero, ámbar = saldo mínimo"
            accion={
              <Button as={Link} to="/tesoreria/flujo-efectivo" size="sm" variant="link" className="no-imprimir">
                Detalle
              </Button>
            }
            columnas={['Semana', 'Saldo final', 'Estado']}
            filas={puntos.map((p) => [p.etiqueta, formatoMonto(String(p.valor)), p.estado === 'DEFICIT' ? 'Déficit' : p.estado === 'BAJO_MINIMO' ? 'Bajo el mínimo' : ''])}
          >
            <GraficoLinea
              puntos={puntos}
              nombreSerie="saldo proyectado"
              referencias={[
                { valor: 0, nombre: 'Cero', tipo: 'base' },
                { valor: Number(f.saldo_minimo), nombre: 'Mínimo', tipo: 'advertencia' },
              ]}
            />
            {(deficit || bajo) && (
              <div className="small text-suave mt-2">
                {deficit && (
                  <span className="me-3">
                    <i className="bi bi-circle-fill me-1" style={{ color: 'var(--bs-danger)', fontSize: '0.6rem' }} />
                    <i className="bi bi-exclamation-octagon me-1" />
                    Semana en déficit
                  </span>
                )}
                {bajo && (
                  <span>
                    <i className="bi bi-circle-fill me-1" style={{ color: '#fab219', fontSize: '0.6rem' }} />
                    <i className="bi bi-exclamation-triangle me-1" />
                    Bajo el mínimo
                  </span>
                )}
              </div>
            )}
          </TarjetaGrafico>
        </Col>
        <Col lg={5}>
          <TarjetaGrafico
            titulo="Entradas y salidas de efectivo"
            subtitulo="Reales, últimos 6 meses"
            leyenda={SERIES_FLUJO}
            columnas={['Mes', 'Entradas', 'Salidas', 'Neto']}
            filas={datos.flujo_mensual.map((m) => [`${MESES[m.mes - 1]} ${m.anio}`, formatoMonto(m.entradas), formatoMonto(m.salidas), formatoMonto(m.neto)])}
          >
            <GraficoColumnas
              series={SERIES_FLUJO}
              categorias={datos.flujo_mensual.map((m) => ({ etiqueta: MESES[m.mes - 1], valores: [Number(m.entradas), Number(m.salidas)] }))}
            />
          </TarjetaGrafico>
        </Col>
      </Row>
    </>
  )
}

export default function DashboardTesoreria() {
  const [fecha, setFecha] = useState(hoyISO())
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const consultar = useCallback(async () => {
    setCargando(true)
    const resp = await api(`/api/tesoreria/dashboard/?fecha=${fecha}`)
    setCargando(false)
    if (!resp.ok) return setError(await mensajeError(resp))
    setError('')
    setDatos(await resp.json())
  }, [fecha])

  useEffect(() => {
    consultar()
  }, [consultar])

  const cxp = datos?.cuentas_por_pagar
  const egresos = datos?.egresos
  const tramo = (t) => egresos.tramos.find((x) => x.tramo === t).monto

  return (
    <>
      <EncabezadoPagina
        titulo="Dashboard de tesorería"
        descripcion="Posición de efectivo, compromisos de pago y alertas de liquidez en una sola vista."
        migas={[{ texto: 'Tesorería' }, { texto: 'Dashboard' }]}
      >
        <Button size="sm" variant="outline-secondary" className="no-imprimir" disabled={!datos} onClick={() => window.print()}>
          <i className="bi bi-printer me-1" /> Imprimir
        </Button>
      </EncabezadoPagina>

      <Row className="g-2 align-items-end mb-3 no-imprimir">
        <Col xs={6} md={3}>
          <Form.Label htmlFor="dash-fecha" className="small text-suave mb-1">
            Fecha de referencia
          </Form.Label>
          <Form.Control id="dash-fecha" size="sm" type="date" value={fecha} onChange={(e) => e.target.value && setFecha(e.target.value)} />
        </Col>
        <Col xs="auto">
          <Button size="sm" variant="outline-primary" onClick={() => setFecha(hoyISO())} disabled={fecha === hoyISO()}>
            Hoy
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger">{error}</Alert>}
      {!datos && !error && <Spinner animation="border" />}

      {datos && (
        // Al recargar se conserva el tablero anterior atenuado (sin saltos de diseño).
        <div style={{ opacity: cargando ? 0.55 : 1, transition: 'opacity 0.2s' }}>
          <SeccionFlujo datos={datos} />

          <h2 className="h6 text-uppercase text-suave mt-4 mb-2">Compromisos de pago</h2>
          <Row className="g-3 mb-3">
            <Indicador
              titulo="Vencido (exigible ya)"
              valor={formatoMonto(tramo('VENCIDO'))}
              alerta={Number(tramo('VENCIDO')) ? 'text-danger' : ''}
              pie={`${cxp.documentos.vencidos} documento(s) por pagar vencido(s)`}
              enlace={{ a: '/tesoreria/cuentas-por-pagar', texto: 'Cuentas por pagar' }}
            />
            {['30', '60', '90'].map((d) => (
              <Indicador
                key={d}
                titulo={`Egresos a ${d} días (acumulado)`}
                valor={formatoMonto(egresos.acumulado[d])}
                pie="Incluye lo vencido"
                enlace={d === '90' ? { a: '/tesoreria/proyeccion-egresos', texto: 'Proyección de egresos' } : null}
              />
            ))}
          </Row>

          <Row className="g-3 mb-3">
            <Col lg={6}>
              <TarjetaGrafico
                titulo="Egresos comprometidos por tramo"
                subtitulo="Cuentas por pagar y egresos programados"
                columnas={['Tramo', 'Monto']}
                filas={egresos.tramos.map((t) => [TRAMOS[t.tramo], formatoMonto(t.monto)])}
              >
                <GraficoBarras items={egresos.tramos.map((t) => ({ etiqueta: TRAMOS[t.tramo], valor: Number(t.monto) }))} />
              </TarjetaGrafico>
            </Col>
            <Col lg={6}>
              <TarjetaGrafico
                titulo="Antigüedad de saldos vencidos"
                subtitulo={`Pendiente total ${formatoMonto(cxp.pendiente)} · vence en ${cxp.dias_por_vencer} días: ${formatoMonto(cxp.por_vencer)}`}
                columnas={['Días de atraso', 'Saldo']}
                filas={cxp.antiguedad.map((a) => [ANTIGUEDAD[a.tramo], formatoMonto(a.monto)])}
              >
                {Number(cxp.vencido) === 0 ? (
                  <EstadoVacio icono="bi-check2-circle">No hay cuentas por pagar vencidas.</EstadoVacio>
                ) : (
                  <GraficoBarras items={cxp.antiguedad.map((a) => ({ etiqueta: ANTIGUEDAD[a.tramo], valor: Number(a.monto) }))} />
                )}
              </TarjetaGrafico>
            </Col>
          </Row>

          <Row className="g-3 mb-4">
            <Col lg={7}>
              <Card className="h-100">
                <Card.Header className="d-flex align-items-center">
                  <span className="fw-semibold me-auto">Próximos pagos (vencidos y 7 días)</span>
                  {datos.proximos_pagos_total > datos.proximos_pagos.length && (
                    <Link to="/tesoreria/proyeccion-egresos" className="small">
                      Ver los {datos.proximos_pagos_total}
                    </Link>
                  )}
                </Card.Header>
                {datos.proximos_pagos.length === 0 ? (
                  <EstadoVacio icono="bi-calendar-check">Sin pagos en los próximos 7 días.</EstadoVacio>
                ) : (
                  <div className="table-responsive">
                    <Table size="sm" hover className="align-middle mb-0">
                      <tbody>
                        {datos.proximos_pagos.map((p, i) => (
                          <tr key={`${p.origen}-${p.id}-${p.fecha}-${i}`} className="small">
                            <td className="text-nowrap">
                              {formatoFecha(p.fecha)}
                              {p.tramo === 'VENCIDO' && (
                                <Badge bg="danger-subtle" text="danger-emphasis" className="ms-2 fw-normal">
                                  vencido
                                </Badge>
                              )}
                            </td>
                            <td>
                              {p.origen === 'CUENTA_POR_PAGAR' ? (
                                <Link to={`/tesoreria/cuentas-por-pagar?documento=${p.id}`}>{p.concepto}</Link>
                              ) : (
                                p.concepto
                              )}
                              <div className="text-suave">{p.proveedor?.nombre || p.categoria_nombre}</div>
                            </td>
                            <td className="monto">{formatoMonto(p.monto)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                )}
              </Card>
            </Col>
            <Col lg={5}>
              <Card className="h-100">
                <Card.Header className="fw-semibold">Egresos a 90 días por categoría</Card.Header>
                {egresos.por_categoria.length === 0 ? (
                  <EstadoVacio icono="bi-calendar-check">Sin egresos comprometidos.</EstadoVacio>
                ) : (
                  <Table size="sm" className="mb-0">
                    <tbody>
                      {egresos.por_categoria.map((c) => (
                        <tr key={c.categoria} className="small">
                          <td>{c.nombre}</td>
                          <td className="monto">{formatoMonto(c.total)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="table-light">
                      <tr className="small fila-subtotal">
                        <td>Total</td>
                        <td className="monto">{formatoMonto(egresos.total)}</td>
                      </tr>
                    </tfoot>
                  </Table>
                )}
              </Card>
            </Col>
          </Row>
        </div>
      )}
    </>
  )
}
