from datetime import datetime
from flask import Flask, render_template, request, send_from_directory, redirect
import os
import fitz  # PyMuPDF
import uuid
from google.cloud import storage, texttospeech
from vertexai.preview.generative_models import GenerativeModel, Part
import vertexai

# Flask setup
app = Flask(__name__, template_folder="templates")

UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Homepage
@app.route('/')
def home():
    results = []
    for filename in sorted(os.listdir(RESULTS_FOLDER), reverse=True):
        if filename.endswith('.txt'):
            base_name = filename.replace('.txt', '')
            with open(os.path.join(RESULTS_FOLDER, filename), 'r', encoding='utf-8') as f:
                content = f.read()
                audio_file = f"{base_name}.mp3"
                results.append((filename, content, audio_file))
    return render_template('index.html', results=results)

# Serve script.js
@app.route('/script.js')
def serve_script():
    return send_from_directory('.', 'script.js')

@app.route('/favicon.ico')
def favicon():
    return '', 204

# Upload audio to GCS
def upload_to_gcs(local_file_path, bucket_name):
    storage_client = storage.Client()
    blob_name = f"audio_inputs/{uuid.uuid4().hex}.webm"
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_file_path)
    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    print("Uploaded to GCS:", gcs_uri)
    return gcs_uri

# Analyze audio + book with Gemini, return text
def analyze_question(file_path):
    bucket_name = "gemini-audio-bucket-1"
    gcs_uri = upload_to_gcs(file_path, bucket_name)

    book_path = os.path.join(UPLOAD_FOLDER, 'book_text.txt')
    if not os.path.exists(book_path):
        return "Please upload a book first."

    with open(book_path, 'r', encoding='utf-8') as f:
        book_text = f.read()[:10000]

    prompt = f"""
    You are a helpful assistant answering questions about a book.
    The user has asked a question based on the following book excerpt:
    ```{book_text}```
    Transcribe their audio question and answer based only on the book.
    """

    vertexai.init(project="gemini-audio-app", location="us-central1")
    model = GenerativeModel("gemini-1.5-pro")

    print("Sending request to Gemini...")
    response = model.generate_content([
        prompt,
        Part.from_uri(gcs_uri, mime_type="audio/webm")
    ])
    print("Gemini response received.")
    return response.text

# Synthesize text to MP3 using TTS
def synthesize_to_mp3(text, output_path):
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    with open(output_path, "wb") as out:
        out.write(response.audio_content)
    print(f"TTS MP3 saved to: {output_path}")

# Upload audio question
@app.route('/upload', methods=['POST'])
def upload_audio():
    try:
        if 'audio_data' not in request.files:
            return "No file part", 400

        file = request.files['audio_data']
        if file.filename == '':
            return "No selected file", 400

        filename = datetime.now().strftime("%Y%m%d-%H%M%S")
        audio_path = os.path.join(UPLOAD_FOLDER, filename + '.webm')
        file.save(audio_path)
        print(f"Audio saved to: {audio_path}")

        response_text = analyze_question(audio_path)

        text_path = os.path.join(RESULTS_FOLDER, filename + '.txt')
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(response_text)

        # Generate TTS
        mp3_path = os.path.join(RESULTS_FOLDER, filename + '.mp3')
        synthesize_to_mp3(response_text, mp3_path)

        return redirect('/')

    except Exception as e:
        print("UPLOAD FAILED:", e)
        return f"Error processing audio: {str(e)}", 500

# Upload book
@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'book' not in request.files:
        return "No book file uploaded", 400

    pdf = request.files['book']
    if pdf.filename == '':
        return "No selected file", 400

    book_path = os.path.join(UPLOAD_FOLDER, 'book.pdf')
    pdf.save(book_path)
    print(f"PDF uploaded: {book_path}")

    try:
        doc = fitz.open(book_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()

        with open(os.path.join(UPLOAD_FOLDER, 'book_text.txt'), 'w', encoding='utf-8') as f:
            f.write(full_text)

        print("Book text extracted.")
        return redirect('/')

    except Exception as e:
        print("Error parsing PDF:", e)
        return f"Error reading book: {str(e)}", 500

# Serve results and audio
@app.route('/results/<filename>')
def get_result(filename):
    return send_from_directory(RESULTS_FOLDER, filename)

# Run app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
