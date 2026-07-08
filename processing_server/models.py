from extensions import db, bcrypt
from datetime import datetime, timezone
import json

def _now():
    return datetime.now(timezone.utc)

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False) 
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    
    videos = db.relationship('Video', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

class Video(db.Model):
    __tablename__ = 'video'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    minio_path = db.Column(db.String(500), nullable=True)
    processed_video_path = db.Column(db.String(500), nullable=True)
    heatmap_video_path = db.Column(db.String(500), nullable=True)
    
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=_now)
    
    # Statistici Generale
    total_unique_people = db.Column(db.Integer, default=0)
    avg_dwell_time_sec = db.Column(db.Float, default=0.0)

    # Statistici DM-Count
    max_people_in_frame = db.Column(db.Integer, default=0)
    avg_people_per_frame = db.Column(db.Float, default=0.0)
    dm_model_used = db.Column(db.String(50), nullable=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relatii
    people_logs = db.relationship('PersonLog', backref='video', lazy=True, cascade="all, delete-orphan")
    multicam_logs = db.relationship('MultiCamLog', backref='video', lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "total_unique_people": self.total_unique_people,
            "created_at": self.created_at.isoformat(),
            "owner": self.owner.username if self.owner else "Unknown"
        }

class GlobalPerson(db.Model):
    """Identitate unica recunoscuta intre mai multe camere."""
    __tablename__ = 'global_people'
    id = db.Column(db.Integer, primary_key=True)
    global_id = db.Column(db.Integer, unique=True, nullable=False) # ID-ul din Re-ID (G1, G2...)
    first_seen = db.Column(db.DateTime, default=_now)
    
    # Legatura cu toate aparitiile in camere
    appearances = db.relationship('MultiCamLog', backref='global_person', lazy=True)

class MultiCamLog(db.Model):
    """Log pentru Dwell Time per camera intr-o sesiune Multi-Camera."""
    __tablename__ = 'multicam_logs'
    id = db.Column(db.Integer, primary_key=True)
    global_person_id = db.Column(db.Integer, db.ForeignKey('global_people.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    camera_name = db.Column(db.String(100))
    
    dwell_time = db.Column(db.Float) # Secunde petrecute in aceasta camera
    enter_frame = db.Column(db.Integer)
    exit_frame = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=_now)

class PersonLog(db.Model):
    """Log local pentru fiecare video (pentru heatmap/traseu)."""
    __tablename__ = 'person_log'
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    track_id = db.Column(db.Integer, nullable=False) 
    start_frame = db.Column(db.Integer) 
    end_frame = db.Column(db.Integer) 
    path_data = db.Column(db.Text, nullable=True) 

    def get_path(self):
        return json.loads(self.path_data) if self.path_data else []