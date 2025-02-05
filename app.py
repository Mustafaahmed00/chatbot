import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from langid import classify as detect_language
from google.cloud import translate_v2 as translate
import google.generativeai as genai
import logging

from extensions import db, bcrypt, login_manager, migrate
from models import Admin, QA, ResponseFeedback
from forms import AdminLoginForm, AddQAForm, EditAdminForm

# Load environment variables first
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

# Initialize Google Cloud Translation client
try:
    translate_client = translate.Client.from_service_account_json(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
    logging.info("Translation client initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing translation client: {e}")
    exit(1)

# Configure Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("No GEMINI_API_KEY set for the application")
genai.configure(api_key=GEMINI_API_KEY)


# Configure logging
logging.basicConfig(level=logging.DEBUG)

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
        if not qa:
            return jsonify({'error': 'Invalid response ID'}), 400

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
        logging.error(f"Error recording feedback: {str(e)}")
        return jsonify({'error': 'Failed to record feedback'}), 500

# Function to translate text
def translate_text(text, target_language="en"):
    try:
        translation = translate_client.translate(text, target_language=target_language)
        return translation['translatedText']
    except Exception as e:
        logging.error(f"Translation error: {e}")
        return f"Translation error: {str(e)}"

@app.route('/get_response', methods=['POST'])
def get_response():
    user_input = request.form.get('message', '').strip().lower()
    
    # First, check for exact match
    existing_qa = QA.query.filter_by(question=user_input).first()
    
    # If no exact match, try similar questions using SQL LIKE
    if not existing_qa:
        similar_questions = QA.query.filter(
            QA.question.like(f"%{user_input}%")
        ).first()
        if similar_questions:
            existing_qa = similar_questions

    if existing_qa:
        logging.info(f"Found answer in database for: {user_input}")
        return jsonify({
            'answer': existing_qa.answer,
            'responseId': existing_qa.id,
            'responseLang': 'en'
        })
    
    # If no match found in database, proceed with language detection and Gemini
    try:
        user_lang, _ = detect_language(user_input)
        logging.debug(f"Detected user language: {user_lang}")
    except Exception as e:
        logging.error(f"Language detection error: {e}")
        user_lang = 'en'
    
    # Translate the input to English for processing
    if user_lang != 'en':
        try:
            translated_input = translate_text(user_input, target_language="en")
            logging.debug(f"Translated input: {translated_input}")
        except Exception as e:
            logging.error(f"Translation error: {e}")
            translated_input = user_input
    else:
        translated_input = user_input
    
    # Process the translated input
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

        prompt = f""" As a Canvas LMS expert, provide a helpful response to this question about Canvas. Your response must: 
        1. Start with "Hi!" or a similar greeting on the first line 
        2. Follow with a brief introduction sentence 
        3. Use ONLY dash/hyphen (-) for bullet points (not *, • or **) 
        4. Put each bullet point on a new line 
        5. Replace any ** with bullet points using - 
        6. Only answer questions about Canvas LMS 
        7. If including links, format them as follows:    
         -Start a new section with "Helpful Resources:"    
         -Each resource on a new line starting with "-"    
         -Put the link description first, no Parentheses
         -include Helpful Resources links with every answer   
        Helpful Resources:    
         -Official Canvas Student Guide https://www.umb.edu/it/training-classroom-support/canvas-resources-for-students    
         -UMB Canvas Support Page https://cases.canvaslms.com/liveagentchat?chattype=student&sfid=A5WgTEKARcWFY5IXRv5FT8ePIss19I2qCvHxwOtD 
         -include these links with every answer
         Question: {translated_input} """

        response = chat_session.send_message(prompt)
        answer = response.text.strip()
        
        # Translate the response back to the user's language
        if user_lang != 'en':
            try:
                answer = translate_text(answer, target_language=user_lang)
                logging.debug(f"Translated response: {answer}")
            except Exception as e:
                logging.error(f"Translation error: {e}")
        
        # Save the response to the database
        new_qa = QA(
            question=user_input,
            answer=answer
        )
        db.session.add(new_qa)
        db.session.commit()
        
        # Format the answer with bullet points
        answer = answer.replace('**', '')
        lines = answer.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith('*'):
                line = '- ' + line[1:].strip()
            formatted_lines.append(line)
        
        answer = '\n'.join(formatted_lines)
        
        # Add follow-up prompt if not present (translate it to the user's language)
        follow_up_prompt = "Is there anything specific you'd like me to clarify?"
        if user_lang != 'en':
            try:
                follow_up_prompt = translate_text(follow_up_prompt, target_language=user_lang)
            except Exception as e:
                logging.error(f"Translation error: {e}")
        answer += f"\n\n- {follow_up_prompt}"

        # Detect the language of the final response
        response_lang, _ = detect_language(answer)
        logging.debug(f"Detected response language: {response_lang}")

        return jsonify({
            'answer': answer,
            'responseId': new_qa.id,
            'responseLang': response_lang  # Return the detected language
        })

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        error_response = """Hi! I apologize, but I'm having trouble right now.

- Please try asking your question again
- Make sure your question is about Canvas LMS
- Try rephrasing your question
- Break down complex questions into simpler ones

Helpful Resources:
- Canvas Student Guide (https://community.canvaslms.com/t5/Canvas-Student-Guide/tkb-p/student)
- UMB Canvas Support (https://www.umb.edu/canvas/)
- Canvas Video Tutorials (https://community.canvaslms.com/t5/Video-Guide/tkb-p/videos)"""
        
        # Translate the error response to the user's language
        if user_lang != 'en':
            try:
                error_response = translate_text(error_response, target_language=user_lang)
            except Exception as e:
                logging.error(f"Translation error: {e}")
        
        return jsonify({
            'answer': error_response,
            'responseId': None,
            'responseLang': user_lang  # Return the user's language for error responses
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
        try:
            qa.question = form.question.data.lower().strip()
            qa.answer = form.answer.data.strip()
            db.session.commit()
            flash('Q&A updated successfully', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating Q&A: {str(e)}', 'danger')
    
    # For GET request, populate form with existing data
    elif request.method == 'GET':
        form.question.data = qa.question
        form.answer.data = qa.answer
    
    # Pass both form and qa_id to template
    return render_template('admin/edit_qa.html', form=form, qa_id=qa_id, qa=qa)

@app.route('/admin/delete/<int:qa_id>', methods=['POST'])
@login_required
def delete_qa(qa_id):
    qa = QA.query.get_or_404(qa_id)
    db.session.delete(qa)
    db.session.commit()
    flash('Q&A deleted successfully', 'success')
    return redirect(url_for('admin_dashboard'))

# In app.py, add this route
@app.route('/admin/feedback_stats')
@login_required
def feedback_stats():
    qas = QA.query.order_by(QA.priority_score.desc()).all()
    return render_template('admin/feedback_stats.html', qas=qas)

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Create the database tables
    with app.app_context():
        db.create_all()
        
        # Create admin user if it doesn't exist
        admin_username = os.getenv('ADMIN_USERNAME')
        admin_password = os.getenv('ADMIN_PASSWORD')
        
        if admin_username and admin_password:
            admin = Admin.query.filter_by(username=admin_username).first()
            if not admin:
                logging.info(f"Creating new admin user with username: {admin_username}")
                hashed_password = bcrypt.generate_password_hash(admin_password).decode('utf-8')
                admin = Admin(username=admin_username, password=hashed_password)
                db.session.add(admin)
                db.session.commit()
                logging.info(f"Admin user '{admin_username}' created successfully")
            else:
                logging.info(f"Admin user '{admin_username}' already exists")
        else:
            logging.error("ADMIN_USERNAME or ADMIN_PASSWORD not set in environment variables")
    
    # Run the application
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)