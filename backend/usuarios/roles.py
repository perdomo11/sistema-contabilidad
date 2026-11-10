"""Roles del sistema. Se implementan como grupos de Django (ver migración 0002)."""

CONTADOR = "Contador"
TESORERO = "Tesorero"
JEFE_AREA = "Jefe de área"
AUDITOR = "Auditor"

TODOS = (CONTADOR, TESORERO, JEFE_AREA, AUDITOR)
