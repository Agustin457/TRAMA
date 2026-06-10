# Python ETL Automation Structure

Este proyecto contiene una estructura modular y profesional para implementar un proceso de Extracción, Transformación y Carga (ETL) en Python.

## Estructura de Directorios

```text
ETL 2/
├── .gitignore              # Archivos y carpetas a ignorar por git
├── README.md               # Documentación del proyecto
├── requirements.txt        # Dependencias de Python
├── config.yaml             # Configuración general (base de datos, rutas, etc.)
├── main.py                 # Orquestador del flujo ETL
├── src/                    # Código fuente del pipeline
│   ├── __init__.py
│   ├── extract.py          # Lógica de extracción de datos
│   ├── transform.py        # Lógica de limpieza y transformación
│   ├── load.py             # Lógica de carga a destino (DB, archivos, APIs)
│   └── utils/              # Funciones auxiliares
│       ├── __init__.py
│       ├── logger.py       # Configuración de logs unificada
│       └── helpers.py      # Funciones utilitarias comunes
├── tests/                  # Pruebas unitarias y de integración
│   ├── __init__.py
│   ├── test_extract.py
│   ├── test_transform.py
│   └── test_load.py
└── data/                   # Directorio local para almacenamiento de datos (opcional)
    ├── raw/                # Datos de entrada crudos
    ├── processed/          # Datos procesados/transformados
    └── output/             # Reportes u otros outputs de salida
```

## Configuración y Ejecución

1. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Ejecutar el pipeline**:
   ```bash
   python main.py
   ```
