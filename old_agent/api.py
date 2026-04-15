from flask import Flask, request, Response, jsonify, session
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from agent_logic import setup_agent, setup_external_agent, SYSTEM_PROMPT
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from models import db, bcrypt, User, APIKey, SystemSetting
from functools import wraps
import json
import time
import secrets
import datetime 
import traceback
import sqlite3
import os
import threading
import logging # Added logging module
from ldap3 import Server, Connection, ALL, NTLM

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('ENVIRONMENT') == 'prod'

def get_system_setting(key, default=None):
    """Helper to get setting from DB, fallback to Env, then default."""
    try:
        with app.app_context():
            setting = SystemSetting.query.get(key)
            if setting and setting.value:
                return setting.value
    except Exception:
        pass
    return os.environ.get(key, default)

def check_ldap_credentials(username, password):
    ldap_host = get_system_setting('LDAP_HOST')
    ldap_domain = get_system_setting('LDAP_DOMAIN')
    ldap_bind_user = get_system_setting('LDAP_BIND_USER')
    ldap_bind_password = get_system_setting('LDAP_BIND_PASSWORD')
    
    if not ldap_host:
        return False
    
    try:
        if ldap_domain:
            user_dn = f"{ldap_domain}\\{username}"
        else:
            user_dn = username
            
        server = Server(ldap_host, get_info=ALL)
        # Note: Currently using user creds for binding directly (NTLM/AD typical)
        # If bind_user is provided, we might use it for search, but here we authenticate the user.
        conn = Connection(server, user=user_dn, password=password, authentication=NTLM, auto_bind=True)
        
        if conn.bind():
            conn.unbind()
            return True
        return False
    except Exception as e:
        logger.error(f"LDAP Auth Error: {e}")
        return False

CORS(app, supports_credentials=True, origins='*')

db.init_app(app)
bcrypt.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({'error': 'Authentication required', 'redirect': '/static/login.html'}), 401

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

from sqlalchemy.exc import IntegrityError

with app.app_context():
    db.create_all()
    try:
        if User.query.count() == 0:
            admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            logger.info(f"Default admin user created: username='admin'")
    except IntegrityError:
        db.session.rollback()
        logger.info("Admin user already exists")

graph = setup_agent() 

if hasattr(graph.checkpointer, 'setup'):
    graph.checkpointer.setup()

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401

        key = APIKey.query.filter_by(key=api_key, is_active=True).first()
        if not key:
            return jsonify({'error': 'Invalid API key'}), 401

        key.last_used = datetime.datetime.utcnow()
        db.session.commit()

        return f(*args, **kwargs)
    return decorated_function

def serialize_step(step):
    serializable_step = {}
    for key, value in step.items():
        if 'messages' in value:
            serializable_messages = []
            for msg in value['messages']:
                if isinstance(msg, BaseMessage):
                    msg_dict = {"type": msg.type, "content": msg.content}
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        msg_dict['tool_calls'] = msg.tool_calls
                    if hasattr(msg, 'tool_call_id') and msg.tool_call_id:
                        msg_dict['tool_call_id'] = msg.tool_call_id
                    serializable_messages.append(msg_dict)
                else:
                    serializable_messages.append(msg)
            serializable_step[key] = {'messages': serializable_messages}
        else:
            serializable_step[key] = value
    return serializable_step

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    if check_ldap_credentials(username, password):
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username, email=f"{username}@ldap.local", is_admin=False)
            user.set_password(secrets.token_hex(16)) 
            db.session.add(user)
            db.session.commit()
        
        login_user(user)
        user.last_login = datetime.datetime.utcnow()
        db.session.commit()
        logger.info(f"User {username} logged in via LDAP")
        return jsonify({
            'message': 'Login successful (LDAP)',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_admin': user.is_admin
            }
        }), 200

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        login_user(user)
        user.last_login = datetime.datetime.utcnow()
        db.session.commit()
        logger.info(f"User {username} logged in")
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_admin': user.is_admin
            }
        }), 200

    logger.warning(f"Failed login attempt for user: {username}")
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/settings', methods=['GET'])
@login_required
def get_settings():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
        
    keys = ['LDAP_HOST', 'LDAP_DOMAIN', 'LDAP_BIND_USER', 'LDAP_BIND_PASSWORD', 'AAP_HOST', 'AAP_TOKEN', 'MAX_EXT_ITERATIONS']
    results = {}
    
    for key in keys:
        setting = SystemSetting.query.get(key)
        val = setting.value if setting else os.environ.get(key, '')
        
        if key == 'MAX_EXT_ITERATIONS' and not val:
            val = '3'
            
        is_secret = key in [' AAP_TOKEN', 'LDAP_BIND_PASSWORD'] 
        
        if is_secret and val:
            val = '********'
            
        results[key] = val
        
    results['OLLAMA_MODEL'] = os.environ.get('OLLAMA_MODEL', 'mistral') 
        
    return jsonify(results), 200

@app.route('/settings', methods=['POST'])
@login_required
def update_settings():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
        
    data = request.get_json()
    keys = ['LDAP_HOST', 'LDAP_DOMAIN', 'LDAP_BIND_USER', 'LDAP_BIND_PASSWORD', 'AAP_HOST', 'AAP_TOKEN', 'MAX_EXT_ITERATIONS']
    
    try:
        for key in keys:
            if key in data:
                val = str(data[key])
                if val == '********':
                    continue
                    
                setting = SystemSetting.query.get(key)
                if not setting:
                    setting = SystemSetting(key=key, is_secret=(key in [' AAP_TOKEN', 'LDAP_BIND_PASSWORD']))
                    db.session.add(setting)
                
                setting.value = val
        
        db.session.commit()
        logger.info(f"Settings updated by user {current_user.username}")
        return jsonify({'message': 'Settings updated successfully'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Settings update failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logout successful'}), 200

@app.route('/me', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'is_admin': current_user.is_admin
    }), 200

@app.route('/me/password', methods=['PUT'])
@login_required
def change_password():
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({'error': 'Current and new password required'}), 400

    if not current_user.check_password(current_password):
        return jsonify({'error': 'Invalid current password'}), 401

    current_user.set_password(new_password)
    db.session.commit()
    logger.info(f"Password changed for user {current_user.username}")

    return jsonify({'message': 'Password updated successfully'}), 200

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'error': 'Username, email, and password required'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    logger.info(f"New user registered: {username}")

    return jsonify({'message': 'User created successfully'}), 201

@app.route('/api-keys', methods=['GET'])
@login_required
def list_api_keys():
    keys = APIKey.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        'keys': [{
            'id': key.id,
            'name': key.name,
            'key': key.key[:8] + '...',
            'is_active': key.is_active,
            'created_at': key.created_at.isoformat(),
            'last_used': key.last_used.isoformat() if key.last_used else None
        } for key in keys]
    }), 200

@app.route('/api-keys', methods=['POST'])
@login_required
def create_api_key():
    data = request.get_json()
    name = data.get('name')

    if not name:
        return jsonify({'error': 'API key name required'}), 400

    key = APIKey(
        key=secrets.token_urlsafe(32),
        name=name,
        user_id=current_user.id
    )
    db.session.add(key)
    db.session.commit()
    logger.info(f"API Key created for user {current_user.username}: {name}")

    return jsonify({
        'message': 'API key created',
        'key': key.key,
        'name': key.name
    }), 201

@app.route('/api-keys/<int:key_id>', methods=['DELETE'])
@login_required
def delete_api_key(key_id):
    key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first()
    if not key:
        return jsonify({'error': 'API key not found'}), 404

    db.session.delete(key)
    db.session.commit()
    logger.info(f"API Key deleted for user {current_user.username}: {key.name}")

    return jsonify({'message': 'API key deleted'}), 200

@app.route('/sessions', methods=['GET'])
@login_required
def list_sessions():
    try:
        checkpointer = graph.checkpointer
        sessions = []
        rows = []

        if hasattr(checkpointer, 'conn'):
            if isinstance(checkpointer.conn, sqlite3.Connection):
                cursor = checkpointer.conn.cursor()
                cursor.execute("""
                    SELECT thread_id, MIN(checkpoint_id) as created_at
                    FROM checkpoints
                    GROUP BY thread_id
                    ORDER BY created_at DESC
                """)
                rows = cursor.fetchall()
            else:
                # Postgres
                pool = checkpointer.conn
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT thread_id, MIN(checkpoint_id) as created_at
                            FROM checkpoints
                            GROUP BY thread_id
                            ORDER BY created_at DESC
                        """)
                        rows = cur.fetchall()

        for row in rows:
            thread_id = row[0]
            created_at = row[1]
            thread_config = {"configurable": {"thread_id": thread_id}}
            state = graph.get_state(thread_config)

            messages = []
            if state.values and state.values.get("messages"):
                for i, msg in enumerate(state.values["messages"]):
                    if isinstance(msg, BaseMessage):
                        if msg.type != "system":
                            content = msg.content

                            if msg.type == "ai" and hasattr(msg, 'tool_calls') and msg.tool_calls:
                                # Skip replacing content for tool calls to rely on structured UI
                                pass
                            elif msg.type == "ai" and content:
                                import re
                                if isinstance(content, str) and ('[{"name":' in content or "[{'name':" in content):
                                     match = re.search(r'(\[\s*\{.*?\}\s*\])', content, re.DOTALL)
                                     if match:
                                         try:
                                             tool_data = json.loads(match.group(1).replace("'", '"'))
                                             if isinstance(tool_data, list) and len(tool_data) > 0:
                                                 # Legacy parsing fallback (optional, can be removed)
                                                 pass
                                         except:
                                             pass

                            messages.append({
                                "index": i,
                                "role": msg.type,
                                "content": content,
                                "tool_calls": getattr(msg, 'tool_calls', None),
                                "tool_call_id": getattr(msg, 'tool_call_id', None)
                            })

            sessions.append({
                "thread_id": thread_id,
                "message_count": len(messages),
                "messages": messages,
                "created_at": created_at
            })

        return jsonify({"sessions": sessions})
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/sessions', methods=['POST'])
@login_required
def create_session():
    try:
        import uuid
        # Generate a new thread_id
        # Use the existing format: session-TIMESTAMP-RANDOM to maintain compatibility
        timestamp = int(time.time() * 1000)
        random_part = str(uuid.uuid4())[:8]
        thread_id = f"session-{timestamp}-{random_part}"
        
        # Persist an initial empty state to ensure the session exists in the database
        # This allows other clients to discover it via GET /sessions
        thread_config = {"configurable": {"thread_id": thread_id}}
        initial_state = {"messages": []}
        
        # Use update_state to initialize the thread
        graph.update_state(thread_config, initial_state)
        
        logger.info(f"Created new session: {thread_id} for user {current_user.username}")
        
        return jsonify({
            "thread_id": thread_id,
            "created_at": timestamp,
            "message": "Session created successfully"
        }), 201
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/sessions/<thread_id>', methods=['DELETE'])
def delete_session(thread_id):
    try:
        checkpointer = graph.checkpointer
        if hasattr(checkpointer, 'conn'):
            if isinstance(checkpointer.conn, sqlite3.Connection):
                cursor = checkpointer.conn.cursor()
                cursor.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
                checkpointer.conn.commit()
            else:
                pool = checkpointer.conn
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
            logger.info(f"Deleted session {thread_id}")
            return jsonify({"status": "deleted", "thread_id": thread_id})
        return jsonify({"error": "Checkpointer not available"}), 500
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return jsonify({"error": str(e)}), 500

import queue

# Helper for Keep-Alive Streaming
def stream_with_keepalive(generator_func):
    """
    Wraps a generator to yield keep-alive comments if the generator blocks.
    This prevents Nginx/Browser timeouts during long-running tool executions.
    """
    q = queue.Queue()
    stop_event = threading.Event()

    def producer():
        try:
            for item in generator_func():
                q.put(item)
        except Exception as e:
            logger.error(f"Stream producer error: {e}")
            traceback.print_exc()
            # Push error as a data chunk so consumer sees it
            q.put(f"data: {json.dumps({'error': str(e)})}\n\n")
        finally:
            stop_event.set()

    t = threading.Thread(target=producer, daemon=True)
    t.start()

    while not stop_event.is_set() or not q.empty():
        try:
            # Wait for data with a short timeout
            item = q.get(timeout=10.0) # 10s timeout
            yield item
        except queue.Empty:
            # If no data for 10s, send keepalive
            yield ": keepalive\n\n"

@app.route('/chat')
@login_required
def chat():
    user_input = request.args.get('message', '').strip()
    thread_id = request.args.get('thread_id', 'default-web-thread')

    if not user_input:
        return Response("Empty message", status=400)

    thread_config = {"configurable": {"thread_id": thread_id}}
    current_state = graph.get_state(thread_config)
    is_new_conversation = not current_state.values.get("messages")

    messages_to_send = []
    if is_new_conversation:
        messages_to_send.append(SystemMessage(content=SYSTEM_PROMPT))
    messages_to_send.append(HumanMessage(content=user_input))

    def event_stream():
        try:
            for step in graph.stream({"messages": messages_to_send}, config=thread_config):
                yield f"data: {json.dumps(serialize_step(step))}\n\n"

            agent_state = graph.get_state(thread_config)
            if agent_state and agent_state.next:
                last_message = agent_state.values['messages'][-1]
                tool_call = last_message.tool_calls[0]
                review_payload = {
                    "type": "review",
                    "tool_call": {"name": tool_call['name'], "args": tool_call['args']}
                }
                yield f"data: {json.dumps(review_payload)}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Error in event_stream: {e}")
            traceback.print_exc()
            yield f"data: {json.dumps({'error': f'Agent processing failed: {str(e)}'})}\n\n"

    return Response(stream_with_keepalive(event_stream), mimetype='text/event-stream')

@app.route('/continue', methods=['POST'])
def continue_agent():
    data = request.json
    thread_id = data.get('thread_id')
    thread_config = {"configurable": {"thread_id": thread_id}}

    def event_stream():
        try:
            for step in graph.stream(None, config=thread_config):
                yield f"data: {json.dumps(serialize_step(step))}\n\n"
            
            # After the stream, check the final state
            final_state = graph.get_state(thread_config)
            
            # Check for subsequent Tool Call (Review Logic)
            if final_state and final_state.next:
                 # The agent stopped (likely for tool approval)
                 last_message = final_state.values['messages'][-1]
                 if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                     tool_call = last_message.tool_calls[0]
                     review_payload = {
                        "type": "review",
                        "tool_call": {"name": tool_call['name'], "args": tool_call['args']}
                     }
                     yield f"data: {json.dumps(review_payload)}\n\n"
            
            # Check for unstreamed final AI message (My previous fix)
            elif final_state and final_state.values and final_state.values.get("messages"):
                last_message = final_state.values["messages"][-1]
                if isinstance(last_message, BaseMessage) and last_message.type == "ai":
                    if not (hasattr(last_message, 'tool_calls') and last_message.tool_calls):
                         # Only yield if it wasn't already the last step in the stream
                         # (Actually, sending it again is harmless as frontend handles dupes, 
                         # but ensures reliability if stream didn't yield it broken out)
                        final_ai_step = {"agent": {"messages": [{"type": last_message.type, "content": last_message.content}]}}
                        yield f"data: {json.dumps(serialize_step(final_ai_step))}\n\n"
            
            yield f"data: {json.dumps({'status': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Error in continue stream: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_keepalive(event_stream), mimetype='text/event-stream')

import sys # Ensure sys is imported

def run_agent_background(thread_id, message):
    try:
        logger.info(f"Starting background execution for thread: {thread_id}")
        
        with app.app_context():
            max_iter_setting = get_system_setting('MAX_EXT_ITERATIONS', '3')
            try:
                recursion_limit = int(max_iter_setting)
            except ValueError:
                recursion_limit = 3
        
        ext_graph = setup_external_agent(recursion_limit=recursion_limit)
        if hasattr(ext_graph.checkpointer, 'setup'):
             ext_graph.checkpointer.setup()

        thread_config = {"configurable": {"thread_id": thread_id, "recursion_limit": recursion_limit + 5}} 
        
        current_state = ext_graph.get_state(thread_config)
        is_new_conversation = not current_state.values or not current_state.values.get("messages")
        
        messages_to_send = []
        if is_new_conversation:
            messages_to_send.append(SystemMessage(content=SYSTEM_PROMPT))
        messages_to_send.append(HumanMessage(content=message))
        
        timeout_seconds = 300
        start_time = time.time()
        
        logger.debug(f"Running external agent with limit {recursion_limit}")
        
        iteration_count = 0
        
        for step in ext_graph.stream({"messages": messages_to_send}, config=thread_config):
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                logger.warning(f"Timeout reached for {thread_id}")
                break
            
            iteration_count += 1
            logger.debug(f"Iteration {iteration_count} for {thread_id}")
            
            if iteration_count >= recursion_limit:
                 logger.warning(f"Max iterations ({recursion_limit}) reached for {thread_id}. Stopping.")
                 break
        
        logger.info(f"Background execution completed for {thread_id}")
        
    except Exception as e:
        logger.error(f"Background execution failed for {thread_id}: {str(e)}")
        traceback.print_exc()

@app.route('/external', methods=['POST'])
@require_api_key
def external_message():
    try:
        data = request.json
        reference_number = data.get('reference_number')
        message = data.get('message')
        
        if not reference_number:
            return jsonify({"error": "reference_number is required"}), 400

        if not message:
            return jsonify({"error": "message is required"}), 400

        thread_id = f"external-{reference_number}"
        
        thread = threading.Thread(target=run_agent_background, args=(thread_id, message))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "status": "accepted",
            "message": "Request processing started in background",
            "thread_id": thread_id,
            "reference_number": reference_number
        }), 202

    except Exception as e:
        logger.error(f"External request error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
@login_required
def status():
    gpu_active = os.environ.get('ENABLE_GPU', 'false').lower() == 'true'
    return jsonify({
        'status': 'online',
        'gpu_active': gpu_active, 
        'version': '1.0.0'
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

