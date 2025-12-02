from pydantic import BaseModel
from typing import Dict, Any, List

class Config(BaseModel):
  Process_table_name: str = "Process"

class Process(BaseModel):
    process_id: str
    user_request:str
    files: Dict[str, Any]
    status:str

class SQSMessage(BaseModel):
  file_ids: List[str]
  process_id:str
  user_message: str
  timestamp: str