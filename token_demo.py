import tiktoken

# Load a specific tokenizer
encoding = tiktoken.get_encoding("cl100k_base")

sentences = [
    "I love Python",
    "I love machine learning",
    "Generative AI is powerful!"
]

for sentence in sentences:
    token_ids = encoding.encode(sentence)

    print("\nText:", sentence)
    print("Token IDs:", token_ids)
    print("Token count:", len(token_ids))
    print("Decoded:", encoding.decode(token_ids))