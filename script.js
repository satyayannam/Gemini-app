const recordButton = document.getElementById('record');
const stopButton = document.getElementById('stop');
const timerDisplay = document.getElementById('timer');

let mediaRecorder;
let audioChunks = [];
let isUploading = false;
let recordingTimer;
let recordingSeconds = 0;

// Function to update the timer display
function updateTimer() {
    const minutes = Math.floor(recordingSeconds / 60);
    const seconds = recordingSeconds % 60;
    timerDisplay.textContent = `Recording: ${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
    recordingSeconds++;
}

recordButton.addEventListener('click', async () => {
    if (isUploading) return;
    
    // Reset recording state
    audioChunks = [];
    recordingSeconds = 0;
    timerDisplay.textContent = "Starting...";
    
    try {
        // Request microphone access
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        
        // Start recording
        mediaRecorder.start();
        timerDisplay.textContent = "Recording: 0:00";
        recordingTimer = setInterval(updateTimer, 1000);
        
        // Show stop button, hide record button
        recordButton.style.display = 'none';
        stopButton.style.display = 'inline-block';

        // Handle data as it becomes available
        mediaRecorder.ondataavailable = e => {
            audioChunks.push(e.data);
        };

        // Handle recording stop
        mediaRecorder.onstop = async () => {
            // Clean up recording UI
            clearInterval(recordingTimer);
            recordButton.style.display = 'inline-block';
            stopButton.style.display = 'none';
            
            timerDisplay.textContent = "Processing audio...";
            isUploading = true;

            // Create audio blob and prepare for upload
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('audio_data', audioBlob, 'recorded_audio.webm');

            try {
                // Send to server
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'Cache-Control': 'no-cache'
                    }
                });

                if (response.ok) {
                    timerDisplay.textContent = "Upload successful! Processing on server...";
                    
                    setTimeout(() => {
                        timerDisplay.textContent = "Processing complete. Refreshing...";
                        location.href = location.href.split('?')[0] + '?nocache=' + new Date().getTime();
                    }, 10000); // Extended delay for processing - 10 seconds
                } else {
                    const errorText = await response.text();
                    console.error("Upload failed:", errorText);
                    timerDisplay.textContent = "Upload failed! Check console for details.";
                }
            } catch (error) {
                console.error("Error uploading:", error);
                timerDisplay.textContent = "Error uploading. Check your connection.";
            } finally {
                isUploading = false;
            }
        };

        // Set up stop button handler
        stopButton.onclick = () => {
            if (mediaRecorder && mediaRecorder.state === "recording") {
                mediaRecorder.stop();
                // Stop all tracks to release the microphone
                stream.getTracks().forEach(track => track.stop());
            }
        };

    } catch (error) {
        console.error("Error accessing microphone:", error);
        timerDisplay.textContent = "Microphone access denied!";
        isUploading = false;
        recordButton.style.display = 'inline-block';
        stopButton.style.display = 'none';
    }
});

// Initial UI setup
stopButton.style.display = 'none';
