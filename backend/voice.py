import os
import asyncio
import pydub
import edge_tts
import numpy as np
import websockets
import json
import io
import openai
import subprocess
import tempfile
from pydub import AudioSegment
from pydub.playback import play
from dotenv import load_dotenv

#Load the variables from the .env file into memory
load_dotenv()

# -- CONFIGURATION --
VOICE_NORMAL = "en-US-AnaNeural"
VOICE_ANGRY = "en-US-ChristopherNeural"
MODEL = "llama-3.1-8b-instant"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")


client = openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

connected_clients = set() # Track connected WebSocket clients

# Check if ffmpeg is installed using subprocess
def is_ffmpeg_installed():
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# Convert text to speech using edge-tts and return as pydub AudioSegment
async def speak_text(text, is_angry, current_websocket):
    """Downloads audio and streams volume data chunk-by-chunk."""
    if not text or not text.strip():
        return
    voice = VOICE_ANGRY if is_angry else VOICE_NORMAL
    pitch = "-50Hz" if is_angry else "+10Hz"
    voice_rate = "-15%" if is_angry else "+0%"
    
    try:
        #Download the audio data from edge-tts
        mp3_bytes = io.BytesIO() # Create an in-memory bytes buffer(temporary invisible file to store the audio data)
        communicate = edge_tts.Communicate(text, voice, rate=voice_rate, pitch=pitch)
        async for chunk in communicate.stream():# Keep pipeline open for live data packets
            if chunk["type"] == "audio":
                mp3_bytes.write(chunk["data"]) #writes the audio data to the in-memory buffer as it arrives
        
        mp3_bytes.seek(0)
        raw_audio_binary = mp3_bytes.read() # Get the entire raw audio data as bytes
        
        
        await current_websocket.send(raw_audio_binary)
        
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"Error in speak_text: {e}")
        

#Loading the Prompt from a file
def load_prompt(filename = None):
    if filename is None:
        base = os.path.dirname(os.path.abspath(__file__))
        filename = os.path.join(base, "prompt.txt")
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error loading prompt: {e}")
        return ("YOU ARE A Helpful and Honest Assistant. Answer as concisely as possible. constantly maintain ANGER_LEVEL:0 at start of every response. Anger will rise if user makes you angry.")
    
#CHAT API CALL
def chat(user_input,messages):
    try:
        messages.append({"role": "user", "content": user_input})
        
        response = client.chat.completions.create(model=MODEL, messages=messages,temperature=0.9, max_tokens=90)
        reply = response.choices[0].message.content
        messages.append({"role": "assistant", "content": reply})
        return reply
    except openai.APITimeoutError:
        print("!!! Groq API Timed Out !!!")
        # Return a fallback string matching your start-of-text tag setup
        return "[ANGER_LEVEL:0] Ugh, my brain stalled for a second. Try saying that again."
    except Exception as e:
        print(f"!!! OpenAI/Groq API Error: {e} !!!")
        return "[ANGER_LEVEL:0] Sorry, I encountered an unexpected error."
    
    
async def websocket_handler(websocket):
    connected_clients.add(websocket)
    print("Browser connected")
    
    # Initialize messages for this specific session
    messages = [{"role": "system", "content": load_prompt()}]
    
    # Track the currently active speech task so we can interrupt it if needed
    current_speech_task = None
    
    try:
        async for message in websocket:
            
            # Skip any raw binary audio arrays reflected back from client scopes
            if isinstance(message, bytes):
                continue
            
            # 1. Receive JSON from the browser
            data = json.loads(message)
            user_text = data.get("text")
            
            if user_text:
                print(f"User said: {user_text}")
                
                # --- INTERRUPT OLD SPEECH IF IT'S STILL RUNNING ---
                if current_speech_task and not current_speech_task.done():
                    print("Interrupting current speech for new user input...")
                    current_speech_task.cancel()
                    try:
                        await current_speech_task  # Await cancellation completion
                    except asyncio.CancelledError:
                        pass
                
                # 2. Get AI response
                answer = chat(user_text, messages)
                
                anger_score = int(answer.split("[ANGER_LEVEL:")[1].split("]")[0])
                is_angry = anger_score > 90
                
                spoken_answer = answer.split("]")[1].strip()
            
                
                if anger_score == 100:
                    print("!!! GAME OVER - TRIGGERING THUNDER !!!")
                    await websocket.send(json.dumps({"type": "play_thunder"}))
                    
                # 3. Send the text reply back to the browser chatbox
                await websocket.send(json.dumps({
                    "type": "text", 
                    "text": spoken_answer,
                    "trigger": "go_red" if is_angry else "default",
                    "anger_score": anger_score
                }))

                # 5. Trigger the AI voice
                current_speech_task = asyncio.create_task(speak_text(spoken_answer, is_angry, websocket))

    except websockets.exceptions.ConnectionClosed:
        print("Browser disconnected")
    finally:
        connected_clients.discard(websocket)

async def main():
    port = int(os.environ.get("PORT", 8765))  # Railway sets PORT automatically
    # Start the WebSocket server on port 8765
    async with websockets.serve(websocket_handler, "0.0.0.0", port):
        print("JelloBait Backend is online")
        print("Waiting for browser connection...")
        
        # This keeps the main function running forever
        await asyncio.Future()        
        
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nJelloBait is going offline. Goodbye!")
