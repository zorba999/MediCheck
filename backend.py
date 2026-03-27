"""
MediCheck Backend — OpenGradient SDK
Private key stays server-side only. Frontend has zero access to it.

Install:
    pip install opengradient flask flask-cors python-dotenv

Run:
    python backend.py
"""

import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv()  # Charge les variables depuis .env
import opengradient as og
from flask import Flask, Response, stream_with_context, jsonify
from flask_cors import CORS

# ─── Config ────────────────────────────────────────────────────────────────
PRIVATE_KEY = os.environ.get("OG_PRIVATE_KEY")  # Use .get() to prevent boot crash on Vercel

MODEL = og.TEE_LLM.CLAUDE_SONNET_4_6

SYSTEM_PROMPT = """You are a compassionate and knowledgeable medical assistant providing preliminary health guidance.
You MUST:
1. Acknowledge and list the reported symptoms clearly
2. Provide 2-3 possible causes (differential diagnosis), from most to least likely
3. Give concrete, actionable recommendations (rest, hydration, OTC medications if appropriate)
4. Clearly indicate whether the patient should seek immediate medical attention (URGENT), see a doctor soon (SOON), or can manage at home (HOME CARE)
5. Add a brief disclaimer about professional medical consultation

Format with clear sections using plain text and line breaks (no markdown).
Important: if symptoms suggest a life-threatening emergency (chest pain + shortness of breath, stroke symptoms, severe allergic reaction), START your response with "EMERGENCY:" on its own line."""

# ─── Init SDK ───────────────────────────────────────────────────────────────
print("Initializing OpenGradient SDK...")
llm = None
if PRIVATE_KEY:
    try:
        llm = og.LLM(private_key=PRIVATE_KEY)
        print("SDK Initialized successfully.")
        # Note for Vercel: We remove the `ensure_opg_approval` blocking call from here 
        # so it doesn't cause a lambda timeout on Vercel during cold boot!
    except Exception as e:
        print(f"Error loading SDK: {e}")

# ─── Flask App ──────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)  # Allow frontend (HTML file) to call this backend


@app.route("/")
def index():
    """Serve the frontend."""
    return app.send_static_file("frontend.html")


@app.route("/api/assess", methods=["POST"])
def assess():
    try:
        if not llm:
            return jsonify({"error": "PRIVATE_KEY is missing or invalid on Vercel environment!"}), 500

        from flask import request
        data = request.get_json()
        if not data or not data.get("symptoms"):
            return jsonify({"error": "Missing symptoms field"}), 400

        symptoms = data.get("symptoms", "")
        age = data.get("age", "Not specified")
        duration = data.get("duration", "Not specified")
        history = data.get("history", "")

        user_message = f"""Patient information:
- Age range: {age}
- Duration of symptoms: {duration}
- Symptoms: {symptoms}
{f'- Medical history: {history}' if history else ''}

Please provide a preliminary health assessment and guidance."""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ]
    except Exception as e:
        import traceback
        return str(traceback.format_exc()), 500

    def generate():
        """Stream SSE chunks to the client."""
        loop = asyncio.new_event_loop()

        async def run_stream():
            stream = await llm.chat(
                model=MODEL,
                messages=messages,
                max_tokens=800,
                temperature=0.1,
                x402_settlement_mode=og.x402SettlementMode.INDIVIDUAL_FULL,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        try:
            async def stream_to_sync():
                full_text = ""
                try:
                    async for text_chunk in run_stream():
                        full_text += text_chunk
                        payload = json.dumps({"text": text_chunk})
                        yield f"data: {payload}\n\n"

                    done_payload = json.dumps({
                        "done": True,
                        "settlement": "INDIVIDUAL_FULL",
                        "model": str(MODEL),
                    })
                    yield f"data: {done_payload}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'text': f'\\n\\n[Backend Error]: {str(e)}'})}\n\n"

            gen = stream_to_sync()
            while True:
                try:
                    chunk = loop.run_until_complete(gen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/status", methods=["GET"])
def status():
    """Health check — frontend calls this to confirm backend is up."""
    return jsonify({
        "status": "ok",
        "model": str(MODEL),
        "settlement": "INDIVIDUAL_FULL",
        "network": "Base Sepolia",
    })


if __name__ == "__main__":
    # Development server — use gunicorn for production
    app.run(host="0.0.0.0", port=5000, debug=True)
