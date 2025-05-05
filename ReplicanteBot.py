import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import json
import os

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Carrega configurações do arquivo ou variáveis de ambiente
def carregar_config():
    # Tenta carregar do arquivo primeiro
    try:
        with open('config.json', 'r') as file:
            config = json.load(file)
            return config
    except FileNotFoundError:
        # Se o arquivo não existir, tenta carregar das variáveis de ambiente
        return {
            "token": os.environ.get("BOT_TOKEN"),
            "grupo_origem_id": int(os.environ.get("GRUPO_ORIGEM_ID", 0)),
            "grupos_destino": [int(id) for id in os.environ.get("GRUPOS_DESTINO", "").split(",") if id],
            "admins": [int(id) for id in os.environ.get("ADMIN_IDS", "").split(",") if id]
        }

# Salva configurações no arquivo
def salvar_config(config):
    with open('config.json', 'w') as file:
        json.dump(config, file, indent=4)

# Carrega a configuração
CONFIG = carregar_config()
TOKEN = CONFIG.get("token", "")
GRUPO_ORIGEM_ID = CONFIG.get("grupo_origem_id", 0)
GRUPOS_DESTINO = CONFIG.get("grupos_destino", [])
ADMIN_IDS = CONFIG.get("admins", [])

# Função para verificar se o usuário é administrador
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem quando o comando /start é emitido."""
    user = update.effective_user
    await update.message.reply_text(f'Olá {user.first_name}! Estou pronto para repostar mensagens.')

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem de ajuda quando o comando /ajuda é emitido."""
    user_id = update.effective_user.id
    
    mensagem_basica = (
        'Este bot reposta mensagens do grupo principal para outros grupos.\n\n'
        'Comandos disponíveis:\n'
        '/start - Inicia o bot\n'
        '/ajuda - Mostra esta mensagem de ajuda\n'
    )
    
    # Adiciona comandos de administrador se o usuário for admin
    if is_admin(user_id):
        mensagem_admin = (
            '\nComandos de administrador:\n'
            '/grupos - Lista os grupos configurados\n'
            '/adicionargrupo <id> - Adiciona um grupo à lista de destinos\n'
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

async def listar_grupos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista os grupos configurados para repostagem."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('Você não tem permissão para usar este comando.')
        return
        
    mensagem = "📋 Grupos configurados para repostagem:\n\n"
    
    if not GRUPOS_DESTINO:
        mensagem += "Nenhum grupo de destino configurado.\n"
    else:
        for i, grupo_id in enumerate(GRUPOS_DESTINO, 1):
            mensagem += f"{i}. {grupo_id}\n"
    
    mensagem += f"\n📢 Grupo de origem: {GRUPO_ORIGEM_ID if GRUPO_ORIGEM_ID != 0 else 'Não configurado'}"
    mensagem += f"\n\n👥 Administradores: {', '.join(map(str, ADMIN_IDS))}"
    
    await update.message.reply_text(mensagem)

async def adicionar_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adiciona um grupo à lista de destinos."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('Você não tem permissão para usar este comando.')
        return
    
    # Verifica se foi fornecido um ID de grupo
    if not context.args:
        await update.message.reply_text('Uso correto: /adicionargrupo <id_do_grupo>')
        return
    
    try:
        grupo_id = int(context.args[0])
        
        # Verifica se o grupo já está na lista
        if grupo_id in GRUPOS_DESTINO:
            await update.message.reply_text(f'O grupo {grupo_id} já está na lista de destinos.')
            return
        
        # Adiciona o grupo
        GRUPOS_DESTINO.append(grupo_id)
        CONFIG["grupos_destino"] = GRUPOS_DESTINO
        salvar_config(CONFIG)
        
        await update.message.reply_text(f'Grupo {grupo_id} adicionado com sucesso à lista de destinos.')
    except ValueError:
        await update.message.reply_text('O ID do grupo deve ser um número inteiro.')

async def remover_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove um grupo da lista de destinos."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('Você não tem permissão para usar este comando.')
        return
    
    # Verifica se foi fornecido um ID de grupo
    if not context.args:
        await update.message.reply_text('Uso correto: /removergrupo <id_do_grupo>')
        return
    
    try:
        grupo_id = int(context.args[0])
        
        # Verifica se o grupo está na lista
        if grupo_id not in GRUPOS_DESTINO:
            await update.message.reply_text(f'O grupo {grupo_id} não está na lista de destinos.')
            return
        
        # Remove o grupo
        GRUPOS_DESTINO.remove(grupo_id)
        CONFIG["grupos_destino"] = GRUPOS_DESTINO
        salvar_config(CONFIG)
        
        await update.message.reply_text(f'Grupo {grupo_id} removido com sucesso da lista de destinos.')
    except ValueError:
        await update.message.reply_text('O ID do grupo deve ser um número inteiro.')

async def definir_grupo_principal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Define o grupo principal de onde as mensagens serão repostadas."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('Você não tem permissão para usar este comando.')
        return
    
    # Verifica se foi fornecido um ID de grupo
    if not context.args:
        await update.message.reply_text('Uso correto: /definirgrupoprincipal <id_do_grupo>')
        return
    
    try:
        grupo_id = int(context.args[0])
        
        # Define o grupo principal
        global GRUPO_ORIGEM_ID
        GRUPO_ORIGEM_ID = grupo_id
        CONFIG["grupo_origem_id"] = GRUPO_ORIGEM_ID
        salvar_config(CONFIG)
        
        await update.message.reply_text(f'Grupo principal definido como {grupo_id}.')
    except ValueError:
        await update.message.reply_text('O ID do grupo deve ser um número inteiro.')

async def adicionar_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adiciona um usuário como administrador do bot."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('Você não tem permissão para usar este comando.')
        return
    
    # Verifica se foi fornecido um ID de usuário
    if not context.args:
        await update.message.reply_text('Uso correto: /adicionaradmin <id_do_usuário>')
        return
    
    try:
        admin_id = int(context.args[0])
        
        # Verifica se o usuário já é admin
        if admin_id in ADMIN_IDS:
            await update.message.reply_text(f'O usuário {admin_id} já é administrador.')
            return
        
        # Adiciona o admin
        ADMIN_IDS.append(admin_id)
        CONFIG["admins"] = ADMIN_IDS
        salvar_config(CONFIG)
        
        await update.message.reply_text(f'Usuário {admin_id} adicionado como administrador com sucesso.')
    except ValueError:
        await update.message.reply_text('O ID do usuário deve ser um número inteiro.')

async def remover_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove um usuário da lista de administradores do bot."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('Você não tem permissão para usar este comando.')
        return
    
    # Verifica se foi fornecido um ID de usuário
    if not context.args:
        await update.message.reply_text('Uso correto: /removeradmin <id_do_usuário>')
        return
    
    try:
        admin_id = int(context.args[0])
        
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
    except ValueError:
        await update.message.reply_text('O ID do usuário deve ser um número inteiro.')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra estatísticas do bot."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('Você não tem permissão para usar este comando.')
        return
    
    # Aqui você pode incluir estatísticas como:
    # - Número de mensagens repostadas
    # - Tempo online
    # - Uso de recursos, etc.
    
    estatisticas = (
        "📊 Status do Bot\n\n"
        f"🔄 Total de grupos de destino: {len(GRUPOS_DESTINO)}\n"
        f"👥 Total de administradores: {len(ADMIN_IDS)}\n"
        f"📢 Grupo de origem configurado: {'Sim' if GRUPO_ORIGEM_ID != 0 else 'Não'}\n"
        "⚙️ Bot em execução"
    )
    
    await update.message.reply_text(estatisticas)

async def repostar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reposta a mensagem para todos os grupos de destino."""
    # Verifica se a mensagem veio do grupo de origem
    if update.effective_chat.id == GRUPO_ORIGEM_ID:
        # Para cada grupo de destino, reposta a mensagem
        for grupo_id in GRUPOS_DESTINO:
            try:
                # Reposta exatamente a mesma mensagem
                await context.bot.copy_message(
                    chat_id=grupo_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                logger.info(f"Mensagem repostada para o grupo {grupo_id}")
            except Exception as e:
                logger.error(f"Erro ao repostar para o grupo {grupo_id}: {e}")
                # Notifica admins sobre o erro
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"⚠️ Erro ao repostar para o grupo {grupo_id}: {e}"
                        )
                    except:
                        pass

def main() -> None:
    """Inicia o bot."""
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
    
    # Handler para repostar mensagens
    application.add_handler(MessageHandler(
        filters.Chat(chat_id=GRUPO_ORIGEM_ID) & ~filters.COMMAND, 
        repostar_mensagem
    ))

    # Inicia o bot
    logger.info("Bot iniciado")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()