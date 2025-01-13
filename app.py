import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user

from extensions import db, bcrypt, login_manager, migrate
from models import Admin, QA, ResponseFeedback
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

migrate.init_app(app, db)

# Configure Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("No GEMINI_API_KEY set for the application")
genai.configure(api_key=GEMINI_API_KEY)

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.get_json()
        response_id = data.get('responseId')
        is_positive = data.get('isPositive')
        session_id = data.get('sessionId')
        metadata = data.get('metadata', {})

        qa = QA.query.get(response_id)
        if not QA.query.filter_by(question="test question").first():
            test_qa = QA(
            question="test question",
            answer="Hi! Here's a test answer.\n\n- This is a test bullet point\n- Here's another one\n- Is there anything else you'd like to know?",
        )
        db.session.add(test_qa)
        db.session.commit()

        # Create feedback record
        feedback = ResponseFeedback(
            qa_id=response_id,
            is_positive=is_positive,
            session_id=session_id,
            metadata=metadata
        )
        db.session.add(feedback)

        # Update QA feedback counts and score
        qa.add_feedback(is_positive)
        
        db.session.commit()
        return jsonify({'message': 'Feedback recorded successfully'}), 200

    except Exception as e:
        print(f"Error recording feedback: {str(e)}")
        return jsonify({'error': 'Failed to record feedback'}), 500

@app.route('/get_response', methods=['POST'])
def get_response():
    user_input = request.form.get('message', '').strip().lower()
    print(f"Received input: {user_input}")  # Debug log
    
    try:
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "max_output_tokens": 500,
        }

        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-exp",
            generation_config=generation_config,
        )

        chat_session = model.start_chat()

        prompt = f"""
        As a Canvas LMS expert, provide a helpful response to this question about Canvas. Your response must:
        1. Start with "Hi!" or a similar greeting on the first line
        2. Follow with a brief introduction sentence
        3. Use ONLY dash/hyphen (-) for bullet points (not *, • or **)
        4. Put each bullet point on a new line
        5. Replace any ** with bullet points using -
        
        Question: {user_input}
        """

        response = chat_session.send_message(prompt)
        answer = response.text.strip()
        
        # Save the response to database
        new_qa = QA(
            question=user_input,
            answer=answer
        )
        db.session.add(new_qa)
        db.session.commit()
        print(f"Saved response with ID: {new_qa.id}")  # Debug log
        
        # Remove any ** markers and convert to proper bullet points
        answer = answer.replace('**', '')
        
        # Convert lines starting with asterisks to bullet points
        lines = answer.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith('*'):
                line = '- ' + line[1:].strip()
            formatted_lines.append(line)
        
        answer = '\n'.join(formatted_lines)
        
        # Add follow-up prompt if not present
        if not any(line.strip().lower().endswith('?') for line in answer.split('\n')):
            answer += "\n\n- Is there anything specific you'd like me to clarify?"

        return jsonify({
            'answer': answer,
            'responseId': new_qa.id  # Now we're returning the actual response ID
        })

    except Exception as e:
        print(f"Error: {str(e)}")  # Debug log
        error_response = """Hi! I apologize, but I'm having trouble right now.

- Please try asking your question again
- Make sure your question is about Canvas LMS
- Try rephrasing your question
- Break down complex questions into simpler ones"""
        
        return jsonify({
            'answer': error_response,
            'responseId': None
        })

    except Exception as e:
        print(f"Error: {str(e)}")
        error_response = """Hi! I apologize, but I'm having trouble right now.

- Please try asking your question again
- Make sure your question is about Canvas LMS
- Try rephrasing your question
- Break down complex questions into simpler ones"""
        
        return jsonify({
            'answer': error_response,
            'responseId': None
        })

    except Exception as e:
        print(f"Error: {str(e)}")
        error_response = """Hi! I apologize, but I'm having trouble right now.

- Please try asking your question again
- Make sure your question is about Canvas LMS
- Try rephrasing your question
- Break down complex questions into simpler ones"""
        
        return jsonify({
            'answer': error_response,
            'responseId': None
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