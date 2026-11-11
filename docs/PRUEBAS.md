# Pruebas del sistema

## Cómo ejecutarlas
```bash
docker compose exec backend python manage.py test                 # toda la suite (≈ 3 min)
docker compose exec backend python manage.py test contabilidad    # una app
docker compose exec backend python manage.py test config          # integración de punta a punta
docker compose exec backend python manage.py verificar_integridad # reglas sobre la base real
```
Las pruebas corren contra **Oracle** (una base temporal que Django crea y destruye), así que también ejercitan las restricciones `CHECK` y los triggers. El usuario de la aplicación tiene los privilegios necesarios por `docker/oracle-init/01_privilegios_pruebas.sh`.

## Resumen por módulo

| Módulo | Archivos | Pruebas | Cubre |
|---|---|---|---|
| `usuarios` | `tests.py` | 17 | Roles, login/logout JWT, permisos, bitácora inmutable (modelo y trigger) |
| `contabilidad` | `tests.py` | 101 | Catálogo jerárquico, periodos, asientos (partida doble, inmutabilidad, reversión), centro obligatorio, libros, exportación a Excel |
| `centros_costo` | `tests.py`, `tests_asignacion.py`, `tests_prorrateo.py` | 65 | Jerarquía y vigencia, reglas de asignación, motor de prorrateo y trazabilidad |
| `reportes` | `tests.py`, `tests_contribucion.py`, `tests_indicadores.py` | 25 | Estado de resultados absorbente, enfoque de contribución, indicadores |
| `presupuesto` | `tests.py`, `tests_distribucion.py`, `tests_ejecucion.py` | 42 | Presupuesto versionado, distribución top-down con topes, ejecución y alertas |
| `tesoreria` | `tests.py`, `tests_cuentas_por_pagar.py`, `tests_libro_compras.py`, `tests_proyeccion.py`, `tests_flujo.py`, `tests_dashboard.py` | 60 | Proveedores, cuentas por pagar, IVA en compras y libro de compras, proyección de egresos, flujo de efectivo, dashboard |
| `ventas` | `tests.py` | 18 | Clientes, documentos de venta con IVA débito fiscal, anulación por reversión, libro de ventas |
| `config` | `tests_integracion.py` | 13 | Ciclo completo con datos de ejemplo (incluye IVA en compras y ventas); los módulos cuadran entre sí; `verificar_integridad`; carga de datos de demostración (`cargar_datos_demo`) |
| **Total** | | **341** | |

## Matriz: reglas contables no negociables → pruebas
"Servicio" = la regla se valida en `services.py`; "BD" = Oracle la impide aunque se salte el servicio (restricción o trigger).

| # | Regla (CLAUDE.md) | Servicio | Base de datos |
|---|---|---|---|
| 1 | Montos `NUMBER(18,2)`, nunca `float` | Todos los modelos usan `DecimalField(18,2)`; validación de 2 decimales en `presupuesto/tests.py::test_validaciones_de_alta`, `tesoreria/tests_cuentas_por_pagar.py::test_validaciones` | Restricciones `*_monto_positivo` (p. ej. `test_monto_positivo_en_bd`) |
| 2 | Partida doble | `contabilidad/tests.py::ContabilizarTests::test_partida_doble_obligatoria` | `TriggersAsientoTests::test_trigger_exige_partida_doble` (`TRG_ASIENTO_REGLAS`); `verificar_integridad` (PARTIDA_DOBLE) |
| 3 | Centro de costo en cada línea (salvo cuentas exentas) | `test_cuenta_no_exenta_exige_centro`, `test_centro_de_agrupacion_o_no_vigente`, `test_gasto_no_puede_quedar_exento_de_centro_de_costo` | `test_trigger_exige_centro`, `test_constraint_bd_exencion_solo_en_balance` |
| 4 | Asientos inmutables; corrección por reversión | `test_contabilizado_es_inmutable_en_el_servicio`, `ReversionTests::*`, `test_el_asiento_de_prorrateo_no_se_revierte_desde_asientos`, `test_asiento_no_se_revierte_desde_asientos` (cuentas por pagar) | `TRG_ASIENTO_REGLAS`, `TRG_LINEA_ASIENTO_INMUTABLE` (`TriggersAsientoTests`); documentos y pagos: `CxPBaseDeDatosTests::test_reglas_en_bd` |
| 5 | Trazabilidad (prorrateo → origen; usuario y fecha) | `test_distribuye_y_traza_cada_linea`, `test_reversion_invierte_lineas_y_conserva_trazabilidad` | `verificar_integridad` (PRORRATEO) |
| 6 | No registrar en periodo cerrado | `test_fecha_en_periodo_cerrado`, `test_fecha_sin_periodo_o_en_periodo_cerrado`, `test_una_vez_por_periodo_y_solo_periodo_abierto` | `test_trigger_exige_periodo_abierto` |
| 7 | Catálogo jerárquico | `test_jerarquia_nivel_y_herencia_de_tipo`, `test_codigo_debe_empezar_con_el_del_padre`, `test_codigo_padre_y_tipo_son_inmutables` | Restricciones del modelo `Cuenta` |
| 8 | Centros jerárquicos con vigencia | `centros_costo/tests.py::test_jerarquia_*`, `test_vigencia_*`, `test_no_se_cierra_padre_con_subunidades_vigentes` | `test_constraint_bd_vigencia` |
| 9 | Bitácora de acciones sensibles | `test_*_bitacora` en cada app (cuentas, periodos, asientos, prorrateo, presupuesto, distribución, cuentas por pagar, egresos programados) | `usuarios/tests.py::test_trigger_impide_update_en_base_de_datos`, `test_trigger_impide_delete_en_base_de_datos` |

### Presupuesto (Bloque 4)
| Regla | Servicio | Base de datos |
|---|---|---|
| Cambios versionados y auditados | `presupuesto/tests.py::test_ajuste_en_borrador`, `test_modificacion_de_aprobado_exige_motivo_y_referencia`, `test_bitacora` | `test_monto_sin_version_en_bd`, `test_versiones_inmutables_y_sin_eliminacion` |
| Σ distribuido ≤ institucional; saldo sin distribuir | `tests_distribucion.py::test_no_excede_el_monto_institucional`, `test_saldo_sin_distribuir`, `test_monto_institucional_no_baja_de_lo_distribuido` | `test_tope_institucional_en_bd`, `test_monto_institucional_en_bd` |
| Σ detalle ≤ asignación del departamento | `test_detalle_no_excede_lo_asignado` | `test_tope_departamento_en_bd` |
| Ejecución vs. presupuesto y alertas | `tests_ejecucion.py::*` | — |

### IVA en compras (T7.2)
| Regla | Servicio | Base de datos |
|---|---|---|
| Total = gravadas + exentas + IVA − retención | `tests_libro_compras.py::test_ccf_carga_iva_credito_fiscal`, `test_ccf_con_exentas_y_retencion` | `test_oracle_exige_que_el_desglose_cuadre` (`cxp_desglose_cuadra`) |
| IVA 13 % y retención 1 % solo en CCF; retención desde US$100 | `test_validaciones`, `test_iva_con_redondeo_del_documento` | `cxp_iva_solo_ccf` (mismo test) |
| Desglose inmutable; anulación por reversión | `test_anulacion_revierte_iva_y_retencion` | `TRG_CXP_REGLAS` (mismo test) |
| Libro de compras = CCF vigentes del mes; IVA del libro = cuenta 1403 | `LibroComprasTests::*` | — |

### Ventas (T7.3)
| Regla | Servicio | Base de datos |
|---|---|---|
| Total = gravadas + exentas + IVA (13 % de gravadas); ingresos con centro | `ventas/tests.py::test_ccf_genera_asiento_con_iva_debito`, `test_validaciones` | `test_reglas_en_bd` (`doc_venta_total_cuadra`) |
| CCF solo a contribuyentes con NIT y NRC | `test_validaciones`, `test_contribuyente_exige_nit_y_nrc` | `test_restriccion_en_bd` (`cliente_contribuyente_nit_nrc`) |
| Documento inmutable; anulación por reversión; número no reutilizable | `test_anular_revierte_el_asiento`, `test_numero_no_se_reutiliza`, `test_asiento_no_se_revierte_desde_asientos` | `TRG_DOC_VENTA_REGLAS`, `doc_venta_numero_unico` (`test_reglas_en_bd`) |
| Libro de ventas; débito fiscal = cuenta 2406 | `LibroVentasTests::*` | `verificar_integridad` (VENTAS) |

### Coherencia entre módulos (integración)
`config/tests_integracion.py::CicloCompletoTests` comprueba con los datos de ejemplo que:
- la balanza cuadra (cargos = abonos);
- estado de resultados = ingresos − gastos; enfoque de contribución e indicadores = absorbente; el prorrateo no cambia el total;
- ejecución presupuestaria = gastos directos del estado de resultados por departamento;
- flujo de efectivo real cuadra con el saldo contable; el dashboard coincide con sus fuentes;
- los libros de compras y ventas cuadran con las cuentas 1403, 2405 y 2406;
- `DatosDemoTests`: `cargar_datos_demo` (marzo y abril) respeta la partida doble y el centro de costo en ingresos y gastos, los libros de IVA cuadran con sus cuentas, el flujo cuadra, la agencia opera con utilidad, una segunda corrida no crea nada (idempotente) y un periodo cerrado detiene la carga sin registrar nada;
- `verificar_integridad` no encuentra fallas, y detecta un saldo de cuenta por pagar alterado por fuera del sistema (`IntegridadDetectaFallasTests`).

## Verificación sobre la base real
`python manage.py verificar_integridad [--anio AAAA]` revisa: partida doble, líneas sin centro (aviso), trazabilidad de prorrateos, saldos de cuentas por pagar, documentos de venta frente a sus asientos, presupuesto (versiones y topes), reportes vs. balanza y que los 14 triggers existan y estén habilitados. Termina con código 1 si hay fallas. Úsela antes de cerrar un periodo y después de restaurar un respaldo.
