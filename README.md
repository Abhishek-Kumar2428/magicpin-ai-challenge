# magicpin AI Challenge — Vera Bot

A deterministic, context-grounded Python bot built for the magicpin AI Challenge.

## Overview

The bot receives category, merchant, customer, and trigger contexts from the judge and uses them to initiate and manage relevant conversations.

It exposes the required HTTP API endpoints:

- `POST /v1/context`
- `POST /v1/tick`
- `POST /v1/reply`
- `GET /v1/healthz`
- `GET /v1/metadata`

## Features

- Stateful context handling
- Version-aware context updates
- Context-grounded message composition
- Merchant and customer conversation handling
- Trigger-based proactive outreach
- Suppression handling
- Opt-out handling
- Commitment and confirmation flows
- Deterministic rule-based responses
- HTTP JSON API

## Project Structure

```text
magicpin-ai-challenge/
├── bot.py
├── server.py
├── requirements.txt
├── dataset/
│   ├── categories/
│   ├── customers_seed.json
│   ├── merchants_seed.json
│   └── triggers_seed.json
├── challenge-brief.md
└── challenge-testing-brief.md
