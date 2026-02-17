# gateway/middleware.py
import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("gateway")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all incoming requests and responses"""
    
    async def dispatch(self, request: Request, call_next):
        # Log request
        start_time = time.time()
        
        # Log request details (without reading body to avoid consuming the stream)
        logger.info(
            f"Request: {request.method} {request.url.path} | "
            f"Client: {request.client.host if request.client else 'unknown'} | "
            f"Query params: {dict(request.query_params)}"
        )
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log exception
            process_time = time.time() - start_time
            logger.error(
                f"Exception: {request.method} {request.url.path} | "
                f"Error: {str(e)} | "
                f"Process time: {process_time:.3f}s"
            )
            raise
        
        # Log response
        process_time = time.time() - start_time
        
        logger.info(
            f"Response: {request.method} {request.url.path} | "
            f"Status: {response.status_code} | "
            f"Process time: {process_time:.3f}s"
        )
        
        return response
