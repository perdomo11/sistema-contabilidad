// Cliente HTTP de la API con manejo de tokens JWT.
const CLAVE_ACCESS = 'contable.access'
const CLAVE_REFRESH = 'contable.refresh'

export const EVENTO_SESION_EXPIRADA = 'contable:sesion-expirada'

function leer(clave) {
  try {
    return localStorage.getItem(clave)
  } catch {
    return null
  }
}

export function guardarTokens({ access, refresh }) {
  try {
    if (access) localStorage.setItem(CLAVE_ACCESS, access)
    if (refresh) localStorage.setItem(CLAVE_REFRESH, refresh)
  } catch {
    /* almacenamiento no disponible */
  }
}

export function limpiarTokens() {
  try {
    localStorage.removeItem(CLAVE_ACCESS)
    localStorage.removeItem(CLAVE_REFRESH)
  } catch {
    /* almacenamiento no disponible */
  }
}

export const tokenAccess = () => leer(CLAVE_ACCESS)
export const tokenRefresh = () => leer(CLAVE_REFRESH)

// Un solo refresco en curso a la vez: con rotación de tokens, dos refrescos
// simultáneos con el mismo refresh harían fallar al segundo.
let refrescoEnCurso = null

function refrescar() {
  const refresh = tokenRefresh()
  if (!refresh) return Promise.resolve(false)
  if (!refrescoEnCurso) {
    refrescoEnCurso = fetch('/api/auth/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
      .then(async (resp) => {
        if (!resp.ok) return false
        guardarTokens(await resp.json())
        return true
      })
      .catch(() => false)
      .finally(() => {
        refrescoEnCurso = null
      })
  }
  return refrescoEnCurso
}

/**
 * fetch con token Bearer. Si la respuesta es 401 intenta refrescar el access
 * una vez; si no se puede, limpia la sesión y emite EVENTO_SESION_EXPIRADA.
 */
export async function api(url, { body, headers, ...opciones } = {}, reintentar = true) {
  const encabezados = { 'Content-Type': 'application/json', ...headers }
  const access = tokenAccess()
  if (access) encabezados.Authorization = `Bearer ${access}`

  const resp = await fetch(url, {
    ...opciones,
    headers: encabezados,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (resp.status === 401 && reintentar && tokenRefresh()) {
    if (await refrescar()) return api(url, { body, headers, ...opciones }, false)
    limpiarTokens()
    window.dispatchEvent(new Event(EVENTO_SESION_EXPIRADA))
  }
  return resp
}

/** Extrae un mensaje de error legible de una respuesta de DRF. */
export async function mensajeError(resp) {
  const datos = await resp.json().catch(() => null)
  if (datos?.detail) return datos.detail
  if (datos && typeof datos === 'object') {
    return Object.entries(datos)
      .map(([campo, msgs]) => `${campo}: ${[].concat(msgs).join(' ')}`)
      .join(' · ')
  }
  return `Error ${resp.status}`
}

/** Recorre todas las páginas de un listado paginado de DRF y devuelve los resultados (o [] si falla). */
export async function apiTodas(url) {
  const resultados = []
  let siguiente = url
  while (siguiente) {
    const resp = await api(siguiente)
    if (!resp.ok) return resultados
    const pagina = await resp.json()
    resultados.push(...pagina.results)
    siguiente = pagina.next ? pagina.next.replace(/^https?:\/\/[^/]+/, '') : null
  }
  return resultados
}
