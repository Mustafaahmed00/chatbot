from extensions import db
from flask_login import UserMixin
from datetime import datetime

class Admin(db.Model, UserMixin):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def update_login_timestamp(self):
        self.last_login = datetime.utcnow()
        db.session.commit()

class QA(db.Model):
    __tablename__ = 'qa'  # Explicitly define table name
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(500), unique=True, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    times_asked = db.Column(db.Integer, default=0)
    positive_feedback = db.Column(db.Integer, default=0)
    negative_feedback = db.Column(db.Integer, default=0)
    priority_score = db.Column(db.Float, default=0.0)

    def increment_asked(self):
        self.times_asked += 1
        db.session.commit()

    def add_feedback(self, is_positive):
        if is_positive:
            self.positive_feedback += 1
        else:
            self.negative_feedback += 1
        self._update_priority_score()
        db.session.commit()

    def _update_priority_score(self):
        total_feedback = self.positive_feedback + self.negative_feedback
        if total_feedback > 0:
            positive_ratio = self.positive_feedback / total_feedback
            self.priority_score = positive_ratio * (1 + total_feedback / 100)
        else:
            self.priority_score = 0.0

    def __repr__(self):
        return f'<QA {self.question[:50]}...>'

class ResponseFeedback(db.Model):
    __tablename__ = 'response_feedback'  # Explicitly define table name
    id = db.Column(db.Integer, primary_key=True)
    qa_id = db.Column(db.Integer, db.ForeignKey('qa.id'), nullable=False)
    is_positive = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(db.String(100))
    feedback_metadata = db.Column(db.JSON)

    qa = db.relationship('QA', backref=db.backref('feedbacks', lazy=True))

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_language = db.Column(db.String(10), default='en')
    response_time = db.Column(db.Float)  # Response time in seconds
    
    def __repr__(self):
        return f'<Conversation {self.session_id[:10]}...>'