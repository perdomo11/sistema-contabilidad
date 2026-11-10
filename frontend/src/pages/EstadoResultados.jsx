import { Fragment } from 'react'
import { Alert, Card, Spinner, Table } from 'react-bootstrap'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import {
  EncabezadoUnidad,
  FiltrosReporte,
  Monto,
  NavegacionUnidad,
  nombreColumna,
  useReporteSegmentado,
} from '../components/reportes/ReporteSegmentado'
import { descargarCSV } from '../exportar'
import { formatoFecha } from '../formato'

export default function EstadoResultados() {
  const reporte = useReporteSegmentado('/api/reportes/estado-resultados/')
  const { datos, error, cargando, irA } = reporte

  const exportar = () => {
    const columnas = datos.columnas.map(nombreColumna)
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
  const sinDatos = datos && datos.secciones.every((s) => s.filas.length === 0)

  return (
    <>
      <EncabezadoPagina
        titulo="Estado de resultados por centro"
        descripcion="Costeo absorbente: ingresos, costos directos y costos indirectos asignados por prorrateo. Cada columna consolida sus subunidades."
        migas={[{ texto: 'Reportes' }, { texto: 'Estado de resultados' }]}
      />
      <FiltrosReporte reporte={reporte} onExportar={exportar} />
      <NavegacionUnidad datos={datos} irA={irA} />

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
                        <EncabezadoUnidad key={c.id ?? 'sin'} columna={c} irA={irA} />
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
