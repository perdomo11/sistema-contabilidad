import { Badge } from 'react-bootstrap'

/** Insignia de estado de un asiento, incluida la condición de revertido. */
export default function EstadoAsiento({ asiento }) {
  if (asiento.estado === 'BORRADOR') {
    return (
      <Badge bg="warning" text="dark">
        Borrador
      </Badge>
    )
  }
  return (
    <>
      <Badge bg="success">Contabilizado</Badge>
      {asiento.tipo === 'REVERSION' && (
        <Badge bg="info" text="dark" className="ms-1">
          Reversión
        </Badge>
      )}
      {asiento.revertido_por && (
        <Badge bg="secondary" className="ms-1">
          Revertido
        </Badge>
      )}
    </>
  )
}
