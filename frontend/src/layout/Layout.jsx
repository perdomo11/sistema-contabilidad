import { useEffect, useState } from 'react'
import { Badge, Dropdown } from 'react-bootstrap'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import { hoyISO, formatoFecha } from '../formato'

/** Menú agrupado por módulo. `roles`: si se indica, solo se muestra a esos roles (y al administrador). */
const MENU = [
  {
    seccion: 'General',
    items: [{ a: '/', icono: 'bi-speedometer2', texto: 'Inicio', exacto: true }],
  },
  {
    seccion: 'Contabilidad',
    items: [
      { a: '/asientos', icono: 'bi-journal-text', texto: 'Asientos' },
      { a: '/libros/diario', icono: 'bi-book', texto: 'Libro diario' },
      { a: '/libros/mayor', icono: 'bi-journal-bookmark', texto: 'Libro mayor' },
      { a: '/libros/balanza', icono: 'bi-calculator', texto: 'Balanza de comprobación' },
    ],
  },
  {
    seccion: 'Centros de costo',
    items: [
      { a: '/centros-costo', icono: 'bi-diagram-2', texto: 'Estructura de centros', exacto: true },
      { a: '/centros-costo/reglas', icono: 'bi-signpost-split', texto: 'Reglas de asignación' },
      { a: '/centros-costo/prorrateo', icono: 'bi-shuffle', texto: 'Prorrateo' },
    ],
  },
  {
    seccion: 'Reportes',
    items: [{ a: '/reportes/estado-resultados', icono: 'bi-graph-up', texto: 'Estado de resultados' }],
  },
  {
    seccion: 'Tesorería',
    items: [{ a: '/proveedores', icono: 'bi-truck', texto: 'Proveedores' }],
  },
  {
    seccion: 'Configuración',
    items: [
      { a: '/catalogo', icono: 'bi-diagram-3', texto: 'Catálogo de cuentas' },
      { a: '/periodos', icono: 'bi-calendar3', texto: 'Periodos contables' },
    ],
  },
  {
    seccion: 'Control',
    items: [{ a: '/bitacora', icono: 'bi-shield-check', texto: 'Bitácora de auditoría', roles: [ROLES.AUDITOR] }],
  },
]

function iniciales(nombre) {
  return nombre
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join('')
}

function MenuLateral({ abierto, onNavegar }) {
  const { usuario } = useAuth()
  return (
    <aside className={`app-menu ${abierto ? 'abierto' : ''}`} aria-label="Menú principal">
      <NavLink to="/" className="app-menu-marca" onClick={onNavegar}>
        <span className="app-logo">
          <i className="bi bi-bank2" />
        </span>
        <span>
          <span className="titulo d-block">Sistema Contable</span>
          <span className="subtitulo">Centros de costo y flujo de efectivo</span>
        </span>
      </NavLink>
      <nav className="app-menu-cuerpo">
        {MENU.map(({ seccion, items }) => {
          const visibles = items.filter((i) => !i.roles || tieneRol(usuario, ...i.roles))
          if (!visibles.length) return null
          return (
            <div key={seccion}>
              <div className="app-menu-seccion">{seccion}</div>
              {visibles.map((i) => (
                <NavLink key={i.a} to={i.a} end={i.exacto} className="app-menu-enlace" onClick={onNavegar}>
                  <i className={`bi ${i.icono}`} aria-hidden="true" />
                  {i.texto}
                </NavLink>
              ))}
            </div>
          )
        })}
      </nav>
      <div className="app-menu-pie">SIC 115 · Universidad de El Salvador</div>
    </aside>
  )
}

function BarraSuperior({ onMenu }) {
  const { usuario, logout } = useAuth()
  const navegar = useNavigate()
  const hoy = hoyISO()

  const cerrarSesion = async () => {
    await logout()
    navegar('/login', { replace: true })
  }

  return (
    <header className="app-barra">
      <button type="button" className="btn btn-light btn-sm d-lg-none" onClick={onMenu} aria-label="Abrir menú">
        <i className="bi bi-list fs-5" />
      </button>
      <div className="text-suave small d-none d-sm-block">
        <i className="bi bi-calendar-event me-1" />
        Ejercicio {hoy.slice(0, 4)} · {formatoFecha(hoy)}
      </div>
      <Dropdown align="end" className="ms-auto">
        <Dropdown.Toggle variant="link" className="d-flex align-items-center gap-2 text-decoration-none text-reset p-0">
          <span className="app-avatar">{iniciales(usuario.nombre)}</span>
          <span className="text-start d-none d-md-block lh-sm">
            <span className="d-block fw-semibold small">{usuario.nombre}</span>
            <span className="d-block text-suave" style={{ fontSize: '0.72rem' }}>
              {usuario.es_admin ? 'Administrador' : usuario.roles.join(', ') || 'Sin rol'}
            </span>
          </span>
        </Dropdown.Toggle>
        <Dropdown.Menu className="shadow-sm">
          <Dropdown.Header>
            <div className="fw-semibold text-body">{usuario.nombre}</div>
            <div className="small">@{usuario.username}</div>
          </Dropdown.Header>
          <div className="px-3 pb-2 d-flex flex-wrap gap-1">
            {usuario.es_admin && (
              <Badge bg="danger-subtle" text="danger-emphasis">
                Administrador
              </Badge>
            )}
            {usuario.roles.map((rol) => (
              <Badge key={rol} bg="primary-subtle" text="primary-emphasis">
                {rol}
              </Badge>
            ))}
          </div>
          <Dropdown.Divider />
          <Dropdown.Item onClick={cerrarSesion}>
            <i className="bi bi-box-arrow-right me-2" />
            Cerrar sesión
          </Dropdown.Item>
        </Dropdown.Menu>
      </Dropdown>
    </header>
  )
}

/** Estructura de la aplicación autenticada: menú lateral + barra superior + contenido. */
export default function Layout() {
  const [menuAbierto, setMenuAbierto] = useState(false)
  const ubicacion = useLocation()

  useEffect(() => setMenuAbierto(false), [ubicacion.pathname])

  return (
    <>
      <MenuLateral abierto={menuAbierto} onNavegar={() => setMenuAbierto(false)} />
      {menuAbierto && <div className="app-velo d-lg-none" onClick={() => setMenuAbierto(false)} />}
      <div className="app-principal">
        <BarraSuperior onMenu={() => setMenuAbierto(true)} />
        <main className="app-contenido">
          <Outlet />
        </main>
      </div>
    </>
  )
}
