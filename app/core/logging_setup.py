# logging_config.py
from typing import Dict, Any

def get_logging_config(log_file_path: str) -> Dict[str, Any]:
    """
    根据传入的日志文件路径，生成日志配置字典。
    """
    
    FILE_FORMATTER = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    config = {
        'version': 1,
        'disable_existing_loggers': False, # 保持现有 logger 启用

        # 1. 格式化器 (Formatters)
        'formatters': {
            'file_formatter': {
                'format': FILE_FORMATTER
            }
            # RichHandler 会自动处理自己的格式
        },

        # 2. 处理器 (Handlers)
        'handlers': {
            # 处理器 A: 控制台 (RichHandler)
            # 对应 main.py
            'console_rich': {
                'class': 'rich.logging.RichHandler', # 必须是完整的导入路径
                'level': 'INFO', # 控制台级别
                'rich_tracebacks': True,
                'show_path': False,
                'markup': True
            },
            
            # 处理器 B: 文件 (FileHandler)
            # 对应 main.py
            'file_handler': {
                'class': 'logging.FileHandler',
                'level': 'DEBUG', # 文件级别
                'formatter': 'file_formatter', # 使用上面定义的格式化器
                'filename': log_file_path, # !! 使用传入的动态路径 !!
                'mode': 'w', # 对应 main.py
                'encoding': 'utf-8' # 对应 main.py
            }
        },

        # 3. 根日志记录器 (Root Logger)
        # 对应 main.py
        'root': {
            'level': 'WARNING', # 根 logger 必须是最低级别
            'handlers': ['console_rich', 'file_handler'] # 应用两个处理器
        },

        # 4. 配置其他 logger
        'loggers': {

            'evaluation':{
                'level': 'DEBUG',
                'handlers': ['console_rich', 'file_handler'],
                'propagate': False
            }

        }

            
        
    }
    return config