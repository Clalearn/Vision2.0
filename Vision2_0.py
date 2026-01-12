from flask import Flask, request, Response, jsonify
import os
import boto3
from botocore.exceptions import ClientError

# === CONFIGURAZIONE CLIENT AI ===
# Le credenziali (Access Key/Secret Key) vengono lette automaticamente dalle 
# variabili d'ambiente del server o dalla configurazione locale.
try:
    ai_client = boto3.client(
        service_name="bedrock-runtime", 
        region_name="us-west-2" 
    )
except Exception as e:
    print(f"Errore inizializzazione Client AI: {e}")

# ID Tecnico del modello (Questo serve al server, ma è invisibile all'utente)
INTERNAL_MODEL_ID = "meta.llama3-1-405b-instruct-v1:0"

# === INIZIALIZZA CRONOLOGIA ===
cronologia_chat_sessions = {}

# === CONFIGURAZIONE PERSONA ===
SYSTEM_PROMPT_TEXT = (
    "Sei un assistente AI utile e cordiale specializzato nell'istruzione. "
    "Rispondi sempre e solo in italiano. "
    "Alle domande su chi sei rispondi sempre: Sono Vision, un'AI creata da Cla!. "
    "Alle domande relative su chi ti ha creato rispondi sempre: Sono stato creato dal team di Cla!"
)

# === LIMITE MEMORIA (Messaggi recenti mantenuti) ===
MAX_HISTORY_MESSAGES = 10 

app = Flask(__name__)

# Funzione helper per gestire la cronologia
def get_ai_messages(session_id):
    if session_id not in cronologia_chat_sessions:
        cronologia_chat_sessions[session_id] = []
    
    full_history = cronologia_chat_sessions[session_id]
    return full_history[-MAX_HISTORY_MESSAGES:]

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cla! Chatbot</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
            .chat-container { background-color: #fff; border-radius: 12px; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1); overflow: hidden; width: 85%; max-width: 600px; display: flex; flex-direction: column; height: 80vh; }
            .chat-header { padding: 20px; text-align: center; border-bottom: 1px solid #eee; background: linear-gradient(135deg, #00838f, #00acc1); color: white; font-weight: bold; font-size: 1.2em; letter-spacing: 1px; }
            .chat-log { padding: 20px; flex-grow: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
            .message { padding: 10px 15px; border-radius: 18px; max-width: 80%; word-wrap: break-word; line-height: 1.5; font-size: 0.95em; }
            .user-message { background-color: #e0f7fa; align-self: flex-end; color: #006064; border-bottom-right-radius: 2px; }
            .bot-message { background-color: #f1f3f4; color: #333; align-self: flex-start; border-bottom-left-radius: 2px; }
            .input-area { padding: 15px; display: flex; border-top: 1px solid #eee; background-color: #fafafa; }
            #user-input { flex-grow: 1; padding: 12px; border: 1px solid #ddd; border-radius: 25px; margin-right: 10px; outline: none; transition: border 0.3s; }
            #user-input:focus { border-color: #00838f; }
            button { background-color: #00838f; color: white; border: none; padding: 10px 20px; border-radius: 25px; cursor: pointer; font-weight: bold; transition: background 0.3s; }
            button:hover { background-color: #006064; }
            
            /* Animazione puntini di attesa */
            .typing-indicator::after { content: '...'; animation: dots 1.5s steps(5, end) infinite; }
            @keyframes dots { 0%, 20% { content: ''; } 40% { content: '.'; } 60% { content: '..'; } 80%, 100% { content: '...'; } }
        </style>
    </head>
    <body>
        <div class="chat-container">
            <div class="chat-header">Cla! Assistente Virtuale</div>
            <div class="chat-log" id="chat-log">
                <div class="message bot-message">Ciao! Sono Vision. Come posso esserti utile oggi?</div>
            </div>
            <div class="input-area">
                <input type="text" id="user-input" placeholder="Scrivi un messaggio..." autofocus>
                <button type="button" onclick="sendMessage()">Invia</button>
            </div>
        </div>
        <script>
            function sendMessage() {
                const userInput = document.getElementById('user-input').value.trim();
                if (!userInput) return;
                
                const chatLog = document.getElementById('chat-log');
                chatLog.innerHTML += `<div class="message user-message">${userInput}</div>`;
                document.getElementById('user-input').value = '';
                chatLog.scrollTop = chatLog.scrollHeight;
                
                const botMessage = document.createElement('div');
                botMessage.className = 'message bot-message';
                botMessage.innerHTML = "<span class='typing-indicator'>Elaborazione</span>";
                chatLog.appendChild(botMessage);
                
                // Generiamo un ID sessione casuale per il browser
                const sessionId = 'web-' + new Date().getDate() + '-' + Math.random().toString(36).substr(2, 9);

                const eventSource = new EventSource(`/get_response?message=${encodeURIComponent(userInput)}&session_id=${encodeURIComponent(sessionId)}`);
                
                let isFirstChunk = true;

                eventSource.onmessage = function(event) {
                    if (event.data === "[END]") {
                        eventSource.close();
                        return;
                    }
                    if (isFirstChunk) {
                        botMessage.innerHTML = ""; // Rimuove "Elaborazione..."
                        isFirstChunk = false;
                    }
                    botMessage.textContent += event.data;
                    chatLog.scrollTop = chatLog.scrollHeight;
                };
                
                eventSource.onerror = function() {
                    if (isFirstChunk) botMessage.textContent = "Errore di connessione.";
                    eventSource.close();
                }
            }
            document.getElementById('user-input').addEventListener('keypress', function (e) {
                if (e.key === 'Enter') sendMessage();
            });
        </script>
    </body>
    </html>
    """

@app.route('/get_response')
def get_response():
    user_input = request.args.get("message", "").strip()
    session_id = request.args.get("session_id", "default")
    
    if session_id not in cronologia_chat_sessions:
        cronologia_chat_sessions[session_id] = []
    
    cronologia_chat_sessions[session_id].append({"role": "user", "content": [{"text": user_input}]})
    
    messages_to_send = get_ai_messages(session_id)
    
    def generate():
        full_response_text = ""
        try:
            # Chiamata al servizio Cloud AI
            response = ai_client.converse_stream(
                modelId=INTERNAL_MODEL_ID,
                messages=messages_to_send,
                system=[{"text": SYSTEM_PROMPT_TEXT}],
                inferenceConfig={"maxTokens": 1024, "temperature": 0.7, "topP": 0.9}
            )
            
            stream = response.get('stream')
            if stream:
                for event in stream:
                    if 'contentBlockDelta' in event:
                        text_chunk = event['contentBlockDelta']['delta']['text']
                        full_response_text += text_chunk
                        safe_chunk = text_chunk.replace("\n", " ") 
                        yield f"data: {safe_chunk}\n\n"
            
            cronologia_chat_sessions[session_id].append({
                "role": "assistant", 
                "content": [{"text": full_response_text}]
            })
            yield "data: [END]\n\n"
            
        except Exception as e:
            # Log interno dell'errore (non mostrato nel dettaglio all'utente per sicurezza)
            print(f"Errore generazione: {e}")
            yield f"data: [Si è verificato un errore tecnico.]\n\n"
            yield "data: [END]\n\n"

    return Response(generate(), mimetype="text/event-stream")

@app.route('/chat', methods=['POST'])
def chat():
    # API Backend Standard (JSON)
    auth_token = request.headers.get('Authorization')
    if auth_token != f"Bearer {os.getenv('AUTH_TOKEN', 'your-secret-token')}":
        return jsonify({'error': 'Non autorizzato'}), 401

    data = request.json
    user_input = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')

    if not user_input:
        return jsonify({'error': 'Messaggio vuoto'}), 400

    if session_id not in cronologia_chat_sessions:
        cronologia_chat_sessions[session_id] = []

    cronologia_chat_sessions[session_id].append({"role": "user", "content": [{"text": user_input}]})
    messages_to_send = get_ai_messages(session_id)

    try:
        response = ai_client.converse(
            modelId=INTERNAL_MODEL_ID,
            messages=messages_to_send,
            system=[{"text": SYSTEM_PROMPT_TEXT}],
            inferenceConfig={"maxTokens": 1024, "temperature": 0.7, "topP": 0.9}
        )

        bot_response = response['output']['message']['content'][0]['text']
        
        cronologia_chat_sessions[session_id].append({
            "role": "assistant", 
            "content": [{"text": bot_response}]
        })

        return jsonify({'response': bot_response})

    except Exception as e:
        print(f"Errore API: {e}")
        return jsonify({'error': 'Errore interno del server'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)