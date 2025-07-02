import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_file
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from langid import classify as detect_language
from google.cloud import translate_v2 as translate
import google.generativeai as genai
import logging
import tempfile
from gtts import gTTS
import io
import time
import json
from datetime import datetime, timedelta
from functools import wraps

from extensions import db, bcrypt, login_manager, migrate
from models import Admin, QA, ResponseFeedback, Conversation
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

# Simple cache for frequently asked questions
qa_cache = {}

def cache_response(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        cache_key = f"{args}_{kwargs}"
        if cache_key in qa_cache:
            return qa_cache[cache_key]
        result = func(*args, **kwargs)
        qa_cache[cache_key] = result
        return result
    return wrapper

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
    start_time = time.time()
    
    user_input = request.form.get('message', '').strip().lower()
    session_id = request.form.get('session_id', generate_session_id())
    
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
        existing_qa.increment_asked()
        
        # Track conversation
        response_time = time.time() - start_time
        conversation = Conversation(
            session_id=session_id,
            user_message=user_input,
            bot_response=existing_qa.answer,
            response_time=response_time
        )
        db.session.add(conversation)
        db.session.commit()
        
        return jsonify({
            'answer': existing_qa.answer,
            'responseId': existing_qa.id,
            'responseLang': 'en',
            'sessionId': session_id
        })
    
    # If no match found in database, proceed with language detection and Gemini
    try:
        user_lang, _ = detect_language(user_input)
        logging.debug(f"Detected user language: {user_lang}")
    except Exception as e:
        logging.error(f"Language detection error: {e}")
        user_lang = 'en'
    
    # Get conversation context
    recent_context = Conversation.query.filter_by(session_id=session_id).order_by(Conversation.created_at.desc()).limit(3).all()
    context_messages = []
    for conv in reversed(recent_context):
        context_messages.append(f"User: {conv.user_message}")
        context_messages.append(f"Bot: {conv.bot_response}")
    
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

        # Build context-aware prompt
        context_text = "\n".join(context_messages) if context_messages else "No previous context"
        
        prompt = f""" As a Canvas LMS expert, provide a helpful response to this question about Canvas. 

Previous conversation context:
{context_text}

Your response must: 
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
        
        # Track conversation
        response_time = time.time() - start_time
        conversation = Conversation(
            session_id=session_id,
            user_message=user_input,
            bot_response=answer,
            user_language=user_lang,
            response_time=response_time
        )
        db.session.add(conversation)
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
            'responseLang': response_lang,  # Return the detected language
            'sessionId': session_id
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
            'responseLang': user_lang,  # Return the user's language for error responses
            'sessionId': session_id
        })

def generate_session_id():
    import random
    import string
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

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

@app.route('/admin/feedback_stats')
@login_required
def feedback_stats():
    qas = QA.query.order_by(QA.priority_score.desc()).all()
    return render_template('admin/feedback_stats.html', qas=qas)

@app.route('/admin/analytics')
@login_required
def analytics():
    # Get basic statistics
    total_conversations = Conversation.query.count()
    total_feedback = ResponseFeedback.query.count()
    positive_feedback = ResponseFeedback.query.filter_by(is_positive=True).count()
    negative_feedback = ResponseFeedback.query.filter_by(is_positive=False).count()
    
    # Get recent conversations
    recent_conversations = Conversation.query.order_by(Conversation.created_at.desc()).limit(10).all()
    
    # Get popular questions
    popular_questions = QA.query.order_by(QA.times_asked.desc()).limit(5).all()
    
    analytics_data = {
        'total_conversations': total_conversations,
        'total_feedback': total_feedback,
        'positive_feedback': positive_feedback,
        'negative_feedback': negative_feedback,
        'satisfaction_rate': (positive_feedback / total_feedback * 100) if total_feedback > 0 else 0,
        'recent_conversations': recent_conversations,
        'popular_questions': popular_questions
    }
    
    return render_template('admin/analytics.html', analytics=analytics_data)

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/text_to_speech', methods=['POST'])
def text_to_speech():
    data = request.get_json()
    text = data.get('text')
    if not text:
        return jsonify({'error': 'No text provided'}), 400

    try:
        tts = gTTS(text=text, lang='en')
        with tempfile.TemporaryFile(mode='wb') as f:
            tts.write_to_fp(f)
            f.seek(0)
            audio_data = f.read()

        return send_file(io.BytesIO(audio_data), mimetype='audio/mp3', as_attachment=True, download_name='output.mp3')
    except Exception as e:
        logging.error(f"Error generating text-to-speech: {str(e)}")
        return jsonify({'error': 'Failed to generate text-to-speech'}), 500

@app.route('/admin/export_data')
@login_required
def export_data():
    """Export conversation and feedback data as JSON"""
    try:
        # Get all conversations
        conversations = Conversation.query.all()
        conv_data = []
        for conv in conversations:
            conv_data.append({
                'session_id': conv.session_id,
                'user_message': conv.user_message,
                'bot_response': conv.bot_response,
                'user_language': conv.user_language,
                'response_time': conv.response_time,
                'created_at': conv.created_at.isoformat()
            })
        
        # Get all feedback
        feedback = ResponseFeedback.query.all()
        feedback_data = []
        for fb in feedback:
            feedback_data.append({
                'qa_id': fb.qa_id,
                'is_positive': fb.is_positive,
                'session_id': fb.session_id,
                'created_at': fb.created_at.isoformat(),
                'metadata': fb.feedback_metadata
            })
        
        export_data = {
            'export_date': datetime.utcnow().isoformat(),
            'conversations': conv_data,
            'feedback': feedback_data
        }
        
        return jsonify(export_data)
    except Exception as e:
        logging.error(f"Error exporting data: {str(e)}")
        return jsonify({'error': 'Failed to export data'}), 500

@app.route('/admin/clear_cache')
@login_required
def clear_cache():
    """Clear the QA cache"""
    global qa_cache
    qa_cache.clear()
    return jsonify({'message': 'Cache cleared successfully'})

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Check database connection
        db.session.execute('SELECT 1')
        
        # Check API keys
        gemini_ok = bool(GEMINI_API_KEY)
        translate_ok = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
        
        # Get basic stats
        total_qa = QA.query.count()
        total_conversations = Conversation.query.count()
        
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'services': {
                'database': 'ok',
                'gemini_api': 'ok' if gemini_ok else 'error',
                'translate_api': 'ok' if translate_ok else 'error'
            },
            'stats': {
                'total_qa': total_qa,
                'total_conversations': total_conversations,
                'cache_size': len(qa_cache)
            }
        }
        
        return jsonify(health_status), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/admin/performance')
@login_required
def performance_stats():
    """Performance statistics for admin dashboard"""
    try:
        # Get response time statistics
        conversations = Conversation.query.filter(
            Conversation.response_time.isnot(None)
        ).all()
        
        if conversations:
            response_times = [conv.response_time for conv in conversations]
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0
        
        # Get daily conversation counts for the last 7 days
        daily_stats = []
        for i in range(7):
            date = datetime.utcnow() - timedelta(days=i)
            count = Conversation.query.filter(
                db.func.date(Conversation.created_at) == date.date()
            ).count()
            daily_stats.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count
            })
        
        performance_data = {
            'response_times': {
                'average': round(avg_response_time, 2),
                'minimum': round(min_response_time, 2),
                'maximum': round(max_response_time, 2),
                'total_requests': len(conversations)
            },
            'daily_stats': list(reversed(daily_stats)),
            'cache_stats': {
                'cache_size': len(qa_cache),
                'cache_hit_rate': 'N/A'  # Would need more sophisticated tracking
            }
        }
        
        return jsonify(performance_data)
    except Exception as e:
        logging.error(f"Error getting performance stats: {str(e)}")
        return jsonify({'error': 'Failed to get performance stats'}), 500

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