import streamlit as st
from Agent import run_agent, run_context_gatherer

# Initialize session state for the active environment ID
if "active_env_id" not in st.session_state:
    st.session_state.active_env_id = None

with st.sidebar:
    api_key = st.text_input("Gemini API Key", key="chatbot_api_key", type="password")
    "[Get a Gemini API key](https://aistudio.google.com/app/apikey)"
    
    st.divider()
    
    # WORKFLOW STEP 1: The UI
    st.subheader("Environment Settings")
    manual_env_id = st.text_input(
        "Resume Environment ID (Optional)", 
        help="Paste an ID from a previous session to resume it. Leave blank to start fresh."
    )

    # Create an empty placeholder for the Environment ID
    env_id_placeholder = st.empty()
    
    # Display the active ID so the user can copy it for next time
    if st.session_state.active_env_id:
        env_id_placeholder.success(f"**Current Environment ID:**\n`{st.session_state.active_env_id}`\n\n*Copy this to resume your session later!*")

    if st.button("Clear API Key & Chat"):
        st.session_state.chatbot_api_key = ""
        st.session_state.messages = []
        st.session_state.active_env_id = None # Clear the ID too
        st.rerun()
        
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
                    except Exception as e:
                        result = f"Error: {e}"
                    # Write straight into the widget's OWN key. This must
                    # happen before the text_area below is instantiated on
                    # this rerun, otherwise Streamlit will keep showing
                    # whatever the widget already had from the previous run.
                    st.session_state["context_output"] = result

        if st.session_state.get("context_output"):
            st.text_area(
                "Result (copy below)",
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

def get_stream(prompt, api_key, env_id):
    stream = run_agent(prompt, api_key=api_key, env_id=env_id)

    for event in stream:
        # 1. Extract the environment ID from our custom dictionary
        if isinstance(event, dict) and event.get("type") == "env_id":
            if not st.session_state.active_env_id:
                st.session_state.active_env_id = event["id"]
            continue

        # 2. Process the text and thought deltas
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

    # If the user pasted an ID in the sidebar, use that. 
    # Otherwise, use the one we saved in session state (if any).
    target_env_id = manual_env_id if manual_env_id else st.session_state.active_env_id

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

        for chunk_type, content in get_stream(prompt, api_key, target_env_id):
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

    if st.session_state.active_env_id:
        env_id_placeholder.success(f"**Current Environment ID:**\n`{st.session_state.active_env_id}`\n\n*Copy this to resume your session later!*")