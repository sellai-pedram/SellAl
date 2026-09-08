SellAI v12 Output Fix
=====================

Features:
- Persian/English product-copy generation from an uploaded image
- Server-side AI provider adapter using an OpenAI Responses API-compatible endpoint
- PBKDF2 password hashing (no plaintext passwords)
- 5 free generations
- Pro: 5 USDT / 30 days
- USDT on TRON/TRC20 payment verification using confirmed TronGrid transfer history
- Duplicate transaction protection
- PWA frontend

Setup:
1) Create a Python 3.11+ virtual environment.
2) pip install -r requirements.txt
3) Copy .env.example to .env and set:
   OPENAI_API_KEY (or another compatible provider key)
   OPENAI_BASE_URL (if not using api.openai.com)
   AI_MODEL
   TRONGRID_API_KEY
   SELLAI_ADMIN_KEY
4) Run:
   uvicorn server:app --host 0.0.0.0 --port 8000

Important:
- Never put an AI key, TRON private key, or seed phrase in the browser.
- The receiving wallet is public and is only used to receive USDT.
- For real production use, put the app behind HTTPS/reverse proxy, use a proper database backup strategy, rate limiting, logging, and secret management.
- Google Play billing/payment rules can apply if this is distributed through Google Play; keep the crypto checkout on the web unless your distribution/payment setup is compliant with the applicable policy.

AI:
The backend sends the uploaded image to POST /responses at OPENAI_BASE_URL.
The model is asked to return JSON keys:
title, description, instagram, hashtags.
If OPENAI_API_KEY is empty, the app intentionally uses a demo response.


V11 fix: browser compresses product images to JPEG before upload and shows clearer network/server errors.
