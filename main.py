from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr

from database import SessionLocal, init_db, Event, Category, User, Registration

app = FastAPI(title="University Event Management System")
templates = Jinja2Templates(directory="templates")

# DB Session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def startup_event():
    init_db()

# Pydantic Schemas for Validation
class EventCreate(BaseModel):
    title: str
    description: str
    date: datetime
    location: str
    max_participants: int
    category_id: int

class UserCreate(BaseModel):
    name: str
    email: EmailStr

class RegistrationCreate(BaseModel):
    user_id: int
    event_id: int

# --- FRONTEND ROUTE ---
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    events = db.query(Event).all()
    categories = db.query(Category).all()
    total_events = len(events)
    total_registrations = db.query(Registration).count()
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "events": events, 
        "categories": categories,
        "total_events": total_events,
        "total_registrations": total_registrations
    })

# --- API ENDPOINTS ---

@app.post("/api/categories/", status_code=status.HTTP_201_CREATED)
def create_category(name: str, db: Session = Depends(get_db)):
    existing = db.query(Category).filter(Category.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu kateqoriya artıq mövcuddur.")
    category = Category(name=name)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category

@app.post("/api/events/", status_code=status.HTTP_201_CREATED)
def create_event(event: EventCreate, db: Session = Depends(get_db)):
    if event.max_participants <= 0:
        raise HTTPException(status_code=400, detail="İştirakçı limiti 0-dan böyük olmalıdır.")
    if event.date < datetime.now():
        raise HTTPException(status_code=400, detail="Keçmiş tarixə tədbir yaratmaq olmaz.")
    
    db_event = Event(**event.dict())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@app.get("/api/events/")
def get_events(search: Optional[str] = None, category_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Event)
    if search:
        query = query.filter(Event.title.contains(search) | Event.location.contains(search))
    if category_id:
        query = query.filter(Event.category_id == category_id)
    return query.all()

@app.post("/api/users/", status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        return existing # Əgər istifadəçi varsa mövcud olanı qaytar
    db_user = User(**user.dict())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/api/registrations/", status_code=status.HTTP_201_CREATED)
def register_to_event(reg: RegistrationCreate, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == reg.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Tədbir tapılmadı.")
    
    user = db.query(User).filter(User.id == reg.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="İstifadəçi tapılmadı.")
    
    # Limit yoxlaması
    current_reg_count = db.query(Registration).filter(Registration.event_id == reg.event_id).count()
    if current_reg_count >= event.max_participants:
        raise HTTPException(status_code=400, detail="Tədbirin iştirakçı limiti dolub.")
    
    # Təkrar qeydiyyat yoxlaması
    existing_reg = db.query(Registration).filter(
        Registration.user_id == reg.user_id, 
        Registration.event_id == reg.event_id
    ).first()
    if existing_reg:
        raise HTTPException(status_code=400, detail="Bu istifadəçi artıq bu tədbirə qeydiyyatdan keçib.")
    
    db_reg = Registration(user_id=reg.user_id, event_id=reg.event_id)
    db.add(db_reg)
    db.commit()
    db.refresh(db_reg)
    return {"message": "Qeydiyyat uğurla tamamlandı!", "registration_id": db_reg.id}

@app.delete("/api/registrations/{reg_id}")
def cancel_registration(reg_id: int, db: Session = Depends(get_db)):
    reg = db.query(Registration).filter(Registration.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Qeydiyyat tapılmadı.")
    db.delete(reg)
    db.commit()
    return {"message": "Qeydiyyat ləğv edildi."}

@app.get("/api/statistics/")
def get_statistics(db: Session = Depends(get_db)):
    total_events = db.query(Event).count()
    total_registrations = db.query(Registration).count()
    
    # Ən çox qeydiyyat olan tədbir
    events = db.query(Event).all()
    popular_event = max(events, key=lambda e: len(e.registrations), default=None)
    
    return {
        "total_events": total_events,
        "total_registrations": total_registrations,
        "most_popular_event": popular_event.title if popular_event else "Yoxdur"
    }