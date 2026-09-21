# OpenLivery + xAI Grok

This fork of [sarrazola/openlivery](https://github.com/sarrazola/openlivery) sends every agent call to **xAI** instead of OpenRouter.

## What changed

| Piece | Upstream | This fork |
| --- | --- | --- |
| Base URL | `https://openrouter.ai/api/v1` | `https://api.x.ai/v1` |
| Settings label | OpenRouter | xAI Grok |
| Key console | openrouter.ai/settings/keys | [console.x.ai](https://console.x.ai/) |
| Default chat model | `openai/gpt-5.6-luna` | `grok-4.6` |
| Catalog | OpenRouter `/models` + `/embeddings/models` | xAI `/models` (embeddings optional) |
| Key check | `GET /key` | `GET /key`, then `GET /models` if 404 |

The internal provider id is still `openrouter` so existing API routes (`PUT /api/providers/openrouter`), migrations and tests keep working. Credentials stored under `xai` are accepted as an alias.

## How to use

1. Create an API key at https://console.x.ai/
2. `make up` as in the README
3. Settings → paste the xAI key (`xai-…`)
4. Create an agent and pick a Grok model

Chat, tools and vision go through `POST /v1/chat/completions` on xAI.

## Knowledge base

xAI does not expose a public embeddings catalog. PDF retrieval falls back to **keyword search** unless you point the registry at a host that speaks `/embeddings`.

## Audio

Inbound audio still uses the OpenAI-shaped `/audio/transcriptions` path. If your xAI account does not serve that route, turn audio off on the agent.
