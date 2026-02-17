# gateway/main.py
from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from typing import Any, Optional
from auth import authenticate_user, create_access_token, get_current_active_user, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta
from middleware import LoggingMiddleware
import logging

logger = logging.getLogger("gateway")

app = FastAPI(title="API Gateway", version="1.0.0")

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs
SERVICES = {
    "student": "http://localhost:8001",
    "course": "http://localhost:8002"
}


class LoginRequest(BaseModel):
    username: str
    password: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int
    timestamp: str


async def forward_request(service: str, path: str, method: str, **kwargs) -> Any:
    """Forward request to the appropriate microservice with enhanced error handling"""
    if service not in SERVICES:
        logger.error(f"Service '{service}' not found in registry")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Service Not Found",
                "message": f"The requested service '{service}' is not available",
                "available_services": list(SERVICES.keys())
            }
        )

    url = f"{SERVICES[service]}{path}"
    logger.info(f"Forwarding {method} request to {service} service: {url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if method == "GET":
                response = await client.get(url, **kwargs)
            elif method == "POST":
                response = await client.post(url, **kwargs)
            elif method == "PUT":
                response = await client.put(url, **kwargs)
            elif method == "DELETE":
                response = await client.delete(url, **kwargs)
            else:
                raise HTTPException(
                    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                    detail={
                        "error": "Method Not Allowed",
                        "message": f"HTTP method '{method}' is not supported",
                        "allowed_methods": ["GET", "POST", "PUT", "DELETE"]
                    }
                )
            
            # Handle different response status codes
            if response.status_code >= 400:
                error_detail = None
                try:
                    error_detail = response.json()
                except:
                    error_detail = {"detail": response.text or "Unknown error"}
                
                logger.warning(f"Service {service} returned error: {response.status_code} - {error_detail}")
                
                raise HTTPException(
                    status_code=response.status_code,
                    detail={
                        "error": f"Service Error ({response.status_code})",
                        "message": error_detail.get("detail", "An error occurred in the microservice"),
                        "service": service,
                        "path": path
                    }
                )
            
            # Return successful response
            response_data = None
            if response.text:
                try:
                    response_data = response.json()
                except:
                    response_data = {"raw": response.text}
            
            return JSONResponse(
                content=response_data,
                status_code=response.status_code
            )
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout connecting to {service} service: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "error": "Gateway Timeout",
                    "message": f"The {service} service did not respond in time",
                    "service": service,
                    "timeout": "30 seconds"
                }
            )
        except httpx.ConnectError as e:
            logger.error(f"Connection error to {service} service: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "Service Unavailable",
                    "message": f"Unable to connect to {service} service. Please check if the service is running.",
                    "service": service,
                    "url": url
                }
            )
        except httpx.RequestError as e:
            logger.error(f"Request error to {service} service: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "Bad Gateway",
                    "message": f"Error communicating with {service} service",
                    "service": service,
                    "error_details": str(e)
                }
            )
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected error forwarding request to {service}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "Internal Server Error",
                    "message": "An unexpected error occurred while processing your request",
                    "service": service
                }
            )


@app.get("/")
def read_root():
    return {
        "message": "API Gateway is running",
        "available_services": list(SERVICES.keys()),
        "version": "1.0.0"
    }


# Authentication endpoints
@app.post("/gateway/auth/login", status_code=status.HTTP_200_OK)
async def login(login_data: LoginRequest):
    """Authenticate user and return JWT token"""
    user = authenticate_user(login_data.username, login_data.password)
    if not user:
        logger.warning(f"Failed login attempt for username: {login_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Authentication Failed",
                "message": "Invalid username or password"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    
    logger.info(f"Successful login for user: {user['username']}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "username": user["username"],
            "role": user["role"]
        }
    }


@app.get("/gateway/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_active_user)):
    """Get current authenticated user information"""
    return {
        "username": current_user["username"],
        "role": current_user["role"]
    }


# Student Service Routes (Protected)
@app.get("/gateway/students")
async def get_all_students(current_user: dict = Depends(get_current_active_user)):
    """Get all students through gateway"""
    return await forward_request("student", "/api/students", "GET")


@app.get("/gateway/students/{student_id}")
async def get_student(student_id: int, current_user: dict = Depends(get_current_active_user)):
    """Get a student by ID through gateway"""
    return await forward_request("student", f"/api/students/{student_id}", "GET")


@app.post("/gateway/students")
async def create_student(request: Request, current_user: dict = Depends(get_current_active_user)):
    """Create a new student through gateway"""
    body = await request.json()
    return await forward_request("student", "/api/students", "POST", json=body)


@app.put("/gateway/students/{student_id}")
async def update_student(student_id: int, request: Request, current_user: dict = Depends(get_current_active_user)):
    """Update a student through gateway"""
    body = await request.json()
    return await forward_request("student", f"/api/students/{student_id}", "PUT", json=body)


@app.delete("/gateway/students/{student_id}")
async def delete_student(student_id: int, current_user: dict = Depends(get_current_active_user)):
    """Delete a student through gateway"""
    return await forward_request("student", f"/api/students/{student_id}", "DELETE")


# Course Service Routes (Protected)
@app.get("/gateway/courses")
async def get_all_courses(current_user: dict = Depends(get_current_active_user)):
    """Get all courses through gateway"""
    return await forward_request("course", "/api/courses", "GET")


@app.get("/gateway/courses/{course_id}")
async def get_course(course_id: int, current_user: dict = Depends(get_current_active_user)):
    """Get a course by ID through gateway"""
    return await forward_request("course", f"/api/courses/{course_id}", "GET")


@app.post("/gateway/courses")
async def create_course(request: Request, current_user: dict = Depends(get_current_active_user)):
    """Create a new course through gateway"""
    body = await request.json()
    return await forward_request("course", "/api/courses", "POST", json=body)


@app.put("/gateway/courses/{course_id}")
async def update_course(course_id: int, request: Request, current_user: dict = Depends(get_current_active_user)):
    """Update a course through gateway"""
    body = await request.json()
    return await forward_request("course", f"/api/courses/{course_id}", "PUT", json=body)


@app.delete("/gateway/courses/{course_id}")
async def delete_course(course_id: int, current_user: dict = Depends(get_current_active_user)):
    """Delete a course through gateway"""
    return await forward_request("course", f"/api/courses/{course_id}", "DELETE")


# Global exception handler for better error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Enhanced HTTP exception handler"""
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail.get("error", "Error") if isinstance(exc.detail, dict) else "Error",
            "message": exc.detail.get("message", exc.detail) if isinstance(exc.detail, dict) else exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path)
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unexpected errors"""
    logger.exception(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
            "status_code": 500,
            "path": str(request.url.path)
        }
    )
