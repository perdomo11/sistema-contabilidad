import { useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Container, Form, Row, Spinner, Table } from 'react-bootstrap'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, apiTodas } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import SelectorCuenta from '../components/SelectorCuenta'
import { aCentavos, centavosATexto, hoyISO } from '../formato'

let siguienteClave = 1
const lineaVacia = () => ({ clave: siguienteClave++, cuenta: null, centro: null, descripcion: '', debe: '', haber: '' })

/** Aplana el árbol del catálogo y deja solo cuentas de detalle activas. */
function cuentasImputables(arbol) {
  const resultado = []
  const recorrer = (nodos) =>
    nodos.forEach((n) => {
      if (n.acepta_movimientos && n.activa) {
        resultado.push({ id: n.id, codigo: n.codigo, nombre: n.nombre, exenta: n.exenta_centro_costo })
      }
      recorrer(n.hijos)
    })
  recorrer(arbol)
  return resultado
}

/** Aplana el árbol de centros y deja solo unidades de detalle (con su vigencia). */
function centrosImputables(arbol) {
  const resultado = []
  const recorrer = (nodos) =>
    nodos.forEach((n) => {
      if (n.acepta_movimientos) {
        resultado.push({ id: n.id, codigo: n.codigo, nombre: n.nombre, desde: n.vigente_desde, hasta: n.vigente_hasta })
      }
      recorrer(n.hijos)
    })
  recorrer(arbol)
  return resultado
}

/** Convierte la respuesta de error de la API en una lista de mensajes. */
async function erroresDe(resp) {
  const datos = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
  const etiquetas = { fecha: 'Fecha', concepto: 'Concepto', referencia: 'Referencia', lineas: 'Líneas', motivo: 'Motivo', proveedor: 'Proveedor' }
  return Object.entries(datos).flatMap(([campo, msgs]) => {
    if (campo === 'detail') return [String(msgs)]
    // Errores anidados por línea del serializer: [{cuenta: [...]}, {}]
    if (Array.isArray(msgs) && msgs.some((m) => m && typeof m === 'object')) {
      return msgs.flatMap((m, i) =>
        m && typeof m === 'object' ? Object.values(m).flat().map((t) => `Línea ${i + 1}: ${t}`) : [],
      )
    }
    return [].concat(msgs).map((m) => (campo === 'lineas' ? m : `${etiquetas[campo] || campo}: ${m}`))
  })
}

export default function AsientoEditor() {
  const { id } = useParams()
  const navegar = useNavigate()
  const [asientoId, setAsientoId] = useState(id ? Number(id) : null)
  const [cuentas, setCuentas] = useState(null)
  const [centros, setCentros] = useState(null)
  const [cargando, setCargando] = useState(Boolean(id))
  const [errores, setErrores] = useState([])
  const [guardando, setGuardando] = useState(false)

  const [fecha, setFecha] = useState(hoyISO())
  const [concepto, setConcepto] = useState('')
  const [referencia, setReferencia] = useState('')
  const [proveedor, setProveedor] = useState(null)
  const [proveedores, setProveedores] = useState(null)
  const [lineas, setLineas] = useState([lineaVacia(), lineaVacia()])
  // Centro que asignaría la regla vigente a cada cuenta: {idCuenta: {centro_codigo, centro_nombre, criterio} | null}
  const [sugerencias, setSugerencias] = useState({})

  useEffect(() => {
    api('/api/cuentas/arbol/').then(async (r) => setCuentas(r.ok ? cuentasImputables(await r.json()) : []))
    api('/api/centros-costo/arbol/').then(async (r) => setCentros(r.ok ? centrosImputables(await r.json()) : []))
    apiTodas('/api/proveedores/?activo=true').then((lista) =>
      setProveedores(lista.map((p) => ({ id: p.id, codigo: p.nit, nombre: p.nombre }))),
    )
  }, [])

  // Vista previa de la asignación por regla (T2.2): el servidor la aplica al guardar
  // en las líneas sin centro; aquí solo se muestra.
  const cuentasConCentro = [...new Set(lineas.filter((l) => l.cuenta && !l.cuenta.exenta).map((l) => l.cuenta.id))]
    .sort((a, b) => a - b)
    .join(',')
  useEffect(() => {
    if (!cuentasConCentro || !fecha) return setSugerencias({})
    let vigente = true
    const params = new URLSearchParams({ fecha, cuentas: cuentasConCentro, proveedor: proveedor?.id ?? '' })
    api(`/api/reglas-asignacion/resolver/?${params}`).then(async (r) => {
      if (vigente) setSugerencias(r.ok ? await r.json() : {})
    })
    return () => {
      vigente = false
    }
  }, [cuentasConCentro, fecha, proveedor])

  // Solo se ofrecen los centros vigentes en la fecha del asiento.
  const centrosVigentes = useMemo(
    () => (centros || []).filter((c) => c.desde <= fecha && (!c.hasta || c.hasta >= fecha)),
    [centros, fecha],
  )

  useEffect(() => {
    if (!id) return
    api(`/api/asientos/${id}/`).then(async (resp) => {
      if (!resp.ok) {
        setErrores(await erroresDe(resp))
        return setCargando(false)
      }
      const a = await resp.json()
      if (a.estado !== 'BORRADOR') return navegar(`/asientos/${a.id}`, { replace: true })
      setFecha(a.fecha)
      setConcepto(a.concepto)
      setReferencia(a.referencia)
      setProveedor(a.proveedor ? { id: a.proveedor, codigo: '', nombre: a.proveedor_nombre } : null)
      setLineas(
        a.lineas.map((l) => ({
          clave: siguienteClave++,
          cuenta: { id: l.cuenta, codigo: l.cuenta_codigo, nombre: l.cuenta_nombre, exenta: l.cuenta_exenta_centro_costo },
          // Un centro puesto por regla se deja vacío: al guardar se vuelve a resolver con la fecha y el proveedor.
          centro:
            l.centro_costo && l.asignacion !== 'REGLA'
              ? { id: l.centro_costo, codigo: l.centro_codigo, nombre: l.centro_nombre }
              : null,
          descripcion: l.descripcion,
          debe: Number(l.debe) ? l.debe : '',
          haber: Number(l.haber) ? l.haber : '',
        })),
      )
      setCargando(false)
    })
  }, [id, navegar])

  const totales = useMemo(() => {
    const suma = (campo) => lineas.reduce((t, l) => t + (aCentavos(l[campo]) || 0), 0)
    const debe = suma('debe')
    const haber = suma('haber')
    return { debe, haber, diferencia: debe - haber }
  }, [lineas])
  const cuadrado = totales.debe > 0 && totales.diferencia === 0

  const actualizarLinea = (clave, cambios) =>
    setLineas((ls) => ls.map((l) => (l.clave === clave ? { ...l, ...cambios } : l)))

  const montoValido = (v) => v === '' || !Number.isNaN(aCentavos(v))

  const cuerpo = () => ({
    fecha,
    concepto,
    referencia,
    proveedor: proveedor?.id ?? null,
    lineas: lineas
      .filter((l) => l.cuenta || l.debe || l.haber || l.descripcion)
      .map((l) => ({
        cuenta: l.cuenta?.id ?? null,
        centro_costo: l.cuenta?.exenta ? null : (l.centro?.id ?? null),
        descripcion: l.descripcion,
        debe: l.debe.replace(/,/g, '') || '0',
        haber: l.haber.replace(/,/g, '') || '0',
      })),
  })

  const guardar = async (contabilizar) => {
    setGuardando(true)
    setErrores([])
    const resp = await api(asientoId ? `/api/asientos/${asientoId}/` : '/api/asientos/', {
      method: asientoId ? 'PUT' : 'POST',
      body: cuerpo(),
    })
    if (!resp.ok) {
      setErrores(await erroresDe(resp))
      return setGuardando(false)
    }
    const guardado = await resp.json()
    setAsientoId(guardado.id)
    if (contabilizar) {
      const r = await api(`/api/asientos/${guardado.id}/contabilizar/`, { method: 'POST' })
      if (!r.ok) {
        // El borrador quedó guardado; se sigue editando con el error a la vista.
        setErrores(['El borrador se guardó, pero no se pudo contabilizar:', ...(await erroresDe(r))])
        return setGuardando(false)
      }
    }
    navegar(`/asientos/${guardado.id}`, { state: { aviso: contabilizar ? 'Asiento contabilizado.' : 'Borrador guardado.' } })
  }

  if (cargando || !cuentas || !centros || !proveedores) {
    return (
      <Container className="py-5 text-center">
        <Spinner animation="border" />
      </Container>
    )
  }

  return (
    <Container fluid className="px-0">
      <EncabezadoPagina
        titulo={asientoId ? 'Editar borrador' : 'Nuevo asiento'}
        descripcion="Puede guardar un borrador descuadrado; para contabilizar, los cargos deben igualar a los abonos."
        migas={[{ texto: 'Asientos', a: '/asientos' }, { texto: asientoId ? 'Editar borrador' : 'Nuevo' }]}
      >
        <Button as={Link} to={asientoId ? `/asientos/${asientoId}` : '/asientos'} variant="outline-secondary">
          <i className="bi bi-arrow-left me-1" /> Volver
        </Button>
      </EncabezadoPagina>

      {errores.length > 0 && (
        <Alert variant="danger">
          {errores.length === 1 ? (
            errores[0]
          ) : (
            <ul className="mb-0 ps-3">
              {errores.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
        </Alert>
      )}

      <Card className="mb-3 shadow-sm">
        <Card.Body>
          <Row className="g-3">
            <Col xs={12} md={3}>
              <Form.Label htmlFor="fecha" className="small text-muted mb-1">
                Fecha
              </Form.Label>
              <Form.Control id="fecha" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
            </Col>
            <Col xs={12} md={6}>
              <Form.Label htmlFor="concepto" className="small text-muted mb-1">
                Concepto
              </Form.Label>
              <Form.Control
                id="concepto"
                value={concepto}
                maxLength={300}
                onChange={(e) => setConcepto(e.target.value)}
                placeholder="Descripción de la operación"
              />
            </Col>
            <Col xs={12} md={3}>
              <Form.Label htmlFor="referencia" className="small text-muted mb-1">
                Referencia
              </Form.Label>
              <Form.Control
                id="referencia"
                value={referencia}
                maxLength={50}
                onChange={(e) => setReferencia(e.target.value)}
                placeholder="Factura, cheque…"
              />
            </Col>
            <Col xs={12} md={6}>
              <Form.Label htmlFor="proveedor" className="small text-muted mb-1">
                Proveedor <span className="text-suave">(opcional)</span>
              </Form.Label>
              <SelectorCuenta
                id="proveedor"
                cuentas={proveedores}
                valor={proveedor}
                onChange={setProveedor}
                placeholder="NIT o nombre del proveedor"
                permitirVacio
              />
              <Form.Text className="text-suave">
                Las reglas de asignación por proveedor completan el centro de costo de las líneas que lo dejen vacío.
              </Form.Text>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      <Card className="shadow-sm mb-3">
        <div className="table-responsive">
          <Table className="mb-0 align-middle" size="sm">
            <thead className="table-light">
              <tr className="small text-uppercase text-muted">
                <th style={{ width: '2.5rem' }}>#</th>
                <th style={{ minWidth: '17rem' }}>Cuenta</th>
                <th style={{ minWidth: '14rem' }}>Centro de costo</th>
                <th style={{ minWidth: '10rem' }}>Descripción</th>
                <th className="text-end" style={{ width: '10rem' }}>
                  Cargo
                </th>
                <th className="text-end" style={{ width: '10rem' }}>
                  Abono
                </th>
                <th style={{ width: '2.5rem' }} />
              </tr>
            </thead>
            <tbody>
              {lineas.map((l, i) => (
                <tr key={l.clave}>
                  <td className="text-muted small">{i + 1}</td>
                  <td>
                    <SelectorCuenta
                      id={`cuenta-${l.clave}`}
                      cuentas={cuentas}
                      valor={l.cuenta}
                      onChange={(cuenta) => actualizarLinea(l.clave, { cuenta })}
                    />
                  </td>
                  <td>
                    <SelectorCuenta
                      id={`centro-${l.clave}`}
                      cuentas={centrosVigentes}
                      valor={l.cuenta?.exenta ? null : l.centro}
                      onChange={(centro) => actualizarLinea(l.clave, { centro })}
                      placeholder={
                        l.cuenta?.exenta
                          ? 'No requiere (cuenta exenta)'
                          : sugerencias[l.cuenta?.id]
                            ? `Por regla: ${sugerencias[l.cuenta.id].centro_codigo} · ${sugerencias[l.cuenta.id].centro_nombre}`
                            : 'Centro de costo'
                      }
                      disabled={Boolean(l.cuenta?.exenta)}
                      permitirVacio
                    />
                    {!l.cuenta?.exenta && !l.centro && sugerencias[l.cuenta?.id] && (
                      <div className="small text-info-emphasis mt-1" title={`Regla por ${sugerencias[l.cuenta.id].criterio}`}>
                        <i className="bi bi-magic me-1" />
                        Por regla ({sugerencias[l.cuenta.id].criterio})
                      </div>
                    )}
                  </td>
                  <td>
                    <Form.Control
                      size="sm"
                      value={l.descripcion}
                      maxLength={200}
                      onChange={(e) => actualizarLinea(l.clave, { descripcion: e.target.value })}
                    />
                  </td>
                  <td>
                    <Form.Control
                      size="sm"
                      className="text-end font-monospace"
                      inputMode="decimal"
                      value={l.debe}
                      isInvalid={!montoValido(l.debe)}
                      onChange={(e) => actualizarLinea(l.clave, { debe: e.target.value, haber: e.target.value ? '' : l.haber })}
                    />
                  </td>
                  <td>
                    <Form.Control
                      size="sm"
                      className="text-end font-monospace"
                      inputMode="decimal"
                      value={l.haber}
                      isInvalid={!montoValido(l.haber)}
                      onChange={(e) => actualizarLinea(l.clave, { haber: e.target.value, debe: e.target.value ? '' : l.debe })}
                    />
                  </td>
                  <td className="text-end">
                    <Button
                      size="sm"
                      variant="link"
                      className="text-danger p-0"
                      title="Quitar línea"
                      aria-label={`Quitar línea ${i + 1}`}
                      disabled={lineas.length <= 1}
                      onClick={() => setLineas((ls) => ls.filter((x) => x.clave !== l.clave))}
                    >
                      ✕
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="table-light">
              <tr>
                <td colSpan={4}>
                  <Button size="sm" variant="outline-primary" onClick={() => setLineas((ls) => [...ls, lineaVacia()])}>
                    + Agregar línea
                  </Button>
                </td>
                <td className="text-end font-monospace fw-semibold">{centavosATexto(totales.debe)}</td>
                <td className="text-end font-monospace fw-semibold">{centavosATexto(totales.haber)}</td>
                <td />
              </tr>
              <tr>
                <td colSpan={4} className="text-end small text-muted">
                  Diferencia
                </td>
                <td colSpan={2} className="text-end">
                  {cuadrado ? (
                    <Badge bg="success">Cuadrado</Badge>
                  ) : (
                    <span className="font-monospace text-danger fw-semibold">
                      {centavosATexto(Math.abs(totales.diferencia))}
                      <span className="small ms-1">{totales.diferencia > 0 ? '(faltan abonos)' : totales.diferencia < 0 ? '(faltan cargos)' : ''}</span>
                    </span>
                  )}
                </td>
                <td />
              </tr>
            </tfoot>
          </Table>
        </div>
      </Card>

      <div className="d-flex flex-wrap justify-content-end gap-2 mb-4">
        <Button variant="outline-primary" disabled={guardando} onClick={() => guardar(false)}>
          Guardar borrador
        </Button>
        <Button disabled={guardando || !cuadrado} onClick={() => guardar(true)} title={cuadrado ? '' : 'El asiento debe estar cuadrado'}>
          {guardando && <Spinner animation="border" size="sm" className="me-2" />}
          Guardar y contabilizar
        </Button>
      </div>
    </Container>
  )
}
