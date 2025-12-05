from pydantic import BaseModel
from typing import List, Optional


class Config:
    Process_table_name = "Process"


class SQSMessage(BaseModel):
    file_ids: List[str]
    process_id: str
    user_message: str
    timestamp: str
    num_slides: int


class Process(BaseModel):
    process_id: str
    user_request: str
    files: Optional[List[str]] = None
    status: str
    num_slides: int 