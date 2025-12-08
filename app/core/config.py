import sys
from pathlib import Path
from typing import Any, Optional
from dotenv import find_dotenv
from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]

ENV_PATH = find_dotenv()
if not ENV_PATH:
    print(f"警告：未找到 .env 文件，将仅依赖环境变量。当前根目录: {PROJECT_ROOT}", file=sys.stderr)
else:
    pass

class Settings(BaseSettings):
    """
    应用配置类
    """
    PROJECT_NAME: str = "rag-practice"

    # --- MinIO 配置 ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str 
    MINIO_SECRET_KEY: str 
    MINIO_BUCKET_NAME: str = "rag-knowledge-base"
    MINIO_SECURE: bool = False

    # --- Redis 配置 ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # queue name
    DEFAULT_QUEUE_NAME: str = "arq:queue"
    DOCLING_QUEUE_NAME: str = "docling_queue"
    
    # --- LLM keys ---
    DEFAULT_LLM_MODEL: str = "qwen-flash"
    ZENMUX_API_KEY: str
    ZENMUX_BASE_URL: str = "https://zenmux.ai/api/v1"
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_API_KEY: str
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_API_KEY: str

    #es
    ES_URL: str = "http://elasticsearch:9200"
    ES_INDEX_PREFIX: str = "rag"
    ES_USER: Optional[str] = None
    ES_PASSWORD: Optional[str] = None
    ES_TIMEOUT: int = 30
    EMBEDDING_DIM: int = 1024

    #db
    DATABASE_URL: str

    # retrieval
    RECALL_TOP_K: int = 50
    TOP_K: int = 5
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # evaluation
    TESTSET_SIZE: int = 1
    
    # langfuse
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_HOST: str 
    
    # rerank service
    RERANK_BASE_URL: str = "http://rerank-service:80" 
    RERANK_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"
    RERANK_THRESHOLD: float = 0.0

    # log
    LOG_DIR: Path = PROJECT_ROOT / "logs"

    # security
    SECRET_KEY: str 
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30


    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_async_db_url(cls, v: str | None) -> str:
        if isinstance(v, str):
            
            if v.startswith("postgresql+psycopg2://"):
                return v.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
            
            if v.startswith("postgresql://"):
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @computed_field
    @property
    def LOG_FILE_PATH(self) -> Path:
        return self.LOG_DIR / "project.log"
    
    @computed_field
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    @computed_field
    @property
    def CHUNK_TOKENIZER_ID(self) -> str:
        local_path = PROJECT_ROOT / "language_models" / "paraphrase-multilingual-MiniLM-L12-v2"
        if local_path.exists():
            return str(local_path)
        return "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding='utf-8',
        extra='ignore'
    )

try:
    settings = Settings()#type: ignore
except Exception as e:
    print(f"错误：加载配置失败。\n{e}", file=sys.stderr)
    sys.exit(1)