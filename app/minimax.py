import httpx

'''
sk-cp-JRo44GMFd_Rb6zUAo_BQ830LGAiXdQkHr5kbHQF_jJm__OAJSoPzexNrhWe65VivPmAfWiq9dXx1NlABFygyQ2EVOhaGtreqoz_B_7n7Vx-cuF5GZP9fPqU
'''

import anthropic

import os

#set up API key and client
os.environ["ANTHROPIC_BASE_URL"] = "https://api.minimax.io/anthropic"
os.environ["ANTHROPIC_API_KEY"] = "sk-cp-JRo44GMFd_Rb6zUAo_BQ830LGAiXdQkHr5kbHQF_jJm__OAJSoPzexNrhWe65VivPmAfWiq9dXx1NlABFygyQ2EVOhaGtreqoz_B_7n7Vx-cuF5GZP9fPqU"


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

