from openai_client import send_training_to_openai
from attackpoint_client import get_report, write_note

if __name__ == "__main__":
    training_data = get_report()
        
    roundup = send_training_to_openai(
        training_input=training_data.to_json(orient="records", date_format="iso")
    )

    write_note(roundup)