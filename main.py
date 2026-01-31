import logging
import json
import os
import types
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

# Get API keys from environment
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Configure Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Reduce httpx logging noise
logging.getLogger('httpx').setLevel(logging.WARNING)

try: 
    with open('data.json', 'r', encoding='utf-8') as f:
        RESPONSES = json.load(f)
    CATEGORIES = list(RESPONSES.keys())
    print(f"Script of responses loaded. Categories: {CATEGORIES}")
except FileNotFoundError:
    RESPONSES = {}
    CATEGORIES = []
    print("Did not find data.json file. Starting with empty responses.")
    
# Initialize Gemini model
GEMINI_MODEL = "gemini-flash-latest"
if GEMINI_API_KEY:
    print(f"Gemini model '{GEMINI_MODEL}' configured.")
else:
    print("Warning: GEMINI_API_KEY not found in environment variables.")

def detect_language(text: str) -> str:
    """Detect if the text is spanish or english"""
    spanish_indicators = [
        'qué', 'cómo', 'cuándo', 'dónde', 'por qué', 'cuál', 'cuáles',
        'puedo', 'necesito', 'quiero', 'ayuda', 'información',
        'países', 'incluye', 'recibo', 'apoyo', 'empezar', 'contactar',
        'hola', 'gracias', 'favor', 'más', 'sí', 'no', 'bueno',
        'también', 'esto', 'eso', 'aquí', 'allí', 'ahora', 'después'
    ]
    
    # Common English words that rarely appear in Spanish
    english_indicators = [
        'what', 'how', 'when', 'where', 'why', 'which', 'who',
        'can', 'need', 'want', 'help', 'information', 'the', 'is',
        'are', 'this', 'that', 'here', 'there', 'now', 'later'
    ]

    text_lower = text.lower()
    spanish_count = sum(1 for indicator in spanish_indicators if indicator in text_lower)
    english_count = sum(1 for indicator in english_indicators if indicator in text_lower)
    
    print(f"DEBUG Language Detection: Spanish={spanish_count}, English={english_count}")
    
    # If we find more Spanish indicators, it's Spanish
    if spanish_count > english_count:
        return 'es'
    elif english_count > 0:
        return 'en'
    
    # Default to English if no clear indicators
    return 'en'

async def translate_response(response_text: str, target_language: str) -> str:
    """Translate response using Gemini model."""
    if target_language == 'en':
        return response_text  # No translation needed
    if not GEMINI_API_KEY:
        print("Warning: No Gemini API key, cannot translate.")
        return response_text
    try: 
        model = genai.GenerativeModel(GEMINI_MODEL)
        translation_prompt = f"""
Translate the following text to Spanish. Keep it professional and natural.
Do not add any extra explanation, just provide the translation.

Text to translate:
{response_text}

Translation:
"""
        response = model.generate_content(
            translation_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                max_output_tokens=500,
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error during translation: {e}")
        return response_text  # Return original if translation fails

    
# Function for prompting 

def get_classification_prompt(user_question: str) -> str:  
    """Builds the prompt for classifying the user's question."""
    
    # Create a mapping of categories with examples in Spanish and English
    category_examples = {
        'GREETING': 'hola, hi, hello, interesado, interested, quiero información, want information',
        'WHAT_IS_REALTYPLUS': 'qué es RealtyPlus, what is RealtyPlus, información sobre la empresa, company information',
        'INTERNATIONAL_PRESENCE': 'en qué países operan, where do you operate, dónde están, countries',
        'FRANCHISE_VS_MASTER': 'diferencia entre franquicia y master, difference between franchise and master',
        'REQUIRED_EXPERIENCE': 'necesito experiencia, do I need experience, requisitos de experiencia',
        'REVENUE_STREAMS': 'cómo gano dinero, how do I make money, ingresos, revenue',
        'SCALABILITY': 'es escalable, is it scalable, growth, crecimiento, negocio escalable',
        'OWN_BRAND': 'puedo mantener mi marca, can I keep my brand, co-branding',
        'PHYSICAL_OFFICE': 'necesito oficina física, do I need physical office, oficina',
        'SUPPORT_AND_TRAINING': 'qué apoyo recibo, what support do I get, capacitación, training, manuales',
        'MARKETING_SUPPORT': 'ayuda de marketing, marketing help, publicidad, advertising',
        'TECHNOLOGY': 'herramientas tecnológicas, technology tools, software, digital tools',
        'INTERNATIONAL_CLIENTS': 'clientes internacionales, international clients, inversores, investors, cross-border',
        'OBJECTION_LIMITED_TIME': 'no tengo tiempo, limited time, dedicación, dedication, part-time',
        'OBJECTION_MARKET_DOUBTS': 'funcionará en mi país, market doubts, dudas mercado, will it work',
        'DOCUMENTATION': 'folleto, brochure, presentación, presentation, enviar información, documentos',
        'HUMAN_CONTACT': 'hablar con alguien, speak with someone, llamada, call, expansión, expansion team',
        'SOFT_CLOSING': 'siguiente paso, next step, cómo proceder, begin, schedule call',
    }
    
    categories_with_hints = '\n'.join([
        f"- {cat}: ({category_examples.get(cat, '')})" 
        for cat in CATEGORIES
    ])
    
    return f"""
You are a question classifier for a franchise support system. 
Analyze the user's question (it may be in Spanish or English) and return ONLY the category keyword that best matches.

Strict Rules:
1. Return ONLY ONE keyword from the list below
2. Return it in UPPERCASE with no extra text or explanation
3. If no category matches well, return 'OTHER'

Categories with example keywords:
{categories_with_hints}

User Question: {user_question}

Return only the category keyword:
"""

async def get_category_from_ai(user_question: str) -> str:
    """Uses the AI model to classify the user's question into a category."""
    
    if not GEMINI_API_KEY:
        print("Warning: No Gemini API key, returning OTHER")
        return "OTHER"
    
    full_prompt = get_classification_prompt(user_question)

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            full_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.0,
                max_output_tokens=50,
            )
        )

        classified_category = response.text.strip().upper()
        print(f"DEBUG: User asked: '{user_question}'")
        print(f"DEBUG: AI classified as: '{classified_category}'")

        if classified_category in CATEGORIES:
            return classified_category
        else:
            print(f"DEBUG: AI returned invalid category '{classified_category}'. Defaulting to 'OTHER'.")
            return "OTHER"
        
    except Exception as e:
        print(f"Error during AI classification: {e}")
        print(f"Using fallback keyword matching instead...")
        # Fallback: simple keyword matching
        user_question_lower = user_question.lower()
        if 'qué es' in user_question_lower or 'what is' in user_question_lower:
            return 'WHAT_IS_REALTYPLUS'
        elif 'países' in user_question_lower or 'countries' in user_question_lower:
            return 'COUNTRIES_OPERATING_IN'
        elif 'incluye' in user_question_lower or 'included' in user_question_lower:
            return 'FRANCHISE_INCLUSIONS'
        elif 'empezar' in user_question_lower or 'started' in user_question_lower:
            return 'STEPS_TO_GET_STARTED'
        elif 'contactar' in user_question_lower or 'contact' in user_question_lower:
            return 'CONTACT_EXPANSION_TEAM'
        else:
            return "OTHER"


def find_similar_categories(user_question: str, top_n=3):
    """Find similar categories based on keyword matching."""
    user_question_lower = user_question.lower()
    
    keyword_map = {
        'GREETING': ['hola', 'hi', 'hello', 'interesado', 'interested', 'información', 'info'],
        'WHAT_IS_REALTYPLUS': ['qué es', 'what is', 'información', 'empresa', 'company', 'realtyplus'],
        'INTERNATIONAL_PRESENCE': ['países', 'countries', 'dónde', 'where', 'ubicación', 'location', 'operan'],
        'FRANCHISE_VS_MASTER': ['diferencia', 'difference', 'master', 'franquicia vs', 'franchise vs'],
        'REQUIRED_EXPERIENCE': ['experiencia', 'experience', 'necesito', 'requisitos', 'requirements'],
        'REVENUE_STREAMS': ['gano dinero', 'make money', 'ingresos', 'revenue', 'ganancias', 'profit'],
        'SCALABILITY': ['escalable', 'scalable', 'crecimiento', 'growth', 'futuro'],
        'OWN_BRAND': ['mi marca', 'my brand', 'propia marca', 'own brand', 'nombre', 'name'],
        'PHYSICAL_OFFICE': ['oficina', 'office', 'física', 'physical', 'local'],
        'SUPPORT_AND_TRAINING': ['apoyo', 'support', 'ayuda', 'help', 'capacitación', 'training'],
        'MARKETING_SUPPORT': ['marketing', 'publicidad', 'advertising', 'promoción'],
        'TECHNOLOGY': ['tecnología', 'technology', 'herramientas', 'tools', 'platform', 'sistema'],
        'INTERNATIONAL_CLIENTS': ['internacional', 'international', 'clientes', 'clients', 'extranjeros'],
        'OBJECTION_LIMITED_TIME': ['tiempo', 'time', 'dedicación', 'dedication', 'ocupado', 'busy'],
        'OBJECTION_MARKET_DOUBTS': ['mercado', 'market', 'país', 'country', 'dudas', 'doubt', 'funciona', 'work'],
        'DOCUMENTATION': ['documentos', 'documents', 'folleto', 'brochure', 'pdf', 'presentación'],
        'HUMAN_CONTACT': ['contactar', 'contact', 'hablar', 'speak', 'llamada', 'call', 'persona', 'person'],
        'SOFT_CLOSING': ['siguiente', 'next', 'paso', 'step', 'empezar', 'start', 'proceder'],
    }
    
    matches = []
    for category, keywords in keyword_map.items():
        score = sum(1 for keyword in keywords if keyword in user_question_lower)
        if score > 0:
            matches.append((category, score))
    
    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)
    return [cat for cat, score in matches[:top_n]]


def get_category_display_name(category: str, language: str = 'en') -> str:
    """Convert category key to friendly display name."""
    names_en = {
        'GREETING': 'Greeting',
        'WHAT_IS_REALTYPLUS': 'What is RealtyPlus?',
        'INTERNATIONAL_PRESENCE': 'International Presence',
        'FRANCHISE_VS_MASTER': 'Franchise vs Master Franchise',
        'REQUIRED_EXPERIENCE': 'Required Experience',
        'REVENUE_STREAMS': 'Revenue Streams',
        'SCALABILITY': 'Scalability',
        'OWN_BRAND': 'Own Brand',
        'PHYSICAL_OFFICE': 'Physical Office',
        'SUPPORT_AND_TRAINING': 'Support & Training',
        'MARKETING_SUPPORT': 'Marketing Support',
        'TECHNOLOGY': 'Technology',
        'INTERNATIONAL_CLIENTS': 'International Clients',
        'OBJECTION_LIMITED_TIME': 'Limited Time Objection',
        'OBJECTION_MARKET_DOUBTS': 'Market Doubts Objection',
        'DOCUMENTATION': 'Documentation',
        'HUMAN_CONTACT': 'Human Contact',
        'SOFT_CLOSING': 'Next Steps',
    }

    names_es = {
        'GREETING': 'Saludo',
        'WHAT_IS_REALTYPLUS': '¿Qué es RealtyPlus?',
        'INTERNATIONAL_PRESENCE': 'Presencia Internacional',
        'FRANCHISE_VS_MASTER': 'Franquicia vs Master Franquicia',
        'REQUIRED_EXPERIENCE': 'Experiencia Requerida',
        'REVENUE_STREAMS': 'Fuentes de Ingresos',
        'SCALABILITY': 'Escalabilidad',
        'OWN_BRAND': 'Marca Propia',
        'PHYSICAL_OFFICE': 'Oficina Física',
        'SUPPORT_AND_TRAINING': 'Soporte y Entrenamiento',
        'MARKETING_SUPPORT': 'Soporte de Marketing',
        'TECHNOLOGY': 'Tecnología',
        'INTERNATIONAL_CLIENTS': 'Clientes Internacionales',
        'OBJECTION_LIMITED_TIME': 'Objeción: Tiempo Limitado',
        'OBJECTION_MARKET_DOUBTS': 'Objeción: Dudas del Mercado',
        'DOCUMENTATION': 'Documentación',
        'HUMAN_CONTACT': 'Contacto Humano',
        'SOFT_CLOSING': 'Próximos Pasos',
    }
    if language == 'es':
        return names_es.get(category, category)
    return names_en.get(category, category)
    


# Telegram bot handlers

async def start(update: Update, context):
    """Responds to the /start command."""
    # Reset user language on start if needed, or default to English
    # We send the default GREETING from the database
    greeting_text = RESPONSES.get('GREETING')
    
    if not greeting_text:
        # Fallback if data.json is empty or missing GREETING
        greeting_text = "Hello! Welcome to RealtyPlus. How can I help you today?"
        
    await update.message.reply_text(greeting_text)

async def handle_message(update: Update, context):
    """Use the ai to classify the user's question and respond accordingly."""

    user_text = update.message.text
    user_id = update.effective_user.id

    # Check if we already have a saved language for this user
    if 'user_language' in context.user_data:
        # Use the saved language
        language = context.user_data['user_language']
        print(f"DEBUG: Using saved language for user: {language}")
    else:
        # First message from user, detect language and save it
        language = detect_language(user_text)
        context.user_data['user_language'] = language
        print(f"DEBUG: First message - Detected and saved language: {language}")
    
    # Check if user is responding to a suggestion
    if context.user_data.get('awaiting_confirmation'):
        # User is selecting from suggested categories
        try:
            choice = int(user_text)
            suggested = context.user_data.get('suggested_categories', [])
            
            if 1 <= choice <= len(suggested):
                category = suggested[choice - 1]
                context.user_data['awaiting_confirmation'] = False
                
                if category in RESPONSES:
                    response_text = RESPONSES[category]
                    # Translate if needed using saved language
                    response_text = await translate_response(response_text, language)
                    await update.message.reply_text(response_text)
                    
                    follow_up = "\n¿Tienes otra pregunta? Pregúntame lo que quieras." if language == 'es' else "\nDo you have another question? Feel free to ask me anything."
                    await update.message.reply_text(follow_up)
                return
            else:
                error_msg = "Por favor selecciona un número válido de la lista." if language == 'es' else "Please select a valid number from the list."
                await update.message.reply_text(error_msg)
                return
        except ValueError:
            # User didn't send a number, treat as new question
            context.user_data['awaiting_confirmation'] = False
    
    # Save the current language for future reference
    context.user_data['user_language'] = language
    
    # Classify the question using AI
    category = await get_category_from_ai(user_text)

    # Search the response in the script
    if category in RESPONSES:
        response_text = RESPONSES[category]
        # Translate response to user's language
        response_text = await translate_response(response_text, language)
        await update.message.reply_text(response_text)
        
        follow_up = "\n¿Tienes otra pregunta? Pregúntame lo que quieras." if language == 'es' else "\nDo you have another question? Feel free to ask me anything."
        await update.message.reply_text(follow_up)

    else: 
        # Try to find similar categories
        similar = find_similar_categories(user_text, top_n=3)
        
        if similar:
            context.user_data['awaiting_confirmation'] = True
            context.user_data['suggested_categories'] = similar
            context.user_data['user_language'] = language  # Save language for when user selects option
            
            if language == 'es':
                suggestion_text = "No estoy seguro de haber entendido tu pregunta. ¿Te refieres a alguna de estas opciones?\n\n"
            else:
                suggestion_text = "I'm not sure I understood your question. Did you mean one of these options?\n\n"
            
            for idx, cat in enumerate(similar, 1):
                suggestion_text += f"{idx}. {get_category_display_name(cat, language)}\n"
            
            if language == 'es':
                suggestion_text += "\nEscribe el número de la opción que te interesa, o reformula tu pregunta."
            else:
                suggestion_text += "\nType the number of the option you're interested in, or rephrase your question."
            
            await update.message.reply_text(suggestion_text)
        else:
            if language == 'es':
                default_response = "Lo siento, no tengo una respuesta específica para esa pregunta. Por favor contacta a nuestro equipo de expansión para más información, o intenta reformular tu pregunta."
            else:
                default_response = "I'm sorry, I don't have a specific answer for that question. Please contact our expansion team for more information, or try rephrasing your question."
            await update.message.reply_text(default_response)

# Principal function of the bot

def main():
    """Starts the Telegram bot."""

    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
        return
        
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started. Listening for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
