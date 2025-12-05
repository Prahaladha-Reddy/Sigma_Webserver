from typing import List, Optional
from dotenv import load_dotenv
import os
import boto3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import uvicorn
import json
from datetime import datetime, timezone
from urllib.parse import urlparse  
from src.database import supabase
from src.config import Process, Config, SQSMessage

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "https://sigma-frontend-self.vercel.app"
                   "https://*.vercel.app"],
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
    "sqs",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
)

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
)

class FileMetadata(BaseModel):
    file_name: str
    file_type: str

class BatchPresignedUrlRequest(BaseModel):
    files: List[FileMetadata]

class ChatRequest(BaseModel):
    message: str
    file_ids: List[str] = []
    num_slides: int = 15
    user_id: str

class DownloadUrlRequest(BaseModel):
    file_url: str  

@app.post("/generate-presigned-urls")
async def generate_presigned_urls(request: BatchPresignedUrlRequest):
    try:
        response_data = []

        for file in request.files:
            url = s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": AWS_BUCKET_NAME,
                    "Key": file.file_name,
                    "ContentType": file.file_type,
                },
                ExpiresIn=3600,
            )

            response_data.append(
                {
                    "original_name": file.file_name,
                    "type": file.file_type,
                    "key": file.file_name,
                    "url": url,
                }
            )

        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-download-url")
async def generate_download_url(request: DownloadUrlRequest):

    try:
        raw = request.file_url.strip()

        parsed = urlparse(raw)

        if parsed.scheme and parsed.netloc:
            key = parsed.path.lstrip("/")
        else:
            key = raw

        if not key:
            raise HTTPException(status_code=400, detail="Could not extract S3 key from file_url")

        download_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_BUCKET_NAME, "Key": key},
            ExpiresIn=3600,  
        )

        return {
            "key": key,
            "download_url": download_url,
            "expires_in": 3600,
        }

    except Exception as e:
        print(f"Error generating download URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        process_id = str(uuid.uuid4())
        current_time = datetime.now(timezone.utc).isoformat()

        Message_content = SQSMessage(
            file_ids=request.file_ids if request.file_ids else [],
            process_id=process_id,
            user_message=request.message,
            timestamp=current_time,
            num_slides=request.num_slides,
        )

        sqs_response = sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=Message_content.model_dump_json(),
            MessageAttributes={
                "MessageType": {
                    "StringValue": "file_processing", 
                    "DataType": "String",
                }
            },
        )

        process = Process(
            process_id=process_id,
            user_request=request.message,
            files=request.file_ids if request.file_ids else [],
            status="queued",
            num_slides=request.num_slides,
            user_id=request.user_id
        )

        supabase.table(Config.Process_table_name).insert(
            process.model_dump()
        ).execute()

        print(f"Job sent to SQS: {sqs_response['MessageId']}")

        return {
            "response": "Job started successfully",
            "process_id": process_id, 
            "processing_status": "queued"
        }


    except Exception as e:
        print(f"Server Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
