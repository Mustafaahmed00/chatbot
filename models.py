from extensions import db
from flask_login import UserMixin
from datetime import datetime

class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def update_login_timestamp(self):
        self.last_login = datetime.utcnow()
        db.session.commit()

class QA(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(500), unique=True, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    times_asked = db.Column(db.Integer, default=0)

    def increment_asked(self):
        self.times_asked += 1
        db.session.commit()
        
    def __repr__(self):
        return f'<QA {self.question[:50]}...>'