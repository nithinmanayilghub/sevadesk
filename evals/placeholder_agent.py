# A stand-in for the real AI Agent (Epic 6 replaces it). It always gives the same reply.

# Every result names the prompt version it used (AR-17). The real Agent's prompts
# will be versioned files; this placeholder has one fixed version id.
PROMPT_VERSION = "placeholder-v1"


def reply(message: str) -> str:
    # The placeholder ignores the message. It only has to prove the eval pipeline works.
    return "Namaste! How can I help you today?"
