import os
import json
import textwrap
import google.generativeai as genai
import pandas as pd
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, abort
from flask_cors import CORS
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from wtforms import StringField, PasswordField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Email
from flask_wtf import FlaskForm
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, HumanMessagePromptTemplate, SystemMessagePromptTemplate

load_dotenv()

import joblib



# --- App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key')
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # On Render, the DATABASE_URL is for a PostgreSQL database.
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url.replace('postgres://', 'postgresql://')
else:
    # For local development, use a SQLite database.
    instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
    os.makedirs(instance_path, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'database.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
try:
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT'))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS').lower() in ['true', 'on', '1']
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
except (TypeError, AttributeError):
    print("Warning: Mail server not configured. Email functionality will be disabled.")

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
CORS(app)




model = joblib.load('budget_model.joblib')
model_columns = joblib.load('model_columns.joblib')

# Read the Gemini API key from the environment
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY environment variable not set. AI features will not work.")
else:
    genai.configure(api_key=GEMINI_API_KEY)


# --- Database Models ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    confirmed = db.Column(db.Boolean, nullable=False, default=False)
    projects = db.relationship('Project', backref='author', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    script_text = db.Column(db.Text, nullable=False)
    analysis_json = db.Column(db.Text, nullable=True)
    genre = db.Column(db.String(50), nullable=True) # New column
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    budget_items = db.relationship('Budget', backref='project', lazy=True)

class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    history = db.Column(db.Text, nullable=False, default='[]')
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, unique=True)
    project = db.relationship('Project', backref=db.backref('conversation', uselist=False))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Token Generation and Email Sending ---
def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='email-confirmation-salt')

def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt='email-confirmation-salt',
            max_age=expiration
        )
    except SignatureExpired:
        return None
    return email

def send_email(to, subject, template):
    msg = Message(
        subject,
        recipients=[to],
        html=template,
        sender=app.config['MAIL_DEFAULT_SENDER']
    )
    mail.send(msg)

# Custom Jinja2 filter to parse JSON
@app.template_filter('from_json')
def from_json_filter(value):
    if value is None:
        return None
    return json.loads(value)


# --- Forms ---
class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is taken. Please choose a different one.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ProjectForm(FlaskForm):
    name = StringField('Project Name', validators=[DataRequired()])
    script_text = TextAreaField('Script Text', validators=[DataRequired()])
    submit = SubmitField('Create Project')


# --- Database Initialization ---
@app.cli.command('init-db')
def init_db_command():
    """Creates the database tables."""
    db.create_all()
    print('Initialized the database.')


# --- Routes for the Frontend ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('list_projects'))
    return render_template('index.html')

@app.route('/script_analysis')
@login_required
def script_analysis():
    project_id = request.args.get('project_id', type=int)
    project = None
    if project_id:
        project = Project.query.get_or_404(project_id)
        if project.author != current_user:
            abort(403) # Forbidden
    return render_template('script_analysis.html', project=project)



@app.route('/budget_oversight/<int:project_id>')
@login_required
def budget_oversight(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden
    budget_items = Budget.query.filter_by(project_id=project.id).all()
    return render_template('budget_oversight.html', project=project, budget_items=budget_items)

@app.route("/projects", methods=['GET'])
@login_required
def list_projects():
    projects = Project.query.filter_by(author=current_user).all()
    return render_template('projects.html', projects=projects)

@app.route("/projects/new", methods=['GET', 'POST'])
@login_required
def create_project():
    form = ProjectForm()
    if form.validate_on_submit():
        project = Project(name=form.name.data, script_text=form.script_text.data, author=current_user)
        db.session.add(project)
        db.session.commit()
        flash('Your project has been created!', 'success')
        return redirect(url_for('list_projects'))
    return render_template('create_project.html', title='New Project', form=form)

@app.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden
    return render_template('project_detail.html', project=project)

# --- Authentication Routes ---
@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(email=form.email.data, password=hashed_password, confirmed=False)
        db.session.add(user)
        db.session.commit()

        token = generate_confirmation_token(user.email)
        confirm_url = url_for('confirm_email', token=token, _external=True)
        html = render_template('email/activate.html', confirm_url=confirm_url)
        subject = "Please confirm your email"
        send_email(user.email, subject, html)

        flash('A confirmation email has been sent via email.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        email = confirm_token(token)
    except:
        flash('The confirmation link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))
    user = User.query.filter_by(email=email).first_or_404()
    if user.confirmed:
        flash('Account already confirmed. Please login.', 'success')
    else:
        user.confirmed = True
        db.session.add(user)
        db.session.commit()
        flash('You have confirmed your account. Thanks!', 'success')
    return redirect(url_for('index'))


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            if user.confirmed:
                login_user(user, remember=True)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('index'))
            else:
                flash('Please confirm your account first.', 'warning')
                return redirect(url_for('login'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('index'))


# --- Mock API Endpoints ---

@app.route('/api/script/analyze', methods=['POST'])
@login_required
def analyze_script():
    """
    Endpoint to perform AI script analysis using the Gemini API.
    """
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured on the server."}), 500

    project_id = request.get_json().get('project_id')
    script_text = request.get_json().get('script')

    if not project_id:
        return jsonify({"error": "Project ID is required for script analysis."}), 400

    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    if not script_text or not isinstance(script_text, str) or len(script_text.strip()) < 50:
        return jsonify({"error": "Invalid or insufficient script text provided."}), 400

    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        prompt = textwrap.dedent("""
            You are a professional script breakdown assistant for film production.
            Analyze the following script text and return a JSON object with the following structure:
            {{"genre": "FILM_GENRE",
            "characters": [{{"name": "CHARACTER_NAME", "dialogue_lines": COUNT}}],
            "locations": [{{"name": "LOCATION_NAME", "scenes": COUNT}}],
            "props": ["PROP_NAME_1", "PROP_NAME_2"],
            "estimated_scenes": TOTAL_SCENE_COUNT}}
            The "genre" should be one of the following: "Action", "Comedy", "Drama", "Horror", "Sci-Fi", "Thriller", "Romance", "Adventure", "Musical", "Indie".
            Only return the raw JSON object, with no surrounding text, comments, or markdown.
            Ensure the JSON is valid.
            Script: {script}
        """).format(script=script_text)

        response = model.generate_content(prompt)

        # Check if the response was blocked
        if response.prompt_feedback.block_reason:
            return jsonify({
                "error": "The AI request was blocked by the content filter.",
                "reason": response.prompt_feedback.block_reason.name,
            }), 500

        full_response_text = response.candidates[0].content.parts[0].text
        cleaned_response = full_response_text.strip().replace('```json', '').replace('```', '').strip()
        try:
            analysis_result = json.loads(cleaned_response)
            project.analysis_json = json.dumps(analysis_result) # Save analysis to project
            project.genre = analysis_result.get('genre') # Save the genre
            db.session.commit()
            return jsonify(analysis_result)
        except json.JSONDecodeError:
            # The AI didn't return valid JSON, log the bad response for debugging
            print("--- DEBUG: AI response was not valid JSON ---")
            print(cleaned_response)
            print("---------------------------------------------")
            return jsonify({"error": "Failed to parse the analysis from the AI response. The AI did not return valid JSON.", "raw_response_for_debugging": cleaned_response}), 500

    except Exception as e:
        # Catch other potential errors from the API call itself
        print(f"--- DEBUG: An unexpected error occurred: {e} ---")
        return jsonify({"error": f"An unexpected error occurred during the AI API call: {str(e)}"}), 500



@app.route('/api/budget/expenses/<int:project_id>', methods=['GET', 'POST', 'DELETE'])
@login_required
def handle_expenses(project_id):
    """
    Endpoint to manage the expense list for a specific project.
    GET returns the list, POST adds a new expense, DELETE removes an expense.
    """
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    if request.method == 'POST':
        data = request.get_json()
        new_expense = Budget(
            description=data['description'],
            amount=data['amount'],
            project=project
        )
        db.session.add(new_expense)
        db.session.commit()
        return jsonify({"id": new_expense.id, "description": new_expense.description, "amount": new_expense.amount}), 201
    elif request.method == 'DELETE':
        expense_id = request.get_json().get('id')
        expense = Budget.query.get_or_404(expense_id)
        if expense.project != project:
            abort(403) # Forbidden
        db.session.delete(expense)
        db.session.commit()
        return jsonify({"message": "Expense deleted."}), 200
    else: # GET request
        expenses_data = [{
            "id": item.id,
            "description": item.description,
            "amount": item.amount
        } for item in project.budget_items]
        return jsonify(expenses_data)

@app.route('/api/budget/generate_from_script', methods=['POST'])
@login_required
def generate_budget_from_script():
    """
    Endpoint to generate a budget from a script analysis for a specific project.
    """
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured on the server."}), 500

    project_id = request.get_json().get('project_id')
    if not project_id:
        return jsonify({"error": "Project ID is required for budget generation."}), 400

    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    if not project.analysis_json:
        return jsonify({"error": "Script analysis not found for this project. Please analyze the script first."}), 400

    script_analysis_data = json.loads(project.analysis_json)

    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        prompt = textwrap.dedent("""
            You are a professional line producer for film. Based on the following script breakdown, 
            generate a list of estimated expenses in JSON format. The list should be comprehensive and 
            include common pre-production, production, and post-production costs. For each expense, 
            provide a description and a rough estimated cost.
            **Script Breakdown:**
            ```json
            {script_analysis}
            ```
            **Output Format:**
            ```json
            {{
              "expenses": [
                {{"description": "Location Scouting", "amount": 5000}},
                {{"description": "Casting Director Fees", "amount": 7500}}
              ]
            }}
            ```
        """).format(script_analysis=json.dumps(script_analysis_data, indent=2))

        response = model.generate_content(prompt)

        if response.prompt_feedback.block_reason:
            return jsonify({
                "error": "The AI request was blocked by the content filter.",
                "reason": response.prompt_feedback.block_reason.name,
            }), 500

        full_response_text = response.candidates[0].content.parts[0].text
        # Find the start of the JSON object
        json_start_index = full_response_text.find('{')
        if json_start_index == -1:
            # Handle case where no JSON object is found
            print("--- DEBUG: No JSON object found in AI response for budget generation ---")
            print(full_response_text)
            print("--------------------------------------------------------------------")
            return jsonify({
                "error": "Failed to find a valid JSON object in the AI response.",
                "raw_response_for_debugging": full_response_text
            }), 500
            
        json_string = full_response_text[json_start_index:]
        cleaned_response = json_string.strip().replace('```json', '').replace('```', '').strip()
        try:
            budget_data = json.loads(cleaned_response)
            
            # Clear existing budget items for the project
            Budget.query.filter_by(project_id=project.id).delete()
            db.session.commit()

            # Add new budget items
            for expense in budget_data.get("expenses", []):
                amount = expense.get("amount")
                if amount is not None and isinstance(amount, (int, float)) and "---" not in expense["description"] and amount > 0:
                    new_expense = Budget(
                        description=expense["description"],
                        amount=expense["amount"],
                        project=project
                    )
                    db.session.add(new_expense)
            db.session.commit()

            return jsonify({"message": "Budget generated successfully."})
        except (json.JSONDecodeError, KeyError) as e:
            print(f"--- DEBUG: AI response for budget generation was not valid JSON or had wrong structure: {e} ---")
            print(cleaned_response)
            print("------------------------------------------------------------------------------------")
            return jsonify({
                "error": "Failed to parse the budget from the AI response.",
                "raw_response_for_debugging": cleaned_response
            }), 500

    except Exception as e:
        print(f"--- DEBUG: An unexpected error occurred during budget generation: {e} ---")
        return jsonify({"error": f"An unexpected error occurred during the AI API call: {str(e)}"}), 500





@app.route('/api/budget/predict/<int:project_id>', methods=['POST'])
@login_required
def predict_budget(project_id):
    """
    Endpoint to predict a budget from script analysis data for a specific project.
    """
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    if not project.analysis_json:
        return jsonify({"error": "Script analysis not found for this project. Please analyze the script first."}), 400

    script_analysis_data = json.loads(project.analysis_json)
    
    # Add the genre from the project model to the data for prediction
    if project.genre:
        script_analysis_data['genre'] = project.genre

    try:
        # Create a DataFrame from the input data
        input_data = pd.DataFrame([script_analysis_data])
        
        # One-hot encode the 'genre' column
        input_data_encoded = pd.get_dummies(input_data, columns=['genre'])
        
        # Align the columns with the model's columns
        print(f"--- DEBUG: Model Columns: {model_columns} ---")
        print(f"--- DEBUG: Input Columns: {input_data_encoded.columns} ---")
        input_data_aligned = input_data_encoded.reindex(columns=model_columns, fill_value=0)
        print(f"--- DEBUG: Aligned Input Data: {input_data_aligned.to_string()} ---")
        
        # Predict the budget
        prediction = model.predict(input_data_aligned)
        
        return jsonify({"predicted_budget": prediction[0]})

    except Exception as e:
        print(f"--- DEBUG: An unexpected error occurred during budget prediction: {e} ---")
        return jsonify({"error": f"An unexpected error occurred during budget prediction: {str(e)}"}), 500


@app.route('/api/budget/copilot/history/<int:project_id>', methods=['GET'])
@login_required
def get_history(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403)

    if not project.conversation:
        # Create a conversation history if it doesn't exist
        conversation = Conversation(project=project, history='[{"role": "ai", "text": "Hello! I\'m your AI Budget Copilot. How can I help you refine your budget today?"}]')
        db.session.add(conversation)
        db.session.commit()

    history_json = json.loads(project.conversation.history)
    return jsonify(history_json)


@app.route('/api/budget/copilot/<int:project_id>', methods=['POST'])
@login_required
def budget_copilot(project_id):
    """
    Endpoint for the AI Budget Copilot, now with persistent memory.
    """
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403)

    data = request.get_json()
    user_message = data.get('message')
    budget_context = data.get('budget')

    if not user_message or not budget_context:
        return jsonify({"error": "Invalid request. Message and budget context are required."}), 400

    # Get or create the conversation history from the database
    if not project.conversation:
        conversation = Conversation(project=project, history='[]')
        db.session.add(conversation)
        db.session.commit()
    else:
        conversation = project.conversation

    history_json = json.loads(conversation.history)
    
    # Create a LangChain memory object from the stored history
    chat_history = ChatMessageHistory()
    for message in history_json:
        if message['role'] == 'user':
            chat_history.add_user_message(message['text'])
        else:
            chat_history.add_ai_message(message['text'])

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro", google_api_key=GEMINI_API_KEY, convert_system_message_to_human=True)
    memory = ConversationBufferMemory(chat_memory=chat_history, return_messages=True)
    prompt = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(
            "You are a helpful and experienced line producer acting as an AI budget copilot for a film project. "
            "Your role is to help the user refine their budget based on their requests. "
            "You must respond with a JSON object. The JSON object should have two keys: 'reply' and 'action'. "
            "'reply' should be a string containing your text response to the user. "
            "'action' should be a JSON object describing the action to be taken, or null if no action is needed. "
            "The 'action' object can have the following 'type': 'add_item'. "
            "For 'add_item', the 'action' object should also include an 'item' object with 'description' and 'amount'."
        ),
        MessagesPlaceholder(variable_name="history"),
        HumanMessagePromptTemplate.from_template("{input}")
    ])
    chain = ConversationChain(memory=memory, prompt=prompt, llm=llm)

    input_message = f"""
    Here is the current state of the budget:
    - Forecasted Budget: ${budget_context.get('forecasted', 0):,.2f}
    - Current Expenses: {json.dumps(budget_context.get('expenses', []), indent=2)}

    The user sent the following message:
    "{user_message}"

    Based on the user's message, the conversation history, and the budget context, provide a helpful reply in the specified JSON format.
    """

    try:
        response_text = chain.predict(input=input_message)
        
        try:
            cleaned_response = response_text.strip().replace('```json', '').replace('```', '').strip()
            response_data = json.loads(cleaned_response)
            action = response_data.get('action')

            if action:
                action_type = action.get('type')
                if action_type == 'add_item':
                    item_data = action.get('item')
                    if item_data and 'description' in item_data and 'amount' in item_data:
                        new_expense = Budget(
                            description=item_data['description'],
                            amount=item_data['amount'],
                            project=project
                        )
                        db.session.add(new_expense)
                        db.session.commit()
            
            # Save the updated history back to the database
            history_json.append({"role": "user", "text": user_message})
            history_json.append({"role": "ai", "text": response_data.get('reply')})
            conversation.history = json.dumps(history_json)
            db.session.commit()

            return jsonify(response_data)

        except json.JSONDecodeError:
            print(f"--- DEBUG: AI response was not valid JSON: {response_text} ---")
            return jsonify({"reply": response_text, "action": None})

    except Exception as e:
        print(f"--- DEBUG: An unexpected error occurred with the AI Copilot: {e} ---")
        return jsonify({"error": f"An unexpected error occurred with the AI Copilot: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
