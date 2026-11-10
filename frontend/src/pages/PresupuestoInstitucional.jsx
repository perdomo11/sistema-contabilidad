import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { Monto } from '../components/reportes/ReporteSegmentado'
import { aCentavos, formatoMonto } from '../formato'

const COLOR_ESTADO = { BORRADOR: 'warning', APROBADO: 'success', CERRADO: 'secondary' }
const COLOR_TIPO = { INICIAL: 'secondary', AJUSTE: 'warning', APROBACION: 'success', MODIFICACION: 'primary' }

const fechaHora = (iso) =>
  iso ? new Date(iso).toLocaleString('es-SV', { dateStyle: 'short', timeStyle: 'short' }) : ''

function InsigniaEstado({ estado, texto }) {
  const c = COLOR_ESTADO[estado]
  return (
    <Badge bg={`${c}-subtle`} text={`${c}-emphasis`}>
      {texto}
    </Badge>
  )
}

/**
 * Modal de formulario genérico. `campos`: [{ nombre, etiqueta, tipo, ayuda, requerido }].
 * Envía `datos` a `url` (POST/PATCH) y muestra los errores por campo que devuelva la API.
 */
function ModalFormulario({ show, titulo, url, metodo = 'POST', campos, inicial, textoBoton, variante = 'primary', aviso, onHide, onGuardado }) {
  const [datos, setDatos] = useState({})
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (show) {
      setDatos(inicial || {})
      setErrores({})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show])

  const enviar = async (e) => {
    e.preventDefault()
    const locales = {}
    for (const c of campos) {
      if (c.tipo === 'monto' && Number.isNaN(aCentavos(datos[c.nombre]))) locales[c.nombre] = 'Monto inválido (máximo 2 decimales).'
    }
    if (Object.keys(locales).length) return setErrores(locales)
    setGuardando(true)
    const cuerpo = Object.fromEntries(
      Object.entries(datos).map(([k, v]) => [k, campos.find((c) => c.nombre === k)?.tipo === 'monto' ? String(v).replace(/,/g, '') : v]),
    )
    const resp = await api(url, { method: metodo, body: cuerpo })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    setErrores(Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).join(' ')])))
  }

  const nombres = campos.map((c) => c.nombre)
  const generales = Object.entries(errores).filter(([c]) => !nombres.includes(c))

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={enviar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {titulo}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {aviso}
          {generales.map(([c, m]) => (
            <Alert key={c} variant="danger">
              {m}
            </Alert>
          ))}
          <Row className="g-3">
            {campos.map((c, i) => (
              <Col xs={12} md={c.ancho || 12} key={c.nombre}>
                <Form.Group controlId={`presupuesto-${c.nombre}`}>
                  <Form.Label>
                    {c.etiqueta}
                    {c.requerido && <span className="text-danger"> *</span>}
                  </Form.Label>
                  <Form.Control
                    as={c.tipo === 'texto-largo' ? 'textarea' : 'input'}
                    rows={c.tipo === 'texto-largo' ? 3 : undefined}
                    type={c.tipo === 'anio' ? 'number' : 'text'}
                    inputMode={c.tipo === 'monto' ? 'decimal' : undefined}
                    className={c.tipo === 'monto' ? 'text-end' : ''}
                    value={datos[c.nombre] ?? ''}
                    maxLength={c.max}
                    autoFocus={i === 0}
                    onChange={(e) => setDatos((d) => ({ ...d, [c.nombre]: e.target.value }))}
                    isInvalid={Boolean(errores[c.nombre])}
                  />
                  <Form.Control.Feedback type="invalid">{errores[c.nombre]}</Form.Control.Feedback>
                  {c.ayuda && <Form.Text>{c.ayuda}</Form.Text>}
                </Form.Group>
              </Col>
            ))}
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onHide}>
            Cancelar
          </Button>
          <Button type="submit" variant={variante} disabled={guardando}>
            {guardando && <Spinner animation="border" size="sm" className="me-2" />}
            {textoBoton}
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  )
}

export default function PresupuestoInstitucional() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR)

  const [lista, setLista] = useState(null)
  const [seleccion, setSeleccion] = useState(null)
  const [detalle, setDetalle] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [modal, setModal] = useState(null)

  const cargarLista = useCallback(async () => {
    const resp = await api('/api/presupuestos/')
    if (!resp.ok) {
      setLista([])
      return setError(await mensajeError(resp))
    }
    const datos = await resp.json()
    setLista(datos)
    setSeleccion((s) => s ?? datos[0]?.id ?? null)
  }, [])

  const cargarDetalle = useCallback(async (id) => {
    if (!id) return setDetalle(null)
    const resp = await api(`/api/presupuestos/${id}/`)
    if (!resp.ok) return setError(await mensajeError(resp))
    setDetalle(await resp.json())
  }, [])

  useEffect(() => {
    cargarLista()
  }, [cargarLista])

  useEffect(() => {
    cargarDetalle(seleccion)
  }, [seleccion, cargarDetalle])

  const alGuardar = (texto) => (p) => {
    setModal(null)
    setError('')
    setAviso(texto(p))
    setDetalle(p)
    setSeleccion(p.id)
    cargarLista()
  }

  const cerrar = async () => {
    setModal(null)
    const resp = await api(`/api/presupuestos/${detalle.id}/cerrar/`, { method: 'POST' })
    if (!resp.ok) return setError(await mensajeError(resp))
    alGuardar((p) => `Presupuesto ${p.anio} cerrado.`)(await resp.json())
  }

  const aprobado = detalle?.estado === 'APROBADO'
  const abierto = detalle && detalle.estado !== 'CERRADO'
  const siguienteAnio = lista?.length ? Math.max(...lista.map((p) => p.anio)) + 1 : new Date().getFullYear() + 1

  return (
    <>
      <EncabezadoPagina
        titulo="Presupuesto institucional"
        descripcion="Monto anual de egresos que fija la gerencia. Cada cambio queda versionado y en la bitácora; después se distribuye a los departamentos."
        migas={[{ texto: 'Presupuesto' }, { texto: 'Presupuesto institucional' }]}
      >
        {puedeEditar && (
          <Button onClick={() => setModal('crear')}>
            <i className="bi bi-plus-lg me-1" /> Nuevo presupuesto
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

      {!lista ? (
        <Spinner animation="border" />
      ) : lista.length === 0 ? (
        <Card>
          <EstadoVacio icono="bi-wallet2">
            Aún no hay presupuestos institucionales.{puedeEditar && ' Registre el del próximo ejercicio con "Nuevo presupuesto".'}
          </EstadoVacio>
        </Card>
      ) : (
        <Row className="g-3">
          <Col lg={4}>
            <Card>
              <Card.Header className="fw-semibold">Ejercicios</Card.Header>
              <Table hover className="align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th>Año</th>
                    <th className="text-end">Monto vigente</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {lista.map((p) => (
                    <tr
                      key={p.id}
                      role="button"
                      className={p.id === seleccion ? 'table-active' : ''}
                      onClick={() => setSeleccion(p.id)}
                    >
                      <td>
                        <strong>{p.anio}</strong>
                        <div className="small text-suave">versión {p.version}</div>
                      </td>
                      <td className="monto">{formatoMonto(p.monto)}</td>
                      <td>
                        <InsigniaEstado estado={p.estado} texto={p.estado_display} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          </Col>

          <Col lg={8}>
            {!detalle ? (
              <Spinner animation="border" />
            ) : (
              <>
                <Card className="mb-3">
                  <Card.Body>
                    <div className="d-flex flex-wrap justify-content-between align-items-start gap-2">
                      <div>
                        <div className="small text-suave text-uppercase">Presupuesto institucional {detalle.anio}</div>
                        <div className="display-6 monto fw-semibold">$ {formatoMonto(detalle.monto)}</div>
                        <div className="mt-1">
                          <InsigniaEstado estado={detalle.estado} texto={detalle.estado_display} />
                          <span className="small text-suave ms-2">versión {detalle.version}</span>
                        </div>
                      </div>
                      {puedeEditar && abierto && (
                        <div className="d-flex flex-wrap gap-2 no-imprimir">
                          <Button size="sm" variant="outline-primary" onClick={() => setModal('monto')}>
                            <i className="bi bi-pencil-square me-1" />
                            {aprobado ? 'Modificar monto' : 'Ajustar monto'}
                          </Button>
                          {detalle.estado === 'BORRADOR' && (
                            <Button size="sm" variant="success" onClick={() => setModal('aprobar')}>
                              <i className="bi bi-check2-circle me-1" /> Aprobar
                            </Button>
                          )}
                          {aprobado && (
                            <Button size="sm" variant="outline-secondary" onClick={() => setModal('cerrar')}>
                              <i className="bi bi-lock me-1" /> Cerrar
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                    <hr />
                    <Row className="small g-2">
                      <Col md={7}>
                        <div className="text-suave">Descripción</div>
                        <div>
                          {detalle.descripcion || <span className="text-suave">Sin descripción</span>}
                          {puedeEditar && abierto && (
                            <Button variant="link" size="sm" className="p-0 ms-2 no-imprimir" onClick={() => setModal('descripcion')}>
                              Editar
                            </Button>
                          )}
                        </div>
                      </Col>
                      <Col md={5}>
                        <div className="text-suave">Aprobación</div>
                        {detalle.aprobado_por ? (
                          <div>
                            {detalle.referencia_aprobacion}
                            <div className="text-suave">
                              {detalle.aprobado_por} · {fechaHora(detalle.aprobado_en)}
                            </div>
                          </div>
                        ) : (
                          <span className="text-suave">Pendiente</span>
                        )}
                      </Col>
                    </Row>
                  </Card.Body>
                </Card>

                <Card>
                  <Card.Header className="fw-semibold">Historial de versiones</Card.Header>
                  <div className="table-responsive">
                    <Table size="sm" className="align-middle mb-0">
                      <thead className="table-light">
                        <tr>
                          <th>#</th>
                          <th>Tipo</th>
                          <th className="text-end">Monto</th>
                          <th className="text-end">Variación</th>
                          <th>Motivo / referencia</th>
                          <th>Registrado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...detalle.versiones].reverse().map((v) => (
                          <tr key={v.id}>
                            <td>{v.numero}</td>
                            <td>
                              <Badge bg={`${COLOR_TIPO[v.tipo]}-subtle`} text={`${COLOR_TIPO[v.tipo]}-emphasis`} className="fw-normal">
                                {v.tipo_display}
                              </Badge>
                            </td>
                            <td className="monto">{formatoMonto(v.monto)}</td>
                            <td className="monto">{v.variacion === null ? <span className="text-suave">–</span> : <Monto valor={v.variacion} alertar />}</td>
                            <td className="small">
                              {v.motivo}
                              {v.referencia && <div className="text-suave">{v.referencia}</div>}
                            </td>
                            <td className="small text-nowrap">
                              {v.registrado_por}
                              <div className="text-suave">{fechaHora(v.registrado_en)}</div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </Card>
              </>
            )}
          </Col>
        </Row>
      )}

      <ModalFormulario
        show={modal === 'crear'}
        titulo="Nuevo presupuesto institucional"
        url="/api/presupuestos/"
        inicial={{ anio: String(siguienteAnio), monto: '', descripcion: '' }}
        campos={[
          { nombre: 'anio', etiqueta: 'Ejercicio', tipo: 'anio', requerido: true, ancho: 4 },
          { nombre: 'monto', etiqueta: 'Monto institucional de egresos', tipo: 'monto', requerido: true, ancho: 8 },
          { nombre: 'descripcion', etiqueta: 'Descripción', tipo: 'texto-largo', max: 500, ayuda: 'Lineamientos de la gerencia (opcional).' },
        ]}
        textoBoton="Crear en borrador"
        onHide={() => setModal(null)}
        onGuardado={alGuardar((p) => `Presupuesto ${p.anio} creado en borrador.`)}
      />

      {detalle && (
        <>
          <ModalFormulario
            show={modal === 'monto'}
            titulo={`${aprobado ? 'Modificación presupuestaria' : 'Ajustar monto'} ${detalle.anio}`}
            url={`/api/presupuestos/${detalle.id}/cambiar-monto/`}
            inicial={{ monto: detalle.monto, motivo: '', referencia: '' }}
            campos={[
              { nombre: 'monto', etiqueta: 'Monto nuevo', tipo: 'monto', requerido: true },
              { nombre: 'motivo', etiqueta: 'Motivo', tipo: 'texto-largo', max: 500, requerido: aprobado },
              { nombre: 'referencia', etiqueta: 'Documento que lo autoriza', max: 200, requerido: aprobado, ayuda: 'Ej.: Acta de junta directiva 03/2027' },
            ]}
            aviso={
              aprobado && (
                <Alert variant="info" className="small">
                  El presupuesto está aprobado: el cambio queda como modificación presupuestaria y requiere motivo y documento.
                </Alert>
              )
            }
            textoBoton="Registrar versión"
            onHide={() => setModal(null)}
            onGuardado={alGuardar((p) => `Monto del presupuesto ${p.anio} actualizado (versión ${p.version}).`)}
          />
          <ModalFormulario
            show={modal === 'aprobar'}
            titulo={`Aprobar presupuesto ${detalle.anio}`}
            url={`/api/presupuestos/${detalle.id}/aprobar/`}
            inicial={{ referencia: '' }}
            campos={[{ nombre: 'referencia', etiqueta: 'Documento de aprobación de la gerencia', max: 200, requerido: true, ayuda: 'Ej.: Acta de junta directiva 12/2026' }]}
            aviso={
              <p className="small">
                Monto a aprobar: <strong>$ {formatoMonto(detalle.monto)}</strong>. Después, cualquier cambio requerirá motivo y documento.
              </p>
            }
            textoBoton="Aprobar"
            variante="success"
            onHide={() => setModal(null)}
            onGuardado={alGuardar((p) => `Presupuesto ${p.anio} aprobado.`)}
          />
          <ModalFormulario
            show={modal === 'descripcion'}
            titulo={`Descripción del presupuesto ${detalle.anio}`}
            url={`/api/presupuestos/${detalle.id}/`}
            metodo="PATCH"
            inicial={{ descripcion: detalle.descripcion }}
            campos={[{ nombre: 'descripcion', etiqueta: 'Descripción', tipo: 'texto-largo', max: 500 }]}
            textoBoton="Guardar"
            onHide={() => setModal(null)}
            onGuardado={alGuardar((p) => `Descripción del presupuesto ${p.anio} actualizada.`)}
          />
          <Modal show={modal === 'cerrar'} onHide={() => setModal(null)} centered>
            <Modal.Header closeButton>
              <Modal.Title as="h2" className="h5">
                Cerrar presupuesto {detalle.anio}
              </Modal.Title>
            </Modal.Header>
            <Modal.Body>Un presupuesto cerrado ya no admite cambios de monto ni de descripción. ¿Continuar?</Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" onClick={() => setModal(null)}>
                Cancelar
              </Button>
              <Button variant="dark" onClick={cerrar}>
                Cerrar presupuesto
              </Button>
            </Modal.Footer>
          </Modal>
        </>
      )}
    </>
  )
}
