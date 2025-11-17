import sys
from pathlib import Path
from dotenv import find_dotenv
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 根目录计算
ENV_PATH = find_dotenv()
if not ENV_PATH:
    print("错误：未找到 .env 文件。请在项目根目录创建。", file=sys.stderr)
    sys.exit(1)

# 项目根目录
PROJECT_ROOT = Path(ENV_PATH).parent


class Settings(BaseSettings):
    """
    应用配置类
    Pydantic 会自动从 .env 文件和环境变量中读取这些值
    """
    
    # --- 1. 从 .env 读取的 "基础" 变量 ---
    # Pydantic 会自动进行类型转换和验证
    QWEN_BASE_URL: str
    VECTOR_DB_NAME: str
    CHROMADB_COLLECTION_NAME: str
    TOP_K: int
    CHUNK_SIZE: int
    CHUNK_OVERLAP: int
    TESTSET_NAME: str
    TESTSET_SIZE: int
    EVALUATION_FILE_NAME: str
    DATABASE_URL: str
    PROJECT_NAME: str
    
    # --- 2. 不依赖其他配置的 "常量" 路径 ---
    #    这些可以直接使用 PROJECT_ROOT，它们是固定的
    LOG_DIR: Path = PROJECT_ROOT / "logs"
    SOURCH_FILE_DIR: Path = PROJECT_ROOT / "data"
    EMBED_MODEL_DIR: Path = PROJECT_ROOT / "embed_models"

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
    def VECTOR_DB_PERSIST_DIR(self) -> str:
        return str(PROJECT_ROOT / "chromadb" / self.VECTOR_DB_NAME)

    @computed_field
    @property
    def TESTSET_OUTPUT_PATH(self) -> Path:
        return self.SOURCH_FILE_DIR / "testset" / self.TESTSET_NAME
    
    @computed_field
    @property
    def EVALUATION_CSV_PATH(self) -> Path:
        return self.SOURCH_FILE_DIR / "scores" / self.EVALUATION_FILE_NAME

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

