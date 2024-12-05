import os
import requests
from flask import Flask, jsonify, request
from mangum import Mangum
from asgiref.wsgi import WsgiToAsgi
from discord_interactions import verify_key_decorator
from dotenv import load_dotenv

load_dotenv()

# Definir constantes ou funções para acessar as variáveis
TOKEN = os.getenv("TOKEN")
APPLICATION_ID = os.getenv("APPLICATION_ID")

# Configurações da API Ticto
DISCORD_PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY")
GUILD_ID = os.getenv("GUILD_ID")
NOBRES_ROLE_ID = os.getenv("NOBRES_ROLE_ID")
TICTO_CLIENT_ID = os.getenv("TICTO_CLIENT_ID")
TICTO_CLIENT_SECRET = os.getenv("TICTO_CLIENT_SECRET")
TICTO_OAUTH_URL = os.getenv("TICTO_OAUTH_URL")
TICTO_ORDERS_URL = os.getenv("TICTO_ORDERS_URL")
TICTO_PRODUCT_IDS = ["72862", "72860"]  # IDs dos produtos

# Caminho para o arquivo de e-mails utilizados
LOGS_DIR = os.path.join(os.path.dirname(__file__), 'logs')
USED_EMAILS_FILE = os.path.join(LOGS_DIR, 'used_emails')

# Garantir que o diretório de logs exista
os.makedirs(LOGS_DIR, exist_ok=True)

# Inicializar o Flask app
app = Flask(__name__)
asgi_app = WsgiToAsgi(app)
handler = Mangum(asgi_app)

def send_dm(user_id, message):
    """
    Envia uma mensagem direta para o usuário no Discord via API REST.
    """
    url = f"https://discord.com/api/v10/users/{user_id}/messages"
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "content": f"{message}"  # Mensagem a ser enviada
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        
        # Verifica o status da resposta
        if response.status_code == 200:
            print(f"Mensagem enviada para o user com sucesso!")
        else:
            print(f"Erro ao enviar mensagem para o user. Status: {response.status_code}")
            print(response.json())  # Log do erro para diagnóstico

    except requests.RequestException as e:
        print(f"Erro ao enviar DM para o user: {e}")

def get_ticto_access_token():
    """
    Obtém um token de acesso para a API da Ticto.
    """
    payload = {
        "grant_type": "client_credentials",
        "scope": "*",
        "client_id": TICTO_CLIENT_ID,
        "client_secret": TICTO_CLIENT_SECRET
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:
        response = requests.post(TICTO_OAUTH_URL, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()['access_token']
    except requests.RequestException as e:
        print(f"Erro ao obter token de acesso: {e}")
        return None

def fetch_ticto_orders(access_token):
    """
    Busca o histórico de pedidos dos produtos especificados.
    """
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {access_token}"
    }
    
    params = {
        "filter[products]": ",".join(TICTO_PRODUCT_IDS)
    }

    try:
        response = requests.get(TICTO_ORDERS_URL, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('data', [])
    except requests.RequestException as e:
        print(f"Erro ao buscar pedidos: {e}")
        return []

def extract_customer_emails(orders):
    """
    Extrai os emails dos clientes a partir dos pedidos.
    """
    return {order.get('customer', {}).get('email') for order in orders if order.get('customer', {}).get('email')}

def is_email_used(email):
    """
    Verifica se o e-mail já foi utilizado, lendo o arquivo 'used_emails'
    """
    if os.path.exists(USED_EMAILS_FILE):
        with open(USED_EMAILS_FILE, 'r') as file:
            used_emails = file.read().splitlines()
        return email in used_emails
    return False

def add_email_to_used_list(email):
    """
    Adiciona o e-mail à lista de e-mails usados no arquivo 'used_emails'
    """
    with open(USED_EMAILS_FILE, 'a') as file:
        file.write(email + "\n")

def add_role_to_user(user_id, role_id):
    """
    Adiciona um cargo a um usuário no Discord usando a API.
    """
    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}/roles/{role_id}"
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json"
    }
    
    response = requests.put(url, headers=headers)
    
    if response.status_code == 204:
        print(f"Cargo {role_id} adicionado ao usuário {user_id} com sucesso!")
    else:
        print(f"Erro ao adicionar cargo: {response.status_code} - {response.text}")

@app.route("/", methods=["POST"])
async def interactions():
    print(f"👉 Request: {request.json}")
    raw_request = request.json
    return interact(raw_request)

@verify_key_decorator(DISCORD_PUBLIC_KEY)
def interact(raw_request):
    if raw_request["type"] == 1:  # PING
        response_data = {"type": 1}  # PONG
    else:
        data = raw_request["data"]
        command_name = data["name"]

        if command_name == "verificar":
            # Tenta encontrar o email na requisição
            email = None
            for option in data["options"]:
                if option["name"] == "email_ou_id":
                    email = option["value"]

            if not email:
                # Retorna mensagem se o email não for fornecido
                message_content = "Não consegui encontrar o seu email ou ID."
                    
            else:
                # Obtém o token de acesso
                access_token = get_ticto_access_token()
                
                if not access_token:
                    message_content = "Erro ao obter token de autenticação."
                else:
                    # Busca pedidos
                    orders = fetch_ticto_orders(access_token)
                    
                    # Extrai emails dos clientes
                    customer_emails = extract_customer_emails(orders)
                    
                    # Verifica se o email existe na lista de clientes
                    if email not in customer_emails:
                        message_content = "Este e-mail não está associado a nenhum dos nossos produtos."
                    else:
                        # Verifica se o email já foi usado
                        if is_email_used(email):
                            message_content = "Este e-mail já foi utilizado para verificação e não pode ser mais usado."
                        else:
                            # Adiciona o email à lista de emails usados
                            add_email_to_used_list(email)
                            
                            # Adiciona cargo ao usuário
                            user_id = data["id"]
                            add_role_to_user(user_id, NOBRES_ROLE_ID)  # ID do cargo de "nobre"

                            # Manda uma mensagem na DM  do usuário falando da confirmação.
                            send_dm(user_id, "Olá, tudo bem? Você verificou o seu e-mail com sucesso! Seja muito bem vindo a Comunidade Nobredim!")
                            
                            message_content = f"E-mail confirmado com sucesso!"
        elif command_name == "echo":
            original_message = data["options"][0]["value"]
            message_content = f"Echoing: {original_message}"

        response_data = {
            "type": 4,
            "data": {"content": message_content},
        }

    return jsonify(response_data)

if __name__ == "__main__":
    app.run(debug=True)