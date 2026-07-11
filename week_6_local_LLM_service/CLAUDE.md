# Witcher Cookbook

## Purpose
Private AI service generating cooking recipes inspired by The Witcher universe, using local LLM + custom RAG. Always follow `spec.md` and `plan.md`.

## Stack
- Backend: Kotlin, Ktor, Gradle, Kotlin Coroutines, kotlinx.serialization
- Frontend: React, TypeScript, Vite
- AI: Ollama, qwen3:4b, nomic-embed-text

## Architecture
Clean Architecture, clear separation of responsibilities. Suggested packages: controller, service, rag, llm, prompt, model, config, util.
Business logic must not depend on HTTP. Retrieval must not depend on Ollama. Prompt generation belongs exclusively to `PromptBuilder`.

## RAG Principles
Manual RAG pipeline: Markdown → Chunking → Embeddings → Local Index → Similarity Search → Prompt Builder → Ollama.
Embeddings generated offline; server only loads the generated index. Never rebuild embeddings at startup.

## Do Not Use
LangChain, LangChain4j, ChromaDB, FAISS, Qdrant, Pinecone, Spring Boot — unless explicitly requested.

## Kotlin Guidelines
Prefer: immutable data, data classes, constructor injection, suspend functions, structured concurrency, small focused classes.
Avoid: global mutable state, unnecessary abstractions, reflection, overengineering.

## Code Principles
Prioritize readability, simplicity, maintainability, explicit code. Optimize only after measuring. Keep functions/classes small. Choose descriptive names.

## Development Workflow
One task at a time; each task leaves project in working state. Avoid unrelated refactoring. Preserve existing architecture.
If multiple solutions exist: explain trade-offs, recommend one, wait for approval before significant architectural changes. When uncertain, ask instead of guessing.
