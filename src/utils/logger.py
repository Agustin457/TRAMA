import logging
import sys
import os

def setup_logger(name: str = "etl_pipeline", log_level: str = "INFO") -> logging.Logger:
    """
    Configura y devuelve un logger unificado con salida a consola y archivo.
    """
    logger = logging.getLogger(name)
    
    # Evitar duplicar handlers si ya está configurado
    if logger.hasHandlers():
        return logger
        
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Formato de logs
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler de Consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Crear carpeta logs si no existe
    os.makedirs("logs", exist_ok=True)
    
    # Handler de Archivo
    file_handler = logging.FileHandler("logs/etl_run.log", encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger
