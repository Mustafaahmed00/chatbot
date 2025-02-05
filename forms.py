from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, EqualTo, Optional, ValidationError
import re

class AdminLoginForm(FlaskForm):
    username = StringField('Username', 
                         validators=[DataRequired(), Length(min=4, max=100)],
                         render_kw={"placeholder": "Enter username", "class": "form-input"})
    password = PasswordField('Password', 
                           validators=[DataRequired(), Length(min=4)],
                           render_kw={"placeholder": "Enter password", "class": "form-input"})
    submit = SubmitField('Login', 
                        render_kw={"class": "btn btn-primary w-full"})

class AddQAForm(FlaskForm):
    question = StringField('Question', 
                         validators=[DataRequired(), Length(min=10, max=500)],
                         render_kw={"placeholder": "Enter the question", "class": "form-input"})
    answer = TextAreaField('Answer', 
                         validators=[DataRequired(), Length(min=20)],
                         render_kw={"placeholder": "Enter the answer", "rows": 5, "class": "form-input"})
    submit = SubmitField('Save Q&A',
                        render_kw={"class": "btn btn-primary"})

    def validate_question(self, field):
        # Remove multiple spaces and normalize whitespace
        field.data = ' '.join(field.data.split())
        
        # Check if question ends with a question mark
        if not field.data.endswith('?'):
            raise ValidationError('Question must end with a question mark.')

class EditAdminForm(FlaskForm):
    username = StringField('New Username', 
                         validators=[DataRequired(), Length(min=4, max=100)],
                         render_kw={"placeholder": "Enter new username", "class": "form-input"})
    
    password = PasswordField('New Password', 
                           validators=[Optional(), Length(min=6)],
                           render_kw={"placeholder": "Enter new password", "class": "form-input"})
    
    confirm_password = PasswordField('Confirm New Password',
                                   validators=[EqualTo('password', message='Passwords must match')],
                                   render_kw={"placeholder": "Confirm new password", "class": "form-input"})
    
    submit = SubmitField('Update Profile',
                        render_kw={"class": "btn btn-primary w-full"})

    def validate_password(self, field):
        if field.data:
            # Check password strength
            if len(field.data) < 8:
                raise ValidationError('Password must be at least 8 characters long.')
            if not re.search(r"[A-Z]", field.data):
                raise ValidationError('Password must contain at least one uppercase letter.')
            if not re.search(r"[a-z]", field.data):
                raise ValidationError('Password must contain at least one lowercase letter.')
            if not re.search(r"\d", field.data):
                raise ValidationError('Password must contain at least one number.')
            if not re.search(r"[ !@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", field.data):
                raise ValidationError('Password must contain at least one special character.')