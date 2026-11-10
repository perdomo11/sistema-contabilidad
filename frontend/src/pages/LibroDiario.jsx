import { Fragment, useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Card, Container, Form, Pagination, Row, Spinner, Table } from 'react-bootstrap'
import { Link } from 'react-router-dom'
import { api, mensajeError } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import { AccionesReporte, CamposRango, rangoPorDefecto } from '../components/FiltroRango'
import { descargarCSV } from '../exportar'
import { formatoFecha, formatoMonto } from '../formato'

const TAMANO_PAGINA = 50

export default function LibroDiario() {
  const [rango, setRango] = useState(rangoPorDefecto)
  const [consultado, setConsultado] = useState(rangoPorDefecto)
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [exportando, setExportando] = useState(false)

  const cargar = useCallback(async () => {
    const resp = await api(`/api/libros/diario/?${new URLSearchParams({ ...consultado, page: pagina })}`)
    if (!resp.ok) {
      setDatos(null)
      return setError(await mensajeError(resp))
    }
    setError('')
    setDatos(await resp.json())
  }, [consultado, pagina])

  useEffect(() => {
    cargar()
  }, [cargar])

  // El CSV incluye todo el rango, no solo la página visible.
  const exportar = async () => {
    setExportando(true)
    const filas = []
    let url = `/api/libros/diario/?${new URLSearchParams(consultado)}`
    while (url) {
      const resp = await api(url)
      if (!resp.ok) break
      const p = await resp.json()
      for (const a of p.results) {
        for (const l of a.lineas) {
          filas.push([formatoFecha(a.fecha), a.codigo, a.concepto, a.referencia, l.cuenta_codigo, l.cuenta_nombre, l.descripcion, l.debe, l.haber])
        }
      }
      url = p.next ? p.next.replace(/^https?:\/\/[^/]+/, '') : null
    }
    filas.push(['', '', 'TOTALES', '', '', '', '', datos.totales.debe, datos.totales.haber])
    descargarCSV(
      `diario_${consultado.desde}_${consultado.hasta}.csv`,
      ['Fecha', 'Asiento', 'Concepto', 'Referencia', 'Código', 'Cuenta', 'Descripción', 'Cargo', 'Abono'],
      filas,
    )
    setExportando(false)
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.count / TAMANO_PAGINA)) : 1

  return (
    <Container fluid className="px-0">
      <EncabezadoPagina
        titulo="Libro diario"
        descripcion="Asientos contabilizados en orden cronológico."
        migas={[{ texto: 'Libros' }, { texto: 'Libro diario' }]}
      />

      <Card className="mb-3 shadow-sm no-imprimir">
        <Card.Body>
          <Form
            onSubmit={(e) => {
              e.preventDefault()
              setPagina(1)
              setConsultado(rango)
            }}
          >
            <Row className="g-2 align-items-end">
              <CamposRango rango={rango} onChange={setRango} />
              <AccionesReporte onExportar={exportar} deshabilitado={!datos || exportando} />
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {error && <Alert variant="danger">{error}</Alert>}
      {!datos && !error && <Spinner animation="border" />}

      {datos && (
        <>
          <div className="encabezado-reporte">
            <strong>Libro diario</strong> del {formatoFecha(consultado.desde)} al {formatoFecha(consultado.hasta)}
          </div>
          <div className="d-flex justify-content-between align-items-center small text-muted mb-2">
            <span>
              {datos.count} asiento(s) del {formatoFecha(consultado.desde)} al {formatoFecha(consultado.hasta)}
            </span>
            <span>
              Total del rango: cargos <span className="monto">{formatoMonto(datos.totales.debe)}</span> · abonos{' '}
              <span className="monto">{formatoMonto(datos.totales.haber)}</span>
            </span>
          </div>
          <Card className="shadow-sm mb-3">
            <div className="table-responsive">
              <Table size="sm" className="mb-0 align-middle">
                <thead className="table-light">
                  <tr className="small text-muted text-uppercase">
                    <th style={{ width: '7rem' }}>Fecha</th>
                    <th>Cuenta</th>
                    <th>Descripción</th>
                    <th className="text-end">Cargo</th>
                    <th className="text-end">Abono</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.results.map((a) => (
                    <Fragment key={a.id}>
                      <tr className="table-group-divider border-top">
                        <td className="text-nowrap fw-semibold">{formatoFecha(a.fecha)}</td>
                        <td colSpan={4} className="fw-semibold">
                          <Link to={`/asientos/${a.id}`}>
                            <code>{a.codigo}</code>
                          </Link>{' '}
                          {a.concepto}
                          {a.referencia && <span className="text-muted small ms-2">Ref. {a.referencia}</span>}
                          {a.tipo === 'REVERSION' && (
                            <Badge bg="info" text="dark" className="ms-2">
                              Reversión
                            </Badge>
                          )}
                        </td>
                      </tr>
                      {a.lineas.map((l) => (
                        <tr key={l.id}>
                          <td />
                          <td className={Number(l.haber) ? 'ps-4' : ''}>
                            <code className="me-2">{l.cuenta_codigo}</code>
                            {l.cuenta_nombre}
                          </td>
                          <td className="small text-muted">{l.descripcion}</td>
                          <td className="monto">{formatoMonto(l.debe, { vacioSiCero: true })}</td>
                          <td className="monto">{formatoMonto(l.haber, { vacioSiCero: true })}</td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                  {datos.results.length === 0 && (
                    <tr>
                      <td colSpan={5} className="text-center text-muted py-4">
                        No hay asientos contabilizados en el rango.
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot className="table-light">
                  <tr className="fw-bold">
                    <td colSpan={3}>Totales del rango</td>
                    <td className="monto">{formatoMonto(datos.totales.debe)}</td>
                    <td className="monto">{formatoMonto(datos.totales.haber)}</td>
                  </tr>
                </tfoot>
              </Table>
            </div>
          </Card>
          {totalPaginas > 1 && (
            <Pagination size="sm" className="no-imprimir">
              <Pagination.Prev disabled={pagina === 1} onClick={() => setPagina(pagina - 1)} />
              <Pagination.Item active>
                {pagina} / {totalPaginas}
              </Pagination.Item>
              <Pagination.Next disabled={pagina === totalPaginas} onClick={() => setPagina(pagina + 1)} />
            </Pagination>
          )}
        </>
      )}
    </Container>
  )
}
