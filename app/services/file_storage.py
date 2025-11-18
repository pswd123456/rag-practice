import shutil
from pathlib import Path
from fastapi import UploadFile
import uuid
from app.core.config import settings

def save_upload_file(upload_file: UploadFile, knowledge_id: int) -> str:
    
    base_path = settings.SOURCH_FILE_DIR/ "uploads" / str(knowledge_id)

    # 确定存在
    base_path.mkdir(parents=True, exist_ok=True)

    # 生成一个唯一存在的文件名
    file_suffix = Path(upload_file.filename).suffix if upload_file.filename else ""
    safe_filename = f"{uuid.uuid4()}{file_suffix}"

    file_path = base_path / safe_filename

    try: 
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
    finally:
        upload_file.file.close()

    return str(file_path.absolute())
