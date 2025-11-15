import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, Movie, Show, Booking, Session

app = FastAPI(title="Movie Ticket Booking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Simple hash for demo (note: for production use passlib/bcrypt)
import hashlib

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# Auth models
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    token: str
    user_id: str
    name: str
    email: EmailStr


async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = authorization.split(" ", 1)[1]
    session = db["session"].find_one({"token": token, "expires_at": {"$gt": now_utc()}})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid/expired token")
    user = db["user"].find_one({"_id": session["user_id"] if isinstance(session["user_id"], ObjectId) else oid(session["user_id"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user, token


@app.get("/")
def read_root():
    return {"message": "Movie Booking API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set"
            response["database_name"] = getattr(db, 'name', 'unknown')
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
            except Exception as e:
                response["database"] = f"⚠️ Connected but error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# Auth endpoints
@app.post("/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(name=payload.name, email=payload.email, password_hash=hash_password(payload.password))
    user_id = create_document("user", user)
    token = hashlib.sha256(f"{payload.email}{now_utc().isoformat()}".encode()).hexdigest()
    session = Session(user_id=str(user_id), token=token, expires_at=now_utc() + timedelta(days=7))
    create_document("session", session)
    return AuthResponse(token=token, user_id=str(user_id), name=payload.name, email=payload.email)


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    user = db["user"].find_one({"email": payload.email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = hashlib.sha256(f"{payload.email}{now_utc().isoformat()}".encode()).hexdigest()
    session = Session(user_id=str(user["_id"]), token=token, expires_at=now_utc() + timedelta(days=7))
    create_document("session", session)
    return AuthResponse(token=token, user_id=str(user["_id"]), name=user["name"], email=user["email"])


# Movies
class MovieCreate(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: int
    rating: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    genre: List[str] = []

@app.post("/movies")
def create_movie(payload: MovieCreate, user=Depends(get_current_user)):
    movie = Movie(**payload.model_dump())
    mid = create_document("movie", movie)
    return {"id": mid}

@app.get("/movies")
def list_movies():
    movies = get_documents("movie")
    for m in movies:
        m["id"] = str(m.pop("_id"))
    return movies


# Shows
class ShowCreate(BaseModel):
    movie_id: str
    start_time: datetime
    screen: str
    price_cents: int
    rows: int
    cols: int

@app.post("/shows")
def create_show(payload: ShowCreate, user=Depends(get_current_user)):
    # validate movie exists
    movie = db["movie"].find_one({"_id": oid(payload.movie_id)})
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    show = Show(**payload.model_dump(), seats_booked=[])
    sid = create_document("show", show)
    return {"id": sid}

@app.get("/shows")
def list_shows(movie_id: Optional[str] = None):
    q = {"movie_id": movie_id} if movie_id else {}
    shows = get_documents("show", q)
    for s in shows:
        s["id"] = str(s.pop("_id"))
    return shows


# Seat map for a show
@app.get("/shows/{show_id}/seats")
def get_seats(show_id: str):
    show = db["show"].find_one({"_id": oid(show_id)})
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    rows, cols = show["rows"], show["cols"]
    booked = set(show.get("seats_booked", []))
    seats = []
    for r in range(rows):
        row_label = chr(ord('A') + r)
        row = []
        for c in range(1, cols + 1):
            sid = f"{row_label}{c}"
            row.append({"id": sid, "booked": sid in booked})
        seats.append({"row": row_label, "seats": row})
    return {"rows": rows, "cols": cols, "layout": seats}


# Booking
class CreateBookingRequest(BaseModel):
    show_id: str
    seats: List[str]

class CreateBookingResponse(BaseModel):
    booking_id: str
    amount_cents: int
    status: str

@app.post("/bookings", response_model=CreateBookingResponse)
def create_booking(payload: CreateBookingRequest, user=Depends(get_current_user)):
    show = db["show"].find_one({"_id": oid(payload.show_id)})
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    # check seat availability
    booked = set(show.get("seats_booked", []))
    for s in payload.seats:
        if s in booked:
            raise HTTPException(status_code=400, detail=f"Seat {s} already booked")
    amount = len(payload.seats) * int(show["price_cents"])
    booking = Booking(user_id=str(user[0]["_id"]), show_id=payload.show_id, seats=payload.seats, amount_cents=amount)
    bid = create_document("booking", booking)
    # update show booked seats
    db["show"].update_one({"_id": oid(payload.show_id)}, {"$addToSet": {"seats_booked": {"$each": payload.seats}}})
    return CreateBookingResponse(booking_id=str(bid), amount_cents=amount, status="confirmed")


# Public booking view
@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str):
    b = db["booking"].find_one({"_id": oid(booking_id)})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    b["id"] = str(b.pop("_id"))
    return b
