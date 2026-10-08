# ```python````
import os
import secrets
import time
import json
import uuid
import sqlite3

from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from google.genai import types


from dotenv import load_dotenv
from google import genai

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    session
)

from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# =========================================================
# LOAD ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 465
app.config["MAIL_USE_TLS"] = False
app.config["MAIL_USE_SSL"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_EMAIL")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

mail = Mail(app)



app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set."
    )

#

# =========================================================
# LOGIN MANAGER
# =========================================================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"


# =========================================================
# FILES / DATABASE
# =========================================================

DATABASE_FILE = "users.db"
HISTORY_FILE = "chat_history.json"


# =========================================================
# GEMINI
# =========================================================

api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=api_key
)


# =========================================================
# USER CLASS
# =========================================================

class User(UserMixin):

    def __init__(
        self,
        user_id,
        name,
        email,
        password
    ):

        self.id = user_id
        self.name = name
        self.email = email
        self.password = password


# =========================================================
# DATABASE
# =========================================================

def init_db():

    conn = sqlite3.connect(DATABASE_FILE)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.commit()

    conn.close()


init_db()


# =========================================================
# LOAD USER
# =========================================================

@login_manager.user_loader
def load_user(user_id):

    conn = sqlite3.connect(DATABASE_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, email, password
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    conn.close()

    if user:

        return User(*user)

    return None


# =========================================================
# HISTORY - LOAD
# =========================================================

def load_history():

    if not os.path.exists(HISTORY_FILE):

        return []


    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)


        if isinstance(data, list):

            return data


        return []


    except (
        json.JSONDecodeError,
        OSError
    ):

        print("History file could not be read.")

        return []


# =========================================================
# HISTORY - SAVE
# =========================================================

def save_history(
    user_id,
    conversation_id,
    question,
    answer
):

    history = load_history()


    # ---------------------------------------------
    # Check whether this conversation already exists
    # ---------------------------------------------

    conversation_exists = any(

        item.get("user_id") == user_id
        and
        item.get("conversation_id") == conversation_id

        for item in history
    )


    # ---------------------------------------------
    # First question becomes conversation title
    # ---------------------------------------------

    title = None

    if not conversation_exists:

        title = question[:60]


    # ---------------------------------------------
    # Add message
    # ---------------------------------------------

    history.append({

        "user_id": user_id,

        "conversation_id": conversation_id,

        "title": title,

        "question": question,

        "answer": answer

    })


    # ---------------------------------------------
    # Save
    # ---------------------------------------------

    try:

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                history,
                file,
                indent=4,
                ensure_ascii=False
            )


        print(
            f"History saved successfully "
            f"for user {user_id}, "
            f"conversation {conversation_id}"
        )


    except OSError as e:

        print(
            "ERROR SAVING HISTORY:",
            e
        )


# =========================================================
# HOME
# =========================================================

@app.route("/")
@login_required
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# SIGNUP PAGE
# =========================================================

@app.route("/signup")
def signup_page():

    return render_template(
        "signup.html"
    )


# =========================================================
# LOGIN PAGE
# =========================================================

@app.route("/login")
def login_page():

    return render_template(
        "login.html"
    )

@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")

@app.route("/forgot-password", methods=["POST"])
def forgot_password():

    data = request.get_json(
        silent=True
    ) or {}

    email = data.get(
        "email",
        ""
    ).strip().lower()

    if not email:
        return jsonify({
            "error": "Email is required."
        }), 400

    conn = sqlite3.connect(
        DATABASE_FILE
    )

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE email = ?",
        (email,)
    )

    user = cursor.fetchone()

    conn.close()

    if not user:
        return jsonify({
            "message":
                "If an account exists with this email, an OTP will be sent."
        })

    # Generate 6-digit OTP
    otp = str(
        secrets.randbelow(900000) + 100000
    )

    # Store OTP in session
    session["reset_email"] = email
    session["reset_otp"] = otp
    session["reset_otp_expiry"] = time.time() + 300
    session["reset_otp_verified"] = False
    session["reset_otp_attempts"] = 0

    # Send OTP email
    msg = Message(
        subject="My AI Assistant - Password Reset OTP",
        sender=os.getenv("MAIL_EMAIL"),
        recipients=[email]
    )

    msg.body = f"""
Hello,

Your password reset OTP for My AI Assistant is:

{otp}

This OTP is valid for 5 minutes.

If you did not request a password reset, please ignore this email.

My AI Assistant
"""

    mail.send(msg)

    return jsonify({
        "message":
            "OTP sent successfully to your registered email."
    })

@app.route("/verify-reset-otp", methods=["POST"])
def verify_reset_otp():

    data = request.get_json(
        silent=True
    ) or {}

    otp = data.get(
        "otp",
        ""
    ).strip()

    if not otp:
        return jsonify({
            "error": "OTP is required."
        }), 400

    saved_otp = session.get(
        "reset_otp"
    )

    expiry = session.get(
        "reset_otp_expiry"
    )

    if not saved_otp or not expiry:
        return jsonify({
            "error": "OTP session expired. Please request a new OTP."
        }), 400

    if time.time() > expiry:

        session.pop(
            "reset_otp",
            None
        )

        session.pop(
            "reset_otp_expiry",
            None
        )

        session.pop(
            "reset_email",
            None
        )

        session.pop(
            "reset_otp_attempts",
            None
        )

        return jsonify({
            "error": "OTP has expired. Please request a new OTP."
        }), 400

    attempts = session.get(
        "reset_otp_attempts",
        0
    )

    if otp != saved_otp:

        attempts += 1

        session["reset_otp_attempts"] = attempts

        if attempts >= 5:

            session.pop(
                "reset_otp",
                None
            )

            session.pop(
                "reset_otp_expiry",
                None
            )

            session.pop(
                "reset_email",
                None
            )

            session.pop(
                "reset_otp_verified",
                None
            )

            session.pop(
                "reset_otp_attempts",
                None
            )

            return jsonify({
                "error":
                    "Too many incorrect attempts. Please request a new OTP."
            }), 400

        return jsonify({
            "error":
                f"Invalid OTP. {5 - attempts} attempts remaining."
        }), 400

    session["reset_otp_verified"] = True

    return jsonify({
        "message": "OTP verified successfully."
    })


@app.route("/reset-password", methods=["GET"])
def reset_password_page():

    if not session.get("reset_otp_verified"):
        return "Please verify the OTP first.", 403

    return render_template(
        "reset_password.html"
    )

@app.route("/reset-password", methods=["POST"])
def reset_password():

    if not session.get("reset_otp_verified"):
        return jsonify({
            "error": "Please verify the OTP first."
        }), 403

    email = session.get(
        "reset_email"
    )

    if not email:
        return jsonify({
            "error": "Password reset session expired."
        }), 400

    data = request.get_json(
        silent=True
    ) or {}

    password = data.get(
        "password",
        ""
    )

    if not password:
        return jsonify({
            "error": "Password is required."
        }), 400

    if len(password) < 6:
        return jsonify({
            "error": "Password must be at least 6 characters."
        }), 400

    hashed_password = generate_password_hash(
        password
    )

    conn = sqlite3.connect(
        DATABASE_FILE
    )

    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE users
        SET password = ?
        WHERE email = ?
        """,
        (
            hashed_password,
            email
        )
    )

    conn.commit()
    conn.close()

    # Clear password reset session
    session.pop("reset_email", None)
    session.pop("reset_otp", None)
    session.pop("reset_otp_expiry", None)
    session.pop("reset_otp_verified", None)

    return jsonify({
        "message":
            "Password reset successfully. You can now login with your new password."
    })

# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    data = request.get_json(
        silent=True
    ) or {}


    email = data.get(
        "email",
        ""
    ).strip().lower()

    password = data.get(
        "password",
        ""
    )


    if not email or not password:

        return jsonify({

            "error":
                "Email and password are required."

        }), 400


    conn = sqlite3.connect(
        DATABASE_FILE
    )

    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT id, name, email, password
        FROM users
        WHERE email = ?
        """,
        (email,)
    )


    user_data = cursor.fetchone()

    conn.close()


    if not user_data:

        return jsonify({

            "error":
                "Invalid email or password."

        }), 401


    user = User(*user_data)


    if not check_password_hash(
        user.password,
        password
    ):

        return jsonify({

            "error":
                "Invalid email or password."

        }), 401


    # Remove old conversation session
    session.pop(
        "conversation_id",
        None
    )


    login_user(user)


    return jsonify({

        "message":
            "Login successful.",

        "name":
            user.name

    })


# =========================================================
# LOGOUT
# =========================================================

@app.route(
    "/logout",
    methods=["POST"]
)
@login_required
def logout():

    logout_user()

    session.pop(
        "conversation_id",
        None
    )


    return jsonify({

        "message":
            "Logged out successfully."

    })


# =========================================================
# CURRENT USER
# =========================================================

@app.route(
    "/me",
    methods=["GET"]
)
@login_required
def get_current_user():

    return jsonify({

        "name":
            current_user.name,

        "email":
            current_user.email

    })


# =========================================================
# SIGNUP
# =========================================================

@app.route(
    "/signup",
    methods=["POST"]
)
def signup():

    data = request.get_json(
        silent=True
    ) or {}

    name = data.get(
        "name",
        ""
    ).strip()

    email = data.get(
        "email",
        ""
    ).strip().lower()

    password = data.get(
        "password",
        ""
    )

    if not name or not email or not password:

        return jsonify({

            "error":
                "All fields are required."

        }), 400

    if len(password) < 6:

        return jsonify({

            "error":
                "Password must be at least 6 characters."

        }), 400

    hashed_password = generate_password_hash(
        password
    )

    try:

        conn = sqlite3.connect(
            DATABASE_FILE
        )

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO users
            (name, email, password)
            VALUES (?, ?, ?)
            """,
            (
                name,
                email,
                hashed_password
            )
        )

        user_id = cursor.lastrowid

        conn.commit()

        conn.close()

    except sqlite3.IntegrityError:

        return jsonify({

            "error":
                "An account with this email already exists."

        }), 409

    # Send new user notification email
    msg = Message(
        subject="New User Registered - My AI Assistant",
        sender=os.getenv("MAIL_EMAIL"),
        recipients=[os.getenv("MAIL_EMAIL")]
    )

    msg.body = f"""
A new user has registered on My AI Assistant.

Name: {name}
Email: {email}
User ID: {user_id}
Registered: {time.strftime("%d-%b-%Y, %I:%M %p")}
"""

    mail.send(msg)

    # Start fresh conversation
    session.pop(
        "conversation_id",
        None
    )

    user = User(
        user_id,
        name,
        email,
        hashed_password
    )

    login_user(user)

    return jsonify({

        "message":
            "Account created successfully.",

        "name":
            user.name

    }), 201


# =========================================================
# CHAT
# =========================================================

@app.route(
    "/chat",
    methods=["POST"]
)
@login_required
def chat():

    # =====================================================
  # TEXT + FILE INPUT
  # =====================================================

      # =====================================================
    # TEXT + FILE INPUT
    # =====================================================

    if request.content_type and request.content_type.startswith("multipart/form-data"):

        question = request.form.get(
            "message",
            ""
        ).strip()

        uploaded_file = request.files.get("file")

        

    else:

        data = request.get_json(
            silent=True
        ) or {}

        question = data.get(
            "message",
            ""
        ).strip()

        uploaded_file = None


    if not question and not uploaded_file:

        return jsonify({
            "error": "Please enter a message or attach a file."
        }), 400

    # =====================================================
    #FILE VALIDATION
    # =====================================================

    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "application/pdf",
    }

    if uploaded_file:

        if uploaded_file.mimetype not in allowed_types:
            return jsonify({
                "error": "Invalid file type. Allowed types: JPEG, PNG, WEBP, GIF, PDF."
            }), 400

        file_bytes = uploaded_file.read()

        if len(file_bytes)>20*1024*1024:
            return jsonify({
                "error": "File size exceeds 20MB limit."
            }), 400


    # =====================================================
    # GET / CREATE CONVERSATION ID
    # =====================================================

    if "conversation_id" not in session:

        session["conversation_id"] = str(
            uuid.uuid4()
        )


    conversation_id = session[
        "conversation_id"
    ]


    print(
        f"User: {current_user.id}"
    )

    print(
        f"Conversation: {conversation_id}"
    )

    print(
        f"Question: {question}"
    )


    # =====================================================
    # LOAD HISTORY
    # =====================================================

    all_history = load_history()


    # =====================================================
    # ONLY CURRENT USER + CURRENT CONVERSATION
    # =====================================================

    current_conversation = [

        item

        for item in all_history

        if (

            item.get("user_id")
            == current_user.id

            and

            item.get("conversation_id")
            == conversation_id

        )

    ]


    # =====================================================
    # GEMINI HISTORY
    # =====================================================

    gemini_history = []


    for item in current_conversation:

        old_question = item.get(
            "question"
        )

        old_answer = item.get(
            "answer"
        )


        if not old_question or not old_answer:

            continue


        gemini_history.append({

            "role":
                "user",

            "parts": [

                {

                    "text":
                        old_question

                }

            ]

        })


        gemini_history.append({

            "role":
                "model",

            "parts": [

                {

                    "text":
                        old_answer

                }

            ]

        })


    # =====================================================
    # GEMINI REQUEST
    # =====================================================

    start_time = time.time()


    try:

        chat_session = client.chats.create(

            model=
                "gemini-3.5-flash-lite",

            history=
                gemini_history

        )

        if uploaded_file:

            parts = []

            if question:
                parts.append(
                    types.Part.from_text(
                        text=question
                    )
                )

            parts.append(
                types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=uploaded_file.mimetype
                )
            )

            response = chat_session.send_message(
                parts
            )

        else:

            response = chat_session.send_message(
                question
            )


        answer = response.text
     

    except Exception as e:

        print(
            "GEMINI ERROR:",
            repr(e)
        )


        return jsonify({

            "error":
                "Sorry, something went wrong. Please try again."

        }), 500


    # =====================================================
    # RESPONSE TIME
    # =====================================================

    end_time = time.time()


    print(
        f"Time taken: "
        f"{end_time - start_time:.2f} seconds"
    )


    # =====================================================
    # SAVE HISTORY
    # =====================================================

    save_history(

        current_user.id,

        conversation_id,

        question,

        answer

    )


    # =====================================================
    # RETURN ANSWER
    # =====================================================

    return jsonify({

        "reply":
            answer,

        "conversation_id":
            conversation_id

    })


# =========================================================
# HISTORY
# =========================================================

@app.route(
    "/history",
    methods=["GET"]
)
@login_required
def history():

    all_history = load_history()


    # =====================================================
    # CURRENT USER ONLY
    # =====================================================

    user_history = [

        item

        for item in all_history

        if item.get("user_id")
        == current_user.id

    ]


    conversations = {}


    # =====================================================
    # GROUP BY CONVERSATION
    # =====================================================

    for item in user_history:

        conversation_id = item.get(
            "conversation_id"
        )


        if not conversation_id:

            continue


        if conversation_id not in conversations:

            conversations[conversation_id] = {

                "conversation_id":
                    conversation_id,

                "title":
                    item.get(
                        "title"
                    )
                    or
                    item.get(
                        "question",
                        "New conversation"
                    )[:60],

                "messages":
                    []

            }


        conversations[
            conversation_id
        ][
            "messages"
        ].append({

            "question":
                item.get(
                    "question",
                    ""
                ),

            "answer":
                item.get(
                    "answer",
                    ""
                )

        })


    return jsonify({

        "history":
            list(
                conversations.values()
            )

    })


# =========================================================
# OPEN CONVERSATION
# =========================================================

@app.route(
    "/conversation/<conversation_id>",
    methods=["GET"]
)
@login_required
def get_conversation(
    conversation_id
):

    all_history = load_history()


    # =====================================================
    # SECURITY CHECK
    # =====================================================

    conversation = [

        item

        for item in all_history

        if (

            item.get("user_id")
            == current_user.id

            and

            item.get("conversation_id")
            == conversation_id

        )

    ]


    if not conversation:

        return jsonify({

            "error":
                "Conversation not found."

        }), 404


    messages = []


    for item in conversation:

        messages.append({

            "question":
                item.get(
                    "question",
                    ""
                ),

            "answer":
                item.get(
                    "answer",
                    ""
                )

        })


    # Set active conversation
    session[
        "conversation_id"
    ] = conversation_id


    return jsonify({

        "conversation_id":
            conversation_id,

        "messages":
            messages

    })


# =========================================================
# CURRENT CHAT
# =========================================================

@app.route(
    "/current-chat",
    methods=["GET"]
)
@login_required
def current_chat():

    if "conversation_id" not in session:

        session["conversation_id"] = str(
            uuid.uuid4()
        )


    return jsonify({

        "conversation_id":
            session[
                "conversation_id"
            ]

    })


# =========================================================
# NEW CHAT
# =========================================================

@app.route(
    "/new-chat",
    methods=["POST"]
)
@login_required
def new_chat():

    conversation_id = str(
        uuid.uuid4()
    )


    session[
        "conversation_id"
    ] = conversation_id


    print(
        f"New conversation created: "
        f"{conversation_id}"
    )


    return jsonify({

        "message":
            "New chat created.",

        "conversation_id":
            conversation_id

    })


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=False
    )

