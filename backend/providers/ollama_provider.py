import ollama
response = ollama.chat(
    model='vaultbox/qwen3.5-uncensored:4b', 
    messages=[
      {
        'role': 'user',
        'content': 'Why is the sky blue?',
      },
  ],
  think=False,)
print(response['message']['content'])