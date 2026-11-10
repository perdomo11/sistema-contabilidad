import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../../api'
import EstadoVacio from '../EstadoVacio'
import SelectorCuenta from '../SelectorCuenta'

function aplanar(arbol, incluir) {
  const lista = []
  const recorrer = (nodos) =>
    nodos.forEach((n) => {
      if (incluir(n)) lista.push({ id: n.id, codigo: n.codigo, nombre: n.nombre })
      recorrer(n.hijos)
    })
  recorrer(arbol)
  return lista
}

/** Alta y edición de una regla de prorrateo. */
function ReglaProrrateoModal({ show, regla, catalogos, onHide, onGuardado }) {
  const editando = Boolean(regla)
  const [datos, setDatos] = useState({})
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setErrores({})
    setDatos(
      editando
        ? {
            nombre: regla.nombre,
            orden: regla.orden,
            centro_origen: catalogos.centros.find((c) => c.id === regla.centro_origen) || null,
            base: regla.base,
            cuentas: regla.cuentas,
            destinos: regla.destinos.map((d) => d.id),
            activa: regla.activa,
          }
        : { nombre: '', orden: 1, centro_origen: null, base: catalogos.bases[0]?.id ?? '', cuentas: [], destinos: [], activa: true },
    )
  }, [show, regla, editando, catalogos])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))
  const alternarDestino = (id) =>
    cambiar('destinos', datos.destinos.includes(id) ? datos.destinos.filter((x) => x !== id) : [...datos.destinos, id])

  const guardar = async (e) => {
    e.preventDefault()
    setGuardando(true)
    setErrores({})
    const cuerpo = {
      nombre: datos.nombre,
      orden: Number(datos.orden) || 1,
      centro_origen: datos.centro_origen?.id ?? null,
      base: Number(datos.base) || null,
      cuentas: datos.cuentas.map((c) => c.id),
      destinos: datos.destinos,
      activa: datos.activa,
    }
    const resp = await api(editando ? `/api/prorrateo/reglas/${regla.id}/` : '/api/prorrateo/reglas/', {
      method: editando ? 'PATCH' : 'POST',
      body: cuerpo,
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    setErrores(Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).join(' ')])))
  }

  const conocidos = ['nombre', 'orden', 'centro_origen', 'base', 'cuentas', 'destinos', 'activa']
  const generales = Object.entries(errores).filter(([c]) => !conocidos.includes(c))
  const error = (campo) => errores[campo] && <div className="invalid-feedback d-block">{errores[campo]}</div>
  const candidatos = catalogos.centros.filter((c) => c.id !== datos.centro_origen?.id)

  return (
    <Modal show={show} onHide={onHide} centered size="lg" scrollable>
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {editando ? `Editar «${regla.nombre}»` : 'Nueva regla de prorrateo'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {generales.map(([c, m]) => (
            <Alert key={c} variant="danger">
              {m}
            </Alert>
          ))}
          {editando && regla.ejecutada && (
            <Alert variant="light" className="border small">
              La regla ya se ejecutó: los cambios aplican a las ejecuciones futuras. Las ya registradas conservan los datos
              con que se calcularon.
            </Alert>
          )}
          <Row className="g-3">
            <Col md={9}>
              <Form.Group controlId="prorrateo-nombre">
                <Form.Label>Nombre</Form.Label>
                <Form.Control
                  value={datos.nombre || ''}
                  maxLength={150}
                  onChange={(e) => cambiar('nombre', e.target.value)}
                  isInvalid={Boolean(errores.nombre)}
                  autoFocus
                />
                {error('nombre')}
              </Form.Group>
            </Col>
            <Col md={3}>
              <Form.Group controlId="prorrateo-orden">
                <Form.Label>Orden</Form.Label>
                <Form.Control
                  type="number"
                  min={1}
                  value={datos.orden ?? 1}
                  onChange={(e) => cambiar('orden', e.target.value)}
                  isInvalid={Boolean(errores.orden)}
                />
                {error('orden')}
              </Form.Group>
            </Col>
            <Col md={7}>
              <Form.Label htmlFor="prorrateo-origen">Centro origen (se descarga)</Form.Label>
              <SelectorCuenta
                id="prorrateo-origen"
                cuentas={catalogos.centros}
                valor={datos.centro_origen}
                onChange={(v) => cambiar('centro_origen', v)}
                isInvalid={Boolean(errores.centro_origen)}
                placeholder="Unidad de servicio"
              />
              {error('centro_origen')}
            </Col>
            <Col md={5}>
              <Form.Group controlId="prorrateo-base">
                <Form.Label>Base de prorrateo</Form.Label>
                <Form.Select value={datos.base ?? ''} onChange={(e) => cambiar('base', e.target.value)} isInvalid={Boolean(errores.base)}>
                  {catalogos.bases.map((b) => (
                    <option key={b.id} value={b.id} disabled={!b.activa}>
                      {b.nombre} ({b.unidad})
                    </option>
                  ))}
                </Form.Select>
                {error('base')}
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Label htmlFor="prorrateo-cuenta">Cuentas a distribuir</Form.Label>
              <SelectorCuenta
                key={`cuentas-${(datos.cuentas || []).length}`}
                id="prorrateo-cuenta"
                cuentas={catalogos.cuentas.filter((c) => !(datos.cuentas || []).some((x) => x.id === c.id))}
                valor={null}
                onChange={(c) => c && cambiar('cuentas', [...datos.cuentas, c])}
                placeholder="Agregar cuenta (una de agrupación incluye sus subcuentas)"
              />
              <div className="d-flex flex-wrap gap-1 mt-2">
                {(datos.cuentas || []).map((c) => (
                  <Badge key={c.id} bg="primary-subtle" text="primary-emphasis" className="d-flex align-items-center gap-1">
                    <code className="text-reset">{c.codigo}</code> {c.nombre}
                    <button
                      type="button"
                      className="btn-close btn-close-sm ms-1"
                      style={{ fontSize: '0.55rem' }}
                      aria-label={`Quitar ${c.codigo}`}
                      onClick={() => cambiar('cuentas', datos.cuentas.filter((x) => x.id !== c.id))}
                    />
                  </Badge>
                ))}
              </div>
              {error('cuentas')}
            </Col>
            <Col xs={12}>
              <div className="d-flex justify-content-between align-items-end">
                <Form.Label className="mb-1">
                  Centros destino <span className="text-suave small">({(datos.destinos || []).length} seleccionados)</span>
                </Form.Label>
                <div className="small">
                  <Button variant="link" size="sm" className="p-0 me-2" onClick={() => cambiar('destinos', candidatos.map((c) => c.id))}>
                    Todos
                  </Button>
                  <Button variant="link" size="sm" className="p-0" onClick={() => cambiar('destinos', [])}>
                    Ninguno
                  </Button>
                </div>
              </div>
              <div className="border rounded p-2 overflow-auto" style={{ maxHeight: '14rem' }}>
                <Row className="g-1">
                  {candidatos.map((c) => (
                    <Col key={c.id} sm={6}>
                      <Form.Check
                        id={`destino-${c.id}`}
                        className="small"
                        checked={(datos.destinos || []).includes(c.id)}
                        onChange={() => alternarDestino(c.id)}
                        label={
                          <>
                            <code className="me-1">{c.codigo}</code>
                            {c.nombre}
                          </>
                        }
                      />
                    </Col>
                  ))}
                </Row>
              </div>
              {error('destinos')}
            </Col>
            <Col xs={12}>
              <Form.Check
                type="switch"
                id="prorrateo-activa"
                label="Activa"
                checked={Boolean(datos.activa)}
                onChange={(e) => cambiar('activa', e.target.checked)}
              />
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

export default function ReglasProrrateo({ puedeEditar }) {
  const [reglas, setReglas] = useState(null)
  const [catalogos, setCatalogos] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [formulario, setFormulario] = useState({ show: false, regla: null })
  const [porEliminar, setPorEliminar] = useState(null)

  const cargar = useCallback(async () => {
    const resp = await api('/api/prorrateo/reglas/')
    if (!resp.ok) {
      setReglas([])
      return setError(await mensajeError(resp))
    }
    setReglas(await resp.json())
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  useEffect(() => {
    if (!puedeEditar) return
    Promise.all([
      api('/api/cuentas/arbol/').then((r) => (r.ok ? r.json() : [])),
      api('/api/centros-costo/arbol/').then((r) => (r.ok ? r.json() : [])),
      api('/api/prorrateo/bases/').then((r) => (r.ok ? r.json() : [])),
    ]).then(([cuentas, centros, bases]) =>
      setCatalogos({
        cuentas: aplanar(cuentas, (n) => n.activa && !n.exenta_centro_costo),
        centros: aplanar(centros, (n) => n.acepta_movimientos),
        bases,
      }),
    )
  }, [puedeEditar])

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const alGuardar = (r) => {
    notificar(`Regla «${r.nombre}» ${formulario.regla ? 'actualizada' : 'creada'}.`)
    setFormulario({ show: false, regla: null })
    cargar()
  }

  const eliminar = async () => {
    const r = porEliminar
    setPorEliminar(null)
    const resp = await api(`/api/prorrateo/reglas/${r.id}/`, { method: 'DELETE' })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`Regla «${r.nombre}» eliminada.`)
    cargar()
  }

  return (
    <>
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div className="small text-suave">
          Método escalonado: las reglas se ejecutan de menor a mayor orden y un centro ya distribuido no vuelve a recibir costos.
        </div>
        {puedeEditar && (
          <Button disabled={!catalogos} onClick={() => setFormulario({ show: true, regla: null })}>
            <i className="bi bi-plus-lg me-1" /> Nueva regla
          </Button>
        )}
      </div>

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

      {!reglas ? (
        <Spinner animation="border" />
      ) : (
        <Card className="mb-4">
          <div className="table-responsive">
            <Table hover className="align-middle">
              <thead>
                <tr>
                  <th style={{ width: '4rem' }}>Orden</th>
                  <th>Regla</th>
                  <th>Cuentas</th>
                  <th>Destinos</th>
                  {puedeEditar && <th className="text-end">Acciones</th>}
                </tr>
              </thead>
              <tbody>
                {reglas.map((r) => (
                  <tr key={r.id} className={r.activa ? '' : 'text-suave'}>
                    <td className="text-center">{r.orden}</td>
                    <td>
                      <div>
                        {r.nombre}
                        {!r.activa && (
                          <Badge bg="secondary-subtle" text="secondary-emphasis" className="ms-2">
                            Inactiva
                          </Badge>
                        )}
                      </div>
                      <div className="small text-suave">
                        Desde <code>{r.centro_origen_codigo}</code> {r.centro_origen_nombre} · por {r.base_nombre.toLowerCase()}
                      </div>
                    </td>
                    <td className="small">
                      {r.cuentas.map((c) => (
                        <div key={c.id}>
                          <code className="me-1">{c.codigo}</code>
                          {c.nombre}
                        </div>
                      ))}
                    </td>
                    <td className="small" title={r.destinos.map((d) => `${d.codigo} ${d.nombre}`).join('\n')}>
                      {r.destinos.length} centro(s): {r.destinos.map((d) => d.codigo).join(', ')}
                    </td>
                    {puedeEditar && (
                      <td className="text-end text-nowrap">
                        <Button
                          size="sm"
                          variant="outline-secondary"
                          className="me-1"
                          title="Editar"
                          disabled={!catalogos}
                          onClick={() => setFormulario({ show: true, regla: r })}
                        >
                          <i className="bi bi-pencil" />
                        </Button>
                        {!r.ejecutada && (
                          <Button size="sm" variant="outline-danger" title="Eliminar" onClick={() => setPorEliminar(r)}>
                            <i className="bi bi-trash" />
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
                {reglas.length === 0 && (
                  <tr>
                    <td colSpan={puedeEditar ? 5 : 4}>
                      <EstadoVacio icono="bi-shuffle">No hay reglas de prorrateo.</EstadoVacio>
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
        </Card>
      )}

      {catalogos && (
        <ReglaProrrateoModal
          show={formulario.show}
          regla={formulario.regla}
          catalogos={catalogos}
          onHide={() => setFormulario({ show: false, regla: null })}
          onGuardado={alGuardar}
        />
      )}

      <Modal show={Boolean(porEliminar)} onHide={() => setPorEliminar(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Eliminar regla
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          ¿Eliminar <strong>{porEliminar?.nombre}</strong>? Solo es posible porque aún no se ha ejecutado.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setPorEliminar(null)}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={eliminar}>
            Eliminar
          </Button>
        </Modal.Footer>
      </Modal>
    </>
  )
}
