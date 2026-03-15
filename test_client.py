from openai import OpenAI
import os

def test_proxy_request():
    """
    Simulate a client request to the LiteLLM proxy.
    """
    client = OpenAI(
        api_key="sk-1234",
        base_url="http://localhost:4000"
    )

    try:
        print("Sending request to proxy...")
        response = client.chat.completions.create(
            model="qwen3.5",
            messages=[
                {"role": "user", "content": "What is the latest Malaysia politics and business news in 2024?"}
            ]
        )
        print("Response received:")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error during request: {e}")

if __name__ == "__main__":
    test_proxy_request()
