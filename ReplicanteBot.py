import logging
import re
import os
import sys
import json
import time
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

# Carrega configurações do arquivo ou variáveis de ambiente
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
                            if isinstance(k, str) and validate_id(k.replace("-", "")) is not None and isinstance(v, str):
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

# Salva configurações no arquivo
def salvar_config(config):
    try:
        # Sanitiza dados antes de salvar
        sanitized_config = {
            "token": config.get("token", ""),
            "grupo_origem_id": config.get("grupo_origem_id", 0),
            "grupos_destino": [g for g in config.get("grupos_destino", []) if validate_id(g) is not None],
            "admins": [a for a in config.get("admins", []) if validate_id(a) is not None],
            "grupos_info": {}
        }
        
        # Sanitiza informações de grupos
        for k, v in config.get("grupos_info", {}).items():
            if isinstance(k, str) and isinstance(v, str):
                sanitized_config["grupos_info"][k] = sanitize_input(v)[:50]
        
        with open('config.json', 'w') as file:
            json.dump(sanitized_config, file, indent=4)
            
    except Exception as e:
        logger.error(f"Erro ao salvar configuração: {e}")

# Carrega a configuração
CONFIG = carregar_config()
TOKEN = CONFIG.get("token", "")
GRUPO_ORIGEM_ID = CONFIG.get("grupo_origem_id", 0)
GRUPOS_DESTINO = CONFIG.get("grupos_destino", [])
ADMIN_IDS = CONFIG.get("admins", [])
GRUPOS_INFO = CONFIG.get("grupos_info", {})

# Dicionário para armazenar mensagens na memória
MENSAGENS_PARA_REPOSTAR = {}

# Função para verificar se o usuário é administrador
def is_admin(user_id):
    return user_id in ADMIN_IDS

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem quando o comando /start é emitido."""
    try:
        user = update.effective_user
        if user:
            await update.message.reply_text(f'Olá {user.first_name}! Estou pronto para repostar mensagens.')
        else:
            await update.message.reply_text('Olá! Estou pronto para repostar mensagens.')
    except Exception as e:
        logger.error(f"Erro no comando start: {e}")
        await update.message.reply_text('Ocorreu um erro ao iniciar o bot.')

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem de ajuda quando o comando /ajuda é emitido."""
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
            
        user_id = update.effective_user.id if update.effective_user else 0
        
        mensagem_basica = (
            'Este bot reposta mensagens do grupo principal para outros grupos.\n\n'
            'Quando você envia uma mensagem no grupo principal, o bot enviará uma mensagem privada para você '
            'com opções para escolher os grupos de destino.\n\n'
            'Comandos disponíveis:\n'
            '/start - Inicia o bot\n'
            '/ajuda - Mostra esta mensagem de ajuda\n'
        )
        
        # Adiciona comandos de administrador se o usuário for admin
        if is_admin(user_id):
            mensagem_admin = (
                '\nComandos de administrador:\n'
                '/grupos - Lista os grupos configurados\n'
                '/adicionargrupo <id> <nome> - Adiciona um grupo à lista de destinos\n'
                '/removergrupo <id> - Remove um grupo da lista de destinos\n'
                '/definirgrupoprincipal <id> - Define o grupo principal\n'
                '/adicionaradmin <id> - Adiciona um administrador\n'
                '/removeradmin <id> - Remove um administrador\n'
                '/status - Mostra estatísticas do bot\n'
            )
            mensagem_final = mensagem_basica + mensagem_admin
        else:
            mensagem_final = mensagem_basica
        
        await update.message.reply_text(mensagem_final)
    except Exception as e:
        logger.error(f"Erro no comando ajuda: {e}")
        await update.message.reply_text('Ocorreu um erro ao exibir a ajuda.')

async def listar_grupos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista os grupos configurados para repostagem."""
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
            
        user_id = update.effective_user.id if update.effective_user else 0
        
        if not is_admin(user_id):
            await update.message.reply_text('Você não tem permissão para usar este comando.')
            return
            
        mensagem = "📋 Grupos configurados para repostagem:\n\n"
        
        if not GRUPOS_DESTINO:
            mensagem += "Nenhum grupo de destino configurado.\n"
        else:
            for i, grupo_id in enumerate(GRUPOS_DESTINO, 1):
                nome_grupo = GRUPOS_INFO.get(str(grupo_id), f"Grupo {i}")
                mensagem += f"{i}. {nome_grupo} ({grupo_id})\n"
        
        mensagem += f"\n📢 Grupo de origem: {GRUPO_ORIGEM_ID if GRUPO_ORIGEM_ID != 0 else 'Não configurado'}"
        mensagem += f"\n\n👥 Administradores: {', '.join(map(str, ADMIN_IDS))}"
        
        await update.message.reply_text(mensagem)
    except Exception as e:
        logger.error(f"Erro ao listar grupos: {e}")
        await update.message.reply_text('Ocorreu um erro ao listar os grupos.')

async def adicionar_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adiciona um grupo à lista de destinos."""
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
            
        user_id = update.effective_user.id if update.effective_user else 0
        
        if not is_admin(user_id):
            await update.message.reply_text('Você não tem permissão para usar este comando.')
            return
        
        # Verifica se foi fornecido um ID de grupo e um nome
        if not context.args or len(context.args) < 2:
            await update.message.reply_text('Uso correto: /adicionargrupo <id_do_grupo> <nome_do_grupo>')
            return
        
        try:
            # Valida o ID
            grupo_id_str = context.args[0]
            grupo_id = validate_id(grupo_id_str)
            if grupo_id is None:
                await update.message.reply_text('ID de grupo inválido. Deve ser um número inteiro.')
                return
                
            # Sanitiza o nome
            nome_grupo = ' '.join(context.args[1:])
            nome_grupo = sanitize_input(nome_grupo)[:50]  # Limita a 50 caracteres
            
            # Verifica se o grupo já está na lista
            if grupo_id in GRUPOS_DESTINO:
                await update.message.reply_text(f'O grupo {nome_grupo} ({grupo_id}) já está na lista de destinos.')
                return
            
            # Adiciona o grupo
            GRUPOS_DESTINO.append(grupo_id)
            GRUPOS_INFO[str(grupo_id)] = nome_grupo
            
            CONFIG["grupos_destino"] = GRUPOS_DESTINO
            CONFIG["grupos_info"] = GRUPOS_INFO
            salvar_config(CONFIG)
            
            await update.message.reply_text(f'Grupo {nome_grupo} ({grupo_id}) adicionado com sucesso à lista de destinos.')
            logger.info(f"Grupo {grupo_id} adicionado por {user_id}")
        except ValueError:
            await update.message.reply_text('O ID do grupo deve ser um número inteiro.')
    except Exception as e:
        logger.error(f"Erro ao adicionar grupo: {e}")
        await update.message.reply_text('Ocorreu um erro ao adicionar o grupo.')

async def remover_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove um grupo da lista de destinos."""
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
            
        user_id = update.effective_user.id if update.effective_user else 0
        
        if not is_admin(user_id):
            await update.message.reply_text('Você não tem permissão para usar este comando.')
            return
        
        # Verifica se foi fornecido um ID de grupo
        if not context.args:
            await update.message.reply_text('Uso correto: /removergrupo <id_do_grupo>')
            return
        
        try:
            # Valida o ID
            grupo_id_str = context.args[0]
            grupo_id = validate_id(grupo_id_str)
            if grupo_id is None:
                await update.message.reply_text('ID de grupo inválido. Deve ser um número inteiro.')
                return
            
            # Verifica se o grupo está na lista
            if grupo_id not in GRUPOS_DESTINO:
                await update.message.reply_text(f'O grupo {grupo_id} não está na lista de destinos.')
                return
            
            # Remove o grupo
            GRUPOS_DESTINO.remove(grupo_id)
            if str(grupo_id) in GRUPOS_INFO:
                del GRUPOS_INFO[str(grupo_id)]
            
            CONFIG["grupos_destino"] = GRUPOS_DESTINO
            CONFIG["grupos_info"] = GRUPOS_INFO
            salvar_config(CONFIG)
            
            await update.message.reply_text(f'Grupo {grupo_id} removido com sucesso da lista de destinos.')
            logger.info(f"Grupo {grupo_id} removido por {user_id}")
        except ValueError:
            await update.message.reply_text('O ID do grupo deve ser um número inteiro.')
    except Exception as e:
        logger.error(f"Erro ao remover grupo: {e}")
        await update.message.reply_text('Ocorreu um erro ao remover o grupo.')

async def definir_grupo_principal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Define o grupo principal de onde as mensagens serão repostadas."""
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
            
        user_id = update.effective_user.id if update.effective_user else 0
        
        if not is_admin(user_id):
            await update.message.reply_text('Você não tem permissão para usar este comando.')
            return
        
        # Verifica se foi fornecido um ID de grupo
        if not context.args:
            await update.message.reply_text('Uso correto: /definirgrupoprincipal <id_do_grupo>')
            return
        
        try:
            # Valida o ID
            grupo_id_str = context.args[0]
            grupo_id = validate_id(grupo_id_str)
            if grupo_id is None:
                await update.message.reply_text('ID de grupo inválido. Deve ser um número inteiro.')
                return
            
            # Define o grupo principal
            global GRUPO_ORIGEM_ID
            GRUPO_ORIGEM_ID = grupo_id
            CONFIG["grupo_origem_id"] = GRUPO_ORIGEM_ID
            salvar_config(CONFIG)
            
            await update.message.reply_text(f'Grupo principal definido como {grupo_id}.')
            logger.info(f"Grupo principal definido como {grupo_id} por {user_id}")
        except ValueError:
            await update.message.reply_text('O ID do grupo deve ser um número inteiro.')
    except Exception as e:
        logger.error(f"Erro ao definir grupo principal: {e}")
        await update.message.reply_text('Ocorreu um erro ao definir o grupo principal.')

async def adicionar_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adiciona um usuário como administrador do bot."""
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
            
        user_id = update.effective_user.id if update.effective_user else 0
        
        if not is_admin(user_id):
            await update.message.reply_text('Você não tem permissão para usar este comando.')
            return
        
        # Verifica se foi fornecido um ID de usuário
        if not context.args:
            await update.message.reply_text('Uso correto: /adicionaradmin <id_do_usuário>')
            return
        
        try:
            # Valida o ID
            admin_id_str = context.args[0]
            admin_id = validate_id(admin_id_str)
            if admin_id is None:
                await update.message.reply_text('ID de usuário inválido. Deve ser um número inteiro.')
                return
            
            # Verifica se o usuário já é admin
            if admin_id in ADMIN_IDS:
                await update.message.reply_text(f'O usuário {admin_id} já é administrador.')
                return
            
            # Adiciona o admin
            ADMIN_IDS.append(admin_id)
            CONFIG["admins"] = ADMIN_IDS
            salvar_config(CONFIG)
            
            await update.message.reply_text(f'Usuário {admin_id} adicionado como administrador com sucesso.')
            logger.info(f"Administrador {admin_id} adicionado por {user_id}")
        except ValueError:
            await update.message.reply_text('O ID do usuário deve ser um número inteiro.')
    except Exception as e:
        logger.error(f"Erro ao adicionar admin: {e}")
        await update.message.reply_text('Ocorreu um erro ao adicionar o administrador.')

async def remover_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove um usuário da lista de administradores do bot."""
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
            
        user_id = update.effective_user.id if update.effective_user else 0
        
        if not is_admin(user_id):
            await update.message.reply_text('Você não tem permissão para usar este comando.')
            return
        
        # Verifica se foi fornecido um ID de usuário
        if not context.args:
            await update.message.reply_text('Uso correto: /removeradmin <id_do_usuário>')
            return
        
        try:
            # Valida o ID
            admin_id_str = context.args[0]
            admin_id = validate_id(admin_id_str)
            if admin_id is None:
                await update.message.reply_text('ID de usuário inválido. Deve ser um número inteiro.')
                return
            
            # Verifica se o usuário é admin
            if admin_id not in ADMIN_IDS:
                await update.message.reply_text(f'O usuário {admin_id} não é administrador.')
                return
            
            # Impede remover o último admin
            if len(ADMIN_IDS) <= 1:
                await update.message.reply_text('Não é possível remover o último administrador.')
                return
            
            # Remove o admin
            ADMIN_IDS.remove(admin_id)
            CONFIG["admins"] = ADMIN_IDS
            salvar_config(CONFIG)
            
            await update.message.reply_text(f'Usuário {admin_id} removido da lista de administradores.')
            logger.info(f"Administrador {admin_id} removido por {user_id}")
        except ValueError:
            await update.message.reply_text('O ID do usuário deve ser um número inteiro.')
    except Exception as e:
        logger.error(f"Erro ao remover admin: {e}")
        await update.message.reply_text('Ocorreu um erro ao remover o administrador.')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra estatísticas do bot."""
    try:
        # Verifica limitação de taxa
        if not await rate_limit_check(update):
            return
            
        user_id = update.effective_user.id if update.effective_user else 0
        
        if not is_admin(user_id):
            await update.message.reply_text('Você não tem permissão para usar este comando.')
            return
        
        estatisticas = (
            "📊 Status do Bot\n\n"
            f"🔄 Total de grupos de destino: {len(GRUPOS_DESTINO)}\n"
            f"👥 Total de administradores: {len(ADMIN_IDS)}\n"
            f"📢 Grupo de origem configurado: {'Sim' if GRUPO_ORIGEM_ID != 0 else 'Não'}\n"
            f"📝 Mensagens em fila para repostagem: {len(MENSAGENS_PARA_REPOSTAR)}\n"
            "⚙️ Bot em execução"
        )
        
        await update.message.reply_text(estatisticas)
    except Exception as e:
        logger.error(f"Erro ao mostrar status: {e}")
        await update.message.reply_text('Ocorreu um erro ao mostrar o status do bot.')

async def processar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens recebidas no grupo de origem."""
    try:
        # Verifica se a mensagem veio do grupo de origem
        if update.effective_chat and update.effective_chat.id == GRUPO_ORIGEM_ID:
            # Verifica limitação de taxa
            if not await rate_limit_check(update):
                return
                
            if not GRUPOS_DESTINO:
                # Se não houver grupos de destino configurados
                await update.message.reply_text("Não há grupos de destino configurados para repostagem.")
                return
            
            user = update.effective_user
            if not user:
                logger.warning("Mensagem recebida sem usuário identificável")
                return
            
            # Armazena a mensagem para repostagem posterior
            mensagem_info = {
                "message_id": update.message.message_id,
                "grupos_selecionados": [],
                "from_user_id": user.id,
                "from_user_name": user.first_name
            }
            
            # Envia uma mensagem privada para o usuário com as opções de repostagem
            try:
                # Cria botões para seleção de grupos
                keyboard = []
                for grupo_id in GRUPOS_DESTINO:
                    nome_grupo = GRUPOS_INFO.get(str(grupo_id), f"Grupo {grupo_id}")
                    keyboard.append([InlineKeyboardButton(nome_grupo, callback_data=f"select_{grupo_id}")])
                
                # Adiciona botões para selecionar todos ou enviar
                keyboard.append([
                    InlineKeyboardButton("✅ Selecionar Todos", callback_data="select_all"),
                    InlineKeyboardButton("❌ Limpar", callback_data="clear_all")
                ])
                keyboard.append([InlineKeyboardButton("📨 Enviar", callback_data="send")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Envia mensagem privada com os botões de seleção
                mensagem_privada = await context.bot.send_message(
                    chat_id=user.id,
                    text=f"Selecione os grupos para onde deseja repostar sua mensagem recente do grupo {GRUPO_ORIGEM_ID}:",
                    reply_markup=reply_markup
                )
                
                # Armazena a mensagem no dicionário
                MENSAGENS_PARA_REPOSTAR[mensagem_privada.message_id] = mensagem_info
                
                # Confirma no grupo que enviou mensagem privada
                await update.message.reply_text(
                    f"Enviei uma mensagem privada para você, @{user.username or user.first_name}, "
                    f"para selecionar os grupos de destino. Por favor, verifique suas mensagens diretas com o bot.",
                    disable_notification=True
                )
                
            except Exception as e:
                # Se não conseguir enviar mensagem privada
                logger.error(f"Erro ao enviar mensagem privada para {user.id}: {e}")
                await update.message.reply_text(
                    f"Não foi possível enviar uma mensagem privada. Por favor, inicie uma conversa privada com o bot primeiro: "
                    f"https://t.me/{context.bot.username}"
                )
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        if update.message:
            await update.message.reply_text("Ocorreu um erro ao processar sua mensagem.")

async def processar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa os callbacks dos botões inline."""
    try:
        query = update.callback_query
        if not query:
            return
            
        await query.answer()
        
        data = query.data
        message_id = query.message.message_id
        user_id = query.from_user.id if query.from_user else 0
        
        if message_id not in MENSAGENS_PARA_REPOSTAR:
            await query.message.edit_text("Esta mensagem expirou ou não está mais disponível.")
            return
        
        mensagem_info = MENSAGENS_PARA_REPOSTAR[message_id]
        
        # Verifica se quem clicou é o dono da mensagem original
        if user_id != mensagem_info["from_user_id"]:
            await query.message.reply_text("Você não pode interagir com os controles de repostagem de outra pessoa.")
            return
        
        grupos_selecionados = mensagem_info["grupos_selecionados"]
        
        if data.startswith("select_"):
            # Seleciona ou deseleciona um grupo ou todos os grupos
            if data == "select_all":
                # Seleciona todos os grupos
                mensagem_info["grupos_selecionados"] = GRUPOS_DESTINO.copy()
            else:
                # Seleciona ou deseleciona um grupo específico
                try:
                    grupo_id_str = data.split("_")[1]
                    grupo_id = validate_id(grupo_id_str)
                    if grupo_id is None:
                        logger.warning(f"ID de grupo inválido recebido: {grupo_id_str}")
                        return
                        
                    if grupo_id in grupos_selecionados:
                        grupos_selecionados.remove(grupo_id)
                    else:
                        grupos_selecionados.append(grupo_id)
                except (IndexError, ValueError) as e:
                    logger.error(f"Erro ao processar seleção de grupo: {e}")
                    return
        
        elif data == "clear_all":
            # Limpa todas as seleções
            mensagem_info["grupos_selecionados"] = []
        
        elif data == "send":
            # Envia a mensagem para os grupos selecionados
            if not grupos_selecionados:
                await query.message.edit_text("Nenhum grupo selecionado. Selecione pelo menos um grupo para repostar.")
                return
            
            # Reposta a mensagem para os grupos selecionados
            original_message_id = mensagem_info["message_id"]
            sucessos = 0
            falhas = 0
            detalhes_falhas = []
            
            for grupo_id in grupos_selecionados:
                try:
                    await context.bot.copy_message(
                        chat_id=grupo_id,
                        from_chat_id=GRUPO_ORIGEM_ID,
                        message_id=original_message_id
                    )
                    sucessos += 1
                    logger.info(f"Mensagem {original_message_id} repostada para o grupo {grupo_id}")
                except Exception as e:
                    falhas += 1
                    nome_grupo = GRUPOS_INFO.get(str(grupo_id), f"Grupo {grupo_id}")
                    erro_msg = f"Grupo {nome_grupo} ({grupo_id}): {str(e)}"
                    detalhes_falhas.append(erro_msg)
                    logger.error(f"Erro ao repostar para o grupo {grupo_id}: {e}")
            
          # Atualiza a mensagem com o resultado
            mensagem_resultado = f"✅ Mensagem repostada com sucesso para {sucessos} grupos.\n"
            if falhas > 0:
                mensagem_resultado += f"❌ Falhas ao repostar para {falhas} grupos.\n\n"
                mensagem_resultado += "Detalhes dos erros:\n"
                for erro in detalhes_falhas:
                    mensagem_resultado += f"- {erro}\n"
            
            await query.message.edit_text(mensagem_resultado)
            
            # Remove a mensagem do dicionário
            del MENSAGENS_PARA_REPOSTAR[message_id]
            return
        
        # Atualiza os botões com base nas seleções
        keyboard = []
        for grupo_id in GRUPOS_DESTINO:
            nome_grupo = GRUPOS_INFO.get(str(grupo_id), f"Grupo {grupo_id}")
            texto = f"✅ {nome_grupo}" if grupo_id in grupos_selecionados else nome_grupo
            keyboard.append([InlineKeyboardButton(texto, callback_data=f"select_{grupo_id}")])
        
        keyboard.append([
            InlineKeyboardButton("✅ Selecionar Todos", callback_data="select_all"),
            InlineKeyboardButton("❌ Limpar", callback_data="clear_all")
        ])
        keyboard.append([InlineKeyboardButton("📨 Enviar", callback_data="send")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Atualiza a mensagem com os novos botões
        await query.message.edit_reply_markup(reply_markup)
    except Exception as e:
        logger.error(f"Erro ao processar callback: {e}")
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text("Ocorreu um erro ao processar sua seleção.")

def main() -> None:
    """Inicia o bot."""
    try:
        # Verifica se o token foi configurado
        if not TOKEN:
            logger.error("Token não configurado. Configure o token no arquivo config.json ou na variável de ambiente BOT_TOKEN.")
            return
        
        # Cria o aplicativo
        application = Application.builder().token(TOKEN).build()

        # Registra os handlers de comandos
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("ajuda", ajuda))
        application.add_handler(CommandHandler("grupos", listar_grupos))
        application.add_handler(CommandHandler("adicionargrupo", adicionar_grupo))
        application.add_handler(CommandHandler("removergrupo", remover_grupo))
        application.add_handler(CommandHandler("definirgrupoprincipal", definir_grupo_principal))
        application.add_handler(CommandHandler("adicionaradmin", adicionar_admin))
        application.add_handler(CommandHandler("removeradmin", remover_admin))
        application.add_handler(CommandHandler("status", status))
        
        # Handler para processar mensagens
        application.add_handler(MessageHandler(
            filters.Chat(chat_id=GRUPO_ORIGEM_ID) & ~filters.COMMAND, 
            processar_mensagem
        ))
        
        # Handler para processar callbacks de botões
        application.add_handler(CallbackQueryHandler(processar_callback))

        # Inicia o bot
        logger.info("Bot iniciado")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"Erro crítico na inicialização do bot: {e}")
        print(f"Erro crítico: {e}")

def main_seguro() -> None:
    """Inicia o bot com verificações de segurança."""
    try:
        # Verifica ambiente
        if os.name == 'posix':  # Linux/Mac
            try:
                # Limita uso de recursos
                import resource
                # Limita uso de memória (512MB)
                resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            except Exception as e:
                logger.warning(f"Não foi possível configurar limites de recursos: {e}")
        
        # Inicializa bot com verificações de segurança
        main()
    except Exception as e:
        logger.critical(f"Erro crítico na inicialização: {e}")
        print(f"Erro crítico: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Inicia o bot com proteções de segurança
    main_seguro()