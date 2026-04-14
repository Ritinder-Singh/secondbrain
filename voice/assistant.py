"""
Hands-free voice Q&A loop.
listen → transcribe → RAG → speak, repeating until Ctrl+C.
"""
from voice.mic import record_and_transcribe
from voice.tts import speak


def voice_query_loop() -> None:
    """
    Run the voice assistant in a loop.
    Each iteration: record question → transcribe → RAG → speak answer.
    Press Ctrl+C to exit.
    """
    from core.rag import ask
    from core.memory import create_conversation

    conversation_id = create_conversation("Voice session")
    print("\n🎙  Voice assistant ready. Press Ctrl+C to exit.\n")
    speak("Voice assistant ready. Ask me anything.")

    while True:
        try:
            query = record_and_transcribe()
            if not query:
                continue

            print(f"\n❓ {query}")
            result = ask(query, conversation_id=conversation_id, n_results=5)
            answer = result["answer"]

            print(f"\n🤖 {answer}\n")
            speak(answer)

        except KeyboardInterrupt:
            print("\n\nExiting voice assistant.")
            speak("Goodbye.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            speak("Sorry, something went wrong.")
