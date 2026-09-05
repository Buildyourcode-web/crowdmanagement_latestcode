import sys
from loguru import logger
from app.config import settings


def setup_logging():
    logger.remove()
    
    log_level = "DEBUG" if settings.DEBUG else "INFO"
    
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    logger.add(
        sys.stdout,
        level=log_level,
        format=log_format,
        colorize=True,
        enqueue=True,
    )
    
    return logger


app_logger = setup_logging()
