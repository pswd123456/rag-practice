import sys
import json
import logging
import logging.config
from pathlib import Path
from typing import Dict, Any

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "request_id"):
            log_record["request_id"] = getattr(record, "request_id")
        return json.dumps(log_record, ensure_ascii=False)

def get_logging_config(log_file_path: str, log_level: str = "INFO") -> Dict[str, Any]:
    
    log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    config = {
        'version': 1,
        
        'disable_existing_loggers': False, 

        # --- Formatters ---
        'formatters': {
            'standard': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'json': {
                '()': JsonFormatter,
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
        },

        # --- Handlers ---
        'handlers': {
            'console': {
                'class': 'rich.logging.RichHandler',
                'level': log_level,
                'formatter': 'standard',
                'rich_tracebacks': True,
                'show_path': False,
                'markup': True
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'DEBUG',
                'formatter': 'json',
                'filename': str(log_path),
                'mode': 'a',
                'maxBytes': 10 * 1024 * 1024,
                'backupCount': 5,
                'encoding': 'utf-8'
            }
        },

        # --- Loggers ---
        'loggers': {
            # 根 Logger
            '': {
                'level': log_level,
                'handlers': ['console', 'file'],
                'propagate': True
            },
            # 核心应用 Logger
            'app': {
                'level': 'DEBUG',
                'handlers': ['console', 'file'],
                'propagate': False
            },
            'evaluation': {
                'level': 'DEBUG',
                'handlers': ['console', 'file'],
                'propagate': False
            },
            
            # --- Uvicorn 日志接管 ---
            'uvicorn': {
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': False
            },
            'uvicorn.error': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False
            },
            'uvicorn.access': {
                'level': 'WARNING',
                'handlers': ['console', 'file'],
                'propagate': False
            },

            # --- 降噪 ---
            'httpx': {'level': 'WARNING'},
            'httpcore': {'level': 'WARNING'},
            'chromadb': {'level': 'WARNING'},
            'pdfminer': {'level': 'WARNING'},
            'multipart': {'level': 'WARNING'},
            'watchfiles': {'level': 'WARNING'},
            'urllib3': {'level': 'WARNING'},

            'elasticsearch': {'level': 'ERROR'},
            'elastic_transport': {'level': 'ERROR'},
        }
    }
    return config

def setup_logging(log_file_path: str, log_level: str = "INFO"):
    """
    初始化日志配置。
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
    
    config = get_logging_config(log_file_path, log_level)
    logging.config.dictConfig(config)