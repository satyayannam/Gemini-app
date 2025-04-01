from datetime import datetime
from flask import Flask, render_template, request, send_from_directory, redirect
import os
import uuid
from google.cloud import aiplatform_v1beta1
from google.cloud import storage

# Flask setup
app = Flask(__name__, template_folder="templates")

UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Route: Homepage
@app.route('/')
def home():
    results = []
    for filename in sorted(os.listdir(RESULTS_FOLDER), reverse=True):
        if filename.endswith('.txt'):
            with open(os.path.join(RESULTS_FOLDER, filename), 'r') as f:
                content = f.read()
                results.append((filename, content))
    return render_template('index.html', results=results)

# Route: Serve script.js from root
@app.route('/script.js')
def serve_script():
    return send_from_directory('.', 'script.js')

# Prevent favicon error
@app.route('/favicon.ico')
def favicon():
    return '', 204

# Upload to Google Cloud Storage
def upload_to_gcs(local_file_path, bucket_name):
    storage_client = storage.Client()
    blob_name = f"audio_inputs/{uuid.uuid4().hex}.wav"
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_file_path)
    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    print("Uploaded to GCS:", gcs_uri)
    return gcs_uri

# Analyze audio with Gemini
def analyze_audio(file_path):
    bucket_name = "gemini-audio-bucket-1"
    gcs_uri = upload_to_gcs(file_path, bucket_name)

    client = aiplatform_v1beta1.PredictionServiceClient()
    endpoint = "projects/gemini-audio-app/locations/us-central1/publishers/google/models/gemini-2.0-flash-001"

    content = [
        {
            "role": "user",
            "parts": [
                {"text": "Transcribe this audio and analyze its sentiment."},
                {"file_data": {
                    "mime_type": "audio/wav",
                    "file_uri": gcs_uri
                }}
            ]
        }
    ]

    request = aiplatform_v1beta1.GenerateContentRequest(
        model=endpoint,
        contents=content
    )

    print("Sending request to Gemini...")
    response = client.generate_content(request=request)
    print("Gemini response received.")
    return response.candidates[0].content.parts[0].text

# Handle audio upload
@app.route('/upload', methods=['POST'])
def upload_audio():
    try:
        if 'audio_data' not in request.files:
            return "No file part", 400

        file = request.files['audio_data']
        if file.filename == '':
            return "No selected file", 400

        filename = datetime.now().strftime("%Y%m%d-%H%M%S") + '.wav'
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        print(f"Audio saved to: {file_path}")
        result_text = analyze_audio(file_path)

        result_filename = filename.replace('.wav', '.txt')
        result_path = os.path.join(RESULTS_FOLDER, result_filename)
        with open(result_path, 'w') as f:
            f.write(result_text)

        print(f"Result saved to: {result_path}")
        return redirect('/')

    except Exception as e:
        print("UPLOAD FAILED:", e)
        return f"Error processing audio: {str(e)}", 500

# Serve sentiment analysis results
@app.route('/results/<filename>')
def get_result(filename):
    return send_from_directory(RESULTS_FOLDER, filename)

# Run Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

