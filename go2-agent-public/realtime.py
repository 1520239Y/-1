import asyncio
import websockets
import pyaudio
import numpy as np
import base64
import json
import os
from dotenv import load_dotenv
import argparse
import threading
import time

# 環境変数の読み込み
load_dotenv()

# 定数
CHUNK = 2048
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000
WS_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

class AudioChat:
    def __init__(self, api_key, voice="echo"):
        self.api_key = api_key
        self.voice = voice
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.is_listening = False
        self.is_paused = False

    def print_welcome_message(self):
        print("===== リアルタイム音声チャットへようこそ! =====")
        print("使い方:")
        print("  - マイクに向かって話しかけてください")
        print("  - '!quit'と言うか、Ctrl+Cを押すと終了します")
        print("  - '!pause'と言うと一時停止、'!resume'で再開します")
        print("  - '!topic <トピック>'と言うと新しい会話トピックを設定できます")
        print("準備ができたら何か話しかけてください！")
        print("==============================================")

    def show_listening_indicator(self):
        while self.is_listening and not self.is_paused:
            print("🎤", end="", flush=True)
            time.sleep(0.5)
            print("\b ", end="", flush=True)
            time.sleep(0.5)

    async def send_audio(self, websocket):
        self.print_welcome_message()
        print("マイクの初期化中...")
        await asyncio.sleep(2)  # マイクの初期化を模倣
        print("準備完了！話しかけてください。")
        
        self.is_listening = True
        threading.Thread(target=self.show_listening_indicator, daemon=True).start()

        while True:
            if self.is_paused:
                await asyncio.sleep(0.1)
                continue

            try:
                audio_data = self.input_stream.read(CHUNK, exception_on_overflow=False)
                base64_audio = base64.b64encode(audio_data).decode("utf-8")
                audio_event = {
                    "type": "input_audio_buffer.append",
                    "audio": base64_audio
                }
                await websocket.send(json.dumps(audio_event))
                await asyncio.sleep(0)
            except Exception as e:
                print(f"音声送信エラー: {e}")
                await asyncio.sleep(1)

    async def receive_audio(self, websocket):
        print("アシスタント: 準備ができました。どのようなお手伝いができますか？")
        while True:
            try:
                response = await websocket.recv()
                response_data = json.loads(response)

                if response_data["type"] == "response.audio_transcript.delta":
                    transcript = response_data["delta"]
                    print(transcript, end="", flush=True)
                    
                    # コマンドの処理
                    if transcript.strip().lower() == "!quit":
                        print("\n終了します...")
                        return
                    elif transcript.strip().lower() == "!pause":
                        self.is_paused = True
                        print("\n一時停止しました。'!resume'で再開します。")
                    elif transcript.strip().lower() == "!resume":
                        self.is_paused = False
                        print("\n再開しました。")
                    elif transcript.strip().lower().startswith("!topic"):
                        new_topic = transcript.strip()[7:]
                        print(f"\n新しいトピックを設定しました: {new_topic}")
                        await self.set_new_topic(websocket, new_topic)

                elif response_data["type"] == "response.audio_transcript.done":
                    print("\nアシスタント: ", end="", flush=True)
                elif response_data["type"] == "response.audio.delta":
                    base64_audio_response = response_data["delta"]
                    if base64_audio_response:
                        pcm16_audio = base64.b64decode(base64_audio_response)
                        self.output_stream.write(pcm16_audio)
            except Exception as e:
                print(f"音声受信エラー: {e}")
                await asyncio.sleep(1)

    async def set_new_topic(self, websocket, topic):
        new_topic_request = {
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": f"新しいトピックについて話し合います: {topic}",
                "voice": self.voice
            }
        }
        await websocket.send(json.dumps(new_topic_request))

    async def chat_session(self):
        async with websockets.connect(WS_URL, extra_headers=self.headers) as websocket:
            print("WebSocketに接続しました。")

            init_request = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": "ユーザーをサポートしてください。",
                    "voice": self.voice
                }
            }
            await websocket.send(json.dumps(init_request))
            print("初期リクエストを送信しました。")

            self.input_stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
            self.output_stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)

            print("マイク入力とサーバーからの音声再生を開始します...")

            try:
                send_task = asyncio.create_task(self.send_audio(websocket))
                receive_task = asyncio.create_task(self.receive_audio(websocket))
                await asyncio.gather(send_task, receive_task)
            except KeyboardInterrupt:
                print("終了中...")
            finally:
                self.cleanup()

    def cleanup(self):
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        self.p.terminate()

def main():
    parser = argparse.ArgumentParser(description="OpenAI APIを使用したリアルタイム音声チャット")
    parser.add_argument("--voice", choices=["alloy", "echo", "shimmer"], default="echo", help="アシスタントの音声を選択")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("環境変数にOPENAI_API_KEYが設定されていません")

    chat = AudioChat(api_key, args.voice)
    asyncio.get_event_loop().run_until_complete(chat.chat_session())

if __name__ == "__main__":
    main()
