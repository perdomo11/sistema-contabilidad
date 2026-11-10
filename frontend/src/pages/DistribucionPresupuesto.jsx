import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, ProgressBar, Row, Spinner, Table } from 'react-bootstrap'
import { useSearchParams } from 'react-router-dom'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import SelectorCuenta from '../components/SelectorCuenta'
import { Monto } from '../components/reportes/ReporteSegmentado'
import { aCentavos, centavosATexto, formatoMonto } from '../formato'

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const COLOR_ESTADO = { BORRADOR: 'warning', APROBADO: 'success', CERRADO: 'secondary' }

const fechaHora = (iso) => (iso ? new Date(iso).toLocaleString('es-SV', { dateStyle: 'short', timeStyle: 'short' }) : '')
const centavos = (v) => {
  const c = aCentavos(v)
  return Number.isNaN(c) ? 0 : c
}
const aTextoAPI = (c) => (c / 100).toFixed(2)

/** Aplana un árbol ({hijos}) aplicando un filtro. */
function aplanar(arbol, incluir) {
  const lista = []
  const recorrer = (nodos) =>
    nodos.forEach((n) => {
      if (incluir(n)) lista.push(n)
      recorrer(n.hijos)
    })
  recorrer(arbol)
  return lista
}

const vigenteEnAnio = (c, anio) => c.vigente_desde <= `${anio}-12-31` && (!c.vigente_hasta || c.vigente_hasta >= `${anio}-01-01`)

/** Errores de la API → { campo: 'texto' } (las listas se unen). */
async function erroresDe(resp) {
  const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
  return Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m)]))
}

/** Alta o cambio de la asignación anual de un departamento. */
function AsignacionModal({ show, presupuestoId, anio, centros, asignacion, disponible, onHide, onGuardado }) {
  const [datos, setDatos] = useState({ centro: '', monto: '', motivo: '' })
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setErrores({})
    setDatos(asignacion ? { centro: String(asignacion.centro.id), monto: asignacion.asignado, motivo: '' } : { centro: '', monto: '', motivo: '' })
  }, [show, asignacion])

  const enviar = async (e) => {
    e.preventDefault()
    if (Number.isNaN(aCentavos(datos.monto)) || datos.monto === '') return setErrores({ monto: ['Monto inválido (máximo 2 decimales).'] })
    setGuardando(true)
    const resp = await api(`/api/presupuestos/${presupuestoId}/distribucion/`, {
      method: 'POST',
      body: { ...datos, monto: String(datos.monto).replace(/,/g, '') },
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    setErrores(await erroresDe(resp))
  }

  const maximo = asignacion ? disponible + centavos(asignacion.asignado) : disponible
  const generales = Object.entries(errores).filter(([c]) => !['centro', 'monto', 'motivo'].includes(c))

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={enviar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {asignacion ? `Asignación de ${asignacion.centro.codigo} ${asignacion.centro.nombre}` : 'Asignar a un departamento'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {generales.map(([c, m]) => (
            <Alert key={c} variant="danger">
              {m.join(' ')}
            </Alert>
          ))}
          <Row className="g-3">
            {!asignacion && (
              <Col xs={12}>
                <Form.Group controlId="asignacion-centro">
                  <Form.Label>Departamento (centro de costo de detalle, vigente en {anio})</Form.Label>
                  <Form.Select
                    value={datos.centro}
                    onChange={(e) => setDatos((d) => ({ ...d, centro: e.target.value }))}
                    isInvalid={Boolean(errores.centro)}
                    autoFocus
                  >
                    <option value="">Seleccione…</option>
                    {centros.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.codigo} · {c.nombre}
                      </option>
                    ))}
                  </Form.Select>
                  <Form.Control.Feedback type="invalid">{errores.centro?.join(' ')}</Form.Control.Feedback>
                </Form.Group>
              </Col>
            )}
            <Col xs={12}>
              <Form.Group controlId="asignacion-monto">
                <Form.Label>Monto anual asignado</Form.Label>
                <Form.Control
                  inputMode="decimal"
                  className="text-end"
                  value={datos.monto}
                  onChange={(e) => setDatos((d) => ({ ...d, monto: e.target.value }))}
                  isInvalid={Boolean(errores.monto)}
                  autoFocus={Boolean(asignacion)}
                />
                <Form.Control.Feedback type="invalid">{errores.monto?.join(' ')}</Form.Control.Feedback>
                <Form.Text>
                  Máximo disponible: <strong>{centavosATexto(maximo)}</strong>.{asignacion && ' Asigne 0 para quitar el departamento (si no tiene detalle).'}
                </Form.Text>
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Group controlId="asignacion-motivo">
                <Form.Label>Motivo</Form.Label>
                <Form.Control
                  maxLength={500}
                  value={datos.motivo}
                  onChange={(e) => setDatos((d) => ({ ...d, motivo: e.target.value }))}
                  placeholder="Opcional; queda en el historial"
                />
              </Form.Group>
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onHide}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardando}>
            {guardando && <Spinner animation="border" size="sm" className="me-2" />}
            Guardar
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  )
}

/** Matriz editable cuentas × meses del departamento elegido. */
function DetalleDepartamento({ presupuestoId, centroId, editable, cuentasGasto, onGuardado }) {
  const [datos, setDatos] = useState(null)
  const [filas, setFilas] = useState([])
  const [nueva, setNueva] = useState(null)
  const [motivo, setMotivo] = useState('')
  const [errores, setErrores] = useState([])
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    const resp = await api(`/api/presupuestos/${presupuestoId}/distribucion/${centroId}/`)
    if (!resp.ok) return setErrores([await mensajeError(resp)])
    const d = await resp.json()
    setDatos(d)
    setFilas(d.filas.map((f) => ({ cuenta: f.cuenta, meses: f.meses.map((m) => (Number(m) ? m : '')) })))
    setErrores([])
    setMotivo('')
  }, [presupuestoId, centroId])

  useEffect(() => {
    cargar()
  }, [cargar])

  const totalesFila = filas.map((f) => f.meses.reduce((s, m) => s + centavos(m), 0))
  const totalesMes = MESES.map((_, i) => filas.reduce((s, f) => s + centavos(f.meses[i]), 0))
  const detallado = totalesFila.reduce((s, t) => s + t, 0)
  const asignado = datos ? centavos(datos.asignado) : 0
  const sinDetallar = asignado - detallado
  const invalidas = filas.some((f) => f.meses.some((m) => Number.isNaN(aCentavos(m))))
  const modificado =
    datos &&
    JSON.stringify(filas.map((f) => [f.cuenta.id, f.meses.map(centavos)])) !==
      JSON.stringify(datos.filas.map((f) => [f.cuenta.id, f.meses.map(centavos)]))

  const cambiarCelda = (fi, mi, valor) =>
    setFilas((fs) => fs.map((f, i) => (i === fi ? { ...f, meses: f.meses.map((m, j) => (j === mi ? valor : m)) } : f)))

  /** Reparte el total anual de la fila en los meses vigentes; los centavos sobrantes van al último. */
  const repartir = (fi) => {
    const total = totalesFila[fi]
    const vigentes = datos.meses_vigentes.map((v, i) => (v ? i : null)).filter((i) => i !== null)
    if (!total || !vigentes.length) return
    const base = Math.floor(total / vigentes.length)
    const resto = total - base * vigentes.length
    setFilas((fs) =>
      fs.map((f, i) =>
        i !== fi
          ? f
          : {
              ...f,
              meses: MESES.map((_, m) => {
                if (!vigentes.includes(m)) return ''
                return aTextoAPI(base + (m === vigentes[vigentes.length - 1] ? resto : 0))
              }),
            },
      ),
    )
  }

  const agregar = (cuenta) => {
    if (!cuenta || filas.some((f) => f.cuenta.id === cuenta.id)) return setNueva(null)
    setFilas((fs) => [...fs, { cuenta, meses: Array(12).fill('') }].sort((a, b) => a.cuenta.codigo.localeCompare(b.cuenta.codigo)))
    setNueva(null)
  }

  const guardar = async () => {
    setGuardando(true)
    const resp = await api(`/api/presupuestos/${presupuestoId}/distribucion/${centroId}/`, {
      method: 'PUT',
      body: {
        motivo,
        filas: filas.map((f) => ({ cuenta: f.cuenta.id, meses: f.meses.map((m) => aTextoAPI(centavos(m))) })),
      },
    })
    setGuardando(false)
    if (!resp.ok) {
      const err = await erroresDe(resp)
      return setErrores(Object.values(err).flat())
    }
    await cargar()
    onGuardado()
  }

  if (!datos) return errores.length ? <Alert variant="danger">{errores.join(' ')}</Alert> : <Spinner animation="border" />

  const disponibles = cuentasGasto.filter((c) => !filas.some((f) => f.cuenta.id === c.id))

  return (
    <Card className="mb-3">
      <Card.Header className="d-flex flex-wrap justify-content-between align-items-center gap-2">
        <span className="fw-semibold">
          Detalle por cuenta y mes · <code>{datos.centro.codigo}</code> {datos.centro.nombre}
        </span>
        <span className="small">
          Asignado <strong className="monto">{formatoMonto(datos.asignado)}</strong> · Detallado{' '}
          <strong className="monto">{centavosATexto(detallado)}</strong> · Sin detallar{' '}
          <strong className={`monto ${sinDetallar < 0 ? 'text-danger' : ''}`}>{centavosATexto(sinDetallar)}</strong>
        </span>
      </Card.Header>
      {errores.length > 0 && (
        <Alert variant="danger" className="m-3 mb-0">
          {errores.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </Alert>
      )}
      {sinDetallar < 0 && (
        <Alert variant="warning" className="m-3 mb-0 small">
          El detalle excede lo asignado al departamento por {centavosATexto(-sinDetallar)}.
        </Alert>
      )}
      <div className="table-responsive">
        <Table size="sm" className="tabla-matriz align-middle mb-0">
          <thead className="table-light">
            <tr>
              <th style={{ minWidth: '13rem' }}>Cuenta</th>
              {MESES.map((m, i) => (
                <th key={m} className={`text-end ${datos.meses_vigentes[i] ? '' : 'text-suave'}`} style={{ minWidth: '6.5rem' }}>
                  {m}
                </th>
              ))}
              <th className="text-end col-total" style={{ minWidth: '7.5rem' }}>
                Total
              </th>
              {editable && <th />}
            </tr>
          </thead>
          <tbody>
            {filas.map((f, fi) => (
              <tr key={f.cuenta.id}>
                <td className="small">
                  <code className="me-1">{f.cuenta.codigo}</code>
                  {f.cuenta.nombre}
                </td>
                {f.meses.map((m, mi) => (
                  <td key={mi} className="p-1">
                    {editable ? (
                      <Form.Control
                        size="sm"
                        inputMode="decimal"
                        className="text-end"
                        aria-label={`${f.cuenta.codigo} ${MESES[mi]}`}
                        value={m}
                        disabled={!datos.meses_vigentes[mi]}
                        isInvalid={Number.isNaN(aCentavos(m))}
                        onChange={(e) => cambiarCelda(fi, mi, e.target.value)}
                      />
                    ) : (
                      <div className="monto">
                        <Monto valor={m || '0'} />
                      </div>
                    )}
                  </td>
                ))}
                <td className="monto col-total">{centavosATexto(totalesFila[fi])}</td>
                {editable && (
                  <td className="text-nowrap">
                    <Button size="sm" variant="link" className="p-1" title="Repartir el total en partes iguales por mes" onClick={() => repartir(fi)}>
                      <i className="bi bi-distribute-horizontal" />
                    </Button>
                    <Button
                      size="sm"
                      variant="link"
                      className="p-1 text-danger"
                      title="Quitar la cuenta"
                      onClick={() => setFilas((fs) => fs.filter((_, i) => i !== fi))}
                    >
                      <i className="bi bi-x-lg" />
                    </Button>
                  </td>
                )}
              </tr>
            ))}
            {filas.length === 0 && (
              <tr>
                <td colSpan={editable ? 15 : 14}>
                  <EstadoVacio icono="bi-grid-3x3">Aún no hay detalle por cuenta y mes para este departamento.</EstadoVacio>
                </td>
              </tr>
            )}
          </tbody>
          <tfoot className="table-light">
            <tr className="fila-subtotal">
              <td>Total por mes</td>
              {totalesMes.map((t, i) => (
                <td key={i} className="monto">
                  {centavosATexto(t)}
                </td>
              ))}
              <td className="monto col-total">{centavosATexto(detallado)}</td>
              {editable && <td />}
            </tr>
          </tfoot>
        </Table>
      </div>
      {editable && (
        <Card.Body className="border-top">
          <Row className="g-2 align-items-end">
            <Col md={5}>
              <Form.Label htmlFor="agregar-cuenta" className="small text-suave mb-1">
                Agregar cuenta de gasto
              </Form.Label>
              <SelectorCuenta id="agregar-cuenta" cuentas={disponibles} valor={nueva} onChange={agregar} placeholder="Código o nombre" />
            </Col>
            <Col md={4}>
              <Form.Label htmlFor="detalle-motivo" className="small text-suave mb-1">
                Motivo del cambio
              </Form.Label>
              <Form.Control id="detalle-motivo" size="sm" maxLength={500} value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Opcional" />
            </Col>
            <Col md={3} className="text-md-end">
              <Button size="sm" variant="outline-secondary" className="me-2" disabled={!modificado || guardando} onClick={cargar}>
                Descartar
              </Button>
              <Button size="sm" disabled={!modificado || invalidas || sinDetallar < 0 || guardando} onClick={guardar}>
                {guardando && <Spinner animation="border" size="sm" className="me-2" />}
                Guardar detalle
              </Button>
            </Col>
          </Row>
          <div className="small text-suave mt-2">
            <i className="bi bi-distribute-horizontal me-1" />
            Escriba el total anual en un mes y use <em>repartir</em> para dividirlo en partes iguales (los centavos sobrantes van al último mes).
            Los meses en gris son aquellos en que el centro no está vigente.
          </div>
        </Card.Body>
      )}
    </Card>
  )
}

function Historial({ presupuestoId, centroId, version }) {
  const [cambios, setCambios] = useState(null)

  useEffect(() => {
    const q = centroId ? `?centro=${centroId}` : ''
    api(`/api/presupuestos/${presupuestoId}/historial-distribucion/${q}`).then(async (r) => setCambios(r.ok ? await r.json() : []))
  }, [presupuestoId, centroId, version])

  if (!cambios) return <Spinner animation="border" size="sm" />
  if (!cambios.length) return <EstadoVacio icono="bi-clock-history">Sin cambios registrados.</EstadoVacio>
  return (
    <div className="table-responsive" style={{ maxHeight: '22rem' }}>
      <Table size="sm" className="align-middle mb-0">
        <thead className="table-light sticky-top">
          <tr>
            <th>Fecha</th>
            <th>Departamento</th>
            <th>Concepto</th>
            <th className="text-end">Anterior</th>
            <th className="text-end">Nuevo</th>
            <th className="text-end">Variación</th>
            <th>Motivo</th>
            <th>Usuario</th>
          </tr>
        </thead>
        <tbody>
          {cambios.map((c) => (
            <tr key={c.id} className="small">
              <td className="text-nowrap">{fechaHora(c.registrado_en)}</td>
              <td>
                <code>{c.centro.codigo}</code>
              </td>
              <td>
                {c.cuenta ? (
                  <>
                    <code className="me-1">{c.cuenta.codigo}</code>
                    {MESES[c.mes - 1]}
                  </>
                ) : (
                  <Badge bg="primary-subtle" text="primary-emphasis" className="fw-normal">
                    Asignación anual
                  </Badge>
                )}
              </td>
              <td className="monto">{formatoMonto(c.monto_anterior)}</td>
              <td className="monto">{formatoMonto(c.monto_nuevo)}</td>
              <td className="monto">
                <Monto valor={c.variacion} alertar />
              </td>
              <td>{c.motivo}</td>
              <td>{c.registrado_por}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}

export default function DistribucionPresupuesto() {
  const { usuario } = useAuth()
  const esContador = tieneRol(usuario, ROLES.CONTADOR)
  const [params, setParams] = useSearchParams()

  const [presupuestos, setPresupuestos] = useState(null)
  const [resumen, setResumen] = useState(null)
  const [catalogos, setCatalogos] = useState({ centros: [], cuentas: [] })
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [modal, setModal] = useState({ show: false, asignacion: null })
  const [version, setVersion] = useState(0)

  const presupuestoId = params.get('presupuesto')
  const centroId = params.get('centro')

  useEffect(() => {
    api('/api/presupuestos/').then(async (r) => {
      const lista = r.ok ? await r.json() : []
      setPresupuestos(lista)
      if (!params.get('presupuesto') && lista.length) setParams({ presupuesto: lista[0].id }, { replace: true })
    })
    Promise.all([
      api('/api/centros-costo/arbol/').then((r) => (r.ok ? r.json() : [])),
      api('/api/cuentas/arbol/').then((r) => (r.ok ? r.json() : [])),
    ]).then(([centros, cuentas]) =>
      setCatalogos({
        centros: aplanar(centros, (n) => n.acepta_movimientos),
        cuentas: aplanar(cuentas, (n) => n.tipo === 'GASTO' && n.acepta_movimientos && n.activa).map((c) => ({ id: c.id, codigo: c.codigo, nombre: c.nombre })),
      }),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const cargarResumen = useCallback(async () => {
    if (!presupuestoId) return setResumen(null)
    const resp = await api(`/api/presupuestos/${presupuestoId}/distribucion/`)
    if (!resp.ok) return setError(await mensajeError(resp))
    setResumen(await resp.json())
  }, [presupuestoId])

  useEffect(() => {
    cargarResumen()
  }, [cargarResumen])

  const elegir = (p) => setParams(p)
  const p = resumen?.presupuesto
  const editable = esContador && p && p.estado !== 'CERRADO'
  const disponible = resumen ? centavos(resumen.sin_distribuir) : 0
  const asignados = useMemo(() => new Set(resumen?.departamentos.map((d) => d.centro.id)), [resumen])
  const centrosLibres = p ? catalogos.centros.filter((c) => vigenteEnAnio(c, p.anio) && !asignados.has(c.id)) : []
  const seleccionado = resumen?.departamentos.find((d) => String(d.centro.id) === centroId)

  const alAsignar = (r) => {
    const a = modal.asignacion
    setModal({ show: false, asignacion: null })
    setError('')
    setAviso(a ? `Asignación de ${a.centro.codigo} actualizada.` : 'Departamento agregado a la distribución.')
    setResumen(r)
    setVersion((v) => v + 1)
    if (a && !r.departamentos.some((d) => d.centro.id === a.centro.id)) elegir({ presupuesto: presupuestoId })
  }

  const usado = resumen ? Math.min(100, Number(resumen.porcentaje_distribuido || 0)) : 0

  return (
    <>
      <EncabezadoPagina
        titulo="Distribución a departamentos"
        descripcion="Reparto top-down del monto institucional a cada departamento y, dentro de él, por cuenta de gasto y mes."
        migas={[{ texto: 'Presupuesto' }, { texto: 'Distribución a departamentos' }]}
      >
        {editable && (
          <Button onClick={() => setModal({ show: true, asignacion: null })} disabled={disponible <= 0}>
            <i className="bi bi-plus-lg me-1" /> Asignar a departamento
          </Button>
        )}
      </EncabezadoPagina>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      {aviso && (
        <Alert variant="success" dismissible onClose={() => setAviso('')}>
          {aviso}
        </Alert>
      )}

      {!presupuestos ? (
        <Spinner animation="border" />
      ) : presupuestos.length === 0 ? (
        <Card>
          <EstadoVacio icono="bi-wallet2">Primero registre un presupuesto institucional (Presupuesto → Presupuesto institucional).</EstadoVacio>
        </Card>
      ) : (
        <>
          <Card className="mb-3">
            <Card.Body>
              <Row className="g-3 align-items-center">
                <Col xs={12} md={3}>
                  <Form.Label htmlFor="ejercicio" className="small text-suave mb-1">
                    Ejercicio
                  </Form.Label>
                  <Form.Select id="ejercicio" size="sm" value={presupuestoId || ''} onChange={(e) => elegir({ presupuesto: e.target.value })}>
                    {presupuestos.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.anio} · {x.estado_display}
                      </option>
                    ))}
                  </Form.Select>
                </Col>
                {resumen && (
                  <>
                    <Col xs={4} md={2}>
                      <div className="small text-suave">Institucional</div>
                      <div className="fw-semibold monto">{formatoMonto(resumen.monto_institucional)}</div>
                    </Col>
                    <Col xs={4} md={2}>
                      <div className="small text-suave">Distribuido</div>
                      <div className="fw-semibold monto">{formatoMonto(resumen.distribuido)}</div>
                    </Col>
                    <Col xs={4} md={2}>
                      <div className="small text-suave">Sin distribuir</div>
                      <div className={`fw-semibold monto ${disponible > 0 ? 'text-warning-emphasis' : 'text-success'}`}>
                        {formatoMonto(resumen.sin_distribuir)}
                      </div>
                    </Col>
                    <Col xs={12} md={3}>
                      <div className="d-flex justify-content-between small text-suave">
                        <span>Avance de la distribución</span>
                        <span>{resumen.porcentaje_distribuido ?? '0.00'} %</span>
                      </div>
                      <ProgressBar now={usado} variant={usado >= 100 ? 'success' : 'primary'} style={{ height: '0.6rem' }} />
                      <Badge bg={`${COLOR_ESTADO[p.estado]}-subtle`} text={`${COLOR_ESTADO[p.estado]}-emphasis`} className="mt-2">
                        Presupuesto {p.estado_display.toLowerCase()} · v{p.version}
                      </Badge>
                    </Col>
                  </>
                )}
              </Row>
            </Card.Body>
          </Card>

          {resumen && (
            <>
              <Card className="mb-3">
                <Card.Header className="fw-semibold">Departamentos</Card.Header>
                <div className="table-responsive">
                  <Table hover className="align-middle mb-0">
                    <thead className="table-light">
                      <tr>
                        <th>Departamento</th>
                        <th className="text-end">Asignado</th>
                        <th className="text-end">% del institucional</th>
                        <th className="text-end">Detallado</th>
                        <th className="text-end">Sin detallar</th>
                        <th className="text-end">Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {resumen.departamentos.map((d) => (
                        <tr key={d.centro.id} className={String(d.centro.id) === centroId ? 'table-active' : ''}>
                          <td>
                            <code className="me-2">{d.centro.codigo}</code>
                            {d.centro.nombre}
                          </td>
                          <td className="monto">{formatoMonto(d.asignado)}</td>
                          <td className="monto">{d.porcentaje} %</td>
                          <td className="monto">{formatoMonto(d.detallado)}</td>
                          <td className="monto">
                            <Monto valor={d.sin_detallar} alertar />
                          </td>
                          <td className="text-end text-nowrap">
                            <Button
                              size="sm"
                              variant={String(d.centro.id) === centroId ? 'primary' : 'outline-primary'}
                              className="me-1"
                              onClick={() => elegir({ presupuesto: presupuestoId, centro: d.centro.id })}
                            >
                              <i className="bi bi-grid-3x3 me-1" /> Detalle
                            </Button>
                            {editable && (
                              <Button size="sm" variant="outline-secondary" title="Cambiar asignación" onClick={() => setModal({ show: true, asignacion: d })}>
                                <i className="bi bi-pencil" />
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {resumen.departamentos.length === 0 && (
                        <tr>
                          <td colSpan={6}>
                            <EstadoVacio icono="bi-diagram-2">
                              Aún no se ha distribuido el presupuesto {p.anio}.{editable && ' Use "Asignar a departamento".'}
                            </EstadoVacio>
                          </td>
                        </tr>
                      )}
                    </tbody>
                    {resumen.departamentos.length > 0 && (
                      <tfoot className="table-light">
                        <tr className="fila-subtotal">
                          <td>Total distribuido</td>
                          <td className="monto">{formatoMonto(resumen.distribuido)}</td>
                          <td className="monto">{resumen.porcentaje_distribuido} %</td>
                          <td className="monto">{formatoMonto(resumen.detallado)}</td>
                          <td colSpan={2} />
                        </tr>
                      </tfoot>
                    )}
                  </Table>
                </div>
              </Card>

              {seleccionado && (
                <DetalleDepartamento
                  key={`${presupuestoId}-${centroId}-${seleccionado.asignado}`}
                  presupuestoId={presupuestoId}
                  centroId={centroId}
                  editable={editable}
                  cuentasGasto={catalogos.cuentas}
                  onGuardado={() => {
                    setAviso(`Detalle de ${seleccionado.centro.codigo} guardado.`)
                    cargarResumen()
                    setVersion((v) => v + 1)
                  }}
                />
              )}

              <Card className="mb-4">
                <Card.Header className="fw-semibold">
                  Historial de cambios{seleccionado && ` · ${seleccionado.centro.codigo}`}
                </Card.Header>
                <Historial presupuestoId={presupuestoId} centroId={seleccionado ? centroId : null} version={version} />
              </Card>
            </>
          )}
        </>
      )}

      {p && (
        <AsignacionModal
          show={modal.show}
          presupuestoId={presupuestoId}
          anio={p.anio}
          centros={centrosLibres}
          asignacion={modal.asignacion}
          disponible={disponible}
          onHide={() => setModal({ show: false, asignacion: null })}
          onGuardado={alAsignar}
        />
      )}
    </>
  )
}
