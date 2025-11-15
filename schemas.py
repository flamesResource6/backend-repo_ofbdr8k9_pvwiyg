"""
Database Schemas for Movie Booking App

Each Pydantic model maps to a MongoDB collection named by the lowercase of the class name.
- User -> "user"
- Movie -> "movie"
- Show -> "show"
- Booking -> "booking"
- Session -> "session"
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="BCrypt hash of the password")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Movie(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., ge=1)
    rating: Optional[str] = Field(None, description="e.g., PG-13")
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    genre: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Show(BaseModel):
    movie_id: str = Field(..., description="ObjectId as string of the movie")
    start_time: datetime
    screen: str
    price_cents: int = Field(..., ge=0)
    rows: int = Field(..., ge=1, le=20)
    cols: int = Field(..., ge=1, le=30)
    seats_booked: List[str] = Field(default_factory=list, description="Seat IDs like A1, B5")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Booking(BaseModel):
    user_id: str
    show_id: str
    seats: List[str]
    amount_cents: int
    status: str = Field("confirmed", description="confirmed|cancelled")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Session(BaseModel):
    user_id: str
    token: str
    expires_at: datetime
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
