import { Fragment, useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Row, Spinner, Table } from 'react-bootstrap'
import { useSearchParams } from 'react-router-dom'
import { api, mensajeError } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { AccionesReporte, CamposRango, rangoPorDefecto } from '../components/FiltroRango'
import { descargarCSV } from '../exportar'
import { formatoFecha, formatoMonto } from '../formato'

const COLOR_TIPO = { COSTO: 'secondary', INGRESO: 'success', UTILIDAD: 'primary', INVERSION: 'warning' }

/** Monto con signo: negativos entre paréntesis y en rojo si `alertar`. */
function Monto({ valor, alertar = false }) {
  const n = Number(valor)
  if (n === 0) return <span className="text-suave">–</span>
  const texto = n < 0 ? `(${formatoMonto(String(-n))})` : formatoMonto(valor)
  return <span className={alertar && n < 0 ? 'text-danger' : ''}>{texto}</span>
}

export default function EstadoResultados() {
  const [params, setParams] = useSearchParams()
  const [rango, setRango] = useState(() => ({
    ...rangoPorDefecto(),
    ...(params.get('desde') && { desde: params.get('desde') }),
    ...(params.get('hasta') && { hasta: params.get('hasta') }),
  }))
  const [nivel, setNivel] = useState(params.get('nivel_cuentas') || '2')
  const centro = params.get('centro') || ''
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const consultar = useCallback(async (filtros) => {
    setCargando(true)
    const q = new URLSearchParams({ desde: filtros.desde, hasta: filtros.hasta, nivel_cuentas: filtros.nivel })
    if (filtros.centro) q.set('centro', filtros.centro)
    const resp = await api(`/api/reportes/estado-resultados/?${q}`)
    setCargando(false)
    if (!resp.ok) {
      setDatos(null)
      return setError(await mensajeError(resp))
    }
    setError('')
    setDatos(await resp.json())
  }, [])

  // La consulta sigue a la URL (unidad elegida); el rango y el nivel se aplican al pulsar Consultar.
  useEffect(() => {
    consultar({ ...rango, nivel, centro })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centro, consultar])

  const irA = (idCentro) => {
    const p = { desde: rango.desde, hasta: rango.hasta, nivel_cuentas: nivel }
    if (idCentro) p.centro = idCentro
    setParams(p)
  }

  const enviar = (e) => {
    e.preventDefault()
    irA(centro)
    consultar({ ...rango, nivel, centro })
  }

  const exportar = () => {
    const columnas = datos.columnas.map((c) => (c.codigo ? `${c.codigo} ${c.nombre}` : c.nombre))
    const filas = []
    for (const s of datos.secciones) {
      filas.push([s.titulo.toUpperCase(), ...columnas.map(() => ''), ''])
      s.filas.forEach((f) => filas.push([`${f.cuenta.codigo} ${f.cuenta.nombre}`, ...f.valores, f.total]))
      filas.push([`Total ${s.titulo.toLowerCase()}`, ...s.valores, s.total])
      if (s.clave === 'directos') filas.push(['Resultado directo', ...datos.resultado_directo.valores, datos.resultado_directo.total])
    }
    filas.push(['Indirectos recibidos', ...datos.indirectos.recibidos.valores, datos.indirectos.recibidos.total])
    filas.push(['Indirectos distribuidos', ...datos.indirectos.distribuidos.valores, datos.indirectos.distribuidos.total])
    filas.push(['RESULTADO NETO (costeo absorbente)', ...datos.resultado.valores, datos.resultado.total])
    const sufijo = datos.centro ? `_${datos.centro.codigo}` : ''
    descargarCSV(`estado_resultados${sufijo}_${datos.desde}_${datos.hasta}.csv`, ['Concepto', ...columnas, 'Total'], filas)
  }

  const fila = (etiqueta, vector, clase = '', alertar = false, sangria = false) => (
    <tr className={clase}>
      <td className={sangria ? 'ps-4' : ''}>{etiqueta}</td>
      {vector.valores.map((v, i) => (
        <td key={i} className="monto">
          <Monto valor={v} alertar={alertar} />
        </td>
      ))}
      <td className="monto col-total">
        <Monto valor={vector.total} alertar={alertar} />
      </td>
    </tr>
  )

  const nColumnas = datos ? datos.columnas.length + 2 : 0
  const sinDatos =
    datos && datos.secciones.every((s) => s.filas.length === 0)

  return (
    <>
      <EncabezadoPagina
        titulo="Estado de resultados por centro"
        descripcion="Costeo absorbente: ingresos, costos directos y costos indirectos asignados por prorrateo. Cada columna consolida sus subunidades."
        migas={[{ texto: 'Reportes' }, { texto: 'Estado de resultados' }]}
      />

      <Card className="mb-3 no-imprimir">
        <Card.Body>
          <Form onSubmit={enviar}>
            <Row className="g-2 align-items-end">
              <CamposRango rango={rango} onChange={setRango} />
              <Col xs={6} md={2}>
                <Form.Label htmlFor="nivel-cuentas" className="small text-muted mb-1">
                  Detalle de cuentas
                </Form.Label>
                <Form.Select id="nivel-cuentas" size="sm" value={nivel} onChange={(e) => setNivel(e.target.value)}>
                  <option value="1">Nivel 1 (rubros)</option>
                  <option value="2">Nivel 2</option>
                  <option value="3">Nivel 3</option>
                  <option value="4">Nivel 4</option>
                </Form.Select>
              </Col>
              <AccionesReporte onExportar={exportar} deshabilitado={!datos} />
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {datos && (
        <nav className="d-flex flex-wrap align-items-center gap-1 small mb-2 no-imprimir" aria-label="Unidad">
          <i className="bi bi-diagram-3 text-suave me-1" />
          <Button variant="link" size="sm" className="p-0" disabled={!datos.centro} onClick={() => irA('')}>
            Toda la institución
          </Button>
          {datos.ruta.map((n, i) => (
            <Fragment key={n.id}>
              <i className="bi bi-chevron-right text-suave" style={{ fontSize: '0.65rem' }} />
              <Button variant="link" size="sm" className="p-0" disabled={i === datos.ruta.length - 1} onClick={() => irA(n.id)}>
                {n.codigo} {n.nombre}
              </Button>
            </Fragment>
          ))}
        </nav>
      )}

      {error && <Alert variant="danger">{error}</Alert>}
      {cargando && <Spinner animation="border" />}

      {datos && !cargando && (
        <>
          <div className="encabezado-reporte">
            <strong>Estado de resultados por centro (costeo absorbente)</strong>
            {datos.centro && ` · ${datos.centro.codigo} ${datos.centro.nombre}`} · del {formatoFecha(datos.desde)} al{' '}
            {formatoFecha(datos.hasta)}
          </div>
          {sinDatos ? (
            <EstadoVacio icono="bi-graph-up">No hay ingresos ni gastos contabilizados en el rango para esta unidad.</EstadoVacio>
          ) : (
            <Card className="mb-3">
              <div className="table-responsive">
                <Table size="sm" className="tabla-matriz align-middle mb-0">
                  <thead className="table-light">
                    <tr>
                      <th className="small text-muted text-uppercase">Concepto</th>
                      {datos.columnas.map((c) => (
                        <th key={c.id ?? 'sin'} className="text-end" style={{ minWidth: '8.5rem' }}>
                          {c.tiene_subunidades ? (
                            <Button
                              variant="link"
                              size="sm"
                              className="p-0 text-end text-decoration-none"
                              title="Ver subunidades"
                              onClick={() => irA(c.id)}
                            >
                              <code>{c.codigo}</code> <i className="bi bi-box-arrow-in-down-right" />
                            </Button>
                          ) : (
                            <code>{c.codigo}</code>
                          )}
                          <div className="small fw-normal">{c.nombre}</div>
                          {c.tipo && (
                            <Badge bg={`${COLOR_TIPO[c.tipo]}-subtle`} text={`${COLOR_TIPO[c.tipo]}-emphasis`} className="fw-normal">
                              {c.tipo_display}
                            </Badge>
                          )}
                          {!c.vigente && <div className="small text-suave fw-normal">no vigente</div>}
                        </th>
                      ))}
                      <th className="text-end col-total" style={{ minWidth: '8.5rem' }}>
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.secciones.map((s) => (
                      <Fragment key={s.clave}>
                        <tr className="fila-seccion">
                          <td colSpan={nColumnas}>{s.titulo}</td>
                        </tr>
                        {s.filas.map((f) => (
                          <Fragment key={f.cuenta.id}>
                            {fila(
                              <>
                                <code className="me-2">{f.cuenta.codigo}</code>
                                {f.cuenta.nombre}
                              </>,
                              f,
                              '',
                              false,
                              true,
                            )}
                          </Fragment>
                        ))}
                        {s.filas.length === 0 && (
                          <tr>
                            <td colSpan={nColumnas} className="ps-4 small text-suave">
                              {s.clave === 'indirectos' ? 'Sin prorrateos ejecutados en el rango.' : 'Sin movimientos.'}
                            </td>
                          </tr>
                        )}
                        {fila(`Total ${s.titulo.toLowerCase()}`, s, 'fila-subtotal')}
                        {s.clave === 'indirectos' && (
                          <>
                            {fila(<span className="small text-suave fst-italic">Recibidos de otras unidades</span>, datos.indirectos.recibidos, 'small', false, true)}
                            {fila(<span className="small text-suave fst-italic">Distribuidos a otras unidades</span>, datos.indirectos.distribuidos, 'small', false, true)}
                          </>
                        )}
                        {s.clave === 'directos' && fila('Resultado directo (antes de indirectos)', datos.resultado_directo, 'fila-subtotal', true)}
                      </Fragment>
                    ))}
                  </tbody>
                  <tfoot className="table-light">
                    {fila('Resultado neto (costeo absorbente)', datos.resultado, 'fila-resultado', true)}
                  </tfoot>
                </Table>
              </div>
            </Card>
          )}
          <div className="small text-suave mb-4 no-imprimir">
            <i className="bi bi-info-circle me-1" />
            Los importes negativos aparecen entre paréntesis. En los centros de servicio, los costos indirectos son negativos: es
            lo que distribuyeron a otras unidades. El total de la institución coincide con el resultado de la balanza.
            {datos.columnas.some((c) => c.id === null) &&
              ' La columna "Sin centro" reúne movimientos registrados antes de exigir centro de costo.'}
          </div>
        </>
      )}
    </>
  )
}
