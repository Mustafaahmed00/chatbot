from flask import Flask, request, jsonify
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

class CanvasAssistantBot:
    negative_responses = ("nothing", "don't", "stop", "sorry")
    exit_commands = ("quit", "pause", "exit", "goodbye", "bye", "later")

    def __init__(self):
        self.matching_phrases = {
            'greetings': [r'hello', r'hi', r'hey', r'good morning', r'good afternoon', r'good evening'],
            'see_grades': [r'where.*see.*grades', r'how.*find.*grades', r'grades'],
            'see_schedule': [r'where.*see.*class.*schedule', r'how.*find.*class.*schedule', r'schedule'],
            'assignment_deadlines': [r'when.*assignment.*due', r'what.*deadlines.*assignments'],
            'course_announcements': [r'latest.*announcements', r'any.*new.*announcements'],
            'class_locations': [r'where.*next.*class', r'where.*biology.*class'],
            'instructor_info': [r'who.*instructor', r'contact.*professor', r'instructor'],
            'technical_support': [r'trouble.*logging in', r'reset.*password'],
            'course_materials': [r'find.*syllabus', r'access.*lecture notes', r'lecture notes', r'lecture'],
            'library_resources': [r'access.*online library', r'find.*research papers'],
            'event_info': [r'events.*campus', r'workshops.*week'],
            'contact_support': [r'contact.*support', r'customer.*support', r'support']
        }
        self.responses = {
            'greetings': "Hello! Welcome to Canvas Assistant. How can I assist you today?",
            'see_grades': "You can view your grades by navigating to the 'Grades' section in your Canvas course. [Click here to view your grades](https://canvas.instructure.com/courses/YOUR_COURSE_ID/grades).",
            'see_schedule': "You can view your class schedule by navigating to the 'Calendar' section in Canvas. [Click here to view your schedule](https://canvas.instructure.com/calendar).",
            'assignment_deadlines': "You can check assignment deadlines in the 'Assignments' section of your Canvas course. [Click here to view your assignments](https://canvas.instructure.com/courses/YOUR_COURSE_ID/assignments).",
            'course_announcements': "You can find the latest announcements in the 'Announcements' section of your Canvas course. [Click here to view announcements](https://canvas.instructure.com/courses/YOUR_COURSE_ID/announcements).",
            'class_locations': "Class locations are usually listed in the course syllabus or under the 'Location' section in your course details.",
            'instructor_info': "You can find your instructor's contact information in the 'People' section of your Canvas course. [Click here to view instructor info](https://canvas.instructure.com/courses/YOUR_COURSE_ID/users).",
            'technical_support': "For technical issues, please contact the Canvas support team at support@canvas.com or visit the IT helpdesk.",
            'course_materials': "Course materials like the syllabus and lecture notes can be found in the 'Files' or 'Modules' section of your Canvas course. [Click here to view course materials](https://canvas.instructure.com/courses/YOUR_COURSE_ID/files).",
            'library_resources': "You can access the online library through the university's library website or through the 'Library Resources' link in Canvas. [Click here to access the library](https://library.youruniversity.edu).",
            'event_info': "Campus events and workshops are listed on the university's events page or in the 'Events' section of Canvas. [Click here to view events](https://canvas.instructure.com/calendar).",
            'contact_support': "If you need further assistance, please contact the Canvas support team at support@canvas.com."
        }

    def get_response(self, message):
        for key, patterns in self.matching_phrases.items():
            for pattern in patterns:
                if re.search(pattern, message.lower()):
                    return self.responses[key]
        return "I did not understand you. Can you please ask your question again?"

chatbot = CanvasAssistantBot()

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.json.get('message')
    response = chatbot.get_response(user_input)
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True)
