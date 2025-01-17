from enum import Enum
import json
import base64
import numpy as np
import json
import base64
import numpy as np
from pydantic.main import BaseModel
from jet.validation.object import is_iterable_but_not_primitive


def make_serializable(obj):
    """
    Recursively converts an object's attributes to be serializable.
    Args:
        obj: The input object to process.
    Returns:
        A serializable representation of the object.
    """

    if isinstance(obj, Enum):
        return obj.value  # Convert Enum to its value
    elif isinstance(obj, (int, float, bool, type(None))):
        return obj
    elif isinstance(obj, str):
        try:
            # Avoid parsing strings that look like numbers or booleans
            parsed_obj = json.loads(obj)
            if isinstance(parsed_obj, (dict, list)):  # Only parse JSON objects or arrays
                return parsed_obj
            return obj  # Keep as string if it's a valid number or boolean
        except json.JSONDecodeError:
            return obj
    elif isinstance(obj, bytes):
        try:
            decoded_str = obj.decode('utf-8')
        except UnicodeDecodeError:
            decoded_str = base64.b64encode(obj).decode('utf-8')
        return make_serializable(decoded_str)

    elif isinstance(obj, BaseModel):
        return make_serializable(vars(obj))
    elif isinstance(obj, (np.integer, np.floating)):
        return obj.item()  # Convert numpy types to native Python types
    elif isinstance(obj, np.ndarray):
        return obj.tolist()  # Convert numpy arrays to lists
    elif is_iterable_but_not_primitive(obj, 'dict'):
        return {key: make_serializable(value) for key, value in obj.items()}
    elif is_iterable_but_not_primitive(obj, 'list'):
        return [make_serializable(item) for item in obj]
    elif is_iterable_but_not_primitive(obj, 'set'):
        return [make_serializable(item) for item in obj]
    elif hasattr(obj, "__dict__"):
        return make_serializable(vars(obj))
    elif isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, list):
        return [make_serializable(item) for item in obj]
    elif isinstance(obj, dict):
        return {make_serializable(key): make_serializable(value) for key, value in obj.items()}
    else:
        return str(obj)  # Fallback for unsupported types


# Example usage
if __name__ == "__main__":
    byte_val = b'{"model": "llama3.2:latest"}'
    dict_bytes_val = {
        "key":  byte_val,
        "nested_bytes": {
            "nested_key":  byte_val
        }
    }
    obj = {
        "list": [4, 2, 3, 2, 5],
        "list_bytes": [byte_val, dict_bytes_val],
        "tuple": (4, 2, 3, 2, 5),
        "tuple_bytes": (byte_val, dict_bytes_val),
        "set": {4, 2, 3, 2, 5},
        "set_bytes": {byte_val, byte_val},
        "dict_bytes": dict_bytes_val
    }
    serializable_obj = make_serializable(obj)

    # Serialize to JSON for testing
    json_data = json.dumps(serializable_obj, indent=2)
    print(json_data)
