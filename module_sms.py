# module_sms.py
import subprocess
import re
import logging
import base64
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# --- Data Processing Functions ---

def sanitize_and_escape_text(text: str) -> str:
    """
    Sanitizes input by removing non-BMP characters (e.g., emojis) to prevent UCS-2 encoding 
    crashes in the modem, and escapes characters for safe Asterisk CLI execution.
    Preserves actual newlines.
    """

    text = re.sub(r'[^\u0000-\uFFFF]', '', text)
    
    text = text.replace('\\', '\\\\')
    text = text.replace('"', '\\"')
    
    text = text.replace('\r\n', '\n')
    text = text.replace('\r', '\n')
    
    return text.strip()

def decode_base64_sms(b64_string: str) -> str:
    """Safely decodes Base64 encoded SMS content."""
    try:
        b64_string = b64_string.strip()
        padding_needed = len(b64_string) % 4
        if padding_needed:
            b64_string += '=' * (4 - padding_needed)
        return base64.b64decode(b64_string).decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error("Base64 decoding failed: %s", str(e))
        return "[Base64 Decode Error]"

def extract_number_from_text(text: str) -> str:
    """Regex parser to extract phone numbers from notification templates."""
    match = re.search(r'From:\s*(\+?\d+)', text)
    if match:
        return match.group(1)
    return ""

def process_incoming_http_payload(data: dict) -> str:
    """
    Converts raw HTTP JSON payload from Asterisk into a formatted Telegram message.
    """
    caller_id = data.get("caller_id", "Unknown")
    b64_msg = data.get("b64_msg", "")
    decoded_msg = decode_base64_sms(b64_msg)
    
    formatted_text = (
        f"New SMS Received\n"
        f"From: {caller_id}\n"
        f"--------------------\n"
        f"{decoded_msg}"
    )
    return formatted_text

# --- Hardware Execution ---

def execute_asterisk_sms(target_number: str, message: str) -> bool:
    """Dispatches the SMS AT command via Asterisk CLI."""
    safe_message = sanitize_and_escape_text(message)
    
    if not safe_message:
        logger.warning("Message payload is empty after sanitization.")
        return False

    cmd_string = f'quectel sms quectel0 {target_number} "{safe_message}"'
    command = ["asterisk", "-rx", cmd_string]
    
    try:
        logger.info("Executing system command: %s", " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logger.info("Asterisk Output: %s", result.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Asterisk CLI rejected command: %s", e.stderr.strip() or e.stdout.strip())
        return False
    except Exception as e:
        logger.error("OS execution failed: %s", str(e))
        return False

# --- Telegram Async Handlers ---

async def command_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /sms command, preserving newlines and spacing."""
    raw_text = update.message.text
    
    # Use regex with DOTALL to capture multiline payloads accurately
    match = re.match(r'^/sms(?:@[^\s]+)?\s+(\+?\d+)\s+(.+)$', raw_text, re.DOTALL)
    
    if not match:
        await update.message.reply_text("Syntax error. Usage: /sms <phone_number> <message_content>")
        return

    target_number = match.group(1)
    message_content = match.group(2)
    
    success = execute_asterisk_sms(target_number, message_content)
    status = "Success" if success else "Failed"
    await update.message.reply_text(f"[ec20bot]: Send SMS to {target_number} -> {status}")

async def command_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles direct replies to existing SMS notifications."""
    original_message = update.message.reply_to_message
    if not original_message or not original_message.text:
        return
        
    target_number = extract_number_from_text(original_message.text)
    if not target_number:
        return
        
    reply_content = update.message.text
    success = execute_asterisk_sms(target_number, reply_content)
    
    status = "Success" if success else "Failed"
    await update.message.reply_text(f"[ec20bot]: Reply SMS to {target_number} -> {status}")