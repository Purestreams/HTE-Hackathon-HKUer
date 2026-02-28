import httpx

'''
sk-api-pX-J83ZFK4sVH33L7yB5JCsSD8KA2TXylwAFVagln-54frDjdUxIzOTLe7ZcyADOn-UtRcc4ZuYMRFO-0j7ZcN_gLCqlkX0fkeZ4bFvF8Vzeyeae96WBZ_A
'''

import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model="MiniMax-M2.5",
    max_tokens=1000,
    system="You are a helpful assistant.",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Hi, how are you?"
                }
            ]
        }
    ]
)

for block in message.content:
    if block.type == "thinking":
        print(f"Thinking:\n{block.thinking}\n")
    elif block.type == "text":
        print(f"Text:\n{block.text}\n")

