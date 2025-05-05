import logging
import re
import os
import sys
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Configuração de logging seguro
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_logs.log'  # Salva logs em arquivo para auditoria
)
logger = logging.getLogger(__name__)

# Limites de segurança
MAX_MESSAGE_SIZE = 4096  # Limite máximo de tamanho de mensagem
MAX_GROUPS = 100  # Limite máximo de grupos
RATE_LIMIT = 20  # Limite de mensagens por minuto
MAX_COMMAND_LENGTH = 100  # Limite máximo de tamanho de comandos

# Contadores para limitação de taxa
rate_counters = {}

# Função para sanitizar entrada de texto
def sanitize_input(text):
    if not text:
        return ""
    # Remove caracteres potencialmente perigosos
    sanitized = re.sub(r'[;\\\/<>$&|]', '', text)
    # Limita o tamanho
    return sanitized[:MAX_MESSAGE_SIZE]

# Função para validar IDs
def validate_id(id_str):
    # Verifica se é um número inteiro válido
    try:
        id_val = int(id_str)
        # Verifica se está dentro de limites razoáveis
        if -1_000_000_000_000 <= id_val <= 1_000_000_000_000:
            return id_val
        return None
    except:
        return None

# Carrega configurações com validação
def carregar_config():
    try:
        # Define valores padrão seguros
        config = {
            "token": "",
            "grupo_origem_id": 0,
            "grupos_destino": [],
            "admins": [],
            "grupos_info": {}
        }
        
        # Tenta carregar do arquivo com tratamento de erros
        try:
            if os.path.exists('config.json'):
                with open('config.json', 'r') as file:
                    loaded_config = json.load(file)
                    
                    # Valida token
                    if isinstance(loaded_config.get("token", ""), str):
                        config["token"] = loaded_config.get("token", "")
                    
                    # Valida grupo de origem
                    origem_id = loaded_config.get("grupo_origem_id", 0)
                    validated_origem = validate_id(origem_id)
                    if validated_origem is not None:
                        config["grupo_origem_id"] = validated_origem
                    
                    # Valida grupos de destino
                    grupos = loaded_config.get("grupos_destino", [])
                    if isinstance(grupos, list) and len(grupos) <= MAX_GROUPS:
                        config["grupos_destino"] = [g for g in grupos if validate_id(g) is not None]
                    
                    # Valida admins
                    admins = loaded_config.get("admins", [])
                    if isinstance(admins, list):
                        config["admins"] = [a for a in admins if validate_id(a) is not None]
                    
                    # Valida grupos_info
                    grupos_info = loaded_config.get("grupos_info", {})
                    if isinstance(grupos_info, dict):
                        sanitized_info = {}
                        for k, v in grupos_info.items():
                            if validate_id(k.replace("-", "")) is not None and isinstance(v, str):
                                sanitized_info[k] = sanitize_input(v)[:50]  # Limita tamanho do nome
                        config["grupos_info"] = sanitized_info
        except json.JSONDecodeError:
            logger.error("Arquivo de configuração mal-formado. Usando configuração padrão.")
        except Exception as e:
            logger.error(f"Erro ao carregar configuração: {e}")
        
        return config
            
    except Exception as e:
        logger.error(f"Erro crítico ao carregar configuração: {e}")
        # Configuração mínima segura
        return {
            "token": os.environ.get("BOT_TOKEN", ""),
            "grupo_origem_id": 0,
            "grupos_destino": [],
            "admins": [],
            "grupos_info": {}
        }

# Função de limitação de taxa
async def rate_limit_check(update: Update) -> bool:
    user_id = update.effective_user.id
    current_time = int(time.time())
    
    # Inicializa ou atualiza contador
    if user_id not in rate_counters:
        rate_counters[user_id] = {"count": 1, "timestamp": current_time}
        return True
    
    # Reseta contador se já passou um minuto
    if current_time - rate_counters[user_id]["timestamp"] > 60:
        rate_counters[user_id] = {"count": 1, "timestamp": current_time}
        return True
    
    # Incrementa contador e verifica limite
    rate_counters[user_id]["count"] += 1
    if rate_counters[user_id]["count"] > RATE_LIMIT:
        logger.warning(f"Usuário {user_id} excedeu limite de taxa. Possível abuso.")
        await update.message.reply_text("Você enviou muitas solicitações. Por favor, aguarde um minuto.")
        return False
    
    return True

# Wrapper de segurança para processar mensagens
async def processar_mensagem_seguro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
        
        # Verifica tamanho da mensagem
        if update.message and update.message.text and len(update.message.text) > MAX_MESSAGE_SIZE:
            await update.message.reply_text(f"Mensagem muito grande. Limite: {MAX_MESSAGE_SIZE} caracteres.")
            return
            
        # Agora chama a função original com entrada validada
        await processar_mensagem(update, context)
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        await update.message.reply_text("Ocorreu um erro ao processar sua mensagem. Por favor, tente novamente.")

# Função principal de inicialização com verificações de segurança
def main_seguro() -> None:
    try:
        # Verifica ambiente
        if os.name == 'posix':  # Linux/Mac
            # Define limites de recursos
            import resource
            # Limita uso de memória (512MB)
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        
        # Inicializa bot com verificações de segurança
        main()
    except Exception as e:
        logger.critical(f"Erro crítico na inicialização: {e}")
        print(f"Erro crítico: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Adicione módulos necessários aqui
    import time
    
    # Inicia o bot com proteções de segurança
    main_seguro()