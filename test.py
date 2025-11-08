import litellm


print(litellm.supports_function_calling(model="gpt-5"))
print(litellm.supports_function_calling(model="claude-sonnet-4-5-20250929"))
print(litellm.supports_function_calling(model="gemini/gemini-pro"))
