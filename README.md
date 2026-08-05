## Professor Oak AI: Pokémon Battle & Lore Assistant
### Problem Statement

When playing Pokémon or researching the games, getting accurate information is surprisingly tricky because the data is split into two completely different types:

* **Strict Numeric Stats**: Things like type effectiveness, base stats, and move sets where precision is key.

* **Open-ended Lore**: Background stories, legendary myths, and Pokédex descriptions spread across different game versions.

General-purpose LLMs usually struggle here. They frequently hallucinate stats, mix up mechanics between different game generations, or confuse move pools. On the flip side, manually digging through wikis and spreadsheets to prepare a single battle strategy takes too much time.

#### Project Goal & Solution

Professor Oak AI is a domain-specific RAG (Retrieval-Augmented Generation) assistant designed to act as an expert guide for Pokémon trainers.

Instead of relying solely on the LLM's pre-trained memory, this system grounds its answers in a curated dataset combining structured game mechanics and Pokédex entries.

#### Key Features

* **Battle & Tactical Advice**: Offers accurate team-building suggestions and type match-up strategies using verified stat data.

* **Lore Search**: Answers questions about Pokémon origins, legendaries, and regional lore straight from canonical descriptions.

* **Hybrid Retrieval**: Uses keyword search (for exact names and stats) alongside vector embeddings (for semantic lore queries) to keep answers accurate and hallucination-free.
