import hrequests

# Function: Simple GET request


def simple_get_request(url):
    """Perform a simple GET request using hrequests."""
    response = hrequests.get(url)
    return {
        "url": response.url,
        "status_code": response.status_code,
        "reason": response.reason,
        "ok": response.ok,
        "text_preview": response.text[:100],  # Preview of the text
        "json_data": response.json() if response.headers.get('Content-Type', '').startswith('application/json') else None,
    }

# Function: Create a session


def create_session(browser="chrome", version=None, os=None):
    """Create a session with specified browser, version, and OS."""
    session = hrequests.Session(browser=browser, version=version, os=os)
    return session

# Function: Perform GET request with a session


def session_get_request(session, url):
    """Perform a GET request using a session."""
    response = session.get(url)
    return {
        "url": response.url,
        "status_code": response.status_code,
        "reason": response.reason,
        "ok": response.ok,
        "text_preview": response.text[:100],  # Preview of the text
        "cookies": session.cookies,
    }

# Function: Update session headers


def update_session_headers(session, os_type):
    """Update the session headers based on the OS type."""
    session.os = os_type
    session.headers = session.generate_headers()  # Regenerate headers
    return session.headers

# Function: Close session


def close_session(session):
    """Close the session."""
    session.close()
    return "Session closed."

# Function: Context manager example


def session_context_manager_example(url):
    """Perform a GET request using a session in a context manager."""
    with hrequests.Session() as session:
        response = session.get(url)
        return {
            "url": response.url,
            "status_code": response.status_code,
            "reason": response.reason,
            "ok": response.ok,
        }


# Sample Usage
if __name__ == "__main__":
    # Simple GET Request
    print("Simple GET Request Example:")
    simple_result = simple_get_request(
        "https://jsonplaceholder.typicode.com/todos/1")
    print(simple_result)

    # Session Example
    print("\nSession Example:")
    session = create_session(browser="firefox", os="win")
    session_result = session_get_request(
        session, "https://jsonplaceholder.typicode.com/posts")
    print(session_result)

    # Update Session Headers
    print("\nUpdated Headers Example:")
    updated_headers = update_session_headers(session, os_type="mac")
    print(updated_headers)

    # Closing Session
    print("\nClosing Session:")
    print(close_session(session))

    # Context Manager Example
    print("\nContext Manager Example:")
    context_result = session_context_manager_example(
        "https://jsonplaceholder.typicode.com/users")
    print(context_result)
