import { Fragment, useCallback, useEffect, useState } from 'react'
import { Badge, Button, Card, Col, Form, Row } from 'react-bootstrap'
import { useSearchParams } from 'react-router-dom'
import { api, mensajeError } from '../../api'
import { formatoMonto } from '../../formato'
import { AccionesReporte, CamposRango, rangoPorDefecto } from '../FiltroRango'

export const COLOR_TIPO = { COSTO: 'secondary', INGRESO: 'success', UTILIDAD: 'primary', INVERSION: 'warning' }

/**
 * Estado compartido de los reportes segmentados: rango, nivel de cuentas y unidad elegida (en la URL).
 * La consulta sigue a la unidad; el rango y el nivel se aplican al pulsar Consultar.
 */
export function useReporteSegmentado(endpoint) {
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

  const consultar = useCallback(
    async (filtros) => {
      setCargando(true)
      const q = new URLSearchParams({ desde: filtros.desde, hasta: filtros.hasta, nivel_cuentas: filtros.nivel })
      if (filtros.centro) q.set('centro', filtros.centro)
      const resp = await api(`${endpoint}?${q}`)
      setCargando(false)
      if (!resp.ok) {
        setDatos(null)
        return setError(await mensajeError(resp))
      }
      setError('')
      setDatos(await resp.json())
    },
    [endpoint],
  )

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

  return { rango, setRango, nivel, setNivel, centro, datos, error, cargando, irA, enviar }
}

/** Tarjeta de filtros: rango, detalle de cuentas (opcional) y acciones. */
export function FiltrosReporte({ reporte, onExportar, conNivel = true }) {
  const { rango, setRango, nivel, setNivel, datos, enviar } = reporte
  return (
    <Card className="mb-3 no-imprimir">
      <Card.Body>
        <Form onSubmit={enviar}>
          <Row className="g-2 align-items-end">
            <CamposRango rango={rango} onChange={setRango} />
            {conNivel && (
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
            )}
            <AccionesReporte onExportar={onExportar} deshabilitado={!datos} />
          </Row>
        </Form>
      </Card.Body>
    </Card>
  )
}

/** Migas de la unidad consultada, para subir en la jerarquía. */
export function NavegacionUnidad({ datos, irA }) {
  if (!datos) return null
  return (
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
  )
}

/** Encabezado de columna de una unidad; si tiene subunidades, permite bajar a ellas. */
export function EncabezadoUnidad({ columna: c, irA, alinear = 'text-end' }) {
  return (
    <th className={alinear} style={{ minWidth: '8.5rem' }}>
      {c.tiene_subunidades ? (
        <Button variant="link" size="sm" className="p-0 text-decoration-none" title="Ver subunidades" onClick={() => irA(c.id)}>
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
  )
}

/** Monto con signo: negativos entre paréntesis (y en rojo si `alertar`); cero como guion. */
export function Monto({ valor, alertar = false }) {
  const n = Number(valor)
  if (n === 0) return <span className="text-suave">–</span>
  const texto = n < 0 ? `(${formatoMonto(String(-n))})` : formatoMonto(valor)
  return <span className={alertar && n < 0 ? 'text-danger' : ''}>{texto}</span>
}

/** Porcentaje "12.50" → "12.50 %"; null → guion. */
export function Porcentaje({ valor, alertar = false }) {
  if (valor === null || valor === undefined) return <span className="text-suave">–</span>
  const n = Number(valor)
  const texto = `${n.toLocaleString('es-SV', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %`
  return <span className={alertar && n < 0 ? 'text-danger' : ''}>{texto}</span>
}

/** Nombre de columna para CSV. */
export const nombreColumna = (c) => (c.codigo ? `${c.codigo} ${c.nombre}` : c.nombre)
