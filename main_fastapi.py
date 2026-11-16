"""
MediMind Clinical AI - FastAPI Gateway Root Entrypoint
Cho phép khởi chạy uvicorn từ thư mục gốc:
  uvicorn main_fastapi:app --host 0.0.0.0 --port 8000
hoặc:
  uvicorn core.main_fastapi:app --host 0.0.0.0 --port 8000
"""
from core.main_fastapi import app

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("core.main_fastapi:app", host="0.0.0.0", port=port, reload=False)

