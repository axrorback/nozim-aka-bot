import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from telebot import TeleBot
bot = TeleBot(os.environ.get('TELEGRAM_BOT_TOKEN'))