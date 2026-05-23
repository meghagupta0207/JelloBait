import os
import asyncio
import pydub
import edge_tts
import numpy as np
import websockets
import json
import io
import openai
from openai import AsyncOpenAI
import subprocess
import tempfile
import uuid
from dotenv import load_dotenv
import time


#Load the variables from the .env file into memory
load_dotenv()

# -- CONFIGURATION --
VOICE_NORMAL = "en-US-AnaNeural"
VOICE_ANGRY = "en-US-ChristopherNeural"
MODEL = "llama-3.1-8b-instant"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")


client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

connected_clients = set() # Track connected WebSocket clients
#active_user_tasks={}#Track active stream task per user session

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
        
        # After streaming is complete, we can read the full audio data from the buffer
        mp3_bytes.seek(0)#rewind to start
        raw_audio_binary = mp3_bytes.read() # Get the entire raw audio data as bytes
        
        # Send the raw audio binary data directly to the client for playback
        await current_websocket.send(raw_audio_binary)
        
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"Error in speak_text: {e}")


class RateLimiter:
    def __init__(self, calls_per_minute):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute # minimum time interval between calls in seconds
        self.last_call_time = 0.0
        self.lock = asyncio.Lock() # one task enters a time and a thread is allocated to it
        
        
    async def wait(self):
        async with self.lock:
            now = time.monotonic() # current time in seconds
            elapsed = now - self.last_call_time # time since last call
            wait_time = self.min_interval - elapsed # time to wait before next call
            #reserving a slot before releasing lock 
            self.last_call_time = time.monotonic() + max(wait_time, 0) # update last call time to now + wait time
         # Lock released HERE — sleep independently
        if wait_time > 0:
            await asyncio.sleep(wait_time)

groq_semaphore = asyncio.Semaphore(5)
groq_rate_limiter = RateLimiter(calls_per_minute=28)

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
async def chat(user_input,messages, websocket):
    try:
        async with groq_semaphore:           # max 5 concurrent
            await groq_rate_limiter.wait()   # space out calls
            
            messages.append({"role": "user", "content": user_input})
            
            response = await client.chat.completions.create(model=MODEL, messages=messages,temperature=0.9, max_tokens=90)
            reply = response.choices[0].message.content
            messages.append({"role": "assistant", "content": reply})
            return reply
        
    except asyncio.CancelledError:
        # User interrupted — remove the user message we just appended
        # so conversation history stays clean
        if messages and messages[-1]["role"] == "user":
            messages.pop()
        raise  # re-raise so task cancellation works properly
    
    except openai.APITimeoutError:
        print("!!! Groq API Timed Out !!!")
        # Return a fallback string matching your start-of-text tag setup
        return "[ANGER_LEVEL:0] Ugh, my brain stalled for a second. Try saying that again."
    
    except Exception as e:
        print(f"!!! OpenAI/Groq API Error: {e} !!!")
        return "[ANGER_LEVEL:0] Sorry, I encountered an unexpected error."
    
async def handle_response(user_text, messages, websocket, user_id):
    try:
        #2. Get AI response
        answer = await chat(user_text, messages, websocket)
                
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
                
        await speak_text(spoken_answer, is_angry, websocket)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[{user_id}] Error: {e}")


                
async def websocket_handler(websocket):
    
    user_id = str(uuid.uuid4())[:8] # Generate a short random user ID for tracking
    print(f"[CONNECTED] User {user_id} joined the session.")
    connected_clients.add(websocket)
    
    
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
                # Trigger new response  
                current_speech_task = asyncio.create_task(handle_response(user_text, messages, websocket, user_id))
                    
    except websockets.exceptions.ConnectionClosed:
        print("Browser disconnected")
    finally:
        connected_clients.discard(websocket)

async def main():
    port = int(os.environ.get("PORT", 8765))  # Railway sets PORT automatically
    # Start the WebSocket server on port 8765
    async with websockets.serve(websocket_handler, "0.0.0.0", port, max_size=10 * 1024 * 1024, ping_interval=20, ping_timeout=60):
        print("JelloBait Backend is online")
        print("Waiting for browser connection...")
        
        # This keeps the main function running forever
        await asyncio.Future()        
        
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nJelloBait is going offline. Goodbye!")
        
        
        
