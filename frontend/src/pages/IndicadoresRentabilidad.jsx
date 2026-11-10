import { Fragment } from 'react'
import { Alert, Card, Col, Row, Spinner, Table } from 'react-bootstrap'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import {
  EncabezadoUnidad,
  FiltrosReporte,
  Monto,
  NavegacionUnidad,
  Porcentaje,
  nombreColumna,
  useReporteSegmentado,
} from '../components/reportes/ReporteSegmentado'
import { descargarCSV } from '../exportar'
import { formatoFecha } from '../formato'

// Filas de resultado (se destacan) dentro de la cascada de montos.
const RESULTADOS = new Set(['margen_bruto', 'resultado_operativo', 'resultado_neto'])

/** Barra horizontal de participación; negativos en rojo hacia la izquierda del cero. */
function BarraParticipacion({ valor }) {
  if (valor === null || valor === undefined) return null
  const n = Number(valor)
  const ancho = Math.min(Math.abs(n), 100)
  return (
    <div className="d-flex" style={{ height: '0.5rem' }} aria-hidden="true">
      <div className="w-25 d-flex justify-content-end bg-body-tertiary rounded-start">
        {n < 0 && <div className="bg-danger h-100 rounded-start" style={{ width: `${Math.min(ancho * 4, 100)}%` }} />}
      </div>
      <div className="w-75 bg-body-tertiary rounded-end">
        {n > 0 && <div className="bg-primary h-100 rounded-end" style={{ width: `${ancho}%` }} />}
      </div>
    </div>
  )
}

export default function IndicadoresRentabilidad() {
  const reporte = useReporteSegmentado('/api/reportes/indicadores/')
  const { datos, error, cargando, irA } = reporte

  const exportar = () => {
    const columnas = datos.columnas.map(nombreColumna)
    const filas = []
    datos.montos.forEach((m) => filas.push([m.titulo, ...m.valores.map((v) => v ?? ''), m.total]))
    filas.push([])
    datos.indicadores.forEach((i) => filas.push([`${i.titulo} (% sobre ${i.base})`, ...i.valores.map((v) => v ?? ''), i.total ?? '']))
    datos.participacion.forEach((p) => filas.push([`${p.titulo} (%)`, ...p.valores.map((v) => v ?? ''), p.total ?? '']))
    const sufijo = datos.centro ? `_${datos.centro.codigo}` : ''
    descargarCSV(`indicadores_rentabilidad${sufijo}_${datos.desde}_${datos.hasta}.csv`, ['Concepto', ...columnas, 'Total'], filas)
  }

  const encabezado = (
    <thead className="table-light">
      <tr>
        <th className="small text-muted text-uppercase">Concepto</th>
        {datos?.columnas.map((c) => (
          <EncabezadoUnidad key={c.id ?? 'sin-centro'} columna={c} irA={irA} />
        ))}
        <th className="text-end col-total" style={{ minWidth: '8.5rem' }}>
          Total
        </th>
      </tr>
    </thead>
  )

  const sinDatos = datos && datos.montos.every((m) => Number(m.total) === 0)
  const resultadoNeto = datos?.montos.find((m) => m.clave === 'resultado_neto')
  const participacion = datos?.participacion.find((p) => p.clave === 'resultado')

  return (
    <>
      <EncabezadoPagina
        titulo="Indicadores de rentabilidad"
        descripcion="Margen bruto, operativo, de contribución y neto por área, y la participación de cada unidad en el resultado."
        migas={[{ texto: 'Reportes' }, { texto: 'Indicadores de rentabilidad' }]}
      />
      <FiltrosReporte reporte={reporte} onExportar={exportar} conNivel={false} />
      <NavegacionUnidad datos={datos} irA={irA} />

      {error && <Alert variant="danger">{error}</Alert>}
      {cargando && <Spinner animation="border" />}

      {datos && !cargando && (
        <>
          <div className="encabezado-reporte">
            <strong>Indicadores de rentabilidad por área</strong>
            {datos.centro && ` · ${datos.centro.codigo} ${datos.centro.nombre}`} · del {formatoFecha(datos.desde)} al{' '}
            {formatoFecha(datos.hasta)}
          </div>
          {sinDatos ? (
            <EstadoVacio icono="bi-speedometer2">No hay ingresos ni gastos contabilizados en el rango para esta unidad.</EstadoVacio>
          ) : (
            <>
              <Card className="mb-3">
                <Card.Header className="fw-semibold">Márgenes (% sobre ingresos)</Card.Header>
                <div className="table-responsive">
                  <Table size="sm" className="tabla-matriz align-middle mb-0">
                    {encabezado}
                    <tbody>
                      {datos.indicadores.map((i) => (
                        <tr key={i.clave}>
                          <td>
                            <strong>{i.titulo}</strong>
                            <div className="small text-suave">sobre {i.base}</div>
                          </td>
                          {i.valores.map((v, k) => (
                            <td key={k} className="monto">
                              <Porcentaje valor={v} alertar />
                            </td>
                          ))}
                          <td className="monto col-total">
                            <Porcentaje valor={i.total} alertar />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </Card>

              <Row className="g-3 mb-3">
                <Col lg={5}>
                  <Card className="h-100">
                    <Card.Header className="fw-semibold">Participación en el resultado</Card.Header>
                    <Card.Body>
                      {!participacion.aplica ? (
                        <Alert variant="warning" className="small mb-0">
                          El resultado de la vista es cero o pérdida ({<Monto valor={resultadoNeto.total} alertar />}): la
                          participación porcentual no es interpretable.
                        </Alert>
                      ) : (
                        datos.columnas.map((c, k) => (
                          <div key={c.id ?? 'sin-centro'} className="mb-2">
                            <div className="d-flex justify-content-between small">
                              <span>
                                {c.codigo && <code className="me-1">{c.codigo}</code>}
                                {c.nombre}
                              </span>
                              <span className="monto">
                                <Porcentaje valor={participacion.valores[k]} alertar />
                              </span>
                            </div>
                            <BarraParticipacion valor={participacion.valores[k]} />
                          </div>
                        ))
                      )}
                    </Card.Body>
                  </Card>
                </Col>
                <Col lg={7}>
                  <Card className="h-100">
                    <Card.Header className="fw-semibold">Participación (%)</Card.Header>
                    <div className="table-responsive">
                      <Table size="sm" className="tabla-matriz align-middle mb-0">
                        <thead className="table-light">
                          <tr>
                            <th className="small text-muted text-uppercase">Unidad</th>
                            {datos.participacion.map((p) => (
                              <th key={p.clave} className="text-end">
                                {p.clave === 'resultado' ? 'En el resultado' : 'En los ingresos'}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {datos.columnas.map((c, k) => (
                            <tr key={c.id ?? 'sin-centro'}>
                              <td className="small">
                                {c.codigo && <code className="me-2">{c.codigo}</code>}
                                {c.nombre}
                              </td>
                              {datos.participacion.map((p) => (
                                <td key={p.clave} className="monto">
                                  <Porcentaje valor={p.valores[k]} alertar />
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>
                  </Card>
                </Col>
              </Row>

              <Card className="mb-3">
                <Card.Header className="fw-semibold">Base de cálculo</Card.Header>
                <div className="table-responsive">
                  <Table size="sm" className="tabla-matriz align-middle mb-0">
                    {encabezado}
                    <tbody>
                      {datos.montos.map((m) => (
                        <Fragment key={m.clave}>
                          {m.clave === 'margen_contribucion' && (
                            <tr>
                              <td colSpan={datos.columnas.length + 2} className="p-1" />
                            </tr>
                          )}
                          <tr className={RESULTADOS.has(m.clave) ? (m.clave === 'resultado_neto' ? 'fila-resultado' : 'fila-subtotal') : ''}>
                            <td className={RESULTADOS.has(m.clave) ? '' : 'ps-3 small'}>{m.titulo}</td>
                            {m.valores.map((v, k) => (
                              <td key={k} className="monto">
                                {v === null ? <span className="text-suave">n/a</span> : <Monto valor={v} alertar={RESULTADOS.has(m.clave)} />}
                              </td>
                            ))}
                            <td className="monto col-total">
                              <Monto valor={m.total} alertar={RESULTADOS.has(m.clave)} />
                            </td>
                          </tr>
                        </Fragment>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </Card>
            </>
          )}
          <div className="small text-suave mb-4 no-imprimir">
            <i className="bi bi-info-circle me-1" />
            Los rubros (de operación, costo de intermediación, no operacional) se configuran por cuenta en el Catálogo. Los gastos
            asignados por prorrateo se suman en el rubro de su cuenta (normalmente gastos de operación), por eso el resultado neto coincide con el costeo absorbente. El
            margen de contribución es el del enfoque de contribución y no se calcula para movimientos sin centro. La participación
            se mide sobre el total de la vista (la institución o la unidad elegida).
          </div>
        </>
      )}
    </>
  )
}
