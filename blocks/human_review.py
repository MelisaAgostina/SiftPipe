import json
import os

from blocks.targets import MATTERMOST, result_path


def build_b6_result(payloads, comment=""):
    """The pipeline_results["B6"] shape both the console review path and
    POST /api/validate produce - shared instead of each building the same
    dict inline."""
    return {
        "status": "complete",
        "total_validated": len(payloads),
        "payloads": payloads,
        "comment": comment,
    }


def save_validated_payloads(target_profile, payloads, comment=""):
    """Writes validated_payloads.json in the shape B7 (execute_attacks ->
    dynamic_injector.run_payloads) expects, and returns the pipeline_results
    ["B6"] entry - the one contract previously reimplemented independently
    by api.py's /api/validate endpoint."""
    os.makedirs("results", exist_ok=True)
    path = result_path(target_profile.name, "validated_payloads.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"status": "complete", "payloads": payloads, "comment": comment}, f, indent=4)
    return build_b6_result(payloads, comment)


def run_human_review(pipeline_results, target_profile=None):
    target_profile = target_profile or MATTERMOST
    print("\n[B6] PAYLOAD REVIEW - intentional pause.")

    # Where B5 left the payloads and where B6 expects the validated ones
    b5_output = result_path(target_profile.name, "B5_payloads.json")
    b6_input = result_path(target_profile.name, "validated_payloads.json")

    # Console stand-in for the frontend's review step
    input(
        f"-> Please review {b5_output}, filter out any attacks you do not want, save the rest as {b6_input} and press Enter to continue..."
    )

    if not os.path.exists(b6_input):
        print(f"[-] Error: {b6_input} not found. Create it to continue.")
        return

    with open(b6_input, encoding="utf-8") as f:
        validated_payloads = json.load(f)

    # Store in the central results dict
    pipeline_results["B6"] = build_b6_result(validated_payloads)

    print(f"[+] B6 complete. Payloads ready to attack: {len(validated_payloads)}\n")
