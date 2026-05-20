"""Auth request/response schemas."""
from pydantic import BaseModel, ConfigDict, EmailStr


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "vet@clinic.com",
                "name": "Dr. Sarah Jones",
                "password": "strongpassword123",
            }
        }
    )

    email: EmailStr
    name: str
    password: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"email": "vet@clinic.com", "password": "strongpassword123"}
        }
    )

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
            }
        }
    )

    access_token: str
    token_type: str = "bearer"
