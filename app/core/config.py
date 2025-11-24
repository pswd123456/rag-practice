import sys
from pathlib import Path
from dotenv import find_dotenv
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 尝试加载 .env 文件 (如果有的话)，没有也不报错，依靠环境变量
ENV_PATH = find_dotenv()
if not ENV_PATH:
    # 在 Docker 生产环境中，可能没有 .env 文件，而是直接通过环境变量注入
    # 所以这里改为 Warning 或直接 pass，不再 sys.exit(1)
    print(f"警告：未找到 .env 文件，将仅依赖环境变量。当前根目录: {PROJECT_ROOT}", file=sys.stderr)
else:
    pass

class Settings(BaseSettings):
    """
    应用配置类
    Pydantic 会自动从 .env 文件和环境变量中读取这些值
    """
    
    PROJECT_NAME: str = "rag-practice"

    # --- MinIO 配置 ---
    MINIO_ENDPOINT: str = "localhost:9000" # Docker Desktop 映射到 localhost
    MINIO_ACCESS_KEY: str 
    MINIO_SECRET_KEY: str 
    MINIO_BUCKET_NAME: str = "rag-knowledge-base"
    MINIO_SECURE: bool = False # 本地开发通常用 HTTP (False)

    # --- Redis 配置 ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # --- 1. 从 .env 读取的 "基础" 变量 ---
    # Pydantic 会自动进行类型转换和验证
    
    # llm keys

    DEFAULT_LLM_MODEL: str = "qwen-flash"

    ZENMUX_API_KEY: str
    ZENMUX_BASE_URL: str = "https://zenmux.ai/api/v1"

    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_API_KEY: str

    # db
    CHROMA_SERVER_HOST: str  
    CHROMA_SERVER_PORT: int = 8000
    DATABASE_URL: str

    # retrieval
    TOP_K: int
    CHUNK_SIZE: int
    CHUNK_OVERLAP: int

    # evaluation
    TESTSET_SIZE: int
    
    # langfuse
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_HOST: str 
    
    # --- 2. 不依赖其他配置的 "常量" 路径 ---
    #    这些可以直接使用 PROJECT_ROOT，它们是固定的
    LOG_DIR: Path = PROJECT_ROOT / "logs"
    # EMBED_MODEL_DIR: Path = PROJECT_ROOT / "embed_models"

    # --- 3. "派生" 的配置 (使用 @computed_field) ---
    #    这些字段的值依赖于上面从 .env 加载的字段
    #    使用 @computed_field 可以让它们在实例创建后被计算
    #    并且像普通属性一样被访问
    
    @computed_field
    @property
    def LOG_FILE_PATH(self) -> Path:
        return self.LOG_DIR / "project.log"
    
    @computed_field
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"
    

    # --- 4. 配置Pydantic-Settings ---
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,        # 明确告诉 Pydantic 加载哪个 .env 文件
        env_file_encoding='utf-8', # 编码
        extra='ignore'            # 忽略 .env 中多余的变量
    )

# --- 5. 创建一个全局单例 ---
# 在应用启动时，Pydantic 会执行一次读取和验证
# 如果 .env 里的 TOP_K 写成了 "abc"，程序会在这里立即报错
try:
    settings = Settings()#type: ignore
except Exception as e:
    print(f"错误：加载配置失败。\n{e}", file=sys.stderr)
    sys.exit(1)

