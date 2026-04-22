import pexpect
import sys

def run_test():
    # Command to run hermes chat inside the container
    cmd = "podman exec -it -u hermes hermes-agent /opt/hermes/.venv/bin/python /opt/hermes/hermes chat"
    
    print(f"Executing: {cmd}")
    child = pexpect.spawn(cmd, encoding='utf-8', timeout=60)
    
    # Enable logging to see the output
    child.logfile = sys.stdout

    try:
        # Wait for the prompt or the header to finish
        child.expect("Welcome to Hermes Agent!")
        
        # Send the command
        print("\nSending command to agent...")
        child.sendline('Check the uptime of the host "test-server"')
        
        # We expect the agent to use a tool or provide a response
        # Wait for a potential tool call or final response
        child.expect("Goodbye!", timeout=60)
        
    except pexpect.TIMEOUT:
        print("\nTest timed out waiting for response.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        child.close()

if __name__ == "__main__":
    run_test()
