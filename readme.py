readme_content = """**Actúa como un Consultor Senior de Transformación Digital y Data Engineer experto en Python, PostgreSQL y WooCommerce.**

A continuación, te presento el README, los archivos adjuntos y el estado actual de nuestro proyecto. Tu objetivo es analizar este contexto y ejecutar la primera tarea que te indicaré al final.

---

# 📄 README: Proyecto Trama Buenos Aires
**Objetivo Central:** Transformación digital del backend operativo, consolidación de catálogos y automatización de WooCommerce (https://tramabuenosaires.com.ar/tienda/) garantizando integridad y cero duplicidad antes de escalar ventas.

### 1. Archivos Adjuntos (Data Dictionary)
Te he adjuntado 4 archivos que son la materia prima de este proyecto. Debes referenciar estos nombres exactos en tus scripts:
*   `woocommerce_products.csv`: El estado actual del catálogo en la tienda online.
*   `ListadePrecios (53).xlsx`: Lista cruda del proveedor **Powerland**.
*   `Lista de Precios ALE Actualizada (49).xlsx`: Lista cruda del proveedor **ALE**.
*   `LISTA Nº 1 - 26 LINEA ROTRING.xlsx`: Lista cruda del proveedor **Rotring**.

### 2. Arquitectura y Stack Tecnológico
*   **Base de Datos:** PostgreSQL (Supabase para Staging con extensión `pgvector`).
*   **ETL (Extract, Transform, Load):** Scripts en Python (Pandas).
*   **Inteligencia Semántica:** Modelo LLM/Embeddings para deduplicar productos sin EAN.
*   **Integración:** API REST de WooCommerce (sólo payloads ligeros: `regular_price` y `stock_quantity`).

### 3. Lógica Financiera e Impositiva
El ETL y la base de datos deben calcular el Precio de Venta al Público (PVP) aplicando una cascada sobre el costo neto del proveedor. El código debe contemplar las variables tributarias de Argentina:
*   Alícuotas de **IVA** (21%, 10.5% o exentos).
*   Percepciones de **Ingresos Brutos**.
*   **Impuesto a los sellos** (si aplica a la transacción u operación).
*   **Impuestos internos**.
*   Incidencia del **Impuesto a los débitos y créditos bancarios**.
*   Margen de ganancia (Markup) segmentado.

### 4. Esquema de Base de Datos
1. `proveedores`: Reglas y márgenes.
2. `productos_raw`: "Corralito" de datos crudos extraídos de los Excel.
3. `catalogo_maestro`: Tabla final limpia que sincroniza con WooCommerce.

### 5. Tablero Kanban
**✅ DONE (Completado):**
* Diagnóstico, Stack definido, Esquema SQL relacional diseñado. Aprobada la Fase 0 (Capa de IA obligatoria para unificar SKUs sin código de barras).

**⏳ IN PROGRESS (En Proceso):**
* Configuración de Supabase (PostgreSQL).

**📝 TO DO (Por Hacer - Tu área de trabajo):**
1. **Script ETL (Extracción):** Lógica en Python/Pandas para parsear los Excels adjuntos.
2. **Motor Semántico (IA):** Script de embeddings para analizar descripciones en `productos_raw`.
3. **Script ETL (Cálculo):** Lógica matemática de la cascada de impuestos.
4. **Conector WooCommerce:** Script de API REST.

---

### 🎯 Tu Primera Tarea
Analiza los 3 archivos Excel adjuntos (`ListadePrecios (53).xlsx`, `Lista de Precios ALE Actualizada (49).xlsx`, `LISTA Nº 1 - 26 LINEA ROTRING.xlsx`). 

Como primera tarea en esta sesión, **escribe la estructura base del código en Python (Pandas)** correspondiente al paso **1 del TO DO (Script ETL de Extracción)**. 

El código debe incluir funciones separadas diseñadas específicamente para leer cada uno de estos tres archivos reales. Debes detectar en qué fila empiezan los datos útiles de cada proveedor (ignorando encabezados decorativos) y estandarizar las columnas resultantes para prepararlas para la tabla `productos_raw`.
"""

with open("README_Trama_Buenos_Aires.md", "w", encoding="utf-8") as f:
    f.write(readme_content)