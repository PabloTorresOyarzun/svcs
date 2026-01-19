
**Lista Maestra de Roles ERP** definitiva, integrando lo financiero con lo operativo:

---

### Los 7 Roles Maestros para tu ERP

Mantuvimos los 5 que ya definiste y agregamos los 2 que faltaban para cubrir a los "Pedidores", "Tramitadores" y el equipo de "Soporte".

#### 1. Rol: Facturación (Revenue)

* **Enfoque:** Transformar carpetas en dinero.
* **Usuarios Buk:** Jefe de Facturación, Facturador, Administrativo (de el área Facturación).

#### 2. Rol: Tesorería (Payments)

* **Enfoque:** Pagar servicios, aduanas y gestionar caja.
* **Usuarios Buk:** Jefe Recaudación y Pagos, Administrativo (de el área Finanzas).

#### 3. Rol: Contabilidad (Controller)

* **Enfoque:** Auditoría, impuestos y balances.
* **Usuarios Buk:** Encargada Contabilidad.

#### 4. Rol: Administración Interna (Backoffice)

* **Enfoque:** Gestión de la oficina, RRHH y compras menores (insumos).
* **Usuarios Buk:** Encargada de Sucursal, Encargada RRHH, Administrativo (de el área Administración).

#### 5. Rol: Gerencia (Strategy & View)

* **Enfoque:** Supervisión general y desbloqueos.
* **Usuarios Buk:** Agente de Aduana, Abogado.

#### 6. Rol: Operaciones Comex (Core Business)

* **Qué hacen:** Este es el grupo más grande (Pedidores, Gestores). Ellos crean la "Carpeta de Despacho", suben los documentos (BL, Factura Comercial), solicitan fondos y digitan los datos de la importación/exportación.
* **Usuarios Buk:**
* **Pedidor / Asistente Pedidor** (Importaciones/Exportaciones).
* **Gestor de Despachos**.
* **Jefe de Operaciones**.
* Administrativos asignados a Importaciones/Exportaciones.

#### 7. Rol: Logística y Terreno (Field Operations)
* **Qué hacen:** Tienen un acceso muy restringido. Generalmente solo marcan hitos ("Documento entregado", "Carga retirada") o suben fotos de gastos menores. Puede que ni siquiera usen el ERP, pero si lo usan, es este rol.
* **Usuarios Buk:**
* **Tramitador Aduanero / Tramitador de Servicios**.
* **Presentador**.
* **Chofer / Junior**.
#### 8: Rol Super Admin (IT)
- **Qué hacen:** Tienen acceso a configuración, creación de usuarios y logs.
* **Usuario:** Soporte y Sistemas TI

---

### Tabla de Mapeo: Cargo Buk  Rol ERP

Esta tabla es la que servirá para configurar los permisos uno por uno según el cargo que tengan en Buk:

| Cargo en Buk                       | Área (Buk)         | **Asignar ROL ERP**                                            |
| ---------------------------------- | ------------------ | -------------------------------------------------------------- |
| Jefe de Facturación / Facturador   | Facturación        | **1. Facturación**                                             |
| Jefe Recaudación / Admin. Finanzas | Finanzas           | **2. Tesorería**                                               |
| Encargada Contabilidad             | Finanzas           | **3. Contabilidad**                                            |
| Enc. Sucursal / RRHH / Admin.      | Administración     | **4. Administración Interna**                                  |
| Agente de Aduana / Abogado         | Gerencia           | **5. Gerencia**                                                |
| **Pedidor / Asistente Pedidor**    | Imp/Exp/Garantías  | **6. Operaciones Comex**                                       |
| **Gestor de Despachos**            | Imp/Info. Aduanera | **6. Operaciones Comex**                                       |
| **Jefe de Operaciones**            | Operaciones        | **6. Operaciones Comex** (Quizás con permisos extra de anular) |
| **Tramitador / Presentador**       | Operaciones/Info.  | **7. Logística y Terreno**                                     |
| **Chofer / Junior**                | Operaciones/Admin  | **7. Logística y Terreno** (O sin usuario si no usan PC)       |
| Soporte y Sistemas TI              | Info. Aduanera     | **8. Super Admin (IT)**                                        |

