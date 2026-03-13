# main_daemon.py
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)

# Import business logic modules
import module_sms
# import module_call
# import module_modem
# import module_system

# Configuration settings
TOKEN = ""
AUTHORIZED_CHAT_ID = 
LOCAL_HTTP_PORT = 5000

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# --- Security Layer (Authentication Firewall) ---
class AuthorizedUserFilter(filters.MessageFilter):
    """
    Custom filter to silently drop any message not originating from the authorized user.
    """
    def filter(self, message):
        return message.chat.id == AUTHORIZED_CHAT_ID

auth_filter = AuthorizedUserFilter()

# --- Internal HTTP API Server ---
async def handle_http_api(request: web.Request) -> web.Response:
    """
    Central dispatcher for incoming HTTP webhooks from Asterisk.
    Routes the payload to the appropriate module based on the URL path.
    """
    path = request.path
    bot = request.app['bot']

    try:
        data = await request.json()

        if path == '/api/sms':
            notification_text = module_sms.process_incoming_http_payload(data)
            await bot.send_message(chat_id=AUTHORIZED_CHAT_ID, text=notification_text)
            return web.Response(text="SMS notification dispatched", status=200)
            
        # Elif path == '/api/call': 
        #   notification_text = module_call.process_incoming_call(data)
        #   ...

        return web.Response(text="Unknown endpoint", status=404)

    except Exception as e:
        logger.error("HTTP dispatcher error: %s", str(e))
        return web.Response(text="Internal Server Error", status=500)

async def setup_http_server(app: Application) -> None:
    """Initializes the local aiohttp server."""
    server_app = web.Application()
    # Register API endpoints
    server_app.router.add_post('/api/sms', handle_http_api)
    # server_app.router.add_post('/api/call', handle_http_api)
    
    server_app['bot'] = app.bot
    runner = web.AppRunner(server_app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', LOCAL_HTTP_PORT)
    await site.start()
    app.bot_data['http_runner'] = runner
    logger.info("Local HTTP Server listening on port %s", LOCAL_HTTP_PORT)

async def teardown_http_server(app: Application) -> None:
    """Gracefully shuts down the HTTP server."""
    runner = app.bot_data.get('http_runner')
    if runner:
        await runner.cleanup()

# --- Global Error Handler ---
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches all unhandled exceptions and notifies the administrator."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_chat:
        error_msg = f"System Exception: {str(context.error)}"
        await context.bot.send_message(chat_id=AUTHORIZED_CHAT_ID, text=error_msg)

# --- Main Initialization ---
def main() -> None:
    """Main entry point for the EC20 Daemon."""
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(setup_http_server)
        .post_shutdown(teardown_http_server)
        .build()
    )

    # Register Error Handler
    application.add_error_handler(global_error_handler)

    # --- Command Routing ---
    # Note: auth_filter ensures these handlers are NEVER triggered by unauthorized users.
    
    # SMS Module
    application.add_handler(CommandHandler("sms", module_sms.command_send, filters=auth_filter))
    application.add_handler(MessageHandler(filters.TEXT & filters.REPLY & auth_filter, module_sms.command_reply))

    # Modem Module (Placeholders)
    # application.add_handler(CommandHandler("at", module_modem.command_at, filters=auth_filter))
    # application.add_handler(CommandHandler("status", module_modem.command_status, filters=auth_filter))

    logger.info("EC20-TeleBot Daemon successfully initialized and running.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()