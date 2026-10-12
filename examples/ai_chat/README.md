# AI chat example

A support chat that remembers each conversation (`@history`) and answers from your
documents (`@augmentation`).

```sh
uv add "patera[dev]" patera-database "patera-aiinterface[augmentation]"
cp .env.example .env                     # then put your OpenAI key in it

uv run patera cli assistant:setup        # creates the tables
uv run patera cli assistant:add-documents docs
uv run patera dev
```

```sh
# a new chat: the answer carries the session id
curl -s localhost:3000/api/chat/ -H "Content-Type: application/json" \
     -d '{"message": "How do I install Patera?"}'

# continue it (the follow-up is rewritten into a standalone question for the search)
curl -s localhost:3000/api/chat/ -H "Content-Type: application/json" \
     -d '{"session_id": "<id from above>", "message": "And how do I start it?"}'

# the same, streamed as NDJSON
curl -sN localhost:3000/api/chat/stream -H "Content-Type: application/json" \
     -d '{"message": "What does the admin dashboard show?"}'

# the stored conversation
curl -s localhost:3000/api/chat/<session id>
```

On first use the embedding model (`all-MiniLM-L6-v2`, about 90 MB) is downloaded into
`app/.ai_cache`. With PostgreSQL and the pgvector extension the document search runs as one
database query; set `PATERA_CHAT_DB__DATABASE_URI` and run `assistant:setup` again.
