# main.py
# ReAct agent with persistent memory and human-in-the-loop approval.

import os
from langchain_core.messages import SystemMessage, HumanMessage
from agent_logic import setup_agent, SYSTEM_PROMPT

# --- Main Execution ---
if __name__ == "__main__":
    graph = setup_agent()

    print("Agent is ready. Type your question or 'quit' to exit.")
    thread_id = "default-thread"

    while True:
        print(f"\nCurrent conversation thread: {thread_id}")
        user_input = input("User: ").strip()

        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        if user_input.lower().startswith("switch to "):
            thread_id = user_input.split("switch to ", 1)[1].strip()
            print(f"Switched to conversation thread: {thread_id}")
            continue

        thread_config = {"configurable": {"thread_id": thread_id}}

        current_state = graph.get_state(thread_config)
        is_new_conversation = not current_state.values or "messages" not in current_state.values
        
        messages_to_send = []
        if is_new_conversation:
            messages_to_send.append(SystemMessage(content=SYSTEM_PROMPT))
        messages_to_send.append(HumanMessage(content=user_input))

        print("\n--- Agent Thinking ---")
        try:
            for step in graph.stream(
                {"messages": messages_to_send},
                config=thread_config
            ):
                print(step)
            
            agent_state = graph.get_state(thread_config)
            if agent_state and agent_state.next:
                print("\n--- Human Approval Required ---")
                last_message = agent_state.values['messages'][-1]
                if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                    tool_call = last_message.tool_calls[0]
                    print(f"Agent wants to run: {tool_call['name']}(args={tool_call['args']})")

                    approval = input("Do you approve? (yes/no): ").strip().lower()

                    if approval == 'yes':
                        print("--- Approved. Continuing execution. ---")
                        for step in graph.stream(None, config=thread_config):
                            print(step)
                    else:
                        print("--- Aborted by user. ---")
                else:
                    print("State indicates next step but no tool call found.")

        except Exception as e:
            print(f"Error: {e}")
        
        print("--- Turn Complete ---")