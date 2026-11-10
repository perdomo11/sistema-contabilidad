/** Mensaje centrado con ícono para listas o reportes sin datos. */
export default function EstadoVacio({ icono = 'bi-inbox', children }) {
  return (
    <div className="estado-vacio">
      <i className={`bi ${icono}`} aria-hidden="true" />
      {children}
    </div>
  )
}
