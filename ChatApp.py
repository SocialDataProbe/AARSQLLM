import streamlit as st
from Agent import run_agent, run_context_gatherer

with st.sidebar:
    api_key = st.text_input("Gemini API Key", key="chatbot_api_key", type="password")
    "[Get a Gemini API key](https://aistudio.google.com/app/apikey)"

    st.divider()

    with st.expander("🔍 Context Gatherer", expanded=False):
        st.caption("Search the web for context on any topic using the AI agent.")
        topic = st.text_input(
            "Topic",
            placeholder="e.g. Woolworths Group financial outlook 2024",
            key="context_topic",
        )
        if st.button("Search", key="context_search_btn", use_container_width=True):
            if not api_key:
                st.warning("Please enter your Gemini API key above first.")
            elif not topic.strip():
                st.warning("Please enter a topic to search.")
            else:
                with st.spinner("Gathering context..."):
                    try:
                        result = run_context_gatherer(topic.strip(), api_key=api_key)
                        st.session_state["context_result"] = result
                    except Exception as e:
                        st.session_state["context_result"] = f"Error: {e}"

        if "context_result" in st.session_state and st.session_state["context_result"]:
            st.text_area(
                "Result (copy below)",
                value=st.session_state["context_result"],
                height=300,
                key="context_output",
            )

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
    stream = run_agent(prompt, api_key=api_key)
    
    for event in stream:
        if getattr(event, 'event_type', None) == 'step.delta':
            delta = getattr(event, 'delta', None)
            if delta is not None:
                delta_type = getattr(delta, 'type', None)
                # Check for thought summary
                if delta_type == 'thought_summary':
                    content = getattr(delta, 'content', None)
                    if content is not None:
                        text_val = getattr(content, 'text', '')
                        if text_val:
                            yield ('thought', f"{text_val}")
                # Check for code execution call
                elif delta_type == 'code_execution_call':
                    code = getattr(getattr(delta, 'arguments', None), 'code', '')
                    if code:
                        yield ('thought', f"\n\n```python\n{code}\n```\n\n")
                # Check for code execution result
                elif delta_type == 'code_execution_result':
                    result = getattr(delta, 'result', '')
                    if result:
                        yield ('thought', f"\n\n```text\n{result}\n```\n\n")
                # Check for function call arguments
                elif delta_type == 'arguments_delta':
                    args = getattr(delta, 'arguments', '')
                    if args:
                        yield ('thought', f"{args}")
                # Check for standard text output
                elif delta_type == 'text':
                    text_val = getattr(delta, 'text', '')
                    if text_val:
                        yield ('text', text_val)


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
