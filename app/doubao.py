import os
from volcenginesdkarkruntime import Ark

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

api_key = os.environ.get("ARK_API_KEY")
if not api_key:
    raise RuntimeError(
        "Missing ARK_API_KEY. Set it in your shell (export ARK_API_KEY=...) or in a .env and load it."
    )

client = Ark(api_key=api_key)


list_of_models = ["doubao-seed-2-0-pro-260215", "doubao-seed-1-8-251228", "deepseek-v3-2-251201"]
main_model = "doubao-seed-1-8-251228"
list_of_thinking_models = ["doubao-seed-2-0-pro-260215", "deepseek-v3-2-251201"]
list_of_image_models = ["doubao-seed-2-0-pro-260215", "doubao-seed-1-8-251228"]

completion = client.chat.completions.create(
    model=main_model,
    messages=[
        {"role": "user", "content": "Say hello in one sentence."}
    ]
)
print(completion.choices[0].message) # type: ignore