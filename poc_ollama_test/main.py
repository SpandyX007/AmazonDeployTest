import ollama
response = ollama.chat(model='qwen:1.8b', messages=[
  {
    'role': 'user',
    'content': 'Hi!',
  },
])
print(response['message']['content'])