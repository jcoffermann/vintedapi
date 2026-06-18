# VintIQ Microservice

FastAPI wrapper around [`vinted-api-wrapper`](https://github.com/Pawikoski/vinted-api-wrapper).
Deploy this separately (Render / Railway / Fly.io). The Lovable app calls it
via HTTPS using a Bearer token.

## Endpoints

All endpoints (except `/health`) require header:
`Authorization: Bearer <API_TOKEN>`

- `GET /health`
- `GET /search?query=...&brand_ids=...&price_from=...&price_to=...&domain=de`
- `GET /item/{item_id}?domain=de`
- `GET /user/{user_id}?domain=de`

## Env vars

| Name | Required | Purpose |
|------|----------|---------|
| `API_TOKEN` | **yes** | Bearer token for auth |
| `DEFAULT_DOMAIN` | no (default `de`) | Vinted country domain |
| `PROXY_URL` | no | e.g. `http://user:pass@host:port` |
| `CACHE_TTL_SECONDS` | no (default `60`) | In-memory cache TTL |
| `PORT` | auto on Render | HTTP port |

## Deploy on Render

1. Push the `microservice/` folder to a GitHub repo (either standalone or as
   the same repo with **Root Directory** set to `microservice` in Render).
2. Render → **New → Web Service** → connect the repo.
3. Settings:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variables:** `API_TOKEN=<generate a long random string>`
     (optional: `PROXY_URL`, `DEFAULT_DOMAIN`)
4. After deploy, test:
   ```
   curl https://<your-service>.onrender.com/health
   curl -H "Authorization: Bearer <API_TOKEN>" \
        "https://<your-service>.onrender.com/search?query=nike&domain=de"
   ```
5. Copy the URL + token — you'll paste them into Lovable as the secrets
   `VINTED_API_URL` and `VINTED_API_TOKEN` in Phase 1.

## Local dev

```
pip install -r requirements.txt
API_TOKEN=dev uvicorn main:app --reload --port 8000
```

## Notes

- Free Render plans sleep after idle — first request may take 30s. Upgrade to
  Starter ($7/mo) for always-on if you want the Sniper cron to be reliable.
- `vinted-api-wrapper` is unofficial. Keep poll intervals conservative and
  configure `PROXY_URL` if you hit rate limits.
