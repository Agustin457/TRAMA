import pandas as pd
import os
from src.utils.logger import setup_logger

logger = setup_logger()

def load_to_csv(df: pd.DataFrame, output_path: str) -> None:
    """
    Guarda los datos transformados en un archivo CSV.
    """
    logger.info(f"Cargando datos en archivo CSV de destino: {output_path}")
    try:
        # Asegurarse de que el directorio existe
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info("Carga en CSV exitosa.")
    except Exception as e:
        logger.error(f"Error cargando datos en CSV: {e}")
        raise

def load_to_database(df: pd.DataFrame, table_name: str, db_connection_uri: str = None) -> None:
    """
    Carga los datos en una tabla de base de datos SQL (por ejemplo, PostgreSQL o SQLite).
    """
    logger.info(f"Cargando datos en tabla de base de datos: {table_name}")
    try:
        # Ejemplo con SQLAlchemy si se configura una conexión real:
        if db_connection_uri:
            # from sqlalchemy import create_engine
            # engine = create_engine(db_connection_uri)
            # df.to_sql(table_name, con=engine, if_exists='append', index=False)
            pass
        else:
            logger.warning("No se proporcionó URI de base de datos. Simulando carga...")
            # Aquí iría tu lógica real
            
        logger.info("Carga en base de datos completada (simulada/real).")
    except Exception as e:
        logger.error(f"Error cargando datos en base de datos: {e}")
        raise

def load_to_excel(df: pd.DataFrame, output_path: str, sheet_name: str = "Master") -> None:
    """
    Guarda los datos transformados en un archivo Excel.
    """
    logger.info(f"Cargando datos en archivo Excel de destino: {output_path}")
    try:
        # Asegurarse de que el directorio existe
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        df.to_excel(output_path, index=False, sheet_name=sheet_name)
        logger.info("Carga en Excel exitosa.")
    except Exception as e:
        logger.error(f"Error cargando datos en Excel: {e}")
        raise

