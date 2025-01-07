import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user

from extensions import db, bcrypt, login_manager
from models import Admin, QA
from forms import AdminLoginForm, AddQAForm, EditAdminForm

import google.generativeai as genai

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_default_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

# Configure Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("No GEMINI_API_KEY set for the application")
genai.configure(api_key=GEMINI_API_KEY)

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

@app.before_first_request
def create_tables():
    db.create_all()
    if not Admin.query.first():
        admin_username = os.environ.get('ADMIN_USERNAME')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        if not admin_username or not admin_password:
            raise ValueError("No admin credentials set")
        hashed_password = bcrypt.generate_password_hash(admin_password).decode('utf-8')
        admin = Admin(username=admin_username, password=hashed_password)
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_response', methods=['POST'])
def get_response():
    user_input = request.form.get('message', '').strip().lower()
    
    # Handle greetings
    greetings = ['hi', 'hello', 'hey', 'hola', 'greetings']
    if user_input in greetings:
        return jsonify({
            'answer': """Hi! I'm your Canvas assistant. Here's how I can help you:
- Ask questions about Canvas features and functionality
- Get help with assignments, grades, and course materials
- Learn about Canvas tools and settings
- Get step-by-step guidance for common tasks

What would you like to know about?"""
        })

    # Check database for answer
    qa = QA.query.filter_by(question=user_input).first()
    if qa:
        answer = qa.answer
        if not any(line.strip().startswith('-') for line in answer.split('\n')):
            sentences = [s.strip() for s in answer.split('.') if s.strip()]
            answer = '\n'.join([f"- {s}." for s in sentences])
        return jsonify({'answer': answer})

    try:
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "max_output_tokens": 500,
        }

        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
        )

        chat_session = model.start_chat()

        prompt = f"""
        As a Canvas LMS expert, please provide a helpful and friendly response to the following question. Your response should:
        - Always start with a brief greeting or acknowledgment
        - Break down the information into clear bullet points using "-" at the start of each point
        - Use a conversational, friendly tone
        - Focus on Canvas LMS features and functionality
        - Include specific steps or examples when relevant
        - End with a gentle prompt for follow-up questions
        
        Format each main point as a new bullet point starting with "-".
        
        Question: {user_input}
        """

        response = chat_session.send_message(prompt)
        answer = response.text.strip()
        
        # Ensure response has bullet points
        if not any(line.strip().startswith('-') for line in answer.split('\n')):
            sentences = [s.strip() for s in answer.split('.') if s.strip()]
            answer = '\n'.join([f"- {s}." for s in sentences])
        
        # Add follow-up prompt if not present
        if not answer.lower().endswith('?'):
            answer += "\n\n- Is there anything specific you'd like me to clarify?"

        return jsonify({'answer': answer})

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            'answer': """I apologize, but I'm having trouble processing your request right now. Here are some suggestions:
- Please try asking your question again
- Make sure your question is specific to Canvas LMS
- Try breaking down complex questions into simpler ones"""
        })

# Admin routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        admin = Admin.query.filter_by(username=form.username.data).first()
        if admin and bcrypt.check_password_hash(admin.password, form.password.data):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        flash('Invalid username or password', 'danger')
    return render_template('admin/login.html', form=form)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    qas = QA.query.all()
    return render_template('admin/dashboard.html', qas=qas)

@app.route('/admin/add', methods=['GET', 'POST'])
@login_required
def add_qa():
    form = AddQAForm()
    if form.validate_on_submit():
        qa = QA(question=form.question.data.lower(), answer=form.answer.data)
        db.session.add(qa)
        db.session.commit()
        flash('Q&A added successfully', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/add_qa.html', form=form)

@app.route('/admin/edit/<int:qa_id>', methods=['GET', 'POST'])
@login_required
def edit_qa(qa_id):
    qa = QA.query.get_or_404(qa_id)
    form = AddQAForm()
    if form.validate_on_submit():
        qa.question = form.question.data.lower()
        qa.answer = form.answer.data
        db.session.commit()
        flash('Q&A updated successfully', 'success')
        return redirect(url_for('admin_dashboard'))
    elif request.method == 'GET':
        form.question.data = qa.question
        form.answer.data = qa.answer
    return render_template('admin/edit_qa.html', form=form)

@app.route('/admin/delete/<int:qa_id>', methods=['POST'])
@login_required
def delete_qa(qa_id):
    qa = QA.query.get_or_404(qa_id)
    db.session.delete(qa)
    db.session.commit()
    flash('Q&A deleted successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)