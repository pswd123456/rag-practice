from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel

if  TYPE_CHECKING:
    from .experiment import Experiment

class Testset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)

    file_path: str = Field(description="MinIO path to the CSV")
    
    status: str = Field(default="PENDING")
    error_message: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(default_factory=datetime.now)

    experiments: List["Experiment"] = Relationship(back_populates="testset")

