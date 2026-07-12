import streamlit as st
from Agent import run_agent

with st.sidebar:
    api_key = st.text_input("Gemini API Key", key="chatbot_api_key", type="password")
    "[Get a Gemini API key](https://aistudio.google.com/app/apikey)"

st.title("ASX Financial Reports Chatbot")
st.write("Powered by Google Antigravity Agent API")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message.get("thoughts"):
            with st.expander("Agent Thinking Process", expanded=False):
                st.markdown(message["thoughts"])
        if message.get("content"):
            st.markdown(message["content"])

def get_stream(prompt, api_key):
    result = run_agent(prompt, api_key=api_key)
    yield ('text', result)


# Accept user input
if prompt := st.chat_input("Ask a question about ASX-listed Australian companies..."):
    if not api_key:
        st.info("Please add your Gemini API key to continue.")
        st.stop()

    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        thought_container = st.empty()
        text_placeholder = st.empty()
        
        full_text = ""
        full_thoughts = ""
        thought_expander = None
        thought_placeholder = None
        
        for chunk_type, content in get_stream(prompt, api_key):
            if chunk_type == 'thought':
                if thought_expander is None:
                    with thought_container:
                        thought_expander = st.expander("Agent Thinking Process", expanded=False)
                        thought_placeholder = thought_expander.empty()
                full_thoughts += content
                thought_placeholder.markdown(full_thoughts)
            elif chunk_type == 'text':
                full_text += content
                text_placeholder.markdown(full_text + "▌")
                
        # Final update to remove the cursor
        if full_text:
            text_placeholder.markdown(full_text)
    
    # Add assistant response to chat history
    st.session_state.messages.append({
        "role": "assistant", 
        "content": full_text,
        "thoughts": full_thoughts
    })
