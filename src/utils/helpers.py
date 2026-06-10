import yaml
import os
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env si existe
load_dotenv()

def load_config(config_path: str = "config.yaml") -> dict:
    """
    Carga el archivo de configuración YAML.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"No se encontró el archivo de configuración en: {config_path}")
        
    with open(config_path, 'r', encoding='utf-8') as file:
        try:
            config = yaml.safe_load(file)
            return config
        except yaml.YAMLError as exc:
            raise ValueError(f"Error parseando el archivo YAML: {exc}")

def get_env_variable(var_name: str, default: str = None) -> str:
    """
    Obtiene una variable de entorno de forma segura.
    """
    val = os.getenv(var_name, default)
    if val is None:
        # Aquí puedes registrar un warning o lanzar excepción según el caso de uso
        pass
    return val
