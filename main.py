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
        'WHAT_IS_REALTYPLUS': 'qué es RealtyPlus, what is RealtyPlus, información sobre la empresa, company information',
        'COUNTRIES_OPERATING_IN': 'en qué países operan, where do you operate, dónde están, countries',
        'FRANCHISE_INCLUSIONS': 'qué incluye la franquicia, what is included, qué recibo, what do I get',
        'FRANCHISE_VS_MASTER': 'diferencia entre franquicia y master, difference between franchise and master',
        'REAL_ESTATE_EXPERIENCE_REQ': 'necesito experiencia, do I need experience, requisitos de experiencia',
        'START_ALONE_OR_TEAM': 'puedo empezar solo, can I start alone, necesito equipo, do I need a team',
        'ONBOARDING_LAUNCH_TIME': 'cuánto tiempo para empezar, how long to start, tiempo de lanzamiento',
        'SUPPORT_RECEIVED': 'qué apoyo recibo, what support do I get, ayuda',
        'OPERATE_INTERNATIONALLY': 'puedo operar internacionalmente, can I work internationally, trabajo global',
        'STEPS_TO_GET_STARTED': 'cómo empezar, how to start, pasos para comenzar, steps to begin',
        'AREA_EXCLUSIVITY': 'exclusividad territorial, area exclusivity, territorio exclusivo',
        'MARKETING_ASSISTANCE': 'ayuda de marketing, marketing help, publicidad, advertising support',
        'RECRUITMENT_ASSISTANCE': 'ayuda para reclutar, recruitment help, contratar equipo',
        'TECHNOLOGY_TOOLS_OFFERED': 'herramientas tecnológicas, technology tools, plataformas digitales',
        'CONTACT_EXPANSION_TEAM': 'contactar, contact, hablar con alguien, speak with someone, agendar llamada, schedule call',
        'WHERE_CAN_I_OPEN': 'dónde puedo abrir, where can I open, ubicaciones disponibles',
        'WHY_CHOOSE_REALTYPLUS': 'por qué elegir RealtyPlus, why choose RealtyPlus, ventajas, benefits',
        'RECEIVE_DOCUMENTS_BROCHURE': 'recibir documentos, receive documents, folleto, brochure, información',
        'TIME_DEDICATION_REQUIRED': 'cuánto tiempo necesito dedicar, how much time required, dedicación',
        'PHYSICAL_OFFICE_NEED': 'necesito oficina física, do I need physical office, oficina',
        'TRAINING_FOR_TEAM': 'capacitación, training, entrenamiento, formación para el equipo',
        'EXPAND_TO_MULTIPLE_CITIES': 'expandir a más ciudades, expand to multiple cities, varias ubicaciones',
        'VISIT_HEADQUARTERS': 'visitar oficinas, visit headquarters, conocer la sede',
        'GROW_BEYOND_SALES': 'crecer más allá de ventas, grow beyond sales, otros servicios',
        'MULTIPLE_LANGUAGES_REQ': 'necesito hablar idiomas, need multiple languages, requisitos de idioma',
        'MAIN_REQUIREMENTS_JOIN': 'requisitos principales, main requirements, qué necesito para unirme',
        'CONTACT_OTHER_FRANCHISEES': 'contactar otros franquiciados, contact other franchisees, testimonios',
        'HOW_INTERNATIONAL_SYSTEM_WORKS': 'cómo funciona el sistema internacional, how international system works',
        'GROW_QUICKLY_POSSIBLE': 'puedo crecer rápido, can I grow quickly, crecimiento rápido',
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
        'WHAT_IS_REALTYPLUS': ['qué es', 'what is', 'información', 'empresa', 'company', 'realtyplus'],
        'COUNTRIES_OPERATING_IN': ['países', 'countries', 'dónde', 'where', 'ubicación', 'location', 'operan'],
        'FRANCHISE_INCLUSIONS': ['incluye', 'included', 'qué recibo', 'what do i get', 'beneficios', 'benefits'],
        'FRANCHISE_VS_MASTER': ['diferencia', 'difference', 'master', 'franquicia vs'],
        'REAL_ESTATE_EXPERIENCE_REQ': ['experiencia', 'experience', 'necesito', 'requisitos'],
        'START_ALONE_OR_TEAM': ['solo', 'alone', 'equipo', 'team'],
        'ONBOARDING_LAUNCH_TIME': ['cuánto tiempo', 'how long', 'tiempo', 'launch', 'empezar'],
        'SUPPORT_RECEIVED': ['apoyo', 'support', 'ayuda', 'help'],
        'OPERATE_INTERNATIONALLY': ['internacional', 'international', 'global'],
        'STEPS_TO_GET_STARTED': ['cómo empezar', 'how to start', 'pasos', 'steps', 'comenzar'],
        'AREA_EXCLUSIVITY': ['exclusividad', 'exclusivity', 'territorio', 'territory'],
        'MARKETING_ASSISTANCE': ['marketing', 'publicidad', 'advertising'],
        'RECRUITMENT_ASSISTANCE': ['reclutar', 'recruitment', 'contratar', 'hiring'],
        'TECHNOLOGY_TOOLS_OFFERED': ['tecnología', 'technology', 'herramientas', 'tools', 'plataforma'],
        'CONTACT_EXPANSION_TEAM': ['contactar', 'contact', 'hablar', 'llamada', 'call', 'reunión'],
        'WHERE_CAN_I_OPEN': ['dónde puedo', 'where can', 'abrir', 'open'],
        'WHY_CHOOSE_REALTYPLUS': ['por qué', 'why', 'elegir', 'choose', 'ventajas'],
        'RECEIVE_DOCUMENTS_BROCHURE': ['documentos', 'documents', 'folleto', 'brochure'],
        'TIME_DEDICATION_REQUIRED': ['dedicación', 'dedication', 'tiempo dedicar'],
        'PHYSICAL_OFFICE_NEED': ['oficina', 'office', 'física', 'physical'],
        'TRAINING_FOR_TEAM': ['capacitación', 'training', 'entrenamiento', 'formación'],
        'EXPAND_TO_MULTIPLE_CITIES': ['expandir', 'expand', 'ciudades', 'cities'],
        'VISIT_HEADQUARTERS': ['visitar', 'visit', 'oficinas', 'headquarters'],
        'GROW_BEYOND_SALES': ['crecer', 'grow', 'más allá', 'beyond'],
        'MULTIPLE_LANGUAGES_REQ': ['idiomas', 'languages'],
        'MAIN_REQUIREMENTS_JOIN': ['requisitos', 'requirements', 'unirme', 'join'],
        'CONTACT_OTHER_FRANCHISEES': ['franquiciados', 'franchisees', 'testimonios'],
        'HOW_INTERNATIONAL_SYSTEM_WORKS': ['sistema', 'system', 'funciona', 'works'],
        'GROW_QUICKLY_POSSIBLE': ['rápido', 'quickly', 'rápidamente'],
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
        'WHAT_IS_REALTYPLUS': 'What is RealtyPlus?',
        'COUNTRIES_OPERATING_IN': 'What countries do you operate in?',
        'FRANCHISE_INCLUSIONS': 'What does the franchise include?',
        'FRANCHISE_VS_MASTER': 'Difference between franchise and master franchise',
        'REAL_ESTATE_EXPERIENCE_REQ': 'Real estate experience required',
        'START_ALONE_OR_TEAM': 'Can I start alone or do I need a team?',
        'ONBOARDING_LAUNCH_TIME': 'Time to get started',
        'SUPPORT_RECEIVED': 'Support I will receive',
        'OPERATE_INTERNATIONALLY': 'International operations',
        'STEPS_TO_GET_STARTED': 'Steps to get started',
        'AREA_EXCLUSIVITY': 'Area exclusivity',
        'MARKETING_ASSISTANCE': 'Marketing assistance',
        'RECRUITMENT_ASSISTANCE': 'Recruitment assistance',
        'TECHNOLOGY_TOOLS_OFFERED': 'Technology tools offered',
        'CONTACT_EXPANSION_TEAM': 'Contact the expansion team',
        'WHERE_CAN_I_OPEN': 'Where can I open?',
        'WHY_CHOOSE_REALTYPLUS': 'Why choose RealtyPlus?',
        'RECEIVE_DOCUMENTS_BROCHURE': 'Receive documents/brochure',
        'TIME_DEDICATION_REQUIRED': 'Time dedication required',
        'PHYSICAL_OFFICE_NEED': 'Physical office requirement',
        'TRAINING_FOR_TEAM': 'Training for the team',
        'EXPAND_TO_MULTIPLE_CITIES': 'Expand to multiple cities',
        'VISIT_HEADQUARTERS': 'Visit headquarters',
        'GROW_BEYOND_SALES': 'Grow beyond sales',
        'MULTIPLE_LANGUAGES_REQ': 'Multiple languages requirement',
        'MAIN_REQUIREMENTS_JOIN': 'Main requirements to join',
        'CONTACT_OTHER_FRANCHISEES': 'Contact other franchisees',
        'HOW_INTERNATIONAL_SYSTEM_WORKS': 'How the international system works',
        'GROW_QUICKLY_POSSIBLE': 'Possibility of growing quickly',
    }

    names_es = {
        'WHAT_IS_REALTYPLUS': '¿Qué es RealtyPlus?',
        'COUNTRIES_OPERATING_IN': '¿En qué países operan?',
        'FRANCHISE_INCLUSIONS': '¿Qué incluye la franquicia?',
        'FRANCHISE_VS_MASTER': 'Diferencia entre franquicia y master franquicia',
        'REAL_ESTATE_EXPERIENCE_REQ': 'Experiencia en bienes raíces requerida',
        'START_ALONE_OR_TEAM': '¿Puedo empezar solo o necesito un equipo?',
        'ONBOARDING_LAUNCH_TIME': 'Tiempo para empezar',
        'SUPPORT_RECEIVED': 'Apoyo que recibiré',
        'OPERATE_INTERNATIONALLY': 'Operaciones internacionales',
        'STEPS_TO_GET_STARTED': 'Pasos para comenzar',
        'AREA_EXCLUSIVITY': 'Exclusividad territorial',
        'MARKETING_ASSISTANCE': 'Ayuda de marketing',
        'RECRUITMENT_ASSISTANCE': 'Ayuda de reclutamiento',
        'TECHNOLOGY_TOOLS_OFFERED': 'Herramientas tecnológicas ofrecidas',
        'CONTACT_EXPANSION_TEAM': 'Contactar al equipo de expansión',
        'WHERE_CAN_I_OPEN': '¿Dónde puedo abrir?',
        'WHY_CHOOSE_REALTYPLUS': '¿Por qué elegir RealtyPlus?',
        'RECEIVE_DOCUMENTS_BROCHURE': 'Recibir documentos/folleto',
        'TIME_DEDICATION_REQUIRED': 'Tiempo de dedicación requerido',
        'PHYSICAL_OFFICE_NEED': 'Requisito de oficina física',
        'TRAINING_FOR_TEAM': 'Capacitación para el equipo',
        'EXPAND_TO_MULTIPLE_CITIES': 'Expandir a múltiples ciudades',
        'VISIT_HEADQUARTERS': 'Visitar la sede',
        'GROW_BEYOND_SALES': 'Crecer más allá de las ventas',
        'MULTIPLE_LANGUAGES_REQ': 'Requisito de múltiples idiomas',
        'MAIN_REQUIREMENTS_JOIN': 'Requisitos principales para unirse',
        'CONTACT_OTHER_FRANCHISEES': 'Contactar a otros franquiciados',
        'HOW_INTERNATIONAL_SYSTEM_WORKS': 'Cómo funciona el sistema internacional',
        'GROW_QUICKLY_POSSIBLE': 'Posibilidad de crecer rápidamente',
    }
    if language == 'es':
        return names_es.get(category, category)
    return names_en.get(category, category)
    


# Telegram bot handlers

async def start(update: Update, context):
    """Responds to the /start command."""
    welcome_text = """Hello! 👋 I'm your RealtyPlus assistant. 
    (If your want to make the questions in spanish you can, I will respond to you in Spanish too)

I can help you with information about:
• What is RealtyPlus
• Franchises and requirements
• Countries where we operate
• Support and training
• Steps to get started
• And much more...

What would you like to know?"""
    
    await update.message.reply_text(welcome_text)

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
