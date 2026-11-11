import { api, mensajeError } from './api'

/**
 * Descarga un CSV compatible con Excel en español: separador ";", UTF-8 con BOM
 * y montos con punto decimal sin separador de miles.
 */
export function descargarCSV(nombreArchivo, encabezados, filas) {
  const celda = (valor) => {
    const texto = valor === null || valor === undefined ? '' : String(valor)
    return /[";\n\r]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto
  }
  const lineas = [encabezados, ...filas].map((fila) => fila.map(celda).join(';'))
  const blob = new Blob(['﻿' + lineas.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombreArchivo
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}

/**
 * Descarga un archivo generado por la API (p. ej. un libro .xlsx) con la sesión actual.
 * Devuelve null si todo salió bien o el mensaje de error.
 */
export async function descargarDesdeApi(url, nombrePorDefecto) {
  const resp = await api(url)
  if (!resp.ok) return mensajeError(resp)
  const disposicion = resp.headers.get('Content-Disposition') || ''
  const nombre = /filename="([^"]+)"/.exec(disposicion)?.[1] || nombrePorDefecto
  const blob = await resp.blob()
  const enlace = document.createElement('a')
  enlace.href = URL.createObjectURL(blob)
  enlace.download = nombre
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(enlace.href)
  return null
}
