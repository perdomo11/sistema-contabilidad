// Debe coincidir con backend/usuarios/roles.py
export const ROLES = {
  CONTADOR: 'Contador',
  TESORERO: 'Tesorero',
  JEFE_AREA: 'Jefe de área',
  AUDITOR: 'Auditor',
}

export function tieneRol(usuario, ...roles) {
  if (!usuario) return false
  if (usuario.es_admin) return true
  return roles.some((rol) => usuario.roles.includes(rol))
}
