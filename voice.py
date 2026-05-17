import whisper
import pyttsx3

model = whisper.load_model("base")
engine = pyttsx3.init()


def transcribe(audio_path):
    result = model.transcribe(audio_path)
    return result["text"]


def speak(text):
    engine.say(text)
    engine.runAndWait()