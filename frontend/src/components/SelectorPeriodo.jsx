import { useEffect, useState } from 'react'
import { Form } from 'react-bootstrap'
import { api } from '../api'
import { hoyISO } from '../formato'

/** Carga todos los periodos contables y propone el que contiene la fecha de hoy (o el último). */
export function usePeriodos() {
  const [periodos, setPeriodos] = useState(null)
  useEffect(() => {
    api('/api/periodos/').then(async (r) => setPeriodos(r.ok ? await r.json() : []))
  }, [])
  const hoy = hoyISO()
  const sugerido = periodos?.find((p) => p.fecha_inicio <= hoy && p.fecha_fin >= hoy) || periodos?.at(-1) || null
  return { periodos, sugerido }
}

/** Lista desplegable de periodos agrupados por ejercicio. `valor`: id del periodo. */
export default function SelectorPeriodo({ id, periodos, valor, onChange }) {
  const ejercicios = [...new Set((periodos || []).map((p) => p.anio))].sort((a, b) => b - a)
  return (
    <Form.Select id={id} size="sm" value={valor ?? ''} onChange={(e) => onChange(Number(e.target.value))}>
      {ejercicios.map((anio) => (
        <optgroup key={anio} label={`Ejercicio ${anio}`}>
          {periodos
            .filter((p) => p.anio === anio)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
                {p.estado === 'CERRADO' ? ' (cerrado)' : ''}
              </option>
            ))}
        </optgroup>
      ))}
    </Form.Select>
  )
}
