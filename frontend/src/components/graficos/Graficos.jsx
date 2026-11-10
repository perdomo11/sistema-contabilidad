/**
 * Gráficos SVG del sistema (T5.4), sin dependencias. Siguen la guía de visualización:
 * marcas finas (línea 2px, barras ≤ 24px con extremo redondeado de 4px y base recta), cuadrícula de
 * líneas finas sólidas, un solo eje, color por función (tokens `--viz-*` en estilos.css), etiquetas
 * directas selectivas, tooltip al pasar el cursor o con el foco del teclado, y el texto siempre en
 * tonos de texto (nunca del color de la serie). La vista de tabla la ofrece `TarjetaGrafico`.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Card, Table } from 'react-bootstrap'
import { formatoMonto } from '../../formato'

const ALTO_BARRA = 24
const RADIO = 4

/** Ancho disponible del contenedor (se ajusta al redimensionar). */
function useAncho() {
  const ref = useRef(null)
  const [ancho, setAncho] = useState(0)
  useEffect(() => {
    if (!ref.current) return undefined
    const obs = new ResizeObserver(([e]) => setAncho(Math.floor(e.contentRect.width)))
    obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])
  return [ref, ancho]
}

/** 12345 → "12K"; ejes con cifras redondas y un solo estilo por eje. */
export function compacto(n, usarK) {
  const v = Number(n)
  if (v === 0) return '0'
  if (usarK) {
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toLocaleString('es-SV', { maximumFractionDigits: 1 })}M`
    return `${(v / 1e3).toLocaleString('es-SV', { maximumFractionDigits: 1 })}K`
  }
  return v.toLocaleString('es-SV', { maximumFractionDigits: 0 })
}

/** Marcas de eje "bonitas" que cubren [min, max]. */
function marcas(min, max, cantidad = 4) {
  if (min === max) max = min + 1
  const paso0 = (max - min) / cantidad
  const mag = 10 ** Math.floor(Math.log10(paso0))
  const paso = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= paso0)
  const desde = Math.floor(min / paso) * paso
  const hasta = Math.ceil(max / paso) * paso
  const lista = []
  for (let v = desde; v <= hasta + paso / 2; v += paso) lista.push(Math.round(v * 100) / 100)
  return lista
}

/** Barra vertical con extremo de datos redondeado (arriba si es positiva) y base recta. */
function rutaColumna(x, y0, y1, w) {
  const alto = Math.abs(y0 - y1)
  const r = Math.min(RADIO, alto, w / 2)
  if (alto === 0) return ''
  return y1 < y0
    ? `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`
    : `M${x},${y0}V${y1 - r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 - r}V${y0}Z`
}

/** Barra horizontal desde la base (izquierda) con extremo derecho redondeado. */
function rutaBarra(x0, x1, y, h) {
  const largo = x1 - x0
  if (largo <= 0) return ''
  const r = Math.min(RADIO, largo, h / 2)
  return `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - r},${y + h}H${x0}Z`
}

function Tooltip({ estado }) {
  if (!estado) return null
  return (
    <div className="grafico-tooltip" style={{ left: estado.x, top: estado.y, transform: estado.alinear }}>
      {estado.titulo && <div className="text-muted mb-1">{estado.titulo}</div>}
      {estado.filas.map((f) => (
        <div key={f.nombre}>
          {f.color && <span className="clave" style={{ background: f.color }} />}
          <span className="valor">{f.valor}</span> <span className="text-muted">{f.nombre}</span>
        </div>
      ))}
    </div>
  )
}

/** Tarjeta con título, alternancia gráfico/tabla y leyenda opcional. */
export function TarjetaGrafico({ titulo, subtitulo, leyenda, columnas, filas, children, accion }) {
  const [tabla, setTabla] = useState(false)
  return (
    <Card className="h-100">
      <Card.Header className="d-flex flex-wrap align-items-center gap-2">
        <div className="me-auto">
          <div className="fw-semibold">{titulo}</div>
          {subtitulo && <div className="small text-suave">{subtitulo}</div>}
        </div>
        {accion}
        <Button size="sm" variant="outline-secondary" className="no-imprimir" onClick={() => setTabla(!tabla)} aria-pressed={tabla}>
          <i className={`bi ${tabla ? 'bi-graph-up' : 'bi-table'} me-1`} />
          {tabla ? 'Gráfico' : 'Tabla'}
        </Button>
      </Card.Header>
      <Card.Body>
        {leyenda && !tabla && (
          <div className="grafico-leyenda mb-2">
            {leyenda.map((l) => (
              <span key={l.nombre}>
                <span className="muestra" style={{ background: l.color }} />
                {l.nombre}
              </span>
            ))}
          </div>
        )}
        {tabla ? (
          <Table size="sm" className="mb-0">
            <thead className="table-light">
              <tr>
                {columnas.map((c, i) => (
                  <th key={c} className={i ? 'text-end' : ''}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filas.map((f, i) => (
                <tr key={i} className="small">
                  {f.map((v, j) => (
                    <td key={j} className={j ? 'monto' : ''}>
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          children
        )}
      </Card.Body>
    </Card>
  )
}

// =============================================================================
// Línea (una serie) con líneas de referencia
// =============================================================================

/**
 * puntos: [{etiqueta, valor, detalle: [{nombre, valor}], estado: 'DEFICIT' | 'BAJO_MINIMO' | 'OK'}]
 * referencias: [{valor, nombre, tipo: 'base' | 'advertencia'}]
 */
export function GraficoLinea({ puntos, referencias = [], alto = 240, nombreSerie }) {
  const [ref, ancho] = useAncho()
  const [hover, setHover] = useState(null)
  const m = { top: 12, right: 64, bottom: 26, left: 52 }
  const w = Math.max(0, ancho - m.left - m.right)
  const h = alto - m.top - m.bottom
  const valores = [...puntos.map((p) => p.valor), ...referencias.map((r) => r.valor)]
  const ticks = marcas(Math.min(0, ...valores), Math.max(0, ...valores))
  const [yMin, yMax] = [ticks[0], ticks[ticks.length - 1]]
  const usarK = Math.max(Math.abs(yMin), Math.abs(yMax)) >= 10000
  const x = (i) => (puntos.length > 1 ? (i * w) / (puntos.length - 1) : w / 2)
  const y = (v) => h - ((v - yMin) / (yMax - yMin)) * h
  const ruta = puntos.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.valor)}`).join('')

  const mostrar = useCallback(
    (i) => {
      const p = puntos[i]
      setHover({
        i,
        x: m.left + x(i),
        y: m.top + Math.min(y(p.valor), h - 60),
        alinear: x(i) > w * 0.65 ? 'translate(calc(-100% - 12px), -50%)' : 'translate(12px, -50%)',
        titulo: p.etiqueta,
        filas: [{ nombre: nombreSerie, valor: formatoMonto(String(p.valor)), color: 'var(--viz-serie-1)' }, ...(p.detalle || [])],
      })
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [puntos, w, h, yMin, yMax],
  )

  const alMover = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - rect.left - m.left
    const i = Math.max(0, Math.min(puntos.length - 1, Math.round((px / w) * (puntos.length - 1))))
    mostrar(i)
  }

  const ultimo = puntos[puntos.length - 1]
  return (
    <div className="grafico" ref={ref}>
      {ancho > 0 && (
        <svg width={ancho} height={alto} role="img" aria-label={`${nombreSerie}: ${puntos.map((p) => `${p.etiqueta} ${p.valor}`).join('; ')}`}>
          <g transform={`translate(${m.left},${m.top})`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={0} x2={w} y1={y(t)} y2={y(t)} stroke={t === 0 ? 'var(--viz-base)' : 'var(--viz-grid)'} strokeWidth={1} />
                <text x={-8} y={y(t)} dy="0.32em" textAnchor="end">
                  {compacto(t, usarK)}
                </text>
              </g>
            ))}
            {referencias
              .filter((r) => r.tipo === 'advertencia' && r.valor > 0)
              .map((r) => (
                <g key={r.nombre}>
                  <line x1={0} x2={w} y1={y(r.valor)} y2={y(r.valor)} stroke="var(--viz-advertencia)" strokeWidth={1.5} />
                  <text x={w + 6} y={y(r.valor)} dy="0.32em">
                    {r.nombre}
                  </text>
                </g>
              ))}
            {puntos.map((p, i) => {
              // Etiquetas espaciadas; se omite la penúltima si quedaría encima de la última.
              const paso = Math.ceil(puntos.length / 7)
              const visible = i === puntos.length - 1 || (i % paso === 0 && puntos.length - 1 - i >= paso)
              return visible ? (
                <text key={`x${i}`} x={x(i)} y={h + 18} textAnchor="middle">
                  {p.etiquetaCorta || p.etiqueta}
                </text>
              ) : null
            })}
            <path d={ruta} fill="none" stroke="var(--viz-serie-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {/* Marcadores solo donde hay estado (déficit o bajo mínimo) y al final; anillo del color del fondo. */}
            {puntos.map((p, i) =>
              p.estado && p.estado !== 'OK' ? (
                <circle
                  key={`m${i}`}
                  cx={x(i)}
                  cy={y(p.valor)}
                  r={4.5}
                  fill={p.estado === 'DEFICIT' ? 'var(--viz-critico)' : 'var(--viz-advertencia)'}
                  stroke="#fff"
                  strokeWidth={2}
                />
              ) : null,
            )}
            <circle cx={x(puntos.length - 1)} cy={y(ultimo.valor)} r={4} fill="var(--viz-serie-1)" stroke="#fff" strokeWidth={2} />
            <text className="etiqueta-valor" x={x(puntos.length - 1) + 8} y={y(ultimo.valor)} dy="0.32em">
              {compacto(ultimo.valor, Math.abs(ultimo.valor) >= 10000)}
            </text>
            {hover && <line x1={x(hover.i)} x2={x(hover.i)} y1={0} y2={h} stroke="var(--viz-base)" strokeWidth={1} />}
            {/* Capa de captura: el cursor solo tiene que acercarse a la fecha. */}
            <rect
              x={0}
              y={0}
              width={w}
              height={h}
              fill="transparent"
              tabIndex={0}
              aria-label="Recorrer los puntos con las flechas"
              onPointerMove={alMover}
              onPointerLeave={() => setHover(null)}
              onBlur={() => setHover(null)}
              onFocus={() => mostrar(hover?.i ?? 0)}
              onKeyDown={(e) => {
                if (e.key === 'ArrowRight') mostrar(Math.min(puntos.length - 1, (hover?.i ?? -1) + 1))
                if (e.key === 'ArrowLeft') mostrar(Math.max(0, (hover?.i ?? 1) - 1))
              }}
            />
          </g>
        </svg>
      )}
      <Tooltip estado={hover} />
    </div>
  )
}

// =============================================================================
// Columnas agrupadas (≤ 4 series)
// =============================================================================

/** categorias: [{etiqueta, valores: [n por serie]}]; series: [{nombre, color}] */
export function GraficoColumnas({ categorias, series, alto = 220 }) {
  const [ref, ancho] = useAncho()
  const [hover, setHover] = useState(null)
  const m = { top: 16, right: 8, bottom: 26, left: 52 }
  const w = Math.max(0, ancho - m.left - m.right)
  const h = alto - m.top - m.bottom
  const ticks = marcas(0, Math.max(1, ...categorias.flatMap((c) => c.valores)))
  const yMax = ticks[ticks.length - 1]
  const usarK = yMax >= 10000
  const banda = categorias.length ? w / categorias.length : 0
  const barra = Math.max(4, Math.min(ALTO_BARRA, (banda * 0.6 - 2 * (series.length - 1)) / series.length))
  const grupo = barra * series.length + 2 * (series.length - 1)
  const y = (v) => h - (v / yMax) * h

  const mostrar = (ci, si) => {
    const c = categorias[ci]
    const cx = m.left + ci * banda + banda / 2
    setHover({
      x: cx,
      y: m.top + y(c.valores[si]) - 8,
      alinear: 'translate(-50%, -100%)',
      titulo: c.etiqueta,
      filas: series.map((s, i) => ({ nombre: s.nombre, valor: formatoMonto(String(c.valores[i])), color: s.color })),
    })
  }

  return (
    <div className="grafico" ref={ref}>
      {ancho > 0 && (
        <svg width={ancho} height={alto} role="img" aria-label={series.map((s) => s.nombre).join(' y ')}>
          <g transform={`translate(${m.left},${m.top})`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={0} x2={w} y1={y(t)} y2={y(t)} stroke={t === 0 ? 'var(--viz-base)' : 'var(--viz-grid)'} strokeWidth={1} />
                <text x={-8} y={y(t)} dy="0.32em" textAnchor="end">
                  {compacto(t, usarK)}
                </text>
              </g>
            ))}
            {categorias.map((c, ci) => {
              const x0 = ci * banda + (banda - grupo) / 2
              return (
                <g key={c.etiqueta}>
                  {/* Área de captura más grande que la marca: toda la banda. */}
                  <rect
                    x={ci * banda}
                    y={0}
                    width={banda}
                    height={h}
                    fill="transparent"
                    onPointerEnter={() => mostrar(ci, 0)}
                    onPointerLeave={() => setHover(null)}
                    style={{ pointerEvents: 'all' }}
                  />
                  {series.map((s, si) => (
                    <path
                      key={s.nombre}
                      className="marca"
                      d={rutaColumna(x0 + si * (barra + 2), y(0), y(c.valores[si]), barra)}
                      fill={s.color}
                      tabIndex={0}
                      aria-label={`${c.etiqueta}, ${s.nombre}: ${formatoMonto(String(c.valores[si]))}`}
                      onPointerEnter={() => mostrar(ci, si)}
                      onPointerLeave={() => setHover(null)}
                      onFocus={() => mostrar(ci, si)}
                      onBlur={() => setHover(null)}
                    />
                  ))}
                  <text x={ci * banda + banda / 2} y={h + 18} textAnchor="middle">
                    {c.etiqueta}
                  </text>
                </g>
              )
            })}
          </g>
        </svg>
      )}
      <Tooltip estado={hover} />
    </div>
  )
}

// =============================================================================
// Barras horizontales (una serie), con el valor en la punta
// =============================================================================

/** items: [{etiqueta, valor}] — todos los valores quedan rotulados, así que no requiere tooltip. */
export function GraficoBarras({ items, color = 'var(--viz-serie-1)', anchoEtiqueta = 96 }) {
  const [ref, ancho] = useAncho()
  const paso = 34
  const alto = items.length * paso
  const maximo = Math.max(1, ...items.map((i) => i.valor))
  const espacioValor = 84
  const w = Math.max(0, ancho - anchoEtiqueta - espacioValor)
  return (
    <div className="grafico" ref={ref}>
      {ancho > 0 && (
        <svg width={ancho} height={alto} role="img" aria-label={items.map((i) => `${i.etiqueta}: ${formatoMonto(String(i.valor))}`).join('; ')}>
          <line x1={anchoEtiqueta} x2={anchoEtiqueta} y1={0} y2={alto} stroke="var(--viz-base)" strokeWidth={1} />
          {items.map((it, k) => {
            const largo = (it.valor / maximo) * w
            const yb = k * paso + (paso - 16) / 2
            return (
              <g key={it.etiqueta}>
                <text x={anchoEtiqueta - 8} y={yb + 8} dy="0.32em" textAnchor="end" style={{ fill: 'var(--viz-texto)' }}>
                  {it.etiqueta}
                </text>
                <path d={rutaBarra(anchoEtiqueta, anchoEtiqueta + largo, yb, 16)} fill={color}>
                  <title>{`${it.etiqueta}: ${formatoMonto(String(it.valor))}`}</title>
                </path>
                <text className="etiqueta-valor" x={anchoEtiqueta + largo + 6} y={yb + 8} dy="0.32em">
                  {it.valor ? formatoMonto(String(it.valor)) : '–'}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}
