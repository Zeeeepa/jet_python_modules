import os
import json
from jet.logger import logger
from jet.transformers import make_serializable


def load_json(file_path):
    """Load existing results from the JSON file."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        return {}


def merge_json(existing_json, new_results):
    """
    Recursively merge two data structures.
    Handles both dictionaries and lists.
    """
    if isinstance(new_results, dict):
        for key, value in new_results.items():
            if key in existing_json and isinstance(existing_json[key], dict) and isinstance(value, dict):
                existing_json[key] = merge_json(existing_json[key], value)
            else:
                existing_json[key] = value
    elif isinstance(new_results, list):
        if not isinstance(existing_json, list):
            existing_json = []
        for i in range(min(len(existing_json), len(new_results))):
            existing_json[i] = merge_json(existing_json[i], new_results[i])
        if len(existing_json) < len(new_results):
            existing_json.extend(new_results[len(existing_json):])
    else:
        existing_json = new_results
    return existing_json


def save_json(results, file_path="generated/results.json"):
    """
    Save results to a JSON file, merging with existing results if the file exists.
    """
    try:
        # Serialize results
        results = make_serializable(results)

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Load existing results
        existing_json = load_json(file_path)

        # Merge existing results with new results
        merged_results = merge_json(existing_json, results)

        # Save the merged results to the file
        with open(file_path, "w") as f:
            json.dump(merged_results, f, indent=2, sort_keys=True)

        # Log success message
        logger.log("Results saved to", file_path,
                   colors=["GRAY", "BRIGHT_SUCCESS"])

    except Exception as e:
        logger.log(f"Error saving results:", str(e), colors=["GRAY", "RED"])
        raise e


def save_file(data: str | dict | list, output_file: str):
    import os
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Write to file
    try:
        if output_file.endswith(".json"):
            if isinstance(data, str):
                data = json.loads(data)
            else:
                data = make_serializable(data)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.log(
                "Save JSON data to:",
                output_file,
                colors=["LOG", "BRIGHT_SUCCESS"]
            )
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(data)
            logger.log(
                "Save data to:",
                output_file,
                colors=["LOG", "BRIGHT_SUCCESS"]
            )
    except Exception as e:
        logger.error(f"Failed to save file: {e}")


def main():
    # Define file path
    file_dir = os.path.dirname(os.path.abspath(__file__))
    file_path1 = os.path.join(file_dir, "generated/results1.json")
    file_path2 = os.path.join(file_dir, "generated/results2.json")
    """Example usage of saving results to JSON."""
    sample_results_1 = {
        "session_data": [
            "item1",
            2,
            {
                "item3": {
                    "task1": {"status": "completed", "details": {"time": "2 hours"}},
                    "task2": {"status": "pending", "priority": "high"},
                },
            }
        ]
    }
    sample_results_2 = [
        {
            "user_data": {
                "id": 1,
                "name": "John Doe",
                "preferences": {
                    "theme": True,
                    "notifications": "dark"
                }
            },
        }
    ]
    save_json(sample_results_1, file_path=file_path1)
    save_json(sample_results_2, file_path=file_path2)


if __name__ == "__main__":
    main()
