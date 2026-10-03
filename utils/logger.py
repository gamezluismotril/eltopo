"""
Sistema de logging centralizado para ELTOPO.
Usa loguru para logs bonitos + rotativos.
"""
import sys
from pathlib import Path
from loguru import logger

from config import LOGS_DIR, LOG_LEVEL


# Quitar el logger por defecto
logger.remove()

# Formato para consola (coloreado)
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
           "<level>{message}</level>",
    level=LOG_LEVEL,
    colorize=True,
)

# Formato para archivo (más detallado, con rotación)
LOG_FILE = LOGS_DIR / "eltopo_{time:YYYY-MM-DD}.log"
logger.add(
    LOG_FILE,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
           "{name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
)


def get_logger(name: str = "eltopo"):
    """
    Devuelve un logger con contexto del modulo.

    Uso:
        from utils.logger import get_logger
        log = get_logger(__name__)
        log.info('Mensaje')
    """
    return logger.bind(module=name)


# Test rapido
if __name__ == "__main__":
    log = get_logger("test")
    log.debug("Esto es un mensaje de debug")
    log.info("Esto es info")
    log.success("Esto es un exito")
    log.warning("Esto es una advertencia")
    log.error("Esto es un error")
    print()
    print(f"Logs guardados en: {LOGS_DIR}")
