from langchain_classic.memory import ConversationBufferMemory

def create_conversation_memory():
    """
    Creates and returns a ConversationBufferMemory instance for future chatbot/UI integration.
    """
    return ConversationBufferMemory(memory_key="chat_history", return_messages=True)
