"""
MediCheck Backend — OpenGradient SDK v0.9.9+
Private key stays server-side only. Frontend has zero access to it.

Install:
    pip install opengradient flask flask-cors python-dotenv

Run:
    python backend.py
"""

import asyncio
import json
import os
import nest_asyncio
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env

import opengradient as og
from flask import Flask, Response, stream_with_context, jsonify, request
from flask_cors import CORS

# Allow nested event loops (needed for sync streaming in Flask)
nest_asyncio.apply()

# ─── Config ────────────────────────────────────────────────────────────────
PRIVATE_KEY = os.environ.get("OG_PRIVATE_KEY")  # Use .get() to prevent boot crash

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
print("Initializing OpenGradient SDK v0.9.9...")
llm = None
if PRIVATE_KEY:
    try:
        llm = og.LLM(private_key=PRIVATE_KEY)
        print("SDK Initialized successfully.")
    except Exception as e:
        print(f"Error loading SDK: {e}")
else:
    print("WARNING: OG_PRIVATE_KEY not set. Assessment endpoint will fail.")

# ─── Flask App ──────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)


@app.route("/")
def index():
    """Serve the frontend."""
    return app.send_static_file("frontend.html")


@app.route("/api/assess", methods=["POST"])
def assess():
    if not llm:
        return jsonify({"error": "OG_PRIVATE_KEY is missing. Set it in .env or Vercel Environment Variables."}), 500

    data = request.get_json()
    if not data or not data.get("symptoms"):
        return jsonify({"error": "Missing symptoms field"}), 400

    symptoms = data.get("symptoms", "")
    age      = data.get("age", "Not specified")
    duration = data.get("duration", "Not specified")
    history  = data.get("history", "")

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

    def generate():
        """Stream SSE chunks — compatible with SDK v0.9.9 StreamChunk API."""
        async def run():
            try:
                # SDK v0.9.9: stream=True returns AsyncGenerator[StreamChunk, None]
                stream = await llm.chat(
                    model=MODEL,
                    messages=messages,
                    max_tokens=1000,
                    temperature=0.1,
                    x402_settlement_mode=og.x402SettlementMode.INDIVIDUAL_FULL,
                    stream=True,
                )

                final_chunk = None
                async for chunk in stream:
                    # Each chunk has chunk.choices[0].delta.content
                    if chunk.choices:
                        content = chunk.choices[0].delta.content
                        if content:
                            yield json.dumps({"text": content}) + "\n\n"

                    # Final chunk carries TEE metadata
                    if chunk.is_final:
                        final_chunk = chunk

                # Send done event with TEE metadata if available
                done_meta = {
                    "done": True,
                    "settlement": "INDIVIDUAL_FULL",
                    "model": str(MODEL),
                }
                if final_chunk:
                    if final_chunk.tee_id:
                        done_meta["tee_id"] = final_chunk.tee_id
                    if final_chunk.tee_timestamp:
                        done_meta["tee_timestamp"] = final_chunk.tee_timestamp
                    if final_chunk.tee_signature:
                        done_meta["tee_signature"] = final_chunk.tee_signature[:40] + "..."

                yield json.dumps(done_meta) + "\n\n"

            except Exception as e:
                yield json.dumps({"text": f"\n\n[Backend Error]: {str(e)}"}) + "\n\n"

        async def collect():
            results = []
            async for item in run():
                results.append(item)
            return results

        loop = asyncio.new_event_loop()
        try:
            items = loop.run_until_complete(collect())
            for item in items:
                yield f"data: {item}"
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
        "sdk_version": "0.9.9",
        "model": str(MODEL),
        "settlement": "INDIVIDUAL_FULL",
        "network": "Base Sepolia",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
