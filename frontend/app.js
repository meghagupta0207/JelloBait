import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
import { GUI } from 'three/addons/libs/lil-gui.module.min.js';


//intialize web audio context to play on user machine
const audioContext = new(window.AudioContext || window.webkitAudioContext)();

// Create analyser once — reuse it for every utterance
const analyser = audioContext.createAnalyser();
analyser.fftSize = 256;
analyser.smoothingTimeConstant = 0.6;
analyser.connect(audioContext.destination);

const freqData = new Uint8Array(analyser.frequencyBinCount);


let mouthVolume = 0;
const angerScoreDiv = document.getElementById('anger-score');


// Call this every animation frame to pull live volume
function updateMouthFromAnalyser() {
    analyser.getByteFrequencyData(freqData);
    // Average the lower frequencies (where speech energy lives)
    const speechBins = freqData.slice(0, 16);
    const avg = speechBins.reduce((a, b) => a + b, 0) / speechBins.length;
    mouthVolume = avg / 255.0; // Normalize to 0.0–1.0
}

//Connecting to Websocket server
let socket;
const backendUrl =  'wss://jellobait-production-bb12.up.railway.app/';


function connectToBackend() {
    
    socket = new WebSocket(backendUrl);

    // Configure channel parameters to receive incoming binary streams as ArrayBuffers
    socket.binaryType = "arraybuffer";

    socket.onopen = () => {
        console.log("Connected to JelloBait voice engine successfully!");
    };

let audioStartTime = null;
//Handling data from server
socket.onmessage = async (event) => {

    if(event.data instanceof ArrayBuffer) {
        try {
            //decoding raw mp3 into audio
            const audioBuffer = await audioContext.decodeAudioData(event.data);//decode
            const source = audioContext.createBufferSource();//creates the audio player
            source.buffer = audioBuffer;//loads the audio in to player
            source.connect(analyser);//plugs the audio into speakers
            source.start(0);//play button
            
            source.onended = () => {
            mouthVolume = 0;
        };

        } catch(err){
            console.error("Audio Playback Error:", err);
        }
        return; 
    }

    const data = JSON.parse(event.data);

    if(data.type=="text"){
        addMessageToChat(data.text, 'bot');// Add the bot's response to the chat interface

        //Checking Trigger
        if (data.trigger === "go_red") {
            changeJellyColor(0x8A0303);
                changeEyeShape(true);
        }
        else if (data.trigger === "default") {
            changeJellyColor(0x08F7EC);
                changeEyeShape(false);
        }
    }

    if (data.type === "play_thunder") {
            const thunderAudio = new Audio("universfield-loud-thunder-192165.mp3");
            thunderAudio.volume = 0.8;
            thunderAudio.play().catch(e => {
                console.warn("Audio resource blocked by safety parameters: ", e);
            });
        }
    
    if (data.anger_score !== undefined && data.anger_score !== null) {
        if (angerScoreDiv) {
            angerScoreDiv.textContent = `Anger Score: ${data.anger_score}`;
        }
    }
};
// Defensive reconnect circuit loop
    socket.onclose = () => {
        console.warn("Connection dropped. Attempting automated reconnection in 3 seconds...");
        setTimeout(connectToBackend, 3000);
    };

    socket.onerror = (err) => {
        console.error("Socket layout fault encountered: ", err);
        socket.close();
    };
}

// Start connection logic when the window is ready
window.addEventListener('DOMContentLoaded', connectToBackend);

// function to change color
function changeJellyColor(colorHex) {
    if (model) {
        model.traverse((child) => {
            if (child.isMesh && child.name === "Sphere") { // Use the name of your body mesh
                child.material.color.set(colorHex);
                
                // If it's angry red, maybe make it glow?
                if (colorHex === 0xff0000) {
                    child.material.emissive = new THREE.Color(0x330000);
                } else {
                    child.material.emissive = new THREE.Color(0x000000);
                }
            }
        });
    }
    
}

//Change eyes when angry
function changeEyeShape(isAngry) {
    renderer.localClippingEnabled = true;

    if (!model) return;

    const leftEyePlane  = new THREE.Plane(new THREE.Vector3(1, -2, 0).normalize(), isAngry ? 0.3 : 99);
    const rightEyePlane = new THREE.Plane(new THREE.Vector3(-1, -2, 0).normalize(), isAngry ? 0.3 : 99);

    model.traverse((child) => {
        if (child.name === "Sphere003") {
            child.material.clippingPlanes = isAngry ? [leftEyePlane] : [];
            child.material.needsUpdate = true;
        }
        if (child.name === "Sphere004") {
            child.material.clippingPlanes = isAngry ? [rightEyePlane] : [];
            child.material.needsUpdate = true;
        }
    });
}


//Sending Message
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');

sendBtn.addEventListener('click', sendMessage);//Event listener for send button

//trigger to send message when send button clicked or when enter key is pressed
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

//Function to send message to the WebSocket server and add it to the chat interface
function sendMessage() {
    if (audioContext.state === 'suspended') {
        audioContext.resume();
    }
    const text = userInput.value.trim();
    if(text!=="" && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({"text": text}));// Send the message as a JSON string to the WebSocket server
        addMessageToChat(text, 'user');// Add the user's message to the chat interface
        userInput.value = '';// Clear the input field after sending the message
    }
}

//Function to add a message to the chat interface
function addMessageToChat(text, sender) {
    // 1. Create a new div element for the message
    const msgDiv = document.createElement('div');
    
    // 2. Add the 'message' class and the sender class ('user' or 'bot')
    msgDiv.classList.add('message', sender);
    
    // 3. Set the text inside the bubble
    msgDiv.textContent = text;
    
    // 4. Put the bubble inside the chat-messages container
    chatMessages.appendChild(msgDiv);
    
    // 5. Scroll to the bottom so the newest message is always visible
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

//Window resize Function
const container = document.getElementById('canvas-container');

function onWindowResize() {
    const container = document.getElementById('canvas-container');
    const width = container.clientWidth;
    const height = container.clientHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
}

//Creating the scene, camera and renderer
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(80, window.innerWidth / window.innerHeight, 0.1, 6000);
camera.position.set(0, 0, -5);
const renderer = new THREE.WebGLRenderer();
container.appendChild(renderer.domElement);//injecting the canvas into the container div
onWindowResize();


//HDRI LOADER
const rgbeLoader = new RGBELoader();
rgbeLoader.load('citrus_orchard_road_puresky_4k.hdr',function(texture) {

        texture.mapping =THREE.EquirectangularReflectionMapping;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 0.9; // Brightness control
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        
        scene.environment = texture;

        scene.background = texture;

    }

);

//Lighting
const light = new THREE.DirectionalLight(0xffffff, 1);
light.position.set(5, 90, 5);
scene.add(light);

//Setting Tools for Animation
let model;
let mixer;

const clock = new THREE.Clock();

//Loading the 3D model
const loader = new GLTFLoader();

loader.load('final_jelly_red.glb' , function(gltf)
{
    model = gltf.scene;
    scene.add(model);
    mixer = new THREE.AnimationMixer(model); //mixer used for playing animations for 3d model
    
// Traverse the model to find all meshes and log them
    model.traverse((child) => {
        if(child.isMesh){
            console.log(child.name);
        }
    });

})//end of loader function

//Camera controls
const controls = new OrbitControls(camera, renderer.domElement);
controls.update();


//Animation Loop
function animate() { // Animate function Starts here

    const delta = clock.getDelta();//accounts for real time between frames
    const time = clock.getElapsedTime();
    updateMouthFromAnalyser(); // Update mouth volume from the analyser data

    
    if(model){

        //Black part of eyes blinking
        model.traverse((child) => {
            if(child.name == "Sphere002" ) {
                const blink = Math.sin(time * 3) > 0.95 ? 0.05 : 1;
                child.scale.y = blink * 0.5;
                
            }
        })//model traverse function(black part of the eyes)

        
        //White part of eyes blinking
        model.traverse((child) => {
            if(child.name == "Sphere003" || child.name == "Sphere004" ) {
                const blink =Math.sin(time * 3) > 0.95 ? 0.05 : 1;
                child.scale.y = blink * 0.33;
            } 
        })//model traverse function(white part of the eyes)


        //Mouth Animation
        model.traverse((child) => {
            if(child.name == "Sphere005" ) {
                const boostedVolume = Math.pow(mouthVolume * 2, 2.5); // Tune these
                const targetScaleY =  1 + boostedVolume * 0.1;
                child.scale.y = THREE.MathUtils.lerp(child.scale.y, targetScaleY, 0.3);

            }
        })//model traverse function(mouth)

    }// End of if statement for model

    if(model){
        mixer.update(delta);// Update the animation mixer with the time delta
    }

    controls.update();// Update camera controls
    renderer.render(scene, camera);//Render the scene from the perspective of the camera
}// End of animate function

window.addEventListener('resize', onWindowResize);//Event listener for window resize
renderer.setAnimationLoop(animate);// Start the animation loop
