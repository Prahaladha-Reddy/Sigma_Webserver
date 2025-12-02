from typing import List
from dotenv import load_dotenv
import os
import boto3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import uvicorn
import json
from datetime import datetime
from src.database import supabase
from src.config import Process,Config,SQSMessage
load_dotenv()
app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION") 
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")

sqs_client = boto3.client(
    'sqs',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION)

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)


class FileMetadata(BaseModel):
    file_name: str
    file_type: str

class BatchPresignedUrlRequest(BaseModel):
    files: List[FileMetadata]

class ChatRequest(BaseModel):
    message: str
    file_ids: List[str] = [] 


@app.post("/generate-presigned-urls")
async def generate_presigned_urls(request: BatchPresignedUrlRequest):
    try:
        response_data = []
        for file in request.files:
            
            url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': AWS_BUCKET_NAME,
                    'Key': file.file_name,
                    'ContentType': file.file_type
                },
                ExpiresIn=3600
            )
            
            response_data.append({
                "original_name": file.file_name,
                "type": file.file_type,
                "key": file.file_name,
                "url": url
            })
            
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        response_text = f"I received your message: '{request.message}'."
        
        if request.file_ids:
            response_text += f" Processing {len(request.file_ids)} file(s) in the background..."
            process_id = str(uuid.uuid4())

            Message_content=SQSMessage(
                file_ids= request.file_ids,
                process_id=process_id,
                user_message= request.message,
                timestamp= datetime.utcnow().isoformat()
            )
            
            sqs_response = sqs_client.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=Message_content.model_dump(),
                MessageAttributes={
                    'MessageType': {
                        'StringValue': 'file_processing',
                        'DataType': 'String'
                    }
                }
            )
            
            process = Process(
                process_id=process_id,
                user_request=request.message,
                files=request.file_ids,
                status="queued"
            )
            supabase.table(Config.Process_table_name).insert(
                process.model_dump()
            ).execute()
            print(f"Message sent to SQS: {sqs_response['MessageId']}")
        
        return {
            "response": response_text,
            "processing_status": "queued" if request.file_ids else "complete"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)