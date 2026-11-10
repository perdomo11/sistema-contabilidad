import { useEffect, useState } from 'react'
import { Spinner, Tab, Tabs } from 'react-bootstrap'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import EjecucionProrrateo from '../components/prorrateo/EjecucionProrrateo'
import MedidasProrrateo from '../components/prorrateo/MedidasProrrateo'
import ReglasProrrateo from '../components/prorrateo/ReglasProrrateo'
import { usePeriodos } from '../components/SelectorPeriodo'

export default function Prorrateo() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR)
  const [params, setParams] = useSearchParams()
  const pestana = params.get('pestana') || 'ejecucion'
  const { periodos, sugerido } = usePeriodos()
  const [periodo, setPeriodo] = useState(null)

  useEffect(() => {
    if (sugerido && !periodo) setPeriodo(sugerido.id)
  }, [sugerido, periodo])

  const comunes = { periodos, periodo, onPeriodo: setPeriodo, puedeEditar }
  const sinPeriodos = periodos && periodos.length === 0
  const conPeriodo = (contenido) =>
    sinPeriodos ? (
      <EstadoVacio icono="bi-calendar3">No hay periodos contables. Cree un ejercicio en Periodos contables.</EstadoVacio>
    ) : periodo ? (
      contenido
    ) : (
      <Spinner animation="border" />
    )

  return (
    <>
      <EncabezadoPagina
        titulo="Prorrateo de costos"
        descripcion="Distribuye los costos de los centros de servicio hacia los centros que los consumen, según bases configurables. Cada línea generada conserva su origen."
        migas={[{ texto: 'Centros de costo' }, { texto: 'Prorrateo' }]}
      />
      <Tabs activeKey={pestana} onSelect={(k) => setParams({ pestana: k }, { replace: true })} className="mb-3" mountOnEnter>
        <Tab eventKey="ejecucion" title={<><i className="bi bi-play-circle me-1" />Ejecución</>}>
          {conPeriodo(<EjecucionProrrateo {...comunes} />)}
        </Tab>
        <Tab eventKey="reglas" title={<><i className="bi bi-shuffle me-1" />Reglas</>}>
          <ReglasProrrateo puedeEditar={puedeEditar} />
        </Tab>
        <Tab eventKey="medidas" title={<><i className="bi bi-rulers me-1" />Bases y medidas</>}>
          {conPeriodo(<MedidasProrrateo {...comunes} />)}
        </Tab>
      </Tabs>
    </>
  )
}
