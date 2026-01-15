import csv
import json

from models.job_listing import JobListing


def is_duplicate_job(job_name: str, seen_names: set) -> bool:
    return job_name in seen_names


def is_complete_job(job: dict, required_keys: list) -> bool:
    return all(key in job for key in required_keys)


def save_jobs_to_csv(jobs: list, filename: str):
    if not jobs:
        print("No jobs to save.")
        return

    # Use field names from the job model
    fieldnames = JobListing.model_fields.keys()

    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs)
    print(f"Saved {len(jobs)} jobs to '{filename}'.")


def save_jobs_to_json(jobs: list, filename: str):
    if not jobs:
        print("No jobs to save.")
        return

    with open(filename, "w", encoding="utf-8") as file:
        json.dump(jobs, file, ensure_ascii=False, indent=4)
    print(f"Saved {len(jobs)} jobs to '{filename}'.")
