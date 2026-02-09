# app/cache/serialize.py
import json
from typing import Any


def serialize(data: Any) -> str:
    """
    Serialize data to a JSON string.

    Args:
        data (Any): The data to serialize.

    Returns:
        str: The JSON string representation of the data.
    """
    return json.dumps(data, default=str)


def deserialize(data: str) -> Any:
    """
    Deserialize data from a JSON string.

    Args:
        data (str): The JSON string to deserialize.

    Returns:
        Any: The deserialized data.
    """
    return json.loads(data)
