from app.core.config import settings
from sqlmodel import Session, SQLModel, create_engine

engine = create_engine(settings.DATABASE_URL, echo=False)
def create_db_and_tables():
    '''
    辅助函数，用于初始化数据库
    检查数据库表是否存在，不存在则创建  
    '''
    SQLModel.metadata.create_all(engine)
def get_session():
    '''
    辅助函数，用于获取数据库连接
    '''
    with Session(engine) as session:
        yield session
