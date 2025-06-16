import os
import io
import json
import logging
from datetime import datetime
import tempfile
from dotenv import load_dotenv
import streamlit as st
import speech_recognition as sr
import pyttsx3
import boto3
import requests
import wikipedia
import webbrowser
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import pytemperature
import pywhatkit as pwt

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI', 'http://localhost:8888/callback')

# Initialize services with error handling
def initialize_services():
    """Initialize all external services with proper error handling"""
    services = {
        's3': None,
        'engine': None,
        'sp': None,
        'recognizer': None
    }
    
    # Initialize AWS S3 client
    try:
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and S3_BUCKET_NAME:
            services['s3'] = boto3.client(
                's3',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name='us-east-1'
            )
            # Verify bucket access
            services['s3'].head_bucket(Bucket=S3_BUCKET_NAME)
            logger.info("AWS S3 client initialized successfully")
    except Exception as e:
        logger.error(f"AWS S3 initialization failed: {str(e)}")
        services['s3'] = None

    # Initialize text-to-speech engine
    try:
        services['engine'] = pyttsx3.init()
        logger.info("Text-to-speech engine initialized")
    except Exception as e:
        logger.error(f"Text-to-speech initialization failed: {str(e)}")
        services['engine'] = None

    # Initialize Spotify
    try:
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            services['sp'] = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope="user-read-playback-state,user-modify-playback-state"
            ))
            logger.info("Spotify client initialized")
    except Exception as e:
        logger.error(f"Spotify initialization failed: {str(e)}")
        services['sp'] = None

    # Initialize speech recognizer
    try:
        services['recognizer'] = sr.Recognizer()
        logger.info("Speech recognizer initialized")
    except Exception as e:
        logger.error(f"Speech recognizer initialization failed: {str(e)}")
        services['recognizer'] = None

    return services

services = initialize_services()
s3 = services['s3']
engine = services['engine']
sp = services['sp']
recognizer = services['recognizer']

def speak(text):
    """Convert text to speech with error handling"""
    if not engine:
        st.warning("Text-to-speech engine not available")
        return
    
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        st.error(f"Error in text-to-speech: {str(e)}")

def recognize_speech():
    """Capture audio from microphone and convert to text"""
    if not recognizer:
        st.error("Speech recognition not available")
        return None
        
    try:
        with sr.Microphone() as source:
            st.session_state.listening = True
            st.rerun()  # Replaced experimental_rerun() with rerun()
            
            # Adjust for ambient noise
            recognizer.adjust_for_ambient_noise(source, duration=1)
            st.sidebar.info("Listening... (speak now)")
            
            # Listen with timeout
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            
            try:
                text = recognizer.recognize_google(audio)
                st.sidebar.success(f"You said: {text}")
                return text
            except sr.UnknownValueError:
                st.sidebar.warning("Could not understand audio")
            except sr.RequestError as e:
                st.sidebar.error(f"Speech recognition error: {str(e)}")
                
    except sr.WaitTimeoutError:
        st.sidebar.warning("Listening timed out (no speech detected)")
    except Exception as e:
        st.sidebar.error(f"Microphone error: {str(e)}")
        st.session_state.microphone_enabled = False
    finally:
        st.session_state.listening = False
        st.rerun()  # Replaced experimental_rerun() with rerun()
    
    return None

def get_weather(city):
    """Get weather data for a city with error handling"""
    if not WEATHER_API_KEY:
        return "Weather API not configured"
        
    base_url = "https://api.openweathermap.org/data/2.5/weather?"
    complete_url = f"{base_url}appid={WEATHER_API_KEY}&q={city}&units=metric"
    
    try:
        response = requests.get(complete_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("cod") != 200:
            return f"Weather error: {data.get('message', 'Unknown error')}"
            
        main = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        
        return (f"Weather in {city}: {weather.get('description', 'N/A')}. "
                f"Temperature: {main.get('temp', 'N/A')}°C, "
                f"feels like {main.get('feels_like', 'N/A')}°C. "
                f"Humidity: {main.get('humidity', 'N/A')}%")
                
    except requests.exceptions.RequestException as e:
        return f"Error fetching weather: {str(e)}"
    except Exception as e:
        return f"Error processing weather data: {str(e)}"

def search_wikipedia(query):
    """Search Wikipedia with error handling"""
    try:
        wikipedia.set_lang("en")
        return wikipedia.summary(query, sentences=2, auto_suggest=False)
    except wikipedia.exceptions.DisambiguationError as e:
        return f"Multiple matches. Be more specific. Options: {', '.join(e.options[:3])}..."
    except wikipedia.exceptions.PageError:
        return "No information found. Try different terms."
    except Exception as e:
        return f"Wikipedia error: {str(e)}"

def play_spotify(song_name):
    """Play a song on Spotify with error handling"""
    if not sp:
        return "Spotify not connected"
        
    try:
        results = sp.search(q=song_name, limit=1, type='track')
        if results['tracks']['items']:
            track = results['tracks']['items'][0]
            sp.start_playback(uris=[track['uri']])
            return f"Now playing: {track['name']} by {track['artists'][0]['name']}"
        return "Song not found."
    except Exception as e:
        return f"Spotify error: {str(e)}"

def search_google(query):
    """Search Google with error handling"""
    try:
        pwt.search(query)
        return f"Searching Google for: {query}"
    except Exception as e:
        return f"Search error: {str(e)}"

def process_command(command):
    """Process user command with validation"""
    if not command or not isinstance(command, str):
        return "Please provide a valid command"
    
    command = command.lower().strip()
    
    if not command:
        return "I didn't catch that. Please try again."
    
    if any(word in command for word in ["hello", "hi", "hey"]):
        return "Hello! How can I help?"
    elif "time" in command:
        return f"The time is {datetime.now().strftime('%H:%M')}"
    elif "date" in command:
        return f"Today is {datetime.now().strftime('%B %d, %Y')}"
    elif "weather" in command:
        city = command.replace("weather", "").replace("in", "").strip()
        return get_weather(city or "New York")
    elif "wikipedia" in command or "wiki" in command:
        query = command.replace("wikipedia", "").replace("wiki", "").strip()
        return search_wikipedia(query) if query else "Specify a search term"
    elif "play" in command and ("song" in command or "music" in command):
        song = command.replace("play", "").replace("song", "").replace("music", "").strip()
        return play_spotify(song) if song else "Specify a song"
    elif "search" in command and "google" in command:
        query = command.replace("search", "").replace("google", "").strip()
        return search_google(query) if query else "Specify a search"
    else:
        return search_google(command)

def save_to_s3(user_input, response):
    """Save interaction to S3 with error handling"""
    if not s3 or not S3_BUCKET_NAME:
        logger.warning("S3 not configured - skipping save")
        return False
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"interactions/{timestamp}.json"
    
    interaction = {
        "timestamp": timestamp,
        "input": user_input,
        "response": response
    }
    
    try:
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=filename,
            Body=json.dumps(interaction),
            ContentType='application/json'
        )
        logger.info(f"Saved to S3: {filename}")
        return True
    except Exception as e:
        logger.error(f"S3 save error: {str(e)}")
        st.sidebar.error("Failed to save interaction")
        return False

def load_history(limit=5):
    """Load interaction history from S3"""
    if not s3 or not S3_BUCKET_NAME:
        logger.warning("S3 not configured - cannot load history")
        return []
        
    try:
        objects = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix="interactions/")
        history = []
        
        if 'Contents' in objects:
            # Sort by last modified (newest first)
            for obj in sorted(objects['Contents'], 
                           key=lambda x: x['LastModified'], 
                           reverse=True)[:limit]:
                try:
                    file_obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=obj['Key'])
                    history.append(json.loads(file_obj['Body'].read().decode('utf-8')))
                except Exception as e:
                    logger.error(f"Error loading {obj['Key']}: {str(e)}")
        
        return history
    except Exception as e:
        logger.error(f"History load error: {str(e)}")
        st.sidebar.error("Failed to load history")
        return []

def main():
    # Initialize session state
    if 'listening' not in st.session_state:
        st.session_state.listening = False
    if 'microphone_enabled' not in st.session_state:
        st.session_state.microphone_enabled = True
    if 'history' not in st.session_state:
        st.session_state.history = load_history()

    # Page configuration
    st.set_page_config(
        page_title="Voice Assistant Pro",
        page_icon="🎙️",
        layout="centered",
        initial_sidebar_state="expanded"
    )

    # Sidebar for controls
    with st.sidebar:
        st.title("Assistant Controls")
        
        # Service status indicators
        st.markdown("### Service Status")
        cols = st.columns(2)
        cols[0].metric("AWS S3", "Connected" if s3 else "Disabled")
        cols[1].metric("Speech", "Ready" if recognizer else "Disabled")
        
        # Voice input
        if st.button("🎤 Voice Command", disabled=not st.session_state.microphone_enabled):
            user_input = recognize_speech()
            if user_input:
                response = process_command(user_input)
                st.success(f"Assistant: {response}")
                speak(response)
                if save_to_s3(user_input, response):
                    st.session_state.history = load_history()
                    st.rerun()  # Replaced experimental_rerun() with rerun()
        
        # Text input
        user_input = st.text_input("Type command:")
        if user_input:
            response = process_command(user_input)
            st.success(f"Assistant: {response}")
            speak(response)
            if save_to_s3(user_input, response):
                st.session_state.history = load_history()
                st.rerun()  # Replaced experimental_rerun() with rerun()
        
        # History section
        st.markdown("---")
        st.subheader("Recent Interactions")
        for i, interaction in enumerate(st.session_state.history):
            with st.expander(f"{interaction.get('timestamp')}"):
                st.write(f"**You**: {interaction.get('input')}")
                st.write(f"**Assistant**: {interaction.get('response')}")

    # Main content area
    st.title("🎙️ Voice Assistant Pro")
    st.markdown("""
    Control with voice or text commands. Supported features:
    - Weather forecasts
    - Wikipedia lookups
    - Spotify music playback
    - Web searches
    - Time/date information
    """)

    # Quick action buttons
    st.subheader("Quick Actions")
    cols = st.columns(4)
    
    with cols[0]:
        if st.button("⏰ Current Time"):
            response = process_command("time")
            st.success(response)
            speak(response)
    
    with cols[1]:
        if st.button("📅 Today's Date"):
            response = process_command("date")
            st.success(response)
            speak(response)
    
    with cols[2]:
        city = st.text_input("🌤️ Get weather for:", "New York")
        if st.button("Check Weather"):
            response = process_command(f"weather {city}")
            st.success(response)
            speak(response)
    
    with cols[3]:
        search = st.text_input("🔍 Search for:")
        if st.button("Web Search"):
            response = process_command(f"search {search}")
            st.success(response)
            speak(response)

    # Visual feedback when listening
    if st.session_state.listening:
        st.markdown("""
        <div style="text-align: center; margin: 2rem;">
            <div style="
                width: 120px; height: 120px;
                border-radius: 50%;
                background: #ff4b4b;
                margin: 0 auto;
                display: flex;
                align-items: center;
                justify-content: center;
                animation: pulse 1.5s infinite;
            ">
                <span style="font-size: 48px;">🎤</span>
            </div>
            <p style="text-align: center; font-size: 1.2rem; margin-top: 1rem;">
                Listening... Speak now
            </p>
        </div>
        <style>
            @keyframes pulse {
                0% { transform: scale(0.95); opacity: 0.7; }
                50% { transform: scale(1.05); opacity: 1; }
                100% { transform: scale(0.95); opacity: 0.7; }
            }
        </style>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()